"""Quantitative features, computed point-in-time.

Every function here returns a frame indexed by the same dates as its input, in
which the value at row `t` uses only rows `<= t`. That is the entire contract
of this module, and `test_agent.py::no_lookahead_in_any_feature` re-derives
each feature on a truncated history and asserts the value at `t` is unchanged.

A backtest that computes a z-score over the full sample and then "tests" on it
is not a backtest. Rolling windows with `min_periods` equal to the window are
the cheapest defence against that, so every window here is closed.

Only daily closes are available (`data/prices.csv` has no high/low), so true
range is approximated from close-to-close movement. `atr` is therefore named
`atr_proxy` everywhere it is returned, because a stop placed off a proxy is a
different object from a stop placed off a real ATR and the caller should know.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Window lengths. Named constants rather than literals because the no-lookahead
# test needs to know the longest warmup to skip.
EMA_FAST = 20
EMA_SLOW = 100
ATR_SPAN = 20
MOMENTUM_LOOKBACK = 252
MOMENTUM_SKIP = 21
REVERSION_WINDOW = 20
BREAKOUT_WINDOW = 55
VOL_WINDOW = 20
VOL_BASELINE = 252
REGIME_TREND = 200

WARMUP = max(EMA_SLOW, MOMENTUM_LOOKBACK, BREAKOUT_WINDOW, VOL_BASELINE, REGIME_TREND)

FEATURE_NAMES = ("trend", "momentum", "reversion", "breakout", "vol_z")


# ── Building blocks ──────────────────────────────────────────────────────────

def atr_proxy(close: pd.Series, span: int = ATR_SPAN) -> pd.Series:
    """Average absolute close-to-close move. Stands in for ATR.

    `adjust=False` makes this a true recursive EMA, so the value at `t` depends
    only on `t` and the value at `t-1` — no renormalisation over the whole
    sample, which an `adjust=True` EMA quietly does.
    """
    move = close.diff().abs()
    return move.ewm(span=span, adjust=False, min_periods=span).mean()


def realized_vol(close: pd.Series, window: int = VOL_WINDOW) -> pd.Series:
    r = close.pct_change()
    return r.rolling(window, min_periods=window).std() * np.sqrt(TRADING_DAYS)


def _squash(x: pd.Series, scale: float) -> pd.Series:
    """Map an unbounded feature onto (-1, 1) without clipping information.

    tanh rather than a hard clip: a signal three times the usual size should
    still rank above one twice the usual size, just with diminishing weight.
    """
    return np.tanh(x / scale)


# ── Features ─────────────────────────────────────────────────────────────────

def trend(close: pd.Series) -> pd.Series:
    """Fast/slow EMA separation, in units of daily range.

    Dividing by ATR is what makes this comparable across a $4 stock and a $400
    one; the raw spread is not.
    """
    fast = close.ewm(span=EMA_FAST, adjust=False, min_periods=EMA_FAST).mean()
    slow = close.ewm(span=EMA_SLOW, adjust=False, min_periods=EMA_SLOW).mean()
    return _squash((fast - slow) / atr_proxy(close), scale=8.0)


def momentum(close: pd.Series) -> pd.Series:
    """Twelve-month return excluding the most recent month.

    The skip is not decoration. Short-horizon returns reverse, so including the
    last month mixes a reversal effect into a continuation signal and the two
    partially cancel.
    """
    trailing = close.shift(MOMENTUM_SKIP)
    raw = trailing / trailing.shift(MOMENTUM_LOOKBACK - MOMENTUM_SKIP) - 1.0
    return _squash(raw, scale=0.35)


def reversion(close: pd.Series) -> pd.Series:
    """Negated z-score against a 20-day mean: oversold reads positive."""
    mean = close.rolling(REVERSION_WINDOW, min_periods=REVERSION_WINDOW).mean()
    sd = close.rolling(REVERSION_WINDOW, min_periods=REVERSION_WINDOW).std(ddof=1)
    z = (close - mean) / sd.replace(0.0, np.nan)
    return _squash(-z, scale=2.0)


def breakout(close: pd.Series) -> pd.Series:
    """Distance from the trailing 55-day high, in ATR units.

    The window is shifted by one bar so today's own close cannot set the high
    it is being compared against — otherwise the feature reads 0.0 at every new
    high and the signal inverts.
    """
    prior_high = close.shift(1).rolling(BREAKOUT_WINDOW, min_periods=BREAKOUT_WINDOW).max()
    return _squash((close - prior_high) / atr_proxy(close), scale=3.0)


def vol_z(close: pd.Series) -> pd.Series:
    """Current realized vol against its own trailing year. Not directional.

    Used to damp position conviction when the market is unusually violent, and
    to classify the regime the risk gate asks for.
    """
    v = realized_vol(close)
    baseline = v.rolling(VOL_BASELINE, min_periods=VOL_BASELINE // 2).median()
    sd = v.rolling(VOL_BASELINE, min_periods=VOL_BASELINE // 2).std(ddof=1)
    return _squash((v - baseline) / sd.replace(0.0, np.nan), scale=2.0)


def features_for(close: pd.Series) -> pd.DataFrame:
    """All five features for one symbol, plus the ATR proxy stops are sized on."""
    return pd.DataFrame(
        {
            "trend": trend(close),
            "momentum": momentum(close),
            "reversion": reversion(close),
            "breakout": breakout(close),
            "vol_z": vol_z(close),
            "atr_proxy": atr_proxy(close),
            "close": close,
        }
    )


def features(prices: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Feature frame per symbol. Symbols with too little history are dropped."""
    out: Dict[str, pd.DataFrame] = {}
    for ticker in prices.columns:
        f = features_for(prices[ticker].astype(float))
        if f[list(FEATURE_NAMES)].notna().any(axis=1).sum() > 0:
            out[ticker] = f
    return out


