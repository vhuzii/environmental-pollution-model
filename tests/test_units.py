"""Перевірка перетворень г/м³ → мкг/м³ і м² → км²."""

import pytest

from src.utils.units import g_per_m3_to_ug_per_m3, m2_to_km2, ug_per_m3_to_g_per_m3
from src.utils.validation import ModelInputError, validate_model_inputs


def test_one_gram_per_cubic_meter_is_one_million_micrograms() -> None:
    assert g_per_m3_to_ug_per_m3(1.0) == 1_000_000.0


def test_milligram_scale_conversion_and_roundtrip() -> None:
    assert g_per_m3_to_ug_per_m3(0.001) == pytest.approx(1000.0)
    assert ug_per_m3_to_g_per_m3(250.0) == pytest.approx(0.00025)
    assert ug_per_m3_to_g_per_m3(g_per_m3_to_ug_per_m3(0.0125)) == pytest.approx(0.0125)


def test_square_meters_to_square_kilometers() -> None:
    assert m2_to_km2(1_000_000.0) == pytest.approx(1.0)
    assert m2_to_km2(10_000.0) == pytest.approx(0.01)


def test_validation_rejects_zero_wind_and_unknown_stability() -> None:
    with pytest.raises(ModelInputError, match="вітру"):
        _validate(wind_speed_m_s=0.0)
    with pytest.raises(ModelInputError, match="стійкості"):
        _validate(stability_class="Z")


def _validate(**overrides: object) -> None:
    values: dict[str, object] = {
        "pollutant": "SO2",
        "emission_rate_g_s": 1.0,
        "effective_height_m": 10.0,
        "wind_speed_m_s": 2.0,
        "wind_direction_deg": 180.0,
        "stability_class": "D",
        "decay_coefficient_per_s": 0.0,
        "background_concentration_ug_m3": 0.0,
        "threshold_ug_m3": 50.0,
        "domain_width_m": 1000.0,
        "domain_length_m": 1000.0,
        "grid_step_m": 100.0,
        "population_density_per_km2": 10.0,
        "exposure_duration_h": 1.0,
        "damage_coefficient_uah": 1.0,
        "filter_installation_cost_uah": 1.0,
        "filter_operating_cost_uah": 1.0,
        "emission_reduction_percent": 0.0,
    }
    values.update(overrides)
    validate_model_inputs(**values)  # type: ignore[arg-type]
