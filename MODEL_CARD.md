# Model card

## Intended use

Research and competition screening for a staged Austrian AI data centre. Compare equivalent workload and buyer heat obligations within a run. The model clock is a synthetic 2025 fixed-CET year. An uploaded trace retains user-supplied unverified status and must follow the same clock. Results are deterministic rules, useful for sensitivities and for defining the evidence needed for a pilot.

## Lineage

The archived audited model was imported from ThermoCircular_Complete_Research_2026.zip and matched byte-for-byte against the separately extracted audited engineering folder. Golden results were reproduced with the original CLI. The v2 submission and pitch handoff determine interpretation and display rounding. Earlier D9 numerical results appear only in the historical reconciliation.

- A uses a conventional campus, no PV and no heat export.
- B uses an efficient campus with PV and no heat export.
- C independently sizes its heat investment without the binding grid allocation at the planning step. It applies the actual grid ceiling in hourly operation.
- D selects sequential capacity only when hourly and design checks pass and the incremental NPV and buyer heat thresholds are met. Hourly dispatch also checks variable economics and the buyer emissions threshold.
- The matched-hardware ablation keeps D's installed count, workload and buyer requirement and uses fixed physical dispatch. The additional installed-equipment analysis may hold 0, 1 or 2 modules fixed independently of investment.

## Boundaries

- 15-year DCF at 6%, 5% distribution loss, 1% auxiliaries, 80% IT heat capture ceiling, 60% mean reference IT utilisation and 0.03 L/kWh IT water allowance.
- Facility PUE excludes the separate heat plant. Design nameplate uses 1.30 or 1.24 overhead with the relevant modules at COP 3 plus auxiliaries. Sampled peaks are hourly imports under scenario profiles.
- The heat DCF includes module and route costs, electricity and fixed operating costs. The intervention perimeter adds the efficient facility package and its modelled power costs. Total campus capital and buyer backup costs fall outside the native operator DCF.
- Renewable matching uses illustrative hydro and wind profiles. Physical imports and location electricity-generation proxies remain separate.
- The historical D9 model used a two-module build and 1.14 PUE. Its import and resistance savings estimates accompany that earlier configuration only.
- The upper-layer site, equipment, bench and roadmap records are decision checklists and calculators. Replay uses static hourly accounting with a proposed fallback. There is no clinical, live electrical, thermal-plant or telemetry interface.

## External verification still required

Document grid allocation, parcel and zoning, buyer load and acceptance, temperatures, route, tariff, backup terms, approved safety and contingency studies, and the component or pilot test. No actual site, measured load, physical pilot result, signed buyer terms, market-based emissions or optional 2035 completion are asserted by the model.
