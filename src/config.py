"""Налаштування, синтетичні початкові значення та читання CSV."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_INPUT_PATH = DATA_DIR / "sample_input.csv"
SAMPLE_SCENARIOS_PATH = DATA_DIR / "sample_scenarios.csv"

DISCLAIMER = (
    "Це навчальне спрощення гаусової моделі шлейфу. Концентрації та грошові суми "
    "не є офіційною екологічною експертизою, гігієнічним нормативом чи оцінкою збитків."
)

# Усі числові значення нижче є synthetic / illustrative. Вони не описують підприємство.
DEFAULT_INPUTS: dict[str, object] = {
    "pollutant": "SO2",
    "emission_rate_g_s": 25.0,
    "effective_height_m": 80.0,
    "wind_speed_m_s": 3.5,
    "wind_direction_deg": 270,
    "stability_class": "D",
    "decay_coefficient_per_s": 0.0,
    "background_concentration_ug_m3": 5.0,
    "threshold_ug_m3": 50.0,
    "domain_width_m": 8000.0,
    "domain_length_m": 10000.0,
    "grid_step_m": 100.0,
    "population_density_per_km2": 400.0,
    "exposure_duration_h": 24.0,
    "damage_coefficient_uah": 15.0,
    "filter_installation_cost_uah": 750_000.0,
    "filter_operating_cost_uah": 120_000.0,
    "emission_reduction_percent": 0,
    "use_constant_sigma": False,
    "sigma_y_m": 80.0,
    "sigma_z_m": 40.0,
}

STABILITY_LABELS: dict[str, str] = {
    "A": "A — дуже нестійка",
    "B": "B — нестійка",
    "C": "C — слабко нестійка",
    "D": "D — нейтральна",
    "E": "E — слабко стійка",
    "F": "F — стійка",
}


@dataclass(frozen=True)
class Settings:
    """Параметри зовнішніх сервісів. Порожній ключ OpenAQ є допустимим."""

    openaq_api_key: str
    openaq_base_url: str
    open_meteo_base_url: str
    request_timeout_seconds: float


def load_settings() -> Settings:
    """Читає `.env`, якщо файл існує, і повертає налаштування з типовими URL."""
    load_dotenv(PROJECT_ROOT / ".env")
    timeout_raw = os.getenv("REQUEST_TIMEOUT_SECONDS", "15")
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = 15.0
    if timeout <= 0:
        timeout = 15.0
    return Settings(
        openaq_api_key=os.getenv("OPENAQ_API_KEY", "").strip(),
        openaq_base_url=os.getenv("OPENAQ_BASE_URL", "https://api.openaq.org/v3").strip(),
        open_meteo_base_url=os.getenv(
            "OPEN_METEO_BASE_URL",
            "https://archive-api.open-meteo.com/v1/archive",
        ).strip(),
        request_timeout_seconds=timeout,
    )


def load_scenario_percents(path: Path = SAMPLE_SCENARIOS_PATH) -> tuple[float, ...]:
    """Читає відсотки скорочення зі CSV. Базовий сценарій 0% додається завжди."""
    fallback = (0.0, 30.0, 60.0, 90.0)
    if not path.is_file():
        return fallback
    frame = pd.read_csv(path)
    if "emission_reduction_percent" not in frame.columns:
        return fallback
    percents = [0.0]
    for raw in frame["emission_reduction_percent"]:
        value = float(raw)
        if all(abs(value - existing) > 1e-6 for existing in percents):
            percents.append(value)
    return tuple(percents)


def parse_input_row(frame: pd.DataFrame) -> dict[str, object]:
    """Повертає перший рядок CSV як словник відомих параметрів."""
    if frame.empty:
        raise ValueError("CSV не містить жодного рядка з параметрами.")
    row = frame.iloc[0]
    parsed: dict[str, object] = {}
    for key, default in DEFAULT_INPUTS.items():
        if key not in frame.columns or pd.isna(row[key]):
            continue
        raw = row[key]
        if isinstance(default, bool):
            parsed[key] = str(raw).strip().lower() in {"1", "true", "yes", "так"}
        elif isinstance(default, str):
            parsed[key] = str(raw).strip()
        else:
            parsed[key] = float(raw)
    if not parsed:
        raise ValueError("У CSV немає жодної відомої колонки параметрів.")
    return parsed
