"""Landing dashboard and guided jury story."""
from html import escape

import streamlit as st

from .config import DEFAULT, Settings
from .engineering import buyer_monthly, installed_comparison
from .investment import gates
from .model import comparator, nameplate, simulate
from .ui import activate_preset, baseline, fmt, metrics, navigate, note, option_labels, top_context, tr


def hero():
    details = (
        (tr("Initial IT stage", "Erste IT-Stufe"), "50 MW"),
        (tr("Full-build IT", "IT-Vollausbau"), "75 MW"),
        (tr("Proposed connection", "Vorgeschlagener Netzanschluss"), "100 MW"),
        (tr("First heat module", "Erstes Wärmemodul"), "5 MWth"),
    )
    rows = "".join(f'<div class="tc-brief-row"><span>{escape(label)}</span><strong>{value}</strong></div>'
                   for label, value in details)
    intro = tr("An Austrian AI data centre concept with independent cooling, staged heat recovery and hourly analysis.",
               "Ein österreichisches KI-Rechenzentrum mit unabhängiger Kühlung, gestufter Wärmenutzung und Stundenanalyse.")
    st.html(f"""<section class="tc-hero">
        <div><div class="tc-kicker">INFINEON INNOSCOPE 2026 / TU WIEN</div>
        <h1>ThermoCircular<br><span>AI Campus</span></h1><p>{escape(intro)}</p></div>
        <div class="tc-brief"><p>{escape(tr("REFERENCE DESIGN", "REFERENZENTWURF"))}</p>{rows}</div>
    </section>""")


def kpis(run):
    r = run.d
    b = comparator(run.traces["B"], "Gas boiler", run.settings.gas_residual_t_mwh)
    d = comparator(run.traces["D"], "Gas boiler", run.settings.gas_residual_t_mwh)
    delta = d["combined_ktCO2e"] - b["combined_ktCO2e"]
    metrics([
        ("Delivered heat", f"{fmt(r['delivered_heat_GWhth'])} GWhth", tr("Annual useful heat at buyer meter, case D.", "Jährliche Nutzwärme am Abnahmezähler, Fall D.")),
        ("Grid imports", f"{fmt(r['grid_GWh'])} GWh", tr("Annual physical campus imports, case D.", "Jährlicher physischer Netzbezug, Fall D.")),
        ("Heat-project NPV", f"{fmt(r['heat_15y_NPV_MEUR'], 2, True)} €m", tr("15-year operator NPV at 6%, case D.", "Betreiber-Kapitalwert über 15 Jahre bei 6 %, Fall D.")),
    ])
    metrics([
        ("Annual IT electricity", f"{fmt(r['IT_GWh'], 1)} GWh", tr("A–D use the same IT workload.", "A–D nutzen dieselbe IT-Last.")),
        (tr("Joint emissions Δ", "Gemeinsame Emissionen Δ"), f"{fmt(delta, 2, True)} ktCO₂e", tr("D minus B, including buyer backup fuel at the scenario factor, per year.", "D minus B mit Ersatzbrennstoff des Abnehmers gemäß Szenario, pro Jahr.")),
        ("Hourly matching", f"{fmt(r['hourly_renewable_matching_pct'])}%", tr("Illustrative hourly coverage, case D, whole year.", "Exemplarische stündliche Deckung, Fall D, gesamtes Jahr.")),
    ])


def architecture(run):
    st.subheader(tr("From grid connection to buyer meter", "Vom Netzanschluss zum Abnahmezähler"))
    flows = (
        ("electric", tr("Electricity [MW]", "Strom [MW]"),
         (tr("Grid + PV", "Netz + PV"), tr("IT / cooling + heat plant", "IT / Kühlung + Wärmeanlage"))),
        ("thermal", tr("Heat [MWth]", "Wärme [MWth]"),
         (tr("IT loop", "IT-Kreislauf"), tr("Heat pump", "Wärmepumpe"), tr("Buyer meter", "Abnahmezähler"))),
        ("thermal", tr("Fallback [MWth]", "Rückfall [MWth]"),
         (tr("IT loop", "IT-Kreislauf"), tr("Independent rejection", "Unabhängige Wärmeabfuhr"))),
        ("thermal", tr("Backup [MWth]", "Ersatz [MWth]"),
         (tr("Buyer backup", "Ersatzwärme"), tr("Unserved buyer demand", "Ungedeckter Wärmebedarf"))),
    )
    lanes = []
    for kind, label, blocks in flows:
        flow = "<small aria-hidden='true'>→</small>".join(f"<span>{escape(block)}</span>" for block in blocks)
        lanes.append(f'<div class="tc-lane tc-{kind}"><div class="tc-lane-title">{escape(label)}</div>'
                     f'<div class="tc-flow">{flow}</div></div>')
    st.html(f'<div class="tc-system">{"".join(lanes)}</div>')
    blocks = ("Grid & PV", "IT and cooling", "Independent rejection", "Heat pump", "Buyer meter", "Backup")
    labels = ("Netz und PV", "IT und Kühlung", "Unabhängige Wärmeabfuhr", "Wärmepumpe", "Abnahmezähler", "Ersatzwärme")
    selected = st.segmented_control(tr("Select a system block", "Systemblock auswählen"), blocks, default=blocks[0],
                                    format_func=option_labels(blocks, lambda x: tr(x, labels[blocks.index(x)])), key="network_block")
    r, t = run.d, run.traces["D"]
    infos = {
        "Grid & PV": ("Grid imports", f"{fmt(r['grid_GWh'])} GWh", "Power & renewables"),
        "IT and cooling": ("Annual IT electricity", f"{fmt(r['IT_GWh'])} GWh", "Power & renewables"),
        "Independent rejection": (tr("IT heat rejected", "Abgeführte IT-Wärme"), f"{fmt(t.rejected_IT_MWth.sum() / 1000)} GWhth", "Heat dispatch"),
        "Heat pump": (tr("Condenser output", "Kondensatorleistung"), f"{fmt(t.condenser_MWth.sum() / 1000)} GWhth", "Heat dispatch"),
        "Buyer meter": ("Delivered heat", f"{fmt(r['delivered_heat_GWhth'])} GWhth", "Heat dispatch"),
        "Backup": ("Buyer backup", f"{fmt(r['backup_heat_GWhth'])} GWhth", "Heat dispatch"),
    }
    label, val, destination = infos[selected or blocks[0]]
    left, right = st.columns([2, 1], vertical_alignment="bottom")
    left.markdown(f"**{tr(label)}**　{val} · {tr('Case D')} · {tr('annual', 'pro Jahr')}")
    right.button(tr("Open engineering view", "Technische Ansicht öffnen"), on_click=navigate, args=(destination,), width="stretch")


