"""The decision layer: evidence in, a proposal and a full audit trail out.

Deliberately not a learned model. The requirement is that a person can read
why a trade was proposed, and a linear sum of named contributions satisfies
that in a way a gradient-boosted ensemble does not. Every weight in this file
was written down by hand, is versioned, and is hashed at startup so a silent
edit is visible in the API response.

The invariant that makes the explanation trustworthy:

    sum(e.contribution for e in proposal.evidence) == proposal.raw_score

exactly, not approximately. `test_agent.py::evidence_sums_to_score` asserts it
on every decision in a full backtest. An explanation that does not reconstruct
the number it claims to explain is decoration.

What this module cannot do, structurally:

* **It cannot set size.** It emits `OrderIntent`, which has no quantity field.
  Size is `trading.sizing`'s decision, computed from the stop distance and
  account equity. A high score buys conviction in the journal and nothing else.
* **It cannot bypass the gate.** Every proposal still goes through
  `trading.checks.evaluate`, which can and does veto proposals that score well.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from trading.types import OrderIntent, Side

from . import signals
from .costs import CostModel
from .news import NewsScore

WEIGHTS_VERSION = "w-1"

# Score needed before the desk proposes anything. Set so that a single strong
# feature is not enough -- roughly two features must agree.
#
# 0.35 sits near the 92nd percentile of the historical score distribution, so
# about one symbol-day in thirteen qualifies. That number was chosen for
# *selectivity* -- how often a desk holding at most eight positions should find
# something worth doing -- and not by sweeping thresholds against returns. The
# distinction matters: the first is a capacity decision, the second is a fit,
# and only the second would need to be declared to the deflated-Sharpe penalty
# in `evaluate.py`.
ENTRY_THRESHOLD = 0.35
# Shorts clear a higher bar. Borrow costs, unbounded loss and a long-run upward
# drift in equities all argue the same direction, so the asymmetry is priced in
# here rather than argued about per-trade.
SHORT_THRESHOLD = 0.55

STOP_ATR_MULTIPLE = 2.0
# A stop must be at least this many times the round-trip cost of the trade.
#
# Without it the desk proposes cash-equivalents. BIL moves about 1.4c a day, so
# a 2x ATR stop sits 2.8c from entry while costing $2.09 to get in and out --
# the stop is one percent of the friction. `_targets` then dutifully places a
# target far enough away to satisfy 2.5R *after* costs, and the geometry check
# passes on a trade that is pure cost. The rule is expressed against cost
# rather than as a list of banned tickers because the thing that makes the
# trade unviable is the ratio, not the symbol.
MIN_STOP_TO_COST = 2.0
TARGET_1_R = 1.0
TARGET_RR = 2.5          # after costs, against a 2.0R policy minimum
MAX_VOL_DAMP = 0.35


@dataclass(frozen=True)
class WeightSet:
    """How much each piece of evidence counts, per regime.

    `calm`      trend-following works; let continuation signals lead.
    `volatile`  continuation signals whipsaw; lean on reversion, damp everything.
    `bear`      the only signals worth much are the slow ones. News gets a
                *lower* weight here, not a higher one -- in a drawdown the tape
                is saturated with alarming headlines that are already priced.
    """

    trend: float
    momentum: float
    reversion: float
    breakout: float
    news: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "trend": self.trend, "momentum": self.momentum,
            "reversion": self.reversion, "breakout": self.breakout,
            "news": self.news,
        }

    @property
    def total(self) -> float:
        return sum(abs(v) for v in self.as_dict().values())


REGIME_WEIGHTS: Dict[str, WeightSet] = {
    "calm":     WeightSet(trend=0.30, momentum=0.25, reversion=0.05, breakout=0.25, news=0.15),
    "volatile": WeightSet(trend=0.20, momentum=0.15, reversion=0.30, breakout=0.10, news=0.25),
    "bear":     WeightSet(trend=0.40, momentum=0.30, reversion=0.15, breakout=0.05, news=0.10),
}


@dataclass(frozen=True)
class Evidence:
    """One named input, its weight, and exactly what it added to the score."""

    name: str
    raw: float
    weight: float
    contribution: float
    note: str = ""

    @property
    def direction(self) -> str:
        if self.contribution > 1e-9:
            return "bullish"
        if self.contribution < -1e-9:
            return "bearish"
        return "neutral"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "raw": round(self.raw, 4),
            "weight": round(self.weight, 4),
            "contribution": round(self.contribution, 4),
            "direction": self.direction,
            "note": self.note,
        }


@dataclass(frozen=True)
class Proposal:
    """What the agent thinks, and why. Not an order, and not a position size."""

    symbol: str
    as_of: datetime
    regime: str
    regime_stability: int
    raw_score: float          # sum of evidence contributions, exactly
    conviction: float         # volatility damper in (0, 1]
    score: float              # raw_score * conviction
    action: str               # "long" | "short" | "flat"
    evidence: Tuple[Evidence, ...]
    intent: Optional[OrderIntent] = None
    news: Optional[NewsScore] = None
    skip_reason: str = ""

    @property
    def proposes_trade(self) -> bool:
        return self.intent is not None

    def rationale(self) -> str:
        """One plain sentence, built from the three largest contributions."""
        if not self.proposes_trade:
            return f"No proposal: {self.skip_reason or 'score inside the flat band'}."
        top = sorted(self.evidence, key=lambda e: -abs(e.contribution))[:3]
        parts = [f"{e.name} {e.contribution:+.3f}" for e in top if abs(e.contribution) > 1e-9]
        return (
            f"{self.action.upper()} {self.symbol} at {self.intent.entry:.2f} in a "
            f"{self.regime} regime; score {self.score:+.3f} driven by "
            f"{', '.join(parts)}."
        )

    def to_dict(self) -> dict:
        d = {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "regime": self.regime,
            "regime_stability": self.regime_stability,
            "raw_score": round(self.raw_score, 4),
            "conviction": round(self.conviction, 4),
            "score": round(self.score, 4),
            "action": self.action,
            "evidence": [e.to_dict() for e in self.evidence],
            "rationale": self.rationale(),
            "weights_version": WEIGHTS_VERSION,
            "weights_hash": weights_hash(),
        }
        if self.intent is not None:
            d["intent"] = {
                "symbol": self.intent.symbol,
                "side": self.intent.side.value,
                "entry": round(self.intent.entry, 4),
                "stop": round(self.intent.stop, 4),
                "target_1": round(self.intent.target_1, 4),
                "target_2": round(self.intent.target_2, 4),
                "stop_distance": round(self.intent.stop_distance, 4),
                "risk_reward": round(self.intent.risk_reward, 3),
                "strategy": self.intent.strategy,
                "invalidation": self.intent.invalidation,
            }
        if self.news is not None:
            d["news"] = self.news.to_dict()
        if self.skip_reason:
            d["skip_reason"] = self.skip_reason
        return d


def weights_hash() -> str:
    """Fingerprint of this file, mirroring `trading.policy.policy_hash`."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def _conviction(vol_z: float) -> float:
    """Shrink conviction when realized vol is unusually high.

    Applied to the score, never to the size. Size is already vol-aware through
    the ATR-based stop distance, and applying a second vol adjustment there
    would double-count it.
    """
    if not np.isfinite(vol_z) or vol_z <= 0:
        return 1.0
    return float(1.0 - MAX_VOL_DAMP * min(1.0, vol_z))


