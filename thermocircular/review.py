"""Sustainability, evidence-backed site screening and validation records."""
from datetime import date
from urllib.parse import urlsplit

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .assessment import BENCH_LOADS, SITE_CRITERIA, SITE_GATES, SITE_WEIGHTS, bench_screen, component, power_input, rank_site
from .model import ROOT, comparator
from .ui import BLUE, TEAL, fmt, heading, metrics, note, option_labels, store, table, tr, chart

EVIDENCE = ROOT / "data/evidence"
BUYERS = ("Gas boiler", "Resistance heat", "Electric heat pump (COP 3)")
BUYERS_DE = ("Gaskessel", "Elektro-Direktheizung", "Elektrische Wärmepumpe (COP 3)")
SITES = ("Vienna northeast", "Linz industrial corridor", "Graz urban heat corridor")
SITE_DE = ("Wien Nordost", "Industriekorridor Linz", "Städtischer Wärmekorridor Graz")
ROADMAP = (
    ("G1", "Grid & site", "DSO / site team", "Firm import and commissioning schedule, plot, water, route and contingency studies."),
    ("G2", "Heat buyer", "Utility / buyer", "Twelve months of heat acceptance and temperatures, signed tariff and backup terms, priced route."),
    ("G3", "Thermal integration", "Thermal engineering / vendor", "Metered loop and independent rejection during off-take loss without compute interruption."),
    ("G4", "Rack power", "Qualified power lab / OEM", "Measured load-weighted benefit above uncertainty, plus protection, thermal, service and EMC checks."),
    ("G5", "Lifecycle", "Asset management / recycler", "Same-work qualification, EPD and documented repair, reuse and downstream disposition."),
    ("G6", "Metered pilot", "IT operations / utility", "Matched trace comparison, independent fallback and signed metering and compliance results."),
    ("G7", "Expansion", "Investment committee", "A full metered year, priced bids and connections, incremental useful heat and positive downside NPV."),
)

SITE_LABEL = {
    "Grid": "Netzanschluss", "Land and pipe route": "Grundstück und Trasse",
    "Fibre": "Glasfaser", "Hazards and ground": "Gefahren und Baugrund", "Water": "Wasser",
    "Permitting": "Genehmigungen", "Heat customer": "Wärmeabnehmer",
}
STATUS = ("Unknown", "Pass", "Fail")
STATUS_DE = ("Unbekannt", "Erfüllt", "Nicht erfüllt")
WORK_STATUS = ("Pending", "In progress", "Evidence logged", "Blocked")
INV_COLUMNS = ("Category", "Quantity", "Mass kg/unit", "Evidence status", "Source / EPD", "Service life yr",
               "Repairability", "Spare availability", "Return custody", "Downstream disposition")


@st.cache_data
def evidence(name):
    return pd.read_csv(EVIDENCE / f"{name}.csv", keep_default_na=False)


def safe_link(url):
    try:
        return url if urlsplit(url).scheme == "https" and urlsplit(url).hostname and "@" not in urlsplit(url).netloc else ""
    except ValueError:
        return ""


