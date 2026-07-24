import uuid

from django.db import models
from django.db.models import Q


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


class VehicleProfile(models.Model):
    class FuelType(models.TextChoices):
        PETROL = "petrol", "Petrol"
        DIESEL = "diesel", "Diesel"
        HYBRID = "hybrid", "Hybrid"
        PLUG_IN_HYBRID = "plug_in_hybrid", "Plug-in hybrid"
        ELECTRIC = "electric", "Electric"
        OTHER = "other", "Other"

    class Category(models.TextChoices):
        MOTORCYCLE = "motorcycle", "Motorcycle"
        SMALL_CAR = "small_car", "Small car"
        MEDIUM_CAR = "medium_car", "Medium car"
        LARGE_CAR = "large_car", "Large car"
        SUV = "suv", "SUV"
        VAN = "van", "Van"
        OTHER = "other", "Other"

    class EconomyBaselineSource(models.TextChoices):
        USER_ENTERED = "user_entered", "User entered"
        GENERIC_VEHICLE_PROFILE = (
            "generic_vehicle_profile",
            "Generic vehicle profile",
        )
        NONE = "none", "None"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_id = models.UUIDField(db_index=True, editable=False)
    display_name = models.CharField(max_length=100)
    make = models.CharField(max_length=80, blank=True)
    model = models.CharField(max_length=80, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    registration_value = models.CharField(max_length=32, blank=True)
    fuel_type = models.CharField(max_length=30, choices=FuelType.choices)
    vehicle_category = models.CharField(max_length=30, choices=Category.choices)
    tank_capacity_litres = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
    )
    battery_capacity_kwh = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
    )
    typical_mpg_uk = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
    )
    typical_litres_per_100km = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
    )
    economy_baseline_source = models.CharField(
        max_length=40,
        choices=EconomyBaselineSource.choices,
        default=EconomyBaselineSource.NONE,
    )
    is_default = models.BooleanField(default=False)
    schema_version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_default", "display_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["owner_id"],
                condition=Q(is_default=True),
                name="unique_default_vehicle_per_owner",
            )
        ]


class CompletedDrive(models.Model):
    class Mode(models.TextChoices):
        SOLO = "solo", "Solo"
        GROUP = "group", "Group"

    class CompletionReason(models.TextChoices):
        ARRIVED = "arrived", "Arrived"
        MANUALLY_ENDED = "manually_ended", "Manually ended"
        GROUP_ENDED = "group_ended", "Group ended"
        CANCELLED = "cancelled", "Cancelled"
        RECOVERED_COMPLETION = "recovered_completion", "Recovered completion"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_id = models.UUIDField(db_index=True, editable=False)
    completion_id = models.CharField(max_length=100, editable=False)
    payload_fingerprint = models.CharField(max_length=64, editable=False)
    vehicle = models.ForeignKey(
        VehicleProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_drives",
    )
    vehicle_name_snapshot = models.CharField(max_length=100, blank=True)
    route_title_snapshot = models.CharField(max_length=200, blank=True)
    route_id = models.CharField(max_length=100, blank=True)
    mode = models.CharField(max_length=20, choices=Mode.choices)
    group_id = models.CharField(max_length=100, blank=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    elapsed_seconds = models.PositiveIntegerField()
    moving_seconds = models.PositiveIntegerField()
    stopped_seconds = models.PositiveIntegerField()
    actual_distance_metres = models.DecimalField(max_digits=12, decimal_places=3)
    planned_distance_metres = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    average_overall_speed_mps = models.DecimalField(
        max_digits=8,
        decimal_places=3,
    )
    average_moving_speed_mps = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
    )
    completion_reason = models.CharField(
        max_length=30,
        choices=CompletionReason.choices,
    )
    reroute_count = models.PositiveSmallIntegerField(null=True, blank=True)
    off_route_count = models.PositiveSmallIntegerField(null=True, blank=True)
    schema_version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-finished_at", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["owner_id", "completion_id"],
                name="unique_drive_completion_per_owner",
            )
        ]
        indexes = [
            models.Index(fields=["owner_id", "finished_at"]),
        ]


class FuelEconomyRecord(models.Model):
    class CalculationMethod(models.TextChoices):
        VEHICLE_PROFILE_ESTIMATE = (
            "vehicle_profile_estimate",
            "Vehicle profile estimate",
        )
        FUEL_LEVEL_ESTIMATE = "fuel_level_estimate", "Fuel level estimate"
        FUEL_USED_ENTRY = "fuel_used_entry", "Fuel used entry"
        FILL_TO_FILL = "fill_to_fill", "Fill to fill"
        OBD_MEASURED = "obd_measured", "OBD measured"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    completed_drive = models.OneToOneField(
        CompletedDrive,
        on_delete=models.CASCADE,
        related_name="fuel_record",
    )
    vehicle = models.ForeignKey(
        VehicleProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fuel_records",
    )
    vehicle_name_snapshot = models.CharField(max_length=100, blank=True)
    fuel_used_litres = models.DecimalField(max_digits=8, decimal_places=4)
    calculation_method = models.CharField(
        max_length=40,
        choices=CalculationMethod.choices,
    )
    estimated = models.BooleanField()
    start_fuel_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    end_fuel_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    tank_capacity_litres_snapshot = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
    )
    economy_model_version = models.CharField(max_length=30, blank=True)
    baseline_source = models.CharField(max_length=40, blank=True)
    calculated_mpg_uk = models.DecimalField(max_digits=9, decimal_places=4)
    calculated_litres_per_100km = models.DecimalField(
        max_digits=9,
        decimal_places=4,
    )
    explanation = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
