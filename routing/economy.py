from dataclasses import dataclass
from decimal import Decimal
import math


UK_LITRES_PER_GALLON = 4.54609
METRES_PER_MILE = 1609.344
ECONOMY_MODEL_VERSION = "vehicle-profile-v1"
MAX_FUEL_LITRES = 1000.0
MAX_DISTANCE_METRES = 10_000_000.0
MAX_PLAUSIBLE_MPG_UK = 500.0
MAX_PLAUSIBLE_LITRES_PER_100KM = 100.0


class EconomyCalculationError(ValueError):
    pass


@dataclass(frozen=True)
class EconomyResult:
    fuel_used_litres: float
    mpg_uk: float
    litres_per_100km: float
    display_mpg_uk: float
    display_litres_per_100km: float
    estimated: bool
    calculation_method: str
    source: str
    model_version: str
    explanation: str


def calculate_fuel_economy(
    *,
    distance_metres,
    fuel_used_litres,
    calculation_method: str,
    estimated: bool,
    source: str,
    model_version: str = "",
    explanation: str = "",
) -> EconomyResult:
    distance = _finite_positive(distance_metres, "distance")
    fuel = _finite_positive(fuel_used_litres, "fuel amount")
    if distance > MAX_DISTANCE_METRES:
        raise EconomyCalculationError("Distance is implausibly large.")
    if fuel > MAX_FUEL_LITRES:
        raise EconomyCalculationError("Fuel amount is implausibly large.")

    distance_miles = distance / METRES_PER_MILE
    distance_km = distance / 1000.0
    mpg_uk = distance_miles / (fuel / UK_LITRES_PER_GALLON)
    litres_per_100km = (fuel / distance_km) * 100
    if (
        mpg_uk > MAX_PLAUSIBLE_MPG_UK
        or litres_per_100km > MAX_PLAUSIBLE_LITRES_PER_100KM
    ):
        raise EconomyCalculationError("Calculated economy is implausible.")

    return EconomyResult(
        fuel_used_litres=fuel,
        mpg_uk=mpg_uk,
        litres_per_100km=litres_per_100km,
        display_mpg_uk=round(mpg_uk, 1),
        display_litres_per_100km=round(litres_per_100km, 1),
        estimated=estimated,
        calculation_method=calculation_method,
        source=source,
        model_version=model_version,
        explanation=explanation,
    )


def calculate_fuel_level_estimate(
    *,
    distance_metres,
    start_fuel_percent,
    end_fuel_percent,
    tank_capacity_litres,
) -> EconomyResult:
    start = _percentage(start_fuel_percent, "start fuel percentage")
    end = _percentage(end_fuel_percent, "end fuel percentage")
    tank = _finite_positive(tank_capacity_litres, "tank capacity")
    if tank > 300:
        raise EconomyCalculationError("Tank capacity is implausibly large.")
    if end >= start:
        raise EconomyCalculationError(
            "End fuel percentage must be lower than start fuel percentage."
        )
    fuel_used = tank * ((start - end) / 100)
    return calculate_fuel_economy(
        distance_metres=distance_metres,
        fuel_used_litres=fuel_used,
        calculation_method="fuel_level_estimate",
        estimated=True,
        source="fuel_level_estimate",
        explanation="Estimated from tank capacity and the reported fuel-level change.",
    )


def calculate_vehicle_profile_estimate(
    *,
    distance_metres,
    baseline_mpg_uk=None,
    baseline_litres_per_100km=None,
    baseline_source: str,
    average_moving_speed_mps=None,
    stopped_time_proportion=None,
) -> EconomyResult | None:
    distance = _finite_positive(distance_metres, "distance")
    baseline_l_per_100km = _baseline_litres_per_100km(
        baseline_mpg_uk,
        baseline_litres_per_100km,
    )
    if baseline_l_per_100km is None or baseline_source == "none":
        return None

    adjustment = 1.0
    reasons = []
    if average_moving_speed_mps is not None:
        speed = _finite_non_negative(average_moving_speed_mps, "moving speed")
        if speed < 8:
            speed_penalty = min((8 - speed) / 8 * 0.12, 0.12)
            adjustment += speed_penalty
            reasons.append("low average moving speed")
        elif speed > 31:
            speed_penalty = min((speed - 31) / 20 * 0.10, 0.10)
            adjustment += speed_penalty
            reasons.append("high average moving speed")

    if stopped_time_proportion is not None:
        stopped = float(stopped_time_proportion)
        if not math.isfinite(stopped) or not 0 <= stopped <= 1:
            raise EconomyCalculationError("Stopped-time proportion is invalid.")
        stop_penalty = min(stopped * 0.20, 0.10)
        adjustment += stop_penalty
        if stop_penalty:
            reasons.append("stopped-time proportion")

    # Version 1 deliberately limits adjustment to 25% above the supplied baseline.
    adjustment = min(max(adjustment, 0.85), 1.25)
    estimated_l_per_100km = baseline_l_per_100km * adjustment
    fuel_used = (distance / 1000) * estimated_l_per_100km / 100
    reason_text = ", ".join(reasons) if reasons else "no drive adjustment"
    return calculate_fuel_economy(
        distance_metres=distance,
        fuel_used_litres=fuel_used,
        calculation_method="vehicle_profile_estimate",
        estimated=True,
        source=baseline_source,
        model_version=ECONOMY_MODEL_VERSION,
        explanation=(
            f"Profile baseline adjusted by {round(adjustment, 2)}x for "
            f"{reason_text}; adjustment is bounded to 0.85x-1.25x."
        ),
    )


def decimal_value(value: float, places: str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal(places))


def _baseline_litres_per_100km(mpg_uk, litres_per_100km):
    if litres_per_100km is not None:
        value = _finite_positive(litres_per_100km, "economy baseline")
        if value > MAX_PLAUSIBLE_LITRES_PER_100KM:
            raise EconomyCalculationError("Economy baseline is implausible.")
        return value
    if mpg_uk is not None:
        mpg = _finite_positive(mpg_uk, "economy baseline")
        if mpg > MAX_PLAUSIBLE_MPG_UK:
            raise EconomyCalculationError("Economy baseline is implausible.")
        return 282.4809363 / mpg
    return None


def _percentage(value, label: str) -> float:
    number = _finite_non_negative(value, label)
    if number > 100:
        raise EconomyCalculationError(f"{label.capitalize()} must not exceed 100.")
    return number


def _finite_positive(value, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise EconomyCalculationError(f"{label.capitalize()} must be greater than zero.")
    return number


def _finite_non_negative(value, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise EconomyCalculationError(f"{label.capitalize()} is invalid.")
    return number
