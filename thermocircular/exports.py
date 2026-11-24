"""Portable exports for the current successful run."""
from html import escape
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from .model import LIMITATIONS, comparator, installed_tradeoff, monthly
from .storage import recipe


def safe_table(frame):
    clean = frame.copy()
    for name in clean.select_dtypes(include=["object", "string"]).columns:
        clean[name] = clean[name].map(
            lambda x: "'" + x if isinstance(x, str) and x.lstrip().startswith(("=", "+", "-", "@")) else x
        )
    return clean


def csv_bytes(frame, index=False):
    return safe_table(frame).to_csv(index=index, lineterminator="\n").encode("utf-8")


def config_bytes(run):
    return (json.dumps(recipe(run), allow_nan=False, indent=2) + "\n").encode("utf-8")


def tables(run, stress=None):
    comp = pd.DataFrame([
        {"case": case, **comparator(run.traces[case], buyer)}
        for case in ("A", "B", "C", "D")
        for buyer in ("Gas boiler", "Resistance heat", "Electric heat pump (COP 3)")
    ])
    output = {
        "Run metadata": pd.DataFrame(run.metadata().items(), columns=["Item", "Value"]),
        "Inputs": pd.DataFrame(run.settings.model_dump().items(), columns=["Input", "Value"]),
        "Annual scenarios": pd.DataFrame(run.cases),
        "Monthly D": monthly(run.traces["D"]).reset_index(),
        "Investment": pd.DataFrame(run.investments),
        "Stage increment": pd.DataFrame([run.increment]),
        "Installed equipment": pd.DataFrame(run.fixed),
        "Dispatch tradeoffs": pd.DataFrame([installed_tradeoff(run)]),
        "Buyer comparisons": comp,
        "Limitations": pd.DataFrame({"Boundary": LIMITATIONS}),
    }
    if stress is not None:
        output["Stress suite"] = stress
    return output


def workbook_bytes(run, stress=None):
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        for name, frame in tables(run, stress).items():
            safe_table(frame).to_excel(writer, sheet_name=name, index=False)
            sheet = writer.sheets[name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                width = max(len(str(cell.value)) for cell in column)
                sheet.column_dimensions[column[0].column_letter].width = min(62, max(15, width + 2))
    return stream.getvalue()


def hourly_zip(run):
    stream = BytesIO()
    names = ("A", "B", "C", "D", "Same modules without coordination", "Installed coordinated", "Installed fixed")
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("scenario.json", config_bytes(run))
        for name in names:
            archive.writestr(f"hourly_{name.lower().replace(' ', '_')}.csv", csv_bytes(run.traces[name], index=True))
    return stream.getvalue()


def html_bytes(run, stress=None):
    output = tables(run, stress)
    metadata = run.metadata()
    d = run.d
    narrative = (
        f"Case D screens {d['modules']} thermal module(s) on the {run.settings.site} scenario, "
        f"with {d['delivered_heat_GWhth']:.2f} GWhth/year delivered and heat-project NPV "
        f"of €{d['heat_15y_NPV_MEUR']:.3f} million over 15 years."
    )
    electrical = output["Annual scenarios"][[
        "reference", "IT_GWh", "grid_GWh", "PUE", "combined_peak_MW", "nameplate_feasible", "hourly_grid_excess_MW",
    ]]
    thermal = output["Annual scenarios"][[
        "reference", "modules", "delivered_heat_GWhth", "backup_heat_GWhth", "heat_15y_NPV_MEUR",
        "heat_break_even_EUR_MWh", "hourly_renewable_matching_pct",
    ]]
    selected = {
        "Technical concept | power and feasibility": electrical,
        "Economics and buyer heat | annual": thermal,
        "Investment | second-stage increment": output["Stage increment"],
        "Sustainability | equal-service heating comparators": output["Buyer comparisons"],
        "Implementation and risks | scope and limitations": output["Limitations"],
        "Reproducibility | inputs": output["Inputs"],
        "Reproducibility | input manifest": output["Run metadata"],
    }
    if stress is not None:
        selected["Stress results | current input overrides"] = stress
    sections = []
    for title, frame in selected.items():
        table = frame.to_html(index=False, escape=True, float_format=lambda x: f"{x:.4f}", na_rep="N/A")
        sections.append(f"<h2>{escape(title)}</h2><div class='scroll'>{table}</div>")
    rendered = "".join(sections)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ThermoCircular {escape(run.id)}</title>
<style>
body{{font:16px/1.5 system-ui;color:#132b3d;margin:5vw auto;max-width:1150px;padding:0 16px}}
h1,h2{{line-height:1.15}} h1{{font-size:3rem;margin-bottom:.4rem}}
header{{border-bottom:4px solid #126f70;padding-bottom:15px}} th{{background:#eaf2f3}}
td,th{{padding:6px 10px;text-align:left;border-bottom:1px solid #dae4e8}}
table{{border-collapse:collapse;min-width:55%}} .scroll{{overflow:auto}}
</style>
<header><p>InnoScope 2026 · Engineering screening</p><h1>ThermoCircular AI Campus</h1>
<p>{escape(metadata['mode'])} · {escape(run.id)} · {escape(metadata['input_evidence'])}</p></header>
<h2>Management summary</h2><p>{escape(narrative)}</p>
<p>Connection, buyer, tariff and route require external validation. The optional 2035 challenge task remains unclaimed.</p>
{rendered}</html>""".encode("utf-8")
