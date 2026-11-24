"""Shared Streamlit labels, charts, navigation and run state."""
from base64 import b64encode
from functools import lru_cache
from html import escape
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .config import DEFAULT, PRESETS, Settings
from .model import ROOT, simulate
from .storage import Store

INK = "#13283b"
TEAL = "#0c6b60"
BLUE = "#3263a2"
SOFT = "#3b8193"
ORANGE = "#ad5a19"
GRAY = "#667b92"
COLORS = (TEAL, BLUE, ORANGE, SOFT, "#735497", "#596577", GRAY)
SERIES_COLORS = {
    "grid_MW": BLUE,
    "IT_MW": "#735497",
    "campus_gross_MW": "#304659",
    "pv_MW": "#32844a",
    "grid_limit_MW": ORANGE,
    "heat_plant_MW": TEAL,
    "offsite_matched_GWh": "#32844a",
    "PV_used_GWh": "#7a9f35",
    "unmatched_grid_GWh": BLUE,
    "required_heat_MWth": "#304659",
    "accepted_heat_MWth": SOFT,
    "delivered_MWth": TEAL,
    "delivered_GWhth": TEAL,
    "backup_MWth": ORANGE,
    "backup_GWhth": ORANGE,
    "Replay delivered MWth": TEAL,
    "Replay backup MWth": ORANGE,
}

PAGES = {
    "Overview": "Übersicht", "Scenario lab": "Szenarien", "Power & renewables": "Strom & Erneuerbare",
    "Heat dispatch": "Wärmebetrieb", "Investment": "Investition", "Impact & circularity": "Umwelt & Kreislauf",
    "Austrian sites": "Standorte", "Validation": "Validierung", "Evidence & exports": "Quellen & Export",
    "Jury mode": "Jury-Modus",
}
BASE_LOCALE = {
    "Official baseline": "Offizielle Referenz", "Custom scenario": "Eigenes Szenario",
    "Historical research": "Frühere Forschung", "Proxy profiles": "Modellprofile",
    "Unverified hourly data": "Ungeprüfte Stundenwerte",
    "Feasible": "Technisch möglich", "Infeasible": "Technisch nicht möglich",
    "Delivered heat": "Gelieferte Wärme", "Buyer backup": "Ersatzwärme", "Grid imports": "Netzbezug",
    "Hourly matching": "Stündliche Deckung", "Heat-project NPV": "Kapitalwert der Wärmeanlage",
    "Installed IT": "Installierte IT-Leistung", "Buyer heat required": "Wärmebedarf des Abnehmers",
    "Case D": "Fall D", "Run simulation": "Simulation starten", "Reset to baseline": "Referenz wiederherstellen",
    "Annual IT electricity": "Jährlicher IT-Strombedarf", "Tariff floor": "Mindestpreis",
    "Use for lab": "Im Szenario öffnen", "Design peak": "Auslegungsspitze", "Sampled peak": "Modellierte Spitze",
    "Nominal headroom": "Nominelle Reserve", "Physical grid imports": "Physischer Netzbezug",
    "Evidence pending": "Nachweise ausstehend", "Eligible": "Geeignet", "Ineligible": "Nicht geeignet",
    "Ratings incomplete": "Bewertung unvollständig", "Official proxy profiles": "Offizielle Modellprofile",
}
CASE_NAMES = {
    "A": "A · Conventional",
    "B": "B · Efficient / no heat export",
    "C": "C · Independent",
    "D": "D · Coordinated",
    "Same modules without coordination": "Matched hardware · Fixed dispatch",
    "Installed coordinated": "Installed · Coordinated",
    "Installed fixed": "Installed · Fixed dispatch",
}
CASE_DE = ("A · Konventionell", "B · Effizient / ohne Wärme", "C · Unabhängig", "D · Koordiniert",
           "Gleiche Anlage · Fester Betrieb", "Installiert · Koordiniert", "Installiert · Fest")


def tr(en, de=None):
    if st.session_state.get("language") == "Deutsch":
        return de or BASE_LOCALE.get(en, PAGES.get(en, en))
    return en


