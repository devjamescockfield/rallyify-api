from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.db import close_old_connections
from django.utils import timezone
import jwt
import pytest

from routing.authentication import _get_jwks_client
from routing.diagnostics import create_route_issue_report, purge_expired_beta_records
from routing.models import RouteIssueReport
from routing.serializers import RouteIssueReportSerializer
from routing.throttles import (
    RouteReportGlobalThrottle,
    RouteReportIPThrottle,
    RouteReportUserBurstThrottle,
    RouteReportUserHourlyThrottle,
)


pytestmark = pytest.mark.django_db

ISSUER = "https://project-ref.supabase.co/auth/v1"
AUDIENCE = "authenticated"


def mobile_report_payload(*, consent=False, **overrides):
    payload = {
        "id": "route_issue_client-1",
        "dedupeKey": "client-1",
        "category": "wrongWay",
        "description": "The instruction used a prohibited direction.",
        "roadName": "Test Street",
        "instructedDirection": "Westbound",
        "believedLegalDirection": "Eastbound only",
        "diagnostics": {
            "appVersion": "1.0.0",
            "buildProfile": "preview",
            "routeProvider": "rallyify_api",
            "routingMode": "hosted",
            "providerRequestId": str(uuid.uuid4()),
            "graphDataVersion": "uk-2026-07-20",
            "routePreference": "fastest",
            "vehicleProfile": "car",
            "routeDistanceMetres": 50_000,
            "routeDurationSeconds": 3600,
            "activeManeuverIndex": 12,
            "timestamp": "2026-07-20T12:00:00Z",
            "coarseArea": {
                "latitudeBand": 52.1,
                "longitudeBand": -1.3,
                "precision": "0.1_degree",
            },
        },
        "locationConsent": consent,
        "createdAt": "2026-07-20T12:00:00Z",
        "retryCount": 0,
    }
    if consent:
        payload["consentedRouteDetails"] = {
            "routeGeometry": [[-1.33, 52.06], [-1.31, 52.07]],
            "start": {"latitude": 52.06, "longitude": -1.33},
            "destination": {"latitude": 52.07, "longitude": -1.31},
            "approximateIncidentLocation": {
                "latitude": 52.062,
                "longitude": -1.34,
            },
            "currentManeuver": {
                "instruction": "Turn left onto Test Street.",
                "type": "15",
                "bearingAfter": 270,
                "legIndex": 0,
                "maneuverIndex": 12,
            },
        }
    payload.update(overrides)
    return payload


@pytest.fixture
def signing_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def report_authentication(settings, monkeypatch, signing_keys):
    _, public_key = signing_keys
    settings.SUPABASE_JWT_ISSUER = ISSUER
    settings.SUPABASE_JWT_AUDIENCE = AUDIENCE
    settings.SUPABASE_JWT_ALGORITHMS = ["RS256"]
    settings.SUPABASE_JWT_LEEWAY_SECONDS = 0
    monkeypatch.setattr(
        "routing.authentication.get_supabase_signing_key",
        lambda token: public_key,
    )
    cache.clear()
    yield
    cache.clear()


def make_token(
    private_key,
    *,
    subject=None,
    issuer=ISSUER,
    audience=AUDIENCE,
    expires_at=None,
):
    claims = {
        "iss": issuer,
        "aud": audience,
        "exp": expires_at or datetime.now(UTC) + timedelta(minutes=10),
        "iat": datetime.now(UTC),
        "role": "authenticated",
    }
    if subject is not None:
        claims["sub"] = str(subject)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


def authorization(private_key, subject=None, **claims):
    subject = subject or uuid.uuid4()
    return f"Bearer {make_token(private_key, subject=subject, **claims)}", subject


def post_report(client, private_key, *, subject=None, key="report-1", payload=None):
    header, subject = authorization(private_key, subject)
    response = client.post(
        "/route-reports",
        data=payload or mobile_report_payload(),
        content_type="application/json",
        HTTP_AUTHORIZATION=header,
        HTTP_IDEMPOTENCY_KEY=key,
    )
    return response, subject