def impact_results(run):
    buyer = st.selectbox(tr("Buyer heating comparator", "Wärmevergleich des Abnehmers"),
                         BUYERS, format_func=option_labels(BUYERS, lambda b: tr(b, BUYERS_DE[BUYERS.index(b)])),
                         help=tr("Post-processes the buyer's residual heat at identical IT activity and heat demand.",
                                 "Bilanziert die Restwärme bei gleicher IT-Aktivität und gleichem Wärmebedarf."))
    fuel_factor = .202 / .90
    rows = [dict(case=k, **comparator(run.traces[k], buyer, fuel_factor)) for k in "ABCD"]
    b, d = rows[1], rows[3]
    de = d["combined_electricity_GWh"] - b["combined_electricity_GWh"]
    dg = d["combined_ktCO2e"] - b["combined_ktCO2e"]
    metrics([
        (tr("Campus import Δ", "Campus-Netzbezug Δ"), f"{fmt(d['campus_import_GWh'] - b['campus_import_GWh'], 2, True)} GWh",
         tr("D minus B, annual physical meter.", "D minus B, physischer Netzbezug pro Jahr.")),
        (tr("Combined electricity Δ", "Gemeinsamer Strom Δ"), f"{fmt(de, 2, True)} GWh",
         tr("D minus B, annual campus and buyer heating electricity.", "D minus B, jährlicher Campus- und Heizstrom.")),
        (tr("Joint emissions Δ", "Gemeinsame Emissionen Δ"), f"{fmt(dg, 2, True)} ktCO₂e",
         tr("D minus B, generation proxy plus buyer fuel if applicable.", "D minus B, Stromerzeugung plus Brennstoff falls zutreffend.")),
    ])
    st.caption(tr(f"Annual D minus B. Buyer accounting is post-processed using {buyer}. D dispatch retains its configured "
                  f"customer threshold of {fmt(run.settings.gas_residual_t_mwh, 4)} tCO₂e/MWhth.",
                  f"Jährlich D minus B. Der Vergleich verwendet {BUYERS_DE[BUYERS.index(buyer)]}. Die Betriebsentscheidung "
                  f"bleibt bei {fmt(run.settings.gas_residual_t_mwh, 4)} tCO₂e/MWhth."))
    frame = pd.DataFrame(rows).set_index("case")
    fig = go.Figure()
    for key, label, color in (
        ("grid_ktCO2e", tr("Campus generation proxy", "Stromerzeugung Campus"), BLUE),
        ("buyer_electricity_ktCO2e", tr("Buyer electricity", "Heizstrom Abnehmer"), TEAL),
        ("buyer_fuel_ktCO2e", tr("Buyer fuel", "Brennstoff Abnehmer"), "#a7b9c7"),
    ):
        fig.add_bar(x=frame.index, y=frame[key], name=label, marker_color=color)
    fig.update_layout(barmode="stack")
    chart(fig, "ktCO₂e/yr", height=310)
    table(frame.drop(columns="buyer"), hide_index=False)
    note(tr("Water allowance", "Wasseransatz"),
         f"{fmt(run.d['water_input_m3'], 0)} m³/yr · 0.03 L/kWh IT. " + tr(
             "The A–D allowance is identical. Comparative water savings, land and critical-material totals remain unevidenced.",
             "Der Ansatz ist in A–D identisch. Vergleichende Wassereinsparungen sowie Flächen- und Rohstoffmengen sind offen."))
    st.caption(tr("Purchased electricity is an operator Scope 2 category. The chart uses a generation proxy and keeps buyer fuel distinct. "
                  "Embodied emissions and contractual claims have separate boundaries.",
                  "Eingekaufter Strom gehört zu Scope 2 des Betreibers. Das Diagramm nutzt eine Näherung für Stromerzeugung "
                  "und trennt Brennstoff, graue Emissionen und Vertragsansprüche."))


def hardware(run):
    a = run.settings
    st.caption(tr("Replacement is a component example and assumes equal useful computing work. Qualify actual service, duty cycle and footprint first.",
                  "Der Ersatz ist ein Bauteilbeispiel bei gleicher Rechenarbeit. Reale Leistung, Auslastung und Fußabdruck sind zu prüfen."))
    left, right, third = st.columns(3)
    ratio = left.number_input(tr("Same-work energy efficiency ratio", "Energieeffizienz bei gleicher Arbeit"), 1.01, 20., a.hardware_efficiency_ratio, step=.05)
    foot = right.number_input(tr("Replacement footprint [kg CO₂e]", "Fußabdruck Ersatz [kg CO₂e]"), 0., 100000., a.hardware_footprint_kg)
    horizon = third.number_input(tr("Service horizon [years]", "Nutzungshorizont [Jahre]"), .01, 50., a.replacement_horizon_years)
    records = []
    for intensity in (53, 123, 10):
        old, saved, avoided, years = component(foot, ratio, intensity)
        records.append({"gCO₂e/kWh": intensity, "Old kWh/year": old, "Saved kWh/year": saved,
                        "Avoided kgCO₂e/year": avoided, "Carbon payback years": years, "Within horizon": years <= horizon})
    table(pd.DataFrame(records))
    st.caption(tr("53, 123 and 10 g/kWh are illustrative accounting cases with different boundaries. The calculator provides no fleet savings claim.",
                  "53, 123 und 10 g/kWh sind exemplarische Bilanzfälle mit unterschiedlichen Grenzen. Keine Einsparaussage für die Flotte."))
    with st.expander(tr("Optional electricity-only cost comparison", "Optionaler Vergleich der Stromkosten")):
        one, two = st.columns(2)
        electricity = one.number_input(tr("Assumed electricity [€/MWh]", "Angenommener Strompreis [€/MWh]"), min_value=0., max_value=1000., value=0.)
        cost = two.number_input(tr("Incremental installed cost [€]", "Zusätzliche Installationskosten [€]"), min_value=0., max_value=1_000_000., value=0.)
        annual = saved * electricity / 1000
        st.write(f"{tr('Annual avoided electricity cost', 'Vermiedene jährliche Stromkosten')} {fmt(annual)} € · "
                 f"{tr('Simple payback', 'Einfache Amortisation')} {fmt(cost / annual if annual else None)}")


