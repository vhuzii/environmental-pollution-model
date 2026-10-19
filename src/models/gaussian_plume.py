"""Навчальна гаусова модель шлейфу від постійного точкового джерела.

Формула є спрощенням для заняття. Вона не замінює промислові моделі
(AERMOD, CALPUFF, ОНД-86) і не призначена для дозвільної документації.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src.utils.units import g_per_m3_to_ug_per_m3, m2_to_km2

STABILITY_CLASSES: tuple[str, ...] = ("A", "B", "C", "D", "E", "F")
_SIGMA_Y_FACTOR: dict[str, float] = {
    "A": 0.22,
    "B": 0.16,
    "C": 0.11,
    "D": 0.08,
    "E": 0.06,
    "F": 0.04,
}
# Мінімальна відстань для σ, щоб уникнути ділення на нуль у точці джерела.
_MIN_SIGMA_DISTANCE_M = 1.0
_MIN_SIGMA_M = 1e-6


@dataclass(frozen=True)
class SourceParameters:
    """Параметри стаціонарного точкового джерела."""

    pollutant: str
    emission_rate_g_s: float
    effective_height_m: float
    wind_speed_m_s: float
    wind_direction_deg: float
    stability_class: str
    decay_coefficient_per_s: float
    background_concentration_ug_m3: float
    sigma_y_m: float | None = None
    sigma_z_m: float | None = None


@dataclass(frozen=True)
class GridSpec:
    """Прямокутна територія з джерелом у центрі. Розміри задані в метрах."""

    width_m: float
    length_m: float
    step_m: float


@dataclass(frozen=True)
class ConcentrationField:
    """Поле приземної концентрації на координатній площині відносно джерела."""

    east_m: np.ndarray
    north_m: np.ndarray
    concentration_ug_m3: np.ndarray
    downwind_m: np.ndarray
    crosswind_m: np.ndarray
    step_m: float


@dataclass(frozen=True)
class EnvironmentalSummary:
    """Зведені екологічні показники одного розрахунку."""

    max_concentration_ug_m3: float
    mean_concentration_ug_m3: float
    max_east_m: float
    max_north_m: float
    max_downwind_m: float
    max_crosswind_m: float
    polluted_area_m2: float
    polluted_area_km2: float
    polluted_fraction: float
    exposed_population: float


@dataclass(frozen=True)
class SimulationResult:
    """Поле концентрації разом зі зведенням."""

    field: ConcentrationField
    summary: EnvironmentalSummary


def briggs_sigmas(
    downwind_m: np.ndarray | float,
    stability_class: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Повертає сільські σy і σz Бріггса для відстані за вітром у метрах.

    Коефіцієнти відповідають поширеному навчальному запису Pasquill–Gifford–Briggs
    для рівної відкритої місцевості. Клас стійкості: A, B, C, D, E або F.
    """
    stability = stability_class.upper()
    if stability not in _SIGMA_Y_FACTOR:
        raise ValueError("Клас стійкості має бути одним із A, B, C, D, E, F.")
    distance = np.asarray(downwind_m, dtype=float)
    if np.any(distance < 0):
        raise ValueError("Відстань за вітром для коефіцієнтів розсіювання не може бути від'ємною.")
    sigma_y = _SIGMA_Y_FACTOR[stability] * distance / np.sqrt(1.0 + 0.0001 * distance)
    sigma_z = _briggs_sigma_z(distance, stability)
    return sigma_y, sigma_z


