import json
import logging
from time import perf_counter

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from routing.serializers import RouteCalculationSerializer
from routing.throttles import RouteBurstThrottle, RouteSustainedThrottle
from routing.valhalla import (
    InvalidValhallaResponseError,
    ValhallaUnavailableError,
    calculate_route as calculate_valhalla_route,
    get_valhalla_status,
)

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health(request):
    return Response(
        {
            "ok": True,
            "service": "rallyify-routing-api",
            "valhalla": get_valhalla_status(),
        }
    )


@api_view(["GET"])
def readiness(request):
    valhalla = get_valhalla_status()
    is_ready = bool(valhalla["reachable"])
    return Response(
        {
            "ok": is_ready,
            "service": "rallyify-routing-api",
            "valhalla": valhalla,
        },
        status=(
            status.HTTP_200_OK
            if is_ready
            else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
    )


@api_view(["POST"])
@throttle_classes([RouteBurstThrottle, RouteSustainedThrottle])
def calculate_route(request):
    request_started = perf_counter()
    diagnostics = {}
    route_request = None

    validation_started = perf_counter()
    serializer = RouteCalculationSerializer(data=request.data)
    is_valid = serializer.is_valid()
    diagnostics["validation_ms"] = duration_ms(validation_started)

    if is_valid:
        route_request = serializer.validated_data

    if not is_valid:
        return build_route_response(
            body=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST,
            diagnostics=diagnostics,
            request_started=request_started,
            route_request=request.data,
        )

    try:
        route = calculate_valhalla_route(route_request, diagnostics=diagnostics)
    except ValhallaUnavailableError:
        return build_route_response(
            body={
                "error": "Valhalla is unavailable.",
                "code": "VALHALLA_UNAVAILABLE",
            },
            status_code=status.HTTP_502_BAD_GATEWAY,
            diagnostics=diagnostics,
            request_started=request_started,
            route_request=route_request,
        )
    except InvalidValhallaResponseError:
        return build_route_response(
            body={
                "error": "Valhalla returned an invalid response.",
                "code": "INVALID_VALHALLA_RESPONSE",
            },
            status_code=status.HTTP_502_BAD_GATEWAY,
            diagnostics=diagnostics,
            request_started=request_started,
            route_request=route_request,
        )
    except Exception:
        logger.exception("Unexpected route calculation failure")
        return build_route_response(
            body={
                "error": "An unexpected error occurred.",
                "code": "INTERNAL_ERROR",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            diagnostics=diagnostics,
            request_started=request_started,
            route_request=route_request,
        )

    return build_route_response(
        body=route,
        status_code=status.HTTP_200_OK,
        diagnostics=diagnostics,
        request_started=request_started,
        route_request=route_request,
        route=route,
    )


def build_route_response(
    body,
    status_code: int,
    diagnostics: dict,
    request_started: float,
    route_request,
    route: dict | None = None,
) -> Response:
    response_started = perf_counter()
    response_size_bytes = json_response_size(body)
    response = Response(body, status=status_code)
    diagnostics["response_construction_ms"] = duration_ms(response_started)

    log_route_metrics(
        status_code=status_code,
        diagnostics=diagnostics,
        request_started=request_started,
        route_request=route_request,
        route=route,
        response_size_bytes=response_size_bytes,
    )

    return response


def log_route_metrics(
    status_code: int,
    diagnostics: dict,
    request_started: float,
    route_request,
    route: dict | None,
    response_size_bytes: int,
) -> None:
    total_ms = duration_ms(request_started)
    metrics = {
        "event": "route_calculate",
        "status_code": status_code,
        "total_ms": total_ms,
        "slow_threshold_ms": settings.ROUTE_SLOW_WARNING_MS,
        "validation_ms": diagnostics.get("validation_ms"),
        "valhalla_request_ms": diagnostics.get("valhalla_request_ms"),
        "normalization_ms": diagnostics.get("normalization_ms"),
        "response_construction_ms": diagnostics.get("response_construction_ms"),
        "response_size_bytes": response_size_bytes,
        "waypoint_count": waypoint_count(route_request),
        "roadPriority": safe_route_value(route_request, "roadPriority"),
        "vehicleProfile": safe_route_value(route_request, "vehicleProfile"),
        "units": safe_route_value(route_request, "units"),
        "polyline_point_count": polyline_point_count(route),
    }

    log = logger.warning if total_ms > settings.ROUTE_SLOW_WARNING_MS else logger.info
    log("route_calculate metrics=%s", json.dumps(metrics, sort_keys=True))


def duration_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def json_response_size(body) -> int:
    payload = json.dumps(body, separators=(",", ":"), default=str)
    return len(payload.encode("utf-8"))


def safe_route_value(route_request, key: str):
    if isinstance(route_request, dict):
        return route_request.get(key)
    return None


def waypoint_count(route_request) -> int:
    if not isinstance(route_request, dict):
        return 0
    waypoints = route_request.get("waypoints")
    return len(waypoints) if isinstance(waypoints, list) else 0


def polyline_point_count(route: dict | None) -> int:
    if not isinstance(route, dict):
        return 0
    polyline = route.get("polyline")
    return len(polyline) if isinstance(polyline, list) else 0
