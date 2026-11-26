"""Electrical, renewable and thermal operating views."""
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .model import feasible, installed_tradeoff, monthly, nameplate
from .ui import BLUE, TEAL, bars, case_label, chart, fmt, heading, lines, metrics, note, option_labels, table, tr


def case_choice(key):
    keys = ("D", "A", "B", "C", "Same modules without coordination", "Installed coordinated", "Installed fixed")
    return st.selectbox(tr("Model case", "Modellfall"), keys, format_func=option_labels(keys, case_label), key=key)


def select_trace(run, case):
    row = next(row for row in (*run.cases, *run.fixed) if row["reference"] == case)
    return row, run.traces[case]


def window(trace, prefix):
    col1, col2 = st.columns([1, 2])
    periods = dict(Year="Jahr", Month="Monat", Week="Woche", Day="Tag", Hour="Stunde")
    period = col1.selectbox(tr("Window", "Zeitraum"), list(periods),
                            format_func=option_labels(periods, lambda x: tr(x, periods[x])),
                            key=f"{prefix}_window")
    if period == "Year":
        return trace
    if period == "Month":
        month = col2.select_slider(tr("Month", "Monat"), list(range(1, 13)), key=f"{prefix}_month")
        return trace[trace.index.month == month]
    day = pd.Timestamp(col2.date_input(tr("Start date (fixed CET)", "Startdatum (feste MEZ)"),
                                       value=date(2025, 1, 1), min_value=date(2025, 1, 1),
                                       max_value=date(2025, 12, 31), key=f"{prefix}_date"))
    if period == "Hour":
        hour = st.slider(tr("Hour starting in fixed CET", "Stundenbeginn in fester MEZ"), 0, 23, key=f"{prefix}_hour")
        return trace.loc[[day + pd.Timedelta(hours=hour)]]
    return trace[(trace.index >= day) & (trace.index < day + pd.Timedelta(days=1 if period == "Day" else 7))]


def status(row):
    if not feasible(row):
        st.error(tr("The nameplate design or hourly grid limit fails. The model preserves IT activity and reports the excess.",
                    "Auslegung oder stündliche Netzgrenze wird verletzt. Das Modell erhält die IT-Aktivität und zeigt die Überschreitung."))