def inventory():
    db = store()
    records = db.register("circularity", [])
    rows = pd.DataFrame(records, columns=INV_COLUMNS)
    for name in ("Quantity", "Mass kg/unit", "Service life yr"):
        rows[name] = pd.to_numeric(rows[name], errors="coerce")
    with st.form("inventory_register"):
        data = st.data_editor(rows, hide_index=True, width="stretch", num_rows="dynamic", column_config={
            "Quantity": st.column_config.NumberColumn(min_value=1, max_value=1000000, step=1),
            "Mass kg/unit": st.column_config.NumberColumn(min_value=0., max_value=100000.),
            "Service life yr": st.column_config.NumberColumn(min_value=0., max_value=100.),
            "Evidence status": st.column_config.SelectboxColumn(options=["Assumed", "Measured with provenance"]),
        })
        save = st.form_submit_button(tr("Save equipment register", "Anlagenregister speichern"))
    if save:
        try:
            clean = data.astype(object).where(data.notna(), None).to_dict("records")
            if len(clean) > 200:
                raise ValueError("The equipment register supports 200 lines.")
            for row in clean:
                if not str(row["Category"] or "").strip() or row["Quantity"] is None or row["Quantity"] < 1 or row["Quantity"] % 1:
                    raise ValueError("Every row needs an equipment category and a whole-number quantity.")
                if row["Evidence status"] == "Measured with provenance" and not row["Source / EPD"]:
                    raise ValueError("Measured rows need a source or measurement record.")
            db.save_register("circularity", clean)
            st.success(tr("Equipment register saved.", "Anlagenregister gespeichert."))
            records = clean
        except ValueError as error:
            st.error(str(error))
    quantity = sum(r["Quantity"] for r in records)
    known = [r for r in records if r["Mass kg/unit"] is not None]
    tracked_qty = sum(r["Quantity"] for r in known)
    measured = sum(r["Quantity"] * r["Mass kg/unit"] for r in known if r["Evidence status"] == "Measured with provenance")
    estimated = sum(r["Quantity"] * r["Mass kg/unit"] for r in known if r["Evidence status"] != "Measured with provenance")
    metrics([
        (tr("Inventory units", "Erfasste Einheiten"), fmt(quantity, 0), None),
        (tr("Units with mass data", "Einheiten mit Masseangabe"), f"{fmt(tracked_qty, 0)} / {fmt(quantity, 0)}", None),
        (tr("Measured mass", "Gemessene Masse"), f"{fmt(measured)} kg", None),
        (tr("Other entered mass", "Sonstige angegebene Masse"), f"{fmt(estimated)} kg", None),
    ])


def impact(run):
    heading("Impact & circularity", "Umwelt & Kreislauf", "Compare buyer-heating boundaries and record real hardware evidence.",
            "Bilanzgrenzen für Wärme vergleichen und Hardware-Nachweise erfassen.")
    energy, parts, register = st.tabs((tr("Energy & emissions", "Energie und Emissionen"), tr("Replacement screen", "Ersatzprüfung"),
                                      tr("Equipment register", "Anlagenregister")))
    with energy:
        impact_results(run)
    with parts:
        hardware(run)
    with register:
        inventory()


