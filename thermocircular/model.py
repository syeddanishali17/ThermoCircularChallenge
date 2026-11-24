"""Adapter, input provenance and energy accounting for the audited engine."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import csv
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
import pandas as pd

from .config import DEFAULT, PRESETS, Settings

ROOT = Path(__file__).resolve().parents[1]
AUDITED = ROOT / "vendor/audited_model"
sys.path.insert(0, str(AUDITED))
try:
    import optimize as engine
finally:
    sys.path.remove(str(AUDITED))
if Path(engine.__file__).resolve() != AUDITED / "optimize.py":
    raise ImportError("The ThermoCircular audited engine could not be loaded.")

PROXY_VERSION = "audited-2026-11-24"
ADAPTER_VERSION = "1.0.0"
ENGINE_HASH = sha256(
    (AUDITED / "optimize.py").read_bytes() + (AUDITED / "legacy_engine.py").read_bytes()
).hexdigest()
ANNUITY = engine.ANNUITY
CLOCK = pd.DatetimeIndex(engine.legacy.CLOCK, name="fixed_CET")
TIME_LABELS = tuple(CLOCK.strftime("%Y-%m-%dT%H:%M"))
CANONICAL = AUDITED / "example_hourly_inputs.csv"
NUMERIC = ("temp_C", "pv_MWh_per_MWp", "it_relative_load", "import_price_EUR_MWh",
           "grid_tCO2e_MWh", "customer_demand_MWth")
INPUT_COLUMNS = ("time_fixed_CET", *NUMERIC)
CLOCK_MONTH = CLOCK.month.to_numpy()
HOURS = np.arange(len(CLOCK))
MAX_CSV = 3_000_000
_PROXY_DRIVERS = engine.legacy.drivers()
PROXY_HASH = sha256(np.column_stack([_PROXY_DRIVERS[key] for key in NUMERIC]).astype("<f8").tobytes()).hexdigest()
del _PROXY_DRIVERS
TRACE_COLUMNS = (
    "ambient_C", "IT_MW", "facility_MW", "pv_MW", "grid_MW", "grid_export_MW", "grid_limit_MW",
    "required_heat_MWth", "accepted_heat_MWth", "condenser_MWth", "source_MWth", "heat_plant_MW",
    "delivered_MWth", "backup_MWth", "power_price_EUR_MWh", "carbon_t_MWh", "matched_offsite_MW",
    "rejected_IT_MWth", "unconstrained_accepted_MWth", "grid_limited_MWth",
    "positive_variable_margin", "beats_customer_carbon",
)
LIMITATIONS = (
    "Deterministic screening on 8,760 fixed-CET hours in 2025. The bundled inputs are scenario proxies.",
    "Connection capacity, parcel, buyer acceptance, route, tariff and renewable contracts require external validation.",
    "Heat-project NPV covers heat assets and their operations. Campus construction, financing, taxes and buyer backup costs are outside this perimeter.",
    "Illustrative offsite matching never reduces physical grid imports or changes the emissions ledger.",
    "Certified reporting, physical validation and the optional 2035 task are outside the current model scope.",
)


def validate_hourly(payload: bytes):
    if not 0 < len(payload) <= MAX_CSV:
        raise ValueError("Hourly CSV must be nonempty and no larger than 3 MB.")
    try:
        rows = csv.reader(StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
        if tuple(next(rows, ())) != INPUT_COLUMNS:
            raise ValueError("Use the seven native columns in the order shown in the template.")
        records = []
        for index, row in enumerate(rows):
            if index == len(CLOCK) or len(row) != len(INPUT_COLUMNS) or row[0] != TIME_LABELS[index]:
                raise ValueError(f"CSV row {index + 2}: expected continuous 2025 fixed CET and seven fields.")
            try:
                records.append([float(value) for value in row[1:]])
            except ValueError:
                raise ValueError(f"CSV row {index + 2}: every driver must be numeric.") from None
    except (UnicodeError, csv.Error):
        raise ValueError("The hourly file must be valid UTF-8 CSV.") from None
    if len(records) != len(CLOCK):
        raise ValueError("The hourly file must contain exactly 8,760 records.")
    values = np.asarray(records)
    if not np.isfinite(values).all():
        raise ValueError("Hourly driver values must be finite.")
    bounds = ((-80, 80), (0, 1), (0, 1 / .6), (-10000, 10000), (0, 10), (0, 2000))
    for index, (lo, hi) in enumerate(bounds):
        if ((values[:, index] < lo) | (values[:, index] > hi)).any():
            raise ValueError(f"Hourly driver {NUMERIC[index]} is outside [{lo:.4g}, {hi:.4g}].")
    if not np.isclose(values[:, 2].mean(), 1, atol=1e-6, rtol=0):
        raise ValueError("The IT load driver must have a mean of 1.")


@contextmanager
def native_hourly(payload):
    if payload is None:
        yield None
        return
    validate_hourly(payload)
    with TemporaryDirectory(prefix="thermocircular-input-") as directory:
        path = Path(directory) / "hourly.csv"
        path.write_bytes(payload)
        yield path


def source_hash(payload):
    return PROXY_HASH if payload is None else sha256(payload).hexdigest()


def scenario_id(settings, payload=None, fixed_modules=1):
    digest = sha256(
        f"{ENGINE_HASH}:{ADAPTER_VERSION}:{source_hash(payload)}:{fixed_modules}:{settings.model_dump_json()}".encode()
    ).hexdigest()
    return f"TC-{digest[:12].upper()}"


def feasible(row):
    return bool(row["nameplate_feasible"] and row["hourly_grid_excess_MW"] <= 1e-9)


def nameplate(settings, modules, conventional=False):
    return settings.it_mw * (1.30 if conventional else 1.24) + modules * settings.module_mw * (1 / 3 + .01)


def resource_profiles(settings):
    hydro = settings.hydro_mw * settings.hydro_fraction * (.72 + .19 * np.cos(2 * np.pi * (HOURS / 24 - 170) / 365))
    wind = settings.wind_mw * settings.wind_fraction * (.29 + .085 * np.cos(2 * np.pi * HOURS / 8760) + .11 * np.sin(2 * np.pi * HOURS / 157))
    return hydro, wind


def frame(native, settings, conventional=False):
    if tuple(native) != TRACE_COLUMNS:
        raise RuntimeError("Unexpected audited hourly output schema.")
    data = pd.DataFrame(native, index=CLOCK)
    cop = np.full(len(CLOCK), settings.cop) if settings.cop else np.clip(4.1 + .035 * (data.ambient_C - 10), 3, 5)
    hydro, wind = resource_profiles(settings)
    data = data.assign(
        COP=cop,
        thermal_loss_MWth=data.condenser_MWth - data.delivered_MWth,
        source_ceiling_MWth=.80 * data.IT_MW,
        pv_used_MW=data.pv_MW - data.grid_export_MW,
        offsite_hydro_MW=0 if conventional else hydro,
        offsite_wind_MW=0 if conventional else wind,
        unmatched_grid_MW=data.grid_MW - data.matched_offsite_MW,
        campus_gross_MW=data.facility_MW + data.heat_plant_MW,
        usable_grid_headroom_MW=np.maximum(0, data.grid_limit_MW - (data.facility_MW - data.pv_MW)),
    )
    return data


def check_trace(t, row):
    tolerance = 1e-8
    if not np.isfinite(t.to_numpy()).all():
        raise RuntimeError("Nonfinite values in hourly output.")
    comparisons = (
        (t.grid_MW + t.pv_MW, t.campus_gross_MW + t.grid_export_MW),
        (t.condenser_MWth, t.source_MWth + t.condenser_MWth / t.COP),
        (t.condenser_MWth, t.delivered_MWth + t.thermal_loss_MWth),
        (t.IT_MW, t.source_MWth + t.rejected_IT_MWth),
        (t.required_heat_MWth, t.delivered_MWth + t.backup_MWth),
    )
    if any(not np.allclose(left, right, rtol=0, atol=tolerance) for left, right in comparisons):
        raise RuntimeError("Hourly energy balance failed.")
    if ((t.delivered_MWth > t.accepted_heat_MWth + tolerance).any()
            or (t.source_MWth > t.source_ceiling_MWth + tolerance).any()
            or t.filter(regex=r"_MW(th)?$").min().min() < -tolerance):
        raise RuntimeError("Hourly flows violate the capture, acceptance or nonnegativity bounds.")
    if not np.isclose((t.grid_MW - t.grid_limit_MW).clip(lower=0).max(), row["hourly_grid_excess_MW"], atol=tolerance, rtol=0):
        raise RuntimeError("Reported grid violation differs from the hourly trace.")
    if not np.isclose(t.delivered_MWth.sum() / 1000, row["delivered_heat_GWhth"], atol=tolerance, rtol=0):
        raise RuntimeError("Annual heat differs from the hourly trace.")


@dataclass
class Run:
    settings: Settings
    payload: bytes | None
    fixed_modules: int
    id: str
    created_at: str
    cases: tuple[dict[str, Any], ...]
    investments: tuple[dict[str, Any], ...]
    increment: dict[str, float]
    fixed: tuple[dict[str, Any], dict[str, Any]]
    traces: dict[str, pd.DataFrame]

    @property
    def d(self):
        return self.cases[3]

    @property
    def official(self):
        return self.settings == DEFAULT and self.payload is None and self.fixed_modules == 1

    @property
    def service_hash(self):
        service = self.traces["A"][["IT_MW", "required_heat_MWth"]].to_numpy().astype("<f8")
        return sha256(service.tobytes()).hexdigest()

    def metadata(self):
        return {
            "scenario_id": self.id,
            "created_at_utc": self.created_at,
            "model_version": PROXY_VERSION,
            "engine_sha256": ENGINE_HASH,
            "adapter_version": ADAPTER_VERSION,
            "input_sha256": source_hash(self.payload),
            "hourly_service_sha256": self.service_hash,
            "input_evidence": "User-supplied unverified" if self.payload is not None else "Scenario assumption / generated proxy",
            "clock": "2025 fixed CET (UTC+01:00), 8760 hourly intervals",
            "fixed_modules": self.fixed_modules,
            "mode": "Official baseline" if self.official else "Custom scenario",
        }


def simulate(settings=DEFAULT, payload=None, fixed_modules=1):
    if type(fixed_modules) is not int or fixed_modules not in range(3):
        raise ValueError("Fixed equipment must contain zero, one or two modules.")
    a = engine.Inputs(**settings.model_dump())
    with native_hourly(payload) as path:
        rows, d_trace, steps, matched, increment = engine.compare(a, path)
        x = engine.source_inputs(a, path)
    cases = (*rows, matched)
    native = {r["reference"]: engine.evaluate(a, x, r["reference"], r["modules"])[1]
              for r in cases if r["reference"] != "D"}
    native["D"] = d_trace
    fixed, coordinated = engine.evaluate(a, x, "D", fixed_modules, True)
    independent, fixed_trace = engine.evaluate(a, x, "C", fixed_modules)
    native.update({"Installed coordinated": coordinated, "Installed fixed": fixed_trace})
    fixed = {**fixed, "reference": "Installed coordinated"}
    independent = {**independent, "reference": "Installed fixed"}
    traces = {key: frame(v, settings, key == "A") for key, v in native.items()}
    for row in (*cases, fixed, independent):
        check_trace(traces[row["reference"]], row)
        if row["nameplate_feasible"] != (nameplate(settings, row["modules"], row["reference"] == "A") <= settings.grid_mw + 1e-9):
            raise RuntimeError("Nameplate screen differs from audited result.")
    for field in ("IT_MW", "required_heat_MWth"):
        if any(not traces["A"][field].equals(traces[key][field]) for key in ("B", "C", "D")):
            raise RuntimeError("A/B/C/D run with different service boundaries.")
    return Run(settings, payload, fixed_modules, scenario_id(settings, payload, fixed_modules),
               datetime.now(timezone.utc).isoformat(), cases, tuple(steps), increment,
               (fixed, independent), traces)


ENERGY_COLS = {
    "IT_MW": "IT_GWh", "facility_MW": "facility_GWh", "campus_gross_MW": "campus_gross_GWh",
    "grid_MW": "grid_GWh", "heat_plant_MW": "heat_plant_GWh", "pv_MW": "PV_GWh",
    "pv_used_MW": "PV_used_GWh", "grid_export_MW": "grid_export_GWh",
    "offsite_hydro_MW": "hydro_generated_GWh", "offsite_wind_MW": "wind_generated_GWh",
    "matched_offsite_MW": "offsite_matched_GWh", "unmatched_grid_MW": "unmatched_grid_GWh",
    "source_MWth": "source_GWhth", "condenser_MWth": "condenser_GWhth",
    "thermal_loss_MWth": "loss_GWhth", "delivered_MWth": "delivered_GWhth",
    "backup_MWth": "backup_GWhth", "required_heat_MWth": "required_GWhth",
    "accepted_heat_MWth": "accepted_GWhth", "rejected_IT_MWth": "rejected_IT_GWhth",
}


def monthly(trace):
    ledger = (trace[list(ENERGY_COLS)].resample("MS").sum() / 1000).rename(columns=ENERGY_COLS)
    ledger["matching_pct"] = 100 * (ledger.PV_used_GWh + ledger.offsite_matched_GWh) / ledger.campus_gross_GWh
    ledger["wholly_matched_hours"] = (trace.unmatched_grid_MW <= 1e-9).resample("MS").sum()
    ledger.index = ledger.index.strftime("%Y-%m")
    ledger.index.name = "month_fixed_CET"
    return ledger


def comparator(trace, buyer, factor=.202 / .90):
    electric_factor = {"Gas boiler": 0, "Resistance heat": 1, "Electric heat pump (COP 3)": 1 / 3}[buyer]
    backup = trace["backup_MWth"]
    grid = trace["grid_MW"]
    buyer_power = electric_factor * backup
    return {
        "buyer": buyer,
        "campus_import_GWh": grid.sum() / 1000,
        "buyer_electricity_GWh": buyer_power.sum() / 1000,
        "combined_electricity_GWh": (grid + buyer_power).sum() / 1000,
        "grid_ktCO2e": (grid @ trace["carbon_t_MWh"]) / 1000,
        "buyer_electricity_ktCO2e": (buyer_power @ trace["carbon_t_MWh"]) / 1000,
        "buyer_fuel_ktCO2e": backup.sum() * factor / 1000 if electric_factor == 0 else 0,
        "combined_ktCO2e": ((grid + buyer_power) @ trace["carbon_t_MWh"]) / 1000
        + (backup.sum() * factor / 1000 if electric_factor == 0 else 0),
    }


def financial(row, trace, settings):
    revenue = row["delivered_heat_GWhth"] * settings.heat_tariff / 1000
    power = (trace.heat_plant_MW @ trace.power_price_EUR_MWh) / 1e6
    om = {0: 0, 1: .30, 2: .45}[row["modules"]]
    return {"Revenue": float(revenue), "Power cost": float(power), "Fixed O&M": om,
            "Operating margin": float(revenue - power - om), "Capex": row["capex_heat_MEUR"]}


def installed_tradeoff(run):
    coord, fixed = run.fixed
    private = coord["heat_15y_NPV_MEUR"] - fixed["heat_15y_NPV_MEUR"]
    backup = coord["backup_heat_GWhth"] - fixed["backup_heat_GWhth"]
    return {
        "operator_delta_MEUR": private,
        "heat_delta_GWhth": coord["delivered_heat_GWhth"] - fixed["delivered_heat_GWhth"],
        "backup_delta_GWhth": backup,
        "emissions_delta_ktCO2e": coord["combined_gas_comparator_ktCO2e"] - fixed["combined_gas_comparator_ktCO2e"],
        "erasing_penalty_EUR_MWh": private * 1000 / (ANNUITY * backup) if backup > 1e-9 else None,
    }


def stress_suite(settings=DEFAULT, payload=None):
    summaries = []
    for case, changes in PRESETS.items():
        # The suite is an explicit set of overrides on the current inputs.
        overrides = dict(changes)
        if case in {"Winter import cap 63 MW", "Stress combination"}:
            cap = 63 if case == "Winter import cap 63 MW" else 62
            overrides["peak_restriction_mw"] = max(0, settings.grid_mw - cap)
        if case == "Civil cost +30%":
            overrides = dict(nonpipe_stage_one_m=settings.nonpipe_stage_one_m * 1.30,
                             pipe_cost_per_km_m=settings.pipe_cost_per_km_m * 1.30)
        candidate = {**settings.model_dump(), **overrides}
        if "grid_mw" in overrides:
            candidate["peak_restriction_mw"] = min(candidate["peak_restriction_mw"], candidate["grid_mw"])
        try:
            variant = Settings.model_validate(candidate)
        except ValueError as error:
            summaries.append(dict(case=case, input_error=str(error.errors()[0]["msg"])))
            continue
        run = simulate(variant, payload, 1)
        d, one, fixed = run.d, run.investments[1], run.cases[4]
        trade = installed_tradeoff(run)
        summaries.append(dict(
            case=case, C_modules=run.cases[2]["modules"], D_modules=d["modules"],
            D_nameplate_feasible=d["nameplate_feasible"], D_grid_excess_MW=d["hourly_grid_excess_MW"],
            D_grid_GWh=d["grid_GWh"], D_PV_GWh=d["PV_GWh"], D_delivered_GWhth=d["delivered_heat_GWhth"],
            D_hourly_renewables_pct=d["hourly_renewable_matching_pct"],
            one_module_heat_GWhth=one["delivered_heat_GWhth"], one_module_NPV_MEUR=one["heat_15y_NPV_MEUR"],
            one_module_break_even_EUR_MWh=one["heat_break_even_EUR_MWh"],
            operating_ablation_D_minus_fixed_MEUR=d["heat_15y_NPV_MEUR"] - fixed["heat_15y_NPV_MEUR"],
            installed_pilot_dispatch_delta_NPV_MEUR=trade["operator_delta_MEUR"],
            installed_pilot_heat_delta_GWhth=trade["heat_delta_GWhth"],
            installed_pilot_combined_delta_ktCO2e=trade["emissions_delta_ktCO2e"],
            backup_penalty_erasing_private_gain_EUR_MWh=trade["erasing_penalty_EUR_MWh"],
            one_module_required_heat_GWhth=one["demand_heat_GWhth"],
            one_module_backup_GWhth=one["backup_heat_GWhth"], **run.increment,
        ))
    return pd.DataFrame(summaries)


def evaluate_one_module(settings, payload, changes):
    """Hold one module fixed to expose downside even when procurement defers."""
    values = {**settings.model_dump(), **changes}
    a = engine.Inputs(**Settings.model_validate(values).model_dump())
    with native_hourly(payload) as path:
        x = engine.source_inputs(a, path)
    row, _ = engine.evaluate(a, x, "D", 1, True)
    return row
