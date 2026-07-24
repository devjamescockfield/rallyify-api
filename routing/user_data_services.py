from decimal import Decimal
import hashlib
import json

from django.db import IntegrityError, transaction

from routing.economy import (
    EconomyCalculationError,
    calculate_fuel_economy,
    calculate_fuel_level_estimate,
    calculate_vehicle_profile_estimate,
    decimal_value,
)
from routing.models import CompletedDrive, FuelEconomyRecord, VehicleProfile


class DriveIdempotencyConflict(Exception):
    pass


def set_default_vehicle(vehicle: VehicleProfile) -> VehicleProfile:
    with transaction.atomic():
        VehicleProfile.objects.filter(
            owner_id=vehicle.owner_id,
            is_default=True,
        ).exclude(id=vehicle.id).update(is_default=False)
        if not vehicle.is_default:
            vehicle.is_default = True
            vehicle.save(update_fields=["is_default", "updated_at"])
    return vehicle


def clear_default_if_requested(vehicle: VehicleProfile) -> None:
    if vehicle.is_default:
        VehicleProfile.objects.filter(id=vehicle.id).update(is_default=False)


def create_completed_drive(*, owner_id, validated_data):
    payload = _canonical_drive_payload(validated_data)
    fingerprint = _fingerprint_drive_payload(payload)
    completion_id = payload["completion_id"]
    existing = CompletedDrive.objects.filter(
        owner_id=owner_id,
        completion_id=completion_id,
    ).first()
    if existing:
        if existing.payload_fingerprint != fingerprint:
            raise DriveIdempotencyConflict
        return existing, True

    vehicle = payload.get("vehicle")
    if vehicle:
        payload["vehicle_name_snapshot"] = vehicle.display_name
    payload.update(_canonical_speeds(payload))
    try:
        with transaction.atomic():
            drive = CompletedDrive.objects.create(
                owner_id=owner_id,
                payload_fingerprint=fingerprint,
                **payload,
            )
    except IntegrityError:
        existing = CompletedDrive.objects.get(
            owner_id=owner_id,
            completion_id=completion_id,
        )
        if existing.payload_fingerprint != fingerprint:
            raise DriveIdempotencyConflict from None
        return existing, True
    return drive, False


def update_completed_drive(drive: CompletedDrive, validated_data):
    payload = dict(validated_data)
    vehicle = payload.get("vehicle", drive.vehicle)
    if "vehicle" in payload and vehicle:
        payload["vehicle_name_snapshot"] = vehicle.display_name
    combined = {
        "actual_distance_metres": payload.get(
            "actual_distance_metres",
            drive.actual_distance_metres,
        ),
        "elapsed_seconds": payload.get("elapsed_seconds", drive.elapsed_seconds),
        "moving_seconds": payload.get("moving_seconds", drive.moving_seconds),
    }
    payload.update(_canonical_speeds(combined))
    for field, value in payload.items():
        setattr(drive, field, value)
    drive.save()
    return drive


def upsert_fuel_record(*, drive: CompletedDrive, validated_data: dict):
    method = validated_data["calculationMethod"]
    vehicle = drive.vehicle
    tank_capacity = validated_data.get("tankCapacityLitres")
    if tank_capacity is None and vehicle:
        tank_capacity = vehicle.tank_capacity_litres

    if method == FuelEconomyRecord.CalculationMethod.FUEL_LEVEL_ESTIMATE:
        if tank_capacity is None:
            raise EconomyCalculationError(
                "Tank capacity is required for a fuel-level estimate."
            )
        result = calculate_fuel_level_estimate(
            distance_metres=drive.actual_distance_metres,
            start_fuel_percent=validated_data["startFuelPercent"],
            end_fuel_percent=validated_data["endFuelPercent"],
            tank_capacity_litres=tank_capacity,
        )
    elif method == FuelEconomyRecord.CalculationMethod.VEHICLE_PROFILE_ESTIMATE:
        if not vehicle:
            raise EconomyCalculationError(
                "A linked vehicle with an economy baseline is required."
            )
        stopped_proportion = (
            drive.stopped_seconds / drive.elapsed_seconds
            if drive.elapsed_seconds
            else None
        )
        result = calculate_vehicle_profile_estimate(
            distance_metres=drive.actual_distance_metres,
            baseline_mpg_uk=vehicle.typical_mpg_uk,
            baseline_litres_per_100km=vehicle.typical_litres_per_100km,
            baseline_source=vehicle.economy_baseline_source,
            average_moving_speed_mps=drive.average_moving_speed_mps,
            stopped_time_proportion=stopped_proportion,
        )
        if result is None:
            raise EconomyCalculationError(
                "The linked vehicle has no usable economy baseline."
            )
    else:
        result = calculate_fuel_economy(
            distance_metres=drive.actual_distance_metres,
            fuel_used_litres=validated_data["fuelUsedLitres"],
            calculation_method=method,
            estimated=False,
            source=method,
            explanation=(
                "Calculated from the fuel amount entered for this completed drive."
            ),
        )

    defaults = {
        "vehicle": vehicle,
        "vehicle_name_snapshot": (
            vehicle.display_name if vehicle else drive.vehicle_name_snapshot
        ),
        "fuel_used_litres": decimal_value(result.fuel_used_litres, "0.0001"),
        "calculation_method": result.calculation_method,
        "estimated": result.estimated,
        "start_fuel_percent": validated_data.get("startFuelPercent"),
        "end_fuel_percent": validated_data.get("endFuelPercent"),
        "tank_capacity_litres_snapshot": tank_capacity,
        "economy_model_version": result.model_version,
        "baseline_source": result.source,
        "calculated_mpg_uk": decimal_value(result.mpg_uk, "0.0001"),
        "calculated_litres_per_100km": decimal_value(
            result.litres_per_100km,
            "0.0001",
        ),
        "explanation": result.explanation,
    }
    with transaction.atomic():
        record, _ = FuelEconomyRecord.objects.update_or_create(
            completed_drive=drive,
            defaults=defaults,
        )
    return record


def _canonical_speeds(payload):
    distance = Decimal(str(payload["actual_distance_metres"]))
    elapsed = payload["elapsed_seconds"]
    moving = payload["moving_seconds"]
    return {
        "average_overall_speed_mps": (
            distance / Decimal(elapsed)
        ).quantize(Decimal("0.001")),
        "average_moving_speed_mps": (
            (distance / Decimal(moving)).quantize(Decimal("0.001"))
            if moving
            else None
        ),
    }


def _fingerprint_drive_payload(payload):
    normalized = {
        key: (
            str(value.id)
            if isinstance(value, VehicleProfile)
            else value.isoformat()
            if hasattr(value, "isoformat")
            else str(value)
            if isinstance(value, Decimal)
            else value
        )
        for key, value in payload.items()
    }
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_drive_payload(validated_data):
    payload = dict(validated_data)
    vehicle = payload.get("vehicle")
    defaults = {
        "vehicle": None,
        "vehicle_name_snapshot": "",
        "route_title_snapshot": "",
        "route_id": "",
        "group_id": "",
        "planned_distance_metres": None,
        "reroute_count": None,
        "off_route_count": None,
    }
    canonical = {**defaults, **payload}
    if vehicle:
        canonical["vehicle_name_snapshot"] = vehicle.display_name
    return canonical
