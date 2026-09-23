# ecocost methodology

Method version 0.3.0. How a token count becomes a carbon, energy and water
estimate with a range and a confidence label, and where every number comes
from. Per-input sources live next to the values in `ecocost/data/*.yaml`.

## Scope and accounting choices

- **Usage only.** Inference of one request. Training and model development are
  out of scope; the Green Software Foundation's SCI for AI treats them as a
  separate boundary.
- **Location-based.** Grid carbon is the physical grid where the accelerator
  sits, never renewable certificates or PPAs (SCI, ISO/IEC 21031:2024).
- **Lifecycle grid intensity.** Upstream methane, fuel supply chain and plant
  construction are included, so countries and US subregions compare like for
  like.
- **Embodied carbon included**, amortised over the hardware's working life, as
  SCI requires.

## The pipeline

```
tokens ──(2 × active params)──────────────────▶ FLOPs
       ──(H100 peak × utilization)────────────▶ H100-seconds   (work, chip-independent)
       ──(chip energy ratio, TDP)─────────────▶ Wh, accelerator
       ──(serving overhead)───────────────────▶ Wh, IT equipment
       ──(PUE)────────────────────────────────▶ Wh at the meter
       ──(grid intensity)─────────────────────▶ gCO2e operational
H100-seconds ──(embodied per H100-second)─────▶ gCO2e embodied
Wh, IT equipment ──(WUE)──────────────────────▶ mL water, data centre
Wh at the meter ──(generation water)──────────▶ mL water, power plant
```

### 1. Tokens to work

A forward pass costs about 2 FLOPs per parameter touched per token (Kaplan et
al. 2020). For mixture-of-experts models only the **active** parameters count:
gpt-oss-120b has 117 B parameters but 5.1 B active per token.

Open-weights models take their counts from the model card (tier 1). Closed
models use EcoLogits' published estimates (an estimated total with a 10 to 30%
MoE activation rule), cross-checked against pricing and decode throughput where
that evidence exists (tier 2, ranges about 3x).

### 2. Work to H100-seconds

The unit is "the work one H100 SXM does in one second", so a measured open
model, a closed model estimated from its size, and a model timed on your own
GPUs land in the same unit with different confidence.

- **Prefill** (input) is compute-bound: about 50% of peak (30 to 70%).
- **Decode** (output) is memory-bound. Where [ML.ENERGY](https://ml.energy/leaderboard/)
  has metered the model on an H100, its Wh per 1k output tokens is used
  directly (tier 1, min = max-batch steady state, max = batch 8). Otherwise the
  FLOPs formula at 12% utilization (5 to 35%).
- **Cached input** tokens are charged at 10% of a fresh prefill (assumed).

Batch regime is the largest single unknown: the metered spread between batch 8
and full batches is 8 to 10x, and only the provider knows where it serves.

### 3. Energy at the meter

```
Wh = H100-seconds × 700 W / 3600 × chip energy ratio × serving overhead × PUE
```

- **Chip energy ratio** (`hardware.yaml`, `energy_vs_h100`): energy a chip
  spends per H100-second of work. B200 is measured from ML.ENERGY's paired
  H100/B200 runs: 0.66 to 0.80 for large MoE models at any batch, but 1.5 to
  2.0 for small dense models at low batch, because a 1 kW chip idles. So the
  B200 range straddles 1. H200 is spec-derived (same die, 1.43x bandwidth);
  MI300X and MI325X are spec-derived and tier 3 until measured. Providers list
  the chips they disclose as `hardware.candidates`; the estimate uses their
  envelope.
- **Serving overhead** 1.6 (1.3 to 2.2): host CPU, DRAM, network and idle
  provisioned capacity. From Google's measured per-prompt breakdown (0.14 Wh
  accelerator, 0.06 host, 0.02 idle), a TPU fleet used as a ratio;
  cross-checked by DGX H100 system power (about 1.8x at full load) and
  EcoLogits' server model (about 1.2 to 1.3x).
- **PUE** follows the same evidence ladder as region: a published per-site or
  fleet figure where the operator discloses one (Google 1.09, AWS 1.14,
  Microsoft Americas 1.16), a stated design target at tier 2, 1.2 (1.09 to
  1.45) for an undisclosed mixed fleet, 1.3 for colocation.

