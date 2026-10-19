"""Порівняння сценаріїв зменшення викидів на спільній сітці."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from src.models.economic_model import (
    EconomicParameters,
    avoided_damage_uah,
    illustrative_damage_uah,
    mitigation_cost_uah,
    net_effect_uah,
)
from src.models.gaussian_plume import (
    ConcentrationField,
    EnvironmentalSummary,
    GridSpec,
    SourceParameters,
    simulate,
)
from src.utils.units import m2_to_km2
from src.utils.validation import validate_model_inputs

_PRESET_NAMES: dict[float, str] = {
    0.0: "Базовий сценарій без очищення",
    30.0: "Зменшення викидів на 30%",
    60.0: "Зменшення викидів на 60%",
    90.0: "Зменшення викидів на 90%",
}


@dataclass(frozen=True)
class ScenarioResult:
    """Екологічні та навчальні економічні показники одного сценарію."""

    name: str
    reduction_percent: float
    emission_rate_g_s: float
    max_concentration_ug_m3: float
    mean_concentration_ug_m3: float
    polluted_area_km2: float
    polluted_fraction: float
    exposed_population: float
    damage_uah: float
    mitigation_cost_uah: float
    avoided_damage_uah: float
    net_effect_uah: float

    def to_dict(self) -> dict[str, float | str]:
        """Повертає показники як словник для таблиці, CSV і JSON."""
        return asdict(self)


@dataclass(frozen=True)
class AnalysisResult:
    """Усі сценарії та поле концентрації для сценарію, показаного на карті."""

    scenarios: tuple[ScenarioResult, ...]
    selected: ScenarioResult
    field: ConcentrationField
    summary: EnvironmentalSummary


def reduced_emission_rate(emission_rate_g_s: float, reduction_percent: float) -> float:
    """Повертає інтенсивність викиду після скорочення на p відсотків, г/с."""
    if reduction_percent < 0 or reduction_percent > 100:
        raise ValueError("Відсоток зменшення викидів має бути в межах від 0 до 100.")
    return float(emission_rate_g_s * (1.0 - reduction_percent / 100.0))


def scenario_name(reduction_percent: float) -> str:
    """Повертає підпис сценарію українською мовою."""
    for preset, name in _PRESET_NAMES.items():
        if abs(preset - reduction_percent) < 1e-6:
            return name
    return f"Обраний сценарій: зменшення на {reduction_percent:g}%"


def analyze(
    source: SourceParameters,
    grid: GridSpec,
    *,
    threshold_ug_m3: float,
    economics: EconomicParameters,
    reduction_percents: tuple[float, ...] | list[float],
    selected_reduction_percent: float,
) -> AnalysisResult:
    """Порівнює сценарії і зберігає поле концентрації обраного відсотка скорочення.

    Чистий ефект завжди рахується відносно базового сценарію без очищення:

    net_effect = (D_0 - D_p) - C_mit(p)
    """
    validate_model_inputs(
        pollutant=source.pollutant,
        emission_rate_g_s=source.emission_rate_g_s,
        effective_height_m=source.effective_height_m,
        wind_speed_m_s=source.wind_speed_m_s,
        wind_direction_deg=source.wind_direction_deg,
        stability_class=source.stability_class,
        decay_coefficient_per_s=source.decay_coefficient_per_s,
        background_concentration_ug_m3=source.background_concentration_ug_m3,
        threshold_ug_m3=threshold_ug_m3,
        domain_width_m=grid.width_m,
        domain_length_m=grid.length_m,
        grid_step_m=grid.step_m,
        population_density_per_km2=economics.population_density_per_km2,
        exposure_duration_h=economics.exposure_duration_h,
        damage_coefficient_uah=economics.damage_coefficient_uah_per_person_hour,
        filter_installation_cost_uah=economics.filter_installation_cost_uah,
        filter_operating_cost_uah=economics.filter_operating_cost_uah,
        emission_reduction_percent=selected_reduction_percent,
        sigma_y_m=source.sigma_y_m,
        sigma_z_m=source.sigma_z_m,
    )
    percents = _normalize_percents(reduction_percents, selected_reduction_percent)
    cell_area_km2 = m2_to_km2(grid.step_m * grid.step_m)
    pending: list[tuple[float, EnvironmentalSummary, float, ConcentrationField]] = []
    selected_field: ConcentrationField | None = None
    selected_summary: EnvironmentalSummary | None = None

    for percent in percents:
        scenario_source = replace(
            source,
            emission_rate_g_s=reduced_emission_rate(source.emission_rate_g_s, percent),
        )
        simulation = simulate(
            scenario_source,
            grid,
            threshold_ug_m3=threshold_ug_m3,
            population_density_per_km2=economics.population_density_per_km2,
        )
        damage = illustrative_damage_uah(
            simulation.field.concentration_ug_m3,
            cell_area_km2=cell_area_km2,
            threshold_ug_m3=threshold_ug_m3,
            parameters=economics,
        )
        pending.append((percent, simulation.summary, damage, simulation.field))
        if abs(percent - selected_reduction_percent) < 1e-6:
            selected_field = simulation.field
            selected_summary = simulation.summary

    if selected_field is None or selected_summary is None:
        raise ValueError("Не вдалося побудувати поле для обраного сценарію.")

    baseline_damage = next(damage for percent, _, damage, _ in pending if abs(percent) < 1e-6)
    scenarios: list[ScenarioResult] = []
    for percent, summary, damage, _field in pending:
        cost = mitigation_cost_uah(
            percent,
            filter_installation_cost_uah=economics.filter_installation_cost_uah,
            filter_operating_cost_uah=economics.filter_operating_cost_uah,
        )
        avoided = avoided_damage_uah(baseline_damage, damage)
        scenarios.append(
            ScenarioResult(
                name=scenario_name(percent),
                reduction_percent=percent,
                emission_rate_g_s=reduced_emission_rate(source.emission_rate_g_s, percent),
                max_concentration_ug_m3=summary.max_concentration_ug_m3,
                mean_concentration_ug_m3=summary.mean_concentration_ug_m3,
                polluted_area_km2=summary.polluted_area_km2,
                polluted_fraction=summary.polluted_fraction,
                exposed_population=summary.exposed_population,
                damage_uah=damage,
                mitigation_cost_uah=cost,
                avoided_damage_uah=avoided,
                net_effect_uah=net_effect_uah(avoided, cost),
            )
        )

    selected = next(item for item in scenarios if abs(item.reduction_percent - selected_reduction_percent) < 1e-6)
    return AnalysisResult(
        scenarios=tuple(scenarios),
        selected=selected,
        field=selected_field,
        summary=selected_summary,
    )


def _normalize_percents(
    reduction_percents: tuple[float, ...] | list[float],
    selected_reduction_percent: float,
) -> list[float]:
    values = [0.0]
    for raw in list(reduction_percents) + [selected_reduction_percent]:
        value = float(raw)
        if value < 0 or value > 100:
            raise ValueError("Відсоток зменшення викидів має бути в межах від 0 до 100.")
        if all(abs(value - existing) > 1e-6 for existing in values):
            values.append(value)
    return values
