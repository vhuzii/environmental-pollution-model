"""Графіки профілю шлейфу та порівняння сценаріїв."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_centerline_chart(
    distance_m: np.ndarray,
    concentration_ug_m3: np.ndarray,
    *,
    threshold_ug_m3: float,
    pollutant: str,
) -> go.Figure:
    """Будує концентрацію вздовж осі шлейфу і горизонтальну лінію порога."""
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=distance_m,
            y=concentration_ug_m3,
            mode="lines",
            name=f"C({pollutant})",
            hovertemplate="x: %{x:.0f} м<br>C: %{y:.2f} мкг/м³<extra></extra>",
        )
    )
    figure.add_hline(
        y=threshold_ug_m3,
        line_dash="dash",
        line_color="#1a1a1a",
        annotation_text="Граничний рівень",
    )
    figure.update_layout(
        title="Концентрація вздовж осі шлейфу",
        xaxis_title="Відстань за вітром, м",
        yaxis_title="Концентрація, мкг/м³",
        template="plotly_white",
    )
    return figure


def build_scenario_comparison(frame: pd.DataFrame) -> go.Figure:
    """Порівнює максимальну концентрацію і навчачні грошові показники сценаріїв."""
    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Максимальна концентрація", "Навчальні грошові показники"),
    )
    figure.add_trace(
        go.Bar(
            x=frame["name"],
            y=frame["max_concentration_ug_m3"],
            name="Максимум, мкг/м³",
            hovertemplate="%{x}<br>%{y:.2f} мкг/м³<extra></extra>",
        ),
        row=1,
        col=1,
    )
    for column, title in (
        ("damage_uah", "Збиток, грн"),
        ("mitigation_cost_uah", "Вартість заходу, грн"),
        ("net_effect_uah", "Чистий ефект, грн"),
    ):
        figure.add_trace(
            go.Bar(
                x=frame["name"],
                y=frame[column],
                name=title,
                hovertemplate="%{x}<br>%{y:,.0f} грн<extra></extra>",
            ),
            row=1,
            col=2,
        )
    figure.update_layout(
        barmode="group",
        template="plotly_white",
        title="Порівняння сценаріїв зменшення викидів",
        legend={"orientation": "h"},
    )
    figure.update_yaxes(title_text="мкг/м³", row=1, col=1)
    figure.update_yaxes(title_text="грн", row=1, col=2)
    return figure


def build_wind_series(times: tuple[str, ...] | list[str], speeds: tuple[float, ...] | list[float]) -> go.Figure:
    """Показує погодинну швидкість вітру, отриману з Open-Meteo."""
    figure = go.Figure(go.Scatter(x=list(times), y=list(speeds), mode="lines", name="Швидкість, м/с"))
    figure.update_layout(
        title="Погодинна швидкість вітру з Open-Meteo",
        xaxis_title="Час",
        yaxis_title="Швидкість, м/с",
        template="plotly_white",
    )
    return figure
