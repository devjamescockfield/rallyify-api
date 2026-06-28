import pytest
import requests

from routing.valhalla import build_valhalla_payload


VALID_ROUTE_REQUEST = {
    "waypoints": [
        {
            "latitude": 54.123,
            "longitude": -5.123,
            "name": "Start",
        },
        {
            "latitude": 54.456,
            "longitude": -5.456,
            "name": "Finish",
        },
    ],
    "vehicleProfile": "car",
    "roadPriority": "balanced",
    "units": "imperial",
    "avoidMotorways": False,
}


VALHALLA_RESPONSE = {
    "trip": {
        "summary": {
            "length": 10,
            "time": 1200,
        },
        "legs": [
            {
                "shape": "encoded-leg-shape",
                "summary": {
                    "length": 10,
                    "time": 1200,
                    "text": "Start to Finish",
                },
                "maneuvers": [
                    {
                        "instruction": "Drive north.",
                        "time": 60,
                        "length": 0.5,
                    }
                ],
            }
        ],
    }
}


class MockValhallaResponse:
    def __init__(self, payload=None, ok=True):
        self.payload = payload or VALHALLA_RESPONSE
        self.ok = ok

    def json(self):
        return self.payload


@pytest.fixture
def mock_valhalla_post(monkeypatch):
    calls = []

    def post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return MockValhallaResponse()

    monkeypatch.setattr("routing.valhalla.requests.post", post)
    return calls


def test_health_returns_200(client):
    response = client.get("/health")

    assert response.status_code == 200


def test_health_includes_service_name(client):
    response = client.get("/health")

    assert response.json()["service"] == "rallyify-routing-api"


def test_valid_request_calls_valhalla_route(client, mock_valhalla_post):
    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST,
        content_type="application/json",
    )

    assert response.status_code == 200
    assert mock_valhalla_post[0]["url"] == "http://localhost:8002/route"


def test_request_payload_maps_waypoints_to_lat_lon(client, mock_valhalla_post):
    client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST,
        content_type="application/json",
    )

    assert mock_valhalla_post[0]["json"]["locations"] == [
        {"lat": 54.123, "lon": -5.123, "name": "Start"},
        {"lat": 54.456, "lon": -5.456, "name": "Finish"},
    ]


@pytest.mark.parametrize(
    ("vehicle_profile", "expected_costing"),
    [
        ("car", "auto"),
        ("motorbike", "motorcycle"),
        ("caravan", "auto"),
    ],
)
def test_vehicle_profile_maps_to_valhalla_costing(vehicle_profile, expected_costing):
    request_data = VALID_ROUTE_REQUEST | {"vehicleProfile": vehicle_profile}

    payload = build_valhalla_payload(request_data)

    assert payload["costing"] == expected_costing


@pytest.mark.parametrize(
    ("units", "expected_units"),
    [
        ("metric", "kilometers"),
        ("imperial", "miles"),
    ],
)
def test_units_map_to_valhalla_directions_units(units, expected_units):
    request_data = VALID_ROUTE_REQUEST | {"units": units}

    payload = build_valhalla_payload(request_data)

    assert payload["directions_options"]["units"] == expected_units


def test_avoid_motorways_changes_costing_options():
    default_payload = build_valhalla_payload(VALID_ROUTE_REQUEST)
    avoid_payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {"avoidMotorways": True}
    )

    assert avoid_payload["costing_options"] != default_payload["costing_options"]
    assert avoid_payload["costing_options"]["auto"]["use_highways"] == 0.05


def test_scenic_changes_costing_options_compared_with_fastest_and_balanced():
    fastest_payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {"roadPriority": "fastest"}
    )
    balanced_payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {"roadPriority": "balanced"}
    )
    scenic_payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {"roadPriority": "scenic"}
    )

    assert scenic_payload["costing_options"] != fastest_payload["costing_options"]
    assert scenic_payload["costing_options"] != balanced_payload["costing_options"]
    assert scenic_payload["costing_options"]["auto"]["use_highways"] == 0.25


def test_invalid_waypoint_count_returns_400(client):
    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST | {"waypoints": VALID_ROUTE_REQUEST["waypoints"][:1]},
        content_type="application/json",
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "waypoint",
    [
        {"latitude": 91, "longitude": -5.123},
        {"latitude": 54.123, "longitude": -181},
        {"longitude": -5.123},
        {"latitude": 54.123},
    ],
)
def test_invalid_lat_lon_returns_400(client, waypoint):
    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST
        | {"waypoints": [waypoint, VALID_ROUTE_REQUEST["waypoints"][1]]},
        content_type="application/json",
    )

    assert response.status_code == 400


def test_invalid_vehicle_profile_returns_400(client):
    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST | {"vehicleProfile": "bicycle"},
        content_type="application/json",
    )

    assert response.status_code == 400


def test_valhalla_timeout_network_error_returns_502(client, monkeypatch):
    def post(url, json, timeout):
        raise requests.Timeout

    monkeypatch.setattr("routing.valhalla.requests.post", post)

    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST,
        content_type="application/json",
    )

    assert response.status_code == 502
    assert response.json()["code"] == "VALHALLA_UNAVAILABLE"


def test_valhalla_non_2xx_returns_502(client, monkeypatch):
    def post(url, json, timeout):
        return MockValhallaResponse(ok=False)

    monkeypatch.setattr("routing.valhalla.requests.post", post)

    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST,
        content_type="application/json",
    )

    assert response.status_code == 502
    assert response.json()["code"] == "VALHALLA_UNAVAILABLE"


def test_malformed_valhalla_response_returns_502(client, monkeypatch):
    def post(url, json, timeout):
        return MockValhallaResponse(payload={"unexpected": "shape"})

    monkeypatch.setattr("routing.valhalla.requests.post", post)

    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST,
        content_type="application/json",
    )

    assert response.status_code == 502
    assert response.json()["code"] == "INVALID_VALHALLA_RESPONSE"


def test_successful_response_returns_normalized_route(client, mock_valhalla_post):
    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST,
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "encodedPolyline": "encoded-leg-shape",
        "distanceMetres": 16093,
        "durationSeconds": 1200,
        "legs": [
            {
                "distanceMetres": 16093,
                "durationSeconds": 1200,
                "summary": "Start to Finish",
                "maneuvers": [
                    {
                        "instruction": "Drive north.",
                        "time": 60,
                        "length": 0.5,
                    }
                ],
            }
        ],
        "waypoints": VALID_ROUTE_REQUEST["waypoints"],
        "provider": "valhalla",
        "generatedAt": response.json()["generatedAt"],
    }
    assert response.json()["generatedAt"]
