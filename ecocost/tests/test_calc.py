import pytest

import json

import ecocost
from ecocost import UnknownModelError, UnknownProviderError, estimate
from ecocost.result import EstimateResult
from ecocost.loader import get_kb

TOKENS = dict(input_tokens=800, output_tokens=300)


def test_kb_loads_and_validates():
    kb = get_kb()
    assert "fireworks" in kb.providers and "nscale" in kb.providers
    assert (
        kb.resolve_model("accounts/fireworks/models/gpt-oss-120b").id == "gpt-oss-120b"
    )


def test_hydro_site_beats_undisclosed_us_fleet_on_carbon():
    fw, ns = (
        estimate("gpt-oss-120b", provider="fireworks", **TOKENS),
        estimate("gpt-oss-120b", provider="nscale", **TOKENS),
    )
    assert ns["carbon"]["value"] < fw["carbon"]["value"]
    assert ns["carbon"]["max"] < fw["carbon"]["max"]
    assert ns["confidence"]["ratio"] < fw["confidence"]["ratio"]
    assert "region_inferred" in fw["confidence"]["reasons"]
    assert "region_inferred" not in ns["confidence"]["reasons"]
    assert ns["electricity"]["primary_source"] == "hydro"


def test_closed_model_is_low_confidence_everywhere():
    for pid in ("openai", "nscale"):
        r = estimate("gpt-5.5-2026-04-23", provider=pid, **TOKENS)
        assert r["confidence"]["level"] == "low"
        assert "active_params_undisclosed" in r["confidence"]["reasons"]


def test_unknown_model_raises_with_suggestions_and_where_to_add_it():
    with pytest.raises(UnknownModelError) as e:
        estimate("accounts/fireworks/models/gpt-oss-120", provider="fireworks")
    assert e.value.suggestions[0] == "gpt-oss-120b"
    assert "CONTRIBUTING.md#adding-a-model" in str(e.value)
    assert "issues/new" in str(e.value)

    with pytest.raises(UnknownModelError) as e:
        estimate("some/brand-new-model", provider="fireworks")
    assert e.value.suggestions == []


def test_ranges_are_ordered_and_monotonic_in_tokens():
    a = estimate("gpt-oss-120b", provider="fireworks", output_tokens=100)
    b = estimate("gpt-oss-120b", provider="fireworks", output_tokens=1000)
    for r in (a, b):
        for k in ("carbon", "energy", "water"):
            assert r[k]["min"] <= r[k]["value"] <= r[k]["max"]
    assert b["carbon"]["value"] > a["carbon"]["value"]
    assert b["water"]["value"] > a["water"]["value"]


def test_cached_tokens_are_cheaper():
    fresh = estimate("gpt-oss-120b", provider="fireworks", input_tokens=1000)
    cached = estimate(
        "gpt-oss-120b",
        provider="fireworks",
        input_tokens=1000,
        cached_input_tokens=1000,
    )
    assert cached["energy"]["value"] < fresh["energy"]["value"]


def test_every_provider_id_estimates_without_fallback():
    for pid in get_kb().providers:
        r = estimate("gpt-oss-120b", provider=pid, **TOKENS)
        assert r["provider"] == pid
        if pid != get_kb().fallback_provider_id:
            assert "provider_unknown_fallback" not in r["confidence"]["reasons"]


def test_no_provider_falls_back_and_says_so():
    for provider in (None, "unknown-us"):
        r = estimate("gpt-oss-120b", provider=provider, **TOKENS)
        assert r["confidence"]["reasons"][0] == "provider_unknown_fallback"


def test_mistyped_provider_raises_instead_of_falling_back():
    with pytest.raises(UnknownProviderError) as e:
        estimate("gpt-oss-120b", provider="fireworkz", **TOKENS)
    assert e.value.suggestions[0] == "fireworks"
    assert "provider=None" in str(e.value)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://inference.api.nscale.com/v1", "nscale"),
        ("https://ws-x.ap-southeast-1.maas.aliyuncs.com/v1", "alibaba-sg"),
        ("api.fireworks.ai", "fireworks"),
        ("https://my-gateway.example.com/v1", "unknown-us"),
    ],
)
def test_base_url_resolves_to_the_provider_publishing_its_host(url, expected):
    r = estimate("gpt-oss-20b", base_url=url, **TOKENS)
    assert r["provider"] == expected


