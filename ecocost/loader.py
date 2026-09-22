"""Load the YAML knowledge base into typed records.

The YAML files under ``ecocost/data`` are the source of truth. Every leaf
number is written as::

    tdp_w: {value: 700, unit: W, tier: 1, source: "https://...", note: "..."}

optionally with ``min``/``max``. Every top-level entry carries a
``provenance`` block. See README.md for the full contract.
"""

from __future__ import annotations

import difflib
import functools
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .errors import UnknownModelError, UnknownProviderError
from .schema import (
    EnergySource,
    Factor,
    Hardware,
    LifecycleStatus,
    Model,
    Provenance,
    Provider,
    Region,
    Tier,
    Verification,
)

DATA_DIR = Path(__file__).parent / "data"


def _factor(raw: dict) -> Factor:
    return Factor(
        value=float(raw["value"]),
        unit=str(raw.get("unit", "")),
        tier=Tier(int(raw["tier"])),
        min=float(raw["min"]) if "min" in raw else None,
        max=float(raw["max"]) if "max" in raw else None,
        source=raw.get("source", "") or "",
        note=raw.get("note", "") or "",
    )


def _date(v) -> date | None:
    if v is None:
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _provenance(raw: dict | None) -> Provenance:
    """Parse an OKF v0.2 style block::

    provenance:
      generated: {by: agent:claude, at: 2026-09-18}
      verified: [{by: human:reviewer, at: 2026-09-20}]
      status: draft
      stale_after: 2027-03-31
      sources: [{resource: https://...}]
    """
    raw = raw or {}
    gen = raw.get("generated") or {}
    ver = raw.get("verified") or []
    if isinstance(ver, dict):
        ver = [ver]
    sources = []
    for src in raw.get("sources") or []:
        sources.append(src["resource"] if isinstance(src, dict) else str(src))
    return Provenance(
        generated_by=str(gen.get("by", "") or ""),
        generated_at=_date(gen.get("at")),
        verified=tuple(
            Verification(by=str(v["by"]), at=_date(v.get("at"))) for v in ver
        ),
        status=LifecycleStatus(raw.get("status", "draft")),
        stale_after=_date(raw.get("stale_after")),
        sources=tuple(sources),
    )


def _weights(raw: dict) -> tuple[tuple[str, float], ...]:
    """A ``candidates: {id: weight}`` map as (id, weight) pairs."""
    return tuple((k, float(w)) for k, w in (raw.get("candidates") or {}).items())


def _read(name: str) -> dict:
    with open(DATA_DIR / name) as f:
        return yaml.safe_load(f) or {}


