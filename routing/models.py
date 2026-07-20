import uuid

from django.db import models


class RouteDiagnostic(models.Model):
    request_id = models.UUIDField(primary_key=True, editable=False)
    provider = models.CharField(max_length=50)
    engine_version = models.CharField(max_length=100, blank=True)
    graph_build_id = models.CharField(max_length=100, blank=True)
    osm_data_date = models.CharField(max_length=50, blank=True)
    costing_profile = models.CharField(max_length=50)
    road_priority = models.CharField(max_length=50)
    units = models.CharField(max_length=20)
    fallback_used = models.BooleanField(default=False)
    request_payload = models.JSONField()
    route_payload = models.JSONField()
    exact_diagnostics = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)


class RouteIssueReport(models.Model):
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    route_request_id = models.CharField(max_length=100, blank=True, db_index=True)
    reporter_fingerprint = models.CharField(max_length=64, db_index=True)
    category = models.CharField(max_length=50)
    metadata = models.JSONField()
    summary = models.JSONField()
    consented_location_data = models.JSONField(default=dict)
    location_consent = models.BooleanField(default=False)
    dedupe_key = models.CharField(max_length=64, unique=True)
    incident_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
