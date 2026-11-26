"""Scenario inputs, explicit simulation and saved-run comparisons."""
import json

import pandas as pd
import streamlit as st

from .config import DEFAULT, PRESETS, Settings
from .model import CANONICAL, feasible, simulate
from .storage import parse_recipe
from .ui import baseline, case_label, change_run, fmt, heading, option_labels, reset, store, table, tr

GROUPS = (
    ("Campus and grid", "Campus und Netz", (
        ("it_mw", "Installed IT [MW]", "Installierte IT [MW]", 1.0),
        ("grid_mw", "Connection allocation [MW]", "Netzanschluss [MW]", 1.0),
        ("module_mw", "Heat module size [MWth]", "Wärmemodul [MWth]", .5),
        ("heat_scale", "Buyer demand multiplier", "Faktor Wärmebedarf", .1),
        ("cop", "Heat-pump COP (0 = auto)", "Wärmepumpen-COP (0 = automatisch)", .1),
        ("heat_tariff", "Delivered heat tariff [€/MWhth]", "Wärmepreis [€/MWhth]", 1.0),
    )),
    ("Heat investment", "Wärmeinvestition", (
        ("pipe_km", "Pipe route [km]", "Leitungsstrecke [km]", .1),
        ("pipe_cost_per_km_m", "Pipe cost [€m/km]", "Leitungskosten [Mio. €/km]", .1),
        ("nonpipe_stage_one_m", "First-stage cost excluding pipe [€m]", "Kosten Stufe 1 ohne Leitung [Mio. €]", .5),
        ("stage_two_m", "Incremental second-stage cost [€m]", "Zusatzkosten Stufe 2 [Mio. €]", .5),
        ("minimum_increment_gwh", "Minimum stage heat gain [GWhth/yr]", "Mindestwärme je Stufe [GWhth/Jahr]", .5),
        ("gas_residual_t_mwh", "Buyer backup emissions [t CO₂e/MWhth]", "Emissionen der Ersatzwärme [t CO₂e/MWhth]", .01),
    )),
    ("Electricity and resources", "Strom und Ressourcen", (
        ("pv_mwp", "On-site PV [MWp]", "PV vor Ort [MWp]", .5),
        ("pv_fraction", "PV yield multiplier", "PV-Ertragsfaktor", .05),
        ("hydro_mw", "Illustrative hydro [MW]", "Exemplarische Wasserkraft [MW]", 1.0),
        ("hydro_fraction", "Hydro yield multiplier", "Wasserkraftertragsfaktor", .05),
        ("wind_mw", "Illustrative wind [MW]", "Exemplarische Windkraft [MW]", 1.0),
        ("wind_fraction", "Wind yield multiplier", "Windkraftertragsfaktor", .05),
        ("price_multiplier", "Power price multiplier", "Strompreisfaktor", .05),
        ("carbon_g", "Grid emissions factor [g CO₂e/kWh]", "Emissionsfaktor Netz [g CO₂e/kWh]", 1.0),
    )),
    ("Stress and hardware", "Stresstest und Hardware", (
        ("hot_delta_c", "Summer temperature change [°C]", "Sommer-Temperaturänderung [°C]", .5),
        ("heat_outage_hours", "Buyer outage [winter hours]", "Abnahmeausfall [Winterstunden]", 1),
        ("peak_restriction_mw", "Winter allocation reduction [MW]", "Abzug Winterleistung [MW]", 1.0),
        ("expensive_hours", "Winter hours with +€240/MWh", "Winterstunden mit +240 €/MWh", 1),
        ("hardware_efficiency_ratio", "Hardware same-work efficiency ratio", "Effizienzfaktor bei gleicher Rechenleistung", .05),
        ("hardware_footprint_kg", "Candidate footprint [kg CO₂e]", "Fußabdruck der Alternative [kg CO₂e]", 10.0),
        ("replacement_horizon_years", "Replacement horizon [yr]", "Ersatzhorizont [Jahre]", .5),
    )),
)

CASE_COLS = {
    "modules": "Modules", "IT_GWh": "IT GWh/yr", "grid_GWh": "Grid GWh/yr", "PUE": "PUE",
    "delivered_heat_GWhth": "Delivered GWhth/yr", "backup_heat_GWhth": "Backup GWhth/yr",
    "hourly_renewable_matching_pct": "Hourly matching %",
    "combined_gas_comparator_ktCO2e": "Joint dispatch-basis ktCO₂e/yr",
    "heat_15y_NPV_MEUR": "Heat NPV €m", "capex_heat_MEUR": "Heat capex €m",
    "hourly_grid_excess_MW": "Hourly grid excess MW",
}

