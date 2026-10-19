"""Клієнт Open-Meteo Historical Weather API для швидкості та напрямку вітру.

Клієнт повертає лише значення, які є у відповіді API. Якщо даних немає або
структура відповіді несподівана, він повідомляє про помилку і нічого не підставляє.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

import requests

from src.utils.validation import validate_coordinates

_MAX_PERIOD_DAYS = 31


class WeatherServiceError(Exception):
    """Помилка мережі, статусу або структури відповіді Open-Meteo."""


@dataclass(frozen=True)
class WindSummary:
    """Зведення вітру, пораховане лише з отриманих погодинних значень."""

    latitude: float
    longitude: float
    start_date: str
    end_date: str
    timezone: str
    wind_speed_m_s: float
    wind_direction_deg: float
    hours_used: int
    speed_unit: str
    times: tuple[str, ...]
    hourly_speed_m_s: tuple[float, ...]
    hourly_direction_deg: tuple[float, ...]
    source: str = "open-meteo-archive"


class OpenMeteoClient:
    """Отримує історичний вітер на висоті 10 м через archive API."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch_wind(
        self,
        latitude: float,
        longitude: float,
        start_date: date | str,
        end_date: date | str,
    ) -> WindSummary:
        """Запитує погодинний вітер і повертає середні швидкість і напрямок.

        Швидкість запитується в м/с (`wind_speed_unit=ms`). Напрямок є круговим
        середнім метеорологічних градусів, швидкість — арифметичним середнім
        лише тих годин, де обидва значення присутні.
        """
        lat, lon = validate_coordinates(latitude, longitude)
        start = _parse_date(start_date, "Дата початку")
        end = _parse_date(end_date, "Дата завершення")
        if end < start:
            raise WeatherServiceError("Дата завершення не може бути раніше за дату початку.")
        if (end - start).days > _MAX_PERIOD_DAYS:
            raise WeatherServiceError(f"Перша версія приймає період не довший за {_MAX_PERIOD_DAYS} добу.")

        try:
            response = requests.get(
                self.base_url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "hourly": "wind_speed_10m,wind_direction_10m",
                    "wind_speed_unit": "ms",
                    "timezone": "auto",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise WeatherServiceError(
                "Open-Meteo не відповів у межах встановленого часу. Введіть вітер вручну."
            ) from exc
        except requests.RequestException as exc:
            raise WeatherServiceError("Не вдалося звернутися до Open-Meteo. Введіть вітер вручну.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherServiceError("Відповідь Open-Meteo не є JSON.") from exc
        if not isinstance(payload, dict):
            raise WeatherServiceError("Відповідь Open-Meteo має неочікувану структуру.")
        if payload.get("error"):
            reason = payload.get("reason") or "Open-Meteo повернув помилку без пояснення."
            raise WeatherServiceError(str(reason))
        return parse_wind_archive(
            payload,
            latitude=lat,
            longitude=lon,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )


def parse_wind_archive(
    payload: dict,
    *,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> WindSummary:
    """Перевіряє тіло відповіді archive API і зводить наявні години."""
    units = payload.get("hourly_units")
    hourly = payload.get("hourly")
    if not isinstance(units, dict) or not isinstance(hourly, dict):
        raise WeatherServiceError("У відповіді Open-Meteo немає блоків hourly та hourly_units.")

    speed_unit = units.get("wind_speed_10m")
    if speed_unit != "m/s":
        raise WeatherServiceError("Open-Meteo повернув швидкість вітру не в м/с. Значення не використано.")
    direction_unit = units.get("wind_direction_10m")
    if direction_unit not in {"°", "degrees"}:
        raise WeatherServiceError(
            "Open-Meteo повернув напрямок вітру в неочікуваних одиницях. Значення не використано."
        )

    times = hourly.get("time")
    speeds = hourly.get("wind_speed_10m")
    directions = hourly.get("wind_direction_10m")
    if not isinstance(times, list) or not isinstance(speeds, list) or not isinstance(directions, list):
        raise WeatherServiceError("Погодинні ряди вітру у відповіді Open-Meteo відсутні або пошкоджені.")
    if not len(times) == len(speeds) == len(directions):
        raise WeatherServiceError("Погодинні ряди Open-Meteo мають різну довжину.")

    kept_times: list[str] = []
    kept_speeds: list[float] = []
    kept_directions: list[float] = []
    for moment, speed, direction in zip(times, speeds, directions, strict=True):
        if speed is None or direction is None:
            continue
        if isinstance(speed, bool) or isinstance(direction, bool):
            continue
        if not isinstance(speed, (int, float)) or not isinstance(direction, (int, float)):
            raise WeatherServiceError("Серед значень вітру є нечислові дані.")
        if not math.isfinite(float(speed)) or not math.isfinite(float(direction)):
            continue
        kept_times.append(str(moment))
        kept_speeds.append(float(speed))
        kept_directions.append(float(direction))

    if not kept_speeds:
        raise WeatherServiceError("Open-Meteo не повернув жодної пари швидкість–напрямок за вибраний період.")

    timezone = payload.get("timezone")
    return WindSummary(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
        timezone=str(timezone) if isinstance(timezone, str) else "невідомий",
        wind_speed_m_s=sum(kept_speeds) / len(kept_speeds),
        wind_direction_deg=_circular_mean_degrees(kept_directions),
        hours_used=len(kept_speeds),
        speed_unit="m/s",
        times=tuple(kept_times),
        hourly_speed_m_s=tuple(kept_speeds),
        hourly_direction_deg=tuple(kept_directions),
    )


def _circular_mean_degrees(directions: list[float]) -> float:
    east = [math.sin(math.radians(value)) for value in directions]
    north = [math.cos(math.radians(value)) for value in directions]
    mean_east = sum(east) / len(east)
    mean_north = sum(north) / len(north)
    if math.hypot(mean_east, mean_north) < 1e-8:
        raise WeatherServiceError("Напрямок вітру за період невизначений: вектори взаємно компенсуються.")
    return math.degrees(math.atan2(mean_east, mean_north)) % 360.0


def _parse_date(value: date | str, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise WeatherServiceError(f"{label} має бути у форматі РРРР-ММ-ДД.") from exc
