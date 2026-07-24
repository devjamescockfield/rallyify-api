from datetime import UTC, datetime, timedelta
import logging
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
import jwt
import pytest

from routing.models import CompletedDrive, FuelEconomyRecord, VehicleProfile
from routing.throttles import (
    UserDataIPThrottle,
    UserDataUserBurstThrottle,
    UserDataUserDailyThrottle,
)


pytestmark = pytest.mark.django_db

ISSUER = "https://project-ref.supabase.co/auth/v1"
AUDIENCE = "authenticated"


@pytest.fixture(scope="module")
def signing_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def authenticated_api(settings, monkeypatch, signing_keys):
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


def auth_header(private_key, subject):
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": datetime.now(UTC) + timedelta(minutes=10),
        "iat": datetime.now(UTC),
        "role": "authenticated",
        "sub": str(subject),
    }
    token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "test"},
    )
    return f"Bearer {token}"


def authorize(client, private_key, subject=None):
    subject = subject or uuid.uuid4()
    client.defaults["HTTP_AUTHORIZATION"] = auth_header(private_key, subject)
    return subject


def vehicle_payload(**overrides):
    payload = {
        "displayName": "Touring car",
        "make": "Example",
        "model": "Roadster",
        "year": 2022,
        "registration": "PRIVATE-REG",
        "fuelType": "petrol",
        "vehicleCategory": "medium_car",
        "tankCapacityLitres": 50,
        "typicalMpgUk": 40,
        "economyBaselineSource": "user_entered",
        "isDefault": True,
    }
    payload.update(overrides)
    return payload


def drive_payload(*, vehicle_id=None, completion_id="completion-1", **overrides):
    payload = {
        "completionId": completion_id,
        "vehicleNameSnapshot": "Touring car",
        "routeTitleSnapshot": "Highlands day one",
        "routeId": "route-123",
        "mode": "solo",
        "startedAt": "2026-07-24T08:00:00Z",
        "finishedAt": "2026-07-24T10:00:00Z",
        "elapsedSeconds": 7200,
        "movingSeconds": 6300,
        "stoppedSeconds": 900,
        "actualDistanceMetres": 100_000,
        "plannedDistanceMetres": 98_000,
        "completionReason": "arrived",
        "rerouteCount": 1,
        "offRouteCount": 2,
    }
    if vehicle_id:
        payload["vehicleId"] = str(vehicle_id)
    payload.update(overrides)
    return payload


def create_vehicle(client, **overrides):
    return client.post(
        "/v1/vehicles",
        vehicle_payload(**overrides),
        content_type="application/json",
    )


def create_drive(client, **overrides):
    return client.post(
        "/v1/drives",
        drive_payload(**overrides),
        content_type="application/json",
    )


@pytest.mark.parametrize(
    "path,method",
    [
        ("/v1/vehicles", "get"),
        ("/v1/vehicles", "post"),
        ("/v1/drives", "get"),
        ("/v1/drives", "post"),
    ],
)
def test_user_data_endpoints_require_authentication(client, path, method):
    response = getattr(client, method)(path, {}, content_type="application/json")
    assert response.status_code == 401


def test_vehicle_create_update_and_owner_is_derived(client, signing_keys):
    private_key, _ = signing_keys
    owner = authorize(client, private_key)
    response = create_vehicle(client, ownerId=str(uuid.uuid4()))

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"

    response = create_vehicle(client)
    assert response.status_code == 201
    vehicle = VehicleProfile.objects.get(id=response.json()["id"])
    assert vehicle.owner_id == owner
    assert response.json()["registration"] == "PRIVATE-REG"

    update = client.patch(
        f"/v1/vehicles/{vehicle.id}",
        {"displayName": "Updated touring car"},
        content_type="application/json",
    )
    assert update.status_code == 200
    assert update.json()["displayName"] == "Updated touring car"


def test_vehicle_ownership_is_enforced(client, signing_keys):
    private_key, _ = signing_keys
    first_owner = authorize(client, private_key)
    vehicle = VehicleProfile.objects.create(
        owner_id=first_owner,
        display_name="Private",
        fuel_type="petrol",
        vehicle_category="medium_car",
    )
    authorize(client, private_key, uuid.uuid4())

    assert client.get(f"/v1/vehicles/{vehicle.id}").status_code == 404
    assert (
        client.patch(
            f"/v1/vehicles/{vehicle.id}",
            {"displayName": "Nope"},
            content_type="application/json",
        ).status_code
        == 404
    )
    assert client.delete(f"/v1/vehicles/{vehicle.id}").status_code == 404


