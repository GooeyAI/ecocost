"""ecocost: estimated carbon, energy and water per LLM run.

Pure Python; the only dependency is PyYAML. See METHODOLOGY.md for how the
estimate is built and CONTRIBUTING.md for how to update the data.

    >>> from ecocost import estimate
    >>> estimate("accounts/fireworks/models/gpt-oss-120b", provider="fireworks",
    ...          input_tokens=800, output_tokens=300)["carbon"]
    {'unit': 'gCO2e', 'value': ..., 'min': ..., 'max': ...}
"""

from __future__ import annotations

import dataclasses
from importlib.metadata import PackageNotFoundError, version
from numbers import Integral

from . import calc
from .errors import UnknownModelError, UnknownProviderError, UnknownRegionError
from .loader import get_kb
from .result import EstimateResult
from .schema import Tier

__all__ = [
    "estimate",
    "EstimateResult",
    "UnknownModelError",
    "UnknownProviderError",
    "UnknownRegionError",
]

# far above any single request; beyond it the float maths would overflow
MAX_TOKENS = 10**12

try:
    __version__ = version("ecocost")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0+unknown"


def estimate(
    model: str,
    *,
    provider: str | None = None,
    endpoint: str | None = None,
    region: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
) -> EstimateResult:
    """Estimate one request.

    ``model`` is a model id; provider-specific ids resolve through aliases.
    Who serves the request is taken, in order, from ``provider`` (an id from
    providers.yaml, listed in the README), else ``endpoint`` (the API URL or
    host called, if a provider publishes that host), else, for a closed model, its vendor's
    own API; otherwise wide US defaults. ``reasons`` says when it was inferred
    or defaulted.

    ``region`` is a grid region id from regions.yaml (``US-VA``, ``SG``, ...)
    for when you know where the request ran. It replaces the provider's
    region, including one implied by ``endpoint``; the provider still sets
    PUE, water use and hardware.

    Ids are matched ignoring case. ``UnknownModelError``,
    ``UnknownProviderError`` and ``UnknownRegionError`` suggest close matches and where to add the
    record. Bad arguments raise ``TypeError`` or ``ValueError``.
    """
    _check_args(
        model,
        provider,
        endpoint,
        region,
        input_tokens,
        output_tokens,
        cached_input_tokens,
    )
    kb = get_kb()
    m = kb.resolve_model(model)
    p, provider_reason = kb.resolve_provider(provider, endpoint=endpoint, model=m)
    if region is not None:
        # the caller knows the site: it is pinned, so no candidates or widening
        p = dataclasses.replace(
            p,
            region=kb.resolve_region(region).id,
            region_tier=Tier.primary,
            region_candidates=(),
        )
    est = calc.estimate(
        m,
        p,
        kb.regions[p.region],
        kb.hardware[p.hardware],
        kb.hardware[calc.REFERENCE_HARDWARE_ID],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        candidate_regions=[(kb.regions[rid], w) for rid, w in p.region_candidates],
        candidate_hardware=[(kb.hardware[hid], w) for hid, w in p.hardware_candidates],
    )
    if provider_reason:
        est.reasons.insert(0, provider_reason)
    out = est.to_dict()
    out["requested"] = {
        "model": model,
        "provider": provider,
        "endpoint": endpoint,
        "region": region,
    }
    return out


def _check_args(
    model, provider, endpoint, region, input_tokens, output_tokens, cached_input_tokens
):
    if not isinstance(model, str):
        raise TypeError(f"model must be a string, got {type(model).__name__}")
    if not model:
        raise ValueError("model must not be empty")
    for name, value in (
        ("provider", provider),
        ("endpoint", endpoint),
        ("region", region),
    ):
        if value is not None and not isinstance(value, str):
            raise TypeError(
                f"{name} must be a string or None, got {type(value).__name__}"
            )
    for name, n in (
        ("input_tokens", input_tokens),
        ("output_tokens", output_tokens),
        ("cached_input_tokens", cached_input_tokens),
    ):
        if isinstance(n, bool) or not isinstance(n, Integral):
            raise TypeError(f"{name} must be an int, got {type(n).__name__}")
        if not 0 <= n <= MAX_TOKENS:
            raise ValueError(f"{name} must be between 0 and {MAX_TOKENS:,}, got {n}")
    if cached_input_tokens > input_tokens:
        raise ValueError(
            f"cached_input_tokens ({cached_input_tokens}) exceeds input_tokens "
            f"({input_tokens}); input_tokens counts cached tokens too"
        )