class KnowledgeBase:
    def __init__(self):
        self.hardware: dict[str, Hardware] = {}
        self.regions: dict[str, Region] = {}
        self.providers: dict[str, Provider] = {}
        self.models: dict[str, Model] = {}
        # lower-cased id or alias -> canonical id, for case-insensitive lookup
        self._model_index: dict[str, str] = {}
        self._provider_index: dict[str, str] = {}
        self.fallback_provider_id: str | None = None
        # creator -> provider id serving its closed models first-party
        self.first_party_provider: dict[str, str] = {}
        # API host -> provider id; a leading dot matches any subdomain
        self._host_index: dict[str, str] = {}

    @classmethod
    def load(cls) -> KnowledgeBase:
        kb = cls()
        for hid, raw in _read("hardware.yaml").get("hardware", {}).items():
            kb.hardware[hid] = Hardware(
                id=hid,
                label=raw.get("label", hid),
                tdp_w=_factor(raw["tdp_w"]),
                peak_dense_flops=_factor(raw["peak_dense_flops"]),
                embodied_kgco2e_per_gpu=_factor(raw["embodied_kgco2e_per_gpu"]),
                lifetime_years=_factor(raw["lifetime_years"]),
                active_fraction=_factor(raw["active_fraction"]),
                **(
                    {"energy_vs_h100": _factor(raw["energy_vs_h100"])}
                    if "energy_vs_h100" in raw
                    else {}
                ),
                provenance=_provenance(raw.get("provenance")),
            )
        for rid, raw in _read("regions.yaml").get("regions", {}).items():
            kb.regions[rid] = Region(
                id=rid,
                label=raw.get("label", rid),
                country=raw["country"],
                carbon_intensity_gco2e_per_kwh=_factor(
                    raw["carbon_intensity_gco2e_per_kwh"]
                ),
                primary_energy_factor=_factor(raw["primary_energy_factor"]),
                water_l_per_kwh_generation=_factor(raw["water_l_per_kwh_generation"]),
                mix={
                    EnergySource(k): float(v) for k, v in (raw.get("mix") or {}).items()
                },
                dataset_year=int(raw.get("dataset_year", 0)),
                mix_source=raw.get("mix_source", "") or "",
                provenance=_provenance(raw.get("provenance")),
            )
        pdoc = _read("providers.yaml")
        kb.fallback_provider_id = pdoc.get("fallback")
        for pid, raw in pdoc.get("providers", {}).items():
            kb.providers[pid] = Provider(
                id=pid,
                label=raw.get("label", pid),
                hosts=tuple(raw.get("hosts") or ()),
                region=raw["region"]["value"],
                region_tier=Tier(int(raw["region"]["tier"])),
                hardware=raw["hardware"]["value"],
                hardware_tier=Tier(int(raw["hardware"]["tier"])),
                pue=_factor(raw["pue"]),
                wue_l_per_kwh=_factor(raw["wue_l_per_kwh"]),
                decode_utilization=_factor(raw["decode_utilization"]),
                prefill_utilization=_factor(raw["prefill_utilization"]),
                serving_overhead=_factor(raw["serving_overhead"]),
                region_candidates=_weights(raw["region"]),
                hardware_candidates=_weights(raw["hardware"]),
                provenance=_provenance(raw.get("provenance")),
            )
            kb._provider_index[pid.lower()] = pid
            for host in kb.providers[pid].hosts:
                kb._index_host(host, pid)
        mdoc = _read("models.yaml")
        kb.first_party_provider = mdoc.get("first_party_provider") or {}
        for mid, raw in mdoc.get("models", {}).items():
            measured = raw.get("measured_wh_per_1k_output_tokens_h100")
            kb.models[mid] = Model(
                id=mid,
                label=raw.get("label", mid),
                creator=raw.get("creator", ""),
                active_params_b=_factor(raw["active_params_b"]),
                total_params_b=raw.get("total_params_b"),
                open_weights=bool(raw.get("open_weights", False)),
                measured_wh_per_1k_output_tokens_h100=(
                    _factor(measured) if measured else None
                ),
                provenance=_provenance(raw.get("provenance")),
            )
            for key in [mid, *(raw.get("aliases") or [])]:
                kb._index_model(key, mid)
        kb._validate()
        return kb

    def _validate(self):
        for p in self.providers.values():
            if p.region not in self.regions:
                raise ValueError(f"provider {p.id}: unknown region {p.region}")
            for rid, _ in p.region_candidates:
                if rid not in self.regions:
                    raise ValueError(f"provider {p.id}: unknown candidate {rid}")
            if p.hardware not in self.hardware:
                raise ValueError(f"provider {p.id}: unknown hardware {p.hardware}")
            for hid, _ in p.hardware_candidates:
                if hid not in self.hardware:
                    raise ValueError(
                        f"provider {p.id}: unknown hardware candidate {hid}"
                    )
        for creator, pid in self.first_party_provider.items():
            if pid not in self.providers:
                raise ValueError(f"first_party_provider {creator}: unknown {pid}")
        for r in self.regions.values():
            if r.mix and abs(sum(r.mix.values()) - 1) > 0.02:
                raise ValueError(
                    f"region {r.id}: mix sums to {sum(r.mix.values()):.2f}"
                )

    # ---- lookups -------------------------------------------------------

    def resolve_model(self, model_id: str) -> Model:
        """The model record for an id or alias, ignoring case; raises
        UnknownModelError."""
        # the id as given, then without a prefix like accounts/fireworks/models/
        for key in (model_id, model_id.rsplit("/", 1)[-1]):
            if mid := self._model_index.get(key.lower()):
                return self.models[mid]
        tail = model_id.rsplit("/", 1)[-1]
        raise UnknownModelError(model_id, _similar(tail, self._model_index))

    def resolve_provider(
        self,
        provider_id: str | None,
        *,
        base_url: str | None = None,
        model: Model | None = None,
    ) -> tuple[Provider, str | None]:
        """(provider, reason code or None). In order: an explicit id (an
        unrecognised one raises UnknownProviderError, since a typo would
        otherwise silently estimate the wrong site); a base_url whose host a
        provider publishes; a closed model's first-party provider; the
        fallback."""
        if provider_id is not None:
            pid = self._provider_index.get(provider_id.lower())
            if not pid:
                raise UnknownProviderError(
                    provider_id, _similar(provider_id, self._provider_index)
                )
            return self._with_reason(pid, None)
        if base_url and (pid := self.provider_for_host(base_url)):
            return self._with_reason(pid, None)
        if model and not model.open_weights:
            if pid := self.first_party_provider.get(model.creator):
                return self._with_reason(pid, "provider_inferred_from_model")
        return self._with_reason(self.fallback_provider_id, None)

    def provider_for_host(self, url_or_host: str) -> str | None:
        """The provider id publishing this API host, or None."""
        host = (
            urlparse(
                url_or_host if "//" in url_or_host else "//" + url_or_host
            ).hostname
            or ""
        ).lower()
        if pid := self._host_index.get(host):
            return pid
        for entry, pid in self._host_index.items():
            if entry.startswith(".") and host.endswith(entry):
                return pid
        return None

    def _with_reason(self, pid: str, reason: str | None) -> tuple[Provider, str | None]:
        if pid == self.fallback_provider_id:
            reason = "provider_unknown_fallback"
        return self.providers[pid], reason

    def _index_host(self, host: str, pid: str):
        other = self._host_index.setdefault(host.lower(), pid)
        if other != pid:
            raise ValueError(f"host {host!r} is published by {other} and {pid}")

    def _index_model(self, key: str, mid: str):
        other = self._model_index.setdefault(key.lower(), mid)
        if other != mid:
            raise ValueError(f"model id or alias {key!r} is used by {other} and {mid}")


def _similar(key: str, index: dict[str, str]) -> list[str]:
    """Up to three canonical ids whose id or alias looks like ``key``."""
    close = difflib.get_close_matches(key.lower(), index, n=6, cutoff=0.6)
    return list(dict.fromkeys(index[c] for c in close))[:3]


@functools.lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    return KnowledgeBase.load()
