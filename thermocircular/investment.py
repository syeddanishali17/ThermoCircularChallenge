"""Heat DCF, sequential procurement gates and bounded engine sensitivities."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .config import Settings
from .model import ANNUITY, evaluate_one_module, feasible, financial, installed_tradeoff
from .ui import TEAL, ORANGE, chart, fmt, heading, metrics, note, table, tr


def gates(run):
    records = []
    for i, (before, after) in enumerate(zip(run.investments, run.investments[1:]), start=1):
        heat = after["delivered_heat_GWhth"] - before["delivered_heat_GWhth"]
        npv = after["heat_15y_NPV_MEUR"] - before["heat_15y_NPV_MEUR"]
        results = feasible(after), npv > 0, heat >= run.settings.minimum_increment_gwh
        records.append({
            tr("Stage", "Stufe"): i,
            "Δ GWhth/yr": heat, "Δ NPV €m": npv,
            tr("Design and hourly", "Auslegung und Stundenprüfung"): results[0],
            tr("Positive Δ NPV", "Positiver Δ Kapitalwert"): results[1],
            tr("Minimum Δ heat", "Mindestzuwachs Wärme"): results[2],
            tr("Decision", "Entscheidung"): tr("Model-screened candidate", "Im Modell geeigneter Kandidat") if i <= run.d["modules"]
            else tr("Defer", "Zurückstellen"),
        })
    table(pd.DataFrame(records))


def cashflows(run):
    r = run.d
    f = financial(r, run.traces["D"], run.settings)
    metrics([
        (tr("Heat capital cost", "Investitionskosten Wärme"), f"{fmt(f['Capex'])} €m", tr("Selected modules plus pipe route.", "Gewählte Module mit Leitung.")),
        (tr("Annual operating margin", "Jährlicher Betriebsüberschuss"), f"{fmt(f['Operating margin'], 3)} €m", tr("Heat revenue less plant electricity and fixed O&M.", "Wärmeerlös abzüglich Strom und fixer Betriebskosten.")),
        ("Heat-project NPV", f"{fmt(r['heat_15y_NPV_MEUR'], 3, True)} €m", tr("15-year operator cash flow at 6%.", "Betreiber-Cashflow über 15 Jahre bei 6 %.")),
        ("Tariff floor", f"{fmt(r['heat_break_even_EUR_MWh'])} €/MWhth" if r["heat_break_even_EUR_MWh"] is not None else "N/A",
         tr("Levelised break-even for dispatched heat.", "Kostendeckender Preis der gelieferten Wärme.")),
    ])
    fig = go.Figure(go.Waterfall(
        x=[tr("Heat sales", "Wärmeerlös"), tr("Power", "Strom"), tr("Fixed O&M", "Fixe Kosten"),
           tr("Heat capex", "Wärme-CAPEX"), tr("NPV", "Kapitalwert")],
        y=[ANNUITY * f["Revenue"], -ANNUITY * f["Power cost"], -ANNUITY * f["Fixed O&M"], -f["Capex"], 0],
        measure=["relative", "relative", "relative", "relative", "total"],
        increasing={"marker": {"color": TEAL}}, decreasing={"marker": {"color": ORANGE}},
    ))
    fig.update_xaxes(tickangle=-30)
    chart(fig, tr("Discounted €m", "Diskontierte Mio. €"))
    payback = r["heat_payback_years"]
    st.write(f"{tr('Simple payback', 'Einfache Amortisation')} · "
             + (f"{fmt(payback)} {tr('years', 'Jahre')}" if payback is not None else "N/A"))
    with st.expander(tr("15-year cash flows and intervention boundary", "15-Jahres-Cashflow und Systemgrenze")):
        years = np.arange(16)
        flows = np.repeat(f["Operating margin"], 16)
        flows[0] = -f["Capex"]
        discounted = flows / (1.06 ** years)
        table(pd.DataFrame({"Year": years, "Cash flow €m": flows, "Present value €m": discounted,
                            "Cumulative PV €m": discounted.cumsum()}))
        table(pd.DataFrame(run.cases)[["reference", "capex_intervention_MEUR", "annual_OPEX_net_MEUR", "discounted_intervention_cost_MEUR"]])
        st.caption(tr("Intervention figures include the efficient campus package, electricity and heat activity. The model excludes whole-campus construction.",
                      "Maßnahmen umfassen Effizienzpaket, Strom und Wärmebetrieb. Der Bau des Gesamtrechenzentrums bleibt außerhalb der Bilanz."))


def sensitivity(run):
    a = run.settings
    st.caption(tr("Hold one new module fixed. Every point reruns hourly dispatch. Blank cells indicate a failed grid screen.",
                  "Ein neues Modul bleibt fest. Jeder Punkt simuliert den Stundenbetrieb. Leere Zellen zeigen verletzte Netzgrenzen."))
    with st.form("sensitivity_grid"):
        left, right = st.columns(2)
        prices = left.slider(tr("Heat tariff range [€/MWhth]", "Wärmepreisbereich [€/MWhth]"), 1, 1000,
                             (max(1, min(999, int(a.heat_tariff - 20))), min(1000, max(2, int(a.heat_tariff + 20)))),
                             key=f"grid_tariff_{run.id}")
        distances = right.slider(tr("Pipe distance range [km]", "Leitungslängen [km]"), 0.0, 100.0,
                                 (max(0.0, min(99.9, a.pipe_km - .5)), min(100., a.pipe_km + 2)),
                                 step=.1, key=f"grid_distance_{run.id}")
        size = st.select_slider(tr("Points per axis", "Punkte pro Achse"), options=(5, 7, 9, 11), value=7)
        launch = st.form_submit_button(tr("Run tariff × distance grid", "Preise × Entfernungen berechnen"), type="primary")
    signature = (run.id, prices, distances, size)
    grid = st.session_state.get("sweep_grid")
    if launch and (grid is None or signature != grid[4]):
        tariffs = np.linspace(*prices, size)
        route = np.linspace(*distances, size)
        progress = st.progress(0)
        values = []
        with st.spinner(tr("Evaluating heat cash flow and constraints…", "Cashflow und Betriebsgrenzen werden berechnet…")):
            for i, tariff in enumerate(tariffs):
                line = []
                for distance in route:
                    r = evaluate_one_module(a, run.payload, {"heat_tariff": tariff, "pipe_km": distance})
                    line.append(r["heat_15y_NPV_MEUR"] if feasible(r) else None)
                values.append(line)
                progress.progress((i + 1) / size)
        progress.empty()
        grid = run.id, tariffs, route, values, signature
        st.session_state["sweep_grid"] = grid
    if grid and grid[0] == run.id:
        _, tariffs, route, values, _ = grid
        fig = go.Figure(go.Heatmap(
            x=route, y=tariffs, z=values, colorscale=[[0, "#a34223"], [.5, "#f8f5ee"], [1, "#126f70"]],
            zmid=0, colorbar=dict(title="NPV €m", thickness=12, tickfont=dict(size=12)), hoverongaps=False,
            hovertemplate="%{x:.2f} km<br>%{y:.2f} €/MWhth<br>NPV %{z:.3f} €m<extra></extra>",
        ))
        chart(fig, "€/MWhth", tr("Pipe route [km]", "Leitungsstrecke [km]"))
        if all(all(cell is None for cell in line) for line in values):
            st.error(tr("Every one-module grid point fails the design or hourly grid screen.",
                        "Kein Punkt mit einem Modul besteht die Netzprüfung."))

    st.subheader(tr("One-way sensitivity", "Einzelfaktor-Sensitivität"))
    st.caption(tr("Compare the change from the current one-module NPV. Automatic COP is compared with two fixed COP endpoints.",
                  "Vergleich mit dem Kapitalwert eines Moduls. Der automatische COP wird mit zwei festen COP-Werten verglichen."))
    with st.form("sensitivity_oneway"):
        spread = st.slider(tr("Relative span around present values [%]", "Relative Spanne um aktuelle Werte [%]"), 5, 60, 30, step=5)
        go_one = st.form_submit_button(tr("Run one-way sensitivity", "Einzelfaktor-Sensitivität berechnen"))
    result = st.session_state.get("oneway_result")
    if go_one and (result is None or (run.id, spread) != (result[0], result[2])):
        b = evaluate_one_module(a, run.payload, {})["heat_15y_NPV_MEUR"]
        fields = {
            "heat_tariff": "Heat tariff", "pipe_km": "Pipe distance", "price_multiplier": "Power price",
            "heat_scale": "Buyer demand", "cop": "COP", "nonpipe_stage_one_m": "Non-pipe capex",
            "grid_mw": "Grid capacity", "module_mw": "Heat module size",
        }
        rows = []
        for k, label in fields.items():
            current = getattr(a, k)
            endpoints = (current * (1 - spread / 100), current * (1 + spread / 100))
            if k == "cop":
                ref = current or 4.1
                endpoints = (max(1.01, ref * (1 - spread / 100)), min(20, ref * (1 + spread / 100)))
            results = []
            for value in endpoints:
                try:
                    Settings.model_validate({**a.model_dump(), k: value})
                    point = evaluate_one_module(a, run.payload, {k: value})
                    results.append(point["heat_15y_NPV_MEUR"] - b if feasible(point) else None)
                except ValueError:
                    results.append(None)
            rows.append({"Parameter": label, "Lower input": endpoints[0], "Upper input": endpoints[1],
                         "Lower input Δ NPV": results[0], "Upper input Δ NPV": results[1]})
        result = run.id, pd.DataFrame(rows).set_index("Parameter"), spread
        st.session_state["oneway_result"] = result
    if result and result[0] == run.id:
        order = result[1].assign(span=lambda frame: (frame["Upper input Δ NPV"] - frame["Lower input Δ NPV"]).abs())
        order = order.sort_values("span", na_position="first").drop(columns="span")
        fig = go.Figure()
        for key, label, color in (("Lower input Δ NPV", tr("Lower input", "Unterer Wert"), TEAL),
                                  ("Upper input Δ NPV", tr("Upper input", "Oberer Wert"), ORANGE)):
            fig.add_bar(y=order.index, x=order[key], orientation="h", name=label, marker_color=color)
        fig.update_layout(barmode="group")
        chart(fig, None, "Δ NPV €m", height=450)
        table(order, hide_index=False)
        st.caption(tr("Blank values indicate infeasible or invalid model inputs.", "Leere Werte zeigen nicht machbare oder ungültige Eingaben."))


def page(run):
    heading("Heat investment", "Wärmeinvestition",
            "Compare staged procurement, operating cash flow and downside sensitivities.",
            "Gestufte Beschaffung, Betriebs-Cashflow und negative Szenarien vergleichen.")
    stages, finance, lab = st.tabs((tr("Procurement gates", "Beschaffungsgrenzen"), tr("Cash flow", "Cashflow"),
                                    tr("Sensitivity lab", "Sensitivitätsanalyse")))
    with stages:
        note(tr("Sequential release", "Gestufte Freigabe"),
             tr("A stage needs connection and hourly headroom, positive incremental NPV and enough additional buyer heat. External evidence gates also apply.",
                "Jede Stufe braucht Netzreserve, einen positiven zusätzlichen Kapitalwert und ausreichend zusätzliche Wärme. Externe Nachweise sind ebenfalls erforderlich."))
        gates(run)
        steps = pd.DataFrame(run.investments).set_index("modules")
        values = steps["heat_15y_NPV_MEUR"]
        fig = go.Figure(go.Bar(
            x=[str(i) for i in steps.index], y=values,
            marker_color=[TEAL if value >= 0 else ORANGE for value in values],
            hovertemplate="%{y:+.3f} €m<extra></extra>",
        ))
        fig.update_xaxes(type="category")
        chart(fig, tr("15-year heat NPV [€m]", "Kapitalwert Wärme über 15 Jahre [Mio. €]"),
              tr("Installed heat modules", "Installierte Wärmemodule"), height=320)
        step_labels = {
            "delivered_heat_GWhth": tr("Delivered [GWhth/yr]", "Geliefert [GWhth/Jahr]"),
            "backup_heat_GWhth": tr("Backup [GWhth/yr]", "Ersatz [GWhth/Jahr]"),
            "capex_heat_MEUR": tr("Heat capex [€m]", "Investition [Mio. €]"),
            "heat_15y_NPV_MEUR": tr("Heat NPV [€m]", "Kapitalwert [Mio. €]"),
            "heat_break_even_EUR_MWh": tr("Tariff floor [€/MWhth]", "Mindestpreis [€/MWhth]"),
            "heat_payback_years": tr("Payback [yr]", "Amortisation [Jahre]"),
        }
        displayed = steps[list(step_labels)].rename_axis(tr("Modules", "Module")).copy()
        for key in ("heat_break_even_EUR_MWh", "heat_payback_years"):
            displayed[key] = displayed[key].map(fmt)
        table(displayed, hide_index=False, labels=step_labels)
        trade = installed_tradeoff(run)
        st.caption(tr("The operator DCF excludes buyer backup costs. Use the installed-equipment comparison on Heat dispatch for the buyer trade-off.",
                      "Der Betreiber-Cashflow enthält keine Ersatzwärmekosten. Der Betriebsvergleich zeigt den Zielkonflikt."))
        if (trade["erasing_penalty_EUR_MWh"] or 0) > 0:
            penalty = st.number_input(tr("Illustrative buyer backup penalty [€/MWhth]", "Exemplarischer Ersatzwärmepreis [€/MWhth]"),
                                      min_value=0., max_value=1000., value=0.)
            net = trade["operator_delta_MEUR"] - penalty * trade["backup_delta_GWhth"] * ANNUITY / 1000
            st.write(f"{tr('Coordinated advantage after illustrative penalty', 'Koordinierter Vorteil nach exemplarischen Ersatzkosten')} {fmt(net, 3, True)} €m")
    with finance:
        cashflows(run)
    with lab:
        sensitivity(run)
