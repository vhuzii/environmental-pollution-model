"""Зрозумілі для людини схеми та пояснення результатів."""

from __future__ import annotations

import math

import plotly.graph_objects as go

from src.models.scenario import AnalysisResult, ScenarioResult

_WIND_SECTORS: tuple[tuple[float, str, str], ...] = (
    (0.0, "північний", "північ"),
    (45.0, "північно-східний", "північний схід"),
    (90.0, "східний", "схід"),
    (135.0, "південно-східний", "південний схід"),
    (180.0, "південний", "південь"),
    (225.0, "південно-західний", "південний захід"),
    (270.0, "західний", "захід"),
    (315.0, "північно-західний", "північний захід"),
)


def _nearest_wind_sector(angle_deg: float) -> tuple[str, str]:
    angle = float(angle_deg) % 360.0
    best = min(_WIND_SECTORS, key=lambda item: abs(((angle - item[0] + 180) % 360) - 180))
    return best[1], best[2]


def wind_direction_label(wind_direction_deg: float) -> str:
    """Повертає короткий підпис метеорологічного напрямку вітру українською."""
    return _nearest_wind_sector(wind_direction_deg)[0]


def air_flow_label(wind_direction_deg: float) -> str:
    """Прикметник напрямку руху повітря (протилежно до «звідки дме»)."""
    flow = (float(wind_direction_deg) + 180.0) % 360.0
    return _nearest_wind_sector(flow)[0]


def air_flow_destination(wind_direction_deg: float) -> str:
    """Куди зносить шлейф: «схід», «південь» тощо."""
    flow = (float(wind_direction_deg) + 180.0) % 360.0
    return _nearest_wind_sector(flow)[1]


def build_process_scheme(
    *,
    pollutant: str,
    wind_direction_deg: float,
    threshold_ug_m3: float,
    selected: ScenarioResult,
) -> go.Figure:
    """Будує просту схему: джерело → вітер → шлейф → зона перевищення → економіка."""
    wind_from = wind_direction_label(wind_direction_deg)
    destination = air_flow_destination(wind_direction_deg)
    nodes = [
        (0.08, 0.55, "1. Джерело", f"{pollutant}\nQ = {selected.emission_rate_g_s:.1f} г/с"),
        (0.32, 0.55, "2. Вітер", f"дме з {wind_from}\nшлейф → {destination}"),
        (0.56, 0.55, "3. Шлейф", f"макс. {selected.max_concentration_ug_m3:.1f}\nмкг/м³"),
        (0.80, 0.78, "4. Зона > порога", f"{selected.polluted_area_km2:.2f} км²\nпорог {threshold_ug_m3:g}"),
        (0.80, 0.28, "5. Економіка", f"чистий ефект\n{selected.net_effect_uah:,.0f} грн"),
    ]
    figure = go.Figure()
    for x, y, title, detail in nodes:
        figure.add_shape(
            type="rect",
            x0=x - 0.09,
            x1=x + 0.09,
            y0=y - 0.14,
            y1=y + 0.14,
            line={"color": "#1f4e79", "width": 2},
            fillcolor="#e8f1fb",
        )
        figure.add_annotation(
            x=x,
            y=y + 0.04,
            text=f"<b>{title}</b>",
            showarrow=False,
            font={"size": 13, "color": "#12324f"},
        )
        figure.add_annotation(
            x=x,
            y=y - 0.05,
            text=detail.replace("\n", "<br>"),
            showarrow=False,
            font={"size": 11, "color": "#334155"},
        )

    arrows = [
        (0.17, 0.55, 0.23, 0.55),
        (0.41, 0.55, 0.47, 0.55),
        (0.65, 0.60, 0.71, 0.72),
        (0.65, 0.50, 0.71, 0.34),
    ]
    for x0, y0, x1, y1 in arrows:
        figure.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=3,
            arrowwidth=2,
            arrowcolor="#1f4e79",
        )

    figure.update_xaxes(visible=False, range=[0, 1])
    figure.update_yaxes(visible=False, range=[0, 1])
    figure.update_layout(
        title="Як працює розрахунок (схема для людини)",
        height=360,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        template="plotly_white",
        plot_bgcolor="white",
    )
    return figure