def _targets(entry: float, stop: float, side: Side, cost_per_share: float) -> Tuple[float, float]:
    """Targets that clear the policy's post-cost reward minimum by construction.

    `trading.protection` computes reward in R *after* costs:
        rr = (|target_2 - entry| - cost) / (stop_distance + cost)
    so solving that for target_2 at TARGET_RR is the only way to guarantee the
    gate will not reject a proposal on geometry it could have been given.
    """
    distance = abs(entry - stop)
    reach = TARGET_RR * (distance + cost_per_share) + cost_per_share
    if side is Side.LONG:
        return entry + TARGET_1_R * distance, entry + reach
    return entry - TARGET_1_R * distance, entry - reach


def decide(
    symbol: str,
    row,
    regime: str,
    regime_stability: int,
    news: Optional[NewsScore] = None,
    costs: CostModel = CostModel.retail(),
    as_of: Optional[datetime] = None,
    strategy_name: str = "evidence_v1",
) -> Proposal:
    """Score one symbol on one bar.

    `row` is a row of `signals.features_for(...)` -- close, the five features
    and the ATR proxy. Nothing else is read, so the caller controls exactly
    which bar the decision sees.
    """
    as_of = as_of or datetime.now(timezone.utc)
    weights = REGIME_WEIGHTS.get(regime)

    if weights is None:
        return Proposal(
            symbol, as_of, regime, regime_stability, 0.0, 1.0, 0.0, "flat", (),
            skip_reason=f"no weight set for regime {regime!r}",
        )

    values = {
        "trend": float(row.get("trend", np.nan)),
        "momentum": float(row.get("momentum", np.nan)),
        "reversion": float(row.get("reversion", np.nan)),
        "breakout": float(row.get("breakout", np.nan)),
        "news": float(news.value) if news is not None else 0.0,
    }

    missing = [k for k, v in values.items() if not np.isfinite(v)]
    if missing:
        return Proposal(
            symbol, as_of, regime, regime_stability, 0.0, 1.0, 0.0, "flat", (),
            news=news,
            skip_reason=f"features not yet defined: {', '.join(sorted(missing))}",
        )

    notes = {
        "trend": "fast/slow EMA separation in ATR units",
        "momentum": "12-month return excluding the last month",
        "reversion": "negated 20-day z-score; oversold reads positive",
        "breakout": "distance from the prior 55-day high, in ATR units",
        "news": (
            f"{news.coverage} headline(s), source={news.source}"
            + (" — thin coverage, damped" if news and news.is_thin else "")
            if news is not None else "no news provider"
        ),
    }

    w = weights.as_dict()
    evidence = tuple(
        Evidence(name, values[name], w[name], w[name] * values[name], notes[name])
        for name in ("trend", "momentum", "reversion", "breakout", "news")
    )

    # The invariant: the explanation reconstructs the number.
    raw_score = sum(e.contribution for e in evidence)

    vz = float(row.get("vol_z", 0.0))
    conviction = _conviction(vz if np.isfinite(vz) else 0.0)
    score = raw_score * conviction

    close = float(row["close"])
    atr = float(row.get("atr_proxy", np.nan))

    if not np.isfinite(atr) or atr <= 0:
        return Proposal(
            symbol, as_of, regime, regime_stability, raw_score, conviction, score,
            "flat", evidence, news=news,
            skip_reason="ATR proxy undefined; cannot place a stop",
        )

    if score >= ENTRY_THRESHOLD:
        side = Side.LONG
    elif score <= -SHORT_THRESHOLD:
        side = Side.SHORT
    else:
        band = (
            f"score {score:+.3f} inside the flat band "
            f"(long ≥ {ENTRY_THRESHOLD:+.2f}, short ≤ {-SHORT_THRESHOLD:+.2f})"
        )
        return Proposal(
            symbol, as_of, regime, regime_stability, raw_score, conviction, score,
            "flat", evidence, news=news, skip_reason=band,
        )

    distance = STOP_ATR_MULTIPLE * atr
    cps = costs.round_trip_marginal(close)

    if cps > 0 and distance < MIN_STOP_TO_COST * cps:
        return Proposal(
            symbol, as_of, regime, regime_stability, raw_score, conviction, score,
            "flat", evidence, news=news,
            skip_reason=(
                f"stop distance {distance:.4f} is below {MIN_STOP_TO_COST:.0f}x the "
                f"round-trip cost {cps:.4f}; the trade is dominated by friction"
            ),
        )

    stop = close - distance if side is Side.LONG else close + distance
    t1, t2 = _targets(close, stop, side, cps)

    intent = OrderIntent(
        symbol=symbol,
        side=side,
        entry=close,
        stop=stop,
        target_1=t1,
        target_2=t2,
        strategy=strategy_name,
        regime=regime,
        invalidation=(
            f"close beyond {stop:.2f} ({STOP_ATR_MULTIPLE:.1f}x ATR proxy), "
            f"or regime leaving {regime}"
        ),
        signal_time=as_of,
    )

    return Proposal(
        symbol=symbol,
        as_of=as_of,
        regime=regime,
        regime_stability=regime_stability,
        raw_score=raw_score,
        conviction=conviction,
        score=score,
        action=side.value,
        evidence=evidence,
        intent=intent,
        news=news,
    )


def rank(proposals: List[Proposal], limit: int) -> List[Proposal]:
    """Strongest first, ties broken by symbol so the order is reproducible.

    Only used to choose which proposals reach the gate when more symbols
    qualify than there are position slots. It does not influence sizing.
    """
    tradable = [p for p in proposals if p.proposes_trade]
    tradable.sort(key=lambda p: (-abs(p.score), p.symbol))
    return tradable[:limit]
