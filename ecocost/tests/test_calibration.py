"""The calibration table in METHODOLOGY.md, recomputed so it can't drift from
the code. A method change that moves an anchor fails here until the table is
updated; one that brings the production anchor into range flips `inside`."""

from pathlib import Path

import pytest

from ecocost import estimate

METHODOLOGY = Path(__file__).parents[2] / "METHODOLOGY.md"

# model, input tokens, output tokens, published Wh, inside our likely range
ANCHORS = [
    # Jegham et al. 2025, arXiv 2505.09598 v6, Table 4: API-based, PUE included
    ("llama-3.3-70b", 100, 300, 0.237, True),
    # Elsworth et al. 2025, arXiv 2509.20241: FP8 production batching, median;
    # below the range because the size-based path assumes BF16
    ("llama-3.1-405b", 500, 300, 0.39, False),
]


@pytest.mark.parametrize("model,input_tokens,output_tokens,published,inside", ANCHORS)
def test_anchor(model, input_tokens, output_tokens, published, inside):
    energy = estimate(
        model,
        provider="unknown-us",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )["energy"]
    assert (energy["min"] <= published <= energy["max"]) == inside
    if METHODOLOGY.exists():
        row = f"{energy['value']} ({energy['min']}–{energy['max']})"
        assert row in METHODOLOGY.read_text(), f"update METHODOLOGY.md: {row}"
