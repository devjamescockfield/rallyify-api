from datetime import datetime
from decimal import Decimal

from rest_framework import serializers

from routing.models import CompletedDrive, FuelEconomyRecord, VehicleProfile
from routing.serializers import FiniteFloatField, StrictFieldsMixin


MAX_VEHICLE_CAPACITY = 300
MAX_DRIVE_SECONDS = 31 * 24 * 60 * 60
MAX_DRIVE_DISTANCE_METRES = 10_000_000
MAX_SPEED_MPS = 100


class VehicleProfileSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    displayName = serializers.CharField(source="display_name", max_length=100)
    registration = serializers.CharField(
        source="registration_value",
        max_length=32,
        required=False,
        allow_blank=True,
    )
    fuelType = serializers.ChoiceField(
        source="fuel_type",
        choices=VehicleProfile.FuelType.choices,
    )
    vehicleCategory = serializers.ChoiceField(
        source="vehicle_category",
        choices=VehicleProfile.Category.choices,
    )
    tankCapacityLitres = serializers.DecimalField(
        source="tank_capacity_litres",
        max_digits=7,
        decimal_places=3,
        min_value=Decimal("1"),
        max_value=Decimal(str(MAX_VEHICLE_CAPACITY)),
        required=False,
        allow_null=True,
    )
    batteryCapacityKwh = serializers.DecimalField(
        source="battery_capacity_kwh",
        max_digits=7,
        decimal_places=3,
        min_value=Decimal("1"),
        max_value=Decimal(str(MAX_VEHICLE_CAPACITY)),
        required=False,
        allow_null=True,
    )
    typicalMpgUk = serializers.DecimalField(
        source="typical_mpg_uk",
        max_digits=7,
        decimal_places=3,
        min_value=Decimal("1"),
        max_value=Decimal("500"),
        required=False,
        allow_null=True,
    )
    typicalLitresPer100Km = serializers.DecimalField(
        source="typical_litres_per_100km",
        max_digits=7,
        decimal_places=3,
        min_value=Decimal("0.1"),
        max_value=Decimal("100"),
        required=False,
        allow_null=True,
    )
    economyBaselineSource = serializers.ChoiceField(
        source="economy_baseline_source",
        choices=VehicleProfile.EconomyBaselineSource.choices,
        required=False,
    )
    isDefault = serializers.BooleanField(source="is_default", required=False)
    schemaVersion = serializers.IntegerField(source="schema_version", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = VehicleProfile
        fields = (
            "id",
            "displayName",
            "make",
            "model",
            "year",
            "registration",
            "fuelType",
            "vehicleCategory",
            "tankCapacityLitres",
            "batteryCapacityKwh",
            "typicalMpgUk",
            "typicalLitresPer100Km",
            "economyBaselineSource",
            "isDefault",
            "schemaVersion",
            "createdAt",
            "updatedAt",
        )
        read_only_fields = ("id",)
        extra_kwargs = {
            "make": {"required": False, "allow_blank": True, "max_length": 80},
            "model": {"required": False, "allow_blank": True, "max_length": 80},
            "year": {"required": False, "allow_null": True},
        }

    def validate_year(self, value):
        if value is not None and not 1886 <= value <= datetime.now().year + 1:
            raise serializers.ValidationError("Year is outside the supported range.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        current = self.instance
        mpg = attrs.get(
            "typical_mpg_uk",
            current.typical_mpg_uk if current else None,
        )
        metric = attrs.get(
            "typical_litres_per_100km",
            current.typical_litres_per_100km if current else None,
        )
        source = attrs.get(
            "economy_baseline_source",
            current.economy_baseline_source
            if current
            else VehicleProfile.EconomyBaselineSource.NONE,
        )
        if mpg is not None and metric is not None:
            raise serializers.ValidationError(
                {
                    "typicalMpgUk": (
                        "Supply either typicalMpgUk or typicalLitresPer100Km, not both."
                    )
                }
            )
        if (mpg is not None or metric is not None) and (
            source == VehicleProfile.EconomyBaselineSource.NONE
        ):
            raise serializers.ValidationError(
                {
                    "economyBaselineSource": (
                        "A baseline source is required when typical economy is supplied."
                    )
                }
            )
        if mpg is None and metric is None and (
            source != VehicleProfile.EconomyBaselineSource.NONE
        ):
            raise serializers.ValidationError(
                {
                    "economyBaselineSource": (
                        "A typical economy value is required for this baseline source."
                    )
                }
            )
        return attrs


class CompletedDriveSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    completionId = serializers.CharField(
        source="completion_id",
        max_length=100,
    )
    vehicleId = serializers.UUIDField(
        source="vehicle_id",
        required=False,
        allow_null=True,
    )
    vehicleNameSnapshot = serializers.CharField(
        source="vehicle_name_snapshot",
        max_length=100,
        required=False,
        allow_blank=True,
    )
    routeTitleSnapshot = serializers.CharField(
        source="route_title_snapshot",
        max_length=200,
        required=False,
        allow_blank=True,
    )
    routeId = serializers.CharField(
        source="route_id",
        max_length=100,
        required=False,
        allow_blank=True,
    )
    groupId = serializers.CharField(
        source="group_id",
        max_length=100,
        required=False,
        allow_blank=True,
    )
    startedAt = serializers.DateTimeField(source="started_at")
    finishedAt = serializers.DateTimeField(source="finished_at")
    elapsedSeconds = serializers.IntegerField(
        source="elapsed_seconds",
        min_value=1,
        max_value=MAX_DRIVE_SECONDS,
    )
    movingSeconds = serializers.IntegerField(
        source="moving_seconds",
        min_value=0,
        max_value=MAX_DRIVE_SECONDS,
    )
    stoppedSeconds = serializers.IntegerField(
        source="stopped_seconds",
        min_value=0,
        max_value=MAX_DRIVE_SECONDS,
    )
    actualDistanceMetres = serializers.DecimalField(
        source="actual_distance_metres",
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0"),
        max_value=Decimal(str(MAX_DRIVE_DISTANCE_METRES)),
    )
    plannedDistanceMetres = serializers.DecimalField(
        source="planned_distance_metres",
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0"),
        max_value=Decimal(str(MAX_DRIVE_DISTANCE_METRES)),
        required=False,
        allow_null=True,
    )
    averageOverallSpeedMps = serializers.DecimalField(
        source="average_overall_speed_mps",
        max_digits=8,
        decimal_places=3,
        read_only=True,
    )
    averageMovingSpeedMps = serializers.DecimalField(
        source="average_moving_speed_mps",
        max_digits=8,
        decimal_places=3,
        read_only=True,
        allow_null=True,
    )
    completionReason = serializers.ChoiceField(
        source="completion_reason",
        choices=CompletedDrive.CompletionReason.choices,
    )
    rerouteCount = serializers.IntegerField(
        source="reroute_count",
        min_value=0,
        max_value=10_000,
        required=False,
        allow_null=True,
    )
    offRouteCount = serializers.IntegerField(
        source="off_route_count",
        min_value=0,
        max_value=10_000,
        required=False,
        allow_null=True,
    )
    schemaVersion = serializers.IntegerField(source="schema_version", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = CompletedDrive
        fields = (
            "id",
            "completionId",
            "vehicleId",
            "vehicleNameSnapshot",
            "routeTitleSnapshot",
            "routeId",
            "mode",
            "groupId",
            "startedAt",
            "finishedAt",
            "elapsedSeconds",
            "movingSeconds",
            "stoppedSeconds",
            "actualDistanceMetres",
            "plannedDistanceMetres",
            "averageOverallSpeedMps",
            "averageMovingSpeedMps",
            "completionReason",
            "rerouteCount",
            "offRouteCount",
            "schemaVersion",
            "createdAt",
            "updatedAt",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        current = self.instance
        started = attrs.get("started_at", current.started_at if current else None)
        finished = attrs.get("finished_at", current.finished_at if current else None)
        elapsed = attrs.get(
            "elapsed_seconds",
            current.elapsed_seconds if current else None,
        )
        moving = attrs.get(
            "moving_seconds",
            current.moving_seconds if current else None,
        )
        stopped = attrs.get(
            "stopped_seconds",
            current.stopped_seconds if current else None,
        )
        mode = attrs.get("mode", current.mode if current else None)
        group_id = attrs.get("group_id", current.group_id if current else "")

        if started and finished and finished <= started:
            raise serializers.ValidationError(
                {"finishedAt": "finishedAt must be later than startedAt."}
            )
        if elapsed is not None and moving is not None and moving > elapsed:
            raise serializers.ValidationError(
                {"movingSeconds": "movingSeconds cannot exceed elapsedSeconds."}
            )
        if elapsed is not None and stopped is not None and stopped > elapsed:
            raise serializers.ValidationError(
                {"stoppedSeconds": "stoppedSeconds cannot exceed elapsedSeconds."}
            )
        if (
            elapsed is not None
            and moving is not None
            and stopped is not None
            and moving + stopped > elapsed
        ):
            raise serializers.ValidationError(
                {
                    "stoppedSeconds": (
                        "movingSeconds plus stoppedSeconds cannot exceed elapsedSeconds."
                    )
                }
            )
        distance = attrs.get(
            "actual_distance_metres",
            current.actual_distance_metres if current else None,
        )
        if distance is not None and elapsed:
            if Decimal(distance) / Decimal(elapsed) > MAX_SPEED_MPS:
                raise serializers.ValidationError(
                    {
                        "actualDistanceMetres": (
                            "The resulting average overall speed is implausible."
                        )
                    }
                )
        if distance is not None and moving:
            if Decimal(distance) / Decimal(moving) > MAX_SPEED_MPS:
                raise serializers.ValidationError(
                    {
                        "actualDistanceMetres": (
                            "The resulting average moving speed is implausible."
                        )
                    }
                )
        if mode == CompletedDrive.Mode.GROUP and not group_id:
            raise serializers.ValidationError(
                {"groupId": "groupId is required for a group drive."}
            )
        if mode == CompletedDrive.Mode.SOLO:
            attrs["group_id"] = ""

        vehicle_id = attrs.get(
            "vehicle_id",
            current.vehicle_id if current else None,
        )
        if vehicle_id:
            owner_id = self.context["owner_id"]
            try:
                attrs["vehicle"] = VehicleProfile.objects.get(
                    id=vehicle_id,
                    owner_id=owner_id,
                )
            except VehicleProfile.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {"vehicleId": "Vehicle was not found."}
                ) from exc
            attrs.pop("vehicle_id", None)
        elif "vehicle_id" in attrs:
            attrs["vehicle"] = None
            attrs.pop("vehicle_id", None)
        return attrs


class FuelEconomyInputSerializer(StrictFieldsMixin, serializers.Serializer):
    calculationMethod = serializers.ChoiceField(
        choices=FuelEconomyRecord.CalculationMethod.choices
    )
    fuelUsedLitres = FiniteFloatField(
        min_value=0.0001,
        max_value=1000,
        required=False,
    )
    startFuelPercent = FiniteFloatField(
        min_value=0,
        max_value=100,
        required=False,
    )
    endFuelPercent = FiniteFloatField(
        min_value=0,
        max_value=100,
        required=False,
    )
    tankCapacityLitres = FiniteFloatField(
        min_value=1,
        max_value=MAX_VEHICLE_CAPACITY,
        required=False,
    )

    def validate(self, attrs):
        method = attrs["calculationMethod"]
        if method == FuelEconomyRecord.CalculationMethod.OBD_MEASURED:
            raise serializers.ValidationError(
                {"calculationMethod": "OBD ingestion is not supported."}
            )
        if method in {
            FuelEconomyRecord.CalculationMethod.FUEL_USED_ENTRY,
            FuelEconomyRecord.CalculationMethod.FILL_TO_FILL,
        } and "fuelUsedLitres" not in attrs:
            raise serializers.ValidationError(
                {"fuelUsedLitres": "fuelUsedLitres is required for this method."}
            )
        if method == FuelEconomyRecord.CalculationMethod.FUEL_LEVEL_ESTIMATE:
            missing = [
                field
                for field in ("startFuelPercent", "endFuelPercent")
                if field not in attrs
            ]
            if missing:
                raise serializers.ValidationError(
                    {field: "This field is required." for field in missing}
                )
        return attrs


def serialize_fuel_record(record: FuelEconomyRecord) -> dict:
    return {
        "id": str(record.id),
        "completedDriveId": str(record.completed_drive_id),
        "vehicleId": str(record.vehicle_id) if record.vehicle_id else None,
        "vehicleNameSnapshot": record.vehicle_name_snapshot,
        "fuelUsedLitres": float(record.fuel_used_litres),
        "calculationMethod": record.calculation_method,
        "estimated": record.estimated,
        "startFuelPercent": (
            float(record.start_fuel_percent)
            if record.start_fuel_percent is not None
            else None
        ),
        "endFuelPercent": (
            float(record.end_fuel_percent)
            if record.end_fuel_percent is not None
            else None
        ),
        "tankCapacityLitresSnapshot": (
            float(record.tank_capacity_litres_snapshot)
            if record.tank_capacity_litres_snapshot is not None
            else None
        ),
        "economyModelVersion": record.economy_model_version or None,
        "baselineSource": record.baseline_source or None,
        "calculatedMpgUk": float(record.calculated_mpg_uk),
        "calculatedLitresPer100Km": float(record.calculated_litres_per_100km),
        "displayMpgUk": round(float(record.calculated_mpg_uk), 1),
        "displayLitresPer100Km": round(
            float(record.calculated_litres_per_100km),
            1,
        ),
        "explanation": record.explanation,
        "createdAt": record.created_at.isoformat(),
        "updatedAt": record.updated_at.isoformat(),
    }