def to_plume_coordinates(
    east_m: np.ndarray,
    north_m: np.ndarray,
    wind_direction_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Повертає відстань за вітром і поперечну відстань у метрах.

    Напрямок вітру — метеорологічний: звідки дме вітер, градуси від півночі за годинниковою
    стрілкою. Додатна вісь за вітром збігається з рухом повітря. Поперечна вісь додатна ліворуч
    від цього напрямку, якщо дивитися за вітром.
    """
    theta = math.radians(float(wind_direction_deg) % 360.0)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    downwind = -east_m * sin_theta - north_m * cos_theta
    crosswind = east_m * cos_theta - north_m * sin_theta
    return downwind, crosswind


def ground_level_concentration_g_m3(
    downwind_m: np.ndarray,
    crosswind_m: np.ndarray,
    *,
    emission_rate_g_s: float,
    wind_speed_m_s: float,
    effective_height_m: float,
    stability_class: str,
    decay_coefficient_per_s: float,
    sigma_y_m: float | None = None,
    sigma_z_m: float | None = None,
) -> np.ndarray:
    """Рахує внесок шлейфу в приземну концентрацію, г/м³, без фону.

    Використовується формула точкового джерела при z = 0:

    C = Q / (2 π u σy σz) · exp(-y² / (2 σy²))
        · [exp(-(z-H)² / (2 σz²)) + exp(-(z+H)² / (2 σz²))]
        · exp(-k x / u)

    Там, де повітря ще не пройшло повз джерело (x <= 0), внесок шлейфу дорівнює нулю.
    """
    if wind_speed_m_s <= 0:
        raise ValueError("Швидкість вітру має бути додатною: модель ділить на u.")

    downwind = np.asarray(downwind_m, dtype=float)
    crosswind = np.asarray(crosswind_m, dtype=float)
    concentration = np.zeros(np.broadcast_shapes(downwind.shape, crosswind.shape), dtype=float)
    positive = downwind > 0
    if not np.any(positive):
        return concentration

    distance = downwind[positive]
    cross = crosswind[positive]
    sigma_y, sigma_z = _resolve_sigmas(
        np.maximum(distance, _MIN_SIGMA_DISTANCE_M),
        stability_class,
        sigma_y_m,
        sigma_z_m,
    )
    sigma_y = np.maximum(sigma_y, _MIN_SIGMA_M)
    sigma_z = np.maximum(sigma_z, _MIN_SIGMA_M)
    height = float(effective_height_m)
    prefactor = emission_rate_g_s / (2.0 * np.pi * wind_speed_m_s * sigma_y * sigma_z)
    horizontal = np.exp(np.clip(-(cross**2) / (2.0 * sigma_y**2), -700.0, 0.0))
    vertical = np.exp(np.clip(-(height**2) / (2.0 * sigma_z**2), -700.0, 0.0)) + np.exp(
        np.clip(-(height**2) / (2.0 * sigma_z**2), -700.0, 0.0)
    )
    decay = np.exp(np.clip(-decay_coefficient_per_s * distance / wind_speed_m_s, -700.0, 0.0))
    concentration[positive] = prefactor * horizontal * vertical * decay
    return concentration


def simulate(
    source: SourceParameters,
    grid: GridSpec,
    *,
    threshold_ug_m3: float,
    population_density_per_km2: float,
) -> SimulationResult:
    """Будує поле приземної концентрації в мкг/м³ і зведення по території."""
    from src.utils.validation import validate_model_inputs

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
        population_density_per_km2=population_density_per_km2,
        exposure_duration_h=1.0,
        damage_coefficient_uah=0.0,
        filter_installation_cost_uah=0.0,
        filter_operating_cost_uah=0.0,
        emission_reduction_percent=0.0,
        sigma_y_m=source.sigma_y_m,
        sigma_z_m=source.sigma_z_m,
    )
    east = _axis(grid.width_m, grid.step_m)
    north = _axis(grid.length_m, grid.step_m)
    east_grid, north_grid = np.meshgrid(east, north, indexing="xy")
    downwind, crosswind = to_plume_coordinates(east_grid, north_grid, source.wind_direction_deg)
    plume_g_m3 = ground_level_concentration_g_m3(
        downwind,
        crosswind,
        emission_rate_g_s=source.emission_rate_g_s,
        wind_speed_m_s=source.wind_speed_m_s,
        effective_height_m=source.effective_height_m,
        stability_class=source.stability_class,
        decay_coefficient_per_s=source.decay_coefficient_per_s,
        sigma_y_m=source.sigma_y_m,
        sigma_z_m=source.sigma_z_m,
    )
    concentration = g_per_m3_to_ug_per_m3(plume_g_m3) + source.background_concentration_ug_m3
    field = ConcentrationField(
        east_m=east,
        north_m=north,
        concentration_ug_m3=concentration,
        downwind_m=downwind,
        crosswind_m=crosswind,
        step_m=grid.step_m,
    )
    summary = summarize_field(
        field,
        threshold_ug_m3=threshold_ug_m3,
        population_density_per_km2=population_density_per_km2,
    )
    return SimulationResult(field=field, summary=summary)


def summarize_field(
    field: ConcentrationField,
    *,
    threshold_ug_m3: float,
    population_density_per_km2: float,
) -> EnvironmentalSummary:
    """Обчислює максимум, середнє, площу перевищення і наближену кількість населення.

    Населення в зоні впливу для першої версії:

    exposed_population = polluted_area_km2 × population_density

    Це наближення рівномірної густоти, а не реєстр мешканців.
    Середня концентрація порахована по всій сітці, тому залежить від розміру території.
    """
    if threshold_ug_m3 <= 0:
        raise ValueError("Граничний рівень концентрації має бути додатним.")
    concentration = field.concentration_ug_m3
    flat_index = int(np.argmax(concentration))
    row, column = np.unravel_index(flat_index, concentration.shape)
    cell_area_m2 = field.step_m * field.step_m
    polluted_cells = int(np.count_nonzero(concentration > threshold_ug_m3))
    polluted_area_m2 = polluted_cells * cell_area_m2
    polluted_area_km2 = m2_to_km2(polluted_area_m2)
    cell_count = int(concentration.size)
    return EnvironmentalSummary(
        max_concentration_ug_m3=float(concentration[row, column]),
        mean_concentration_ug_m3=float(np.mean(concentration)),
        max_east_m=float(field.east_m[column]),
        max_north_m=float(field.north_m[row]),
        max_downwind_m=float(field.downwind_m[row, column]),
        max_crosswind_m=float(field.crosswind_m[row, column]),
        polluted_area_m2=float(polluted_area_m2),
        polluted_area_km2=float(polluted_area_km2),
        polluted_fraction=polluted_cells / cell_count if cell_count else 0.0,
        exposed_population=float(polluted_area_km2 * population_density_per_km2),
    )


def centerline_profile(field: ConcentrationField) -> tuple[np.ndarray, np.ndarray]:
    """Повертає відстань за вітром і концентрацію біля осі шлейфу.

    До осі потрапляють комірки, у яких поперечна відстань не перевищує половину кроку сітки.
    """
    band = np.abs(field.crosswind_m) <= (field.step_m / 2.0 + 1e-9)
    usable = band & (field.downwind_m >= 0)
    distance = field.downwind_m[usable]
    concentration = field.concentration_ug_m3[usable]
    if distance.size == 0:
        return np.array([]), np.array([])
    order = np.argsort(distance)
    return distance[order], concentration[order]


def _axis(span_m: float, step_m: float) -> np.ndarray:
    half = span_m / 2.0
    return np.arange(-half, half + 0.5 * step_m, step_m, dtype=float)


def _resolve_sigmas(
    distance_m: np.ndarray,
    stability_class: str,
    sigma_y_m: float | None,
    sigma_z_m: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    if sigma_y_m is not None and sigma_z_m is not None:
        return (
            np.full(distance_m.shape, float(sigma_y_m), dtype=float),
            np.full(distance_m.shape, float(sigma_z_m), dtype=float),
        )
    return briggs_sigmas(distance_m, stability_class)


def _briggs_sigma_z(distance: np.ndarray, stability: str) -> np.ndarray:
    if stability == "A":
        return 0.20 * distance
    if stability == "B":
        return 0.12 * distance
    if stability == "C":
        return 0.08 * distance / np.sqrt(1.0 + 0.0002 * distance)
    if stability == "D":
        return 0.06 * distance / np.sqrt(1.0 + 0.0015 * distance)
    if stability == "E":
        return 0.03 * distance / (1.0 + 0.0003 * distance)
    return 0.016 * distance / (1.0 + 0.0003 * distance)
