"""Перевірки пояснювальних підписів і схем огляду."""

from src.visualization.overview import air_flow_destination, air_flow_label, wind_direction_label


def test_wind_direction_labels() -> None:
    assert wind_direction_label(270) == "західний"
    assert air_flow_label(270) == "східний"
    assert air_flow_destination(270) == "схід"
    assert wind_direction_label(0) == "північний"
    assert air_flow_destination(0) == "південь"
