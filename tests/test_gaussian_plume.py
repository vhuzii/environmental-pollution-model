"""Перевірка гаусової моделі на формулі, напрямку вітру та межах застосовності."""

import math

import numpy as np
import pytest

from src.models.gaussian_plume import (
    GridSpec,
    SourceParameters,
    briggs_sigmas,
    centerline_profile,
    ground_level_concentration_g_m3,
    simulate,
    summarize_field,
    to_plume_coordinates,
)
from src.utils.units import g_per_m3_to_ug_per_m3


def test_ground_concentration_matches_analytical_formula() -> None:
    concentration = ground_level_concentration_g_m3(
        np.array([100.0]),
        np.array([0.0]),
        emission_rate_g_s=10.0,
        wind_speed_m_s=2.0,
        effective_height_m=0.0,
        stability_class="D",
        decay_coefficient_per_s=0.0,
        sigma_y_m=50.0,
        sigma_z_m=20.0,
    )
    expected_g_m3 = 10.0 / (2.0 * math.pi * 2.0 * 50.0 * 20.0) * (1.0 + 1.0)
    assert concentration[0] == pytest.approx(expected_g_m3)
    assert g_per_m3_to_ug_per_m3(concentration[0]) == pytest.approx(expected_g_m3 * 1_000_000.0)


def test_both_reflection_terms_are_used_for_elevated_source() -> None:
    concentration = ground_level_concentration_g_m3(
        np.array([100.0]),
        np.array([0.0]),
        emission_rate_g_s=10.0,
        wind_speed_m_s=2.0,
        effective_height_m=50.0,
        stability_class="D",
        decay_coefficient_per_s=0.0,
        sigma_y_m=50.0,
        sigma_z_m=20.0,
    )
    vertical = 2.0 * math.exp(-(50.0**2) / (2.0 * 20.0**2))
    expected = 10.0 / (2.0 * math.pi * 2.0 * 50.0 * 20.0) * vertical
    assert concentration[0] == pytest.approx(expected)


def test_decay_reduces_concentration_along_the_plume() -> None:
    shared = {
        "emission_rate_g_s": 10.0,
        "wind_speed_m_s": 2.0,
        "effective_height_m": 0.0,
        "stability_class": "D",
        "sigma_y_m": 50.0,
        "sigma_z_m": 20.0,
    }
    fresh = ground_level_concentration_g_m3(np.array([100.0]), np.array([0.0]), decay_coefficient_per_s=0.0, **shared)
    decayed = ground_level_concentration_g_m3(
        np.array([100.0]), np.array([0.0]), decay_coefficient_per_s=0.01, **shared
    )
    assert decayed[0] == pytest.approx(fresh[0] * math.exp(-0.5))


def test_upwind_plume_contribution_is_zero() -> None:
    concentration = ground_level_concentration_g_m3(
        np.array([-50.0, 0.0]),
        np.array([0.0, 0.0]),
        emission_rate_g_s=10.0,
        wind_speed_m_s=2.0,
        effective_height_m=0.0,
        stability_class="D",
        decay_coefficient_per_s=0.0,
        sigma_y_m=50.0,
        sigma_z_m=20.0,
    )
    assert concentration.tolist() == [0.0, 0.0]


def test_zero_wind_is_rejected() -> None:
    with pytest.raises(ValueError, match="додатною"):
        ground_level_concentration_g_m3(
            np.array([100.0]),
            np.array([0.0]),
            emission_rate_g_s=1.0,
            wind_speed_m_s=0.0,
            effective_height_m=10.0,
            stability_class="D",
            decay_coefficient_per_s=0.0,
        )


def test_emission_scales_concentration_above_background() -> None:
    low = _simulate(emission_rate_g_s=10.0)
    high = _simulate(emission_rate_g_s=20.0)
    background = 5.0
    assert high.summary.max_concentration_ug_m3 - background == pytest.approx(
        2.0 * (low.summary.max_concentration_ug_m3 - background)
    )