def test_closed_model_without_provider_is_inferred_from_its_vendor():
    r = estimate("claude-sonnet-5", **TOKENS)
    assert r["provider"] == "anthropic"
    assert r["confidence"]["reasons"][0] == "provider_inferred_from_model"
    # open weights are served by many providers, so there is no inference
    assert estimate("gpt-oss-20b", **TOKENS)["provider"] == "unknown-us"


def test_explicit_provider_beats_base_url_and_vendor():
    r = estimate(
        "claude-sonnet-5",
        provider="fireworks",
        base_url="https://api.anthropic.com",
        **TOKENS,
    )
    assert r["provider"] == "fireworks"
    assert "provider_inferred_from_model" not in r["confidence"]["reasons"]


def test_ids_match_ignoring_case():
    r = estimate("GPT-OSS-120B", provider="NScale", **TOKENS)
    assert (r["model"], r["provider"]) == ("gpt-oss-120b", "nscale")
    assert r["requested"]["provider"] == "NScale"


@pytest.mark.parametrize(
    "kwargs,error",
    [
        (dict(model=None), TypeError),
        (dict(model=""), ValueError),
        (dict(provider=3), TypeError),
        (dict(output_tokens="10"), TypeError),
        (dict(output_tokens=1.5), TypeError),
        (dict(output_tokens=True), TypeError),
        (dict(input_tokens=-1), ValueError),
        (dict(output_tokens=10**400), ValueError),
        (dict(input_tokens=10, cached_input_tokens=50), ValueError),
    ],
)
def test_bad_arguments_raise_clear_errors(kwargs, error):
    args = dict(model="gpt-oss-120b", provider="nscale") | kwargs
    with pytest.raises(error):
        estimate(**args)


def test_no_tokens_is_an_exact_zero_and_valid_json():
    r = estimate("gpt-oss-120b", provider="nscale")
    assert r["carbon"]["value"] == 0 and r["confidence"]["ratio"] == 1
    json.dumps(r, allow_nan=False)


def test_output_matches_its_typed_dict():
    r = estimate("gpt-oss-120b", provider="nscale", **TOKENS)
    assert set(r) == set(EstimateResult.__annotations__)


def test_version_is_exposed():
    assert ecocost.__version__


def test_format_grams_never_uses_scientific_notation():
    from ecocost.display import format_grams

    assert format_grams(0.15) == "150 mg"
    assert format_grams(0.0038) == "3.8 mg"
    assert format_grams(8.2) == "8.2 g"
    assert format_grams(45) == "45 g"
    assert format_grams(1234) == "1.23 kg"
    assert format_grams(0.00002) == "<0.1 mg"


def test_independent_factors_combine_in_quadrature_not_by_stacking():
    import math

    from ecocost.schema import Range

    r = Range(0.5, 1.0, 2.0) * Range(0.5, 1.0, 2.0)
    assert r.hi == pytest.approx(2 ** math.sqrt(2))
    assert r.lo == pytest.approx(2 ** -math.sqrt(2))
    assert (r.wlo, r.whi) == (0.25, 4.0)
    # sums stay linear: terms usually share upstream work
    assert (Range(1, 2, 3) + Range(1, 2, 3)).hi == 6


def test_likely_range_sits_inside_worst_case():
    r = estimate("gpt-oss-120b", provider="fireworks", **TOKENS)
    for k in ("carbon", "energy", "water"):
        wc = r[k]["worst_case"]
        assert wc["min"] <= r[k]["min"] <= r[k]["value"] <= r[k]["max"] <= wc["max"]
    assert r["carbon"]["max"] / r["carbon"]["min"] < (
        r["carbon"]["worst_case"]["max"] / r["carbon"]["worst_case"]["min"]
    )