def test_valid_supabase_jwt_is_accepted_and_subject_is_stored(client, signing_keys):
    private_key, _ = signing_keys
    subject = uuid.uuid4()
    response, _ = post_report(client, private_key, subject=subject)

    assert response.status_code == 201
    assert response.json() == {
        "reportId": response.json()["reportId"],
        "status": "accepted",
        "receivedAt": response.json()["receivedAt"],
        "duplicate": False,
    }
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert report.reporter_id == subject


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda key: make_token(
            key,
            subject=uuid.uuid4(),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        ),
        lambda key: make_token(key, subject=uuid.uuid4(), issuer="https://wrong.test"),
        lambda key: make_token(key, subject=uuid.uuid4(), audience="wrong-audience"),
        lambda key: make_token(key, subject=None),
    ],
    ids=["expired", "wrong-issuer", "wrong-audience", "missing-subject"],
)
def test_invalid_supabase_claims_are_rejected(client, signing_keys, token_factory):
    private_key, _ = signing_keys
    response = client.post(
        "/route-reports",
        data=mobile_report_payload(),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token_factory(private_key)}",
        HTTP_IDEMPOTENCY_KEY="report-1",
    )

    assert response.status_code == 401


def test_invalid_signature_is_rejected(client, signing_keys):
    _, _ = signing_keys
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = make_token(other_key, subject=uuid.uuid4())
    response = client.post(
        "/route-reports",
        data=mobile_report_payload(),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY="report-1",
    )

    assert response.status_code == 401


def test_shared_beta_token_is_rejected_by_default(client):
    response = client.post(
        "/route-reports",
        data=mobile_report_payload(),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer beta-report-token",
        HTTP_IDEMPOTENCY_KEY="report-1",
    )

    assert response.status_code == 401


def test_jwks_client_is_reused_within_cache_configuration():
    _get_jwks_client.cache_clear()
    first = _get_jwks_client("https://example.test/jwks", 600, 3)
    second = _get_jwks_client("https://example.test/jwks", 600, 3)

    assert first is second


def test_payload_user_id_is_ignored(client, signing_keys):
    private_key, _ = signing_keys
    verified_subject = uuid.uuid4()
    payload = mobile_report_payload(userId=str(uuid.uuid4()))
    response, _ = post_report(
        client,
        private_key,
        subject=verified_subject,
        payload=payload,
    )

    assert response.status_code == 201
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert report.reporter_id == verified_subject


def test_exact_location_requires_consent(client, signing_keys):
    private_key, _ = signing_keys
    payload = mobile_report_payload()
    payload["consentedRouteDetails"] = mobile_report_payload(consent=True)[
        "consentedRouteDetails"
    ]
    response, _ = post_report(client, private_key, payload=payload)

    assert response.status_code == 400


def test_exact_location_is_stored_with_consent(client, signing_keys):
    private_key, _ = signing_keys
    response, _ = post_report(
        client,
        private_key,
        payload=mobile_report_payload(consent=True),
    )

    assert response.status_code == 201
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert report.consented_location_data["exactLocation"]["latitude"] == 52.062


