from datetime import UTC, datetime
import logging
import math
from time import perf_counter

from django.conf import settings
import requests

from routing.contracts import SUPPORTED_ROUTE_PRIORITIES, SUPPORTED_VEHICLE_PROFILES


_cached_status_metadata = {}
logger = logging.getLogger(__name__)


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

    _cache_status_metadata(response)

    return status


def get_valhalla_graph_information(*, probe: bool = True) -> dict[str, object]:
    if probe:
        get_valhalla_status()

    live_engine_version = _cached_status_metadata.get("engineVersion")
    if (
        live_engine_version
        and settings.VALHALLA_ENGINE_VERSION
        and live_engine_version != settings.VALHALLA_ENGINE_VERSION
    ):
        logger.warning(
            "routing_metadata_mismatch field=engineVersion configured=%s live=%s",
            settings.VALHALLA_ENGINE_VERSION,
            live_engine_version,
        )
    engine_version = live_engine_version or settings.VALHALLA_ENGINE_VERSION or None
    graph_build_id = (
        _cached_status_metadata.get("graphBuildId")
        or settings.VALHALLA_GRAPH_BUILD_ID
        or None
    )
    osm_data_date = (
        _cached_status_metadata.get("osmDataDate")
        or settings.VALHALLA_OSM_DATA_DATE
        or None
    )
    return {
        "routingEngine": "valhalla",
        "engineVersion": engine_version,
        "graphBuildId": graph_build_id,
        "osmDataDate": osm_data_date,
        "supportedVehicleProfiles": SUPPORTED_VEHICLE_PROFILES,
        "supportedRoutePriorities": SUPPORTED_ROUTE_PRIORITIES,
    }


def _cache_status_metadata(response: requests.Response) -> None:
    try:
        payload = response.json()
    except ValueError:
        return
    if not isinstance(payload, dict):
        return

    version = payload.get("version") or payload.get("valhalla_version")
    graph_build_id = payload.get("graph_build_id") or payload.get("tileset_id")
    osm_data_date = payload.get("osm_data_date") or payload.get("source_data_date")
    if version is not None:
        _cached_status_metadata["engineVersion"] = str(version)
    if graph_build_id is not None:
        _cached_status_metadata["graphBuildId"] = str(graph_build_id)
    if osm_data_date is not None:
        _cached_status_metadata["osmDataDate"] = str(osm_data_date)


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


class RouteValidationError(InvalidValhallaResponseError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


VEHICLE_COSTING = {
    "car": "auto",
    "motorbike": "motorcycle",
    "caravan": "truck",
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
    if diagnostics is not None:
        diagnostics["costing_profile"] = payload["costing"]
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
    validation_diagnostics = validate_route_response(route, route_request)
    if diagnostics is not None:
        diagnostics["route_validation"] = validation_diagnostics
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
        raise RouteValidationError("MISSING_LEGS")

    if trip.get("status") not in (None, 0):
        raise InvalidValhallaResponseError

    encoded_polyline = trip.get("shape") or legs[0].get("shape") or ""
    try:
        polyline = _decode_route_polyline(trip, legs)
    except InvalidValhallaResponseError as exc:
        raise RouteValidationError("MALFORMED_GEOMETRY") from exc

    try:
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
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise RouteValidationError("NON_FINITE_OR_MALFORMED_METRICS") from exc


def validate_route_response(route: dict, original_request: dict) -> dict:
    polyline = route.get("polyline")
    if not isinstance(polyline, list) or len(polyline) < 2:
        raise RouteValidationError("MALFORMED_GEOMETRY")
    if not _is_finite_positive(route.get("distanceMetres")):
        raise RouteValidationError("NON_FINITE_DISTANCE")
    if not _is_finite_positive(route.get("durationSeconds")):
        raise RouteValidationError("NON_FINITE_DURATION")
    if not isinstance(route.get("legs"), list) or not route["legs"]:
        raise RouteValidationError("MISSING_LEGS")

    try:
        start = original_request["waypoints"][0]
        destination = original_request["waypoints"][-1]
        route_start = {"longitude": polyline[0][0], "latitude": polyline[0][1]}
        route_end = {"longitude": polyline[-1][0], "latitude": polyline[-1][1]}
    except (IndexError, KeyError, TypeError) as exc:
        raise RouteValidationError("MALFORMED_GEOMETRY") from exc

    try:
        start_snap_metres = _haversine_metres(start, route_start)
        destination_snap_metres = _haversine_metres(destination, route_end)
        reversed_start_metres = _haversine_metres(destination, route_start)
        reversed_destination_metres = _haversine_metres(start, route_end)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise RouteValidationError("MALFORMED_GEOMETRY") from exc

    if (
        reversed_start_metres < start_snap_metres
        and reversed_destination_metres < destination_snap_metres
        and reversed_start_metres + reversed_destination_metres
        < (start_snap_metres + destination_snap_metres) * 0.5
    ):
        raise RouteValidationError("START_END_REVERSED")

    if (
        start_snap_metres > settings.ROUTE_MAX_ENDPOINT_SNAP_METRES
        or destination_snap_metres > settings.ROUTE_MAX_ENDPOINT_SNAP_METRES
    ):
        raise RouteValidationError("ENDPOINT_SNAP_TOO_DISTANT")

    maximum_gap_metres = 0.0
    for first, second in zip(polyline, polyline[1:]):
        try:
            gap_metres = _haversine_metres(
                {"longitude": first[0], "latitude": first[1]},
                {"longitude": second[0], "latitude": second[1]},
            )
        except (IndexError, TypeError, ValueError, OverflowError) as exc:
            raise RouteValidationError("MALFORMED_GEOMETRY") from exc
        maximum_gap_metres = max(maximum_gap_metres, gap_metres)
        if gap_metres > settings.ROUTE_MAX_GEOMETRY_GAP_METRES:
            raise RouteValidationError("SEVERE_GEOMETRY_DISCONTINUITY")

    return {
        "startSnapMetres": round(start_snap_metres, 2),
        "destinationSnapMetres": round(destination_snap_metres, 2),
        "maximumGeometryGapMetres": round(maximum_gap_metres, 2),
        "startSnapBand": _snap_distance_band(start_snap_metres),
        "destinationSnapBand": _snap_distance_band(destination_snap_metres),
    }


def _is_finite_positive(value) -> bool:
    return isinstance(value, int | float) and math.isfinite(value) and value > 0


def _snap_distance_band(distance_metres: float) -> str:
    if distance_metres < 25:
        return "under_25m"
    if distance_metres < 100:
        return "25_to_100m"
    if distance_metres < 500:
        return "100_to_500m"
    if distance_metres < 2000:
        return "500m_to_2km"
    if distance_metres < 5000:
        return "2_to_5km"
    return "over_5km"


def _haversine_metres(first: dict, second: dict) -> float:
    first_latitude = math.radians(float(first["latitude"]))
    second_latitude = math.radians(float(second["latitude"]))
    latitude_delta = second_latitude - first_latitude
    longitude_delta = math.radians(
        float(second["longitude"]) - float(first["longitude"])
    )
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude)
        * math.cos(second_latitude)
        * math.sin(longitude_delta / 2) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    return 6_371_000 * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


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
    value = float(length) * DISTANCE_FACTORS_TO_METRES[units]
    if not math.isfinite(value):
        raise RouteValidationError("NON_FINITE_DISTANCE")
    return round(value)


def _duration_to_seconds(duration: int | float) -> int:
    value = float(duration)
    if not math.isfinite(value):
        raise RouteValidationError("NON_FINITE_DURATION")
    return round(value)