def page(run):
    hero()
    left, right, third = st.columns(3)
    left.button(tr("Open scenario lab", "Szenarien öffnen"), type="primary", on_click=navigate, args=("Scenario lab",), width="stretch")
    right.button(tr("Winter price stress", "Winter-Strompreis"), on_click=activate_preset,
                 args=("High winter price", "Heat dispatch"), width="stretch")
    third.button(tr("Buyer outage", "Abnahmeausfall"), on_click=activate_preset,
                 args=("Heat buyer outage 336 h", "Heat dispatch"), width="stretch")
    st.subheader(tr("Annual performance", "Jahresergebnisse"))
    kpis(run)
    st.caption(tr("Case D · 8,760 fixed-CET hours · engineering screening. Emissions use the current buyer fuel factor as the backup boundary.",
                  "Fall D · 8.760 Stunden in fester MEZ · technische Vorprüfung. Emissionen verwenden den aktuellen Brennstofffaktor für Ersatzwärme."))
    a, b = st.tabs((tr("Buyer heat by month", "Wärmeabnahme nach Monat"), tr("System architecture", "Systemarchitektur")))
    with a:
        buyer_monthly(run)
        diff = run.d["heat_15y_NPV_MEUR"] - run.cases[4]["heat_15y_NPV_MEUR"]
        note(tr("Dispatch and investment", "Betrieb und Investition"),
             tr(f"The same hourly acceptance and limits inform both decisions. Coordination adds {fmt(diff, 3, True)} €m versus "
                "fixed dispatch at matched installed hardware in this run.",
                f"Dieselben stündlichen Abnahme- und Betriebsgrenzen bestimmen beide Entscheidungen. Der Kapitalwertunterschied "
                f"bei gleicher installierter Anlage beträgt {fmt(diff, 3, True)} Mio. €."))
    with b:
        architecture(run)


def shift_step(delta):
    st.session_state["jury_step"] += delta


def jury():
    run = baseline()
    sections = (
        ("Campus", "Campus"), ("Buyer heat", "Wärmeabnahme"), ("Investment", "Investition"),
        ("Winter stress", "Winter-Stresstest"), ("Sustainability", "Nachhaltigkeit"),
        ("Validation gates", "Validierungsstufen"),
    )
    st.session_state.setdefault("jury_step", 0)
    ix = st.session_state["jury_step"]
    top_context(jury_winter() if ix == 3 else run)
    name = tr(*sections[ix])
    st.title(name)
    progress = f"{ix + 1} / {len(sections)}"
    back, center, next_ = st.columns([1, 4, 1], vertical_alignment="center")
    back.button(tr("Previous", "Zurück"), key="jury_prev", disabled=ix == 0, on_click=shift_step, args=(-1,), width="stretch")
    center.caption(progress)
    next_.button(tr("Next", "Weiter"), key="jury_next", type="primary", disabled=ix == len(sections) - 1,
                 on_click=shift_step, args=(1,), width="stretch")
    if ix == 0:
        hero()
        kpis(run)
    elif ix == 1:
        buyer_monthly(run)
        architecture(run)
    elif ix == 2:
        gates(run)
        note(tr("Indicative full-build peak", "Indikative Spitze im Vollausbau"),
             f"{fmt(nameplate(run.settings, run.d['modules']))} MW / {fmt(run.settings.grid_mw, 0)} MW")
    elif ix == 3:
        installed_comparison(jury_winter())
    elif ix == 4:
        from .review import impact_results
        impact_results(run)
    else:
        from .review import roadmap_summary
        roadmap_summary()
    if st.button(tr("Restart pitch at baseline", "Präsentation bei der Referenz neu starten")):
        st.session_state["jury_step"] = 0
        st.rerun()


@st.cache_resource(show_spinner=False)
def jury_winter():
    return simulate(Settings.model_validate({**DEFAULT.model_dump(), "expensive_hours": 320}))
