from django.contrib import admin

from routing.models import RouteDiagnostic, RouteIssueReport


@admin.register(RouteIssueReport)
class RouteIssueReportAdmin(admin.ModelAdmin):
    list_display = (
        "report_id",
        "category",
        "status",
        "graph_version",
        "location_consent",
        "created_at",
    )
    list_filter = ("status", "category", "location_consent", "graph_version")
    search_fields = ("report_id", "route_request_id", "idempotency_key")
    readonly_fields = (
        "report_id",
        "reporter_id",
        "idempotency_key",
        "payload_fingerprint",
        "route_request_id",
        "category",
        "graph_version",
        "metadata",
        "summary",
        "location_consent",
        "consented_location_data",
        "incident_time",
        "created_at",
        "updated_at",
        "exact_data_expires_at",
        "exact_data_purged_at",
        "summary_expires_at",
    )
    fields = readonly_fields + ("status", "internal_notes")
    ordering = ("-created_at",)


@admin.register(RouteDiagnostic)
class RouteDiagnosticAdmin(admin.ModelAdmin):
    list_display = (
        "request_id",
        "provider",
        "graph_build_id",
        "vehicle_profile",
        "road_priority",
        "created_at",
        "expires_at",
    )
    list_filter = ("provider", "vehicle_profile", "road_priority")
    search_fields = ("request_id", "graph_build_id")
    readonly_fields = tuple(field.name for field in RouteDiagnostic._meta.fields)
    ordering = ("-created_at",)