def option_labels(options, translate):
    labels = {option: translate(option) for option in options}
    return labels.__getitem__


@lru_cache(maxsize=3)
def svg_asset(filename, paused=False):
    svg = (ROOT / "assets" / filename).read_text(encoding="utf-8")
    if paused:
        svg = svg.replace("</style>", ".pulse { animation-play-state: paused; }\n</style>")
    return "data:image/svg+xml;base64," + b64encode(svg.encode()).decode("ascii")


def case_label(key):
    return tr(CASE_NAMES[key], CASE_DE[list(CASE_NAMES).index(key)])


def fmt(value, digits=2, signed=False):
    if value is None or pd.isna(value):
        return "N/A"
    if abs(value) < .5 * 10 ** -digits:
        value = 0
    result = f"{value:+,.{digits}f}" if signed else f"{value:,.{digits}f}"
    if st.session_state.get("language") == "Deutsch":
        result = result.translate(str.maketrans({",": ".", ".": ","}))
    return result


def metrics(items):
    for col, (label, value, help_text) in zip(st.columns(len(items)), items, strict=True):
        col.metric(tr(label), value, help=help_text)


@st.cache_resource(show_spinner=False)
def baseline():
    return simulate()


def active():
    return st.session_state.get("custom_run") or baseline()


def store():
    if "scenario_store" not in st.session_state:
        path = ROOT / ".data/scenarios.sqlite3" if os.environ.get("TC_LOCAL_STORAGE") == "1" else None
        st.session_state["scenario_store"] = Store(path)
    return st.session_state["scenario_store"]


def change_run(run, name=None, seed=True):
    st.session_state["custom_run"] = None if run.official else run
    st.session_state["run_name"] = name
    if seed:
        st.session_state["lab_seed"] = run.settings
        st.session_state["lab_payload"] = run.payload
        st.session_state["lab_modules"] = run.fixed_modules
        st.session_state["lab_epoch"] = st.session_state.get("lab_epoch", 0) + 1
        preset = "Custom inputs"
        if run.payload is None and run.fixed_modules == 1:
            preset = next((key for key, edits in PRESETS.items()
                           if run.settings.model_dump() == {**DEFAULT.model_dump(), **edits}), preset)
        st.session_state["lab_preset"] = preset


def reset():
    change_run(baseline())


def activate_preset(key, destination="Scenario lab"):
    change_run(simulate(Settings.model_validate({**DEFAULT.model_dump(), **PRESETS[key]})), key)
    if destination == "Heat dispatch":
        st.session_state["heat_case"] = "D"
    st.session_state["nav"] = destination


def navigate(destination):
    st.session_state["nav"] = destination


def top_context(run, historical=False):
    if historical:
        label = tr("Historical research")
        detail = tr("Earlier D9 · legacy perimeter", "Frühere D9-Studie · abweichende Bilanzgrenze")
    else:
        label = tr("Official baseline" if run.official else "Custom scenario")
        profile = tr("Proxy profiles" if run.payload is None else "Unverified hourly data")
        detail = f"{run.id} · {profile} · {tr('2025 fixed CET', '2025 feste MEZ')}"
    mode = "" if run.official and not historical else " custom"
    language = tr("en", "de")
    st.html(f'<div class="tc-context" lang="{language}"><span class="tc-mode{mode}">{escape(label)}</span>'
            f'<span class="tc-run">{escape(detail)}</span></div>')


def jump_to_section():
    navigate(st.session_state["section_picker"])


def workspace_bar(run):
    st.session_state["section_picker"] = st.session_state["nav"]
    with st.container(key="workspace_bar", vertical_alignment="center"):
        status, picker = st.columns([1.65, 1], vertical_alignment="bottom")
        with status:
            top_context(run)
        picker.selectbox(tr("Jump to section", "Zum Abschnitt"), list(PAGES),
                         key="section_picker", on_change=jump_to_section,
                         format_func=option_labels(PAGES, tr))


def heading(en, de, detail, detail_de):
    with st.container(key="page_intro"):
        st.title(tr(en, de))
        st.markdown(tr(detail, detail_de))