# ── Market regime ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RegimeSeries:
    """Labels plus how many consecutive bars each label has held.

    `trading.checks` vetoes a proposal whose regime has held fewer than three
    bars, so the stability count is not a diagnostic — it is an input to the
    gate and has to be computed point-in-time like everything else.
    """

    label: pd.Series
    stability: pd.Series

    def at(self, date) -> tuple:
        return str(self.label.loc[date]), int(self.stability.loc[date])


def classify_regime(benchmark: pd.Series) -> RegimeSeries:
    """calm / volatile / bear from the benchmark series alone.

    bear      below the 200-day average *and* more than 10% off the year's peak
    volatile  realized vol in the top quartile of its own trailing year
    calm      everything else

    Requiring both conditions for `bear` keeps a single sharp dip below the
    average from flipping the whole desk defensive for one bar.
    """
    close = benchmark.astype(float)
    sma = close.rolling(REGIME_TREND, min_periods=REGIME_TREND).mean()
    peak = close.rolling(TRADING_DAYS, min_periods=TRADING_DAYS // 2).max()
    off_peak = close / peak - 1.0

    v = realized_vol(close)
    hi_vol = v.rolling(VOL_BASELINE, min_periods=VOL_BASELINE // 2).quantile(0.75)

    label = pd.Series("calm", index=close.index, dtype=object)
    label[(v > hi_vol).fillna(False)] = "volatile"
    label[((close < sma) & (off_peak <= -0.10)).fillna(False)] = "bear"
    # Before the longest window fills there is no honest label to give.
    label[sma.isna()] = "unknown"

    changed = label.ne(label.shift(1))
    group = changed.cumsum()
    stability = label.groupby(group).cumcount() + 1

    return RegimeSeries(label=label, stability=stability.astype(int))


def warmup_date(index: pd.DatetimeIndex) -> pd.Timestamp:
    """First date on which every feature is defined. Nothing trades before it."""
    if len(index) <= WARMUP:
        raise ValueError(
            f"need more than {WARMUP} bars of history; got {len(index)}"
        )
    return index[WARMUP]


def tradable_dates(prices: pd.DataFrame) -> List[pd.Timestamp]:
    return list(prices.index[prices.index >= warmup_date(prices.index)])