### 4. Carbon and water

- **Operational carbon** = kWh × grid intensity.
- **Embodied carbon** = H100-seconds × (kgCO2e per GPU / (lifetime × active
  fraction)) / chip work rate. Per GPU including its server share: 276 to 985
  kgCO2e (NVIDIA HGX H100 PCF, ADEME GPU LCA, BoaviztAPI, EcoLogits). Lifetime
  3 to 6 years and active fraction 50 to 100% are policy choices (tier 3). On a
  clean grid this term can be a third of the total.
- **Data-centre water** (`water.data_center`) = IT kWh × the operator's WUE
  (cooling). WUE is litres per kWh of IT energy, the energy before PUE
  ([The Green Grid WP#35](https://www.thegreengrid.org/en/resources/library-and-tools/238-WP%2335---Water-Usage-Effectiveness-%28WUE%29%3A-A-Green-Grid-Data-Center-Sustainability-Metric-),
  ISO/IEC 30134-9), so it is not applied to energy at the meter, which would
  count the facility overhead twice. Power-plant water, carbon and primary
  energy use energy at the meter, since the plant supplies the whole site.
  This is the split in [Li et al. 2023](https://arxiv.org/abs/2304.03271).
- **Power-plant water** (`water.power_plant`) = kWh × water consumed generating the electricity (WRI
  2020). This is usually the larger term and, on hydro grids, is dominated by
  reservoir evaporation *attributed* to hydropower, a standard LCA allocation
  but a contested one. It is not water withdrawn because a request ran.

## Where the region comes from

Grid intensity, generation water and primary energy all depend on the site.
Most providers do not say which site served a request, so each provider record
carries the most specific evidence available:

| Evidence | Treatment |
|---|---|
| Caller passes `region` | that region, tier 1; overrides the provider's |
| Site pinned (region in the hostname, or a single physical site) | that region, tier 1 |
| Provider discloses a set of sites | `region.candidates`: range is the envelope of the candidates, point is their weighted mean, tier 2 |
| Nothing disclosed | national average, widened by the tier's default half-width |

A cloud region request is not a site guarantee: Google, for example, commits a
regional Vertex endpoint only to the multi-region.

### Grid data

| Scope | Intensity | Mix | Water |
|---|---|---|---|
| Countries | [Ember](https://ember-energy.org/data/yearly-electricity-data/) lifecycle via [Our World in Data](https://ourworldindata.org/grapher/carbon-intensity-electricity), 2025 | [OWID share-elec-by-source](https://ourworldindata.org/grapher/share-elec-by-source), 2025 | [WRI 2020](https://files.wri.org/d8/s3fs-public/guidance-calculating-water-use-embedded-purchased-electricity.pdf) Appendix 2 |
| US subregions | [EPA eGRID2023](https://www.epa.gov/system/files/documents/2025-06/summary_tables_rev2.pdf) direct rates × 1.124, the same-year Ember/eGRID national ratio, to put them on the lifecycle basis (tier 2) | eGRID2023 Table 2 | WRI 2020 Appendix 1 |

Primary energy factors come from EcoLogits (`electricity_mixes.json`, ADEME
Base Empreinte). The mix is display-only; carbon always comes from the
intensity figure.

## Ranges and confidence

Every input is a `Factor`: value, min, max, evidence tier, source.

| Tier | Meaning | Default half-width |
|---|---|---|
| 1 | published by the primary source | ×1.1 |
| 2 | derived from a reputable secondary source or close proxy | ×1.4 |
| 3 | assumed default | ×2.5 |

**Likely range.** Independent multiplicative inputs combine their log
half-widths in quadrature (JCGM GUM §5.1). Sums stay linear. This assumes each
input's min/max covers a similar share of its plausible values; it is an
approximation, not a statistical confidence interval.

**Worst case.** Plain interval arithmetic, every input at its extreme at once,
reported alongside as `worst_case`.

**Confidence label** is computed from max ÷ min of the likely carbon range:
under 2 is high, 2 to 5 medium, above 5 low. It is never typed in. The
`reasons` list names every tier-3 input, so it is both the explanation and the
to-do list: publishing a figure removes the reason for every estimate that
depends on it.

## Calibration

Energy at the meter from the size-based path (models without measured energy),
with default assumptions (`provider="unknown-us"`), against independent
published figures. `ecocost/tests/test_calibration.py` recomputes this table.

| Anchor | How it was obtained | Published | Ours (likely range) | Published ÷ ours |
|---|---|---|---|---|
| Llama 3.3 70B, 100 in / 300 out ([Jegham et al. 2025](https://arxiv.org/abs/2505.09598), Table 4) | public API throughput and latency, assumed hardware, PUE included | 0.237 Wh | 0.144 (0.0513–0.368) | 1.6× |
| Llama 3.1 405B, 500 in / 300 out ([Elsworth et al. 2025](https://arxiv.org/abs/2509.20241), median; IQR 0.19–0.68) | production serving simulation: FP8, large batches, full node and PUE | 0.39 Wh | 1.07 (0.459–2.58) | 0.36× |

The two anchors bracket the point value, as the batch-size unknown says they
should: the API-based estimate sits 1.6× above it, inside the likely range
(matching it would take about 7% decode utilization against our 12%).

**The production anchor falls below the likely range.** Utilization is
measured against the H100's BF16 peak, and the size-based path does not model
numeric precision. A deployment serving in FP8 with large batches does the
same work in roughly half the time, so for production-optimised serving the
size-based estimate is high, here 2.7×. Estimates for models with measured
energy are not affected. See [Known gaps](#known-gaps).

**Consistency checks, not independent tests:**

- ML.ENERGY's measured energy for smaller models: the measured path uses that
  data as its input.
- [Epoch AI](https://epoch.ai)'s ~0.3 Wh for a ~100B-active model: the same
  size × utilization method.
- Google's 0.24 Wh and 0.26 mL per median Gemini prompt
  ([2025](https://arxiv.org/abs/2508.15734)): our serving overhead and
  Vertex's water per kWh come from that paper, and the prompt size is not
  disclosed.
- ML.ENERGY's 3,353 J of GPU energy per Llama 3.1 405B response, reported by
  [MIT Technology Review](https://www.technologyreview.com/2025/05/20/1116327/ai-energy-usage-climate-footprint-big-tech/):
  the response length is not stated, so it cannot be recomputed.

What would make this a real calibration: providers publishing energy per
token at a known batch size and precision.

## Known gaps

Ranked by how much of the likely carbon range each causes, measured by fixing
each input at its point value for typical requests (gpt-oss-120b on Fireworks
and nScale, Claude Opus 5 on Anthropic, GPT-5.5 on OpenAI).

| Gap | Share of the range | Why | What would close it |
|---|---|---|---|
| Batch size (decode utilization) | 33–50% | Metered energy per token varies 8–10× between batch 8 and full batches; the size-based path assumes 5–35% utilization | Providers publishing tokens/s per GPU or Wh per token |
| Serving site | 20–36% | Undisclosed US sites span ~100–700 gCO2e/kWh | Providers publishing serving regions |
| Closed-model size | ~26% (closed models only) | About 3×; wider where sources disagree | Vendor disclosure, or metered energy |
| Chip fleet | up to 13% | B200 ranges from 0.66× to 2.0× an H100 per unit of work; TPU, Trainium and Ascend use the H100 proxy | Fleet disclosure; public energy-per-work figures for those chips |
| Embodied carbon | 2–16%, more on clean grids | Lifetime and utilization are policy defaults; H200, B200 and MI300X/MI325X footprints are scaled from H100 | Providers' real lifetimes; product carbon footprints for newer chips |
| Serving overhead | 2–6% | Taken from one TPU fleet's ratio | Provider measurement |
| PUE | ≤1% where disclosed | | |

**Not reflected in the range:**

- **Numeric precision.** The size-based path assumes BF16; FP8 or FP4 serving
  can halve the energy or better, which puts production-optimised deployments
  below the range (see [Calibration](#calibration)).
- Cached input charged at 10% of a fresh prefill.
- Grid data is annual; hourly intensity is a planned upgrade.
- Generation water rests on WRI's 2016 grid mixes, and on hydro grids on a
  contested allocation of reservoir evaporation (reported separately as
  `water.power_plant`).

**Out of scope:** training, image, video and audio models, network transfer,
end-user devices.