def note(title, detail):
    st.html(f'<div class="tc-note"><strong>{escape(title)}</strong> {escape(detail)}</div>')


def chart(fig, y=None, x=None, height=350):
    show_legend = len([trace for trace in fig.data if trace.showlegend is not False
                       and trace.type != "heatmap"]) > 1
    fig.update_yaxes(automargin=True, title_standoff=13, gridcolor="#e1e9f2", zerolinecolor="#b9c8d7")
    fig.update_xaxes(automargin=True, title_standoff=16, gridcolor="#edf2f4", nticks=4)
    if y is not None:
        fig.update_yaxes(title_text=y)
    if x is not None:
        fig.update_xaxes(title_text=x)
    fig.update_layout(height=height + (42 if show_legend else 12), paper_bgcolor="#ffffff",
                      plot_bgcolor="#ffffff", separators=tr(".,", ",."),
                      font=dict(family="Arial, sans-serif", size=14, color=INK), colorway=COLORS,
                      margin=dict(l=56, r=24, t=58 if show_legend else 32, b=62 if x else 48, autoexpand=True),
                      hoverlabel=dict(font_size=14, namelength=-1), showlegend=show_legend,
                      legend=dict(orientation="h", yref="paper", yanchor="bottom", y=1.045,
                                  xref="paper", xanchor="left", x=0, font=dict(size=13)))
    st.plotly_chart(fig, theme=None, width="stretch", config={"displaylogo": False, "scrollZoom": False})


def lines(frame, names, unit, height=350):
    fig = go.Figure()
    time_format = "%{x}"
    if isinstance(frame.index, pd.DatetimeIndex):
        days = (frame.index[-1] - frame.index[0]) / pd.Timedelta(days=1)
        fig.update_xaxes(tickformat="%b" if days >= 90 else "%d %b" if days >= 4 else "%H:%M")
        time_format = "%{x|%d %b %Y, %H:%M}"
    for index, (key, label) in enumerate(names.items()):
        fig.add_scatter(x=frame.index, y=frame[key], name=label, mode="lines",
                        line=dict(color=SERIES_COLORS.get(key, COLORS[index % len(COLORS)]), width=1.8,
                                  dash="dash" if key in ("grid_limit_MW", "required_heat_MWth") else "solid"),
                        hovertemplate="%{y:,.2f} " + unit + "<br>" + time_format)
    chart(fig, unit, height=height)


def bars(frame, names, unit, stack=False, height=350):
    fig = go.Figure()
    months = frame.index.name == "month_fixed_CET"
    values = pd.to_datetime(frame.index) if months else frame.index
    if months:
        fig.update_xaxes(type="date", tickformat="%b")
    for index, (key, label) in enumerate(names.items()):
        fig.add_bar(x=values, y=frame[key], name=label,
                    marker_color=SERIES_COLORS.get(key, COLORS[index % len(COLORS)]),
                    hovertemplate="%{y:,.2f} " + unit + ("<br>%{x|%b %Y}" if months else "<br>%{x}"))
    fig.update_layout(barmode="stack" if stack else "group")
    chart(fig, unit, height=height)


def table(frame, *, hide_index=True, labels=None):
    if labels:
        frame = frame.rename(columns=labels)
    column_config = {
        name: st.column_config.NumberColumn(format="localized")
        for name in frame.select_dtypes(include="number").columns if name not in ("Year", "Modules")
    }
    st.dataframe(frame, hide_index=hide_index, width="stretch", column_config=column_config)


def sidebar():
    with st.sidebar:
        st.html(f'<div class="tc-brand"><img class="tc-mark" src="{svg_asset("thermocircular-mark.svg")}" alt="">'
                '<div><strong>ThermoCircular</strong><small>AI Campus</small></div></div>')
        st.radio(tr("Navigation", "Navigation"), list(PAGES), key="nav",
                 format_func=option_labels(PAGES, tr), label_visibility="collapsed")
        st.selectbox("Language / Sprache", ("English", "Deutsch"), key="language")