def power(run):
    heading("Power & renewables", "Strom & Erneuerbare",
            "Inspect the connection limit, campus consumption and time-matched procurement.",
            "Netzgrenze, Campusverbrauch und zeitgleiche Strombeschaffung prüfen.")
    case = case_choice("power_case")
    r, t = select_trace(run, case)
    status(r)
    grid_limit = run.settings.grid_mw
    peak = nameplate(run.settings, r["modules"], case == "A")
    metrics([
        ("Design peak", f"{fmt(peak)} MW", tr("Conservative nameplate screen with no firm solar credit.", "Konservative Auslegung ohne sichere PV-Leistung.")),
        ("Sampled peak", f"{fmt(r['combined_peak_MW'])} MW", tr("Maximum hourly import in this trace.", "Maximaler stündlicher Netzbezug.")),
        ("Nominal headroom", f"{fmt(grid_limit - peak)} MW", tr("Connection allocation minus the design screen.", "Netzanschlussleistung abzüglich Auslegungsspitze.")),
        ("Physical grid imports", f"{fmt(r['grid_GWh'])} GWh", tr("Annual meter imports before any financial matching.", "Jährlicher Netzbezug vor bilanzieller Deckung.")),
    ])
    a, b, c = st.tabs((tr("Load profile", "Lastprofil"), tr("Renewable matching", "Erneuerbare Deckung"),
                       tr("Energy ledger", "Energiebilanz")))
    with a:
        visible = window(t, "power")
        if len(visible) == 1:
            table(visible[["IT_MW", "facility_MW", "heat_plant_MW", "pv_MW", "grid_MW", "grid_limit_MW"]], hide_index=False)
        else:
            lines(visible, {
                "grid_MW": tr("Grid imports"), "IT_MW": tr("IT load", "IT-Last"),
                "campus_gross_MW": tr("Gross campus", "Bruttolast Campus"), "pv_MW": "PV",
                "heat_plant_MW": tr("Heat plant", "Wärmeanlage"), "grid_limit_MW": tr("Import limit", "Netzgrenze"),
            }, "MW")
        peak_time = t.grid_MW.idxmax()
        grid = t.loc[peak_time]
        st.write(tr("Peak event", "Spitzenereignis"), f"{peak_time:%d %b, %H:%M} CET · {fmt(grid.grid_MW)} / {fmt(grid.grid_limit_MW)} MW")
        st.caption(tr("800 V DC, battery storage and N−1 protection are research topics outside the active dispatch model.",
                      "800-V-Gleichstrom, Batteriespeicher und N−1-Schutz sind Forschungsthemen außerhalb des Betriebsmodells."))
    with b:
        ledger = monthly(t)
        metrics([
            ("Hourly matching", f"{fmt(r['hourly_renewable_matching_pct'])}%", tr("On-site PV used plus matched offsite energy, divided by gross campus use.", "Genutzte PV plus zeitgleich zugeordneter externer Strom geteilt durch Bruttolast.")),
            (tr("Annual generation ratio", "Jährliches Erzeugungsverhältnis"), f"{fmt(r['annual_renewable_matching_pct'])}%", tr("Annual supply compared with demand. Surplus generation can take this ratio above 100%.", "Jahreserzeugung im Verhältnis zum Bedarf. Überschüsse können den Wert über 100 % erhöhen.")),
        (tr("Fully matched hours", "Vollständig gedeckte Stunden"), f"{fmt(r['wholly_matched_hours'], 0)} / {fmt(8760, 0)}",
         tr("Hours when on-site solar and matched off-site renewables cover all campus electricity use.",
            "Stunden, in denen PV vor Ort und zeitgleich zugeordnete externe Erzeugung den gesamten Strombedarf decken.")),
        ])
        bars(ledger, {"offsite_matched_GWh": tr("Offsite matched", "Extern zeitgleich"),
                      "PV_used_GWh": tr("On-site PV used", "PV-Eigenverbrauch"),
                      "unmatched_grid_GWh": tr("Residual grid", "Restnetzbezug")}, "GWh", stack=True)
        table(ledger[["hydro_generated_GWh", "wind_generated_GWh", "PV_GWh", "grid_export_GWh", "grid_GWh",
                      "offsite_matched_GWh", "matching_pct", "wholly_matched_hours"]], hide_index=False)
        site = "Vienna (Linz proxy)" if run.settings.site == "Linz" else run.settings.site
        profile = tr("uploaded hourly CSV", "hochgeladene CSV") if run.payload else site
        note(tr("Solar shape", "Solarprofil"), f"{profile}. " + tr(
            "Offsite generation is illustrative. Matching leaves physical grid imports intact.",
            "Externe Erzeugung ist exemplarisch. Die bilanzielle Deckung ändert den Netzbezug nicht."))
    with c:
        ledger = monthly(t)
        r_total = (r["facility_GWh"] + r["heat_system_GWh"]) / r["IT_GWh"]
        st.markdown(f"**PUE {fmt(r['PUE'], 3)}** · {tr('Gross campus electricity / IT', 'Bruttostrom Campus / IT')} **{fmt(r_total, 3)}**")
        st.caption(tr("PUE divides facility electricity by IT electricity. The gross campus ratio also includes the heat plant.",
                      "PUE teilt den Gebäudestrom durch den IT-Strom. Das Bruttoverhältnis enthält zusätzlich die Wärmeanlage."))
        fields = ["IT_GWh", "facility_GWh", "campus_gross_GWh", "heat_plant_GWh", "PV_GWh", "grid_export_GWh", "grid_GWh"]
        table(pd.concat([ledger[fields], ledger[fields].sum().to_frame(tr("Annual", "Jahr")).T]), hide_index=False)


def buyer_monthly(run, case="D"):
    ledger = monthly(run.traces[case])
    bars(ledger, {"delivered_GWhth": tr("Delivered heat"), "backup_GWhth": tr("Buyer backup")}, "GWhth", stack=True)


