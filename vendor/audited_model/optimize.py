"""Reproducible annual screening of an Austrian AI campus and its heat contract."""
import argparse
import csv
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import legacy_engine as legacy


@dataclass(frozen=True)
class Inputs:
    site: str = "Vienna"
    it_mw: float = 75
    grid_mw: float = 100
    pv_mwp: float = 2
    pv_fraction: float = 1
    price_multiplier: float = 1
    carbon_g: float = 123
    heat_scale: float = 1
    cop: float = 0
    heat_tariff: float = 85
    pipe_km: float = 1
    pipe_cost_per_km_m: float = 2
    nonpipe_stage_one_m: float = 10
    stage_two_m: float = 6
    hot_delta_c: float = 0
    heat_outage_hours: int = 0
    peak_restriction_mw: float = 0
    expensive_hours: int = 0
    minimum_increment_gwh: float = 5
    gas_residual_t_mwh: float = .202 / .90
    hydro_mw: float = 20
    hydro_fraction: float = 1
    wind_mw: float = 30
    wind_fraction: float = 1
    hardware_efficiency_ratio: float = 1.7
    hardware_footprint_kg: float = 2274
    replacement_horizon_years: float = 3
    module_mw: float = 5


MONTHLY = np.array([t.month for t in legacy.CLOCK])
GRAZ_SOLAR = np.array([71.1, 82.8, 114, 121.7, 123, 125.3, 133.2, 126.9, 110.9, 95.7, 61.8, 59.4])
ANNUITY = (1 - 1.06**-15) / .06
HOURS = np.arange(8760)


def source_inputs(a, observed=None):
    if min(a.it_mw, a.grid_mw, a.heat_tariff, a.module_mw) <= 0 or min(a.pv_mwp, a.heat_scale, a.carbon_g, a.pipe_km, a.pv_fraction, a.hydro_fraction, a.wind_fraction) < 0:
        raise ValueError("Use positive power, module size and tariff, and nonnegative capacity, demand, resource and factor inputs.")
    if a.cop and a.cop <= 1 or a.hardware_efficiency_ratio <= 1:
        raise ValueError("COP and the equivalent-work efficiency ratio must exceed one.")
    x = legacy.input_data(observed)
    if a.site == "Graz" and not observed:
        x["pv_MWh_per_MWp"] *= (GRAZ_SOLAR / np.asarray(legacy.MONTHLY_PV))[MONTHLY - 1]
    x["temp_C"] += a.hot_delta_c * np.isin(MONTHLY, [6, 7, 8])
    x["import_price_EUR_MWh"] *= a.price_multiplier
    if not observed:
        x["grid_tCO2e_MWh"][:] = a.carbon_g / 1000
    x["customer_demand_MWth"] *= a.heat_scale
    first_winter = (MONTHLY == 1) | (MONTHLY == 2) | (MONTHLY == 12)
    outage = np.flatnonzero(first_winter)[:a.heat_outage_hours]
    x["customer_acceptance_MWth"] = x["customer_demand_MWth"].copy()
    x["customer_acceptance_MWth"][outage] = 0
    high = np.argsort(np.where(first_winter, x["import_price_EUR_MWh"], -np.inf))
    if a.expensive_hours:
        x["import_price_EUR_MWh"][high[-a.expensive_hours:]] += 240
    return x


