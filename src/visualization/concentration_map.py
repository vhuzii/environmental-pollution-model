"""Теплова карта приземної концентрації на координатній площині."""

from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go


def build_concentration_map(
    east_m: np.ndarray,
    north_m: np.ndarray,
    concentration_ug_m3: np.ndarray,
    *,
    threshold_ug_m3: float,
    wind_direction_deg: float,
    pollutant: str,
) -> go.Figure:
    """Будує теплову карту, контур порога, джерело і стрілку напрямку руху повітря.

    Осі — метри на схід і на північ від джерела. Географічна підкладка в першій версії не використовується.
    """
    figure = go.Figure()
    figure.add_trace(
        go.Heatmap(
            x=east_m,
            y=north_m,
            z=concentration_ug_m3,
            colorbar={"title": "C, мкг/м³"},
            colorscale="YlOrRd",
            hovertemplate="Схід: %{x:.0f} м<br>Північ: %{y:.0f} м<br>C: %{z:.2f} мкг/м³<extra></extra>",
            name="Концентрація",
        )
    )
    figure.add_trace(
        go.Contour(
            x=east_m,
            y=north_m,
            z=concentration_ug_m3,
            contours={
                "start": threshold_ug_m3,
                "end": threshold_ug_m3,
                "size": 1,
                "coloring": "none",
            },
            line={"color": "#1a1a1a", "width": 2},
            showscale=False,
            hoverinfo="skip",
            name=f"Поріг {threshold_ug_m3:g} мкг/м³",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers",
            marker={"size": 12, "color": "#0b3d91", "symbol": "star"},
            name="Джерело",
            hovertemplate="Джерело<extra></extra>",
        )
    )
    _add_wind_arrow(figure, east_m, north_m, wind_direction_deg)
    figure.update_layout(
        title=f"Приземна концентрація {pollutant}, мкг/м³",
        xaxis_title="Схід, м",
        yaxis_title="Північ, м",
        yaxis={"scaleanchor": "x", "scaleratio": 1},
        legend={"orientation": "h"},
        template="plotly_white",
    )
    return figure


def _add_wind_arrow(
    figure: go.Figure,
    east_m: np.ndarray,
    north_m: np.ndarray,
    wind_direction_deg: float,
) -> None:
    theta = math.radians(float(wind_direction_deg) % 360.0)
    span = max(float(east_m[-1] - east_m[0]), float(north_m[-1] - north_m[0]), 1.0)
    length = 0.12 * span
    head_east = -math.sin(theta) * length
    head_north = -math.cos(theta) * length
    figure.add_annotation(
        x=head_east,
        y=head_north,
        ax=0,
        ay=0,
        xref="x",
        yref="y",
        axref="x",
        ayref="y",
        showarrow=True,
        arrowhead=3,
        arrowwidth=2,
        arrowcolor="#0b3d91",
    )
    figure.add_trace(
        go.Scatter(
            x=[head_east],
            y=[head_north],
            mode="text",
            text=["Рух повітря"],
            textposition="top center",
            showlegend=False,
            hoverinfo="skip",
        )
    )
