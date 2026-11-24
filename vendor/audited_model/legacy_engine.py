"""Vienna heat reuse screening model. Python 3.10+ and numpy. Run in this directory."""
import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
HOURS = 8760
SCENARIOS = {
    'S1': (1.21, 0.08, 0.03, 1.30),
    'S2': (1.16, 0.065, 0.03, 1.24),
    'S3': (1.14, 0.06, 0.03, 1.20),
}
MONTHLY_TEMP = [0.8, 2.3, 6.1, 11.3, 15.8, 19.6, 21.4, 20.9, 15.7, 10.5, 5.8, 1.5]
MONTHLY_PV = [49.7, 70.8, 106.9, 128.5, 129.8, 132.6, 137.7, 129.3, 113.2, 84.5, 49.7, 43.6]
ANNUITY = (1 - (1.06 ** -15)) / 0.06
CLOCK = [datetime(2025,1,1) + timedelta(hours=h) for h in range(HOURS)]

def write_rows(filename, rows):
    with (ROOT / filename).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

def drivers():
    h = np.arange(HOURS)
    day, hour = h // 24, h % 24
    month = np.array([t.month-1 for t in CLOCK])
    # Deterministic proxy weather. Centre anomalies separately in each month.
    season = np.cos(2*np.pi*(day-172)/365)
    daylight = 12 + 3.8 * season
    sun = np.maximum(0, np.cos(np.pi*(hour + .5 - 12)/daylight))
    sun *= .76 + .20*np.sin(2*np.pi*day/8.3)
    temp = 3*np.sin(2*np.pi*(hour-9)/24) + 2.4*np.sin(2*np.pi*day/9.7)
    pv = np.zeros(HOURS)
    for m in range(12):
        ix = month == m
        temp[ix] += MONTHLY_TEMP[m] - temp[ix].mean()
        pv[ix] = sun[ix] * MONTHLY_PV[m] / sun[ix].sum()
    assert 0 <= pv.min() and pv.max() <= 1
    shape = 1 + .06*np.cos(2*np.pi*(hour-16)/24) + .05*np.sin(2*np.pi*day/7) + .07*np.sin(2*np.pi*day/29)
    shape /= shape.mean()
    # A realised synthetic bill, with an assumed hourly energy price, excluding demand charges.
    price = 100 + 23*np.cos(2*np.pi*(hour-19)/24) - 28*np.cos(2*np.pi*(hour-13)/12) + 9*np.cos(2*np.pi*day/365)
    price += 100 - price.mean()
    return dict(temp_C=temp, pv_MWh_per_MWp=pv, it_relative_load=shape,
                import_price_EUR_MWh=price, grid_tCO2e_MWh=np.full(HOURS,.123),
                customer_demand_MWth=np.minimum(14, 1.2 + .50*np.maximum(16-temp,0)))

