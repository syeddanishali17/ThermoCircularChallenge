"""Offline CLI access to the same validation, engine and exports as Streamlit."""
import argparse
import json
from pathlib import Path

from .exports import config_bytes, csv_bytes, html_bytes, workbook_bytes
from .model import simulate, stress_suite
from .storage import parse_recipe
from .config import Settings
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--recipe", type=Path)
    inputs.add_argument("--settings", type=Path, help="JSON object with native settings")
    parser.add_argument("--hourly", type=Path, help="Approved native 2025 hourly CSV")
    parser.add_argument("--fixed-modules", type=int, choices=(0, 1, 2), default=1)
    parser.add_argument("--stress", action="store_true")
    parser.add_argument("--out", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    if args.recipe and (args.hourly or args.fixed_modules != 1):
        parser.error("A recipe already specifies its hourly input and fixed module count.")
    try:
        if args.recipe:
            settings, source, modules = parse_recipe(args.recipe.read_bytes())
        else:
            settings = Settings.model_validate_json(args.settings.read_bytes() if args.settings else b"{}")
            source = args.hourly.read_bytes() if args.hourly else None
            modules = args.fixed_modules
        run = simulate(settings, source, modules)
        stress = stress_suite(settings, source) if args.stress else None
        artifacts = {
            "scenario.json": config_bytes(run),
            "annual.csv": csv_bytes(pd.DataFrame(run.cases)),
            "hourly_D.csv": csv_bytes(run.traces["D"], index=True),
            "thermocircular.xlsx": workbook_bytes(run, stress),
            "summary.html": html_bytes(run, stress),
        }
        if stress is not None:
            artifacts["stress.csv"] = csv_bytes(stress)
        args.out.mkdir(parents=True, exist_ok=False)
        for name, content in artifacts.items():
            (args.out / name).write_bytes(content)
        print(json.dumps(run.metadata(), indent=2))
    except (OSError, ValueError, AssertionError) as error:
        parser.exit(2, f"Run failed: {error}\n")


if __name__ == "__main__":
    main()