def sites(run):
    heading("Austrian site screening", "Standortprüfung Österreich",
            "Use regional evidence to shortlist, then qualify each parcel before scoring it.",
            "Regionale Hinweise eingrenzen und Grundstücke vor der Bewertung qualifizieren.")
    research, scoring = st.tabs((tr("Regional evidence", "Regionale Quellen"), tr("Parcel gates & scores", "Grundstücksprüfung")))
    with research:
        leads = evidence("regional_leads")
        shortlisted = leads[leads.iloc[:, 0].isin(("R01", "R06", "R07"))]
        table(shortlisted)
        st.markdown(tr("Floridsdorf provides a public operating precedent for data centre heat reuse. ThermoCircular still needs its own parcel, buyer and connection.",
                       "Floridsdorf ist ein öffentlich dokumentiertes Betriebsbeispiel. ThermoCircular benötigt ein eigenes Grundstück, einen Abnehmer und Netzanschluss."))
        st.link_button(tr("City of Vienna: Klinik Floridsdorf", "Stadt Wien: Klinik Floridsdorf"),
                       "https://www.wien.gv.at/umwelt/energie-projekt-klinik-floridsdorf")
        solar = evidence("monthly").set_index("Month").iloc[:, :2]
        solar.columns = [tr("Vienna / Linz proxy", "Wien / Linz-Näherung"), "Graz"]
        fig = go.Figure()
        for name in solar:
            fig.add_scatter(x=solar.index, y=solar[name], name=name, mode="lines+markers")
        chart(fig, "kWh/kWp", height=290)
        st.caption(tr("Archived D4 monthly solar estimates, JRC PVGIS [A11/A12]. Linz uses the Vienna proxy in the audited engine.",
                      "Archivierte monatliche Solarwerte D4, JRC PVGIS [A11/A12]. Linz verwendet im Modell das Wiener Profil."))
        with st.expander(tr("Required evidence for each parcel", "Erforderliche Nachweise je Grundstück")):
            table(evidence("gate_evidence"))
            st.caption(tr("Commissioning, title and zoning, flood and ground, water/cooling, diverse fibre, heat demand/return temperatures, tariff and backup must be supported.",
                          "Inbetriebnahme, Eigentum und Widmung, Hochwasser/Baugrund, Wasser/Kühlung, Glasfaser, Bedarf/Rücklauftemperatur, Tarif und Ersatzwärme sind zu belegen."))
    with scoring:
        site_scoring()