def build_status_gauge(
    *,
    max_concentration_ug_m3: float,
    threshold_ug_m3: float,
    pollutant: str,
) -> go.Figure:
    """Показує, наскільки максимум вищий або нижчий за поріг."""
    threshold = max(float(threshold_ug_m3), 1e-9)
    ratio = float(max_concentration_ug_m3) / threshold
    axis_max = max(2.0, math.ceil(ratio * 10) / 10 + 0.2)
    if ratio <= 1.0:
        bar_color = "#2e7d32"
        status = "нижче порога"
    elif ratio <= 1.5:
        bar_color = "#ef6c00"
        status = "помірне перевищення"
    else:
        bar_color = "#c62828"
        status = "сильне перевищення"

    figure = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=float(max_concentration_ug_m3),
            delta={"reference": threshold, "increasing": {"color": "#c62828"}, "decreasing": {"color": "#2e7d32"}},
            number={"suffix": " мкг/м³"},
            title={"text": f"Максимум {pollutant}: {status}"},
            gauge={
                "axis": {"range": [0, axis_max * threshold], "ticksuffix": ""},
                "bar": {"color": bar_color},
                "steps": [
                    {"range": [0, threshold], "color": "#e8f5e9"},
                    {"range": [threshold, 1.5 * threshold], "color": "#fff3e0"},
                    {"range": [1.5 * threshold, axis_max * threshold], "color": "#ffebee"},
                ],
                "threshold": {
                    "line": {"color": "#1a1a1a", "width": 3},
                    "thickness": 0.8,
                    "value": threshold,
                },
            },
        )
    )
    figure.update_layout(height=300, margin={"l": 30, "r": 30, "t": 60, "b": 20})
    return figure


def build_area_share_chart(polluted_fraction: float) -> go.Figure:
    """Кругова діаграма частки території з перевищенням порога."""
    polluted = max(0.0, min(1.0, float(polluted_fraction)))
    clean = 1.0 - polluted
    figure = go.Figure(
        data=[
            go.Pie(
                labels=["Нижче порога", "Вище порога"],
                values=[clean, polluted],
                hole=0.55,
                marker={"colors": ["#c8e6c9", "#ef9a9a"]},
                hovertemplate="%{label}<br>%{percent}<extra></extra>",
                textinfo="label+percent",
            )
        ]
    )
    figure.update_layout(
        title="Частка території з перевищенням",
        height=300,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        showlegend=False,
    )
    return figure


def plain_language_summary(
    analysis: AnalysisResult,
    *,
    pollutant: str,
    wind_direction_deg: float,
    threshold_ug_m3: float,
    exposure_duration_h: float,
) -> str:
    """Формує коротке текстове пояснення поточного сценарію."""
    selected = analysis.selected
    summary = analysis.summary
    wind_from = wind_direction_label(wind_direction_deg)
    destination = air_flow_destination(wind_direction_deg)
    if selected.max_concentration_ug_m3 > threshold_ug_m3:
        eco_line = (
            f"Максимум **{selected.max_concentration_ug_m3:.1f} мкг/м³** перевищує поріг "
            f"**{threshold_ug_m3:g} мкг/м³** у **{selected.max_concentration_ug_m3 / threshold_ug_m3:.2f}** раза."
        )
    else:
        eco_line = (
            f"Максимум **{selected.max_concentration_ug_m3:.1f} мкг/м³** не перевищує поріг "
            f"**{threshold_ug_m3:g} мкг/м³**."
        )

    if selected.net_effect_uah > 0:
        money_line = (
            f"За навчальними коефіцієнтами чистий ефект додатний: "
            f"**{selected.net_effect_uah:,.0f} грн**."
        )
    elif abs(selected.net_effect_uah) < 1e-6 and selected.reduction_percent == 0:
        money_line = (
            "Це базовий сценарій без очищення: вартість заходу 0 грн, чистий ефект 0 грн "
            "(точка порівняння для інших сценаріїв)."
        )
    else:
        money_line = (
            f"За навчальними коефіцієнтами чистий ефект від’ємний: "
            f"**{selected.net_effect_uah:,.0f} грн** — уникнений збиток менший за вартість заходу."
        )

    best = max(analysis.scenarios, key=lambda item: item.net_effect_uah)
    eco_best = min(analysis.scenarios, key=lambda item: item.polluted_area_km2)

    return f"""
**Що відбувається зараз**

Джерело викидає **{pollutant}**. Вітер **{wind_from}** (шлейф зносить на **{destination}**).
{eco_line}

Зона перевищення займає **{selected.polluted_area_km2:.3f} км²**
({selected.polluted_fraction:.1%} території). Наближено там проживає
**{selected.exposed_population:.0f} осіб** (площа × густота).
Точка максимуму — близько **{summary.max_downwind_m:.0f} м** за вітром від джерела.
Період впливу в розрахунку збитку: **{exposure_duration_h:g} год**.

{money_line}

**Як читати порівняння сценаріїв**

- Найменша зона перевищення серед пресетів: **{eco_best.name}**
  ({eco_best.polluted_area_km2:.3f} км²).
- Найкращий навчальний чистий ефект: **{best.name}**
  ({best.net_effect_uah:,.0f} грн).
"""
