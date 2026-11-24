import json
from dataclasses import asdict
from io import BytesIO
from zipfile import ZipFile

import numpy as np
import openpyxl
import pandas as pd
import pytest

from thermocircular.assessment import BENCH_LOADS, SITE_GATES, SITE_WEIGHTS, bench_screen, component, power_input, rank_site
from thermocircular.config import DEFAULT, PRESETS, Settings
from thermocircular.exports import config_bytes, csv_bytes, hourly_zip, html_bytes, workbook_bytes
from thermocircular.model import (
    AUDITED, CANONICAL, TRACE_COLUMNS, comparator, engine, feasible, installed_tradeoff, monthly,
    nameplate, simulate, stress_suite, validate_hourly,
)
from thermocircular.storage import Store, parse_recipe


@pytest.fixture(scope="module")
def base():
    return simulate()


def variant(name):
    return Settings.model_validate({**DEFAULT.model_dump(), **PRESETS[name]})


def test_reference_defaults():
    assert DEFAULT.model_dump() == asdict(engine.Inputs())


def test_full_adapter_parity(base):
    for actual, name in ((base.cases[:4], "scenario_results"), (base.investments, "investment_steps")):
        pd.testing.assert_frame_equal(pd.DataFrame(actual), pd.read_csv(AUDITED / f"results/{name}.csv"),
                                      check_dtype=False, rtol=0, atol=1e-6)
    expected = pd.read_csv(AUDITED / "results/hourly_D.csv", parse_dates=["fixed_CET"]).set_index("fixed_CET")
    pd.testing.assert_frame_equal(base.traces["D"][list(TRACE_COLUMNS)], expected,
                                  check_freq=False, check_index_type=True, check_dtype=False, rtol=0, atol=1e-6)


def test_all_native_stresses():
    pd.testing.assert_frame_equal(stress_suite(), pd.read_csv(AUDITED / "results/stress_tests.csv"),
                                  check_dtype=False, rtol=0, atol=1e-6)


def test_default_baseline_display(base):
    d = base.d
    assert d["modules"] == 1
    assert f"{d['delivered_heat_GWhth']:.2f}" == "27.63"
    assert f"{d['heat_15y_NPV_MEUR']:.2f}" == "0.36"
    assert f"{d['heat_break_even_EUR_MWh']:.2f}" == "83.64"
    assert d["heat_15y_NPV_MEUR"] == pytest.approx(base.cases[4]["heat_15y_NPV_MEUR"], abs=1e-9)
    assert nameplate(base.settings, 1) == pytest.approx(94.7166666667)
    assert d["water_input_m3"] == pytest.approx(11826)


def test_ledger_and_counterfactual(base):
    ledger = monthly(base.traces["D"])
    assert ledger.grid_GWh.sum() == pytest.approx(base.d["grid_GWh"])
    assert ledger.delivered_GWhth.sum() == pytest.approx(base.d["delivered_heat_GWhth"])
    assert (ledger.delivered_GWhth + ledger.backup_GWhth).sum() == pytest.approx(ledger.required_GWhth.sum())
    assert ledger.offsite_matched_GWh.sum() + ledger.unmatched_grid_GWh.sum() == pytest.approx(ledger.grid_GWh.sum())
    for buyer, metric, target in (
        ("Gas boiler", "combined_ktCO2e", -5.27),
        ("Electric heat pump (COP 3)", "combined_electricity_GWh", -1.64),
    ):
        assert round(comparator(base.traces["D"], buyer)[metric] - comparator(base.traces["B"], buyer)[metric], 2) == target


@pytest.mark.parametrize("case", ["Grid delay or 90 MW firm", "100 MW IT test above facility limit"])
def test_grid_restrictions(case):
    run = simulate(variant(case))
    assert not feasible(run.d)
    assert run.d["modules"] == 0
    assert np.array_equal(run.traces["D"].IT_MW, run.traces["B"].IT_MW)


def test_buyer_outage_keeps_required_heat(base):
    out = simulate(variant("Heat buyer outage 336 h"))
    t = out.traces["Installed coordinated"]
    assert out.d["modules"] == 0
    assert t.iloc[:336].accepted_heat_MWth.eq(0).all()
    assert t.required_heat_MWth.equals(base.traces["D"].required_heat_MWth)
    assert t.delivered_MWth.sum() / 1000 == pytest.approx(26.03, abs=.01)


def test_winter_installed_tradeoff():
    run = simulate(variant("High winter price"))
    trade = installed_tradeoff(run)
    assert run.d["modules"] == 0
    assert trade["operator_delta_MEUR"] == pytest.approx(.396, abs=.002)
    assert trade["backup_delta_GWhth"] == pytest.approx(1.52, abs=.01)
    assert trade["emissions_delta_ktCO2e"] == pytest.approx(.2880850451)
    assert trade["erasing_penalty_EUR_MWh"] == pytest.approx(26.79695732)


