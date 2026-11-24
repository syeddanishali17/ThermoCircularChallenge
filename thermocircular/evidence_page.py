"""Archived source browser, methodological notes and run-specific exports."""
import pandas as pd
import streamlit as st

from .exports import config_bytes, csv_bytes, hourly_zip, html_bytes, workbook_bytes
from .model import LIMITATIONS, monthly, stress_suite
from .review import evidence, safe_link
from .ui import heading, table, top_context, tr


def source_browser():
    sources = (
        ("Research_Master_Bibliography", "Master bibliography", "Gesamtbibliografie"),
        ("Submission_Sources", "Submission sources", "Quellen der Einreichung"),
        ("sources", "Austrian site sources", "Österreichische Standortquellen"),
    )
    names = {key: tr(en, de) for key, en, de in sources}
    category = st.selectbox(tr("Source register", "Quellenregister"), list(names), format_func=names.__getitem__)
    frame = evidence(category).copy()
    urls = next((c for c in frame if "URL" in c), None)
    if urls is not None:
        frame[urls] = frame[urls].map(safe_link)
    term = st.text_input(tr("Search title, ID or organisation", "Titel, ID oder Organisation suchen"), max_chars=120).strip()
    if category == "Research_Master_Bibliography":
        options = sorted(x for x in frame["Source type"].unique() if x)
        filters = st.multiselect(tr("Source type", "Quellentyp"), options)
        if filters:
            frame = frame[frame["Source type"].isin(filters)]
    if term:
        mask = frame.apply(lambda column: column.astype(str).str.contains(term, case=False, regex=False)).any(axis=1)
        frame = frame[mask]
    st.caption(tr(f"{len(frame)} entries · Archived citations; underlying status and limitations vary by source.",
                  f"{len(frame)} Einträge · Archivierte Quellenverweise mit unterschiedlichem Status und Grenzen."))
    column_config = {urls: st.column_config.LinkColumn("URL", display_text=tr("Open", "Öffnen"))} if urls else {}
    st.dataframe(frame, hide_index=True, width="stretch", column_config=column_config)
    st.divider()
    st.subheader(tr("Research lineage", "Forschungsgrundlagen"))
    table(pd.DataFrame([
        ("D1–D2", "Architecture and system decomposition", "Problem and design boundaries"),
        ("D3", "International technical benchmarks", "Public documented precedent"),
        ("D4", "Austrian regional data and site screening", "Climate and solar context, site gates"),
        ("D5–D6", "Lifecycle screening and Infineon reference designs", "Component hypotheses and bench qualification"),
        ("D7–D8", "Transferability and integrated design", "Alternatives and integration priorities"),
        ("D9", "Earlier comparative model", "Historical perimeter; see reconciliation"),
        ("Audited", "Engineering model and audited CSVs", "Runs and numeric regressions"),
        ("v2", "Submission and pitch handoff", "Interpretation and display rounding"),
    ], columns=("Phase", "Document", "Use in this app")))


def methodology():
    st.subheader(tr("Hourly calculation", "Stündliche Berechnung"))
    st.markdown(tr(
        "Condenser output is limited by installed capacity, buyer acceptance divided by 0.95, "
        "available IT source heat and grid headroom. Coordinated dispatch also checks variable heat margin and the "
        "buyer emissions threshold. The fixed-dispatch case uses the same physical limits.",
        "Die Kondensatorleistung wird durch Modulgröße, Abnahme geteilt durch 0,95, IT-Quellwärme und Netzreserve begrenzt. "
        "Koordinierter Betrieb prüft zusätzlich Deckungsbeitrag und Emissionsschwelle. Fester Betrieb nutzt dieselben physikalischen Grenzen.",
    ))
    st.latex(r"\mathrm{COP}_{auto} = \operatorname{clip}(4.1+0.035(T_{ambient}-10),3,5)")
    st.latex(r"Q_{buyer}=0.95 Q_{condenser},\quad P_{plant}=Q_{condenser}(1/\mathrm{COP}+0.01)")
    st.latex(r"P_{grid}=\max(0,P_{facility}+P_{plant}-P_{PV})")
    st.latex(r"\mathrm{NPV} = \mathrm{margin}_{annual}\frac{1-1.06^{-15}}{0.06}-\mathrm{CAPEX}")
    table(pd.DataFrame([
        ("Modelled IT utilisation", "60% average at reference shape", "Scenario assumption"),
        ("Facility PUE", "1.21 conventional / 1.16 efficient before hot-temperature penalty", "Scenario assumption"),
        ("Nameplate factors", "1.30 / 1.24, plus installed plant at COP 3 + 1% auxiliaries", "Design screen"),
        ("Available source heat", "≤80% of hourly IT electricity", "Scenario assumption"),
        ("Thermal distribution loss", "5% of condenser heat", "Scenario assumption"),
        ("Fixed thermal O&M", "€0.30m/yr first stage + €0.15m/yr second", "Scenario assumption"),
        ("Water", "0.03 L/kWh IT", "Scenario allowance"),
        ("ERF proxy", "Extracted source heat / facility electricity", "Proxy, outside certified reporting"),
        ("Clock", "2025 fixed CET (UTC+1), 8,760 one-hour intervals", "Deterministic calendar"),
    ], columns=("Item", "Assumption", "Evidence status")))
    st.subheader(tr("Risk register R01–R11", "Risikoregister R01–R11"))
    table(evidence("risks"))


