"""Model portfolios and the time-horizon glide path.

Three static targets, one per risk tier. Horizon is applied *on top* of the
tier by blending toward a capital-preservation anchor: a 30-year-old saving
aggressively for a house purchase in 2 years should not be 95% equity no matter
what they clicked. This is the single most defensible piece of finance in the
project and it costs four lines.
"""

from __future__ import annotations

from .universe import BY_TICKER

RiskTier = str  # "conservative" | "balanced" | "aggressive"

TARGETS: dict[RiskTier, dict[str, float]] = {
    "conservative": {
        "BIL": 0.10, "BND": 0.30, "TIP": 0.15, "TLT": 0.05,
        "VTI": 0.20, "VXUS": 0.08, "GLD": 0.07, "JNJ": 0.05,
    },
    "balanced": {
        "VTI": 0.32, "VXUS": 0.13, "QQQ": 0.08, "VBR": 0.05,
        "BND": 0.18, "TIP": 0.05, "GLD": 0.05, "VNQ": 0.04,
        "AAPL": 0.04, "MSFT": 0.04, "JNJ": 0.02,
    },
    "aggressive": {
        "VTI": 0.24, "VXUS": 0.10, "QQQ": 0.18, "VBR": 0.08,
        "NVDA": 0.08, "AAPL": 0.07, "MSFT": 0.07, "JPM": 0.05,
        "VNQ": 0.05, "GLD": 0.03, "BND": 0.05,
    },
}

# What every portfolio collapses toward as the horizon shortens.
PRESERVATION: dict[str, float] = {"BIL": 0.55, "BND": 0.25, "TIP": 0.12, "VTI": 0.08}

FULL_HORIZON_YEARS = 15.0
MIN_BLEND = 0.20

LABELS = {
    "conservative": "Conservative",
    "balanced": "Balanced",
    "aggressive": "Aggressive",
}


def horizon_factor(years: float) -> float:
    """1.0 at 15+ years, floored at 0.20 for very short horizons."""
    return max(MIN_BLEND, min(1.0, years / FULL_HORIZON_YEARS))


def blend(a: dict[str, float], b: dict[str, float], w: float) -> dict[str, float]:
    """w*a + (1-w)*b, dropping negligible positions and renormalizing."""
    out: dict[str, float] = {}
    for t in set(a) | set(b):
        v = w * a.get(t, 0.0) + (1.0 - w) * b.get(t, 0.0)
        if v > 0.0025:  # below 0.25% isn't a position, it's noise
            out[t] = v
    total = sum(out.values())
    return {t: v / total for t, v in sorted(out.items(), key=lambda kv: -kv[1])}


def target_weights(risk: RiskTier, horizon_years: float) -> dict[str, float]:
    if risk not in TARGETS:
        raise ValueError(f"unknown risk tier {risk!r}; expected one of {list(TARGETS)}")
    return blend(TARGETS[risk], PRESERVATION, horizon_factor(horizon_years))


def equity_share(weights: dict[str, float]) -> float:
    return sum(w for t, w in weights.items() if BY_TICKER[t].kind == "equity")
