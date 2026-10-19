"""Необов'язковий клієнт OpenAQ API v3.

Перша версія вміє знайти станції біля точки і прочитати вимірювання сенсора.
Ці дані не підставляються в гаусову модель автоматично.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import requests

from src.utils.validation import validate_coordinates

_MAX_RADIUS_M = 25_000


class OpenAQError(Exception):
    """Помилка конфігурації, мережі або структури відповіді OpenAQ."""


@dataclass(frozen=True)
class OpenAQSensor:
    """Сенсор станції моніторингу."""

    sensor_id: int
    parameter: str
    units: str


@dataclass(frozen=True)
class OpenAQLocation:
    """Станція, знайдена за координатами. Відстань заповнюється лише якщо її повернув API."""

    location_id: int
    name: str
    latitude: float
    longitude: float
    sensors: tuple[OpenAQSensor, ...]
    locality: str | None = None
    distance_m: float | None = None


@dataclass(frozen=True)
class OpenAQMeasurement:
    """Одне вимірювання, прочитане з відповіді API без додаткових підставлень."""

    value: float
    parameter: str
    units: str
    datetime_utc: str | None


class OpenAQClient:
    """Шукає локації і вимірювання OpenAQ. Без API-ключа запит не виконується."""

    def __init__(self, api_key: str, base_url: str, timeout_seconds: float) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def find_locations(
        self,
        latitude: float,
        longitude: float,
        radius_m: int = 10_000,
        limit: int = 20,
    ) -> list[OpenAQLocation]:
        """Повертає станції в радіусі пошуку. Порожній список означає, що станцій поруч немає."""
        self._require_api_key()
        lat, lon = validate_coordinates(latitude, longitude)
        if radius_m <= 0 or radius_m > _MAX_RADIUS_M:
            raise OpenAQError("Радіус пошуку OpenAQ має бути від 1 до 25000 метрів.")
        if limit <= 0 or limit > 1000:
            raise OpenAQError("Кількість станцій у запиті має бути від 1 до 1000.")

        payload = self._get(
            "/locations",
            params={
                "coordinates": f"{lat},{lon}",
                "radius": radius_m,
                "limit": limit,
            },
        )
        return parse_locations(payload)

    def get_sensor_measurements(
        self,
        sensor_id: int,
        *,
        datetime_from: date | datetime | str | None = None,
        datetime_to: date | datetime | str | None = None,
        limit: int = 100,
    ) -> list[OpenAQMeasurement]:
        """Повертає вимірювання вибраного сенсора. Порожній список означає відсутність даних."""
        self._require_api_key()
        if isinstance(sensor_id, bool) or not isinstance(sensor_id, int) or sensor_id <= 0:
            raise OpenAQError("Ідентифікатор сенсора має бути додатним цілим числом.")
        if limit <= 0 or limit > 1000:
            raise OpenAQError("Кількість вимірювань у запиті має бути від 1 до 1000.")

        params: dict[str, object] = {"limit": limit}
        if datetime_from is not None:
            params["datetime_from"] = _to_iso(datetime_from)
        if datetime_to is not None:
            params["datetime_to"] = _to_iso(datetime_to)
        payload = self._get(f"/sensors/{sensor_id}/measurements", params=params)
        return parse_measurements(payload)

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise OpenAQError(
                "Ключ OpenAQ не налаштовано. Додайте OPENAQ_API_KEY у файл .env. "
                "Розрахунок гаусової моделі від цього не залежить."
            )

    def _get(self, path: str, params: dict[str, object]) -> dict:
        try:
            response = requests.get(
                f"{self.base_url}{path}",
                params=params,
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise OpenAQError("OpenAQ не відповів у межах встановленого часу.") from exc
        except requests.RequestException as exc:
            raise OpenAQError("Не вдалося звернутися до OpenAQ.") from exc

        if response.status_code in {401, 403}:
            raise OpenAQError("OpenAQ відхилив ключ API. Перевірте OPENAQ_API_KEY.")
        if response.status_code == 404:
            raise OpenAQError("OpenAQ не знайшов запитаний ресурс.")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise OpenAQError(f"OpenAQ повернув помилку HTTP {response.status_code}.") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenAQError("Відповідь OpenAQ не є JSON.") from exc
        if not isinstance(payload, dict):
            raise OpenAQError("Відповідь OpenAQ має неочікувану структуру.")
        return payload


def parse_locations(payload: dict) -> list[OpenAQLocation]:
    """Розбирає список локацій. Порожній `results` є коректною відповіддю «станцій немає»."""
    results = _require_results(payload)
    locations: list[OpenAQLocation] = []
    for item in results:
        if not isinstance(item, dict):
            raise OpenAQError("Елемент списку станцій OpenAQ має неочікуваний тип.")
        coordinates = item.get("coordinates")
        if not isinstance(coordinates, dict):
            raise OpenAQError("У станції OpenAQ немає координат.")
        sensors = _parse_sensors(item.get("sensors", []))
        distance = item.get("distance")
        locations.append(
            OpenAQLocation(
                location_id=_require_int(item.get("id"), "ідентифікатор станції"),
                name=str(item.get("name") or "Без назви"),
                latitude=_require_float(coordinates.get("latitude"), "широта станції"),
                longitude=_require_float(coordinates.get("longitude"), "довгота станції"),
                sensors=tuple(sensors),
                locality=item.get("locality") if isinstance(item.get("locality"), str) else None,
                distance_m=(
                    float(distance) if isinstance(distance, (int, float)) and not isinstance(distance, bool) else None
                ),
            )
        )
    return locations


def parse_measurements(payload: dict) -> list[OpenAQMeasurement]:
    """Розбирає вимірювання. Записи без числового value пропускаються, а не доповнюються."""
    results = _require_results(payload)
    measurements: list[OpenAQMeasurement] = []
    for item in results:
        if not isinstance(item, dict):
            raise OpenAQError("Елемент списку вимірювань OpenAQ має неочікуваний тип.")
        raw_value = item.get("value")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            continue
        parameter = item.get("parameter") if isinstance(item.get("parameter"), dict) else {}
        measurements.append(
            OpenAQMeasurement(
                value=float(raw_value),
                parameter=str(parameter.get("name") or ""),
                units=str(parameter.get("units") or ""),
                datetime_utc=_measurement_time(item),
            )
        )
    return measurements


def _parse_sensors(raw_sensors: object) -> list[OpenAQSensor]:
    if raw_sensors is None:
        return []
    if not isinstance(raw_sensors, list):
        raise OpenAQError("Список сенсорів OpenAQ має неочікувану структуру.")
    sensors: list[OpenAQSensor] = []
    for raw in raw_sensors:
        if not isinstance(raw, dict):
            raise OpenAQError("Опис сенсора OpenAQ має неочікуваний тип.")
        parameter = raw.get("parameter") if isinstance(raw.get("parameter"), dict) else {}
        sensors.append(
            OpenAQSensor(
                sensor_id=_require_int(raw.get("id"), "ідентифікатор сенсора"),
                parameter=str(parameter.get("name") or raw.get("name") or ""),
                units=str(parameter.get("units") or ""),
            )
        )
    return sensors


def _measurement_time(item: dict) -> str | None:
    period = item.get("period")
    if isinstance(period, dict):
        start = period.get("datetimeFrom")
        if isinstance(start, dict) and isinstance(start.get("utc"), str):
            return start["utc"]
    coverage = item.get("coverage")
    if isinstance(coverage, dict):
        start = coverage.get("datetimeFrom")
        if isinstance(start, dict) and isinstance(start.get("utc"), str):
            return start["utc"]
    return None


def _require_results(payload: dict) -> list:
    if "results" not in payload:
        raise OpenAQError("У відповіді OpenAQ немає поля results.")
    results = payload["results"]
    if not isinstance(results, list):
        raise OpenAQError("Поле results у відповіді OpenAQ не є списком.")
    return results


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpenAQError(f"OpenAQ не повернув коректний {label}.")
    return value


def _require_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenAQError(f"OpenAQ не повернув коректну величину: {label}.")
    return float(value)


def _to_iso(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
