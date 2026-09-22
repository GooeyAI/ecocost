"""Human formatting for eco-cost figures. UI-agnostic, no HTML."""

from __future__ import annotations


def _sig(x: float, sig: int = 2) -> str:
    """Two significant figures, never scientific notation: 150, 8.2, 0.41."""
    return f"{float(f'{x:.{sig}g}'):,.10g}"


def format_grams(g: float) -> str:
    """5.1 -> '5.1 g', 0.0177 -> '18 mg', 0.00002 -> '<0.1 mg', 1234 -> '1.2 kg'."""
    g = float(g)
    if g >= 1000:
        return f"{_sig(g / 1000, 3)} kg"
    if g >= 1:
        return f"{_sig(g)} g"
    mg = g * 1000
    if mg >= 0.1:
        return f"{_sig(mg)} mg"
    return "<0.1 mg"


def format_wh(wh: float) -> str:
    wh = float(wh)
    if wh >= 1000:
        return f"{_sig(wh / 1000, 3)} kWh"
    if wh >= 1:
        return f"{_sig(wh)} Wh"
    return f"{_sig(wh * 1000)} mWh"


def format_ml(ml: float) -> str:
    ml = float(ml)
    if ml >= 1000:
        return f"{_sig(ml / 1000, 3)} L"
    return f"{_sig(ml)} mL"
