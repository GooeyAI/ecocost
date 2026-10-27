# Contributing

ecocost is only as good as its inputs. If you run inference, build
accelerators, publish grid data or study any of this, you can correct a number
with a pull request. Most changes are a few lines of YAML in `ecocost/data/`.

## What you can update

| File | Records | Typical contributions |
|---|---|---|
| `providers.yaml` | who runs inference | API `hosts` (a caller's `endpoint` is matched against them; a leading dot means any subdomain), serving regions (`region.candidates`), accelerator fleet (`hardware.candidates`), PUE, WUE, utilization, serving overhead |
| `models.yaml` | models | active and total parameters, measured Wh per 1k output tokens, aliases |
| `regions.yaml` | electricity grids | carbon intensity, generation mix, generation water, primary energy factor |
| `hardware.yaml` | accelerators | TDP, peak FLOPS, measured energy ratio vs H100, embodied carbon |

A provider that publishes its serving regions, PUE or fleet removes the
matching `*_assumed` reason from every estimate that routes to it, and
tightens the range. That is the most useful kind of PR.

## Adding a model

`estimate` raises `UnknownModelError` for a model that isn't in
`models.yaml` rather than guessing its size, because a guessed size would
dominate the estimate. Every model id resolves to exactly one record, either
as its key or through one of its `aliases` or `proxies`. The loader rejects
an id claimed twice.

### Record, alias or proxy?

Work through these in order and stop at the first that fits.

1. **Alias:** the id is another name for weights that are already listed.
   Add it to that record's `aliases`. These count as the same weights:
   - a provider or gateway prefix (`accounts/fireworks/models/x`, `openai/x`);
   - the dated snapshot the record's size source is about
     (`gpt-5.4-2026-03-05` under `gpt-5.4`);
   - a pointer the vendor documents as routing to that snapshot (`-latest`,
     a router such as `kimi-k3-fast`, an unsuffixed family id);
   - a deployment name for that model (add a comment saying so);
   - a quantised serving of the same checkpoint (FP8, NVFP4), named in `note`.

   These are **not** the same weights: another dated snapshot of the same
   named model (GPT-4 `0314` vs `0613`, `claude-3-5-sonnet-20240620` vs
   `-20241022`, a preview later replaced by a release), even when the vendor
   lists the snapshots under one name, because each was retrained; a
   fine-tune, a distilled or "mini" variant; an earlier or later version; or
   anything the vendor lists as a separate model. Those need their own record
   or a proxy, even when the numbers would come out the same.
2. **Record:** the model has a size source of its own (see the table below).
   Add a record.
3. **Proxy:** the model has no size or estimate of its own, but its vendor
   ties it to a listed model. List it under that record's `proxies` (see
   [Proxies](#proxies)).
4. **None of these:** don't add it.
   [Open an issue](https://github.com/GooeyAI/ecocost/issues/new) instead of
   guessing.

### Where a size comes from

| Evidence | Tier | `min`/`max` |
|---|---|---|
| The creator's model card, tech report or release post, including the parameter count of the creator's own weights repo | 1 | omit |
| Computed from the creator's `config.json` when the card is silent (say how in `note`) | 2 | omit |
| Carried over from a listed model the creator says it shares an architecture with (a "post-trained version of", "same architecture as"); `source` is that model's card and `note` quotes the tie | 2 | omit |
| A published estimate for this exact model (EcoLogits, for example); point = the rounded geometric mean of its range | 2 | the estimate's range |
| A single third-party figure with no range (a paper's aside, for example); `note` says whether it is total or active | 3 | omit |
| A closed model with none of the above, sized from the vendor's most similar listed model (same tier and price); `note` explains | 3 | an honest span |

Look in that order: the model card, then the creator's own docs and reports,
then EcoLogits, then Epoch AI, then secondary sources (press, blogs,
trackers), which can support tier 2 or 3, never tier 1. Never derive a size
from benchmark scores or throughput alone. Prefer a proxy to a tier-3 record
when the vendor ties the models together.

Other fields:

- **`total_params_b`** is a plain number from the same source. If the weights
  repo counts more (an MTP layer, a vision encoder), say so in `note`.
- **`open_weights`** is true only once the weights can be downloaded. If they
  are promised, set it false and say when in `note`.
- **`measured_wh_per_1k_output_tokens_h100`** comes only from a metered H100
  run of these exact weights (ML.ENERGY): `min` is the max-batch steady state,
  `max` batch 8, and `value` their geometric mean. `note` gives the precision,
  GPU count and parallelism. Leave it out for a different precision, a run
  with no batch-8 point, or image or video tasks, which put vision energy on
  the output tokens.
- **The key** is the vendor's API id for a closed model, and the weights
  repo's name (lowercased, or the short form its neighbours use) for an open
  one. Put the record next to its creator's other records.

A record looks like this:

```yaml
  gpt-oss-20b:
    label: gpt-oss-20b
    creator: OpenAI
    open_weights: true
    total_params_b: 21
    aliases:
    - openai/gpt-oss-20b                 # ids providers use for these weights
    active_params_b:                     # parameters used per token (MoE: active only)
      value: 3.6
      unit: B
      tier: 1                            # see the table above
      source: https://huggingface.co/openai/gpt-oss-20b
      note: MoE, 3.6B active.
    measured_wh_per_1k_output_tokens_h100:   # optional; only with a metered H100 run
      value: 0.0346
      min: 0.012
      max: 0.1
      unit: Wh per 1k output tokens, H100, GPU-only, PUE 1.0
      tier: 1
      source: https://ml.energy/leaderboard/
      note: min = max-batch steady state, max = batch 8.
    provenance:
      generated: {by: human:<your-github-handle>, at: 2026-10-01}
      verified: []
      status: draft
      stale_after: 2027-10-01
      sources:
      - resource: https://huggingface.co/openai/gpt-oss-20b
```

### Proxies

A model with no published size or estimate of its own, which its vendor
ties to a model that is already listed (another snapshot of the same named
model, a preview the later model is "based on", a model it was superseded
by), can be listed as a proxy of that model instead.
It is not an alias: the weights differ, so its estimate is flagged, its
range widened and its confidence set to low (see
[METHODOLOGY.md](METHODOLOGY.md#proxies)).

```yaml
  gemini-3.1-pro-preview:
    proxies:
    - ids: [gemini-3-pro-preview]
      note: "Google's model card: 'Gemini 3.1 Pro is based on Gemini 3 Pro'; no estimate of 3 Pro itself."
      source: https://deepmind.google/models/model-cards/gemini-3-1-pro/
```

`note` says why the two are related and `source` links the vendor page that
ties them together; both are required, and `source` must be registered like
any other. Similar names or prices alone aren't enough. A weaker tie is
accepted as a last resort: the same vendor's next model in the same product
line (Qwen3.7-Max under Qwen3.8-Max), when neither has a closer relative
listed. Its `note` must say the tie is inferred rather than stated, and
`source` links the vendor page describing the listed model's place in that
line. A proxy can't reuse an
id or alias. When the model gets a published size or estimate, give it a
record and remove the proxy.

### Keeping records current

- When a model gets its own published size or estimate, give it a record
  and remove it from any proxy or alias that covered it.
- When promised weights are published, set `open_weights: true` and cite the
  model card.
- When a record passes its `stale_after` date, recheck its sources and
  update the record or its `provenance`.
- An alias that turns out to name different weights is a bug. Move the id to
  its own record or a proxy, and if that moves an estimate, add a CHANGELOG
  line saying it corrects a mapping, not the model's energy use.

## Adding a provider

Copy a similar record in `providers.yaml`, give it a lowercase id, and fill in
what the provider discloses: API `hosts`, serving `region` (with `candidates`
if it serves from several sites), accelerator `hardware` (with `candidates`
for a mixed fleet), `pue`, `wue_l_per_kwh`, and utilization and serving
overhead if measured. Anything undisclosed keeps the tier-3 defaults its
neighbours use; `reasons` will then name exactly what the provider could
publish. Add the id to the provider table in README.md.

## Every number is a Factor

```yaml
pue:
  value: 1.12
  min: 1.08          # optional; the tier's default half-width applies if absent
  max: 1.25
  unit: ratio
  tier: 1            # 1 published by the primary source, 2 derived / proxy, 3 assumed
  source: https://example.com/sustainability-report-2026.pdf#page=14
  note: "Fleet TTM PUE, calendar 2025, all sites."
```

Rules the reviewers apply:

- **`source` is required** and should deep-link to the page, table or section
  that holds the figure (`#page=`, anchors). A value with no external source
  uses `source: assumption` (a tier-3 default), `derived` (computed from other
  records) or `definition`, and explains itself in `note`.
- **The source must be registered.** `ecocost/data/sources.yaml` lists every
  source we cite with its licence and terms. Citing a new site or dataset means
  adding it there; if its licence requires attribution, add it to `NOTICE` too.
  Read an entry's `terms` before citing it: WRI 2020, for example, is capped at
  its current values.
- **Secondary sources** (press, blogs, trackers) can support a tier-2 or tier-3
  value, never a tier-1 one.
- **`tier` must match the evidence.** Your own published figure is tier 1. A
  design target, a proxy from a sibling site or a secondary compilation is
  tier 2. Never tier 1 for an estimate.
- **Ranges should be honest.** If you only know a point value, omit `min` and
  `max` and let the tier set them.
- **Say what the number is** in `note`: period, scope (site or fleet),
  measured or target, and any unit conversion you did.
- **Location-based only.** Do not submit market-based figures (after
  renewable certificates or PPAs) as grid intensity.

## Provenance

Every record carries an [OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md#5-provenance-trust-and-lifecycle)
block. When you change a record, update it:

```yaml
provenance:
  generated: {by: human:<your-github-handle>, at: 2026-10-01}
  verified: []           # reviewers add themselves here
  status: draft
  stale_after: 2027-10-01
  sources:
    - {resource: https://example.com/sustainability-report-2026.pdf}
```

If you represent the organisation the record describes, say so in the PR;
reviewers will note it.

## Before you open the PR

```bash
poetry install
poetry run pytest -q
poetry run ruff check . && poetry run ruff format --check .
```

The tests load the whole knowledge base and check it: every region and
hardware reference resolves, generation mixes sum to 1, ranges are ordered,
every value is cited, every cited source is registered with its licence, and
capped sources stay within their cap. CI runs the same suite on every pull request, plus ruff and a package build.
A maintainer reviews every PR: CI can check that a number is well-formed and
cited, not that it is right.

Before opening a data PR, have every new value checked against its source by
someone other than its author (a second person, or a fresh agent that sees
only the diff). Each value should come back confirmed, corrected or
unsupported. Apply corrections, drop unsupported values, and say in the PR
that this was done.

If your change moves an estimate, say by how much in the PR description, for
example the `estimate("gpt-oss-120b", provider="your-provider", ...)` carbon
before and after.

## Code changes

Changes to the method (`calc.py`, `schema.py`) need a note in `METHODOLOGY.md`
and, if they change outputs, a bump of `METHOD_VERSION` in `calc.py`.
