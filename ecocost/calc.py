"""Eco-cost estimation pipeline.

    tokens ──(active params, utilization)──▶ H100-seconds (work, chip-independent)
           ──(chip energy ratio, TDP, PUE)─▶ Wh at the meter
           ──(grid intensity)────────────▶ gCO2e (operational)
           ──(embodied per H100-second)──▶ gCO2e (embodied)
           ──(WUE)───────────────────────▶ mL water, data-centre cooling
           ──(generation water)──────────▶ mL water, at the power plant
           ──(primary energy factor)─────▶ MJ primary energy

Every step is arithmetic over ``Range``. min/max is the likely range:
independent multiplicative inputs combine in quadrature in log space.
``worst_case`` keeps the plain interval bounds with every input at its
extreme at once. Confidence is bucketed from the max/min ratio of the likely
carbon range and explained by listing every tier-3 input that went into it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .schema import (
    DEFAULT_HALF_WIDTH,
    H100_TDP_W,
    Hardware,
    Model,
    Provider,
    Range,
    Region,
    Tier,
    sig_round,
)

METHOD_VERSION = "0.3.0"

# H100 SXM is the unit of work: an H100-second is "the work one H100 does in
# one second", whatever chip actually ran it.
REFERENCE_HARDWARE_ID = "h100-sxm"

# Cached prefix tokens cost about a tenth of a fresh prefill (assumed).
CACHED_INPUT_COST = 0.1

# Confidence label from the max/min ratio of the likely carbon range. "high"
# is within about +/-40% of the point value, "medium" within about a factor
# of 2.2 either way. For scale, Epoch's plausible range for a ChatGPT query
# is 0.1 to 4 Wh, a 40x span.
HIGH_CONFIDENCE_RATIO = 2.0
MEDIUM_CONFIDENCE_RATIO = 5.0


def estimate(
    model: Model,
    provider: Provider,
    region: Region,
    hardware: Hardware,
    reference_hardware: Hardware,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    candidate_regions: Sequence[tuple[Region, float]] = (),
    candidate_hardware: Sequence[tuple[Hardware, float]] = (),
) -> Estimate:
    """``region`` and ``hardware`` are the provider's primary site and chip.
    When the provider discloses several, the candidates set the ranges."""
    chips = list(candidate_hardware) or [(hardware, 1.0)]

    def regional(factor: str, floor: float = 0.0) -> Range:
        return _regional(factor, region, provider.region_tier, candidate_regions, floor)

    # 1. Work, in H100-seconds on the reference chip so the unit does not
    #    depend on the fleet; the fleet enters in step 2.
    fresh_input = max(input_tokens - cached_input_tokens, 0)
    work = _h100_seconds(
        model,
        reference_hardware,
        fresh_input + cached_input_tokens * CACHED_INPUT_COST,
        provider.prefill_utilization.as_range(),
    )
    measured = model.measured_wh_per_1k_output_tokens_h100
    if measured is not None:
        # Measured path: Wh on an H100 -> H100-seconds at its TDP.
        wh = measured.as_range() * (output_tokens / 1000)
        work += wh * 3600 / reference_hardware.tdp_w.as_range()
    else:
        work += _h100_seconds(
            model,
            reference_hardware,
            output_tokens,
            provider.decode_utilization.as_range(),
        )

    # 2. Energy. The chip ratio is how much energy this fleet spends per
    #    H100-second of work (B200 ~0.75, H200 ~0.85). Serving overhead covers
    #    host CPU/RAM/network and idle capacity: Google reports 0.24 Wh/prompt
    #    all-in vs 0.10 Wh for the accelerators alone. Together that is the IT
    #    equipment energy; PUE then adds the facility's cooling and power
    #    losses to give energy at the meter.
    chip_ratio = _envelope([(hw.energy_vs_h100.as_range(), w) for hw, w in chips])
    it_equipment_wh = (
        work * H100_TDP_W / 3600 * chip_ratio * provider.serving_overhead.as_range()
    )
    energy_wh = it_equipment_wh * provider.pue.as_range()
    kwh = energy_wh / 1000

    # 3. Carbon. An uncertain site widens the grid range too: "somewhere in
    #    the US" spans ~100-700 gCO2e/kWh.
    grid = regional("carbon_intensity_gco2e_per_kwh", floor=10.0)
    embodied_rate = _envelope(
        [(hw.embodied_gco2e_per_h100_second, w) for hw, w in chips]
    )

    # 4. Water, in two parts because they follow different conventions.
    #    Data-centre water is what the operator's WUE measures (and what Google's
    #    0.26 mL per prompt counts). WUE is litres per kWh of IT energy (The
    #    Green Grid WP#35, ISO/IEC 30134-9), so it applies before PUE; applying
    #    it to energy at the meter would count the facility overhead twice.
    #    Generation water (WRI 2020) is the LCA convention and covers all the
    #    electricity the site draws, so it uses energy at the meter; it is
    #    usually larger and, on hydro grids, contested. This is the split in
    #    Li et al. 2023 (arXiv:2304.03271).
    return Estimate(
        model=model,
        provider=provider,
        region=region,
        hardware=hardware,
        chips=tuple(hw.id for hw, _ in chips),
        tokens=(input_tokens, output_tokens, cached_input_tokens),
        h100_seconds=work,
        chip_energy_ratio=chip_ratio,
        energy_wh=energy_wh,
        primary_energy_mj=kwh * 3.6 * regional("primary_energy_factor"),
        grid_intensity=grid,
        carbon_operational_g=kwh * grid,
        carbon_embodied_g=work * embodied_rate,
        water_data_center_ml=it_equipment_wh * provider.wue_l_per_kwh.as_range(),
        water_power_plant_ml=kwh * regional("water_l_per_kwh_generation") * 1000,
        reasons=_assumed_inputs(model, provider, region, [hw for hw, _ in chips]),
    )


@dataclass(frozen=True)
class Estimate:
    model: Model
    provider: Provider
    region: Region
    hardware: Hardware
    chips: tuple[str, ...]
    tokens: tuple[int, int, int]  # input, output, cached input
    h100_seconds: Range
    chip_energy_ratio: Range  # vs H100, envelope over the fleet
    energy_wh: Range
    primary_energy_mj: Range
    grid_intensity: Range
    carbon_operational_g: Range
    carbon_embodied_g: Range
    water_data_center_ml: Range
    water_power_plant_ml: Range
    reasons: list[str]

    @property
    def carbon_g(self) -> Range:
        return self.carbon_operational_g + self.carbon_embodied_g

    @property
    def water_ml(self) -> Range:
        return self.water_data_center_ml + self.water_power_plant_ml

    @property
    def confidence_level(self) -> str:
        ratio = self.carbon_g.ratio
        if ratio < HIGH_CONFIDENCE_RATIO:
            return "high"
        if ratio < MEDIUM_CONFIDENCE_RATIO:
            return "medium"
        return "low"

    def to_dict(self) -> dict:
        input_tokens, output_tokens, cached_input_tokens = self.tokens
        measured = self.model.measured_wh_per_1k_output_tokens_h100 is not None
        return {
            "model": self.model.id,
            "provider": self.provider.id,
            "method_version": METHOD_VERSION,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "cached_input": cached_input_tokens,
            },
            "carbon": {
                **self.carbon_g.to_dict("gCO2e"),
                "operational": self.carbon_operational_g.to_dict("gCO2e"),
                "embodied": self.carbon_embodied_g.to_dict("gCO2e"),
            },
            # each quantity carries the inputs that produced it
            "energy": {
                **self.energy_wh.to_dict("Wh"),
                "chips": list(self.chips),
                "chip_energy_vs_h100": sig_round(self.chip_energy_ratio.mid),
                "serving_overhead": self.provider.serving_overhead.value,
                "pue": self.provider.pue.value,
            },
            "primary_energy": self.primary_energy_mj.to_dict("MJ"),
            "water": {
                **self.water_ml.to_dict("mL"),
                "data_center": {
                    **self.water_data_center_ml.to_dict("mL"),
                    "wue": self.provider.wue_l_per_kwh.value,
                },
                "power_plant": self.water_power_plant_ml.to_dict("mL"),
            },
            "compute": {
                **self.h100_seconds.to_dict("H100-s"),
                "method": "measured" if measured else "model_size",
                "active_params_billion": {
                    "min": sig_round(self.model.active_params_b.min),
                    "max": sig_round(self.model.active_params_b.max),
                },
                # measured energy replaces it, so it was not used
                "decode_utilization": (
                    None if measured else self.provider.decode_utilization.value
                ),
            },
            "confidence": {
                "level": self.confidence_level,
                "range_ratio": round(self.carbon_g.ratio, 2),
                "reasons": self.reasons,
            },
            "grid": {
                "region": self.region.id,
                "country": self.region.country,
                "carbon_intensity": self.grid_intensity.to_dict("gCO2e/kWh"),
                "largest_source": self.region.largest_source.value,
                "mix": {k.value: v for k, v in self.region.mix.items()},
                "data_year": self.region.dataset_year,
            },
            "provenance": {
                name: {
                    "trust": record.provenance.trust.value,
                    "status": record.provenance.status.value,
                    "generated_by": record.provenance.generated_by,
                    "stale": record.provenance.is_stale(),
                }
                for name, record in (
                    ("model", self.model),
                    ("provider", self.provider),
                    ("region", self.region),
                    ("hardware", self.hardware),
                )
            },
        }


def _h100_seconds(
    model: Model, reference: Hardware, tokens: float, utilization: Range
) -> Range:
    """A forward pass is ~2 FLOPs per active parameter per token."""
    if tokens <= 0:
        return Range(0.0, 0.0, 0.0)
    flops = model.active_params_b.as_range() * 2e9 * tokens
    return flops / (reference.peak_dense_flops.as_range() * utilization)


def _envelope(ranges: Sequence[tuple[Range, float]]) -> Range:
    """Weighted mean as the point, min/max of the members as the range."""
    total = sum(w for _, w in ranges)
    return Range(
        min(r.lo for r, _ in ranges),
        sum(r.mid * w for r, w in ranges) / total,
        max(r.hi for r, _ in ranges),
        min(r.wlo for r, _ in ranges),
        max(r.whi for r, _ in ranges),
    )


def _regional(
    factor: str,
    region: Region,
    region_tier: Tier,
    candidates: Sequence[tuple[Region, float]],
    floor: float,
) -> Range:
    """A per-kWh regional factor for a provider whose site may be uncertain.

    Disclosed candidate sites give an envelope, which is evidence. Without
    them, the national figure is widened by the region tier's half-width.
    """
    if candidates:
        return _envelope([(getattr(c, factor).as_range(), w) for c, w in candidates])
    r = getattr(region, factor).as_range()
    if region_tier == Tier.primary:
        return r
    half_width = DEFAULT_HALF_WIDTH[region_tier]
    return Range(max(r.lo / half_width, floor), r.mid, r.hi * half_width)


def _assumed_inputs(
    model: Model, provider: Provider, region: Region, chips: Sequence[Hardware]
) -> list[str]:
    """Reason codes: every tier-3 input, most important first."""
    measured = model.measured_wh_per_1k_output_tokens_h100 is not None
    reasons = []
    if not measured and not model.open_weights:
        reasons.append("active_params_undisclosed")
    tiers = {
        # measured energy replaces the parameter count and decode utilization
        # on the decode path
        "active_params_assumed": None if measured else model.active_params_b.tier,
        "region_assumed": provider.region_tier,
        "chips_assumed": provider.hardware_tier,
        "pue_assumed": provider.pue.tier,
        "wue_assumed": provider.wue_l_per_kwh.tier,
        "decode_utilization_assumed": (
            None if measured else provider.decode_utilization.tier
        ),
        "serving_overhead_assumed": provider.serving_overhead.tier,
        "grid_intensity_assumed": region.carbon_intensity_gco2e_per_kwh.tier,
        "embodied_carbon_assumed": max(hw.embodied_tier for hw in chips),
    }
    return reasons + [code for code, tier in tiers.items() if tier == Tier.assumed]