def test_only_one_default_vehicle_per_owner(client, signing_keys):
    private_key, _ = signing_keys
    authorize(client, private_key)
    first = create_vehicle(client)
    second = create_vehicle(
        client,
        displayName="Second car",
        registration="",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert VehicleProfile.objects.filter(is_default=True).count() == 1
    assert str(VehicleProfile.objects.get(is_default=True).id) == second.json()["id"]

    response = client.post(f"/v1/vehicles/{first.json()['id']}/set-default")
    assert response.status_code == 200
    assert VehicleProfile.objects.filter(is_default=True).count() == 1
    assert VehicleProfile.objects.get(is_default=True).id == uuid.UUID(
        first.json()["id"]
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"year": 1800},
        {"year": datetime.now().year + 2},
        {"tankCapacityLitres": 301},
        {"batteryCapacityKwh": 301},
        {"typicalMpgUk": 501},
        {"typicalLitresPer100Km": 101},
    ],
)
def test_vehicle_numeric_limits(client, signing_keys, overrides):
    private_key, _ = signing_keys
    authorize(client, private_key)
    response = create_vehicle(client, **overrides)
    assert response.status_code == 400


def test_vehicle_count_limit(client, signing_keys, settings):
    private_key, _ = signing_keys
    owner = authorize(client, private_key)
    settings.USER_DATA_MAX_VEHICLES = 1
    VehicleProfile.objects.create(
        owner_id=owner,
        display_name="Existing",
        fuel_type="petrol",
        vehicle_category="medium_car",
    )
    response = create_vehicle(client)
    assert response.status_code == 409
    assert response.json()["code"] == "VEHICLE_LIMIT_REACHED"


def test_drive_create_stores_canonical_metrics_without_trace(client, signing_keys):
    private_key, _ = signing_keys
    owner = authorize(client, private_key)
    response = create_drive(client)

    assert response.status_code == 201
    assert response.json()["averageOverallSpeedMps"] == "13.889"
    assert response.json()["averageMovingSpeedMps"] == "15.873"
    drive = CompletedDrive.objects.get(id=response.json()["id"])
    model_fields = {field.name for field in CompletedDrive._meta.fields}
    assert "trace" not in model_fields
    assert "start_location" not in model_fields
    assert "destination" not in model_fields
    assert drive.owner_id == owner

    unsafe = drive_payload(
        completion_id="completion-unsafe",
        routeGeometry=[[0, 0], [1, 1]],
    )
    rejected = client.post(
        "/v1/drives",
        unsafe,
        content_type="application/json",
    )
    assert rejected.status_code == 400


def test_drive_uses_owned_vehicle_and_preserves_snapshot_on_delete(
    client,
    signing_keys,
):
    private_key, _ = signing_keys
    authorize(client, private_key)
    vehicle_response = create_vehicle(client)
    response = create_drive(client, vehicle_id=vehicle_response.json()["id"])

    assert response.status_code == 201
    drive_id = response.json()["id"]
    assert response.json()["vehicleNameSnapshot"] == "Touring car"
    assert client.delete(f"/v1/vehicles/{vehicle_response.json()['id']}").status_code == 204

    drive = CompletedDrive.objects.get(id=drive_id)
    assert drive.vehicle_id is None
    assert drive.vehicle_name_snapshot == "Touring car"


def test_drive_cannot_reference_another_users_vehicle(client, signing_keys):
    private_key, _ = signing_keys
    first = authorize(client, private_key)
    vehicle = VehicleProfile.objects.create(
        owner_id=first,
        display_name="First user's vehicle",
        fuel_type="petrol",
        vehicle_category="medium_car",
    )
    authorize(client, private_key, uuid.uuid4())
    response = create_drive(client, vehicle_id=vehicle.id)
    assert response.status_code == 400


def test_drive_idempotency_and_conflict(client, signing_keys):
    private_key, _ = signing_keys
    authorize(client, private_key)
    first = create_drive(client)
    retry = create_drive(client)
    conflict = create_drive(client, actualDistanceMetres=101_000)

    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True
    assert retry.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "COMPLETION_ID_REUSED"
    assert CompletedDrive.objects.count() == 1


