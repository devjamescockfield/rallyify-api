from datetime import UTC, datetime

from django.conf import settings
import requests


def get_valhalla_status() -> dict[str, bool]:
    return {
        "configured": bool(settings.VALHALLA_URL),
        "reachable": False,
    }


class ValhallaUnavailableError(Exception):
    pass


class InvalidValhallaResponseError(Exception):
    pass


VEHICLE_COSTING = {
    "car": "auto",
    "motorbike": "motorcycle",
    "caravan": "auto",
}

UNIT_MAPPING = {
    "metric": "kilometers",
    "imperial": "miles",
}

DISTANCE_FACTORS_TO_METRES = {
    "metric": 1000,
    "imperial": 1609.344,
}


def build_valhalla_payload(route_request: dict) -> dict:
    costing = VEHICLE_COSTING[route_request["vehicleProfile"]]
    costing_options = _build_costing_options(
        costing=costing,
        road_priority=route_request["roadPriority"],
        avoid_motorways=route_request["avoidMotorways"],
    )

    return {
        "locations": [
            _build_location(waypoint) for waypoint in route_request["waypoints"]
        ],
        "costing": costing,
        "costing_options": costing_options,
        "directions_options": {
            "units": UNIT_MAPPING[route_request["units"]],
        },
    }


def calculate_route(route_request: dict) -> dict:
    payload = build_valhalla_payload(route_request)
    url = f"{settings.VALHALLA_URL.rstrip('/')}/route"

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=settings.VALHALLA_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise ValhallaUnavailableError from exc

    if not response.ok:
        raise ValhallaUnavailableError

    try:
        valhalla_response = response.json()
    except ValueError as exc:
        raise InvalidValhallaResponseError from exc

    return normalize_valhalla_response(
        valhalla_response=valhalla_response,
        original_request=route_request,
    )


def normalize_valhalla_response(
    valhalla_response: dict,
    original_request: dict,
) -> dict:
    try:
        trip = valhalla_response["trip"]
        summary = trip["summary"]
        legs = trip.get("legs", [])
    except (KeyError, TypeError) as exc:
        raise InvalidValhallaResponseError from exc

    if not isinstance(legs, list) or not legs:
        raise InvalidValhallaResponseError

    encoded_polyline = trip.get("shape") or legs[0].get("shape") or ""

    return {
        "encodedPolyline": encoded_polyline,
        "distanceMetres": _length_to_metres(
            summary["length"],
            original_request["units"],
        ),
        "durationSeconds": _duration_to_seconds(summary["time"]),
        "legs": [
            _normalize_leg(leg, original_request["units"])
            for leg in legs
        ],
        "waypoints": original_request["waypoints"],
        "provider": "valhalla",
        "generatedAt": datetime.now(UTC).isoformat(),
    }


def _build_location(waypoint: dict) -> dict:
    location = {
        "lat": waypoint["latitude"],
        "lon": waypoint["longitude"],
    }
    if waypoint.get("name"):
        location["name"] = waypoint["name"]
    return location


def _build_costing_options(
    costing: str,
    road_priority: str,
    avoid_motorways: bool,
) -> dict:
    options = {}

    # Valhalla's use_highways value ranges from 0 to 1. Lower values make
    # motorway/highway routing less attractive without banning roads outright.
    use_highways = None
    if road_priority == "scenic":
        use_highways = 0.25
    elif avoid_motorways:
        use_highways = 0.05

    if use_highways is not None:
        options[costing] = {"use_highways": use_highways}

    return options


def _normalize_leg(leg: dict, units: str) -> dict:
    try:
        summary = leg["summary"]
        normalized = {
            "distanceMetres": _length_to_metres(summary["length"], units),
            "durationSeconds": _duration_to_seconds(summary["time"]),
        }
    except (KeyError, TypeError) as exc:
        raise InvalidValhallaResponseError from exc

    if summary.get("text"):
        normalized["summary"] = summary["text"]

    maneuvers = leg.get("maneuvers")
    if isinstance(maneuvers, list):
        normalized["maneuvers"] = maneuvers

    return normalized


def _length_to_metres(length: int | float, units: str) -> int:
    return round(float(length) * DISTANCE_FACTORS_TO_METRES[units])


def _duration_to_seconds(duration: int | float) -> int:
    return round(float(duration))