def site_scoring():
    db = store()
    empty = {"gates": {k: ["Unknown", ""] for k in SITE_GATES}, "ratings": [[0, ""] for _ in SITE_CRITERIA]}
    state = db.register("site_screen", {"parcels": {}, "weights": list(SITE_WEIGHTS)})
    registry, weights = state["parcels"], state["weights"]
    selected = st.selectbox(tr("Candidate parcel region", "Kandidatenregion"), SITES,
                            format_func=option_labels(SITES, lambda s: tr(s, SITE_DE[SITES.index(s)])))
    current = registry.get(selected, empty)
    with st.form(f"site_form_{selected}"):
        gates = {}
        for key in SITE_GATES:
            label = tr(key, SITE_LABEL[key])
            col1, col2 = st.columns([1, 2])
            status, reference = current["gates"][key]
            gates[key] = [col1.selectbox(label, STATUS, index=STATUS.index(status),
                                          format_func=option_labels(STATUS, lambda x: tr(x, STATUS_DE[STATUS.index(x)])),
                                          key=f"gate_{key}_{selected}"),
                          col2.text_input(tr(f"{key} dated evidence", f"{label} mit Datum"), reference, max_chars=300,
                                          key=f"gate_ref_{key}_{selected}")]
        st.subheader(tr("Conditional score", "Bedingte Bewertung"))
        st.caption(tr("Score 1 to 5 after all seven gates pass. Use 0 for unknown. Editable weights are normalised to 100.",
                      "Nach bestandenen sieben Prüfungen mit 1 bis 5 bewerten. 0 für unbekannt. Gewichte werden auf 100 normiert."))
        new_weights, ratings = [], []
        criteria_de = ("Vertraglich gesicherte Wärme", "Kosten gelieferter Wärme", "Netz und Dekarbonisierung",
                       "Kühlung und Wasser", "Kreislauf und Eignung", "Glasfaser-Resilienz")
        for ix, criterion in enumerate(SITE_CRITERIA):
            a, b, c = st.columns([1.25, 1, 2])
            label = tr(criterion, criteria_de[ix])
            score, ref = current["ratings"][ix]
            ratings.append([a.number_input(label, 0, 5, score, key=f"rate_{ix}_{selected}"),
                            c.text_input(tr(f"Evidence: {criterion}", f"Nachweis: {label}"), ref, max_chars=300, key=f"rate_ref_{ix}_{selected}")])
            new_weights.append(b.number_input(tr(f"Weight: {criterion}", f"Gewicht: {label}"), 0, 100, weights[ix],
                                              key=f"weight_{ix}_{selected}"))
        submitted = st.form_submit_button(tr("Save gates and scores", "Prüfung und Bewertung speichern"))
    if submitted:
        try:
            rank_site(gates, ratings, new_weights)
            registry[selected] = {"gates": gates, "ratings": ratings}
            db.save_register("site_screen", {"parcels": registry, "weights": new_weights})
            weights = new_weights
            st.success(tr("Site screen saved.", "Standortprüfung gespeichert."))
        except ValueError as error:
            st.error(str(error))
    ranking = []
    for candidate in SITES:
        item = registry.get(candidate, empty)
        status, score = rank_site(item["gates"], item["ratings"], weights)
        ranking.append({"Candidate": tr(candidate, SITE_DE[SITES.index(candidate)]), "Status": tr(status), "Score /100": score})
    table(pd.DataFrame(ranking).sort_values("Score /100", ascending=False, na_position="last"))
    st.caption(tr("A missing score means the candidate is unranked.", "Fehlende Punktzahl bedeutet, dass der Standort ohne Rang bleibt."))


