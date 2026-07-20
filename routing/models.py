import uuid

from django.db import models


class RouteDiagnostic(models.Model):
    request_id = models.UUIDField(primary_key=True, editable=False)
    provider = models.CharField(max_length=50)
    engine_version = models.CharField(max_length=100, blank=True)
    graph_build_id = models.CharField(max_length=100, blank=True)
    osm_data_date = models.CharField(max_length=50, blank=True)
    costing_profile = models.CharField(max_length=50)
    vehicle_profile = models.CharField(max_length=50)
    road_priority = models.CharField(max_length=50)
    units = models.CharField(max_length=20)
    fallback_used = models.BooleanField(default=False)
    waypoint_count = models.PositiveSmallIntegerField()
    response_summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)


class RouteIssueReport(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        TRIAGED = "triaged", "Triaged"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    route_request_id = models.CharField(max_length=100, blank=True, db_index=True)
    reporter_id = models.UUIDField(db_index=True, editable=False)
    idempotency_key = models.CharField(max_length=100, editable=False)
    payload_fingerprint = models.CharField(max_length=64, editable=False)
    category = models.CharField(max_length=50, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    graph_version = models.CharField(max_length=100, blank=True, db_index=True)
    metadata = models.JSONField()
    summary = models.JSONField()
    consented_location_data = models.JSONField(default=dict)
    location_consent = models.BooleanField(default=False)
    incident_time = models.DateTimeField()
    internal_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    exact_data_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    exact_data_purged_at = models.DateTimeField(null=True, blank=True)
    summary_expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reporter_id", "idempotency_key"],
                name="unique_route_report_idempotency_per_user",
            )
        ]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["category", "created_at"]),
        ]
