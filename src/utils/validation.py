"""Перевірка вхідних значень перед розрахунком."""

from __future__ import annotations

import math
from typing import Any

MAX_GRID_CELLS = 250_000
STABILITY_CLASSES = frozenset({"A", "B", "C", "D", "E", "F"})


class ModelInputError(ValueError):
    """Неприпустиме значення параметра навчальної моделі."""


def _finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelInputError(f"{name} має бути числом.")
    number = float(value)
    if not math.isfinite(number):
        raise ModelInputError(f"{name} має бути скінченним числом.")
    return number


def validate_model_inputs(
    *,
    pollutant: str,
    emission_rate_g_s: float,
    effective_height_m: float,
    wind_speed_m_s: float,
    wind_direction_deg: float,
    stability_class: str,
    decay_coefficient_per_s: float,
    background_concentration_ug_m3: float,
    threshold_ug_m3: float,
    domain_width_m: float,
    domain_length_m: float,
    grid_step_m: float,
    population_density_per_km2: float,
    exposure_duration_h: float,
    damage_coefficient_uah: float,
    filter_installation_cost_uah: float,
    filter_operating_cost_uah: float,
    emission_reduction_percent: float,
    sigma_y_m: float | None = None,
    sigma_z_m: float | None = None,
) -> None:
    """Перевіряє параметри джерела, сітки та економічного розрахунку.

    Нульова швидкість вітру заборонена, бо гаусова формула ділить на u.
    """
    if not isinstance(pollutant, str) or not pollutant.strip():
        raise ModelInputError("Укажіть назву забруднювальної речовини.")

    emission = _finite_number("Інтенсивність викиду Q, г/с", emission_rate_g_s)
    height = _finite_number("Ефективна висота H, м", effective_height_m)
    wind_speed = _finite_number("Швидкість вітру u, м/с", wind_speed_m_s)
    _finite_number("Напрямок вітру, градуси", wind_direction_deg)
    decay = _finite_number("Коефіцієнт розпаду k, 1/с", decay_coefficient_per_s)
    background = _finite_number("Фонова концентрація, мкг/м³", background_concentration_ug_m3)
    threshold = _finite_number("Граничний рівень, мкг/м³", threshold_ug_m3)
    width = _finite_number("Ширина території, м", domain_width_m)
    length = _finite_number("Довжина території, м", domain_length_m)
    step = _finite_number("Крок сітки, м", grid_step_m)
    density = _finite_number("Густота населення, осіб/км²", population_density_per_km2)
    duration = _finite_number("Тривалість впливу, год", exposure_duration_h)
    damage = _finite_number("Коефіцієнт збитку, грн", damage_coefficient_uah)
    installation = _finite_number("Вартість встановлення, грн", filter_installation_cost_uah)
    operating = _finite_number("Експлуатаційні витрати, грн", filter_operating_cost_uah)
    reduction = _finite_number("Зменшення викидів, %", emission_reduction_percent)

    if emission < 0:
        raise ModelInputError("Інтенсивність викиду Q не може бути від'ємною.")
    if height < 0:
        raise ModelInputError("Ефективна висота H не може бути від'ємною.")
    if wind_speed <= 0:
        raise ModelInputError(
            "Швидкість вітру має бути додатною. При u = 0 гаусова формула ділить на нуль і не описує штиль."
        )
    if not isinstance(stability_class, str) or stability_class.upper() not in STABILITY_CLASSES:
        raise ModelInputError("Клас стійкості атмосфери має бути одним із A, B, C, D, E, F.")
    if decay < 0:
        raise ModelInputError("Коефіцієнт природного розпаду k не може бути від'ємним.")
    if background < 0:
        raise ModelInputError("Фонова концентрація не може бути від'ємною.")
    if threshold <= 0:
        raise ModelInputError("Граничний рівень має бути додатним: відносне перевищення ділить на цей рівень.")
    if width <= 0 or length <= 0:
        raise ModelInputError("Ширина і довжина території мають бути додатними.")
    if step <= 0:
        raise ModelInputError("Крок сітки має бути додатним.")
    if step > min(width, length):
        raise ModelInputError("Крок сітки не може перевищувати менший бік території.")

    east_count = int(width / step) + 1
    north_count = int(length / step) + 1
    if east_count * north_count > MAX_GRID_CELLS:
        raise ModelInputError(
            "Сітка надто густа для першої версії. Збільште крок або зменште територію "
            f"(зараз понад {MAX_GRID_CELLS} комірок)."
        )
    if density < 0:
        raise ModelInputError("Густота населення не може бути від'ємною.")
    if duration <= 0:
        raise ModelInputError("Тривалість впливу має бути додатною.")
    if damage < 0 or installation < 0 or operating < 0:
        raise ModelInputError("Грошові коефіцієнти не можуть бути від'ємними.")
    if reduction < 0 or reduction > 100:
        raise ModelInputError("Відсоток зменшення викидів має бути в межах від 0 до 100.")

    sigma_provided = sigma_y_m is not None or sigma_z_m is not None
    if sigma_provided and (sigma_y_m is None or sigma_z_m is None):
        raise ModelInputError("Сталі σy і σz потрібно задавати разом.")
    if sigma_y_m is not None and sigma_z_m is not None:
        sigma_y = _finite_number("σy, м", sigma_y_m)
        sigma_z = _finite_number("σz, м", sigma_z_m)
        if sigma_y <= 0 or sigma_z <= 0:
            raise ModelInputError("Сталі σy і σz мають бути додатними.")


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """Перевіряє широту і довготу у градусах WGS84."""
    lat = _finite_number("Широта", latitude)
    lon = _finite_number("Довгота", longitude)
    if lat < -90 or lat > 90:
        raise ModelInputError("Широта має бути в межах від -90 до 90.")
    if lon < -180 or lon > 180:
        raise ModelInputError("Довгота має бути в межах від -180 до 180.")
    return lat, lon
