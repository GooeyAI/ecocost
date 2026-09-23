# API reference

ecocost 0.2.0. The public API is one function, its result type and three
errors:

```python
from ecocost import (
    estimate, EstimateResult, UnknownModelError, UnknownProviderError, UnknownRegionError,
)
```

It is pure and synchronous. The knowledge base (`ecocost/data/*.yaml`) is
parsed once per process on first use and cached.

- [`estimate`](#estimate)
- [Output](#output)
- [Reason codes](#reason-codes)
- [Unknown models and providers](#unknown-models-and-providers)
- [Types and helpers](#types-and-helpers)
- [Versioning and caching](#versioning-and-caching)

## estimate

```python
estimate(
    model: str,
    *,
    provider: str | None = None,
    endpoint: str | None = None,
    region: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
) -> EstimateResult
```

Estimates one request.

| Parameter | Description |
|---|---|
| `model` | A model id, matched ignoring case. Provider-specific ids resolve through the `aliases` in `models.yaml`, and a trailing path segment is tried too, so `accounts/fireworks/models/gpt-oss-120b`, `openai/gpt-oss-120b` and `gpt-oss-120b` are the same record. |
| `provider` | A provider id from the [provider table](README.md#provider-ids), matched ignoring case, or `None` if you don't know who serves the request. Mapping an API endpoint, SDK or gateway name to an id is the caller's job; each provider's API hosts are published to help. |
| `endpoint` | Optional. The API URL called, e.g. `https://inference.api.nscale.com/v1`, or just its host. Matched against the hosts providers publish; used only when `provider` is not given. An unlisted host is ignored. |
| `region` | Optional. A grid region id from `regions.yaml` (`US-VA`, `GB`, `SG`, …), matched ignoring case, for when you know where the request ran. It replaces the provider's region, including one implied by `endpoint`, and pins it: no candidate envelope or widening, and no `region_assumed`. PUE, WUE, hardware and utilization still come from the provider. Cloud region names such as `us-central1` are not accepted; map them to a grid id yourself. |
| `input_tokens` | Prompt tokens, **including** any cached ones. |
| `output_tokens` | Completion tokens, including reasoning tokens. |
| `cached_input_tokens` | The part of `input_tokens` served from a prefix cache. Charged at 10% of a fresh prefill. |

Returns the [output dict](#output), typed as `EstimateResult`. Raises:

- `UnknownModelError`, `UnknownProviderError` or `UnknownRegionError` for an id it doesn't know
  ([details](#unknown-models-and-providers));
- `TypeError` for a non-string `model`, `provider`, `endpoint` or `region`, or a non-integer token
  count;
- `ValueError` for an empty `model`, a token count below 0 or above 10¹², or
  `cached_input_tokens` greater than `input_tokens`.

```python
>>> r = estimate("gpt-oss-120b", provider="nscale", input_tokens=800, output_tokens=300)
>>> r["carbon"]["value"], r["carbon"]["min"], r["carbon"]["max"]
(0.00178, 0.000427, 0.00708)
>>> r["carbon"]["operational"]["value"], r["carbon"]["embodied"]["value"]
(0.00115, 0.000632)
>>> r["confidence"]["level"], r["confidence"]["reasons"]
('low', ['wue_assumed', 'serving_overhead_assumed', 'embodied_carbon_assumed'])
```

To estimate a run that called several models, call `estimate` once per model
and add the figures. Sum `min` and `max` too: it is the conservative choice,
since the requests share the same unknowns. To compare providers, call it once
per provider id with the same tokens.

Call `estimate` with the real token counts rather than scaling a per-1k
result: the likely range is propagated across input and output together, so
adding separately scaled input and output ranges would come out wider.

## Output

Every quantity is a **range object**:

```python
{"unit": "gCO2e", "value": 0.00178, "min": 0.000427, "max": 0.00708,
 "worst_case": {"min": 0.000116, "max": 0.0309}}
```

- `value` is the point estimate, `min`/`max` the likely range. Independent
  inputs are combined in quadrature, as in the
  [methodology](METHODOLOGY.md#ranges-and-confidence).
- `worst_case` has every input at its extreme at the same time.
- Numbers are rounded to 3 significant figures.
- A quantity also carries the inputs that produced it: `energy.pue`,
  `compute.decode_utilization`, `water.data_center.wue`. These are point
  values; the quantity's range already accounts for their uncertainty.

| Field | Type | Meaning |
|---|---|---|
| `model` | str | Resolved model id (aliases resolve to the canonical id) |
| `provider` | str | The provider the estimate used; see [how it's chosen](#unknown-models-and-providers) |
| `method_version` | str | Version of the calculation. Store it with any figure you keep; see [versioning](#versioning-and-caching) |
| `tokens` | `{input, output, cached_input}` | As passed |
| `carbon` | range, gCO2e | `operational` + `embodied` |
| `carbon.operational` | range, gCO2e | From generating the electricity the request used: `energy` × `grid.carbon_intensity` |
| `carbon.embodied` | range, gCO2e | From manufacturing the hardware, amortised over its lifetime and the request's share of `compute`. On a clean grid it can be a third of the total |
| `energy` | range, Wh | Electricity at the data centre's meter: `compute` converted to chip energy, then scaled by `serving_overhead` and `pue` |
| `energy.chips` | list[str] | Accelerators the provider is taken to run on, from `hardware.yaml`: disclosed, or guessed when `reasons` includes `chips_assumed`. With several, energy spans the range between them |
| `energy.chip_energy_vs_h100` | float | Energy these chips use for the same work as an H100, as a multiple: 0.75 means 25% less. Weighted average over `chips` |
| `energy.serving_overhead` | float | Multiplier for energy beyond the accelerators: host CPUs, memory, networking and capacity kept idle for peaks. 1.6 means 60% on top |
| `energy.pue` | float | Power usage effectiveness: the data centre's total power divided by the power reaching its servers. 1.09 means 9% extra for cooling and power conversion. Point value; the estimate uses its range |
| `primary_energy` | range, MJ | Raw energy taken from nature (fuel burned, or wind, sun and water captured) to generate and deliver `energy`. It is larger than `energy` because power plants and the grid lose energy: about 2.7× on the US grid, 1.2× on hydro grids. Not a measure of how clean the grid is: nuclear counts about 3×, like fossil fuel; use `carbon` for that |
| `water` | range, mL | Water consumed, i.e. evaporated and not returned to its source: `data_center` + `power_plant`. Water withdrawn and returned is not counted |
| `water.data_center` | range, mL | Water the data centre evaporates to cool its servers, in cooling towers or evaporative coolers: IT energy (`energy` ÷ `pue`) × the operator's WUE (litres per kWh of IT energy). Near zero for air- or closed-loop-cooled sites; this is the figure operators report |
| `water.data_center.wue` | float | Water usage effectiveness used: litres of water the data centre evaporates per kWh. Point value; the estimate uses its range |
| `water.power_plant` | range, mL | Water evaporated at the power plants that made the electricity: kWh × the grid's litres per kWh (WRI). Mostly thermal-plant cooling towers; on hydro grids, mostly evaporation from reservoirs, attributed to the electricity by a standard but contested convention. Usually larger than `data_center` |
| `compute` | range, H100-s | Work done, in H100-seconds: the seconds one H100 would take, whatever chip actually ran it |
| `compute.method` | `"measured" \| "model_size"` | How output tokens were costed: `measured` from the model's measured energy per token, `model_size` from its parameter count and `decode_utilization`. Input tokens always use the parameter count |
| `compute.active_params_billion` | `{min, max}` | Parameters the model uses per token, in billions. For a mixture-of-experts model, only the experts active for each token. Sets the compute for input tokens, and for output tokens unless the model has measured energy |
| `compute.decode_utilization` | float or `null` | Share of the chips' peak compute actually used while generating output tokens; low because output is produced one token at a time. `null` when `method` is `measured` |
| `confidence.level` | `"high" \| "medium" \| "low"` | From `range_ratio`: under 2 is high, under 5 medium, otherwise low |
| `confidence.range_ratio` | float | `carbon.max / carbon.min`; 1 when there are no tokens |
| `confidence.reasons` | list[str] | [Reason codes](#reason-codes), most important first |
| `grid.region` | str | The `region` you passed, else the provider's primary region id (see `regions.yaml`) |
| `grid.country` | str | ISO 3166-1 alpha-2 |
| `grid.carbon_intensity` | range, gCO2e/kWh | Grid intensity used (lifecycle). When the provider discloses several candidate sites, the value is their weighted mean and min/max their envelope |
| `grid.largest_source` | str | Largest source in `grid.mix` |
| `grid.mix` | dict[str, float] | Generation share by source in `grid.region` (display only; carbon uses `carbon_intensity`). With candidate sites this is the primary region's mix, not a blend |
| `grid.data_year` | int | Year of the grid data |
| `provenance.{model,provider,region,hardware}` | dict | Per-record `trust` (`unverified`, `machine_confirmed`, `human_reviewed`), `status` (`draft`, `stable`, `deprecated`), `generated_by`, `stale` |
| `requested` | `{model, provider, endpoint, region}` | What you passed, before resolution |

`carbon.operational + carbon.embodied == carbon` and
`water.data_center + water.power_plant == water`, for `value`, `min` and `max`,
up to rounding.

## Reason codes

`confidence.reasons` lists every input that wasn't backed by published data,
most important first. It explains why the range is as wide as it is, and it
doubles as the list of figures a provider could publish to narrow its
estimates.

Each code is `<input>_<status>`, where `<input>` matches the output field it
affects and `<status>` is one of:

- `assumed`: a default with no evidence specific to this model, provider or
  region (tier 3);
- `inferred`: worked out from indirect evidence;
- `unknown`: nothing to go on, so wide defaults are used;
- `undisclosed`: the owner exists but doesn't publish it.

| Code | Meaning |
|---|---|
| `provider_unknown` | Nobody could be identified as serving the request: no `provider`, an `endpoint` no provider publishes, and an open-weights model. The estimate assumes an unnamed US provider, spread across every US grid that hosts cloud capacity, with an industry-average data centre. Expect a very wide range. |
| `provider_inferred_from_model` | No `provider` or recognised `endpoint` was given, so the closed model's own vendor is assumed to serve it (`claude-*` → `anthropic`, `gpt-*` → `openai`). Wrong if the request actually went through a reseller or cloud marketplace. |
| `active_params_undisclosed` | The model is closed and its vendor doesn't publish its size. The parameter count comes from outside estimates and can be off by about 3×. For closed models this is usually the biggest uncertainty after utilization. |
| `active_params_assumed` | No model card or reliable source gives the model's active parameter count, so it is a rough estimate. Not reported when the model has measured energy per token, which replaces the parameter count. |
| `region_assumed` | The provider doesn't say where it runs inference. The grid figures cover every site it plausibly uses, or a widened national average, so `grid.carbon_intensity` has a wide range. Pass `region` if you know the site. |
| `chips_assumed` | The provider doesn't say which accelerators it uses; `energy.chips` is a guess, usually the H100. Affects energy and embodied carbon. |
| `pue_assumed` | The provider doesn't publish its data centres' PUE (total facility power divided by IT power), so an industry figure is used. |
| `wue_assumed` | The provider doesn't publish its cooling water use per kWh (WUE), so `water.data_center` uses a default with a wide range. |
| `decode_utilization_assumed` | How much of the chip's peak compute is used while generating output tokens depends on batch size, which no provider publishes. A default of about 12% is used. This is usually the largest single source of uncertainty in the estimate. Not reported when the model has measured energy per token, which replaces it. |
| `serving_overhead_assumed` | Energy beyond the accelerators (host CPUs, memory, networking and capacity kept idle for peaks) uses a default multiplier taken from one published fleet. |
| `grid_intensity_assumed` | The carbon intensity for `grid.region` is itself a rough estimate rather than taken from a grid dataset. |
| `embodied_carbon_assumed` | Spreading manufacturing emissions over each request depends on how many years the hardware is kept and how busy it is, which operators don't publish. Policy defaults are used (3–6 years, 50–100% busy). Present on almost every estimate. |

New codes may be added in minor versions; treat unknown codes as "assumed
input".

## Unknown models and providers

**An unknown model raises.** Model size drives the whole estimate, so ecocost
won't guess it:

```python
>>> estimate("gpt-oss-120", provider="fireworks")
UnknownModelError: ecocost has no data for model 'gpt-oss-120'.
  Did you mean 'gpt-oss-120b', 'gpt-oss-20b'?
  Another id for a known model? Add it to that model's `aliases`.
  A new model? Add it: https://github.com/GooeyAI/ecocost/blob/main/CONTRIBUTING.md#adding-a-model
  Or request it: https://github.com/GooeyAI/ecocost/issues/new?title=Add+model%3A+gpt-oss-120
```

**An unrecognised provider id raises too**, with the same kind of message.
A typo such as `"nscal"` would otherwise silently estimate a different site,
which can be 10x off:

```python
>>> estimate("gpt-oss-120b", provider="fireworkz")
UnknownProviderError: ecocost has no provider 'fireworkz'.
  Did you mean 'fireworks'?
  Don't know who serves the request? Pass provider=None.
  ...
```

**An unrecognised `region` raises `UnknownRegionError`** for the same reason:
`"US-VAA"` suggests `'US-VA'` rather than falling back to the provider's site.

All three errors are `LookupError`s with `.suggestions` (up to three close known
ids), `.contribute_url` and `.request_url`, plus `.model`, `.provider` or `.region`, so
an application can catch them and show its own message.

**Without a provider id, the provider is inferred or defaulted**, in order:

1. `endpoint`, if a provider publishes its host (`.ap-southeast-1.maas.aliyuncs.com`
   covers any subdomain);
2. for a closed model, its vendor's own API, from `first_party_provider` in
   `models.yaml`, with `provider_inferred_from_model` in `reasons`. Open-weights
   models are served by many providers, so there is no such inference;
3. otherwise `unknown-us`: US-wide region candidates and mixed-fleet PUE and
   WUE, with `provider_unknown` in `reasons`. The range is very wide
   and the confidence `low`, on purpose.

Callers often can't tell who serves a request, and what a provider sets
(site, PUE, water use) varies within known bounds, where a model's size can be
off by 100x; that's why a missing provider degrades gracefully and a missing
model doesn't.

## Types and helpers

Not needed for normal use, but stable enough to import:

| Import | What |
|---|---|
| `ecocost.EstimateResult` | `TypedDict` of the output; the nested types are in `ecocost.result` |
| `ecocost.loader.get_kb()` | The parsed knowledge base: `.models`, `.providers`, `.regions`, `.hardware` (dicts of typed records), `resolve_model(id)`, `resolve_region(id)`, `resolve_provider(id, endpoint=, model=)`, `provider_for_host(url_or_host)` |
| `ecocost.schema.Factor` | One sourced number: `value, unit, tier, min, max, source, note` |
| `ecocost.schema.Range` | Propagated uncertainty: `lo, mid, hi` (likely), `wlo, whi` (worst case) |
| `ecocost.schema.Tier` | `primary = 1`, `derived = 2`, `assumed = 3` |
| `ecocost.schema.{Model, Provider, Region, Hardware}` | The record types, each with a `provenance` |
| `ecocost.display` | `format_grams`, `format_wh`, `format_ml` (2 significant figures, no scientific notation, unit scaling) |
| `ecocost.calc.METHOD_VERSION` | Current method version string |

To list provider ids at runtime: `list(get_kb().providers)`. Each provider's
published API hosts are in `.hosts`; a leading dot means any subdomain.

## Versioning and caching

- **Package version** (`ecocost.__version__`) follows semver for the Python API
  above. In 0.x, minor versions may change it; changes will be listed in the
  release notes.
- **Method version** (`method_version`) changes when the
  calculation changes. The same inputs give different numbers across method
  versions.
- **Data** changes in any release, since that is the point of the PR model.
  Store `method_version` and the package version with any figure you persist,
  and recompute rather than compare figures across versions.
