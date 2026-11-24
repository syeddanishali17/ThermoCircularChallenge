"""Independent checks against the earlier research and new equal-service outputs."""
import argparse
import csv
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import legacy_engine


def table(path):
    with path.open(encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--archive", type=Path, help="Original InnoScope_Research_2026.zip, for archive CRC and version checks.")
p.add_argument("--results", default=Path(__file__).resolve().parent/"results", type=Path)
a = p.parse_args()
if a.archive:
    with ZipFile(a.archive) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert sum(name.endswith(".docx") for name in names) >= 9
        assert any(name.endswith("/D9_Comparative_Evaluation_Validation_Roadmap.docx") for name in names)
        assert any(name.endswith("/Model/hourly_inputs.csv") for name in names)
        print("Prior archive contains", len(names), "verified member files.")

baseline = legacy_engine.drivers()
one, _, _ = legacy_engine.run(baseline, heat_cap=5, capex=12, heat_fixed_om=.30)
two, _, _ = legacy_engine.run(baseline)
no_heat, _, _ = legacy_engine.run(baseline, scenario="S2")
for label,value,want in (
    ("legacy 5 MW customer MWh/1000",one["heat_delivered_GWhth"],27.62711027339302),
    ("legacy 10 MW customer MWh/1000",two["heat_delivered_GWhth"],37.802542270241176),
    ("legacy 10 MW combined grid delta",two["grid_GWh"]-no_heat["grid_GWh"],2.614482038962379),
    ("legacy resistance combined saving",two["heat_delivered_GWhth"]-(two["grid_GWh"]-no_heat["grid_GWh"]),35.1880602312788),
):
    assert abs(value-want)<1e-6, (label,value,want)
    print(f"{label}: {value:.6f}")

rows = table(a.results/"hourly_D.csv")
assert len(rows)==8760 and len({r["fixed_CET"] for r in rows})==8760
v = {key: np.array([float(r[key]) for r in rows]) for key in rows[0] if key!="fixed_CET"}
expected_delivery = v["condenser_MWth"] * .95
assert np.allclose(expected_delivery,v["delivered_MWth"])
assert np.allclose(v["backup_MWth"] + expected_delivery,v["required_heat_MWth"])
assert np.all(expected_delivery <= v["accepted_heat_MWth"] + 1e-9)
compressor = v["heat_plant_MW"] - .01 * v["condenser_MWth"]
assert np.allclose(v["source_MWth"] + compressor,v["condenser_MWth"])
assert np.allclose(v["rejected_IT_MWth"] + v["source_MWth"],v["IT_MW"])
assert np.allclose(v["grid_MW"]+v["pv_MW"],v["facility_MW"]+v["heat_plant_MW"]+v["grid_export_MW"])
assert np.all(v["grid_MW"] <= v["grid_limit_MW"] + 1e-9)
summary = {row["reference"]:row for row in table(a.results/"scenario_results.csv")}
stages = table(a.results/"investment_steps.csv")
npv = (expected_delivery.sum()*85 - v["heat_plant_MW"]@v["power_price_EUR_MWh"] - 300000)/1e6*sum(1.06**-i for i in range(1,16))-12
assert np.isclose(npv,float(summary["D"]["heat_15y_NPV_MEUR"]))
assert np.isclose(v["grid_MW"].sum()/1000,float(summary["D"]["grid_GWh"]))
assert np.isclose(expected_delivery.sum()/1000,float(summary["D"]["delivered_heat_GWhth"]))
saved = 5.6 * .60 * 1.21 * 8760 * (1-1/1.7)
assert np.isclose(2274/(saved*.123),float(summary["D"]["component_carbon_payback_years"]))
assert np.isclose(2274/(saved*.053),2.9257466625723152)
assert len({r["IT_GWh"] for r in summary.values()}) == 1
assert np.isclose(float(stages[2]["heat_15y_NPV_MEUR"])-npv,-2.0096523504648065)
tests = {r["case"]:r for r in table(a.results/"stress_tests.csv")}
assert tests["Heat buyer outage 336 h"]["D_modules"] == "0"
assert tests["Pipe route 3 km"]["D_modules"] == "0"
assert tests["Grid delay or 90 MW firm"]["D_nameplate_feasible"] == "False"
assert float(tests["High winter price"]["installed_pilot_dispatch_delta_NPV_MEUR"]) > 0
assert float(tests["Base"]["installed_pilot_dispatch_delta_NPV_MEUR"]) == 0
assert np.isclose(float(tests["High winter price"]["installed_pilot_combined_delta_ktCO2e"]),.2880850451)
assert np.isclose(float(tests["High winter price"]["backup_penalty_erasing_private_gain_EUR_MWh"]),26.79695732)
outage=tests["Heat buyer outage 336 h"]
assert np.isclose(float(outage["one_module_required_heat_GWhth"]),float(tests["Base"]["one_module_required_heat_GWhth"]))
assert np.isclose(float(outage["one_module_required_heat_GWhth"]),float(outage["one_module_backup_GWhth"])+float(outage["one_module_heat_GWhth"]))
print(f"New model: 8760 ordered unique hours, four equal-compute references, independently checked heat balance, NPV {npv:.6f} million, import, fixed-hardware ablation and component payback.")