def test_duplicate_returns_409_with_required_contract(client, signing_keys):
    private_key, _ = signing_keys
    subject = uuid.uuid4()
    payload = mobile_report_payload()
    first, _ = post_report(
        client,
        private_key,
        subject=subject,
        key="same-key",
        payload=payload,
    )
    second, _ = post_report(
        client,
        private_key,
        subject=subject,
        key="same-key",
        payload=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["duplicate"] is True
    assert second.json()["status"] == "accepted"
    assert second.json()["reportId"] == first.json()["reportId"]
    assert second.json()["receivedAt"] == first.json()["receivedAt"]


def test_same_idempotency_key_is_independent_per_user(client, signing_keys):
    private_key, _ = signing_keys
    first, _ = post_report(client, private_key, subject=uuid.uuid4(), key="shared-key")
    second, _ = post_report(client, private_key, subject=uuid.uuid4(), key="shared-key")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["reportId"] != second.json()["reportId"]


def test_reused_idempotency_key_with_different_payload_is_rejected(
    client,
    signing_keys,
):
    private_key, _ = signing_keys
    subject = uuid.uuid4()
    first, _ = post_report(client, private_key, subject=subject, key="same-key")
    changed = mobile_report_payload(description="Different incident")
    second, _ = post_report(
        client,
        private_key,
        subject=subject,
        key="same-key",
        payload=changed,
    )

    assert first.status_code == 201
    assert second.status_code == 422


def test_user_throttle_is_isolated_per_verified_subject(
    client,
    monkeypatch,
    signing_keys,
):
    private_key, _ = signing_keys
    monkeypatch.setattr(RouteReportUserBurstThrottle, "get_rate", lambda self: "1/hour")
    monkeypatch.setattr(RouteReportUserHourlyThrottle, "get_rate", lambda self: "100/hour")
    monkeypatch.setattr(RouteReportIPThrottle, "get_rate", lambda self: "100/hour")
    monkeypatch.setattr(RouteReportGlobalThrottle, "get_rate", lambda self: None)
    first_user = uuid.uuid4()
    second_user = uuid.uuid4()

    first, _ = post_report(client, private_key, subject=first_user, key="first")
    second, _ = post_report(client, private_key, subject=second_user, key="second")
    limited, _ = post_report(client, private_key, subject=first_user, key="third")

    assert [first.status_code, second.status_code, limited.status_code] == [201, 201, 429]


def test_ip_throttle_applies_across_verified_users(client, monkeypatch, signing_keys):
    private_key, _ = signing_keys
    monkeypatch.setattr(RouteReportUserBurstThrottle, "get_rate", lambda self: "100/hour")
    monkeypatch.setattr(RouteReportUserHourlyThrottle, "get_rate", lambda self: "100/hour")
    monkeypatch.setattr(RouteReportIPThrottle, "get_rate", lambda self: "2/hour")
    monkeypatch.setattr(RouteReportGlobalThrottle, "get_rate", lambda self: None)

    responses = [
        post_report(client, private_key, subject=uuid.uuid4(), key=f"key-{index}")[0]
        for index in range(3)
    ]

    assert [response.status_code for response in responses] == [201, 201, 429]


@pytest.mark.django_db(transaction=True)
def test_concurrent_sqlite_report_inserts_for_different_users():
    serializer = RouteIssueReportSerializer(data=mobile_report_payload())
    serializer.is_valid(raise_exception=True)
    validated_data = serializer.validated_data

    def insert_report(subject):
        close_old_connections()
        try:
            report, duplicate = create_route_issue_report(
                validated_data=validated_data,
                reporter_id=subject,
                idempotency_key="same-key",
            )
            return report.report_id, duplicate
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(insert_report, [uuid.uuid4(), uuid.uuid4()]))

    assert len({report_id for report_id, _ in results}) == 2
    assert all(duplicate is False for _, duplicate in results)


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_user_insert_resolves_to_one_report():
    serializer = RouteIssueReportSerializer(data=mobile_report_payload())
    serializer.is_valid(raise_exception=True)
    validated_data = serializer.validated_data
    subject = uuid.uuid4()

    def insert_report(_):
        close_old_connections()
        try:
            report, duplicate = create_route_issue_report(
                validated_data=validated_data,
                reporter_id=subject,
                idempotency_key="same-user-key",
            )
            return report.report_id, duplicate
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(insert_report, range(2)))

    assert len({report_id for report_id, _ in results}) == 1
    assert sorted(duplicate for _, duplicate in results) == [False, True]