def heat(run):
    heading("Heat dispatch", "Wärmebetrieb",
            "Follow heat from the IT loop to the customer meter and see which gates bind.",
            "Wärme vom IT-Kreislauf bis zum Abnahmezähler verfolgen und Betriebsgrenzen prüfen.")
    case = case_choice("heat_case")
    r, t = select_trace(run, case)
    status(r)
    metrics([
        ("Delivered heat", f"{fmt(r['delivered_heat_GWhth'])} GWhth", tr("Annual useful heat at the buyer meter, after losses.", "Jährliche Nutzwärme am Abnahmezähler, nach Verlusten.")),
        ("Buyer backup", f"{fmt(r['backup_heat_GWhth'])} GWhth", tr("Required heat minus delivered heat for the year.", "Jährlicher Wärmebedarf abzüglich gelieferter Wärme.")),
        (tr("Effective delivery COP", "Effektiver Liefer-COP"), fmt(r["effective_delivery_COP"] or None), tr("Delivered heat divided by total plant electricity.", "Gelieferte Wärme geteilt durch Strombedarf der Wärmeanlage.")),
        (tr("Heat-plant power use", "Strombedarf Wärmeanlage"), f"{fmt(r['heat_system_GWh'])} GWh", tr("Includes compressor and auxiliary electricity.", "Enthält Verdichter und Hilfsenergie.")),
    ])
    tabs = st.tabs(tuple(tr(en, de) for en, de in (("Buyer balance", "Wärmebilanz"), ("Hourly gates", "Stündliche Grenzen"),
                                                   ("Duration & COP", "Dauer und COP"), ("Installed comparison", "Installierte Module"))))
    with tabs[0]:
        buyer_monthly(run, case)
        fields = ("source_MWth", "condenser_MWth", "thermal_loss_MWth", "delivered_MWth", "backup_MWth", "rejected_IT_MWth")
        totals = t[list(fields)].sum() / 1000
        flow_labels = ("IT source heat", "Condenser heat", "Network losses", "Buyer delivery", "Buyer backup", "Rejected IT heat")
        flow_de = ("IT-Quellwärme", "Kondensatorwärme", "Netzverluste", "Wärmelieferung", "Ersatzwärme", "Abgeführte IT-Wärme")
        table(pd.DataFrame({
            tr("Flow", "Wärmestrom"): [tr(en, de) for en, de in zip(flow_labels, flow_de, strict=True)],
            "GWhth/yr": totals.to_numpy(),
        }))
        note(tr("Independent rejection", "Unabhängige Wärmeabfuhr"),
             tr("With the buyer unavailable, the proposed design sends IT heat to an independent rejection path and the buyer relies on backup.",
                "Bei Ausfall der Abnahme sieht das Konzept eine unabhängige Wärmeabfuhr für die IT und Ersatzwärme beim Abnehmer vor."))
    with tabs[1]:
        visible = window(t, "heat")
        if len(visible) > 1:
            lines(visible, {"required_heat_MWth": tr("Required", "Bedarf"), "accepted_heat_MWth": tr("Accepted", "Abnahme"),
                            "delivered_MWth": tr("Delivered heat"), "backup_MWth": tr("Buyer backup")}, "MWth")
        start, end = t.index.get_loc(visible.index[0]), t.index.get_loc(visible.index[-1])
        ix = start if start == end else st.slider(tr("Inspect hour in this window", "Stunde im Zeitraum prüfen"), int(start), int(end),
                        value=int(start), key=f"inspect_hour_{start}_{end}",
                        format="%d", help=tr("Each step is one hour. Hour 0 is midnight on 1 January 2025, CET.",
                                             "Jeder Schritt ist eine Stunde. Stunde 0 beginnt am 1. Januar 2025 um 00:00 MEZ."))
        hourly_detail(run, case, r, t.iloc[ix], t.index[ix])
    with tabs[2]:
        fig = go.Figure()
        for field, name, color in (("required_heat_MWth", tr("Buyer heat required"), BLUE), ("delivered_MWth", tr("Delivered heat"), TEAL)):
            fig.add_scatter(x=np.arange(1, len(t) + 1), y=np.sort(t[field])[::-1], name=name, line=dict(color=color))
        chart(fig, "MWth", tr("Hours at or above power", "Stunden ab dieser Leistung"))
        lines(t.resample("D").mean(), {"COP": tr("Daily average equipment COP", "Mittlerer Tages-COP")}, "COP", height=270)
    with tabs[3]:
        installed_comparison(run)