def test_wind_from_the_west_puts_the_maximum_to_the_east() -> None:
    result = _simulate(wind_direction_deg=270.0)
    assert result.summary.max_east_m > 0
    assert result.summary.max_downwind_m > 0
    west = result.field.concentration_ug_m3[:, 0]
    assert west == pytest.approx(np.full(west.shape, 5.0))


def test_briggs_sigma_grows_with_distance_for_class_d() -> None:
    near_y, near_z = briggs_sigmas(500.0, "D")
    far_y, far_z = briggs_sigmas(2000.0, "D")
    expected_y = 0.08 * 1000.0 / math.sqrt(1.0 + 0.0001 * 1000.0)
    actual_y, _actual_z = briggs_sigmas(1000.0, "D")
    assert float(actual_y) == pytest.approx(expected_y)
    assert float(far_y) > float(near_y)
    assert float(far_z) > float(near_z)


def test_invalid_stability_class_is_rejected() -> None:
    with pytest.raises(ValueError):
        briggs_sigmas(100.0, "Z")


def test_coordinate_rotation_for_north_wind() -> None:
    downwind, crosswind = to_plume_coordinates(np.array([0.0]), np.array([-100.0]), 0.0)
    assert float(downwind[0]) == pytest.approx(100.0)
    assert float(crosswind[0]) == pytest.approx(0.0)


def test_exposed_population_uses_polluted_area_and_density() -> None:
    result = _simulate(threshold_ug_m3=1.0, population_density_per_km2=250.0)
    assert result.summary.exposed_population == pytest.approx(result.summary.polluted_area_km2 * 250.0)
    assert result.summary.polluted_area_km2 > 0


def test_centerline_contains_the_downwind_maximum() -> None:
    result = _simulate()
    _distance, concentration = centerline_profile(result.field)
    assert float(np.max(concentration)) == pytest.approx(result.summary.max_concentration_ug_m3)


def test_summary_area_for_a_known_mask() -> None:
    concentration = np.array([[10.0, 80.0], [80.0, 10.0]])
    field = _simulate().field
    synthetic = type(field)(
        east_m=np.array([0.0, 1000.0]),
        north_m=np.array([0.0, 1000.0]),
        concentration_ug_m3=concentration,
        downwind_m=np.zeros((2, 2)),
        crosswind_m=np.zeros((2, 2)),
        step_m=1000.0,
    )
    summary = summarize_field(synthetic, threshold_ug_m3=50.0, population_density_per_km2=10.0)
    assert summary.polluted_area_km2 == pytest.approx(2.0)
    assert summary.polluted_fraction == pytest.approx(0.5)
    assert summary.exposed_population == pytest.approx(20.0)


def _simulate(**overrides: float):
    values = {
        "pollutant": "SO2",
        "emission_rate_g_s": 25.0,
        "effective_height_m": 80.0,
        "wind_speed_m_s": 3.5,
        "wind_direction_deg": 270.0,
        "stability_class": "D",
        "decay_coefficient_per_s": 0.0,
        "background_concentration_ug_m3": 5.0,
        "threshold_ug_m3": 50.0,
        "population_density_per_km2": 400.0,
    }
    values.update(overrides)
    source = SourceParameters(
        pollutant=str(values["pollutant"]),
        emission_rate_g_s=float(values["emission_rate_g_s"]),
        effective_height_m=float(values["effective_height_m"]),
        wind_speed_m_s=float(values["wind_speed_m_s"]),
        wind_direction_deg=float(values["wind_direction_deg"]),
        stability_class=str(values["stability_class"]),
        decay_coefficient_per_s=float(values["decay_coefficient_per_s"]),
        background_concentration_ug_m3=float(values["background_concentration_ug_m3"]),
    )
    grid = GridSpec(width_m=2000.0, length_m=2000.0, step_m=100.0)
    return simulate(
        source,
        grid,
        threshold_ug_m3=float(values["threshold_ug_m3"]),
        population_density_per_km2=float(values["population_density_per_km2"]),
    )