def test_drive_idempotency_normalizes_empty_optional_fields(client, signing_keys):
    private_key, _ = signing_keys
    authorize(client, private_key)
    payload = drive_payload(completion_id="normalized")
    payload.pop("plannedDistanceMetres")
    first = client.post("/v1/drives", payload, content_type="application/json")
    payload["plannedDistanceMetres"] = None
    retry = client.post("/v1/drives", payload, content_type="application/json")

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True


def test_completion_id_is_scoped_per_owner(client, signing_keys):
    private_key, _ = signing_keys
    authorize(client, private_key)
    first = create_drive(client)
    authorize(client, private_key, uuid.uuid4())
    second = create_drive(client)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_drive_history_is_owned_and_paginated(client, signing_keys, settings):
    private_key, _ = signing_keys
    first_owner = authorize(client, private_key)
    for index in range(3):
        response = create_drive(
            client,
            completion_id=f"first-{index}",
            routeTitleSnapshot=f"First {index}",
        )
        assert response.status_code == 201
    authorize(client, private_key, uuid.uuid4())
    create_drive(client, completion_id="second-owner")

    settings.DRIVE_HISTORY_DEFAULT_PAGE_SIZE = 2
    response = client.get("/v1/drives?pageSize=2")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert len(response.json()["results"]) == 1
    assert CompletedDrive.objects.filter(owner_id=first_owner).count() == 3


def test_drive_legacy_optional_fields_and_delete(client, signing_keys):
    private_key, _ = signing_keys
    authorize(client, private_key)
    payload = drive_payload()
    for field in (
        "vehicleNameSnapshot",
        "routeTitleSnapshot",
        "routeId",
        "plannedDistanceMetres",
        "rerouteCount",
        "offRouteCount",
    ):
        payload.pop(field, None)
    response = client.post("/v1/drives", payload, content_type="application/json")
    assert response.status_code == 201
    assert response.json()["plannedDistanceMetres"] is None
    assert client.delete(f"/v1/drives/{response.json()['id']}").status_code == 204
    assert not CompletedDrive.objects.exists()


def test_user_cannot_read_another_users_drive(client, signing_keys):
    private_key, _ = signing_keys
    first = authorize(client, private_key)
    drive = CompletedDrive.objects.create(
        owner_id=first,
        completion_id="private",
        payload_fingerprint="a" * 64,
        mode="solo",
        started_at=datetime.now(UTC) - timedelta(hours=1),
        finished_at=datetime.now(UTC),
        elapsed_seconds=3600,
        moving_seconds=3600,
        stopped_seconds=0,
        actual_distance_metres=50_000,
        average_overall_speed_mps=13.889,
        average_moving_speed_mps=13.889,
        completion_reason="arrived",
    )
    authorize(client, private_key, uuid.uuid4())
    assert client.get(f"/v1/drives/{drive.id}").status_code == 404
    assert client.get("/v1/drives").json()["count"] == 0


def test_user_data_rate_limit_uses_authenticated_user(
    client,
    signing_keys,
    monkeypatch,
):
    private_key, _ = signing_keys
    monkeypatch.setattr(UserDataUserBurstThrottle, "get_rate", lambda self: "1/hour")
    monkeypatch.setattr(UserDataUserDailyThrottle, "get_rate", lambda self: "100/hour")
    monkeypatch.setattr(UserDataIPThrottle, "get_rate", lambda self: "100/hour")
    authorize(client, private_key)
    assert client.get("/v1/vehicles").status_code == 200
    assert client.get("/v1/vehicles").status_code == 429


def test_registration_is_not_logged(client, signing_keys, caplog):
    private_key, _ = signing_keys
    authorize(client, private_key)
    with caplog.at_level(logging.INFO):
        response = create_vehicle(client, registration="SECRET-REG")
    assert response.status_code == 201
    assert "SECRET-REG" not in caplog.text


def test_oversized_user_data_request_is_rejected(client, signing_keys, settings):
    private_key, _ = signing_keys
    authorize(client, private_key)
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 100
    response = create_vehicle(client, displayName="x" * 100)
    assert response.status_code == 413


