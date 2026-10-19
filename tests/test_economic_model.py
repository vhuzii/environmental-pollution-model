"""Перевірка навчальної грошової формули і порівняння сценаріїв."""

import numpy as np
import pytest

from src.models.economic_model import (
    EconomicParameters,
    avoided_damage_uah,
    illustrative_damage_uah,
    mitigation_cost_uah,
    net_effect_uah,
)
from src.models.gaussian_plume import GridSpec, SourceParameters
from src.models.scenario import analyze, reduced_emission_rate


def test_damage_follows_the_documented_cell_formula() -> None:
    parameters = EconomicParameters(
        damage_coefficient_uah_per_person_hour=5.0,
        exposure_duration_h=2.0,
        filter_installation_cost_uah=1000.0,
        filter_operating_cost_uah=500.0,
        population_density_per_km2=1000.0,
    )
    damage = illustrative_damage_uah(
        np.array([[150.0]]),
        cell_area_km2=0.01,
        threshold_ug_m3=50.0,
        parameters=parameters,
    )
    assert damage == pytest.approx(200.0)


def test_no_damage_when_concentration_is_below_threshold() -> None:
    parameters = EconomicParameters(5.0, 2.0, 0.0, 0.0, 1000.0)
    damage = illustrative_damage_uah(
        np.array([[40.0, 50.0]]),
        cell_area_km2=0.01,
        threshold_ug_m3=50.0,
        parameters=parameters,
    )
    assert damage == 0.0


def test_mitigation_cost_is_linear_and_zero_without_reduction() -> None:
    assert mitigation_cost_uah(0, filter_installation_cost_uah=1000, filter_operating_cost_uah=500) == 0
    assert mitigation_cost_uah(30, filter_installation_cost_uah=1000, filter_operating_cost_uah=500) == pytest.approx(
        450.0
    )


def test_net_effect_subtracts_mitigation_cost_from_avoided_damage() -> None:
    assert avoided_damage_uah(200.0, 50.0) == pytest.approx(150.0)
    assert net_effect_uah(150.0, 450.0) == pytest.approx(-300.0)


def test_reduced_emission_is_ten_percent_after_ninety_percent_cut() -> None:
    assert reduced_emission_rate(100.0, 90.0) == pytest.approx(10.0)


def test_scenarios_compare_damage_cost_and_net_effect() -> None:
    source = SourceParameters(
        pollutant="SO2",
        emission_rate_g_s=40.0,
        effective_height_m=0.0,
        wind_speed_m_s=2.0,
        wind_direction_deg=270.0,
        stability_class="D",
        decay_coefficient_per_s=0.0,
        background_concentration_ug_m3=0.0,
        sigma_y_m=40.0,
        sigma_z_m=20.0,
    )
    economics = EconomicParameters(
        damage_coefficient_uah_per_person_hour=10.0,
        exposure_duration_h=8.0,
        filter_installation_cost_uah=1000.0,
        filter_operating_cost_uah=500.0,
        population_density_per_km2=500.0,
    )
    analysis = analyze(
        source,
        GridSpec(width_m=600.0, length_m=800.0, step_m=100.0),
        threshold_ug_m3=1.0,
        economics=economics,
        reduction_percents=(0.0, 30.0, 60.0, 90.0),
        selected_reduction_percent=0.0,
    )
    by_percent = {item.reduction_percent: item for item in analysis.scenarios}
    baseline = by_percent[0.0]
    strong = by_percent[90.0]
    assert baseline.mitigation_cost_uah == 0.0
    assert baseline.net_effect_uah == 0.0
    assert strong.max_concentration_ug_m3 == pytest.approx(0.1 * baseline.max_concentration_ug_m3)
    assert strong.damage_uah < baseline.damage_uah
    assert strong.mitigation_cost_uah == pytest.approx(0.9 * 1500.0)
    assert strong.net_effect_uah == pytest.approx(strong.avoided_damage_uah - strong.mitigation_cost_uah)
    assert strong.avoided_damage_uah == pytest.approx(baseline.damage_uah - strong.damage_uah)
