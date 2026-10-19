"""Інтерфейс навчальної моделі поширення атмосферного забруднення."""

from __future__ import annotations

import streamlit as st

from src.config import DEFAULT_INPUTS, STABILITY_LABELS, load_scenario_percents
from src.models.economic_model import EconomicParameters
from src.models.gaussian_plume import GridSpec, SourceParameters, briggs_sigmas, centerline_profile
from src.models.scenario import AnalysisResult, analyze
from src.utils.validation import ModelInputError
from src.visualization.charts import build_centerline_chart
from src.visualization.concentration_map import build_concentration_map
from src.visualization.overview import (
    air_flow_destination,
    build_area_share_chart,
    build_status_gauge,
    wind_direction_label,
)

_BRIGGS_SIGMA_Y_A = {
    "A": 0.22,
    "B": 0.16,
    "C": 0.11,
    "D": 0.08,
    "E": 0.06,
    "F": 0.04,
}
_BRIGGS_SIGMA_Z_LATEX = {
    "A": r"0.20\,x",
    "B": r"0.12\,x",
    "C": r"0.08\,x/\sqrt{1+0.0002\,x}",
    "D": r"0.06\,x/\sqrt{1+0.0015\,x}",
    "E": r"0.03\,x/(1+0.0003\,x)",
    "F": r"0.016\,x/(1+0.0003\,x)",
}
_BRIGGS_SIGMA_Z_TEXT = {
    "A": "0.20 x",
    "B": "0.12 x",
    "C": "0.08 x / sqrt(1 + 0.0002 x)",
    "D": "0.06 x / sqrt(1 + 0.0015 x)",
    "E": "0.03 x / (1 + 0.0003 x)",
    "F": "0.016 x / (1 + 0.0003 x)",
}