def test_fuel_used_entry_uses_uk_gallons_and_updates_one_record(
    client,
    signing_keys,
):
    private_key, _ = signing_keys
    authorize(client, private_key)
    drive = create_drive(client)
    url = f"/v1/drives/{drive.json()['id']}/fuel"
    first = client.put(
        url,
        {"calculationMethod": "fuel_used_entry", "fuelUsedLitres": 10},
        content_type="application/json",
    )
    second = client.put(
        url,
        {"calculationMethod": "fill_to_fill", "fuelUsedLitres": 8},
        content_type="application/json",
    )

    assert first.status_code == 200
    assert first.json()["calculatedMpgUk"] == pytest.approx(28.2481, rel=1e-4)
    assert first.json()["calculatedLitresPer100Km"] == 10.0
    assert first.json()["displayMpgUk"] == 28.2
    assert second.status_code == 200
    assert FuelEconomyRecord.objects.count() == 1
    assert second.json()["calculationMethod"] == "fill_to_fill"


def test_fuel_level_estimate_and_invalid_percentages(client, signing_keys):
    private_key, _ = signing_keys
    authorize(client, private_key)
    drive = create_drive(client)
    url = f"/v1/drives/{drive.json()['id']}/fuel"
    valid = client.put(
        url,
        {
            "calculationMethod": "fuel_level_estimate",
            "startFuelPercent": 80,
            "endFuelPercent": 70,
            "tankCapacityLitres": 50,
        },
        content_type="application/json",
    )
    invalid = client.put(
        url,
        {
            "calculationMethod": "fuel_level_estimate",
            "startFuelPercent": 50,
            "endFuelPercent": 60,
            "tankCapacityLitres": 50,
        },
        content_type="application/json",
    )
    assert valid.status_code == 200
    assert valid.json()["estimated"] is True
    assert valid.json()["fuelUsedLitres"] == 5.0
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_ECONOMY_INPUT"


def test_profile_estimate_requires_baseline_and_is_versioned(
    client,
    signing_keys,
):
    private_key, _ = signing_keys
    authorize(client, private_key)
    no_baseline = create_vehicle(
        client,
        displayName="No baseline",
        typicalMpgUk=None,
        economyBaselineSource="none",
        registration="",
    )
    drive = create_drive(client, vehicle_id=no_baseline.json()["id"])
    rejected = client.put(
        f"/v1/drives/{drive.json()['id']}/fuel",
        {"calculationMethod": "vehicle_profile_estimate"},
        content_type="application/json",
    )
    assert rejected.status_code == 400

    baseline = create_vehicle(
        client,
        displayName="Baseline car",
        registration="",
        isDefault=False,
    )
    another_drive = create_drive(
        client,
        completion_id="profile-drive",
        vehicle_id=baseline.json()["id"],
    )
    accepted = client.put(
        f"/v1/drives/{another_drive.json()['id']}/fuel",
        {"calculationMethod": "vehicle_profile_estimate"},
        content_type="application/json",
    )
    assert accepted.status_code == 200
    assert accepted.json()["estimated"] is True
    assert accepted.json()["economyModelVersion"] == "vehicle-profile-v1"
    assert accepted.json()["baselineSource"] == "user_entered"


@pytest.mark.parametrize("fuel", [0, -1, 1001])
def test_invalid_fuel_amount_is_rejected(client, signing_keys, fuel):
    private_key, _ = signing_keys
    authorize(client, private_key)
    drive = create_drive(client)
    response = client.put(
        f"/v1/drives/{drive.json()['id']}/fuel",
        {"calculationMethod": "fuel_used_entry", "fuelUsedLitres": fuel},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_zero_distance_protects_fuel_calculation(client, signing_keys):
    private_key, _ = signing_keys
    authorize(client, private_key)
    drive = create_drive(client, actualDistanceMetres=0)
    response = client.put(
        f"/v1/drives/{drive.json()['id']}/fuel",
        {"calculationMethod": "fuel_used_entry", "fuelUsedLitres": 10},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ECONOMY_INPUT"


def test_obd_method_is_reserved_but_not_implemented(client, signing_keys):
    private_key, _ = signing_keys
    authorize(client, private_key)
    drive = create_drive(client)
    response = client.put(
        f"/v1/drives/{drive.json()['id']}/fuel",
        {"calculationMethod": "obd_measured", "fuelUsedLitres": 10},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert FuelEconomyRecord.objects.count() == 0