@pytest.mark.parametrize(
    ("mobile_category", "stored_category"),
    [
        ("wrongWay", "wrong_way_or_one_way"),
        ("closedRoad", "closed_or_inaccessible_road"),
        ("unsafeRoad", "unsafe_or_unsuitable_road"),
        ("unnecessarilyLong", "route_unnecessarily_long"),
        ("wrongEntrance", "wrong_destination_entrance"),
        ("incorrectInstruction", "incorrect_instruction"),
        ("other", "other"),
    ],
)
def test_all_mobile_categories_are_mapped(
    client,
    signing_keys,
    mobile_category,
    stored_category,
):
    private_key, _ = signing_keys
    response, _ = post_report(
        client,
        private_key,
        key=f"category-{mobile_category}",
        payload=mobile_report_payload(category=mobile_category),
    )
    assert response.status_code == 201
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert report.category == stored_category


def test_optional_text_fields_may_be_omitted(client, signing_keys):
    private_key, _ = signing_keys
    payload = mobile_report_payload()
    for field in (
        "description",
        "roadName",
        "instructedDirection",
        "believedLegalDirection",
    ):
        payload.pop(field)
    response, _ = post_report(client, private_key, payload=payload)
    assert response.status_code == 201


def test_unknown_nested_diagnostic_field_is_rejected(client, signing_keys):
    private_key, _ = signing_keys
    payload = mobile_report_payload()
    payload["diagnostics"]["exactCoordinates"] = [52.0, -1.0]
    response, _ = post_report(client, private_key, payload=payload)
    assert response.status_code == 400


def test_out_of_range_consented_coordinate_is_rejected(client, signing_keys):
    private_key, _ = signing_keys
    payload = mobile_report_payload(consent=True)
    payload["consentedRouteDetails"]["approximateIncidentLocation"][
        "latitude"
    ] = 95
    response, _ = post_report(client, private_key, payload=payload)
    assert response.status_code == 400


def test_oversized_request_is_rejected(client, signing_keys, settings):
    private_key, _ = signing_keys
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 200
    response, _ = post_report(client, private_key)
    assert response.status_code == 413


def test_graph_version_is_retained(client, signing_keys):
    private_key, _ = signing_keys
    response, _ = post_report(client, private_key)
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert report.graph_version == "uk-2026-07-20"
    assert report.metadata["client"]["graphBuildId"] == "uk-2026-07-20"


def test_retention_purges_exact_data_before_summary(client, signing_keys):
    private_key, _ = signing_keys
    response, _ = post_report(
        client,
        private_key,
        payload=mobile_report_payload(consent=True),
    )
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    report.exact_data_expires_at = timezone.now() - timedelta(seconds=1)
    report.save(update_fields=["exact_data_expires_at"])

    purge_expired_beta_records()
    report.refresh_from_db()
    assert report.consented_location_data == {}
    assert report.exact_data_purged_at is not None

    report.summary_expires_at = timezone.now() - timedelta(seconds=1)
    report.save(update_fields=["summary_expires_at"])
    purge_expired_beta_records()
    assert not RouteIssueReport.objects.filter(pk=report.pk).exists()


def test_investigating_report_keeps_consented_data_until_case_retention(
    client,
    signing_keys,
):
    private_key, _ = signing_keys
    response, _ = post_report(
        client,
        private_key,
        payload=mobile_report_payload(consent=True),
    )
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    report.status = RouteIssueReport.Status.INVESTIGATING
    report.exact_data_expires_at = timezone.now() - timedelta(seconds=1)
    report.save(update_fields=["status", "exact_data_expires_at"])
    purge_expired_beta_records()
    report.refresh_from_db()
    assert report.consented_location_data


def test_report_logs_exclude_tokens_and_exact_coordinates(
    client,
    signing_keys,
    caplog,
):
    private_key, _ = signing_keys
    token = make_token(private_key, subject=uuid.uuid4())
    caplog.set_level("INFO", logger="routing.diagnostics")
    response = client.post(
        "/route-reports",
        data=mobile_report_payload(consent=True),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY="safe-log-test",
    )
    assert response.status_code == 201
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in messages
    assert "52.062" not in messages
    assert "-1.34" not in messages
