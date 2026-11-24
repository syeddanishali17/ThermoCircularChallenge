"""Landing dashboard and guided jury story."""
from base64 import b64encode
from html import escape

import streamlit as st

from .config import DEFAULT, Settings
from .engineering import buyer_monthly, installed_comparison
from .investment import gates
from .model import comparator, nameplate, simulate
from .ui import activate_preset, baseline, fmt, navigate, note, option_labels, svg_asset, tr, workspace_bar


def hero():
    details = (
        (tr("Initial IT stage", "Erste IT-Stufe"), "50 MW"),
        (tr("Full-build IT", "IT-Vollausbau"), "75 MW"),
        (tr("Proposed connection", "Vorgeschlagener Netzanschluss"), "100 MW"),
        (tr("First heat module", "Erstes Wärmemodul"), "5 MWth"),
    )
    rows = "".join(f'<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>'
                   for label, value in details)
    intro = tr("Model an Austrian AI data centre with independent cooling and staged heat recovery.",
               "Ein österreichisches KI-Rechenzentrum mit unabhängiger Kühlung und gestufter Wärmenutzung modellieren.")
    paused = st.session_state.get("campus_motion_paused", False)
    source = svg_asset("campus-flow.svg", paused)
    mark = svg_asset("thermocircular-mark.svg")
    alt = tr("Conceptual data centre with server racks, a heat pump, and pipes serving external buildings.",
             "Schematisches Rechenzentrum mit Serverracks, Wärmepumpe und Leitungen zu externen Gebäuden.")
    st.html(f"""<section class="tc-hero">
        <div>
          <div class="tc-hero-brand"><img src="{mark}" alt=""><div class="tc-kicker">INFINEON INNOSCOPE 2026 / TU WIEN</div></div>
          <h1>ThermoCircular<br><span>AI Campus</span></h1><p>{escape(intro)}</p>
        </div>
        <figure class="tc-campus">
          <img src="{source}" alt="{escape(alt)}">
          <figcaption>
            <span class="tc-electric-flow">{escape(tr("Grid power", "Netzstrom"))}</span>
            <span class="tc-heat-flow">{escape(tr("Recovered heat", "Abwärme"))}</span>
            <span class="tc-return-flow">{escape(tr("Cooling return", "Kühlrücklauf"))}</span>
          </figcaption>
        </figure>
        <div class="tc-brief"><p>{escape(tr("Reference design", "Referenzentwurf"))}</p><dl>{rows}</dl></div>
    </section>""")
    with st.container(key="campus_animation_control"):
        st.button(tr("Play campus animation", "Campus-Animation abspielen") if paused
                  else tr("Pause campus animation", "Campus-Animation pausieren"),
                  key="campus_motion", on_click=toggle_campus_motion,
                  help=tr("Illustrative flows in the proposed campus.", "Schematische Flüsse für den geplanten Campus."))


def toggle_campus_motion():
    st.session_state["campus_motion_paused"] = not st.session_state.get("campus_motion_paused", False)


def kpis(run):
    r = run.d
    b = comparator(run.traces["B"], "Gas boiler", run.settings.gas_residual_t_mwh)
    d = comparator(run.traces["D"], "Gas boiler", run.settings.gas_residual_t_mwh)
    delta = d["combined_ktCO2e"] - b["combined_ktCO2e"]
    values = (
        (tr("Delivered heat"), fmt(r["delivered_heat_GWhth"]), "GWhₜₕ/yr",
         tr("At buyer meter", "Am Abnahmezähler"), "heat"),
        (tr("Grid imports"), fmt(r["grid_GWh"]), "GWh/yr",
         tr("Physical campus imports", "Physischer Netzbezug"), "power"),
        (tr("Heat-project NPV"), fmt(r["heat_15y_NPV_MEUR"], 2, True), "€m",
         tr("15 years at 6%", "15 Jahre bei 6 %"), ""),
        (tr("Annual IT electricity"), fmt(r["IT_GWh"], 1), "GWh/yr",
         tr("IT workload", "IT-Last"), "power"),
        (tr("Joint emissions Δ", "Gemeinsame Emissionen Δ"), fmt(delta, 2, True), "ktCO₂e/yr",
         tr("D minus B, with backup", "D minus B, mit Ersatzwärme"), ""),
        (tr("Hourly matching"), fmt(r["hourly_renewable_matching_pct"]), "%",
         tr("Renewable electricity", "Erneuerbarer Strom"), ""),
    )
    cards = []
    for label, value, unit, detail, kind in values:
        cards.append(f'<div class="tc-kpi {kind}"><dt>{escape(label)}</dt>'
                     f'<dd><strong>{escape(value)}</strong> <span>{escape(unit)}</span>'
                     f'<small>{escape(detail)}</small></dd></div>')
    st.html(f'<dl class="tc-kpi-grid">{"".join(cards)}</dl>')


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
    schematic = campus_schematic()
    st.html(f'<figure class="tc-architecture">{schematic}<div class="tc-system">{"".join(lanes)}</div>'
            f'<figcaption>{escape(tr("Conceptual flow. Building and site details are illustrative.", "Konzeptioneller Ablauf. Anlage und Standort sind schematisch dargestellt."))}</figcaption></figure>')
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


