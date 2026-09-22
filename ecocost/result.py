"""The shape of what ``estimate`` returns, for type checkers and editors.
API.md describes every field."""

from __future__ import annotations

from typing import Literal, TypedDict


class Bounds(TypedDict):
    min: float
    max: float


class Quantity(TypedDict):
    """A point value, its likely range and the worst case."""

    unit: str
    value: float
    min: float
    max: float
    worst_case: Bounds


class Energy(Quantity):
    primary_energy_mj: float


class Water(Quantity):
    on_site: Quantity
    generation: Quantity


class Tokens(TypedDict):
    input: int
    output: int
    cached_input: int


class Confidence(TypedDict):
    level: Literal["high", "medium", "low"]
    ratio: float
    reasons: list[str]


class Electricity(TypedDict):
    region: str
    country: str
    gco2e_per_kwh: float
    gco2e_per_kwh_range: list[float]
    primary_source: str
    mix: dict[str, float]
    dataset_year: int


class Grams(TypedDict):
    gco2e: float


class Breakdown(TypedDict):
    h100_seconds: Quantity
    usage: Grams
    embodied: Grams


class Assumptions(TypedDict):
    active_params_b: Bounds
    hardware: list[str]
    chip_energy_vs_h100: float
    pue: float
    decode_utilization: float
    serving_overhead: float
    method_version: str


class RecordProvenance(TypedDict):
    trust: str
    status: str
    generated_by: str
    stale: bool


class Provenance(TypedDict):
    model: RecordProvenance
    provider: RecordProvenance
    region: RecordProvenance
    hardware: RecordProvenance


class Requested(TypedDict):
    model: str
    provider: str | None
    base_url: str | None


class EstimateResult(TypedDict):
    model: str
    provider: str
    tokens: Tokens
    carbon: Quantity
    energy: Energy
    water: Water
    confidence: Confidence
    electricity: Electricity
    breakdown: Breakdown
    assumptions: Assumptions
    provenance: Provenance
    requested: Requested