FIELD_HELP = {
    "module_mw": (
        "Maximum heat output of one heat pump before losses in the pipe.",
        "Maximale Wärmeleistung einer Wärmepumpe vor den Verlusten in der Leitung.",
    ),
    "heat_scale": (
        "Scales the customer's hourly heat demand. Use 1 for the reference demand or 0.5 for half.",
        "Skaliert den stündlichen Wärmebedarf des Abnehmers. 1 entspricht der Referenz, 0,5 der Hälfte.",
    ),
    "cop": (
        "Heat output per unit of electricity used by the heat pump. With 0, the model estimates COP from outdoor temperature.",
        "Wärmeleistung je Einheit Stromverbrauch der Wärmepumpe. Bei 0 schätzt das Modell den COP aus der Außentemperatur.",
    ),
    "heat_tariff": (
        "Revenue per megawatt-hour of heat measured at the customer meter.",
        "Erlös je Megawattstunde Wärme, die am Abnahmezähler gemessen wird.",
    ),
    "gas_residual_t_mwh": (
        "Emissions per unit of backup heat. The heat pump must stay below this threshold in coordinated operation.",
        "Emissionen je Einheit Ersatzwärme. Im koordinierten Betrieb muss die Wärmepumpe unter der Schwelle bleiben.",
    ),
}


def results_table(run):
    rows = pd.DataFrame(run.cases).set_index("reference")
    visible = rows[list(CASE_COLS)].rename(columns=CASE_COLS)
    visible.insert(0, tr("Case", "Fall"), [case_label(name) for name in rows.index])
    visible[tr("Design screen", "Auslegung")] = [
        tr("Feasible" if feasible(r) else "Infeasible") for r in run.cases
    ]
    table(visible)


def field(col, seed, suffix, field_info):
    key, en, de, step = field_info
    kwargs = {}
    for bound in Settings.model_fields[key].metadata:
        for kind, widget in (("ge", "min_value"), ("le", "max_value"), ("gt", "min_value")):
            if hasattr(bound, kind):
                value = getattr(bound, kind)
                if kind == "gt":
                    value = value + (1 if isinstance(step, int) else .01)
                kwargs[widget] = type(step)(value)
    help_text = FIELD_HELP.get(key)
    return col.number_input(tr(en, de), value=type(step)(getattr(seed, key)), step=step,
                            key=f"{key}_{suffix}", help=tr(*help_text) if help_text else None, **kwargs)


def preset_seed():
    preset = st.session_state["preset_choice"]
    st.session_state["lab_preset"] = preset
    if preset == "Custom inputs":
        return
    st.session_state["lab_seed"] = Settings.model_validate({**DEFAULT.model_dump(), **PRESETS[preset]})
    st.session_state["lab_modules"] = 1
    st.session_state["lab_payload"] = None
    st.session_state["lab_epoch"] = st.session_state.get("lab_epoch", 0) + 1


