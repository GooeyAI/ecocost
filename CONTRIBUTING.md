# Contributing

ecocost is only as good as its inputs. If you run inference, build
accelerators, publish grid data or study any of this, you can correct a number
with a pull request. Most changes are a few lines of YAML in `ecocost/data/`.

## What you can update

| File | Records | Typical contributions |
|---|---|---|
| `providers.yaml` | who runs inference | API `hosts` (a caller's `base_url` is matched against them; a leading dot means any subdomain), serving regions (`region.candidates`), accelerator fleet (`hardware.candidates`), PUE, WUE, utilization, serving overhead |
| `models.yaml` | models | active and total parameters, measured Wh per 1k output tokens, aliases |
| `regions.yaml` | electricity grids | carbon intensity, generation mix, generation water, primary energy factor |
| `hardware.yaml` | accelerators | TDP, peak FLOPS, measured energy ratio vs H100, embodied carbon |

A provider that publishes its serving regions, PUE or fleet removes the
matching `*_assumed` reason from every estimate that routes to it, and
tightens the range. That is the most useful kind of PR.

## Adding a model

`estimate` raises `UnknownModelError` for a model that isn't in
`models.yaml` rather than guessing its size, because a guessed size would
dominate the estimate. If the model is another id for a model that is already
listed (a provider's own name for the same weights), add the id to that
model's `aliases`. Otherwise add a record:

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
      tier: 1                            # 1 from the model card; 2 for a published estimate
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

For a closed model, cite a published estimate of its size (EcoLogits, for
example) at tier 2 with an honest range, and set `open_weights: false`. If you
can't find one, [open an issue](https://github.com/GooeyAI/ecocost/issues/new)
instead of guessing.

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

If your change moves an estimate, say by how much in the PR description, for
example the `estimate("gpt-oss-120b", provider="your-provider", ...)` carbon
before and after.

## Code changes

Changes to the method (`calc.py`, `schema.py`) need a note in `METHODOLOGY.md`
and, if they change outputs, a bump of `METHOD_VERSION` in `calc.py`.
