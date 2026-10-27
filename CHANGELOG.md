# Changelog

## Unreleased

- Give Claude Sonnet 4.5 its own record (`claude-sonnet-4-5`, aliases
  `claude-sonnet-4-5-20250929`, `anthropic/claude-sonnet-4-5`). Its ids were
  aliases of Claude Sonnet 5, which EcoLogits sizes smaller. Sonnet 4.5 now
  uses EcoLogits' own estimate, 76B active (44–132B) instead of Sonnet 5's
  60B (29–100B), which raises its energy, carbon and water estimates by
  about 27% at fixed tokens and provider. This corrects the mapping; it is
  not a change in the model's actual energy use.
- Give GPT-5.1 its own record (`gpt-5.1`, alias `gpt-5.1-2025-11-13`); it
  was an alias of GPT-5. EcoLogits sizes the two the same, so its estimates
  do not change.

## 0.2.4 — 2026-10-27

Method version unchanged (0.3.0): every id that resolved in 0.2.3 gives the
same numbers. Ids that raised `UnknownModelError` before can now resolve,
through new records, wider alias matching or proxies. The result gains a
`proxy` field (`null` unless a proxy was used).

- Add MiniMax M3.1 Flash (`minimax-m3.1-flash`): 23B active / 428B total
  from its model card.
- Add 20 open-weight models: Kimi K2.6, K2 Thinking and K2 Instruct 0905;
  GLM-5.2, 5.1 and 4.7; DeepSeek V3.2, V3.1 and R1; MiniMax M2.7 and M2.1;
  Llama 4 Maverick and Scout, Llama 3 70B and 8B, Llama-3-Groq-70B-Tool-Use,
  AfroLlama V1; Mixtral 8x7B Instruct; Qwen3-VL-235B-A22B; Sarvam-M. Sizes
  are from model cards or creator reports (tier 1), or computed from
  `config.json` where the card is silent (tier 2). Llama 4 Scout gets an
  ML.ENERGY H100 measurement.
- Add closed models from EcoLogits' estimates (tier 2): GPT-4 Turbo, GPT-4,
  GPT-3.5 Turbo, GPT-5.4, Gemini 2.5 Pro, Gemini 2.5 Flash, and the Gemini 3
  Flash and 3.1 Flash-Lite previews, with the snapshot ids their vendors
  list as aliases.
- Give Gemini 3.7 Flash its own record; its ids were aliases of Gemini 3.8
  Flash. Estimates are unchanged, since EcoLogits sizes both the same.
- Add Azure OpenAI deployment names in use as aliases of GPT-4o, GPT-4o
  mini, GPT-4 Turbo, GPT-4 and GPT-3.5 Turbo.
- A prefixed alias now also matches the same id behind another prefix, or
  none: `accounts/fireworks/models/kimi-k3-fast` resolves through Kimi K3's
  `accounts/fireworks/routers/kimi-k3-fast` alias. A last segment shared by
  aliases of two different models stays unresolved rather than guessing.
- Proxies: a record can list `proxies`, ids of related models (an earlier
  snapshot or a model the vendor says it is based on) that have no size or
  estimate of their own. `estimate` uses the record for them with the size
  treated as an assumption (tier 3, at least ×2.5 either way), measured
  energy dropped, confidence `low`, the new reason
  `model_inferred_from_sibling` and a new `proxy` field in the result.
  Every other unknown model still raises `UnknownModelError`.
- Seed proxies: `chatgpt-4o-latest` and the `gpt-4o-realtime-preview`
  snapshots under GPT-4o, `gpt-realtime` under GPT Realtime 1.5, and
  `gemini-3-pro-preview` under Gemini 3.1 Pro.

## 0.2.3 — 2026-10-18

Data-only release; method version unchanged (0.3.0).

- Add Muse Wonder (`muse-wonder-1.0`, alias `meta/muse-wonder`). Meta has
  not disclosed its size; 164B active (90–300B) is a tier-3 proxy from
  gpt-5.6-sol, which has the same list price, in EcoLogits.
- Add Gemini 4 Argon (`gemini-4-argon`, aliases `google/gemini-4-argon`,
  `gemini/gemini-4-argon`). No size estimate is published yet; 268B active
  (120–600B) is a tier-3 proxy spanning EcoLogits' estimates for Gemini 3.1
  Pro and Gemini 2.5 Pro. It will be replaced once an estimate is published.
- Register `dev.meta.ai` as a provider-docs source.

## 0.2.2 — 2026-10-08

Data-only release; method version unchanged (0.3.0).

- Add GPT-6.1 Sol, Claude Sonnet 5.5 and Gemini 3.5 Flash-Lite using
  EcoLogits' published size estimates (tier 2), and Mistral Large 4 using
  its disclosed 52B active parameters (tier 1). Include the preview API's
  `mistral-large-4-0` alias.
- Replace Claude Opus 5.5's pricing/throughput assumption with EcoLogits'
  70–200B active-parameter estimate (tier 2). Its point estimate rises from
  80B to 118B, increasing energy, carbon and water estimates by 47.5% at
  fixed tokens and provider. This reflects revised evidence, not a change
  in the model's actual energy use.
- Infer the Mistral provider for its closed preview model; weights are
  not yet available as of this release.

## 0.2.1

Data-only release; method version unchanged (0.3.0).

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
