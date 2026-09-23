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


class Carbon(Quantity):
    operational: Quantity
    embodied: Quantity


class Energy(Quantity):
    chips: list[str]
    chip_energy_vs_h100: float
    serving_overhead: float
    pue: float


class DataCenterWater(Quantity):
    wue: float


class Water(Quantity):
    data_center: DataCenterWater
    power_plant: Quantity


class Compute(Quantity):
    method: Literal["measured", "model_size"]
    active_params_billion: Bounds
    decode_utilization: float | None


class Tokens(TypedDict):
    input: int
    output: int
    cached_input: int


class Confidence(TypedDict):
    level: Literal["high", "medium", "low"]
    range_ratio: float
    reasons: list[str]


class Grid(TypedDict):
    region: str
    country: str
    carbon_intensity: Quantity
    largest_source: str
    mix: dict[str, float]
    data_year: int


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
    endpoint: str | None
    region: str | None


class EstimateResult(TypedDict):
    model: str
    provider: str
    method_version: str
    tokens: Tokens
    carbon: Carbon
    energy: Energy
    primary_energy: Quantity
    water: Water
    compute: Compute
    confidence: Confidence
    grid: Grid
    provenance: Provenance
    requested: Requested