def hourly_detail(run, case, row, h, stamp):
    st.subheader(f"{stamp:%d %B %Y · %H:%M} CET")
    ceiling = row["modules"] * run.settings.module_mw
    gates = {
        tr("Installed condenser capacity [MWth]", "Installierte Kondensatorleistung [MWth]"): ceiling,
        tr("Customer acceptance ceiling [MWth at condenser]", "Abnahmegrenze [MWth am Kondensator]"): h.accepted_heat_MWth / .95,
        tr("IT source ceiling [MWth at condenser]", "IT-Quellgrenze [MWth am Kondensator]"): h.source_ceiling_MWth / (1 - 1 / h.COP),
        tr("Headroom ceiling [MWth at condenser]", "Netzreserve [MWth am Kondensator]"): h.usable_grid_headroom_MW / (1 / h.COP + .01),
    }
    tight = min(gates.values())
    operating = case in ("D", "Installed coordinated")
    table(pd.DataFrame({
        tr("Physical constraint", "Physikalische Grenze"): list(gates),
        tr("Value", "Wert"): [fmt(v, 3) for v in gates.values()],
        tr("Binding", "Bindend"): [abs(v - tight) < 1e-8 for v in gates.values()],
    }))
    price = h.power_price_EUR_MWh * (1 / h.COP + .01)
    carbon = h.carbon_t_MWh * (1 / h.COP + .01)
    earnings = .95 * run.settings.heat_tariff
    factor = .95 * run.settings.gas_residual_t_mwh
    table(pd.DataFrame({
        tr("Dispatch gate", "Betriebsgrenze"): [tr("Variable economics", "Variable Wirtschaftlichkeit"), tr("Buyer carbon", "CO₂e des Abnehmers")],
        tr("Marginal plant", "Grenzwert Anlage"): [f"{fmt(price)} €/MWhth", f"{fmt(carbon, 4)} t/MWhth"],
        tr("Threshold", "Schwelle"): [f"{fmt(earnings)} €/MWhth", f"{fmt(factor, 4)} t/MWhth"],
        tr("Pass", "Erfüllt"): [bool(h.positive_variable_margin), bool(h.beats_customer_carbon)],
    }))
    st.caption(tr("Thresholds apply to coordinated dispatch." if operating else "Fixed dispatch shows these thresholds for comparison.",
                  "Schwellen gelten für koordinierten Betrieb." if operating else "Fester Betrieb zeigt Schwellen zum Vergleich."))
    st.write(f"{tr('Delivered heat')} {fmt(h.delivered_MWth)} MWth · {tr('Buyer backup')} {fmt(h.backup_MWth)} MWth")


def installed_comparison(run):
    st.subheader(tr("Same installed equipment", "Identische installierte Anlage"))
    st.caption(tr(f"{run.fixed_modules} fixed module(s) in both policies. Procurement case D independently screens whether to invest.",
                  f"{run.fixed_modules} feste Module in beiden Betriebsweisen. Fall D prüft die Investition separat."))
    delta = installed_tradeoff(run)
    metrics([
        (tr("Operator NPV Δ", "Betreiber-Kapitalwert Δ"), f"{fmt(delta['operator_delta_MEUR'], 3, True)} €m", tr("Coordinated minus fixed under equal hardware.", "Koordiniert abzüglich fest bei gleicher Anlage.")),
        (tr("Buyer backup Δ", "Ersatzwärme Δ"), f"{fmt(delta['backup_delta_GWhth'], 2, True)} GWhth", tr("Additional annual backup volume.", "Zusätzliche jährliche Ersatzwärme.")),
        (tr("Joint emissions Δ", "Gemeinsame Emissionen Δ"), f"{fmt(delta['emissions_delta_ktCO2e'], 3, True)} kt CO₂e",
         tr("Coordinated minus fixed operation. Includes campus electricity and the customer's backup heat.",
            "Koordinierter abzüglich fester Betrieb, einschließlich Campusstrom und Ersatzwärme des Abnehmers.")),
    ])
    penalty = delta["erasing_penalty_EUR_MWh"]
    st.write(f"{tr('Backup price that erases operator gain', 'Ersatzwärmepreis, der den Vorteil aufhebt')} · "
             + (f"{fmt(penalty)} €/MWhth" if penalty is not None and penalty > 0 else "N/A"))
    table(pd.DataFrame(run.fixed)[["reference", "delivered_heat_GWhth", "backup_heat_GWhth",
                                  "heat_15y_NPV_MEUR", "nameplate_feasible", "hourly_grid_excess_MW"]])
