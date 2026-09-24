# Changelog

## Unreleased

- Models: `claude-opus-4-6`, `claude-opus-4-7`, `claude-opus-4-8`,
  `claude-sonnet-4-6` and `claude-fable-5` (EcoLogits sizes, tier 2);
  `gpt-realtime-1.5`, `gpt-realtime-2.1-mini` and `muse-spark-1.2` (proxies
  of same-priced siblings, tier 3).

## 0.2.0

Breaking release. Method version 0.3.0 (see METHODOLOGY.md).

- `estimate` takes `region`, a grid id from `regions.yaml`, for callers who
  know where a request ran. It replaces the provider's region (including one
  implied by `endpoint`) as a pinned site; the provider still sets PUE, WUE
  and hardware. An unknown id raises the new `UnknownRegionError`.
  `requested` now includes `region`.
- `base_url` is renamed `endpoint`, since it takes a bare host as well as a
  URL. `requested.base_url` is now `requested.endpoint`.
- `timestamp` is removed; it was accepted but never used. It will come back
  with hourly grid intensity.
- Output renamed and reshaped (method version 0.3.0). Every quantity is now a
  range object with its unit inside, and each total holds its parts:
  - `breakdown.usage.gco2e` / `breakdown.embodied.gco2e` → `carbon.operational`
    / `carbon.embodied`, now ranges; `breakdown.h100_seconds` → `compute`;
    `breakdown` is gone.
  - `energy.primary_energy_mj` → `primary_energy`, a range in MJ.
  - `water.on_site` / `water.generation` → `water.data_center` /
    `water.power_plant`.
  - `electricity` → `grid`; `gco2e_per_kwh` and `gco2e_per_kwh_range` →
    `grid.carbon_intensity` (range); `primary_source` → `largest_source`;
    `dataset_year` → `data_year`.
  - `confidence.ratio` → `confidence.range_ratio`.
  - `assumptions` is gone; each value now sits in the quantity it produced.
    `chips` (was `hardware`), `chip_energy_vs_h100`, `serving_overhead` and
    `pue` are in `energy`; `active_params_billion` (was `active_params_b`) and
    `decode_utilization` are in `compute`, with a new `compute.method`
    (`measured` or `model_size`). `decode_utilization` is `null` for measured
    models, which don't use it. `water.data_center.wue` is new.
  - `assumptions.method_version` → top-level `method_version`.
- Reason codes renamed to `<input>_<assumed|inferred|unknown|undisclosed>`:
  `active_params_estimated` → `active_params_assumed`, `region_inferred` →
  `region_assumed`, `hardware_assumed` → `chips_assumed`,
  `utilization_assumed` → `decode_utilization_assumed`,
  `grid_intensity_national_average` → `grid_intensity_assumed`,
  `embodied_carbon_default` → `embodied_carbon_assumed`,
  `provider_unknown_fallback` → `provider_unknown`.
- Fix: `water.data_center` applied WUE to energy at the meter, which already
  includes PUE, overstating it by the PUE factor (9% for Google, 20% at the
  default). WUE is defined per kWh of IT energy (The Green Grid, ISO/IEC
  30134-9), so it now applies before PUE. `water.power_plant`, carbon and
  energy are unchanged.
- `decode_utilization_assumed` is no longer reported for models with measured
  energy per token: the measurement replaces decode utilization, so the
  default never entered the estimate.

## 0.1.0

First public release. Method version 0.2.0 (see METHODOLOGY.md).

- `estimate(model, *, provider, base_url, input_tokens, output_tokens,
  cached_input_tokens, timestamp)` returns carbon, energy and water for one
  request, each with a likely range and a worst case, a computed confidence
  label, and reason codes naming every assumed input. Typed as
  `EstimateResult`.
- The provider comes from `provider`, else the host of `base_url`, else a
  closed model's vendor, else wide US defaults; `reasons` says which.
- `UnknownModelError` and `UnknownProviderError` suggest close matches and
  link to how to add the record. Ids match ignoring case.
- Knowledge base: 17 providers, 19 grid regions, 5 accelerators and the
  models in `ecocost/data/models.yaml`, each value sourced, tiered and carrying
  OKF provenance. Every cited source is registered with its licence in
  `sources.yaml`; attribution is in NOTICE.
- The data is an agent-generated draft awaiting human review
  (`status: draft`); corrections are welcome as pull requests.