def bench():
    st.subheader("REF_12KW_HFHD_PSU")
    st.write(tr("Infineon reports 97.8% peak and specifies at least 96.5% across 30–100% nominal load at 230 V AC, "
                "with the reference chassis fan included. The audited baseline assigns zero savings to the bench candidate.",
                "Infineon meldet 97,8 % Spitze und spezifiziert mindestens 96,5 % bei 30–100 % Nennlast an 230 V AC "
                "einschließlich Lüfter. Die geprüfte Referenz setzt hierfür keine Einsparung an."))
    infineon = evidence("Submission_Sources")
    source = infineon.loc[infineon["ID"] == 15, "URL"].iloc[0]
    st.link_button(tr("Infineon application note", "Infineon-Anwendungshinweis"), source)
    a, b, c = st.columns(3)
    dc = a.number_input(tr("Matched DC output [kW]", "Gleiche DC-Ausgangsleistung [kW]"), .1, 1000., 12., step=.1)
    inc = b.number_input(tr("Incumbent efficiency [%]", "Wirkungsgrad Bestand [%]"), 1., 100., 96.)
    cand = c.number_input(tr("Candidate efficiency [%]", "Wirkungsgrad Alternative [%]"), 1., 100., 97.)
    ai, ac, loss = power_input(dc, inc, cand)
    metrics([
        (tr("Incumbent AC draw", "AC-Aufnahme Bestand"), f"{fmt(ai, 3)} kW", None),
        (tr("Candidate AC draw", "AC-Aufnahme Alternative"), f"{fmt(ac, 3)} kW", None),
        (tr("AC draw reduction", "Reduzierte AC-Aufnahme"), f"{fmt(loss, 3, True)} kW", None),
    ])
    st.subheader(tr("Measured bench record", "Messprotokoll"))
    st.caption(tr("Enter paired readings at matched DC output and document voltage, conditions, repetitions and instrument uncertainty. "
                  "The uncertainty screen sums duty-weighted expanded point bounds conservatively.",
                  "Gepaarte Messungen bei gleicher DC-Leistung mit Spannung, Bedingungen, Wiederholungen und Messunsicherheit "
                  "eintragen. Die Prüfung summiert gewichtete erweiterte Unsicherheiten konservativ."))
    db = store()
    fields = ("Voltage V", "Temperature °C", "Repetitions", "Duty share %", "Incumbent AC kW",
              "Candidate AC kW", "Combined uncertainty kW")
    saved = db.register("psu_bench", {"rows": [{"Load %": load, **dict.fromkeys(fields), "Conditions": "", "Record": ""}
                                              for load in BENCH_LOADS], "checks": ["Unknown"] * 5})
    frame = pd.DataFrame(saved["rows"])
    for field in fields:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    with st.form("bench_measurements"):
        edited = st.data_editor(frame, hide_index=True, width="stretch", disabled=["Load %"])
        check_names = ("Protection", "Thermals", "EMC", "Reliability", "Service / warranty")
        columns = st.columns(3)
        checks = [columns[ix % 3].selectbox(tr(key, de), STATUS, index=STATUS.index(saved["checks"][ix]),
                                            format_func=option_labels(STATUS, lambda x: tr(x, STATUS_DE[STATUS.index(x)])))
                  for ix, (key, de) in enumerate(zip(check_names, ("Schutz", "Thermik", "EMV", "Zuverlässigkeit", "Service/Garantie"), strict=True))]
        submit = st.form_submit_button(tr("Save measurement record", "Messprotokoll speichern"))
    if submit:
        rows = edited.astype(object).where(edited.notna(), None).to_dict("records")
        try:
            bench_screen(rows, checks)
            saved = {"rows": rows, "checks": checks}
            db.save_register("psu_bench", saved)
        except ValueError as error:
            st.error(str(error))
    outcome, gain, bound = bench_screen(saved["rows"], saved["checks"])
    translations = {"Untested / incomplete": "Nicht getestet / unvollständig", "Qualification failed": "Qualifizierung nicht bestanden",
                    "Qualification pending": "Qualifizierung ausstehend", "Bench screen passed": "Messprüfung bestanden",
                    "Improvement below uncertainty": "Verbesserung unter Messunsicherheit"}
    st.markdown(f"**{tr(outcome, translations[outcome])}**")
    if gain is not None:
        st.caption(f"Δ {fmt(gain, 4, True)} kW · ±{fmt(bound, 4)} kW")


def roadmap_summary():
    table(pd.DataFrame(ROADMAP, columns=("Gate", "Decision", "Proposed owner", "Evidence to release")))
    st.caption(tr("Grid and customer terms precede thermal and electrical qualification. A metered pilot and a full-year record inform later expansion.",
                  "Netz- und Abnahmebedingungen gehen der thermischen und elektrischen Qualifizierung voraus. Pilotmessung und Jahresdaten stützen den Ausbau."))


def roadmap():
    roadmap_summary()
    db = store()
    records = db.register("roadmap", {})
    gate = st.selectbox(tr("Gate to update", "Prüfschritt auswählen"), [r[0] for r in ROADMAP])
    saved = records.get(gate, {"owner": next(r[2] for r in ROADMAP if r[0] == gate),
                               "status": "Pending", "due": None, "notes": "", "evidence": ""})
    with st.form(f"roadmap_{gate}"):
        a, b, c = st.columns(3)
        owner = a.text_input(tr("Owner", "Verantwortlich"), saved["owner"], max_chars=120)
        statuses_de = ("Offen", "In Arbeit", "Nachweis eingetragen", "Blockiert")
        status = b.selectbox("Status", WORK_STATUS, index=WORK_STATUS.index(saved["status"]),
                             format_func=option_labels(WORK_STATUS, lambda x: tr(x, statuses_de[WORK_STATUS.index(x)])))
        due = c.date_input(tr("Due date", "Fälligkeitsdatum"), date.fromisoformat(saved["due"]) if saved["due"] else None)
        ref = st.text_input(tr("Evidence reference", "Nachweisreferenz"), saved["evidence"], max_chars=300)
        notes = st.text_area(tr("Notes", "Notizen"), saved["notes"], max_chars=1000)
        submit = st.form_submit_button(tr("Save gate record", "Prüfschritt speichern"))
    if submit:
        if not owner.strip() or (status == "Evidence logged" and not ref.strip()):
            st.error(tr("Enter an owner and attach a reference for any logged evidence.", "Verantwortlichen und gegebenenfalls Nachweisreferenz angeben."))
        else:
            records[gate] = {"owner": owner, "status": status, "due": due.isoformat() if due else None,
                             "notes": notes, "evidence": ref}
            db.save_register("roadmap", records)
            st.success(tr("Gate record saved.", "Prüfschritt gespeichert."))
    if records:
        table(pd.DataFrame.from_dict(records, orient="index"), hide_index=False)


