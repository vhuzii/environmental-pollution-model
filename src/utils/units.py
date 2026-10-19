"""Перетворення одиниць, якими користується навчальна модель."""

from __future__ import annotations

import numpy as np

GRAMS_TO_MICROGRAMS = 1_000_000.0
M2_PER_KM2 = 1_000_000.0


def g_per_m3_to_ug_per_m3(value: float | np.ndarray) -> float | np.ndarray:
    """Перетворює концентрацію з г/м³ на мкг/м³.

    1 г = 1 000 000 мкг, тому 1 г/м³ = 1 000 000 мкг/м³.
    Гаусова формула з Q у г/с, u у м/с і σ у метрах дає саме г/м³.
    Скаляр повертається як float, масив зберігає форму сітки.
    """
    converted = np.asarray(value, dtype=float) * GRAMS_TO_MICROGRAMS
    if converted.ndim == 0:
        return float(converted)
    return converted


def ug_per_m3_to_g_per_m3(value: float | np.ndarray) -> float | np.ndarray:
    """Повертає концентрацію з мкг/м³ у г/м³."""
    converted = np.asarray(value, dtype=float) / GRAMS_TO_MICROGRAMS
    if converted.ndim == 0:
        return float(converted)
    return converted


def m2_to_km2(value: float) -> float:
    """Перетворює площу з м² на км²."""
    return float(value) / M2_PER_KM2
