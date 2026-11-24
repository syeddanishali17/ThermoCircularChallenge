"""Explicit decision boundaries outside the frozen model."""
from math import isfinite
from numbers import Real

SITE_GATES = ("Grid", "Land and pipe route", "Fibre", "Hazards and ground", "Water", "Permitting", "Heat customer")
SITE_WEIGHTS = (30, 25, 20, 10, 10, 5)
SITE_CRITERIA = ("Contracted buyer heat", "Delivered heat cost", "Grid and decarbonisation",
                 "Cooling and water resilience", "Circularity and site fit", "Fibre resilience")
BENCH_LOADS = (30, 50, 75, 100)


def rank_site(gates, ratings, weights):
    if set(gates) != set(SITE_GATES):
        raise ValueError("Include every site gate.")
    if any(status not in ("Unknown", "Pass", "Fail") for status, _ in gates.values()):
        raise ValueError("Invalid site gate status.")
    if any(status != "Unknown" and not evidence.strip() for status, evidence in gates.values()):
        raise ValueError("Each pass or fail needs dated evidence.")
    if len(weights) != 6 or any(not isfinite(w) or w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError("Use six nonnegative weights with a positive total.")
    if any(status == "Fail" for status, _ in gates.values()):
        return "Ineligible", None
    if any(status == "Unknown" for status, _ in gates.values()):
        return "Evidence pending", None
    if len(ratings) != 6 or any(type(score) is not int or not 1 <= score <= 5 or not evidence.strip()
                                 for score, evidence in ratings):
        return "Ratings incomplete", None
    return "Eligible", sum(score * w for (score, _), w in zip(ratings, weights, strict=True)) * 20 / sum(weights)


def component(footprint, ratio, intensity):
    old = 5.6 * .60 * 1.21 * 8760
    saving = old * (1 - 1 / ratio)
    avoided = saving * intensity / 1000
    return old, saving, avoided, footprint / avoided if avoided > 0 else None


def power_input(output_kw, incumbent_pct, candidate_pct):
    incumbent = output_kw / (incumbent_pct / 100)
    candidate = output_kw / (candidate_pct / 100)
    return incumbent, candidate, incumbent - candidate


def bench_screen(rows, checks):
    required = ("Voltage V", "Temperature °C", "Repetitions", "Duty share %", "Incumbent AC kW",
                "Candidate AC kW", "Combined uncertainty kW")
    if tuple(r.get("Load %") for r in rows) != BENCH_LOADS:
        raise ValueError("Retain the four protocol load points.")
    if any(not isinstance(r.get(k), Real) or not isfinite(r[k]) for r in rows for k in required):
        return "Untested / incomplete", None, None
    if any(not str(r.get("Conditions") or "").strip() or not str(r.get("Record") or "").strip() for r in rows):
        return "Untested / incomplete", None, None
    if any(r["Voltage V"] <= 0 or r["Repetitions"] < 2 or int(r["Repetitions"]) != r["Repetitions"]
           or not 0 <= r["Duty share %"] <= 100 or r["Combined uncertainty kW"] < 0
           or min(r["Incumbent AC kW"], r["Candidate AC kW"]) < 12 * r["Load %"] / 100 for r in rows):
        raise ValueError("Check voltage, repetitions, duty, uncertainty and matched DC output per point.")
    if abs(sum(r["Duty share %"] for r in rows) - 100) > .001:
        raise ValueError("Duty shares must total 100%.")
    delta = sum(r["Duty share %"] * (r["Incumbent AC kW"] - r["Candidate AC kW"]) for r in rows) / 100
    bound = sum(r["Duty share %"] * r["Combined uncertainty kW"] for r in rows) / 100
    if any(check == "Fail" for check in checks):
        return "Qualification failed", delta, bound
    if len(checks) != 5 or any(check != "Pass" for check in checks):
        return "Qualification pending", delta, bound
    return ("Bench screen passed" if delta > bound else "Improvement below uncertainty"), delta, bound
