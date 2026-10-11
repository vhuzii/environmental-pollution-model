"""Інтерфейс навчальної моделі поширення атмосферного забруднення."""

from __future__ import annotations

import json
from dataclasses import asdict

import pandas as pd
import streamlit as st

from src.config import (
    DEFAULT_INPUTS,
    DISCLAIMER,
    SAMPLE_INPUT_PATH,
    STABILITY_LABELS,
    load_scenario_percents,
    load_settings,
    parse_input_row,
)
from src.models.economic_model import EconomicParameters
from src.models.gaussian_plume import GridSpec, SourceParameters, briggs_sigmas, centerline_profile
from src.models.scenario import AnalysisResult, analyze
from src.services.open_meteo_client import OpenMeteoClient, WeatherServiceError
from src.services.openaq_client import OpenAQClient, OpenAQError
from src.utils.validation import ModelInputError, validate_coordinates
from src.visualization.charts import (
    build_centerline_chart,
    build_scenario_comparison,
    build_wind_series,
)
from src.visualization.concentration_map import build_concentration_map
from src.visualization.overview import (
    air_flow_destination,
    build_area_share_chart,
    build_process_scheme,
    build_status_gauge,
    plain_language_summary,
    wind_direction_label,
)
from src.visualization.concentration_map import build_concentration_map
from src.visualization.overview import (
    air_flow_destination,
    build_area_share_chart,
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

DISPLAY_COLUMNS = {
    "name": "Сценарій",
    "reduction_percent": "Зменшення, %",
    "emission_rate_g_s": "Q, г/с",
    "max_concentration_ug_m3": "Максимум, мкг/м³",
    "mean_concentration_ug_m3": "Середнє, мкг/м³",
    "polluted_area_km2": "Площа перевищення, км²",
    "polluted_fraction": "Частка території",
    "exposed_population": "Населення, осіб",
    "damage_uah": "Навчальний збиток, грн",
    "mitigation_cost_uah": "Вартість заходу, грн",
    "avoided_damage_uah": "Уникнений збиток, грн",
    "net_effect_uah": "Чистий ефект, грн",
}


def main() -> None:
    """Збирає бічну панель, розрахунок і вкладки результатів."""
    _ensure_state()
    st.title("Моделювання поширення атмосферного забруднення")
    st.caption(DISCLAIMER)
    _render_sidebar()
    try:
        analysis = _run_analysis()
    except ModelInputError as error:
        st.error(str(error))
        st.stop()
    _render_results(analysis)
    overview, environmental, economy, visual, weather, monitoring, about = st.tabs(
        [
            "Огляд для людини",
            "Екологічний розрахунок",
            "Економіка і сценарії",
            "Карта і графіки",
            "Погода Open-Meteo",
            "OpenAQ",
            "Про модель",
        ]
    )
    with overview:
        _render_overview(analysis)
    with environmental:
        _render_environmental(analysis)
    with economy:
        _render_economy(analysis)
    with visual:
        _render_visual(analysis)
    with weather:
        _render_weather()
    with monitoring:
        _render_openaq()
    with about:
        _render_about()


def _ensure_state() -> None:
    for key, value in DEFAULT_INPUTS.items():
        st.session_state.setdefault(key, value)


def _render_sidebar() -> None:
    st.sidebar.header("Вхідні параметри")
def _render_sidebar() -> None:
    st.sidebar.header("Вхідні параметри")
    st.sidebar.caption("Початкові числа є синтетичними (synthetic / illustrative).")
    uploaded = st.sidebar.file_uploader("Імпорт параметрів із CSV", type="csv")
    if uploaded is not None:
        _apply_uploaded_csv(uploaded)

    st.sidebar.text_input(
        "Забруднювальна речовина",
        key="pollutant",
        help="Назва для підписів. Хімічна специфіка в першій версії задається лише коефіцієнтом розпаду.",
    )
    st.sidebar.number_input(
        "Інтенсивність викиду Q, г/с",
        min_value=0.0,
        key="emission_rate_g_s",
        help="Маса речовини, що викидається за секунду.",
    )
    st.sidebar.number_input(
        "Ефективна висота джерела H, м",
        min_value=0.0,
        key="effective_height_m",
        help="Висота труби разом із підйомом шлейфу. Підйом окремо не розраховується.",
    )
    st.sidebar.number_input(
        "Швидкість вітру u, м/с",
        min_value=0.1,
        key="wind_speed_m_s",
        help="Має бути додатною. Значення 0 у формулі дає ділення на нуль і не описує штиль.",
    )
    st.sidebar.slider(
        "Напрямок вітру, градуси",
        min_value=0,
        max_value=360,
        key="wind_direction_deg",
        help="Метеорологічний напрямок: звідки дме вітер. 0° — з півночі, 90° — зі сходу.",
    )
    st.sidebar.selectbox(
        "Клас стійкості атмосфери",
        options=list(STABILITY_LABELS),
        format_func=lambda code: STABILITY_LABELS[code],
        key="stability_class",
    st.sidebar.selectbox(
        "Клас стійкості атмосфери",
        options=list(STABILITY_LABELS),
        format_func=lambda code: STABILITY_LABELS[code],
        key="stability_class",
        help="Класи Паскуіла A–F. За ними обчислюються σy(x) і σz(x), якщо не задано сталі значення.",
    )
    _render_briggs_sidebar()
    st.sidebar.number_input(
        "Коефіцієнт природного розпаду k, 1/с",
        min_value=0.0,
        format="%.6f",
        key="decay_coefficient_per_s",
        help="Множник exp(-k·x/u). Нуль означає відсутність розпаду.",
    )
    st.sidebar.number_input(
        "Фонова концентрація, мкг/м³",
        min_value=0.0,
        key="background_concentration_ug_m3",
        help="Додається до внеску шлейфу. За вітром угору залишається лише фон.",
    )
    st.sidebar.number_input(
        "Граничний рівень, мкг/м³",
        min_value=0.01,
        key="threshold_ug_m3",
        help="Навчальний поріг перевищення. Не підставляйте його як офіційну ГДК.",
    )
    st.sidebar.number_input(
        "Ширина території (схід–захід), м",
        min_value=1.0,
        key="domain_width_m",
        help="Повний розмір розрахункової області. Джерело розташоване в центрі.",
    )
    st.sidebar.number_input(
        "Довжина території (північ–південь), м",
        min_value=1.0,
        key="domain_length_m",
        help="Повний розмір розрахункової області. Джерело розташоване в центрі.",
    )
    st.sidebar.number_input(
        "Крок сітки, м",
        min_value=1.0,
        key="grid_step_m",
        help="Відстань між вузлами. Менший крок детальніший, але збільшує число комірок.",
    )
    st.sidebar.number_input(
        "Густота населення, осіб/км²",
        min_value=0.0,
        key="population_density_per_km2",
        help="Синтетичне рівномірне значення. Населення = площа перевищення × густота.",
    )
    st.sidebar.number_input(
        "Тривалість впливу, год",
        min_value=0.1,
        key="exposure_duration_h",
        help="Час, на який множиться навчальний збиток.",
    )
    st.sidebar.number_input(
        "Коефіцієнт збитку, грн/(особа·год·відносне перевищення)",
        min_value=0.0,
        key="damage_coefficient_uah",
    st.sidebar.number_input(
        "Коефіцієнт збитку, грн/(особа·год·відносне перевищення)",
        min_value=0.0,
        key="damage_coefficient_uah",
        help="Навчальне припущення, а не офіційна ставка збитку.",
    )
    st.sidebar.number_input(
        "Вартість встановлення очищення за 100% скорочення, грн",
        min_value=0.0,
        key="filter_installation_cost_uah",
        help="Капітальні витрати повного скорочення. Для сценарію p% береться частка p/100.",
    )
    st.sidebar.number_input(
        "Експлуатаційні витрати за 100% скорочення, грн",
        min_value=0.0,
        key="filter_operating_cost_uah",
        help="Витрати за вибраний період аналізу для повного скорочення, не ставка за годину.",
    )
    st.sidebar.slider(
        "Зменшення викидів для карти, %",
        min_value=0,
        max_value=100,
        key="emission_reduction_percent",
        help="Карта і блок екологічних показників відповідають цьому відсотку. Таблиця порівнює 0, 30, 60 і 90%.",
    )
    with st.sidebar.expander("Сталі σy і σz замість кривих Бріггса"):
        st.checkbox(
            "Використати сталі коефіцієнти розсіювання",
            key="use_constant_sigma",
            help="Додаткове спрощення: σ не зростають із відстанню.",
        )
        st.number_input("σy, м", min_value=0.1, key="sigma_y_m", help="Горизонтальне розсіювання.")
        st.number_input("σz, м", min_value=0.1, key="sigma_z_m", help="Вертикальне розсіювання.")


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


def _apply_uploaded_csv(uploaded: object) -> None:
    signature = getattr(uploaded, "name", "") + str(getattr(uploaded, "size", ""))
    if st.session_state.get("_csv_signature") == signature:
        return
    try:
        parsed = parse_input_row(pd.read_csv(uploaded))
    except (ValueError, pd.errors.ParserError, UnicodeError) as error:
        st.sidebar.error(f"Не вдалося прочитати CSV: {error}")
        return
    for key, value in parsed.items():
        st.session_state[key] = value
    st.session_state["_csv_signature"] = signature
    st.sidebar.success("Параметри з CSV застосовано.")
    source = SourceParameters(
        pollutant=str(st.session_state["pollutant"]),
        emission_rate_g_s=float(st.session_state["emission_rate_g_s"]),
        effective_height_m=float(st.session_state["effective_height_m"]),
        wind_speed_m_s=float(st.session_state["wind_speed_m_s"]),
        wind_direction_deg=float(st.session_state["wind_direction_deg"]),
        stability_class=str(st.session_state["stability_class"]),
def _run_analysis() -> AnalysisResult:
    use_sigma = bool(st.session_state["use_constant_sigma"])
    source = SourceParameters(
        pollutant=str(st.session_state["pollutant"]),
        emission_rate_g_s=float(st.session_state["emission_rate_g_s"]),
        effective_height_m=float(st.session_state["effective_height_m"]),
        wind_speed_m_s=float(st.session_state["wind_speed_m_s"]),
        wind_direction_deg=float(st.session_state["wind_direction_deg"]),
        stability_class=str(st.session_state["stability_class"]),
        decay_coefficient_per_s=float(st.session_state["decay_coefficient_per_s"]),
        background_concentration_ug_m3=float(st.session_state["background_concentration_ug_m3"]),
        sigma_y_m=float(st.session_state["sigma_y_m"]) if use_sigma else None,
        sigma_z_m=float(st.session_state["sigma_z_m"]) if use_sigma else None,
    )
    )
    grid = GridSpec(
        width_m=float(st.session_state["domain_width_m"]),
        length_m=float(st.session_state["domain_length_m"]),
        step_m=float(st.session_state["grid_step_m"]),
    )
    economics = EconomicParameters(
        damage_coefficient_uah_per_person_hour=float(st.session_state["damage_coefficient_uah"]),
        exposure_duration_h=float(st.session_state["exposure_duration_h"]),
    economics = EconomicParameters(
        damage_coefficient_uah_per_person_hour=float(st.session_state["damage_coefficient_uah"]),
        exposure_duration_h=float(st.session_state["exposure_duration_h"]),
        filter_installation_cost_uah=float(st.session_state["filter_installation_cost_uah"]),
        filter_operating_cost_uah=float(st.session_state["filter_operating_cost_uah"]),
        population_density_per_km2=float(st.session_state["population_density_per_km2"]),
    )
        population_density_per_km2=float(st.session_state["population_density_per_km2"]),
    )
    return analyze(
        source,
        grid,
        threshold_ug_m3=float(st.session_state["threshold_ug_m3"]),
        economics=economics,
        reduction_percents=load_scenario_percents(),
    return analyze(
        source=source,
        grid=grid,
        threshold_ug_m3=float(st.session_state["threshold_ug_m3"]),
        economics=economics,
        reduction_percents=load_scenario_percents(),
        selected_reduction_percent=float(st.session_state["emission_reduction_percent"]),
    )


def _render_overview(analysis: AnalysisResult) -> None:
    """Пояснює результат простою мовою: схема, статус, ключові числа."""
    pollutant = str(st.session_state["pollutant"])
    threshold = float(st.session_state["threshold_ug_m3"])
    wind_deg = float(st.session_state["wind_direction_deg"])
    selected = analysis.selected
    pollutant = str(st.session_state["pollutant"])
    threshold = float(st.session_state["threshold_ug_m3"])
    wind_deg = float(st.session_state["wind_direction_deg"])
    selected = analysis.selected
    summary = analysis.summary
    field = analysis.field
    destination = air_flow_destination(wind_deg)

    st.subheader("Огляд результату")
    st.markdown(
        plain_language_summary(
            analysis,
            pollutant=pollutant,
            wind_direction_deg=wind_deg,
            threshold_ug_m3=threshold,
            exposure_duration_h=float(st.session_state["exposure_duration_h"]),
        )
    )

    st.plotly_chart(
        build_process_scheme(
            pollutant=pollutant,
            wind_direction_deg=wind_deg,
            threshold_ug_m3=threshold,
            selected=selected,
        ),
        use_container_width=True,
    )

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

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Речовина", pollutant)
    c2.metric(
        "Вітер",
        f"{wind_direction_label(wind_deg)}",
        help=(
            f"Метеорологічний напрямок {wind_deg:g}°: звідки дме. "
            f"Шлейф зносить на {air_flow_destination(wind_deg)}."
        ),
    )
    c3.metric("Зона перевищення", f"{selected.polluted_area_km2:.3f} км²")
    c4.metric("Навчальний збиток", f"{selected.damage_uah:,.0f} грн")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Максимальна концентрація", f"{summary.max_concentration_ug_m3:.2f} мкг/м³")
    m2.metric("Середня концентрація", f"{summary.mean_concentration_ug_m3:.2f} мкг/м³")
    m3.metric("Площа перевищення", f"{summary.polluted_area_km2:.4f} км²")
    m4.metric("Частка території", f"{summary.polluted_fraction:.1%}")
    st.metric("Населення в зоні впливу, наближено", f"{summary.exposed_population:.1f} осіб")

    st.info(
        "Далі: вкладка **Карта і графіки** — де саме лежить шлейф; "
        "**Економіка і сценарії** — порівняння 0 / 30 / 60 / 90% очищення."
    )
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

    st.markdown(
        "Профіль нижче — концентрація **вздовж осі шлейфу**. "
        "Пунктир — поріг. Якщо крива вище пунктиру, у цій відстані є перевищення."
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

    st.markdown(
        "Стовпчики порівнюють сценарії очищення: ліворуч екологія (максимум), "
        "праворуч навчальні грошові показники в грн."
    )
    st.plotly_chart(
        build_scenario_comparison(_scenario_frame(analysis, localized=False)),
        use_container_width=True,
    )


def _render_weather() -> None:
    st.subheader("Вітер з Open-Meteo")
    st.markdown(
        "Сервіс читає історичний вітер на висоті 10 м. Якщо API недоступний, залиште швидкість "
        "і напрямок у бічній панелі: розрахунок моделі від мережі не залежить."
    )
    latitude = st.number_input("Широта, градуси", value=50.45, key="meteo_lat")
    longitude = st.number_input("Довгота, градуси", value=30.52, key="meteo_lon")
    start = st.date_input("Дата початку", key="meteo_start")
    end = st.date_input("Дата завершення", key="meteo_end")
    if st.button("Отримати вітер"):
        settings = load_settings()
        try:
            summary = _fetch_wind_cached(
                float(latitude),
                float(longitude),
                start.isoformat(),
                end.isoformat(),
                settings.open_meteo_base_url,
                settings.request_timeout_seconds,
            )
        except (WeatherServiceError, ModelInputError) as error:
            st.error(str(error))
        else:
            st.session_state["meteo_summary"] = summary
    summary = st.session_state.get("meteo_summary")
    if not summary:
        return
    st.success(
        f"Отримано з Open-Meteo: швидкість {summary['wind_speed_m_s']:.2f} м/с, "
        f"напрямок {summary['wind_direction_deg']:.1f}°. "
        f"Усереднено {summary['hours_used']} год, часовий пояс {summary['timezone']}."
    )
    st.caption("Це середні отриманих годин, а не підставлені значення.")
    st.plotly_chart(
        build_wind_series(summary["times"], summary["hourly_speed_m_s"]),
        use_container_width=True,
    )
    if st.button("Підставити цей вітер у модель"):
        st.session_state["wind_speed_m_s"] = float(summary["wind_speed_m_s"])
        st.session_state["wind_direction_deg"] = int(round(summary["wind_direction_deg"]))
        st.rerun()


@st.cache_data(show_spinner=False, ttl=3600)
def _fetch_wind_cached(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    base_url: str,
    timeout_seconds: float,
) -> dict[str, object]:
    """Кешує лише успішну відповідь Open-Meteo."""
    client = OpenMeteoClient(base_url, timeout_seconds)
    summary = client.fetch_wind(latitude, longitude, start_date, end_date)
    return asdict(summary)


def _render_openaq() -> None:
    st.subheader("Станції OpenAQ")
    st.markdown(
        "Цей блок підготовлений для наступних етапів. Вимірювання не калібрують гаусову модель "
        "і не потрібні для її запуску. Ключ задається змінною `OPENAQ_API_KEY` у файлі `.env`."
    )
    settings = load_settings()
    if not settings.openaq_api_key:
        st.info("Ключ OpenAQ не налаштовано. Решта програми працює без нього.")
    latitude = st.number_input("Широта для пошуку станцій", value=50.45, key="aq_lat")
    longitude = st.number_input("Довгота для пошуку станцій", value=30.52, key="aq_lon")
    radius = st.number_input("Радіус пошуку, м", min_value=1, max_value=25000, value=10000, key="aq_radius")
    if st.button("Шукати станції"):
        client = OpenAQClient(
            settings.openaq_api_key,
            settings.openaq_base_url,
            settings.request_timeout_seconds,
        )
        try:
            validate_coordinates(float(latitude), float(longitude))
            locations = client.find_locations(float(latitude), float(longitude), radius_m=int(radius))
        except (OpenAQError, ModelInputError) as error:
            st.error(str(error))
        else:
            st.session_state["aq_locations"] = [
                {
                    "location_id": item.location_id,
                    "name": item.name,
                    "locality": item.locality,
                    "latitude": item.latitude,
                    "longitude": item.longitude,
                    "distance_m": item.distance_m,
                    "sensors": [asdict(sensor) for sensor in item.sensors],
                }
                for item in locations
            ]
    locations = st.session_state.get("aq_locations")
    if locations is None:
        return
    if not locations:
        st.info("Поблизу вказаних координат станцій OpenAQ не знайдено.")
        return
    labels = [
        f"{item['name']} (id {item['location_id']}"
        + (f", {item['distance_m']:.0f} м" if item["distance_m"] is not None else "")
        + ")"
        for item in locations
    ]
    index = st.selectbox("Станція", range(len(labels)), format_func=lambda i: labels[i])
    sensors = locations[index]["sensors"]
    if not sensors:
        st.info("У вибраної станції API не повернув сенсорів.")
        return
    sensor_labels = [
        f"{sensor['parameter'] or 'сенсор'} [{sensor['units']}], id {sensor['sensor_id']}" for sensor in sensors
    ]
    sensor_index = st.selectbox("Сенсор", range(len(sensor_labels)), format_func=lambda i: sensor_labels[i])
    if st.button("Отримати вимірювання"):
        client = OpenAQClient(
            settings.openaq_api_key,
            settings.openaq_base_url,
            settings.request_timeout_seconds,
        )
        try:
            measurements = client.get_sensor_measurements(int(sensors[sensor_index]["sensor_id"]))
        except OpenAQError as error:
            st.error(str(error))
        else:
            if not measurements:
                st.info("Для цього сенсора вимірювань не отримано.")
            else:
                st.dataframe(pd.DataFrame([asdict(item) for item in measurements]), use_container_width=True)


def _render_about() -> None:
    st.subheader("Що рахує перша версія")
    st.markdown(
        f"""
Модель рахує приземну концентрацію постійного точкового джерела на площині в метрах.
σy і σz беруться з сільських формул Бріггса для класу стійкості або зі сталих значень.
Внесок шлейфу переводиться з г/м³ у мкг/м³ множенням на 1 000 000 і після цього додається фон.

Демонстраційний файл параметрів: `{SAMPLE_INPUT_PATH.name}` у каталозі `data`.
Формули, джерела даних і обмеження описані в каталозі `docs`.

**Документи для захисту першого етапу**

- `docs/defense_conclusion.md` — висновок з розрахунками
- `docs/defense_conclusion.docx` — той самий текст для Teams / друку
- `docs/project_statement.md` — постановка задачі
        """
    )


def _scenario_frame(analysis: AnalysisResult, *, localized: bool = True) -> pd.DataFrame:
    frame = pd.DataFrame([item.to_dict() for item in analysis.scenarios])
    if not localized:
        return frame
    renamed = frame.rename(columns=DISPLAY_COLUMNS)
    return renamed[list(DISPLAY_COLUMNS.values())]


if __name__ == "__main__":
    main()
