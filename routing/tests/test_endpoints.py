import json
import logging

import pytest
import requests
from django.test import override_settings

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

VALHALLA_POLYLINE6 = "o~kffBnztwHokiSnkiS"

VALHALLA_RESPONSE = {
    "trip": {
        "status": 0,
        "summary": {
            "length": 10,
            "time": 1200,
        },
        "legs": [
            {
                "shape": VALHALLA_POLYLINE6,
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
                        "type": 1,
                        "begin_heading": 15,
                        "begin_shape_index": 0,
                        "end_shape_index": 1,
                        "street_names": ["Main Street"],
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


class MockValhallaStatusResponse:
    def __init__(self, payload=None, ok=True):
        self.payload = payload or {}
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


def test_health_returns_200_when_valhalla_unavailable(client, monkeypatch):
    def get(url, timeout):
        raise requests.Timeout

    monkeypatch.setattr("routing.valhalla.requests.get", get)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["valhalla"] == {
        "configured": True,
        "reachable": False,
    }


def test_health_includes_service_name(client, monkeypatch):
    def get(url, timeout):
        raise requests.Timeout

    monkeypatch.setattr("routing.valhalla.requests.get", get)

    response = client.get("/health")

    assert response.json()["service"] == "rallyify-routing-api"


@override_settings(VALHALLA_URL="http://localhost:8002")
def test_health_reports_valhalla_reachable_with_version(client, monkeypatch):
    calls = []

    def get(url, timeout):
        calls.append({"url": url, "timeout": timeout})
        return MockValhallaStatusResponse(payload={"version": "3.5.1"})

    monkeypatch.setattr("routing.valhalla.requests.get", get)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["valhalla"] == {
        "configured": True,
        "reachable": True,
        "version": "3.5.1",
    }
    assert calls == [{"url": "http://localhost:8002/status", "timeout": 1.0}]


@override_settings(VALHALLA_URL="http://localhost:8002")
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


@pytest.mark.parametrize("road_priority", ["avoid_motorways", "prefer_b_roads"])
def test_app_road_priority_values_are_accepted(client, mock_valhalla_post, road_priority):
    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST | {"roadPriority": road_priority},
        content_type="application/json",
    )

    assert response.status_code == 200


def test_avoid_motorways_priority_reduces_highways_more_than_balanced():
    balanced_payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {"roadPriority": "balanced"}
    )
    avoid_motorways_payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {"roadPriority": "avoid_motorways"}
    )

    assert balanced_payload["costing_options"] == {}
    assert avoid_motorways_payload["costing_options"]["auto"]["use_highways"] == 0.05


def test_prefer_b_roads_changes_costing_options_compared_with_balanced():
    balanced_payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {"roadPriority": "balanced"}
    )
    prefer_b_roads_payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {"roadPriority": "prefer_b_roads"}
    )

    assert prefer_b_roads_payload["costing_options"] != balanced_payload["costing_options"]
    assert prefer_b_roads_payload["costing_options"]["auto"]["use_highways"] == 0.35


@pytest.mark.parametrize("road_priority", ["fastest", "balanced"])
def test_avoid_motorways_boolean_overrides_fastest_and_balanced(road_priority):
    payload = build_valhalla_payload(
        VALID_ROUTE_REQUEST | {
            "roadPriority": road_priority,
            "avoidMotorways": True,
        }
    )

    assert payload["costing_options"]["auto"]["use_highways"] == 0.05


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


def test_invalid_road_priority_returns_400(client):
    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST | {"roadPriority": "twisty"},
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


def test_valhalla_response_without_decodable_shape_returns_502(client, monkeypatch):
    def post(url, json, timeout):
        return MockValhallaResponse(
            payload={
                "trip": {
                    "status": 0,
                    "summary": {"length": 10, "time": 1200},
                    "legs": [{"summary": {"length": 10, "time": 1200}}],
                }
            }
        )

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
        "encodedPolyline": VALHALLA_POLYLINE6,
        "polyline": [
            [-5.123, 54.123],
            [-5.456, 54.456],
        ],
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
                        "distanceMetres": 805,
                        "type": "1",
                        "bearing_after": 15,
                        "beginShapeIndex": 0,
                        "endShapeIndex": 1,
                        "streetNames": ["Main Street"],
                    }
                ],
            }
        ],
        "waypoints": VALID_ROUTE_REQUEST["waypoints"],
        "provider": "valhalla",
        "generatedAt": response.json()["generatedAt"],
    }
    assert response.json()["generatedAt"]


def test_successful_response_contains_app_route_result_fields(
    client,
    mock_valhalla_post,
):
    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST,
        content_type="application/json",
    )

    body = response.json()

    assert isinstance(body["polyline"], list)
    assert len(body["polyline"]) >= 2
    assert all(len(coordinate) == 2 for coordinate in body["polyline"])
    assert isinstance(body["distanceMetres"], int)
    assert isinstance(body["durationSeconds"], int)
    assert isinstance(body["legs"], list)
    assert body["legs"][0]["maneuvers"] == [
        {
            "instruction": "Drive north.",
            "distanceMetres": 805,
            "type": "1",
            "bearing_after": 15,
            "beginShapeIndex": 0,
            "endShapeIndex": 1,
            "streetNames": ["Main Street"],
        }
    ]


@override_settings(ROUTE_SLOW_WARNING_MS=-1)
def test_route_calculate_logs_summary_metrics_without_geometry(
    client,
    caplog,
    mock_valhalla_post,
):
    caplog.set_level(logging.WARNING, logger="routing.views")

    response = client.post(
        "/routes/calculate",
        data=VALID_ROUTE_REQUEST,
        content_type="application/json",
    )

    assert response.status_code == 200
    record = next(
        item for item in caplog.records if item.name == "routing.views"
    )
    assert record.levelno == logging.WARNING

    message = record.getMessage()
    assert VALHALLA_POLYLINE6 not in message
    assert "54.123" not in message

    metrics = json.loads(message.split("metrics=", 1)[1])
    assert metrics["event"] == "route_calculate"
    assert metrics["status_code"] == 200
    assert metrics["waypoint_count"] == 2
    assert metrics["roadPriority"] == "balanced"
    assert metrics["vehicleProfile"] == "car"
    assert metrics["units"] == "imperial"
    assert metrics["polyline_point_count"] == 2
    assert metrics["response_size_bytes"] > 0
    assert metrics["validation_ms"] >= 0
    assert metrics["valhalla_request_ms"] >= 0
    assert metrics["normalization_ms"] >= 0
    assert metrics["response_construction_ms"] >= 0
