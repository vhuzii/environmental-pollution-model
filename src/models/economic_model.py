"""Навчальна грошова оцінка впливу перевищення концентрації.

Усі коефіцієнти першої версії є припущеннями. Результат не є офіційною
оцінкою збитків і не спирається на затверджену методику.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EconomicParameters:
    """Грошові припущення одного розрахунку. Суми задані в гривнях."""

    damage_coefficient_uah_per_person_hour: float
    exposure_duration_h: float
    filter_installation_cost_uah: float
    filter_operating_cost_uah: float
    population_density_per_km2: float


def illustrative_damage_uah(
    concentration_ug_m3: np.ndarray,
    *,
    cell_area_km2: float,
    threshold_ug_m3: float,
    parameters: EconomicParameters,
) -> float:
    """Повертає навчальний збиток, грн, як суму по комірках із перевищенням.

    Для кожної комірки, де C > C_lim:

    D_i = k · N_i · T · (C_i - C_lim) / C_lim
    N_i = ρ · A_i

    k — умовна вартість одиниці відносного перевищення на одну особу за годину, грн;
    T — тривалість впливу, год;
    ρ — густота населення, осіб/км²;
    A_i — площа комірки, км².

    Оскільки густота однакова, N_i виноситься за знак суми.
    """
    if threshold_ug_m3 <= 0:
        raise ValueError("Граничний рівень має бути додатним.")
    if cell_area_km2 < 0:
        raise ValueError("Площа комірки не може бути від'ємною.")
    relative_excess = np.maximum(concentration_ug_m3 - threshold_ug_m3, 0.0) / threshold_ug_m3
    population_per_cell = parameters.population_density_per_km2 * cell_area_km2
    damage = (
        parameters.damage_coefficient_uah_per_person_hour
        * population_per_cell
        * parameters.exposure_duration_h
        * float(np.sum(relative_excess))
    )
    return float(damage)


def mitigation_cost_uah(
    emission_reduction_percent: float,
    *,
    filter_installation_cost_uah: float,
    filter_operating_cost_uah: float,
) -> float:
    """Повертає навчальну вартість заходу, грн.

    Введені капітальні та експлуатаційні суми відповідають повному скороченню викидів.
    Для сценарію p% вартість лінійно зменшується:

    C_mit(p) = (p / 100) · (C_inst + C_op)

    Для базового сценарію p = 0 вартість дорівнює нулю. Лінійність є припущенням.
    """
    if emission_reduction_percent < 0 or emission_reduction_percent > 100:
        raise ValueError("Відсоток зменшення викидів має бути в межах від 0 до 100.")
    full_cost = filter_installation_cost_uah + filter_operating_cost_uah
    return float(emission_reduction_percent / 100.0 * full_cost)


def avoided_damage_uah(baseline_damage_uah: float, scenario_damage_uah: float) -> float:
    """Повертає зменшення навчального збитку відносно сценарію без очищення, грн."""
    return float(baseline_damage_uah - scenario_damage_uah)


def net_effect_uah(avoided_damage: float, mitigation_cost: float) -> float:
    """Повертає чистий навчальний ефект, грн: уникнений збиток мінус вартість заходу."""
    return float(avoided_damage - mitigation_cost)
