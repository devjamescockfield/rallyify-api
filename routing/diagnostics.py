import hashlib
import json
import logging
from datetime import timedelta
from time import sleep
import uuid

from django.conf import settings
from django.db import IntegrityError, OperationalError, connections, transaction
from django.utils import timezone

from routing.models import RouteDiagnostic, RouteIssueReport


logger = logging.getLogger(__name__)


def purge_expired_beta_records() -> None:
    now = timezone.now()
    RouteDiagnostic.objects.filter(expires_at__lte=now).delete()
    RouteIssueReport.objects.filter(summary_expires_at__lte=now).delete()
    RouteIssueReport.objects.filter(
        exact_data_expires_at__lte=now,
    ).exclude(status=RouteIssueReport.Status.INVESTIGATING).update(
        consented_location_data={},
        exact_data_expires_at=None,
        exact_data_purged_at=now,
    )


def store_route_diagnostic(
    *,
    request_id: str,
    route_request: dict,
    route: dict,
    routing_metadata: dict,
) -> None:
    expires_at = timezone.now() + timedelta(
        days=settings.ROUTE_DIAGNOSTIC_RETENTION_DAYS
    )
    RouteDiagnostic.objects.update_or_create(
        request_id=request_id,
        defaults={
            "provider": routing_metadata["provider"],
            "engine_version": routing_metadata.get("engineVersion") or "",
            "graph_build_id": routing_metadata.get("graphBuildId") or "",
            "osm_data_date": routing_metadata.get("osmDataDate") or "",
            "costing_profile": routing_metadata["costingProfile"],
            "vehicle_profile": routing_metadata["vehicleProfile"],
            "road_priority": routing_metadata["roadPriority"],
            "units": routing_metadata["units"],
            "fallback_used": routing_metadata["fallbackUsed"],
            "waypoint_count": len(route_request["waypoints"]),
            "response_summary": {
                "distanceMetres": route.get("distanceMetres"),
                "durationSeconds": route.get("durationSeconds"),
                "polylinePointCount": len(route.get("polyline", [])),
                "legCount": len(route.get("legs", [])),
                "endpointSnaps": routing_metadata.get("endpointSnaps", {}),
            },
            "expires_at": expires_at,
        },
    )


class IdempotencyKeyConflict(Exception):
    pass


def _payload_fingerprint(validated_data: dict) -> str:
    encoded = json.dumps(
        validated_data,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_route_issue_report(
    *,
    validated_data: dict,
    reporter_id: uuid.UUID,
    idempotency_key: str,
):
    for attempt in range(8):
        try:
            return _create_route_issue_report_once(
                validated_data=validated_data,
                reporter_id=reporter_id,
                idempotency_key=idempotency_key,
            )
        except OperationalError as exc:
            is_sqlite_lock = (
                connections["default"].vendor == "sqlite"
                and "locked" in str(exc).lower()
            )
            if not is_sqlite_lock or attempt == 7:
                raise
            connections["default"].close()
            sleep(0.05 * (attempt + 1))


def _create_route_issue_report_once(
    *,
    validated_data: dict,
    reporter_id: uuid.UUID,
    idempotency_key: str,
):
    route_request_id = validated_data.get("routeRequestId", "")
    manoeuvre_index = validated_data.get("manoeuvreIndex")
    payload_fingerprint = _payload_fingerprint(validated_data)
    existing = RouteIssueReport.objects.filter(
        reporter_id=reporter_id,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.payload_fingerprint != payload_fingerprint:
            raise IdempotencyKeyConflict
        return existing, True

    try:
        diagnostic_request_id = uuid.UUID(route_request_id)
    except (AttributeError, TypeError, ValueError):
        diagnostic = None
    else:
        diagnostic = RouteDiagnostic.objects.filter(
            request_id=diagnostic_request_id
        ).first()
    metadata = {
        "api": {
            "version": settings.RALLYIFY_API_VERSION,
            "buildProfile": settings.DEPLOYMENT_ENV,
        },
        "client": {
            "provider": validated_data["provider"],
            "engineVersion": validated_data.get("engineVersion", ""),
            "graphBuildId": validated_data.get("graphBuildId", ""),
            "osmDataDate": validated_data.get("osmDataDate", ""),
            "roadPriority": validated_data["roadPriority"],
            "vehicleProfile": validated_data["vehicleProfile"],
            "appVersion": validated_data.get("appVersion", ""),
            "buildProfile": validated_data.get("buildProfile", ""),
            "routingMode": validated_data.get("routingMode", ""),
            "coarseArea": validated_data.get("coarseArea"),
        },
        "serverDiagnosticAvailable": diagnostic is not None,
    }
    if diagnostic:
        metadata["server"] = {
            "provider": diagnostic.provider,
            "engineVersion": diagnostic.engine_version,
            "graphBuildId": diagnostic.graph_build_id,
            "osmDataDate": diagnostic.osm_data_date,
            "roadPriority": diagnostic.road_priority,
            "costingProfile": diagnostic.costing_profile,
        }

    summary = {
        "distanceMetres": validated_data["distanceMetres"],
        "durationSeconds": validated_data["durationSeconds"],
        "manoeuvreIndex": manoeuvre_index,
        "notes": validated_data.get("notes", ""),
        "roadName": validated_data.get("roadName", ""),
        "instructedDirection": validated_data.get("instructedDirection", ""),
        "believedLegalDirection": validated_data.get(
            "believedLegalDirection",
            "",
        ),
    }
    consented_location_data = {
        key: validated_data[key]
        for key in (
            "exactLocation",
            "start",
            "destination",
            "routeGeometry",
            "currentManeuver",
        )
        if key in validated_data
    }
    now = timezone.now()
    summary_expires_at = now + timedelta(
        days=settings.ROUTE_REPORT_SUMMARY_RETENTION_DAYS
    )
    exact_data_expires_at = (
        now + timedelta(days=settings.ROUTE_REPORT_EXACT_RETENTION_DAYS)
        if consented_location_data
        else None
    )

    try:
        with transaction.atomic():
            report = RouteIssueReport.objects.create(
                route_request_id=route_request_id,
                reporter_id=reporter_id,
                idempotency_key=idempotency_key,
                payload_fingerprint=payload_fingerprint,
                category=validated_data["category"],
                graph_version=validated_data.get("graphBuildId", ""),
                metadata=metadata,
                summary=summary,
                consented_location_data=consented_location_data,
                location_consent=validated_data["locationConsent"],
                incident_time=validated_data["incidentTime"],
                exact_data_expires_at=exact_data_expires_at,
                summary_expires_at=summary_expires_at,
            )
    except IntegrityError:
        report = RouteIssueReport.objects.get(
            reporter_id=reporter_id,
            idempotency_key=idempotency_key,
        )
        if report.payload_fingerprint != payload_fingerprint:
            raise IdempotencyKeyConflict from None
        return report, True

    logger.info(
        "route_issue_report event=created report_id=%s request_id=%s category=%s "
        "location_consent=%s",
        report.report_id,
        route_request_id,
        report.category,
        report.location_consent,
    )
    return report, False