st.set_page_config(
    page_title="Поширення атмосферного забруднення",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    """Збирає бічну панель і односторінковий результат."""
    _ensure_state()
    st.title("Моделювання поширення атмосферного забруднення")
    _render_sidebar()
    try:
        analysis = _run_analysis()
    except ModelInputError as error:
        st.error(str(error))
        st.stop()
    _render_results(analysis)


def _ensure_state() -> None:
    for key, value in DEFAULT_INPUTS.items():
        st.session_state.setdefault(key, value)


def _render_sidebar() -> None:
    st.sidebar.header("Вхідні параметри")
    st.sidebar.text_input("Забруднювальна речовина", key="pollutant")
    st.sidebar.number_input("Інтенсивність викиду Q, г/с", min_value=0.0, key="emission_rate_g_s")
    st.sidebar.number_input("Ефективна висота джерела H, м", min_value=0.0, key="effective_height_m")
    st.sidebar.number_input("Швидкість вітру u, м/с", min_value=0.1, key="wind_speed_m_s")
    st.sidebar.slider("Напрямок вітру, градуси", min_value=0, max_value=360, key="wind_direction_deg")
    st.sidebar.selectbox(
        "Клас стійкості атмосфери",
        options=list(STABILITY_LABELS),
        format_func=lambda code: STABILITY_LABELS[code],
        key="stability_class",
    )
    _render_briggs_sidebar()
    st.sidebar.number_input("Фонова концентрація, мкг/м³", min_value=0.0, key="background_concentration_ug_m3")
    st.sidebar.number_input("Граничний рівень, мкг/м³", min_value=0.01, key="threshold_ug_m3")
    st.sidebar.number_input("Ширина території (схід–захід), м", min_value=1.0, key="domain_width_m")
    st.sidebar.number_input("Довжина території (північ–південь), м", min_value=1.0, key="domain_length_m")
    st.sidebar.number_input("Крок сітки, м", min_value=1.0, key="grid_step_m")
    st.sidebar.number_input("Густота населення, осіб/км²", min_value=0.0, key="population_density_per_km2")
    st.sidebar.number_input("Тривалість впливу, год", min_value=0.1, key="exposure_duration_h")
    st.sidebar.number_input(
        "Коефіцієнт збитку, грн/(особа·год·відносне перевищення)",
        min_value=0.0,
        key="damage_coefficient_uah",
    )


def _render_briggs_sidebar() -> None:
    """Показує формули Бріггса σy, σz для обраного класу і таблицю всіх класів."""
    stability = str(st.session_state["stability_class"]).upper()
    a_factor = _BRIGGS_SIGMA_Y_A[stability]
    sigma_y_m, sigma_z_m = briggs_sigmas(1000.0, stability)
    st.sidebar.markdown("**σy, σz за Бріггсом (сільські)**")
    st.sidebar.latex(
        rf"\sigma_y=\dfrac{{{a_factor}\,x}}{{\sqrt{{1+0.0001\,x}}}}"
        rf"\quad(\mathrm{{клас\ {stability}}})"
    )
    st.sidebar.latex(rf"\sigma_z={_BRIGGS_SIGMA_Z_LATEX[stability]}")
    st.sidebar.caption(f"Приклад при x = 1000 м: σy = {float(sigma_y_m):.1f} м, σz = {float(sigma_z_m):.1f} м")
    rows = "\n".join(
        f"| {code} | {_BRIGGS_SIGMA_Y_A[code]} | {_BRIGGS_SIGMA_Z_TEXT[code]} |" for code in _BRIGGS_SIGMA_Y_A
    )
    with st.sidebar.expander("Усі класи A–F"):
        st.markdown(
            f"""
σy для всіх: `a·x / sqrt(1 + 0.0001·x)`

| Клас | a (для σy) | σz |
| --- | ---: | --- |
{rows}
            """
        )


def _run_analysis() -> AnalysisResult:
    source = SourceParameters(
        pollutant=str(st.session_state["pollutant"]),
        emission_rate_g_s=float(st.session_state["emission_rate_g_s"]),
        effective_height_m=float(st.session_state["effective_height_m"]),
        wind_speed_m_s=float(st.session_state["wind_speed_m_s"]),
        wind_direction_deg=float(st.session_state["wind_direction_deg"]),
        stability_class=str(st.session_state["stability_class"]),
        decay_coefficient_per_s=float(DEFAULT_INPUTS["decay_coefficient_per_s"]),
        background_concentration_ug_m3=float(st.session_state["background_concentration_ug_m3"]),
    )
    grid = GridSpec(
        width_m=float(st.session_state["domain_width_m"]),
        length_m=float(st.session_state["domain_length_m"]),
        step_m=float(st.session_state["grid_step_m"]),
    )
    economics = EconomicParameters(
        damage_coefficient_uah_per_person_hour=float(st.session_state["damage_coefficient_uah"]),
        exposure_duration_h=float(st.session_state["exposure_duration_h"]),
        filter_installation_cost_uah=float(DEFAULT_INPUTS["filter_installation_cost_uah"]),
        filter_operating_cost_uah=float(DEFAULT_INPUTS["filter_operating_cost_uah"]),
        population_density_per_km2=float(st.session_state["population_density_per_km2"]),
    )
    return analyze(
        source,
        grid,
        threshold_ug_m3=float(st.session_state["threshold_ug_m3"]),
        economics=economics,
        reduction_percents=load_scenario_percents(),
        selected_reduction_percent=0.0,
    )


def _render_results(analysis: AnalysisResult) -> None:
    pollutant = str(st.session_state["pollutant"])
    threshold = float(st.session_state["threshold_ug_m3"])
    wind_deg = float(st.session_state["wind_direction_deg"])
    selected = analysis.selected
    summary = analysis.summary
    field = analysis.field
    destination = air_flow_destination(wind_deg)

    st.subheader("Гаусова модель")
    st.markdown("Приземна концентрація постійного точкового джерела:")
    st.latex(
        r"C(x,y,0)=\dfrac{Q}{2\pi u\,\sigma_{y}\sigma_{z}}"
        r"\exp\!\left(-\dfrac{y^{2}}{2\sigma_{y}^{2}}\right)"
        r"\cdot 2\exp\!\left(-\dfrac{H^{2}}{2\sigma_{z}^{2}}\right)"
    )
    st.markdown(
        f"де $Q$ — інтенсивність викиду (г/с), $u$ — швидкість вітру (м/с), "
        f"$H$ — ефективна висота (м), $\\sigma_{{y}}$, $\\sigma_{{z}}$ — коефіцієнти розсіювання (м). "
        f"Шлейф зносить на **{destination}**."
    )

    st.subheader("Формули показників")
    st.markdown(
        "**Речовина** — вхідний параметр (назва забруднювача). "
        f"**Вітер** — метеорологічний напрямок {wind_deg:g}° "
        f"(підпис: **{wind_direction_label(wind_deg)}**)."
    )
    st.markdown("Максимальна та середня концентрація по розрахунковій сітці:")
    st.latex(r"C_{\max}=\max_{i,j}\,C_{ij}")
    st.latex(r"C_{\mathrm{mean}}=\dfrac{1}{N}\sum_{i,j} C_{ij}")
    st.markdown(
        "Площа перевищення — сума площ комірок, де $C_{ij} > C_{\\lim}$ "
        r"($\Delta x$ — крок сітки):"
    )
    st.latex(r"S=N_{>}\,(\Delta x)^{2}")
    st.markdown("Частка території та наближене населення в зоні впливу:")
    st.latex(r"f=\dfrac{S}{S_{\mathrm{domain}}}")
    st.latex(r"N_{\mathrm{exp}}=S\cdot\rho")
    st.markdown(
        "Навчальний збиток — сума по комірках із перевищенням "
        r"($k_d$ — коефіцієнт збитку, $T$ — тривалість впливу, $\rho$ — густота населення):"
    )
    st.latex(
        r"D_i=k_d\cdot(\rho A_i)\cdot T\cdot\dfrac{C_i-C_{\lim}}{C_{\lim}},"
        r"\quad D=\sum_i D_i"
    )
    st.markdown(
        r"**Що таке $D_i$ і $D$:** "
        r"$D_i$ — навчальний збиток **однієї комірки** сітки (грн), де концентрація вища за поріг; "
        r"$(\rho A_i)$ — наближена кількість людей у цій комірці; "
        r"$\dfrac{C_i-C_{\lim}}{C_{\lim}}$ — наскільки сильно перевищено поріг (відносно). "
        r"$D=\sum_i D_i$ — **загальний** навчальний збиток по зоні перевищення "
        r"(метрика «Навчальний збиток»)."
    )

    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            build_status_gauge(
                max_concentration_ug_m3=selected.max_concentration_ug_m3,
                threshold_ug_m3=threshold,
                pollutant=pollutant,
            ),
            use_container_width=True,
        )
    with right:
        st.plotly_chart(
            build_area_share_chart(selected.polluted_fraction),
            use_container_width=True,
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Речовина", pollutant)
    c2.metric("Вітер", wind_direction_label(wind_deg))
    c3.metric("Навчальний збиток", f"{selected.damage_uah:,.0f} грн")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Максимальна концентрація", f"{summary.max_concentration_ug_m3:.2f} мкг/м³")
    m2.metric("Середня концентрація", f"{summary.mean_concentration_ug_m3:.2f} мкг/м³")
    m3.metric("Площа перевищення", f"{summary.polluted_area_km2:.4f} км²")
    m4.metric("Частка території", f"{summary.polluted_fraction:.1%}")
    st.metric("Населення в зоні впливу, наближено", f"{summary.exposed_population:.1f} осіб")

    st.plotly_chart(
        build_concentration_map(
            field.east_m,
            field.north_m,
            field.concentration_ug_m3,
            threshold_ug_m3=threshold,
            wind_direction_deg=wind_deg,
            pollutant=pollutant,
        ),
        use_container_width=True,
    )

    distance, concentration = centerline_profile(field)
    st.plotly_chart(
        build_centerline_chart(
            distance,
            concentration,
            threshold_ug_m3=threshold,
            pollutant=pollutant,
        ),
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
