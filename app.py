"""Streamlit entry point for the ThermoCircular AI Campus demonstrator."""
import streamlit as st

from thermocircular import engineering, evidence_page, investment, lab, overview, review
from thermocircular.model import ROOT, feasible
from thermocircular.ui import active, reset, sidebar, tr, workspace_bar

st.set_page_config(
    page_title="ThermoCircular · AI Campus",
    page_icon="♨️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

VIEWS = {
    "Overview": overview.page,
    "Scenario lab": lab.page,
    "Power & renewables": engineering.power,
    "Heat dispatch": engineering.heat,
    "Investment": investment.page,
    "Impact & circularity": review.impact,
    "Austrian sites": review.sites,
    "Validation": review.validation,
    "Evidence & exports": evidence_page.page,
    "Jury mode": overview.jury,
}

st.html((ROOT / "assets/style.css").read_text(encoding="utf-8"))
sidebar()
view = st.session_state["nav"]
run = active()

if view == "Jury mode":
    overview.jury()
else:
    workspace_bar(run)
    if not run.official:
        with st.sidebar:
            st.button(tr("Reset to baseline"), key="sidebar_reset", on_click=reset, width="stretch")
    if not feasible(run.d):
        st.warning(tr("Case D is infeasible under the current design or hourly grid limit.",
                      "Fall D überschreitet die aktuelle Auslegungs- oder stündliche Netzgrenze."))
    if not 50 <= run.settings.it_mw <= 100:
        st.warning(tr("The installed IT size is outside the 50–100 MW study range.",
                      "Die installierte IT-Leistung liegt außerhalb des Untersuchungsbereichs von 50–100 MW."))
    VIEWS[view](run)
