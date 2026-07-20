import hashlib
import json
import logging
from datetime import timedelta
import uuid

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from routing.models import RouteDiagnostic, RouteIssueReport


logger = logging.getLogger(__name__)


def purge_expired_beta_records() -> None:
    now = timezone.now()
    RouteDiagnostic.objects.filter(expires_at__lte=now).delete()
    RouteIssueReport.objects.filter(expires_at__lte=now).delete()


def store_route_diagnostic(
    *,
    request_id: str,
    route_request: dict,
    route: dict,
    routing_metadata: dict,
    exact_diagnostics: dict,
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
            "road_priority": routing_metadata["roadPriority"],
            "units": routing_metadata["units"],
            "fallback_used": routing_metadata["fallbackUsed"],
            "request_payload": route_request,
            "route_payload": route,
            "exact_diagnostics": exact_diagnostics,
            "expires_at": expires_at,
        },
    )
    purge_expired_beta_records()


def create_route_issue_report(*, validated_data: dict, reporter_fingerprint: str):
    route_request_id = validated_data.get("routeRequestId", "")
    manoeuvre_index = validated_data.get("manoeuvreIndex")
    dedupe_material = {
        "reporter": reporter_fingerprint,
        "clientReportId": validated_data.get("clientReportId", ""),
        "routeRequestId": route_request_id,
        "category": validated_data["category"],
        "manoeuvreIndex": manoeuvre_index,
    }
    dedupe_key = hashlib.sha256(
        json.dumps(dedupe_material, sort_keys=True).encode()
    ).hexdigest()

    existing = RouteIssueReport.objects.filter(dedupe_key=dedupe_key).first()
    if existing:
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
    expires_at = timezone.now() + timedelta(days=settings.ROUTE_REPORT_RETENTION_DAYS)

    try:
        report = RouteIssueReport.objects.create(
            route_request_id=route_request_id,
            reporter_fingerprint=reporter_fingerprint,
            category=validated_data["category"],
            metadata=metadata,
            summary=summary,
            consented_location_data=consented_location_data,
            location_consent=validated_data["locationConsent"],
            dedupe_key=dedupe_key,
            incident_time=validated_data["incidentTime"],
            expires_at=expires_at,
        )
    except IntegrityError:
        report = RouteIssueReport.objects.get(dedupe_key=dedupe_key)
        return report, True

    purge_expired_beta_records()
    logger.info(
        "route_issue_report event=created report_id=%s request_id=%s category=%s "
        "location_consent=%s",
        report.report_id,
        route_request_id,
        report.category,
        report.location_consent,
    )
    return report, False