def evaluate(a, x, reference, modules, coordinated=False):
    conventional = reference == "A"
    scenario = "S1" if conventional else "S2"
    facility_hw = 1.30 if conventional else 1.24
    pv_mwp = 0 if conventional else a.pv_mwp * a.pv_fraction
    _, h, _ = legacy.run(x, scenario=scenario, mw=a.it_mw, pv=pv_mwp)
    solar, facility, it = h["pv_MW"], h["facility_MW"], h["it_MW"]
    # A temperature sensitivity in addition to the calibrated PUE shape.
    hot_penalty = .002 * it * np.maximum(x["temp_C"] - 28, 0)
    facility = facility + hot_penalty
    demand = x["customer_demand_MWth"]
    acceptance = x["customer_acceptance_MWth"]
    cop = np.full(8760, a.cop) if a.cop else np.clip(4.1 + .035 * (x["temp_C"] - 10), 3, 5)
    target = np.minimum.reduce([np.full(8760, modules * a.module_mw), acceptance / .95, .80 * it / (1 - 1 / cop)])
    electric_per_heat = 1 / cop + .01
    if a.grid_mw + 1e-9 < a.it_mw * facility_hw + modules * a.module_mw * (1 / 3 + .01):
        nameplate_ok = False
    else:
        nameplate_ok = True
    headroom = np.full(8760, a.grid_mw)
    headroom[np.isin(MONTHLY, [1, 2, 12])] -= a.peak_restriction_mw
    pre_heat = facility - solar
    feasible_thermal = np.minimum(target, np.maximum(0, headroom - pre_heat) / electric_per_heat)
    price, intensity = x["import_price_EUR_MWh"], x["grid_tCO2e_MWh"]
    economic = .95 * a.heat_tariff >= electric_per_heat * price
    beats_customer = electric_per_heat * intensity <= .95 * a.gas_residual_t_mwh
    decision = economic & beats_customer if coordinated else np.ones(8760, dtype=bool)
    heat = feasible_thermal * decision
    extracted, delivered = heat * (1 - 1 / cop), .95 * heat
    plant = heat * electric_per_heat
    grid = np.maximum(0, pre_heat + plant)
    exported = np.maximum(0, -(pre_heat + plant))
    customer_backup = demand - delivered
    assert (customer_backup > -1e-9).all()
    assert (extracted <= .80 * it + 1e-9).all()
    assert np.max(np.abs(grid + solar - facility - plant - exported)) < 1e-8
    assert np.max(np.abs(extracted + heat / cop - delivered - .05 * heat)) < 1e-8
    assert np.max(np.abs(delivered + customer_backup - demand)) < 1e-8
    electricity_violation = float(np.maximum(0, grid - headroom).max())
    capex = ((a.nonpipe_stage_one_m + a.pipe_km * a.pipe_cost_per_km_m) if modules else 0) + a.stage_two_m * max(0, modules - 1)
    fixed_heat_om = (.30 + .15 * (modules - 1)) if modules else 0
    heat_bill = plant @ price / 1e6
    heat_mwh = delivered.sum()
    heat_revenue = heat_mwh * a.heat_tariff / 1e6
    margin = heat_revenue - heat_bill - fixed_heat_om
    npv = margin * ANNUITY - capex
    import_bill = (grid @ price - exported @ (price * .5)) / 1e6
    pkg = (8 * a.it_mw / 75 + .90 * a.pv_mwp) if not conventional else 0
    fixed_site_om = (8 * a.it_mw / 75 * .015 + .90 * a.pv_mwp * .012) if not conventional else 0
    residual_grid = grid
    if conventional:
        hydro = wind = np.zeros(8760)
    else:
        # Illustrative generation shapes, with no guarantees of origin or contractual claim.
        hydro = a.hydro_mw * a.hydro_fraction * (.72 + .19 * np.cos(2 * np.pi * (HOURS / 24 - 170) / 365))
        wind = a.wind_mw * a.wind_fraction * (.29 + .085 * np.cos(2 * np.pi * HOURS / 8760) + .11 * np.sin(2 * np.pi * HOURS / 157))
    matched = np.minimum(residual_grid, hydro + wind)
    zero_capex_thermal = modules == 0
    old_energy = 5.6 * .60 * 1.21 * 8760
    saved_board_kwh = old_energy * (1 - 1 / a.hardware_efficiency_ratio)
    carbon_saving = saved_board_kwh / 1000 * np.average(intensity, weights=it)
    board_payback_years = (a.hardware_footprint_kg / 1000 / carbon_saving) if carbon_saving > 0 else None
    result = dict(reference=reference, modules=modules, IT_MW=a.it_mw, connection_MW=a.grid_mw, nameplate_feasible=nameplate_ok,
                  hourly_grid_excess_MW=electricity_violation, combined_peak_MW=grid.max(), IT_GWh=it.sum()/1000,
                  facility_GWh=facility.sum()/1000, grid_GWh=grid.sum()/1000, PV_GWh=solar.sum()/1000,
                  illustrative_offsite_generation_GWh=(wind + hydro).sum()/1000,
                  annual_renewable_matching_pct=100*(solar.sum()-exported.sum()+wind.sum()+hydro.sum())/(facility + plant).sum(),
                  hourly_renewable_matching_pct=100*(solar.sum()-exported.sum()+matched.sum())/(facility + plant).sum(),
                  wholly_matched_hours=int(np.sum(grid <= matched + 1e-9)), PUE=facility.sum()/it.sum(),
                  water_input_m3=it.sum()*.03, WUE_L_per_kWh_IT=.03,
                  exported_source_heat_GWhth=extracted.sum()/1000, proxy_ERF_pct=100*extracted.sum()/facility.sum(),
                  delivered_heat_GWhth=heat_mwh/1000, demand_heat_GWhth=demand.sum()/1000, backup_heat_GWhth=customer_backup.sum()/1000,
                  curtailment_GWhth=.95*(target-heat).sum()/1000, heat_system_GWh=plant.sum()/1000,
                  effective_delivery_COP=heat_mwh/plant.sum() if plant.sum() else 0,
                  grid_direct_ktCO2e=grid@intensity/1000, heat_system_direct_ktCO2e=plant@intensity/1000,
                  gross_avoided_gas_ktCO2e=heat_mwh*a.gas_residual_t_mwh/1000,
                  combined_gas_comparator_ktCO2e=(grid@intensity + customer_backup.sum()*a.gas_residual_t_mwh)/1000,
                  capex_heat_MEUR=capex, capex_intervention_MEUR=capex+pkg, annual_OPEX_net_MEUR=import_bill+fixed_heat_om+fixed_site_om-heat_revenue,
                  heat_15y_NPV_MEUR=npv, heat_break_even_EUR_MWh=(capex/ANNUITY+fixed_heat_om+heat_bill)*1e6/heat_mwh if heat_mwh else None,
                  heat_payback_years=capex/margin if margin>0 and not zero_capex_thermal else None,
                  discounted_intervention_cost_MEUR=capex+pkg+ANNUITY*(import_bill+fixed_heat_om+fixed_site_om-heat_revenue),
                  component_carbon_payback_years=board_payback_years,
                  component_screen="Benchmark replacement candidate" if board_payback_years is not None and board_payback_years <= a.replacement_horizon_years else "Retain or redeploy subject to service qualification")
    series = dict(ambient_C=x["temp_C"], IT_MW=it, facility_MW=facility, pv_MW=solar, grid_MW=grid,
                  grid_export_MW=exported, grid_limit_MW=headroom,
                  required_heat_MWth=demand, accepted_heat_MWth=acceptance, condenser_MWth=heat, source_MWth=extracted, heat_plant_MW=plant,
                  delivered_MWth=delivered, backup_MWth=customer_backup, power_price_EUR_MWh=price, carbon_t_MWh=intensity,
                  matched_offsite_MW=matched, rejected_IT_MWth=it-extracted,
                  unconstrained_accepted_MWth=target, grid_limited_MWth=feasible_thermal,
                  positive_variable_margin=economic.astype(int), beats_customer_carbon=beats_customer.astype(int))
    return result, series