def history(run):
    top_context(run, historical=True)
    st.markdown(tr("Earlier D9 examined two modules and used PUE 1.14. The audited current case uses one module and 1.16. "
                   "Use each result with its original service boundary.",
                   "Die frühere D9-Studie untersuchte zwei Module bei PUE 1,14. Der aktuelle geprüfte Fall verwendet ein Modul und 1,16. "
                   "Jedes Ergebnis gilt für seine Bilanzgrenze."))
    table(pd.DataFrame([
        ("Campus grid import increase", "+2.61 GWh/yr", "+7.57 GWh/yr vs B", "Different cooling PUE and build"),
        ("Resistance comparison", "35.19 GWh/yr savings", "See current post-processed comparator", "Earlier workload-equivalent study"),
        ("Base-case coordination", "Historical D9 design", "€0.00m incremental NPV vs matched hardware", "Fixed hardware and identical service"),
        ("Infineon efficiency", "Reviewed wording: >96.5% over 30–100%", "Manufacturer note: minimum 96.5% at 230 V AC", "Application note §§2.1/2.2; zero campus savings credit"),
    ], columns=("Item", "Historical", "Current interpretation", "Reconciliation")))


def downloads(run):
    st.caption(tr("Downloads correspond to the last successful run. The scenario recipe includes any uploaded hourly driver for reproducibility.",
                  "Downloads gehören zum letzten erfolgreichen Lauf. Das Szenario enthält ggf. hochgeladene Stundenwerte für Reproduzierbarkeit."))
    stress_record = st.session_state.get("stress_result")
    if st.button(tr("Run 21-case stress suite on current inputs", "21 Stresstests für aktuelle Eingaben starten"), type="primary"):
        with st.spinner(tr("Running stress cases…", "Stresstests laufen…")):
            try:
                stress_record = (run.id, stress_suite(run.settings, run.payload))
                st.session_state["stress_result"] = stress_record
            except (ValueError, RuntimeError, AssertionError) as error:
                st.error(str(error) or "Stress run failed a model check.")
    stress = stress_record[1] if stress_record and stress_record[0] == run.id else None
    if stress is not None:
        with st.expander(tr("Current stress results", "Aktuelle Stresstests"), expanded=True):
            table(stress)
    package = (
        ("Scenario JSON", "Szenario-JSON", "scenario.json", "application/json", config_bytes(run)),
        ("Annual CSV", "Jahreswerte CSV", "annual.csv", "text/csv", csv_bytes(pd.DataFrame(run.cases))),
        ("Monthly D CSV", "Monatswerte D CSV", "monthly_D.csv", "text/csv", csv_bytes(monthly(run.traces["D"]), index=True)),
        ("Investment CSV", "Investition CSV", "investment.csv", "text/csv", csv_bytes(pd.DataFrame(run.investments))),
        ("Stress CSV", "Stresstests CSV", "stress.csv", "text/csv", csv_bytes(stress) if stress is not None else None),
        ("Summary HTML", "Bericht HTML", "summary.html", "text/html", html_bytes(run, stress)),
        ("Workbook XLSX", "Excel-Arbeitsmappe", "thermocircular.xlsx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", workbook_bytes(run, stress)),
        ("Case D hourly CSV", "Stundenwerte D CSV", "hourly_D.csv", "text/csv", csv_bytes(run.traces["D"], index=True)),
    )
    layout = st.columns(2)
    for i, (label, de, filename, mime, data) in enumerate(package):
        layout[i % 2].download_button(tr(label, de), data or b"", f"{run.id}_{filename}", mime,
                                       disabled=data is None, on_click="ignore", width="stretch")
    bundle = st.session_state.get("hourly_bundle")
    if st.button(tr("Prepare all seven hourly traces (ZIP)", "Alle sieben Zeitreihen als ZIP vorbereiten")):
        with st.spinner(tr("Preparing hourly files…", "Stundenwerte werden erstellt…")):
            bundle = run.id, hourly_zip(run)
            st.session_state["hourly_bundle"] = bundle
    if bundle and bundle[0] == run.id:
        st.download_button(tr("Download hourly trace bundle", "ZIP mit Stundenwerten herunterladen"), bundle[1],
                           f"{run.id}_hourly_traces.zip", "application/zip", on_click="ignore")
    with st.expander(tr("Run manifest and limits", "Laufverzeichnis und Grenzen")):
        st.json(run.metadata())
        for item in LIMITATIONS:
            st.markdown(f"- {item}")


def page(run):
    heading("Evidence & exports", "Quellen & Export", "Trace the assumptions and take an auditable copy of a run.",
            "Annahmen nachvollziehen und eine prüfbare Kopie des Laufs herunterladen.")
    a, b, c, d = st.tabs((tr("Downloads", "Downloads"), tr("Source registers", "Quellenregister"),
                           tr("Method & risks", "Methodik und Risiken"), tr("Historical research")))
    with a:
        downloads(run)
    with b:
        source_browser()
    with c:
        methodology()
    with d:
        history(run)
