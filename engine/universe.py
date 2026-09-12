"""The fixed investable universe.

Deliberately small. A fixed universe means every portfolio is a weight vector
over the same assets, which makes comparison, backtesting and rebalancing
trivial. Expanding this later is a one-line change per asset.

`mu` and `sigma` are long-run annualized return / volatility estimates. They are
ONLY used to generate synthetic fallback data when real prices are unavailable.
All reported metrics are computed from the actual price series.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    ticker: str
    name: str
    kind: str  # "equity" | "bond" | "real_asset"
    beta: float  # sensitivity to the common market factor
    mu: float  # annualized drift, synthetic data only
    sigma: float  # annualized idiosyncratic vol, synthetic data only
    expense_ratio: float


UNIVERSE: tuple[Asset, ...] = (
    # Broad equity
    Asset("VTI", "US Total Market", "equity", 1.00, 0.098, 0.055, 0.0003),
    Asset("VXUS", "International ex-US", "equity", 0.88, 0.070, 0.075, 0.0007),
    Asset("QQQ", "Nasdaq 100", "equity", 1.15, 0.125, 0.090, 0.0020),
    Asset("VBR", "US Small-Cap Value", "equity", 1.05, 0.095, 0.100, 0.0007),
    # Single names — the "which stocks" part of the brief
    Asset("AAPL", "Apple", "equity", 1.12, 0.150, 0.180, 0.0000),
    Asset("MSFT", "Microsoft", "equity", 1.05, 0.150, 0.170, 0.0000),
    Asset("NVDA", "NVIDIA", "equity", 1.60, 0.220, 0.330, 0.0000),
    Asset("JNJ", "Johnson & Johnson", "equity", 0.60, 0.070, 0.140, 0.0000),
    Asset("JPM", "JPMorgan Chase", "equity", 1.10, 0.105, 0.190, 0.0000),
    # Defensive
    Asset("BND", "US Aggregate Bond", "bond", 0.12, 0.032, 0.045, 0.0003),
    Asset("TLT", "Long Treasury", "bond", -0.10, 0.030, 0.140, 0.0015),
    Asset("TIP", "Inflation-Protected", "bond", 0.10, 0.030, 0.055, 0.0019),
    Asset("BIL", "1-3 Month T-Bill", "bond", 0.00, 0.025, 0.004, 0.0014),
    # Diversifiers
    Asset("GLD", "Gold", "real_asset", 0.05, 0.055, 0.150, 0.0040),
    Asset("VNQ", "US Real Estate", "real_asset", 0.95, 0.075, 0.130, 0.0013),
)

TICKERS: tuple[str, ...] = tuple(a.ticker for a in UNIVERSE)
BY_TICKER: dict[str, Asset] = {a.ticker: a for a in UNIVERSE}


def expense_ratio(weights: dict[str, float]) -> float:
    """Weighted average expense ratio of a portfolio."""
    return sum(w * BY_TICKER[t].expense_ratio for t, w in weights.items())
