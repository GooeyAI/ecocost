# ecocost

```bash
pip install ecocost
```

Per-request carbon, energy and water estimates for AI inference, each with a
likely range and a confidence label computed from the evidence behind it.
Every input is sourced and tiered, and the knowledge base in `ecocost/data/`
is open to pull requests from providers, hardware makers and researchers.

Maintained by [Gooey.AI](https://gooey.ai). Pure Python; the only dependency
is PyYAML.

## Quick start

```python
from ecocost import estimate

r = estimate(
    "gpt-oss-120b",
    provider="nscale",
    input_tokens=800,
    output_tokens=300,
)
r["carbon"]      # {"unit": "gCO2e", "value": 0.0018, "min": ..., "max": ..., "worst_case": {...}}
r["confidence"]  # {"level": "low", "ratio": 16.6, "reasons": ["wue_assumed", ...]}
```

Model ids are matched through aliases, so provider-specific ids such as
`accounts/fireworks/models/gpt-oss-120b` resolve to the same record. A model
that isn't in the knowledge base raises `UnknownModelError`, which suggests
close matches and links to [adding it](CONTRIBUTING.md#adding-a-model). Ids
are matched ignoring case.

## Provider ids

Who serves the request is taken, in order, from:

1. `provider`: one of these ids. An unrecognised id raises
   `UnknownProviderError`, so a typo can't silently estimate the wrong site.
2. `base_url` (optional): the API endpoint you called. Its host is matched
   against the hosts below; an unlisted host is ignored.
3. For a closed model, its vendor's own API (`claude-*` → `anthropic`,
   `gpt-*` → `openai`, …), flagged `provider_inferred_from_model`.
4. Otherwise wide US defaults, flagged `provider_unknown_fallback`.

| id | provider | API hosts |
|---|---|---|
| `fireworks` | Fireworks AI | `api.fireworks.ai` |
| `nscale` | nScale | `inference.api.nscale.com` |
| `openai` | OpenAI (direct API) | `api.openai.com` |
| `anthropic` | Anthropic (direct API) | `api.anthropic.com` |
| `google-vertex` | Google Vertex AI (us-central1) | `aiplatform.googleapis.com` |
| `vercel-gateway` | Vercel AI Gateway | `ai-gateway.vercel.sh` |
| `mistral` | Mistral AI (La Plateforme) | `api.mistral.ai` |
| `alibaba-sg` | Alibaba Cloud Model Studio (Singapore) | `.ap-southeast-1.maas.aliyuncs.com` |
| `modal` | Modal | `.modal.run` |
| `zai` | Z.ai (Zhipu) | `api.z.ai` |
| `sarvam` | Sarvam AI (Yotta NM1, Navi Mumbai) | `api.sarvam.ai` |
| `fal` | fal.ai | — |
| `novita` | Novita AI | `api.novita.ai` |
| `meta` | Meta AI API | `api.meta.ai` |
| `dhenu` | KissanAI Dhenu | `apibeta.dhenu.ai` |
| `sea-lion` | AI Singapore SEA-LION API | `api.sea-lion.ai` |
| `unknown-us` | Unknown provider (US default) | — |

To add a provider, see [CONTRIBUTING.md](CONTRIBUTING.md).

## API

One function:

```python
estimate(model, *, provider=None, base_url=None, input_tokens=0, output_tokens=0, cached_input_tokens=0, timestamp=None) -> EstimateResult
```

Full parameters, every output field, reason codes, errors and fallbacks, and versioning:
**[API.md](API.md)**.

### Output

```
model, provider, tokens
carbon       gCO2e: value, min, max, worst_case {min, max}
energy       Wh at the meter, primary_energy_mj
water        mL: total, on_site (cooling, WUE), generation (off-site)
confidence   level, ratio (max/min), reasons (every assumed input)
electricity  region, country, gco2e_per_kwh (+ range), mix, dataset_year
breakdown    h100_seconds, usage (operational) and embodied gCO2e
assumptions  active params, chips, chip energy ratio, PUE, utilization, overhead, method_version
provenance   trust, status, generated_by, stale for model, provider, region, hardware
```

`min`/`max` is the likely range; `worst_case` puts every input at its extreme
at once. Cache results against `assumptions.method_version`.

## How it works

```
tokens ─▶ FLOPs ─▶ H100-seconds ─▶ Wh at the meter ─▶ gCO2e operational + gCO2e embodied
                                                    ─▶ mL water on-site + off-site
```

Location-based, lifecycle grid intensity, embodied carbon included, usage
only. See [METHODOLOGY.md](METHODOLOGY.md) for the pipeline, the sources behind
every default, how ranges and confidence are computed, calibration against
published measurements, and the known gaps.

## Confidence

Every input carries an evidence tier: 1 published by the primary source, 2
derived or proxy, 3 assumed. The confidence label is computed from the width of
the likely carbon range (under 2x high, under 5x medium, otherwise low), never
typed in. `reasons` lists each assumed input, so it doubles as the list of
figures a provider could publish to tighten its estimates.

## Data

| File | What |
|---|---|
| `ecocost/data/models.yaml` | active and total parameters, measured energy, aliases |
| `ecocost/data/providers.yaml` | serving regions and chips (with candidates), PUE, WUE, utilization, overhead |
| `ecocost/data/regions.yaml` | grid intensity (lifecycle), mix, generation water, primary energy |
| `ecocost/data/hardware.yaml` | TDP, peak FLOPS, energy ratio vs H100, embodied carbon |
| `ecocost/data/sources.yaml` | every cited source, with its licence and terms of use |

Every value has a `source`, a `tier` and an [OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
provenance block. To correct or add a figure, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Development

```bash
poetry install
poetry run pytest -q
```

## License

Code: Apache-2.0. The data draws on Ember and Our World in Data (CC BY 4.0),
EPA eGRID, WRI, EcoLogits (MPL-2.0) and ML.ENERGY, among others; see
[NOTICE](NOTICE) for attribution and each source's terms.
