import uuid

import pytest
from django.core.cache import cache
from django.test import override_settings

from routing.models import RouteIssueReport
from routing.throttles import RouteReportThrottle


pytestmark = pytest.mark.django_db

AUTHORIZATION = "Bearer beta-report-token"


def report_payload(**overrides):
    payload = {
        "routeRequestId": str(uuid.uuid4()),
        "category": "wrong_way_or_one_way",
        "provider": "valhalla",
        "engineVersion": "3.7.0-test",
        "graphBuildId": "uk-2026-07-20",
        "osmDataDate": "2026-07-19",
        "roadPriority": "fastest",
        "vehicleProfile": "car",
        "distanceMetres": 50_000,
        "durationSeconds": 3600,
        "manoeuvreIndex": 12,
        "notes": "Instruction appeared to use a one-way street incorrectly.",
        "incidentTime": "2026-07-20T12:00:00Z",
        "locationConsent": False,
    }
    payload.update(overrides)
    return payload


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


@pytest.fixture(autouse=True)
def clear_report_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_authenticated_report_submission_creates_server_id(client):
    response = client.post(
        "/routes/report",
        data=report_payload(),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 201
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert str(report.route_request_id) == response.json()["routeRequestId"]
    assert report.reporter_fingerprint
    assert report.reporter_fingerprint != "beta-report-token"
    assert report.consented_location_data == {}


def test_report_submission_requires_authentication(client):
    response = client.post(
        "/routes/report",
        data=report_payload(),
        content_type="application/json",
    )

    assert response.status_code == 401


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_mobile_report_contract_is_accepted_at_app_endpoint(client):
    response = client.post(
        "/route-reports",
        data=mobile_report_payload(),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 201
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert report.category == "wrong_way_or_one_way"
    assert report.metadata["client"]["appVersion"] == "1.0.0"
    assert report.metadata["client"]["coarseArea"]["precision"] == "0.1_degree"
    assert report.consented_location_data == {}


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_mobile_consented_route_details_are_accepted(client):
    response = client.post(
        "/route-reports",
        data=mobile_report_payload(consent=True),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 201
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert report.consented_location_data["exactLocation"] == {
        "latitude": 52.062,
        "longitude": -1.34,
    }
    assert report.consented_location_data["currentManeuver"]["maneuverIndex"] == 12


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_exact_location_is_rejected_without_consent(client):
    response = client.post(
        "/routes/report",
        data=report_payload(
            exactLocation={"latitude": 52.062, "longitude": -1.34},
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 400
    assert "locationConsent" in response.json()


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_exact_location_is_stored_only_with_consent(client):
    response = client.post(
        "/routes/report",
        data=report_payload(
            locationConsent=True,
            exactLocation={"latitude": 52.062, "longitude": -1.34},
            start={"latitude": 52.06, "longitude": -1.33},
            destination={"latitude": 52.07, "longitude": -1.31},
            routeGeometry=[[-1.33, 52.06], [-1.31, 52.07]],
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 201
    report = RouteIssueReport.objects.get(report_id=response.json()["reportId"])
    assert report.location_consent is True
    assert report.consented_location_data["exactLocation"] == {
        "latitude": 52.062,
        "longitude": -1.34,
    }


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_report_notes_size_limit(client):
    response = client.post(
        "/routes/report",
        data=report_payload(notes="x" * 2001),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 400


@override_settings(
    ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"],
    DATA_UPLOAD_MAX_MEMORY_SIZE=200,
)
def test_report_request_body_size_limit(client):
    response = client.post(
        "/routes/report",
        data=report_payload(notes="x" * 100),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 413


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_duplicate_report_returns_existing_report_id(client):
    payload = report_payload()
    first = client.post(
        "/routes/report",
        data=payload,
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )
    second = client.post(
        "/routes/report",
        data=payload,
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["reportId"] == first.json()["reportId"]
    assert RouteIssueReport.objects.count() == 1


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_report_submission_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(RouteReportThrottle, "get_rate", lambda self: "2/hour")
    responses = [
        client.post(
            "/routes/report",
            data=report_payload(routeRequestId=str(uuid.uuid4())),
            content_type="application/json",
            HTTP_AUTHORIZATION=AUTHORIZATION,
        )
        for _ in range(3)
    ]

    assert [response.status_code for response in responses] == [201, 201, 429]


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_client_supplied_user_id_is_rejected(client):
    response = client.post(
        "/routes/report",
        data=report_payload(userId="untrusted-user"),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 400
    assert "userId" in response.json()


@override_settings(ROUTE_REPORT_BEARER_TOKENS=["beta-report-token"])
def test_report_logs_do_not_leak_token_or_coordinates(client, caplog):
    caplog.set_level("INFO", logger="routing.diagnostics")
    response = client.post(
        "/routes/report",
        data=report_payload(
            locationConsent=True,
            exactLocation={"latitude": 52.062, "longitude": -1.34},
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=AUTHORIZATION,
    )

    assert response.status_code == 201
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "beta-report-token" not in messages
    assert "52.062" not in messages
    assert "-1.34" not in messages
