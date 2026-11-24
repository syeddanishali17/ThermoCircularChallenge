# Reproduce the engineering comparison

Requires Python 3.10 or later and NumPy. From this directory run:

```text
python -m pip install numpy
python optimize.py --out reproduced
python check_model.py --results reproduced
```

For a site sensitivity, run `python optimize.py --site Graz --grid-mw 100 --it-mw 75 --pipe-km 2 --heat-scale 0.8 --heat-tariff 92 --out graz_case`. Use a new output directory for every scenario. The default stress set is reproducible. `--help` lists adjustable variables, including capacity, prices, solar, heat pump, pipe costs and equal-work replacement assumptions. `--hourly-inputs` accepts an independently assembled timestamped CSV that follows the packaged legacy schema. It replaces the synthetic profiles, and its carbon column overrides the constant factor.

The default clock is 2025 in continuous fixed CET (no DST) and contains 8,760 hours. The default weather and heat inputs are proxies propagated from the earlier model. PV uses monthly PVGIS-based yield for Vienna, or a separate monthly Graz shape. Linz currently uses Vienna values as an explicit placeholder. The hydro and wind generation profiles used in the portfolio are illustrative, not measured or contractual. The rack fleet is held equivalent across the four energy cases. A separate same-work component calculation screens a candidate refresh.

`scenario_results.csv` summarizes A conventional, B modern, C independently planned, and D coordinated. `investment_steps.csv` isolates 0, 1 and 2 modules, and `stress_tests.csv` records procurement and installed-module dispatch under disruption. `hourly_D.csv` records facility meter and thermal quantities for the selected D case. An hour with positive pre-heat grid constraint violation is infeasible. The model neither sheds IT silently nor uses PV as firm connection capacity.

Hourly dispatch solves a separable continuous decision within a bounded output range. It has an economic and an emissions condition for D. The search enumerates three investment choices. There is no storage, minimum stable compressor loading or endogenous workload scheduling. Formal implementation requires site constraints, monthly tests, customer backup verification and audited data. Avoided customer heat stays outside the campus emissions inventory, while joint electricity/heat service allows comparisons.

The legacy file is an unmodified copy for rollback. Restore the legacy calculation by keeping the packaged old archive intact. `python check_model.py --archive path/to/InnoScope_Research_2026.zip` verifies CRC and required legacy files before repeating the independent arithmetic checks. Running the legacy script directly writes CSVs next to the legacy script, so use a scratch copy for exact legacy regeneration.
