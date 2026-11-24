# ThermoCircular 1.0.0 implementation report

## Scope delivered

The Streamlit app provides ten views with an immutable official baseline, a scenario builder with all native inputs, A–D and matched-hardware comparisons, fixed-installed dispatch, electrical and thermal ledgers, renewable matching, cash flow and sensitivities, buyer emissions comparisons, circular inventory, gated Austrian site scoring, Infineon bench and validation records, a source/risk browser, exports and a six-view jury sequence.

The CLI uses the same adapter as the UI. It supports the native seven-column hourly CSV, scenario settings or replay recipes. Desktop scenarios and registers can persist in SQLite. The public configuration uses separate session workspaces. All calculations operate on bundled or supplied files without fetching live data.

## Results

| Quantity | Audited result |
|---|---:|
| Case D useful buyer heat per year | 27.627110273393 GWhth |
| Case D physical grid imports per year | 462.49 GWh, displayed |
| Case D heat-only 15-year NPV | €0.364645964442m |
| First-stage tariff floor | €83.641010370156/MWhth |
| Second-stage increment | 10.175431996848 GWhth/year, −€2.009652350465m |
| Case D hourly renewable matching | 44.050959361890% |
| Matched installed baseline dispatch NPV difference | €0.000m |

## Verification

- Python 3.12.10, Streamlit 1.62.0, NumPy 2.5.2, pandas 3.0.5, Plotly 7.1.0, openpyxl 3.1.5 and Pydantic 2.13.5 on Windows.
- The baseline script verified 18 bundled hashes and reproduced all four original result CSVs cell by cell, including four annual cases, three staged investments, 21 stress cases and 8,760 hourly trace rows. Numeric tolerance is absolute 1e−6.
- The application test suite has 34 passing cases. It covers full adapter parity, adverse outcomes, thermal and electrical identities, strict hourly inputs, case comparisons, saved scenario replay, the six jury steps, sensitivity runs and exports.
- Chromium checks reached all ten views at 1,440 and 390 pixels without horizontal overflow of the main view. The Windows launcher successfully served the app and returned an actionable message on a port conflict.
- Browser workflow rejected a malformed hourly CSV, ran a valid upload, saved the scenario, opened the JSON/XLSX downloads and confirmed that a second public-mode session did not see the saved scenario. The CLI produced annual, hourly, stress, JSON, XLSX and HTML outputs.
- Five measured adapter runs gave a median of 0.173 seconds for the official baseline and 0.128 seconds for the winter-price case. The 21-case suite took 2.869 seconds. These times exclude Streamlit startup and rendering.

## Source decisions and limitations

The model and golden data remain byte-identical to the independent audited folder and the ZIP. Earlier D9 comparisons appear in the historical section with their original PUE and module count. The PSU view uses Infineon's specified 96.5% minimum at 230 V AC across 30–100% nominal load and the reported 97.8% peak. The app assigns no campus efficiency credit to that reference design.

The core interface is bilingual. Archived source text, some engineering table fields and downloadable reports are English-first. Open external gates include a firm grid allocation, parcel, buyer contract, route, metered pilot and hardware qualification. The optional 2035 competition task remains unclaimed.

The team authorised release of the app, audited model and synthetic scenario data. The repository is configured for Streamlit Community Cloud using app.py and Python 3.12. See README.md for the Cloud build and public URL settings.

## Files and commands

- app.py, thermocircular and assets contain the UI, native-model adapter, assessment logic, persistence and exports.
- vendor/audited_model and data hold the exact audit snapshot and selected evidence catalogues.
- scripts, tests and the pinned requirements support replay and verification.
- MODEL_CARD.md, DATA_DICTIONARY.md and SOURCE_NOTICES.md record method, outputs, source boundaries and publication scope.
- START_THERMOCIRCULAR.bat and .streamlit/config.toml provide desktop and Community Cloud entry points.

Start with START_THERMOCIRCULAR.bat. See README.md for CLI commands, Cloud setup and rollback.
