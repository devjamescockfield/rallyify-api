import pytest

from routing.economy import (
    EconomyCalculationError,
    calculate_fuel_economy,
    calculate_vehicle_profile_estimate,
)


def test_uk_gallon_conversion_and_display_values():
    result = calculate_fuel_economy(
        distance_metres=160_934.4,
        fuel_used_litres=4.54609,
        calculation_method="fuel_used_entry",
        estimated=False,
        source="fuel_used_entry",
    )
    assert result.mpg_uk == pytest.approx(100)
    assert result.litres_per_100km == pytest.approx(2.824809363)
    assert result.display_mpg_uk == 100.0
    assert result.display_litres_per_100km == 2.8
    assert result.estimated is False


@pytest.mark.parametrize(
    "distance,fuel",
    [(0, 1), (-1, 1), (1000, 0), (1000, -1), (10_000_001, 1), (1000, 1001)],
)
def test_invalid_or_implausible_inputs_are_rejected(distance, fuel):
    with pytest.raises(EconomyCalculationError):
        calculate_fuel_economy(
            distance_metres=distance,
            fuel_used_litres=fuel,
            calculation_method="fuel_used_entry",
            estimated=False,
            source="fuel_used_entry",
        )


def test_profile_estimate_is_omitted_without_baseline():
    result = calculate_vehicle_profile_estimate(
        distance_metres=100_000,
        baseline_source="none",
    )
    assert result is None


def test_profile_adjustment_is_bounded_and_deterministic():
    inputs = {
        "distance_metres": 100_000,
        "baseline_litres_per_100km": 8,
        "baseline_source": "user_entered",
        "average_moving_speed_mps": 0,
        "stopped_time_proportion": 1,
    }
    first = calculate_vehicle_profile_estimate(**inputs)
    second = calculate_vehicle_profile_estimate(**inputs)
    assert first == second
    assert first.fuel_used_litres == pytest.approx(9.76)
    assert first.model_version == "vehicle-profile-v1"
    assert first.estimated is True
    assert "bounded to 0.85x-1.25x" in first.explanation