def inputs(run):
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    current = st.session_state.get("lab_preset", "Base")
    choices = [*PRESETS, "Custom inputs"] if current == "Custom inputs" else list(PRESETS)
    st.session_state["preset_choice"] = current
    c1.selectbox(tr("Load assumptions from a preset", "Annahmen einer Vorlage laden"), choices,
                 key="preset_choice", on_change=preset_seed,
                 help=tr("Loads values into the form. Select Run simulation to update the charts and results.",
                         "Lädt Werte in das Formular. Simulation starten aktualisiert Diagramme und Ergebnisse."),
                 format_func=option_labels(choices, lambda choice: tr(choice, "Eigene Eingaben")
                                             if choice == "Custom inputs" else choice))
    c2.button(tr("Reset to baseline"), on_click=reset, width="stretch")
    if st.session_state.get("lab_seed", run.settings) != run.settings or st.session_state.get("lab_payload") != run.payload:
        st.warning(tr("Pending changes. Charts show the last successful run until you simulate.",
                      "Änderungen ausstehend. Die Diagramme zeigen den letzten erfolgreichen Lauf."))
    st.caption(tr("Edits in this form apply when you run it. The current result stays available if validation fails.",
                  "Eingaben werden beim Start übernommen. Bei einem Fehler bleibt der letzte Lauf verfügbar."))
    suffix = st.session_state.get("lab_epoch", 0)
    seed = st.session_state.get("lab_seed", run.settings)
    feedback = st.empty()
    if st.session_state.pop("lab_run_completed", False):
        feedback.success(tr(
            "Simulation complete. See A–D results to review the output or Compare runs to compare scenarios.",
            "Simulation abgeschlossen. Unter Ergebnisse A–D stehen die Resultate. Unter Läufe vergleichen kannst du Szenarien vergleichen.",
        ))
    with st.form("scenario_form"):
        submitted = st.form_submit_button(tr("Run simulation"), type="primary", width="stretch")
        area, fixed = st.columns(2)
        sites = ("Vienna", "Linz", "Graz")
        site = area.selectbox(tr("Regional proxy", "Regionalprofil"), sites, index=sites.index(seed.site),
                              key=f"site_{suffix}", format_func=option_labels(sites, lambda x: tr(x, "Wien" if x == "Vienna" else x)))
        modules = fixed.selectbox(tr("Fixed equipment for dispatch comparison", "Installierte Module für Betriebsvergleich"),
                                  (0, 1, 2), index=st.session_state.get("lab_modules", run.fixed_modules),
                                  key=f"fixed_{suffix}",
                                  help=tr("Both operating strategies use this number of heat pumps. Case D separately tests whether to invest.",
                                          "Beide Betriebsstrategien nutzen diese Anzahl Wärmepumpen. Fall D prüft die Investition gesondert."))
        values = {"site": site}
        for i, (en, de, fields) in enumerate(GROUPS):
            with st.expander(tr(en, de), expanded=i == 0):
                cols = st.columns(3)
                for j, controls in enumerate(fields):
                    values[controls[0]] = field(cols[j % 3], seed, suffix, controls)
        with st.expander(tr("Hourly input CSV", "CSV mit Stundenwerten")):
            st.caption(tr("Seven native fields and all 8,760 ordered hours of 2025 fixed CET are required. "
                          "The hourly file supplies carbon intensity and solar shape. Outages still affect acceptance.",
                          "Erforderlich sind sieben Originalfelder und 8.760 Stunden in fester MEZ für 2025. "
                          "Die Datei liefert Emissionsintensität und Solarprofil. Ausfälle beeinflussen die Wärmeabnahme."))
            upload = st.file_uploader(tr("Replace hourly input", "Stundenwerte ersetzen"), type=["csv"], key=f"hourly_{suffix}")
            keep = st.checkbox(tr("Keep attached hourly input when no new file is supplied",
                                  "Vorhandene Stundenwerte ohne neue Datei beibehalten"), value=True, key=f"keep_{suffix}")
    st.download_button(tr("Download hourly input template", "Vorlage für Stundenwerte"), CANONICAL.read_bytes(),
                       "example_hourly_inputs.csv", "text/csv", on_click="ignore")
    if submitted:
        try:
            settings = Settings.model_validate(values)
            payload = upload.getvalue() if upload is not None else st.session_state.get("lab_payload", run.payload) if keep else None
            with st.spinner(tr("Running 8,760 hours across the engineering cases…", "8.760 Stunden werden simuliert…")):
                result = simulate(settings, payload, modules)
            change_run(result)
            st.session_state["lab_run_completed"] = True
            st.rerun()
        except (ValueError, AssertionError, RuntimeError) as error:
            feedback.error(str(error) or tr("The input failed an audited physical constraint.",
                                      "Eine physikalische Prüfung der Eingabe ist fehlgeschlagen."))


def saved(run):
    db = store()
    if st.session_state.pop("scenario_saved_notice", False):
        st.success(tr("Scenario saved.", "Szenario gespeichert."))
    st.caption(tr("Desktop launcher: saved on this computer. Public demo: saved for this session; download JSON to keep a copy.",
                  "Desktop-Start: lokal gespeichert. Öffentliche Demo: für diese Sitzung gespeichert. JSON sichert eine Kopie."))
    with st.form("save_scenario"):
        name = st.text_input(tr("Scenario name", "Szenarioname"), max_chars=64)
        save = st.form_submit_button(tr("Save current result", "Aktuelles Ergebnis speichern"))
    if save:
        try:
            db.save(name, run)
            st.session_state["scenario_saved_notice"] = True
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    upload = st.file_uploader(tr("Import a scenario recipe", "Szenario-JSON importieren"), type=["json"])
    if st.button(tr("Run imported recipe", "Importiertes Szenario ausführen"), disabled=upload is None):
        try:
            result = simulate(*parse_recipe(upload.getvalue()))
            change_run(result, "Imported recipe")
            st.rerun()
        except (ValueError, RuntimeError, AssertionError) as error:
            st.error(str(error) or tr("Imported scenario failed a model check.", "Importiertes Szenario ist ungültig."))
    entries = {key: (name, created) for key, name, created in db.list()}
    if not entries:
        return
    key = st.selectbox(tr("Saved scenario", "Gespeichertes Szenario"), entries,
                       format_func=lambda k: f"{entries[k][0]} · {entries[k][1][:16].replace('T', ' ')} UTC")
    if st.button(tr("Open saved scenario", "Gespeichertes Szenario öffnen")):
        try:
            config, _ = db.get(key)
            change_run(simulate(*parse_recipe(config)), entries[key][0])
            st.rerun()
        except (ValueError, AssertionError, RuntimeError) as error:
            st.error(str(error))
    with st.form(f"manage_{key}"):
        edited = st.text_input(tr("Rename or duplicate as", "Umbenennen oder duplizieren als"), value=entries[key][0], max_chars=64)
        confirmed = st.checkbox(tr("Confirm deletion of this saved copy", "Löschen dieser Kopie bestätigen"))
        a, b, c = st.columns(3)
        rename = a.form_submit_button(tr("Rename", "Umbenennen"))
        duplicate = b.form_submit_button(tr("Duplicate", "Duplizieren"))
        with c.container(key="delete_saved_scenario"):
            delete = st.form_submit_button(tr("Delete", "Löschen"))
    if rename or duplicate or delete:
        try:
            if rename:
                db.rename(key, edited)
            if duplicate:
                db.save(edited, simulate(*parse_recipe(db.get(key)[0])))
            if delete:
                if not confirmed:
                    raise ValueError(tr("Confirm deletion first.", "Bitte Löschung bestätigen."))
                db.delete(key)
            st.rerun()
        except (ValueError, AssertionError, RuntimeError) as error:
            st.error(str(error))