@pytest.mark.parametrize("changes", [
    {"cop": 1.0}, {"heat_outage_hours": 2161}, {"peak_restriction_mw": 101}, {"carbon_g": float("inf")},
    {"pipe_km": -1}, {"heat_tariff": True}, {"unexpected": 42},
])
def test_invalid_settings(changes):
    with pytest.raises(ValueError):
        Settings.model_validate(changes)


@pytest.mark.parametrize("corrupt", [
    lambda b: b.replace(b"time_fixed_CET,", b"time,"),
    lambda b: b.replace(b"2025-01-01T01:00", b"2025-01-01T00:00"),
    lambda b: b.replace(b"2025-01-01T01:00", b"2025-01-01T01:00+01:00"),
    lambda b: b.splitlines(keepends=True)[0],
    lambda b: b.replace(b"-1.36167669141", b"NaN", 1),
    lambda b: b.replace(b",-1.36167669141,0,", b",-1.36167669141,1.2,", 1),
])
def test_malformed_hourly_file(corrupt):
    with pytest.raises(ValueError):
        validate_hourly(corrupt(CANONICAL.read_bytes()))


def test_uploaded_hourly_precedence():
    csv = CANONICAL.read_bytes()
    run = simulate(Settings(site="Graz", carbon_g=500), csv)
    assert run.traces["D"].carbon_t_MWh.eq(.123).all()
    assert run.d["PV_GWh"] == pytest.approx(2.3526)
    assert run.metadata()["input_evidence"] == "User-supplied unverified"


def test_round_trip_store_exports(tmp_path, base):
    path = tmp_path / "test.sqlite3"
    store = Store(path)
    store.save("Audited", base)
    key = store.list()[0][0]
    store = Store(path)
    file, snapshot = store.get(key)
    loaded = simulate(*parse_recipe(file))
    assert loaded.id == base.id
    assert snapshot["annual"][3]["grid_GWh"] == base.d["grid_GWh"]
    store.rename(key, "Reference")
    assert store.list()[0][1] == "Reference"
    assert not Store().list()
    store.save_register("inventory", [{"quantity": 2}])
    assert Store(path).register("inventory", []) == [{"quantity": 2}]
    store.delete(key)
    assert not store.list()
    assert parse_recipe(config_bytes(base))[0] == base.settings
    assert b"27.63" in html_bytes(base)
    book = openpyxl.load_workbook(BytesIO(workbook_bytes(base)), data_only=True)
    assert "Buyer comparisons" in book
    with ZipFile(BytesIO(hourly_zip(base))) as archive:
        assert len(archive.namelist()) == 8
        assert archive.testzip() is None
    assert b"'=1+1" in csv_bytes(pd.DataFrame({"Input": ["=1+1"]}))


def test_recipe_provenance_guard(base):
    doc = json.loads(config_bytes(base))
    doc["settings"]["heat_tariff"] = 90
    with pytest.raises(ValueError, match="fingerprints"):
        parse_recipe(json.dumps(doc).encode())


def test_rank_only_supported_sites():
    gates = {gate: ("Unknown", "") for gate in SITE_GATES}
    ratings = [(5, "Reference") for _ in SITE_WEIGHTS]
    assert rank_site(gates, ratings, SITE_WEIGHTS) == ("Evidence pending", None)
    gates = {gate: ("Pass", "2026-11-24 subject evidence") for gate in SITE_GATES}
    assert rank_site(gates, ratings, SITE_WEIGHTS) == ("Eligible", 100)
    gates["Fibre"] = ("Fail", "2026-11-24 qualification")
    assert rank_site(gates, ratings, SITE_WEIGHTS) == ("Ineligible", None)
    gates["Grid"] = ("Pass", "")
    with pytest.raises(ValueError):
        rank_site(gates, ratings, SITE_WEIGHTS)


def test_component_and_psu_comparison():
    assert component(2274, 1.7, 123)[3] == pytest.approx(1.26069, abs=1e-5)
    assert component(2274, 1.7, 53)[3] == pytest.approx(2.92575, abs=1e-5)
    assert component(2274, 1.7, 0)[3] is None
    assert power_input(12, 96, 97)[2] == pytest.approx(.12886598)


def test_psu_qualification():
    assert bench_screen([{"Load %": k} for k in BENCH_LOADS], ["Unknown"] * 5)[0] == "Untested / incomplete"
    rows = [{"Load %": k, "Voltage V": 230, "Temperature °C": 23, "Repetitions": 3, "Duty share %": 25,
             "Incumbent AC kW": .12 * k + .2, "Candidate AC kW": .12 * k + .1,
             "Combined uncertainty kW": .025, "Conditions": "matched fixture", "Record": "qualified record"}
            for k in BENCH_LOADS]
    assert bench_screen(rows, ["Pass"] * 5)[0] == "Bench screen passed"
    assert bench_screen(rows, ["Pass"] * 4 + ["Fail"])[0] == "Qualification failed"
    rows[0]["Combined uncertainty kW"] = 1.
    assert bench_screen(rows, ["Pass"] * 5)[0] == "Improvement below uncertainty"