def compare(a, measured=None):
    x = source_inputs(a, measured)
    a_row, _ = evaluate(a, x, "A", 0)
    b_row, _ = evaluate(a, x, "B", 0)
    c_choices = [evaluate(a, x, "C", n)[0] for n in range(3)]
    d_choices = [evaluate(a, x, "D", n, True) for n in range(3)]
    # Independent procurement sizes heat for its own modelled cash flow without a
    # carbon dispatch rule or contractual grid guard. The chosen plant still trips on the live limit.
    standalone = replace(a, grid_mw=1e4, peak_restriction_mw=0)
    nominated = max(range(3), key=lambda n: evaluate(standalone, x, "C", n)[0]["heat_15y_NPV_MEUR"])
    c_row = c_choices[nominated]
    d_scenarios = [pair[0] for pair in d_choices]
    selected = 0
    for index in (1, 2):
        r, prev = d_scenarios[index], d_scenarios[index - 1]
        if r["nameplate_feasible"] and r["hourly_grid_excess_MW"] <= 1e-9 and r["heat_15y_NPV_MEUR"] > prev["heat_15y_NPV_MEUR"] and r["delivered_heat_GWhth"] - prev["delivered_heat_GWhth"] >= a.minimum_increment_gwh:
            selected = index
        else:
            break
    d_row, detailed = d_choices[selected]
    ablation, _ = evaluate(a, x, "Same modules without coordination", selected)
    incremental_stage_two = dict(
        second_stage_incremental_heat_GWhth=d_scenarios[2]["delivered_heat_GWhth"]-d_scenarios[1]["delivered_heat_GWhth"],
        second_stage_incremental_NPV_MEUR=d_scenarios[2]["heat_15y_NPV_MEUR"]-d_scenarios[1]["heat_15y_NPV_MEUR"])
    assert max(row["IT_GWh"] for row in (a_row,b_row,c_row,d_row))-min(row["IT_GWh"] for row in (a_row,b_row,c_row,d_row)) < 1e-9
    return [a_row,b_row,c_row,d_row], detailed, d_scenarios, ablation, incremental_stage_two


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--site", choices=["Vienna", "Linz", "Graz"], default="Vienna")
    p.add_argument("--out", default="results")
    p.add_argument("--hourly-inputs")
    for k in ("it_mw","grid_mw","pv_mwp","price_multiplier","carbon_g","heat_scale","cop","heat_tariff","pipe_km",
              "pipe_cost_per_km_m","module_mw","hardware_efficiency_ratio","hardware_footprint_kg","replacement_horizon_years"):
        p.add_argument("--"+k.replace("_","-"), type=float, default=getattr(Inputs(),k))
    a = p.parse_args()
    target = Path(a.out)
    target.mkdir(parents=True, exist_ok=True)
    base = Inputs(**{k:v for k,v in vars(a).items() if k not in ("hourly_inputs","out")})
    scenarios, trace, stages, ablation, increment = compare(base, a.hourly_inputs)
    write_csv(target/"scenario_results.csv",scenarios)
    write_csv(target/"investment_steps.csv",stages)
    cases = {
        "Base": base,
        "Low renewable year": replace(base,pv_fraction=.75,hydro_fraction=.65,wind_fraction=.8,carbon_g=180),
        "High winter price": replace(base,expensive_hours=320),
        "High summer temperature": replace(base,hot_delta_c=5),
        "Winter import cap 63 MW": replace(base,peak_restriction_mw=max(0,base.grid_mw-63)),
        "Grid delay or 90 MW firm": replace(base,grid_mw=90),
        "Half heat demand": replace(base,heat_scale=.5),
        "Heat buyer outage 336 h": replace(base,heat_outage_hours=336),
        "Electricity +30%": replace(base,price_multiplier=1.3),
        "Pipe route 3 km": replace(base,pipe_km=3),
        "Civil cost +30%": replace(base,nonpipe_stage_one_m=base.nonpipe_stage_one_m*1.30,pipe_cost_per_km_m=base.pipe_cost_per_km_m*1.30),
        "Low delivered tariff": replace(base,heat_tariff=65),
        "COP 3": replace(base,cop=3),
        "High import carbon / low-carbon DH counterfactual": replace(base,carbon_g=550,gas_residual_t_mwh=.080),
        "Graz solar proxy": replace(base,site="Graz"),
        "Linz uncalibrated solar proxy": replace(base,site="Linz"),
        "50 MW IT initial phase": replace(base,it_mw=50,grid_mw=75),
        "100 MW IT test above facility limit": replace(base,it_mw=100,grid_mw=100),
        "10 MWp ground PV sensitivity": replace(base,pv_mwp=10),
        "Efficient heat pump customer": replace(base,gas_residual_t_mwh=.123/3),
        "Stress combination": replace(base,expensive_hours=320,carbon_g=220,peak_restriction_mw=max(0,base.grid_mw-62)),
    }
    rows=[]
    for name, variant in cases.items():
        result, _, investments, fixed, step = compare(variant, a.hourly_inputs)
        c, d = result[2], result[3]
        one = investments[1]
        live_x = source_inputs(variant,a.hourly_inputs)
        pilot_coordinated, _ = evaluate(variant,live_x,"D",1,True)
        pilot_fixed, _ = evaluate(variant,live_x,"C",1)
        private_delta = pilot_coordinated["heat_15y_NPV_MEUR"] - pilot_fixed["heat_15y_NPV_MEUR"]
        extra_backup = pilot_coordinated["backup_heat_GWhth"] - pilot_fixed["backup_heat_GWhth"]
        break_even_backup = private_delta * 1000 / (ANNUITY * extra_backup) if extra_backup > 1e-9 else None
        rows.append(dict(case=name,C_modules=c["modules"],D_modules=d["modules"],D_nameplate_feasible=d["nameplate_feasible"],
                         D_grid_excess_MW=d["hourly_grid_excess_MW"],D_grid_GWh=d["grid_GWh"],D_PV_GWh=d["PV_GWh"],
                         D_delivered_GWhth=d["delivered_heat_GWhth"],D_hourly_renewables_pct=d["hourly_renewable_matching_pct"],
                         one_module_heat_GWhth=one["delivered_heat_GWhth"],one_module_NPV_MEUR=one["heat_15y_NPV_MEUR"],
                         one_module_break_even_EUR_MWh=one["heat_break_even_EUR_MWh"],operating_ablation_D_minus_fixed_MEUR=d["heat_15y_NPV_MEUR"]-fixed["heat_15y_NPV_MEUR"],
                         installed_pilot_dispatch_delta_NPV_MEUR=private_delta,
                         installed_pilot_heat_delta_GWhth=pilot_coordinated["delivered_heat_GWhth"]-pilot_fixed["delivered_heat_GWhth"],
                         installed_pilot_combined_delta_ktCO2e=pilot_coordinated["combined_gas_comparator_ktCO2e"]-pilot_fixed["combined_gas_comparator_ktCO2e"],
                         backup_penalty_erasing_private_gain_EUR_MWh=break_even_backup,
                         one_module_required_heat_GWhth=one["demand_heat_GWhth"],one_module_backup_GWhth=one["backup_heat_GWhth"],**step))
    write_csv(target/"stress_tests.csv",rows)
    with (target/"hourly_D.csv").open("w",encoding="utf-8",newline="") as stream:
        writer=csv.writer(stream)
        writer.writerow(["fixed_CET",*trace])
        writer.writerows((t.isoformat(),*(v[i] for v in trace.values())) for i,t in enumerate(legacy.CLOCK))
    for s in scenarios:
        print(f'{s["reference"]}: {s["grid_GWh"]:.2f} GWh grid, {s["delivered_heat_GWhth"]:.2f} GWhth delivered, {s["modules"]} heat modules, heat NPV €{s["heat_15y_NPV_MEUR"]:.3f}m')
    print(f"First module tariff floor €{stages[1]['heat_break_even_EUR_MWh']:.2f}/MWh. Stage 2 {increment}.")


if __name__ == "__main__":
    main()