def input_data(path):
    if path is None:
        return drivers()
    with Path(path).open(encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    expected = [d.strftime('%Y-%m-%dT%H:%M') for d in CLOCK]
    if [r['time_fixed_CET'] for r in rows] != expected:
        raise ValueError('Supply continuous 2025 hourly fixed CET timestamps from the example.')
    keys = drivers().keys()
    x = {k:np.array([float(r[k]) for r in rows]) for k in keys}
    if not all(np.isfinite(v).all() for v in x.values()):
        raise ValueError('Missing or nonfinite input.')
    if any((x[k]<0).any() for k in ['pv_MWh_per_MWp','it_relative_load','grid_tCO2e_MWh','customer_demand_MWth']) or x['pv_MWh_per_MWp'].max()>1 or not np.isclose(x['it_relative_load'].mean(),1,atol=1e-6):
        raise ValueError('Check nonnegative drivers, PV <=1 and mean-one IT shape.')
    return x

def assets(case, mw):
    return mw if case=='IT' else min(mw/1.30,mw/1.24,(mw-3.45)/1.20)

def storage(net, price, enabled, headroom=None):
    charge, discharge, soc = (np.zeros(HOURS) for _ in range(3))
    if not enabled:
        return charge,discharge,soc
    eta = .90**.5
    # A daily trading cycle. Buy in cheapest earlier slot, release at later dearer slot.
    # Perfect next-day price visibility, no standby losses, no UPS reserve revenue.
    for first in range(0,HOURS,24):
        available = 0.0
        buyers = sorted(range(first,first+12),key=lambda i:price[i])[:4]
        sellers = sorted(range(first+12,first+24),key=lambda i:-price[i])[:4]
        if np.mean(price[sellers])*.9 <= np.mean(price[buyers]):
            continue
        for i in range(first,first+24):
            if i in buyers:
                room = max(0,headroom-net[i]) if headroom is not None else 5
                charge[i] = min(5,(10-available)/eta,room)
            if i in sellers:
                discharge[i] = min(5,available*eta,max(net[i],0))
            available += charge[i]*eta - discharge[i]/eta
            soc[i] = available
        if abs(available)>1e-6:
            raise ValueError('Battery cannot empty on this load trace with this controller.')
    return charge,discharge,soc

def run(x, scenario='S3', case='IT', mw=75, util=.6, pv=None, bess=False,
        heat_cap=10, demand=1, fixed_cop=None, price_mult=1, grid_mult=1, capex=18,
        heat_price=85, source_frac=.8, annual_pue=None, water_intensity=None, heat_fixed_om=.45):
    pue, noncool, wue, design_ratio = SCENARIOS[scenario]
    if annual_pue is not None: pue=annual_pue
    if water_intensity is not None: wue=water_intensity
    installed = assets(case,mw)
    it = installed * util * x['it_relative_load']
    assert it.min()>=0 and it.max()<=installed
    overhead = it*noncool
    tshape = 1 + .025*(x['temp_C']-10)
    tshape = np.maximum(.35,tshape)
    cooling = it*tshape*(pue-1-noncool)/(it@tshape/it.sum())
    facility = it + cooling + overhead
    solar = x['pv_MWh_per_MWp'] * ((0 if scenario=='S1' else 2) if pv is None else pv)
    heat_demand = x['customer_demand_MWth']*demand
    fraction = source_frac if scenario=='S3' else 0
    source = fraction*it
    cop = np.full(HOURS,fixed_cop) if fixed_cop else np.clip(4.1+.035*(x['temp_C']-10),3,5)
    heat = np.minimum.reduce([source/(1-1/cop),heat_demand/.95,np.full(HOURS,heat_cap)])
    hp = heat/cop
    aux = .01*heat
    extracted = heat-hp
    delivered = .95*heat
    leakage = heat-delivered
    net = facility+hp+aux-solar
    price = x['import_price_EUR_MWh']*price_mult
    emissions = x['grid_tCO2e_MWh']*grid_mult
    charge, discharge, soc = storage(net,price,bess,mw if case=='FAC' else None)
    grid = np.maximum(0,net+charge-discharge)
    export = np.maximum(0,-(net+charge-discharge))
    rejected = it-extracted
    tests = {
        'electricity_residual_MWh':np.max(np.abs(grid+solar+discharge-facility-hp-aux-charge-export)),
        'thermal_residual_MWh':np.max(np.abs(extracted+hp-delivered-leakage)),
        'heat_source_residual_MWh':np.max(np.abs(extracted+rejected-it)),
        'annual_pue_error':abs(facility.sum()/it.sum()-pue),
        'battery_SOC_residual_MWh':np.max(np.abs(soc-np.r_[0,soc[:-1]]-charge*.9**.5+discharge/.9**.5)),
        'battery_terminal_MWh':abs(soc[-1]),
        'battery_overrun_MWh':max(0,soc.max()-10,-soc.min()),
        'customer_demand_excess_MWh':max(0,(delivered-heat_demand).max()),
        'capture_excess_MWh':max(0,(extracted-source).max()),
        'PV_exceeds_nameplate_MW':max(0,solar.max()-((0 if scenario=='S1' else 2) if pv is None else pv)),
        'FAC_import_excess_MW':max(0,grid.max()-mw) if case=='FAC' else 0,
    }
    if max(tests.values())>1e-6: raise AssertionError(tests)
    energy_bill = (grid@price-export@(price*.5))/1e6
    thermal_bill = ((hp+aux)@price)/1e6
    thermal_margin = delivered.sum()*heat_price/1e6 - thermal_bill - heat_fixed_om
    loop_npv = thermal_margin*ANNUITY-capex
    # System cost perimeter: modelled energy and incremental interventions only.
    improve = {'S1':0, 'S2':8, 'S3':13}[scenario]*installed/75
    pv_size = (0 if scenario=='S1' else 2) if pv is None else pv
    package_capex = improve + .90*pv_size + (capex if scenario=='S3' else 0) + (3.25 if bess else 0)
    extra_om = .015*improve + .012*.90*pv_size + (heat_fixed_om if scenario=='S3' else 0)+(.06 if bess else 0)
    cost = energy_bill + extra_om - delivered.sum()*heat_price/1e6
    out = dict(scenario=scenario,case=case,nameplate_MW=mw,installed_IT_MW=installed,average_IT_MW=it.mean(),PUE=facility.sum()/it.sum(),
          IT_GWh=it.sum()/1000,facility_GWh=facility.sum()/1000,cooling_GWh=cooling.sum()/1000,other_overhead_GWh=overhead.sum()/1000,
          grid_GWh=grid.sum()/1000,grid_export_GWh=export.sum()/1000,peak_import_MW=grid.max(),
          PV_GWh=solar.sum()/1000,onsite_PV_share_pct=100*(solar.sum()-export.sum())/(facility+hp+aux+charge-discharge).sum(),
          battery_charge_GWh=charge.sum()/1000,battery_discharge_GWh=discharge.sum()/1000,
          demand_GWhth=heat_demand.sum()/1000,heat_available_GWhth=source.sum()/1000,
          heat_extracted_GWhth=extracted.sum()/1000,heat_delivered_GWhth=delivered.sum()/1000,
          unmet_heat_GWhth=(heat_demand-delivered).sum()/1000,rejected_IT_heat_GWhth=rejected.sum()/1000,
          heating_COP=heat.sum()/hp.sum() if hp.sum() else 0,heat_HP_GWh=hp.sum()/1000,heat_aux_GWh=aux.sum()/1000,
          network_losses_GWhth=leakage.sum()/1000,external_reused_IT_fraction_pct=100*extracted.sum()/it.sum(),
          site_water_input_m3=it.sum()*wue,grid_operational_ktCO2e=(grid@emissions)/1e3,
          heat_plant_ktCO2e=((hp+aux)@emissions)/1e3,gas_counterfactual_ktCO2=delivered.sum()*.202/.90/1e3,
          import_bill_net_mEUR=energy_bill,heat_revenue_mEUR=delivered.sum()*heat_price/1e6,
          heat_energy_bill_mEUR=thermal_bill,heat_operating_margin_mEUR=thermal_margin if scenario=='S3' else 0,
          heat_15y_NPV_mEUR=loop_npv if scenario=='S3' else 0,heat_payback_years=capex/thermal_margin if thermal_margin>0 and scenario=='S3' else '',
          heat_breakeven_EUR_MWh=(capex/ANNUITY+heat_fixed_om+thermal_bill)*1e6/delivered.sum() if delivered.sum() else '',
          scope_incremental_capex_mEUR=package_capex,scope_annual_net_cost_mEUR=cost,
          scope_15y_present_cost_mEUR=package_capex+cost*ANNUITY)
    hourly = dict(it_MW=it,facility_MW=facility,cooling_MW=cooling,other_overhead_MW=overhead,pv_MW=solar,
                  grid_MW=grid,export_MW=export,source_available_MWth=source,source_extracted_MWth=extracted,
                  condenser_MWth=heat,delivered_MWth=delivered,distribution_loss_MWth=leakage,heat_pump_MW=hp,
                  heat_aux_MW=aux,COP=cop,charge_MW=charge,discharge_MW=discharge,SOC_MWh=soc)
    return out,hourly,tests

def write_series(filename,series):
    with (ROOT/filename).open('w', newline='',encoding='utf-8') as f:
        w=csv.writer(f)
        w.writerow(['time_fixed_CET',*series])
        for i,t in enumerate(CLOCK):
            w.writerow([t.strftime('%Y-%m-%dT%H:%M'),*[format(v[i],'.12g') for v in series.values()]])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', help='Optional CSV following hourly_inputs.csv schema.')
    args=parser.parse_args()
    x=input_data(args.inputs)
    if args.inputs is None: write_series('hourly_inputs.csv',x)
    cases,checks,monthly,hourly=[],[],[],{}
    for case in ['IT','FAC']:
        for mw in [50,75,100]:
            for s in SCENARIOS:
                r,h,t=run(x,s,case,mw)
                cases.append(r)
                checks.append(dict(test=f'{case}{mw}_{s}',**t))
                if mw==75 and case=='IT':
                    hourly.update({f'{s}_{k}':v for k,v in h.items()})
                    for m in range(1,13):
                        ix=np.array([t.month==m for t in CLOCK])
                        monthly.append(dict(scenario=s,month=m,IT_GWh=h['it_MW'][ix].sum()/1000,
                               grid_GWh=h['grid_MW'][ix].sum()/1000,demand_GWhth=x['customer_demand_MWth'][ix].sum()/1000,
                               delivered_GWhth=h['delivered_MWth'][ix].sum()/1000,heatplant_GWh=(h['heat_pump_MW'][ix]+h['heat_aux_MW'][ix]).sum()/1000))
    write_series('hourly_results_IT75.csv',hourly)
    write_rows('scenario_summary.csv',cases)
    write_rows('monthly_IT75.csv',monthly)
    sensitivities = {
      'base':{}, 'COP_3':dict(fixed_cop=3),'COP_4':dict(fixed_cop=4),'COP_5':dict(fixed_cop=5),
      'half_customer_demand':dict(demand=.5),'double_customer_demand':dict(demand=2),
      'phase_one_5MWth_same_fixed_cost':dict(heat_cap=5),
      'phase_one_5MWth_shared_trench':dict(heat_cap=5,capex=12,heat_fixed_om=.30),
      'source_fraction_0.50':dict(source_frac=.5),'source_fraction_0.95':dict(source_frac=.95),
      'heat_tariff_55':dict(heat_price=55),'heat_tariff_110':dict(heat_price=110),
      'capex_minus_30pct':dict(capex=12.6),'capex_plus_30pct':dict(capex=23.4),
      'electricity_70':dict(price_mult=.7),'electricity_130':dict(price_mult=1.3),
      'grid_factor_production_53g':dict(grid_mult=.053/.123),'grid_factor_with_upstream_152g':dict(grid_mult=.152/.123),
      'grid_factor_200g':dict(grid_mult=.20/.123),'grid_factor_400g':dict(grid_mult=.4/.123),
      'water_input_0.14L_kWhIT':dict(water_intensity=.14),'water_input_0.58L_kWhIT':dict(water_intensity=.58),
      'electricity_134_workbook':dict(price_mult=1.34),
      'inference_util_0.40':dict(util=.4),'training_util_0.50':dict(util=.5),'training_util_0.71':dict(util=.71),
      'PUE_1.11':dict(annual_pue=1.11),'PUE_1.18':dict(annual_pue=1.18),
      'PV_10MWp':dict(pv=10),'battery_5MW_10MWh':dict(bess=True),
      'adverse_bundle':dict(demand=.5,capex=23.4,price_mult=1.3,heat_price=55,fixed_cop=3),
      'upside_bundle':dict(demand=2,capex=12.6,price_mult=.7,heat_price=110,fixed_cop=5),
    }
    sens=[]
    for label,kw in sensitivities.items():
        r,h,t=run(x,**kw)
        checks.append(dict(test=label,**t))
        sens.append(dict(test=label,**r))
        if kw.get('bess'):
            write_series('hourly_battery_IT75.csv',{k:h[k] for k in ('grid_MW','charge_MW','discharge_MW','SOC_MWh')})
    write_rows('sensitivity_IT75.csv',sens)
    size_sens=[]
    for case in ['IT','FAC']:
        for mw in [50,100]:
            for label,kw in sensitivities.items():
                r,h,t=run(x,case=case,mw=mw,**kw)
                checks.append(dict(test=f'{case}{mw}_{label}',**t))
                size_sens.append(dict(test=label,**r))
    write_rows('sensitivity_50_100.csv',size_sens)
    write_rows('validation.csv',checks)
    # Criterion scores out of five are explicit team judgements, not measured jury scores.
    scores=np.array([[1,5,2,3],[3,4.5,3.5,4],[4.5,3,4.5,3]])
    weights=np.array([5/18,5/18,5/18,3/18])
    names=['innovation','feasibility','sustainability','economics']
    designs={'official_normalized':weights}
    for i,name in enumerate(names):
        for step in [-.10,.10]:
            altered=weights*(1-weights[i]-step)/(1-weights[i])
            altered[i]=weights[i]+step
            designs[f'{name}_{step:+.2f}']=altered
    mcda=[]
    for key,w in designs.items():
        total=scores@w
        mcda.append(dict(test=key,**dict(zip(names,w)),**dict(zip(SCENARIOS,total)),rank=' > '.join(np.array(list(SCENARIOS))[np.argsort(-total)])))
    write_rows('mcda.csv',mcda)
    print(f'Passed {len(checks)} scenario runs, {len(checks[0])-1} invariants per run.')

if __name__=='__main__':
    main()

