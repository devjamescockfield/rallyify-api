from django.contrib import admin

from routing.models import (
    CompletedDrive,
    FuelEconomyRecord,
    RouteDiagnostic,
    RouteIssueReport,
    VehicleProfile,
)


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


@admin.register(VehicleProfile)
class VehicleProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "owner_id",
        "display_name",
        "fuel_type",
        "vehicle_category",
        "is_default",
        "created_at",
    )
    list_filter = ("fuel_type", "vehicle_category", "is_default", "created_at")
    search_fields = ("id", "owner_id", "display_name")
    readonly_fields = ("id", "owner_id", "created_at", "updated_at")
    exclude = ("registration_value",)
    ordering = ("-created_at",)


@admin.register(CompletedDrive)
class CompletedDriveAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "owner_id",
        "vehicle_name_snapshot",
        "mode",
        "completion_reason",
        "finished_at",
    )
    list_filter = ("mode", "completion_reason", "created_at")
    search_fields = ("id", "owner_id", "route_title_snapshot", "route_id")
    readonly_fields = (
        "id",
        "owner_id",
        "completion_id",
        "payload_fingerprint",
        "vehicle_name_snapshot",
        "created_at",
        "updated_at",
    )
    ordering = ("-finished_at",)


@admin.register(FuelEconomyRecord)
class FuelEconomyRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "completed_drive",
        "calculation_method",
        "estimated",
        "created_at",
    )
    list_filter = ("calculation_method", "estimated", "created_at")
    search_fields = ("id", "completed_drive__id", "completed_drive__owner_id")
    readonly_fields = tuple(field.name for field in FuelEconomyRecord._meta.fields)
    ordering = ("-created_at",)
