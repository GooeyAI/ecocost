# Changelog

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