def replay(run):
    st.caption(tr("Read-only replay on the installed coordinated trace. Tests illustrate fallback accounting with static hourly balances.",
                  "Schreibgeschützte Wiedergabe der koordinierten Anlage. Die Tests bilden Rückfalllogik mit statischen Stundenbilanzen ab."))
    events = {"Normal": "Normal", "Buyer unavailable": "Abnahmeausfall", "Stale telemetry": "Veraltete Messwerte"}
    event = st.radio(tr("Injected condition", "Simulierter Zustand"), list(events),
                     horizontal=True, format_func=option_labels(events, lambda x: tr(x, events[x])))
    start_day = st.slider(tr("Start day of four-week replay", "Starttag der Vier-Wochen-Wiedergabe"), 1, 338, 1)
    length = st.slider(tr("First affected hours", "Erste betroffene Stunden"), 1, 672, 24)
    trace = run.traces["Installed coordinated"].iloc[(start_day - 1) * 24:(start_day - 1) * 24 + 672].copy()
    trace["Replay delivered MWth"] = trace.delivered_MWth
    trace["Replay backup MWth"] = trace.backup_MWth
    if event != "Normal":
        affected = trace.index[:length]
        trace.loc[affected, "Replay delivered MWth"] = 0.
        trace.loc[affected, "Replay backup MWth"] = trace.loc[affected, "required_heat_MWth"]
        st.warning(tr("Illustrative fallback: request zero export, independent rejection and full buyer backup during affected hours.",
                      "Exemplarischer Rückfall: kein Export, unabhängige Wärmeabfuhr und vollständige Ersatzwärme in betroffenen Stunden."))
    table(pd.DataFrame([{
        "Delivered before MWhth": trace.delivered_MWth.sum(), "Delivered in replay MWhth": trace["Replay delivered MWth"].sum(),
        "Buyer backup in replay MWhth": trace["Replay backup MWth"].sum(), "Required MWhth": trace.required_heat_MWth.sum(),
    }]))
    st.line_chart(trace[["Replay delivered MWth", "Replay backup MWth"]], width="stretch")
    with st.expander(tr("Pilot safety evidence checklist", "Nachweisliste Pilot-Sicherheit")):
        st.markdown(tr("- Independent rejection and protected computing during buyer loss\n- Meter freshness and safe fallback\n"
                       "- Instrumented acceptance and thermal limits\n- Documented incident response and protected restart",
                       "- Unabhängige Wärmeabfuhr und geschützte IT bei Abnahmeausfall\n- Aktuelle Messwerte und sichere Rückfallfunktion\n"
                       "- Gemessene Abnahme und Temperaturgrenzen\n- Dokumentierte Störfallreaktion und geschützter Neustart"))


def validation(run):
    heading("Validation & Infineon", "Validierung & Infineon",
            "Tie a component test and pilot replay to the evidence needed for a procurement decision.",
            "Bauteiltest und Pilot-Wiedergabe mit Nachweisen für die Beschaffung verbinden.")
    a, b, c = st.tabs((tr("Power bench", "Leistungsprüfstand"), tr("Validation roadmap", "Validierungsplan"),
                       tr("Four-week replay", "Vier-Wochen-Wiedergabe")))
    with a:
        bench()
    with b:
        roadmap()
    with c:
        replay(run)