def campus_schematic():
    nodes = (
        (18, 52, tr("Grid + PV", "Netz + PV"), "electric"),
        (212, 52, tr("IT and cooling", "IT und Kühlung"), "electric"),
        (406, 52, tr("Heat pump", "Wärmepumpe"), "thermal"),
        (600, 52, tr("Buyer meter", "Abnahmezähler"), "thermal"),
        (212, 151, tr("Heat rejection", "Wärmeabfuhr"), "thermal"),
        (600, 151, tr("Buyer backup", "Ersatzwärme"), "thermal"),
    )
    boxes = "".join(
        f'<g class="{kind}"><rect x="{x}" y="{y}" width="149" height="44" rx="9"/>'
        f'<text x="{x + 74.5}" y="{y + 28}" text-anchor="middle">{escape(label)}</text></g>'
        for x, y, label, kind in nodes
    )
    paths = (
        ("M167 74H210", "electric"), ("M93 51V23H480V50", "electric"),
        ("M361 74H404", "thermal"), ("M555 74H598", "thermal"),
        ("M286 96V149", "thermal"), ("M674 151V98", "thermal"),
    )
    arrows = "".join(
        f'<path d="{path}" class="{kind}" marker-end="url(#tc-arrow-{kind})"/>'
        for path, kind in paths
    )
    label = tr("Conceptual campus energy flows", "Konzeptionelle Energieflüsse des Campus")
    description = tr(
        "Grid and solar power feed IT, cooling and the heat pump. IT heat goes to the heat pump or independent rejection. The heat pump and buyer backup supply the buyer.",
        "Netz und PV versorgen IT, Kühlung und Wärmepumpe. IT-Wärme geht zur Wärmepumpe oder Wärmeabfuhr. Wärmepumpe und Ersatzwärme versorgen den Abnehmer.",
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 767 220" role="img">
      <title>{escape(label)}</title>
      <desc>{escape(description)}</desc>
      <style>
        text {{ font: 650 15px Arial, sans-serif; fill: #13283b; }}
        .electric rect {{ fill: #edf4ff; stroke: #a7c2e5; }}
        .thermal rect {{ fill: #e8f5ef; stroke: #a5cec2; }}
        path.electric {{ stroke: #3263a2; }}
        path.thermal {{ stroke: #0c6b60; }}
        .tc-electric-label {{ fill: #3263a2; }}
        .tc-thermal-label {{ fill: #0c6b60; }}
      </style>
      <defs>
        <marker id="tc-arrow-electric" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0 0L7 3.5L0 7Z" fill="#3263a2"/></marker>
        <marker id="tc-arrow-thermal" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0 0L7 3.5L0 7Z" fill="#0c6b60"/></marker>
      </defs>
      <g class="tc-arrows" fill="none" stroke-width="2.5">{arrows}</g>
      {boxes}
      <text x="18" y="126" class="tc-electric-label">{escape(tr("Electricity [MW]", "Strom [MW]"))}</text>
      <text x="18" y="150" class="tc-thermal-label">{escape(tr("Heat [MWth]", "Wärme [MWth]"))}</text>
    </svg>'''
    image = b64encode(svg.encode()).decode("ascii")
    return f'<img class="tc-schematic" src="data:image/svg+xml;base64,{image}" alt="{escape(description)}">'


def page(run):
    hero()
    with st.container(key="overview_actions"):
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
    workspace_bar(jury_winter() if ix == 3 else run)
    name = tr(*sections[ix])
    with st.container(key="jury_controls"):
        back, center, next_ = st.columns([1, 2, 1], vertical_alignment="center")
        back.button(tr("Previous", "Zurück"), key="jury_prev", disabled=ix == 0,
                    on_click=shift_step, args=(-1,), width="stretch")
        center.progress((ix + 1) / len(sections),
                        text=f"{tr('Jury mode')} · {ix + 1} / {len(sections)}")
        next_.button(tr("Next", "Weiter"), key="jury_next", type="primary", disabled=ix == len(sections) - 1,
                     on_click=shift_step, args=(1,), width="stretch")
    if ix == 0:
        hero()
        kpis(run)
    else:
        st.title(name)
    if ix == 1:
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
    elif ix == 5:
        from .review import jury_gates
        jury_gates()
    if st.button(tr("Restart pitch at baseline", "Präsentation bei der Referenz neu starten")):
        st.session_state["jury_step"] = 0
        st.rerun()


@st.cache_resource(show_spinner=False)
def jury_winter():
    return simulate(Settings.model_validate({**DEFAULT.model_dump(), "expensive_hours": 320}))
