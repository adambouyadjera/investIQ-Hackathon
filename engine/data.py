"""Price data loading.

Three tiers, tried in order:
  1. data/prices.csv          -- the snapshot. Fast, offline, reproducible.
  2. yfinance                  -- live download, writes the snapshot for next time.
  3. synthetic generator       -- deterministic fake data so the app always runs.

The synthetic tier exists so a demo never dies because an API rate-limited you
five minutes before you present. It is clearly flagged: `load_prices` returns
the source it used, and the UI should surface that.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from .universe import TICKERS, UNIVERSE

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT = DATA_DIR / "prices.csv"

TRADING_DAYS = 252
DEFAULT_YEARS = 12


def load_prices(
    years: int = DEFAULT_YEARS, allow_network: bool = True
) -> tuple[pd.DataFrame, str]:
    """Return (prices, source) where prices is a daily close DataFrame.

    Index is a DatetimeIndex, columns are tickers, no missing values.
    """
    if SNAPSHOT.exists():
        df = pd.read_csv(SNAPSHOT, index_col=0, parse_dates=True)
        missing = [t for t in TICKERS if t not in df.columns]
        if not missing:
            return _clean(df[list(TICKERS)]), "snapshot"

    if allow_network and os.environ.get("PS_NO_NETWORK") != "1":
        df = _try_yfinance(years)
        if df is not None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(SNAPSHOT)
            return _clean(df), "yfinance"

    return _synthetic(years), "synthetic"


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_index().ffill().dropna()


def _try_yfinance(years: int) -> pd.DataFrame | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        raw = yf.download(
            list(TICKERS),
            period=f"{years}y",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw is None or raw.empty:
            return None
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        close = close[list(TICKERS)].dropna(how="all")
        # Require a reasonable amount of history before trusting it.
        if len(close) < TRADING_DAYS * 2:
            return None
        return close
    except Exception:
        return None


def _synthetic(years: int, seed: int = 20260911) -> pd.DataFrame:
    """Correlated GBM with a shared market factor and two drawdown regimes.

    Correlation comes from the `beta` loading on a common factor, which is both
    simpler and more realistic than a hand-written correlation matrix.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(
        end=pd.Timestamp.today().normalize(), periods=years * TRADING_DAYS
    )
    n = len(dates)
    dt = 1.0 / TRADING_DAYS

    # Common market factor with volatility clustering: calm regime punctuated
    # by two crisis windows where vol triples and drift goes negative.
    factor_vol = np.full(n, 0.14)
    factor_drift = np.full(n, 0.055)
    for start_frac, length_frac in ((0.22, 0.05), (0.61, 0.08)):
        a, b = int(n * start_frac), int(n * (start_frac + length_frac))
        factor_vol[a:b] = 0.42
        factor_drift[a:b] = -0.55
    factor = factor_drift * dt + factor_vol * np.sqrt(dt) * rng.standard_normal(n)

    out = {}
    for asset in UNIVERSE:
        idio = asset.sigma * np.sqrt(dt) * rng.standard_normal(n)
        # Subtract the factor's own drift contribution so total drift ~= mu.
        drift = (asset.mu - asset.beta * 0.055 - 0.5 * asset.sigma**2) * dt
        rets = drift + asset.beta * factor + idio
        out[asset.ticker] = 100.0 * np.exp(np.cumsum(rets))

    return pd.DataFrame(out, index=dates)[list(TICKERS)]


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna()


def portfolio_returns(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Return series of a *constantly rebalanced* portfolio.

    Used for metrics and Monte Carlo. The backtest module models discrete
    rebalancing separately, because the difference is a feature we show.
    """
    rets = daily_returns(prices)
    w = pd.Series(weights, dtype=float).reindex(rets.columns).fillna(0.0)
    return (rets * w).sum(axis=1)
