"""Typed records for eco-cost estimation.

Every physical input is a ``Factor``: a point value with a min/max range, an
evidence tier and a source. Tiers drive confidence, so they are data, not
opinion:

* tier 1: published by the primary source (spec sheet, provider disclosure,
  direct measurement)
* tier 2: derived from a reputable secondary source or a close proxy
* tier 3: assumed industry default

Provenance is a separate axis from confidence. ``ai_generated`` vs
``human_verified`` says whether a person checked the inputs; it never changes
the computed range.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from datetime import date


class Tier(enum.IntEnum):
    primary = 1
    derived = 2
    assumed = 3


# Multiplicative half-width applied to a point value when no explicit
# min/max is given. A tier-3 value may be 2.5x higher or lower than stated.
DEFAULT_HALF_WIDTH = {Tier.primary: 1.1, Tier.derived: 1.4, Tier.assumed: 2.5}


class LifecycleStatus(str, enum.Enum):
    """OKF v0.2 ``status``."""

    draft = "draft"
    stable = "stable"
    deprecated = "deprecated"


class TrustTier(str, enum.Enum):
    """Derived from OKF v0.2 ``verified``: no entries, machine-only, or any human."""

    unverified = "unverified"
    machine_confirmed = "machine_confirmed"
    human_reviewed = "human_reviewed"


class EnergySource(str, enum.Enum):
    coal = "coal"
    gas = "gas"
    oil = "oil"
    nuclear = "nuclear"
    hydro = "hydro"
    wind = "wind"
    solar = "solar"
    geothermal = "geothermal"
    biomass = "biomass"
    other = "other"


@dataclass(frozen=True)
class Verification:
    by: str  # OKF actor string; "human:<id>" marks a human reviewer
    at: date | None = None

    @property
    def is_human(self) -> bool:
        return self.by.startswith("human:")


@dataclass(frozen=True)
class Provenance:
    """OKF v0.2 trust and lifecycle fields.

    https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md
    """

    generated_by: str = ""  # e.g. "agent:claude-fable-5-1" or "human:reviewer"
    generated_at: date | None = None
    verified: tuple[Verification, ...] = ()
    status: LifecycleStatus = LifecycleStatus.draft
    stale_after: date | None = None
    sources: tuple[str, ...] = ()  # OKF sources[].resource

    @property
    def trust(self) -> TrustTier:
        if not self.verified:
            return TrustTier.unverified
        if any(v.is_human for v in self.verified):
            return TrustTier.human_reviewed
        return TrustTier.machine_confirmed

    def is_stale(self, today: date | None = None) -> bool:
        return bool(self.stale_after and (today or date.today()) >= self.stale_after)


@dataclass(frozen=True)
class Factor:
    """A number we are not sure about."""

    value: float
    unit: str
    tier: Tier
    min: float | None = None
    max: float | None = None
    source: str = ""
    note: str = ""

    def __post_init__(self):
        hw = DEFAULT_HALF_WIDTH[self.tier]
        if self.min is None:
            object.__setattr__(self, "min", self.value / hw)
        if self.max is None:
            object.__setattr__(self, "max", self.value * hw)
        if not (self.min <= self.value <= self.max):
            raise ValueError(f"Factor out of range: {self}")

    def as_range(self) -> Range:
        return Range(self.min, self.value, self.max)


def _ln(hi: float, lo: float) -> float:
    return math.log(hi / lo) if hi > 0 and lo > 0 else 0.0


@dataclass(frozen=True)
class Range:
    """Uncertainty carrier. lo <= mid <= hi is the *likely* range; wlo/whi are
    the worst-case bounds where every input sits at its extreme at once.

    Products and quotients of independent inputs combine their log half-widths
    in quadrature (GUM-style propagation for multiplicative models), so five
    1.5x uncertainties give ~2.5x, not 7.6x. Sums add linearly, which treats
    the terms as fully correlated: they usually share the same upstream work,
    and it is the conservative choice. Worst-case bounds are always plain
    interval arithmetic.
    """

    lo: float
    mid: float
    hi: float
    wlo: float | None = None
    whi: float | None = None

    def __post_init__(self):
        if self.wlo is None:
            object.__setattr__(self, "wlo", self.lo)
        if self.whi is None:
            object.__setattr__(self, "whi", self.hi)

    def __mul__(self, other: Range | float) -> Range:
        if not isinstance(other, Range):
            return Range(
                self.lo * other,
                self.mid * other,
                self.hi * other,
                self.wlo * other,
                self.whi * other,
            )
        mid = self.mid * other.mid
        up = math.hypot(_ln(self.hi, self.mid), _ln(other.hi, other.mid))
        down = math.hypot(_ln(self.mid, self.lo), _ln(other.mid, other.lo))
        return Range(
            mid * math.exp(-down),
            mid,
            mid * math.exp(up),
            self.wlo * other.wlo,
            self.whi * other.whi,
        )

    __rmul__ = __mul__

    def __truediv__(self, other: Range | float) -> Range:
        if not isinstance(other, Range):
            return self * (1 / other)
        inverse = Range(
            1 / other.hi, 1 / other.mid, 1 / other.lo, 1 / other.whi, 1 / other.wlo
        )
        return self * inverse

    def __add__(self, other: Range | float) -> Range:
        if not isinstance(other, Range):
            other = Range(other, other, other)
        return Range(
            self.lo + other.lo,
            self.mid + other.mid,
            self.hi + other.hi,
            self.wlo + other.wlo,
            self.whi + other.whi,
        )

    __radd__ = __add__

    @property
    def ratio(self) -> float:
        if self.hi <= 0:
            return 1.0  # a point at zero, e.g. no tokens
        return self.hi / self.lo if self.lo > 0 else float("inf")

    def to_dict(self, unit: str, sig: int = 3) -> dict:
        return {
            "unit": unit,
            "value": sig_round(self.mid, sig),
            "min": sig_round(self.lo, sig),
            "max": sig_round(self.hi, sig),
            "worst_case": {
                "min": sig_round(self.wlo, sig),
                "max": sig_round(self.whi, sig),
            },
        }


def sig_round(x: float, sig: int = 3) -> float:
    """Round to significant figures so sub-milligram values survive."""
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, sig - int(math.floor(math.log10(abs(x)))) - 1)


SECONDS_PER_YEAR = 365.25 * 24 * 3600

# The reference chip's TDP. Work is measured in H100-seconds, so energy is
# H100-seconds x this x the fleet's energy ratio.
H100_TDP_W = 700.0


@dataclass(frozen=True)
class Hardware:
    id: str
    label: str
    tdp_w: Factor
    peak_dense_flops: Factor  # FLOP/s, BF16 dense
    # Embodied carbon is kept as its three independent inputs so the range is
    # propagated, not pre-stacked: kg / (years * active fraction).
    embodied_kgco2e_per_gpu: Factor  # cradle-to-gate GPU plus its server share
    lifetime_years: Factor
    active_fraction: Factor  # share of the lifetime spent serving
    # Energy this chip spends per H100-second of *work*, relative to an H100
    # (1.0). Measured where ML.ENERGY has both chips, spec-derived otherwise.
    # It is what "newer chip" means for the estimate: B200 at high batch is
    # ~0.75, but a 1 kW chip serving a small model at batch 8 is >1.
    energy_vs_h100: Factor = field(
        default_factory=lambda: Factor(1.0, "ratio", Tier.primary, min=1.0, max=1.0)
    )
    provenance: Provenance = field(default_factory=Provenance)

    @property
    def work_rate_vs_h100(self) -> Range:
        """H100-seconds of work this chip does per real second: power ratio
        over energy ratio. A B200 (1 kW, 0.75x energy) does ~1.9 H100-s/s."""
        return (self.tdp_w.as_range() / H100_TDP_W) / self.energy_vs_h100.as_range()

    @property
    def embodied_gco2e_per_h100_second(self) -> Range:
        """Embodied carbon charged per H100-second of work: the per-real-second
        rate divided by how much work a real second buys on this chip."""
        per_second = (
            self.embodied_kgco2e_per_gpu.as_range()
            * 1000
            / (
                self.lifetime_years.as_range()
                * SECONDS_PER_YEAR
                * self.active_fraction.as_range()
            )
        )
        return per_second / self.work_rate_vs_h100

    @property
    def embodied_tier(self) -> Tier:
        return max(
            self.embodied_kgco2e_per_gpu.tier,
            self.lifetime_years.tier,
            self.active_fraction.tier,
        )


@dataclass(frozen=True)
class Region:
    id: str
    label: str
    country: str
    carbon_intensity_gco2e_per_kwh: Factor
    primary_energy_factor: Factor  # MJ primary per MJ final electricity
    water_l_per_kwh_generation: Factor
    mix: dict[EnergySource, float]
    dataset_year: int
    mix_source: str = ""
    provenance: Provenance = field(default_factory=Provenance)

    @property
    def largest_source(self) -> EnergySource:
        return max(self.mix, key=self.mix.get) if self.mix else EnergySource.other


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    hosts: tuple[str, ...]  # published API hosts; a leading dot means any subdomain
    region: str  # Region.id
    region_tier: Tier
    hardware: str  # Hardware.id
    hardware_tier: Tier
    pue: Factor
    wue_l_per_kwh: Factor
    decode_utilization: Factor  # fraction of peak FLOPS achieved during decode
    prefill_utilization: Factor
    serving_overhead: Factor  # all-in energy / accelerator-only energy
    # Region.id -> weight. The sites a provider discloses when it won't say
    # which one serves a request; the grid range becomes their envelope.
    region_candidates: tuple[tuple[str, float], ...] = ()
    # Hardware.id -> weight, same idea for the chip fleet a provider discloses.
    hardware_candidates: tuple[tuple[str, float], ...] = ()
    provenance: Provenance = field(default_factory=Provenance)


@dataclass(frozen=True)
class Model:
    id: str
    label: str
    creator: str
    active_params_b: Factor
    total_params_b: float | None = None
    open_weights: bool = False
    # Optional measured energy per 1k output tokens, normalised to H100 at
    # PUE 1.0. When present it beats the FLOPs formula.
    measured_wh_per_1k_output_tokens_h100: Factor | None = None
    provenance: Provenance = field(default_factory=Provenance)
