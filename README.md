# ThermoCircular AI Campus

An interactive engineering demonstrator for the Infineon InnoScope 2026 challenge. Test a 50–100 MW-class Austrian AI campus over 8,760 hours, trace heat to the buyer meter, and compare staged procurement under electricity, demand and cost stress.

## Run locally

Use **Python 3.12**. On Windows, double-click **START_THERMOCIRCULAR.bat** or run it in a terminal. It checks the pinned dependencies and prints the local URL. If port 8501 is occupied, use:

    START_THERMOCIRCULAR.bat 8502

For macOS or Linux:

    python3.12 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
    TC_LOCAL_STORAGE=1 python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501

The first dependency installation needs access to your package index. After installation, the app and all bundled analyses work offline. The Windows launcher and the command above store desktop scenarios and editable registers in .data/scenarios.sqlite3. Back up that file before resetting a desktop installation. The public build defaults to a separate in-memory workspace per browser session. Scenario JSON is the portable way to retain a run.

## Jury walkthrough

The sidebar starts collapsed. Use **Jump to section** on any screen to move around, or open **Menu** for the full navigation list and language setting.

1. Open **Overview** for the reference design and annual metrics. Select a system block to follow the electrical or thermal flow.
2. Open **Investment**. The first 5 MWth module adds 27.63 GWhth/year and €0.365m heat-project NPV. A second adds 10.18 GWhth/year and reduces incremental NPV by €2.010m.
3. Run **Winter price stress**. Open **Heat dispatch → Installed comparison** for the operator gain, extra buyer backup and joint emissions increase on the same equipment. Case D defers new investment in this stress.
4. Open **Impact & circularity** and switch the buyer heating comparator. The electricity and emissions comparisons use different meters and buyer assumptions.
5. Use **Jury mode** for a guided six-view walkthrough, or **Evidence & exports** for the stress suite, source registers, reproducibility manifest and downloads.

To edit inputs, open **Scenario lab**, load a preset or enter assumptions, then click **Run simulation**. The official reference is immutable. Closed input sections are still part of the form. A saved record contains its exact scenario recipe and an annual result snapshot. Opening it reproduces the run against the archived engine fingerprint.

## CLI and verification

    python -m thermocircular.cli --out run-baseline --stress
    python -m thermocircular.cli --recipe run-baseline/scenario.json --out run-replay
    python -m pip install -r requirements-dev.txt
    python scripts/verify_baseline.py
    python -m pytest -q

The CLI creates a new output directory. Add --settings with a JSON object of native inputs or --hourly with the bundled CSV structure. The verifier runs the original audit scripts in a temporary directory, checks the SHA-256 manifest, and compares every cell in the four golden CSVs. It preserves all source files.

## Streamlit Community Cloud

After team consent and source publication review, publish this application directory at the root of the GitHub repository. Include app.py, requirements.txt, .streamlit, assets, thermocircular, vendor, data and the accompanying documentation. The app requires no secrets.

In [Streamlit Community Cloud](https://share.streamlit.io), create an app and pick the GitHub repository **syeddanishali17/ThermoCircularChallenge**, branch **main**, entry point **app.py**, and **Python 3.12**. Set the optional subdomain if available. Verify Overview, the winter-price demo, export and a second independent session at the public URL. Leave TC_LOCAL_STORAGE unset in a public deployment.

For rollback, use the last verified commit on a dedicated deployment branch or revert the offending commit and redeploy. For a local recovery, keep the SQLite backup and run a clean checkout of the last verified version. To launch the reference without opening stored records, start normally and select Overview or Jury mode.

The frontend styles live in assets/style.css and .streamlit/config.toml. Shared navigation, metric and chart styling is in thermocircular/ui.py. For rollback of the frontend refinement, revert its commit on main and allow Streamlit to redeploy app.py at the existing address. The verified pre-refinement tree is Git commit a3bb37f.

### Troubleshooting

- An occupied port is handled by selecting another port on the launcher. Start one local server per intended URL.
- If dependency installation fails, check your active Python version and access to your package index, then re-run the launcher.
- An uploaded CSV must match the sample header and all 8,760 timestamps in fixed CET. It supplies hourly carbon intensity and solar shape, even if the scenario selects a different regional proxy.
- A scenario JSON fingerprint mismatch means the original recipe or exact engine version is needed to replay it.
- A failed design or hourly screen retains diagnostic traces. Zero selected modules can mean deferral while a separately configured installed unit still dispatches.
- The interface is English-first. The principal navigation and controls are bilingual. Archived evidence, engineering field names and exports retain their source language.

See [MODEL_CARD.md](MODEL_CARD.md), [DATA_DICTIONARY.md](DATA_DICTIONARY.md),
[SOURCE_NOTICES.md](SOURCE_NOTICES.md) and the [implementation report](IMPLEMENTATION_REPORT.md).
