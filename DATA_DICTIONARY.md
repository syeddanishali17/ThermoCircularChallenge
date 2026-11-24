# Data dictionary

## Source manifest

data/source_manifest.json records SHA-256 for each archive member, the original ZIP and the files bundled for the app. The archived model and CSV bytes are preserved under vendor/audited_model. Extracted regional tables are derived from the specified D4 workbook sheets, and the evidence CSVs are catalogues of references. Verified-source citations indicate the provenance of a specific published claim, while scenario assumptions and benchmarks preserve their original status.

## Hourly input

| Column | Unit and representation |
|---|---|
| time_fixed_CET | Ordered local fixed UTC+01:00 stamps, YYYY-MM-DDTHH:MM, 2025 only |
| temp_C | Dry-bulb temperature, °C |
| pv_MWh_per_MWp | 1-hour PV yield per installed MWp, between zero and one |
| it_relative_load | Mean-one normalized shape, 0.60 is applied internally for reference scale |
| import_price_EUR_MWh | Hourly wholesale scenario price, €/MWh, can be negative |
| grid_tCO2e_MWh | Electricity-generation proxy, tCO₂e per MWh |
| customer_demand_MWth | Required power at the buyer boundary before acceptance and outages |

With an uploaded file, native price and heat scaling still apply. The source supplies the hourly carbon column and solar shape. With the generated proxy, carbon is the configured constant and Graz adjusts monthly solar shape. Linz uses Vienna solar. No acceptance column is accepted by the native input parser.

## Hourly output

All exported timestamps are fixed CET (UTC+1). Interval power values in MW or MWth are average power over one hour. Annual and monthly energy sums use the one-hour interval divided by 1,000 to report GWh or GWhth.

| Key or family | Meaning |
|---|---|
| IT_MW, facility_MW, campus_gross_MW | Computing, facility-inclusive electricity, and facility plus heat-plant electricity |
| pv_MW, pv_used_MW, grid_export_MW | On-site solar generation, self-used PV and outgoing meter flow |
| grid_MW, grid_limit_MW | Physical grid imports and binding maximum for each hour |
| offsite_hydro_MW, offsite_wind_MW, matched_offsite_MW | Illustrative generation and hourly matched volume |
| unmatched_grid_MW | Physical import less illustrative matching |
| required_heat_MWth, accepted_heat_MWth | Buyer load and envelope the buyer will accept |
| condenser_MWth, source_MWth, delivered_MWth | Condenser output, recovered IT heat and buyer-meter output after losses |
| thermal_loss_MWth, backup_MWth, rejected_IT_MWth | Network loss, buyer residual need and IT heat rejected |
| heat_plant_MW, COP | Compressor plus auxiliary draw, and equipment COP |
| source_ceiling_MWth, usable_grid_headroom_MW | Available capture and pre-heat electrical headroom |
| unconstrained_accepted_MWth, grid_limited_MWth | Thermal target before and after hourly headroom |
| power_price_EUR_MWh, carbon_t_MWh | Actual modeled input price and grid factor for the hour |
| positive_variable_margin, beats_customer_carbon | Audited binary dispatch gate outcomes |

## Annual outputs

- Suffixes give the unit: MW/MWth for power, GWh/GWhth for annual energy, MEUR for millions of euro, ktCO2e for annual thousand tonnes, pct for the percentage on a 0–100 scale unless described as an annual generation ratio.
- nameplate_feasible and hourly_grid_excess_MW are separate physical tests. Greater than 1e−9 MW hourly excess fails the hourly check.
- annual_renewable_matching_pct is annual supply availability versus consumption, and may exceed 100%. hourly_renewable_matching_pct uses each hour's coincidence. wholly_matched_hours counts near-zero unallocated imports.
- Native grid_direct_ktCO2e is the electricity-generation proxy associated with grid consumption. combined_gas_comparator_ktCO2e adds configured buyer fuel. Post-processed electrified comparators apply the hourly grid proxy to buyer electricity.
- The additional impact comparison and its HTML/XLSX export use a 90% gas boiler at 0.202 tCO₂e/MWh of gas. The audited D dispatch retains its configured buyer factor, listed in Inputs.
- Null DCF outputs mean undefined. For example, zero delivery has no break-even tariff.

## Reproducible scenario

scenario.json records format, engine and adapter versions, input/status hashes, input settings, teaching clock and fixed module count. The exact driving bytes are base64-encoded only for a user upload. The scenario ID fingerprints settings, engine, proxy or uploaded input and fixed equipment. This app stores results in engineering units independent of interface language.
