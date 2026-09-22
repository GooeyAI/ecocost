"""Citation checks: every value is cited, every cited source is registered in
sources.yaml with its licence, and sources with conditions stay within them."""

import functools
import re
from pathlib import Path

import pytest
import yaml

from ecocost.loader import DATA_DIR

NOTICE = Path(__file__).parents[2] / "NOTICE"
URL = re.compile(r"https?://[^\s,;)\]}'\"]+")
# a value with no external source says why in `note`
NON_URL_SOURCES = {"assumption", "derived", "definition"}


def test_every_value_is_cited():
    for path, factor in _factors():
        source = str(factor.get("source") or "")
        assert URL.search(source) or source in NON_URL_SOURCES, (
            f"{path}: needs a source URL or one of {sorted(NON_URL_SOURCES)}"
        )
        if not URL.search(source):
            assert factor.get("note"), f"{path}: source {source!r} needs a note"
            assert source != "assumption" or factor["tier"] == 3, (
                f"{path}: an assumption is tier 3"
            )


def test_every_cited_url_is_registered():
    registry = _registry()
    unregistered = sorted(
        {url for _, url, _ in _citations() if not _match(url, registry)}
    )
    assert not unregistered, f"add these to sources.yaml: {unregistered}"


def test_every_registered_source_is_cited():
    used = {sid for _, url, _ in _citations() for sid in _match(url, _registry())}
    assert set(_registry()) == used, f"unused: {set(_registry()) - used}"


def test_capped_sources_stay_within_their_cap():
    registry = _registry()
    for sid, entry in registry.items():
        if "max_values" not in entry:
            continue
        n = sum(
            1
            for _, url, is_value in _citations()
            if is_value and sid in _match(url, registry)
        )
        assert n <= entry["max_values"], f"{sid}: {n} values, cap {entry['max_values']}"


def test_secondary_sources_never_back_a_tier_1_value():
    registry = _registry()
    for path, factor in _factors():
        for url in URL.findall(str(factor.get("source") or "")):
            kinds = {registry[sid]["kind"] for sid in _match(url, registry)}
            assert not ("secondary" in kinds and factor["tier"] == 1), path


@pytest.mark.skipif(not NOTICE.exists(), reason="NOTICE is not shipped with tests")
def test_sources_that_require_attribution_are_in_notice():
    notice = " ".join(NOTICE.read_text().split())
    for sid, entry in _registry().items():
        if entry.get("attribution"):
            assert entry.get("notice"), f"{sid}: attribution needs a notice string"
        if entry.get("notice"):
            assert entry["notice"] in notice, (
                f"{sid}: add {entry['notice']!r} to NOTICE"
            )


@functools.cache
def _registry() -> dict:
    return yaml.safe_load((DATA_DIR / "sources.yaml").read_text())["sources"]


def _match(url: str, registry: dict) -> list[str]:
    """Registry ids whose `match` covers the URL (host suffix + path prefix)."""
    host, _, path = re.sub(r"^https?://(www\.)?", "", url).partition("/")
    matched = []
    for sid, entry in registry.items():
        for pattern in entry["match"]:
            p_host, _, p_path = pattern.partition("/")
            if (host == p_host or host.endswith("." + p_host)) and path.startswith(
                p_path
            ):
                matched.append(sid)
                break
    return matched


def _factors():
    """(path, dict) for every value in the knowledge base."""
    for path, node in _walk_data():
        if isinstance(node, dict) and "value" in node and "tier" in node:
            yield path, node


def _citations():
    """(path, url, is_value) for every URL cited: values' `source`, plus
    `mix_source` and provenance `resource` entries."""
    for path, node in _walk_data():
        if not isinstance(node, dict):
            continue
        is_value = "value" in node and "tier" in node
        for key in ("source", "mix_source", "resource"):
            for url in URL.findall(str(node.get(key) or "")):
                yield path, url, is_value and key == "source"


def _walk_data():
    for name, doc in _data():
        yield from _walk(doc, name)


@functools.cache
def _data() -> tuple:
    return tuple(
        (f.name, yaml.safe_load(f.read_text()))
        for f in sorted(DATA_DIR.glob("*.yaml"))
        if f.name != "sources.yaml"
    )


def _walk(node, path):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
