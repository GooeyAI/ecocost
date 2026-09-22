# API reference

ecocost 0.1.0. The public API is one function, its result type and two
errors:

```python
from ecocost import estimate, EstimateResult, UnknownModelError, UnknownProviderError
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
    base_url: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    timestamp: datetime | None = None,
) -> EstimateResult
```

Estimates one request.

| Parameter | Description |
|---|---|
| `model` | A model id, matched ignoring case. Provider-specific ids resolve through the `aliases` in `models.yaml`, and a trailing path segment is tried too, so `accounts/fireworks/models/gpt-oss-120b`, `openai/gpt-oss-120b` and `gpt-oss-120b` are the same record. |
| `provider` | A provider id from the [provider table](README.md#provider-ids), matched ignoring case, or `None` if you don't know who serves the request. Mapping an API endpoint, SDK or gateway name to an id is the caller's job; each provider's API hosts are published to help. |
| `base_url` | Optional. The API endpoint called, e.g. `https://inference.api.nscale.com/v1`, or just its host. Matched against the hosts providers publish; used only when `provider` is not given. An unlisted host is ignored. |
| `input_tokens` | Prompt tokens, **including** any cached ones. |
| `output_tokens` | Completion tokens, including reasoning tokens. |
| `cached_input_tokens` | The part of `input_tokens` served from a prefix cache. Charged at 10% of a fresh prefill. |
| `timestamp` | Accepted and ignored for now. Reserved for hourly grid intensity; pass it now so your call sites won't change. |

Returns the [output dict](#output), typed as `EstimateResult`. Raises:

- `UnknownModelError` or `UnknownProviderError` for an id it doesn't know
  ([details](#unknown-models-and-providers));
- `TypeError` for a non-string `model`, `provider` or `base_url`, or a non-integer token
  count;
- `ValueError` for an empty `model`, a token count below 0 or above 10¹², or
  `cached_input_tokens` greater than `input_tokens`.

```python
>>> r = estimate("gpt-oss-120b", provider="nscale", input_tokens=800, output_tokens=300)
>>> r["carbon"]
{'unit': 'gCO2e', 'value': 0.00178, 'min': 0.000427, 'max': 0.00708,
 'worst_case': {'min': 0.000116, 'max': 0.0309}}
>>> r["confidence"]["level"], r["confidence"]["reasons"]
('low', ['wue_assumed', 'utilization_assumed', 'serving_overhead_assumed', 'embodied_carbon_default'])
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

| Field | Type | Meaning |
|---|---|---|
| `model` | str | Resolved model id (aliases resolve to the canonical id) |
| `provider` | str | The provider the estimate used; see [how it's chosen](#unknown-models-and-providers) |
| `tokens` | `{input, output, cached_input}` | As passed |
| `carbon` | range, gCO2e | Operational + embodied |
| `energy` | range, Wh | At the meter: chip, host, idle capacity and PUE |
| `energy.primary_energy_mj` | float | Primary energy behind that electricity, MJ |
| `water` | range, mL | `on_site` + `generation` |
| `water.on_site` | range, mL | Data-centre cooling (operator WUE) |
| `water.generation` | range, mL | Water consumed generating the electricity (off-site). On hydro grids this is mostly reservoir evaporation attributed to hydropower |
| `confidence.level` | `"high" \| "medium" \| "low"` | From `ratio`: under 2 is high, under 5 medium, otherwise low |
| `confidence.ratio` | float | `carbon.max / carbon.min`; 1 when there are no tokens |
| `confidence.reasons` | list[str] | [Reason codes](#reason-codes), most important first |
| `electricity.region` | str | The provider's primary region id (see `regions.yaml`) |
| `electricity.country` | str | ISO 3166-1 alpha-2 |
| `electricity.gco2e_per_kwh` | float | Grid intensity used: the weighted mean over the provider's candidate sites when it discloses several |
| `electricity.gco2e_per_kwh_range` | `[min, max]` | Envelope over those sites |
| `electricity.primary_source` | str | Largest source in the primary region's mix |
| `electricity.mix` | dict[str, float] | Generation share by source (display only; carbon uses the intensity) |
| `electricity.dataset_year` | int | Year of the grid data |
| `breakdown.h100_seconds` | range, s | Work in H100-seconds, independent of the chip that ran it |
| `breakdown.usage.gco2e` | float | Operational carbon (grid electricity), point value |
| `breakdown.embodied.gco2e` | float | Embodied carbon (hardware manufacturing, amortised), point value |
| `assumptions.active_params_b` | `{min, max}` | Active parameters, billions |
| `assumptions.hardware` | list[str] | Chips the provider discloses; energy uses their envelope |
| `assumptions.chip_energy_vs_h100` | float | Weighted energy per H100-second of work, relative to an H100 |
| `assumptions.pue` | float | Data-centre PUE used |
| `assumptions.decode_utilization` | float | Decode utilization used on the FLOPs path |
| `assumptions.serving_overhead` | float | Host and idle overhead multiplier |
| `assumptions.method_version` | str | See [versioning](#versioning-and-caching) |
| `provenance.{model,provider,region,hardware}` | dict | Per-record `trust` (`unverified`, `machine_confirmed`, `human_reviewed`), `status` (`draft`, `stable`, `deprecated`), `generated_by`, `stale` |
| `requested` | `{model, provider, base_url}` | What you passed, before resolution |

`breakdown.usage + breakdown.embodied == carbon.value` and
`water.on_site + water.generation == water.value`, up to rounding.

## Reason codes

`confidence.reasons` names every input that was assumed rather than published.
It explains the confidence label, and it lists the figures a provider could
publish to tighten its estimates.

| Code | Meaning | Cleared by |
|---|---|---|
| `provider_unknown_fallback` | no `provider`, a `base_url` no provider publishes, and not a closed model | passing a provider id or `base_url` |
| `provider_inferred_from_model` | no `provider` or matching `base_url`; the closed model's vendor API was assumed | passing a provider id or `base_url` |
| `active_params_undisclosed` | closed model; size estimated from secondary sources | the vendor disclosing it, or a measurement |
| `active_params_estimated` | model size is tier 3 | a model card |
| `region_inferred` | provider's serving site is assumed | the provider publishing regions |
| `hardware_assumed` | provider's accelerator fleet is assumed | the provider publishing its fleet |
| `pue_assumed` | data-centre PUE is an industry default | a published PUE |
| `wue_assumed` | cooling water per kWh is a default | a published WUE |
| `utilization_assumed` | decode utilization is a default | measured energy for the model, or provider batch data |
| `serving_overhead_assumed` | host and idle overhead is a default | provider measurement |
| `grid_intensity_national_average` | grid figure is an assumed national average | a regional source |
| `embodied_carbon_default` | hardware lifetime and active fraction are policy defaults | a provider's actual lifetime and utilization |

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

Both errors are `LookupError`s with `.suggestions` (up to three close known
ids), `.contribute_url` and `.request_url`, plus `.model` or `.provider`, so
an application can catch them and show its own message.

**Without a provider id, the provider is inferred or defaulted**, in order:

1. `base_url`, if a provider publishes its host (`.ap-southeast-1.maas.aliyuncs.com`
   covers any subdomain);
2. for a closed model, its vendor's own API, from `first_party_provider` in
   `models.yaml`, with `provider_inferred_from_model` in `reasons`. Open-weights
   models are served by many providers, so there is no such inference;
3. otherwise `unknown-us`: US-wide region candidates and mixed-fleet PUE and
   WUE, with `provider_unknown_fallback` in `reasons`. The range is very wide
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
| `ecocost.loader.get_kb()` | The parsed knowledge base: `.models`, `.providers`, `.regions`, `.hardware` (dicts of typed records), `resolve_model(id)`, `resolve_provider(id, base_url=, model=)`, `provider_for_host(url_or_host)` |
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
- **Method version** (`assumptions.method_version`) changes when the
  calculation changes. The same inputs give different numbers across method
  versions.
- **Data** changes in any release, since that is the point of the PR model.
  Store `method_version` and the package version with any figure you persist,
  and recompute rather than compare figures across versions.
