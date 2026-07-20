import json
import logging
import re
from time import perf_counter
import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from routing.authentication import SupabaseJWTAuthentication
from routing.diagnostics import (
    IdempotencyKeyConflict,
    create_route_issue_report,
    store_route_diagnostic,
)
from routing.serializers import RouteCalculationSerializer, RouteIssueReportSerializer
from routing.throttles import (
    RouteBurstThrottle,
    RouteReportGlobalThrottle,
    RouteReportIPThrottle,
    RouteReportIPDailyThrottle,
    RouteReportUserBurstThrottle,
    RouteReportUserHourlyThrottle,
    RouteReportUserDailyThrottle,
    RouteSustainedThrottle,
)
from routing.valhalla import (
    InvalidValhallaResponseError,
    RouteValidationError,
    ValhallaUnavailableError,
    calculate_route as calculate_valhalla_route,
    get_valhalla_graph_information,
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


@api_view(["GET"])
def graph_information(request):
    return Response(get_valhalla_graph_information(probe=True))


@api_view(["GET"])
def routing_information(request):
    graph = get_valhalla_graph_information(probe=True)
    return Response(
        {
            "provider": "valhalla",
            "providerVersion": graph["engineVersion"],
            "graphVersion": graph["graphBuildId"],
            "dataVersion": graph["osmDataDate"],
            "buildDate": settings.ROUTING_BUILD_DATE or None,
            "supportedProfiles": graph["supportedVehicleProfiles"],
            "supportedPriorities": graph["supportedRoutePriorities"],
        }
    )


@api_view(["POST"])
@throttle_classes([RouteBurstThrottle, RouteSustainedThrottle])
def calculate_route(request):
    request_id = str(uuid.uuid4())
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
            request_id=request_id,
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
            request_id=request_id,
        )
    except RouteValidationError as exc:
        return build_route_response(
            body={
                "error": "Calculated route failed validation.",
                "code": "INVALID_ROUTE_RESULT",
                "reason": exc.reason,
            },
            status_code=status.HTTP_502_BAD_GATEWAY,
            diagnostics=diagnostics,
            request_started=request_started,
            route_request=route_request,
            request_id=request_id,
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
            request_id=request_id,
        )
    except Exception:
        logger.exception("Unexpected route calculation failure request_id=%s", request_id)
        return build_route_response(
            body={
                "error": "An unexpected error occurred.",
                "code": "INTERNAL_ERROR",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            diagnostics=diagnostics,
            request_started=request_started,
            route_request=route_request,
            request_id=request_id,
        )

    routing_metadata = build_routing_metadata(route_request, diagnostics)
    route["requestId"] = request_id
    route["routingMetadata"] = routing_metadata
    try:
        store_route_diagnostic(
            request_id=request_id,
            route_request=route_request,
            route=route,
            routing_metadata=routing_metadata,
        )
    except Exception:
        logger.exception("Route diagnostic storage failed request_id=%s", request_id)

    return build_route_response(
        body=route,
        status_code=status.HTTP_200_OK,
        diagnostics=diagnostics,
        request_started=request_started,
        route_request=route_request,
        route=route,
        request_id=request_id,
    )


@api_view(["POST"])
@authentication_classes([SupabaseJWTAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes(
    [
        RouteReportUserBurstThrottle,
        RouteReportUserHourlyThrottle,
        RouteReportUserDailyThrottle,
        RouteReportIPThrottle,
        RouteReportIPDailyThrottle,
        RouteReportGlobalThrottle,
    ]
)
def submit_route_report(request):
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", idempotency_key):
        return Response(
            {
                "error": "A valid Idempotency-Key header is required.",
                "code": "INVALID_IDEMPOTENCY_KEY",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = RouteIssueReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        report, duplicate = create_route_issue_report(
            validated_data=serializer.validated_data,
            reporter_id=uuid.UUID(request.user.subject),
            idempotency_key=idempotency_key,
        )
    except IdempotencyKeyConflict:
        return Response(
            {
                "error": "Idempotency key was already used for another report.",
                "code": "IDEMPOTENCY_KEY_REUSED",
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return Response(
        {
            "reportId": str(report.report_id),
            "status": "accepted",
            "receivedAt": report.created_at.isoformat(),
            "duplicate": duplicate,
        },
        status=status.HTTP_409_CONFLICT if duplicate else status.HTTP_201_CREATED,
    )


def build_routing_metadata(route_request: dict, diagnostics: dict) -> dict:
    graph = get_valhalla_graph_information(probe=True)
    validation = diagnostics.get("route_validation", {})
    return {
        "provider": "valhalla",
        "apiVersion": settings.RALLYIFY_API_VERSION,
        "providerVersion": graph["engineVersion"],
        "engineVersion": graph["engineVersion"],
        "graphVersion": graph["graphBuildId"],
        "graphBuildId": graph["graphBuildId"],
        "dataVersion": graph["osmDataDate"],
        "osmDataDate": graph["osmDataDate"],
        "buildDate": settings.ROUTING_BUILD_DATE or None,
        "costingProfile": diagnostics.get("costing_profile"),
        "vehicleProfile": route_request["vehicleProfile"],
        "roadPriority": route_request["roadPriority"],
        "units": route_request["units"],
        "fallbackUsed": False,
        "endpointSnaps": {
            "start": validation.get("startSnapBand"),
            "destination": validation.get("destinationSnapBand"),
        },
    }


def build_route_response(
    body,
    status_code: int,
    diagnostics: dict,
    request_started: float,
    route_request,
    request_id: str,
    route: dict | None = None,
) -> Response:
    if isinstance(body, dict) and "requestId" not in body:
        body = {**body, "requestId": request_id}
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
        request_id=request_id,
    )
    response["X-Route-Request-ID"] = request_id
    response["X-Request-ID"] = request_id
    if route:
        graph_version = route.get("routingMetadata", {}).get("graphBuildId")
        if graph_version:
            response["X-Rallyify-Graph-Version"] = graph_version
    return response


def log_route_metrics(
    status_code: int,
    diagnostics: dict,
    request_started: float,
    route_request,
    route: dict | None,
    response_size_bytes: int,
    request_id: str,
) -> None:
    total_ms = duration_ms(request_started)
    metrics = {
        "event": "route_calculate",
        "request_id": request_id,
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
