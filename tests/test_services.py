"""Перевірка розбору відповідей Open-Meteo та OpenAQ без звернення до мережі."""

import pytest
import requests

from src.services.open_meteo_client import OpenMeteoClient, WeatherServiceError, parse_wind_archive
from src.services.openaq_client import (
    OpenAQClient,
    OpenAQError,
    parse_locations,
    parse_measurements,
)


def test_wind_archive_averages_only_complete_hours() -> None:
    summary = parse_wind_archive(
        {
            "timezone": "Europe/Kyiv",
            "hourly_units": {
                "time": "iso8601",
                "wind_speed_10m": "m/s",
                "wind_direction_10m": "°",
            },
            "hourly": {
                "time": ["2024-01-01T00:00", "2024-01-01T01:00", "2024-01-01T02:00"],
                "wind_speed_10m": [2.0, None, 4.0],
                "wind_direction_10m": [0.0, 180.0, 90.0],
            },
        },
        latitude=50.0,
        longitude=30.0,
        start_date="2024-01-01",
        end_date="2024-01-01",
    )
    assert summary.hours_used == 2
    assert summary.wind_speed_m_s == pytest.approx(3.0)
    assert summary.wind_direction_deg == pytest.approx(45.0)
    assert summary.speed_unit == "m/s"


def test_wind_archive_rejects_kilometers_per_hour() -> None:
    with pytest.raises(WeatherServiceError, match="м/с"):
        parse_wind_archive(
            {
                "hourly_units": {"wind_speed_10m": "km/h", "wind_direction_10m": "°"},
                "hourly": {
                    "time": ["2024-01-01T00:00"],
                    "wind_speed_10m": [10.0],
                    "wind_direction_10m": [90.0],
                },
            },
            latitude=50.0,
            longitude=30.0,
            start_date="2024-01-01",
            end_date="2024-01-01",
        )


def test_open_meteo_timeout_does_not_invent_wind(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise requests.Timeout("timeout")

    monkeypatch.setattr("src.services.open_meteo_client.requests.get", boom)
    client = OpenMeteoClient("https://archive-api.open-meteo.com/v1/archive", timeout_seconds=1)
    with pytest.raises(WeatherServiceError):
        client.fetch_wind(50.0, 30.0, "2024-01-01", "2024-01-01")


def test_openaq_without_key_does_not_call_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Мережевий запит не має виконуватися без ключа.")

    monkeypatch.setattr("src.services.openaq_client.requests.get", boom)
    client = OpenAQClient("", "https://api.openaq.org/v3", timeout_seconds=5)
    with pytest.raises(OpenAQError, match="OPENAQ_API_KEY"):
        client.find_locations(50.0, 30.0)


def test_empty_location_list_means_no_nearby_stations() -> None:
    assert parse_locations({"results": []}) == []


def test_measurements_skip_records_without_numeric_value() -> None:
    measurements = parse_measurements(
        {
            "results": [
                {"value": None, "parameter": {"name": "pm25", "units": "µg/m³"}},
                {
                    "value": 12.5,
                    "parameter": {"name": "pm25", "units": "µg/m³"},
                    "period": {"datetimeFrom": {"utc": "2024-01-01T00:00:00Z"}},
                },
            ]
        }
    )
    assert len(measurements) == 1
    assert measurements[0].value == pytest.approx(12.5)
    assert measurements[0].datetime_utc == "2024-01-01T00:00:00Z"


def test_malformed_openaq_payload_is_rejected() -> None:
    with pytest.raises(OpenAQError, match="results"):
        parse_locations({"locations": []})
