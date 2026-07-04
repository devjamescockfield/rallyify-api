from datetime import UTC, datetime
from time import perf_counter

from django.conf import settings
import requests


def get_valhalla_status() -> dict[str, object]:
    status = {
        "configured": bool(settings.VALHALLA_URL),
        "reachable": False,
    }

    if not settings.VALHALLA_URL:
        return status

    try:
        response = requests.get(
            f"{settings.VALHALLA_URL.rstrip('/')}/status",
            timeout=settings.VALHALLA_HEALTH_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return status

    status["reachable"] = response.ok
    if not response.ok:
        return status

    version = _extract_valhalla_version(response)
    if version:
        status["version"] = version

    return status


def _extract_valhalla_version(response: requests.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    version = payload.get("version") or payload.get("valhalla_version")
    if version is None:
        return None

    return str(version)


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


def calculate_route(route_request: dict, diagnostics: dict | None = None) -> dict:
    payload = build_valhalla_payload(route_request)
    url = f"{settings.VALHALLA_URL.rstrip('/')}/route"

    try:
        valhalla_started = perf_counter()
        response = requests.post(
            url,
            json=payload,
            timeout=settings.VALHALLA_TIMEOUT_SECONDS,
        )
        record_duration(diagnostics, "valhalla_request_ms", valhalla_started)
    except requests.RequestException as exc:
        record_duration(diagnostics, "valhalla_request_ms", valhalla_started)
        raise ValhallaUnavailableError from exc

    if not response.ok:
        raise ValhallaUnavailableError

    try:
        valhalla_response = response.json()
    except ValueError as exc:
        raise InvalidValhallaResponseError from exc

    normalization_started = perf_counter()
    route = normalize_valhalla_response(
        valhalla_response=valhalla_response,
        original_request=route_request,
    )
    record_duration(diagnostics, "normalization_ms", normalization_started)
    return route


def record_duration(
    diagnostics: dict | None,
    key: str,
    started_at: float,
) -> None:
    if diagnostics is None:
        return
    diagnostics[key] = round((perf_counter() - started_at) * 1000, 2)


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

    if trip.get("status") not in (None, 0):
        raise InvalidValhallaResponseError

    encoded_polyline = trip.get("shape") or legs[0].get("shape") or ""
    polyline = _decode_route_polyline(trip, legs)

    return {
        "encodedPolyline": encoded_polyline,
        "polyline": polyline,
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

    # First-pass Rallyify preference mappings. Valhalla's use_highways value
    # ranges from 0 to 1; lower values make motorway/highway routing less
    # attractive without banning roads outright. These conservative values
    # should be refined after testing against a live Valhalla instance and real
    # Rallyify route examples.
    use_highways = None

    if avoid_motorways or road_priority == "avoid_motorways":
        use_highways = 0.05
    elif road_priority == "scenic":
        use_highways = 0.25
    elif road_priority == "prefer_b_roads":
        use_highways = 0.35

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

    maneuvers = leg.get("maneuvers", [])
    normalized["maneuvers"] = [
        _normalize_maneuver(maneuver, units)
        for maneuver in maneuvers
        if isinstance(maneuver, dict)
    ]

    return normalized


def _normalize_maneuver(maneuver: dict, units: str) -> dict:
    normalized = {
        "instruction": str(maneuver.get("instruction", "")),
        "distanceMetres": _length_to_metres(maneuver.get("length", 0), units),
        "type": str(maneuver.get("type", "")),
        "bearing_after": round(float(maneuver.get("begin_heading", 0))),
    }

    if "begin_shape_index" in maneuver:
        normalized["beginShapeIndex"] = maneuver["begin_shape_index"]
    if "end_shape_index" in maneuver:
        normalized["endShapeIndex"] = maneuver["end_shape_index"]
    if "street_names" in maneuver:
        normalized["streetNames"] = maneuver["street_names"]

    return normalized


def _decode_route_polyline(trip: dict, legs: list[dict]) -> list[list[float]]:
    if trip.get("shape"):
        return _decode_polyline6(trip["shape"])

    coordinates = []
    for leg in legs:
        shape = leg.get("shape")
        if not shape:
            continue
        decoded_leg = _decode_polyline6(shape)
        if coordinates and decoded_leg and coordinates[-1] == decoded_leg[0]:
            coordinates.extend(decoded_leg[1:])
        else:
            coordinates.extend(decoded_leg)

    if len(coordinates) < 2:
        raise InvalidValhallaResponseError

    return coordinates


def _decode_polyline6(encoded: str) -> list[list[float]]:
    if not isinstance(encoded, str) or not encoded:
        raise InvalidValhallaResponseError

    coordinates = []
    index = 0
    latitude = 0
    longitude = 0

    try:
        while index < len(encoded):
            latitude_delta, index = _decode_polyline_value(encoded, index)
            longitude_delta, index = _decode_polyline_value(encoded, index)
            latitude += latitude_delta
            longitude += longitude_delta
            coordinates.append([longitude / 1_000_000, latitude / 1_000_000])
    except (IndexError, ValueError) as exc:
        raise InvalidValhallaResponseError from exc

    if len(coordinates) < 2:
        raise InvalidValhallaResponseError

    return coordinates


def _decode_polyline_value(encoded: str, index: int) -> tuple[int, int]:
    result = 0
    shift = 0

    while True:
        byte = ord(encoded[index]) - 63
        index += 1
        result |= (byte & 0x1F) << shift
        shift += 5
        if byte < 0x20:
            break
        if shift > 60:
            raise ValueError("Invalid polyline encoding")

    value = ~(result >> 1) if result & 1 else result >> 1
    return value, index


def _length_to_metres(length: int | float, units: str) -> int:
    return round(float(length) * DISTANCE_FACTORS_TO_METRES[units])


def _duration_to_seconds(duration: int | float) -> int:
    return round(float(duration))