def comparisons(run):
    db = store()
    entries = {key: name for key, name, _ in db.list()}
    names = list(entries.values())
    options = {key: name if names.count(name) == 1 else f"{name} · {key[:6]}" for key, name in entries.items()}
    keys = st.multiselect(tr("Compare up to four saved scenarios", "Bis zu vier gespeicherte Szenarien vergleichen"),
                          options, format_func=options.__getitem__, max_selections=4)
    reference = baseline()
    labels = [tr("Current case D", "Aktueller Fall D")]
    rows = [run.d]
    workload_differs = run.service_hash != reference.service_hash
    for key in keys:
        try:
            raw, snapshot = db.get(key)
            fingerprint = json.loads(raw)["metadata"].get("hourly_service_sha256")
            workload_differs |= fingerprint != reference.service_hash
            labels.append(options[key])
            rows.append(snapshot["annual"][3])
        except ValueError as error:
            st.error(str(error))
    cols = ("IT_GWh", "demand_heat_GWhth", "grid_GWh", "delivered_heat_GWhth", "heat_15y_NPV_MEUR",
            "hourly_renewable_matching_pct")
    if workload_differs:
        st.warning(tr("The hourly IT workload or buyer heat demand differs from the baseline or lacks a matching fingerprint. "
                      "Deltas show scenario differences.",
                      "Die stündliche IT-Last oder der Wärmebedarf weicht ab oder hat keinen passenden Fingerabdruck. "
                      "Differenzen zeigen Szenariounterschiede."))
    st.caption(tr("Differences use the immutable official case D as reference. Percentage differences use the baseline value.",
                  "Differenzen beziehen sich auf den offiziellen Fall D. Prozentwerte verwenden den Referenzwert."))
    records = []
    for label, row in zip(labels, rows, strict=True):
        for field in cols:
            original, value = reference.d[field], row[field]
            delta = value - original
            records.append({
                tr("Scenario", "Szenario"): label, tr("Metric", "Kennzahl"): CASE_COLS.get(field, "Buyer demand GWhth/yr"),
                tr("Baseline", "Referenz"): fmt(original), tr("Value", "Wert"): fmt(value),
                tr("Absolute Δ", "Absolutes Δ"): fmt(delta, signed=True),
                tr("Relative Δ", "Relatives Δ"): f"{fmt(100 * delta / original, signed=True)}%" if original else "N/A",
            })
    table(pd.DataFrame(records))


def page(run):
    heading("Scenario lab", "Szenarien", "Configure the campus, run the audited model and compare the outcomes.",
            "Campus konfigurieren, das geprüfte Modell ausführen und Ergebnisse vergleichen.")
    builder, cases, compare, library = st.tabs(tuple(tr(en, de) for en, de in (
        ("Build scenario", "Szenario erstellen"), ("A–D results", "Ergebnisse A–D"),
        ("Compare runs", "Läufe vergleichen"), ("Saved scenarios", "Gespeicherte Szenarien"),
    )))
    with builder:
        inputs(run)
    with cases:
        if not feasible(run.d):
            st.error(tr("Case D fails the grid design or hourly screen. The trace is retained for diagnosis.",
                        "Fall D verletzt die Netzgrenze. Die Zeitreihe dient der Diagnose."))
        results_table(run)
        st.caption(tr("A–D use equivalent computing activity and required customer heat. C sizes independently but dispatches within the actual operating limit.",
                      "A–D verwenden dieselbe Rechenaktivität und denselben Wärmebedarf. C dimensioniert unabhängig und beachtet im Betrieb die Netzgrenze."))
        table(pd.DataFrame(run.fixed)[["reference", *CASE_COLS]].rename(columns=CASE_COLS))
    with compare:
        comparisons(run)
    with library:
        saved(run)