def test_undisclosed_site_uses_envelope_of_disclosed_candidates():
    kb = get_kb()
    fw = kb.providers["fireworks"]
    cands = [
        kb.regions[rid].carbon_intensity_gco2e_per_kwh
        for rid, _ in fw.region_candidates
    ]
    r = estimate("gpt-oss-120b", provider="fireworks", **TOKENS)["electricity"]
    assert r["gco2e_per_kwh_range"] == [
        min(c.min for c in cands),
        max(c.max for c in cands),
    ]
    assert (
        r["gco2e_per_kwh_range"][0] < r["gco2e_per_kwh"] < r["gco2e_per_kwh_range"][1]
    )
    # a pinned site is not widened at all
    sg = estimate("qwen3.8-max", provider="alibaba-sg", **TOKENS)["electricity"]
    sing = kb.regions["SG"].carbon_intensity_gco2e_per_kwh
    assert sg["gco2e_per_kwh_range"] == [sing.min, sing.max]


def test_embodied_carbon_is_propagated_from_its_three_inputs():
    hw = get_kb().hardware["h100-sxm"]
    r = hw.embodied_gco2e_per_h100_second
    assert r.mid == pytest.approx(0.005, rel=0.02)
    stacked = (
        (hw.embodied_kgco2e_per_gpu.max / hw.embodied_kgco2e_per_gpu.min)
        * (hw.lifetime_years.max / hw.lifetime_years.min)
        * (hw.active_fraction.max / hw.active_fraction.min)
    )
    assert r.ratio < stacked


def test_every_region_mix_is_sourced_and_sums_to_one():
    for r in get_kb().regions.values():
        assert r.mix_source, r.id
        assert sum(r.mix.values()) == pytest.approx(1, abs=0.005), r.id


def test_water_splits_into_onsite_and_generation():
    r = estimate("gpt-oss-120b", provider="nscale", **TOKENS)["water"]
    assert r["value"] == pytest.approx(
        r["on_site"]["value"] + r["generation"]["value"], rel=0.01
    )
    # hydro grid: upstream water dwarfs the adiabatic-cooled site
    assert r["generation"]["value"] > 5 * r["on_site"]["value"]


def test_generation_water_uses_the_same_candidate_envelope_as_carbon():
    from ecocost.calc import _regional

    kb = get_kb()
    fw = kb.providers["fireworks"]
    cands = [(kb.regions[rid], w) for rid, w in fw.region_candidates]
    facs = [c.water_l_per_kwh_generation for c, _ in cands]
    r = _regional(
        "water_l_per_kwh_generation", kb.regions[fw.region], fw.region_tier, cands, 0.0
    )
    assert (r.lo, r.hi) == (min(f.min for f in facs), max(f.max for f in facs))
    assert r.lo < r.mid < r.hi
    # and the estimate reflects it: Fireworks' upstream water range is far wider
    # than the +/-40% the national record alone would give
    gen = estimate("gpt-oss-120b", provider="fireworks", **TOKENS)["water"][
        "generation"
    ]
    assert gen["max"] / gen["min"] > 10


def test_fleet_chips_change_energy_but_not_work():
    kb = get_kb()
    fw = kb.providers["fireworks"]
    assert fw.hardware_candidates, "fireworks discloses its fleet"
    r = estimate("gpt-oss-120b", provider="fireworks", **TOKENS)
    single = estimate("gpt-oss-120b", provider="sarvam", **TOKENS)  # H100 only
    # work is chip-independent: same H100-seconds either way
    assert (
        r["breakdown"]["h100_seconds"]["value"]
        == single["breakdown"]["h100_seconds"]["value"]
    )
    assert set(r["assumptions"]["hardware"]) == {
        hid for hid, _ in fw.hardware_candidates
    }
    assert 0.8 < r["assumptions"]["chip_energy_vs_h100"] < 1.0


def test_newer_chip_is_not_automatically_greener():
    """ML.ENERGY's paired runs: B200 beats H100 for MoE at high batch but
    loses for small dense models at low batch, so its range must straddle 1."""
    b200 = get_kb().hardware["b200-sxm"].energy_vs_h100
    assert b200.min < 1.0 < b200.max
    assert b200.value < 1.0


def test_envelope_keeps_worst_case_bounds():
    # embodied carbon's worst case is wider than its likely range; a fleet
    # envelope must not collapse it
    r = get_kb().hardware["h100-sxm"].embodied_gco2e_per_h100_second
    est = estimate("gpt-oss-120b", provider="nscale", **TOKENS)
    work = est["breakdown"]["h100_seconds"]
    assert (
        est["carbon"]["worst_case"]["max"] >= work["worst_case"]["max"] * r.whi * 0.99
    )
