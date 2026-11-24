"""Shared Streamlit labels, charts, navigation and run state."""
from html import escape
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .config import DEFAULT, PRESETS, Settings
from .model import ROOT, simulate
from .storage import Store

INK = "#132b3d"
TEAL = "#126f70"
BLUE = "#426b92"
SOFT = "#8bb8bf"
ORANGE = "#b35324"
GRAY = "#a7b9c7"
COLORS = (TEAL, BLUE, ORANGE, SOFT, "#7456a2", "#495d65", GRAY)

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


def reset():
    change_run(baseline())
    st.session_state["preset_choice"] = "Base"


def activate_preset(key, destination="Scenario lab"):
    change_run(simulate(Settings.model_validate({**DEFAULT.model_dump(), **PRESETS[key]})), key)
    st.session_state["preset_choice"] = key
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
        detail = f"{run.id}  ·  {profile}  ·  2025 fixed CET"
    mode = "" if run.official and not historical else " custom"
    st.html(f'<div class="tc-context"><span class="tc-mode{mode}">{escape(label)}</span>'
            f'<span class="tc-run">{escape(detail)}</span></div>')


def heading(en, de, detail, detail_de):
    st.title(tr(en, de))
    st.caption(tr(detail, detail_de))


def note(title, detail):
    st.html(f'<div class="tc-note"><strong>{escape(title)}</strong> {escape(detail)}</div>')


def chart(fig, y=None, x=None, height=350):
    if y:
        fig.update_yaxes(title_text=y, gridcolor="#e1eaef", zerolinecolor="#ccdce3", automargin=True)
    if x:
        fig.update_xaxes(title_text=x, gridcolor="#edf2f4", automargin=True)
    fig.update_layout(height=height, paper_bgcolor="white", plot_bgcolor="white", separators=tr(".,", ",."),
                      font=dict(family="Arial, sans-serif", size=14, color=INK), colorway=COLORS,
                      margin=dict(l=60, r=25, t=24, b=80 if x else 62),
                      hoverlabel=dict(font_size=14),
                      legend=dict(orientation="h", yanchor="top", y=-.19, x=0, font=dict(size=13)))
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": False})


def lines(frame, names, unit, height=350):
    fig = go.Figure()
    for index, (key, label) in enumerate(names.items()):
        fig.add_scatter(x=frame.index, y=frame[key], name=label, mode="lines",
                        line=dict(color=COLORS[index % len(COLORS)], width=1.8,
                                  dash="dash" if key == "grid_limit_MW" else "solid"))
    chart(fig, unit, height=height)


def bars(frame, names, unit, stack=False, height=350):
    fig = go.Figure()
    for key, label in names.items():
        fig.add_bar(x=frame.index, y=frame[key], name=label)
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
        st.html('<div class="tc-brand"><span class="tc-mark" aria-hidden="true">◈</span>'
                '<div><strong>ThermoCircular</strong><small>AI Campus</small></div></div>')
        st.selectbox("Language / Sprache", ("English", "Deutsch"), key="language")
        st.radio(tr("Navigation", "Navigation"), list(PAGES), key="nav",
                 format_func=option_labels(PAGES, tr), label_visibility="collapsed")
        st.divider()
        st.caption(tr("InnoScope 2026 · Engineering screening", "InnoScope 2026 · Technische Vorprüfung"))
