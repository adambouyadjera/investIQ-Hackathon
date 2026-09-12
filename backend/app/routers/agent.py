"""Paper-trading desk endpoints.

Thin wrappers over `agent/`, in keeping with the project's rule that the API
authenticates and routes but computes nothing financial. Every figure returned
here was produced by a deterministic, unit-tested module.

No endpoint in this file can place an order. There is no broker client in the
process, and `/agent/config` reports `live_trading_supported: false` so a
client can display the fact rather than take it on trust.

Backtests take a few seconds, so they run in a worker thread and are cached by
their request signature -- the event loop must not block while a five-year
simulation walks the tape.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..models.user import User
from ..routers.auth import get_current_user

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent import decide, evaluate, news as news_mod, signals   # noqa: E402
from agent.costs import CostModel                               # noqa: E402
from agent.paper import LIVE_TRADING_SUPPORTED                  # noqa: E402
from engine.data import load_prices                             # noqa: E402
from trading import policy                                      # noqa: E402

router = APIRouter(prefix="/agent", tags=["agent"])

# Backtests are pure functions of their inputs, so caching them is safe and
# turns a repeated 4-second call into an instant one. Bounded so a user cannot
# grow it without limit by sweeping parameters.
_CACHE: Dict[str, dict] = {}
_CACHE_LIMIT = 24

DISCLAIMER = (
    "Simulated on historical data. No broker is connected, no order is placed, "
    "and this software does not support real-money trading. Educational use "
    "only. Not financial advice."
)


def _prices() -> pd.DataFrame:
    prices, _ = load_prices()
    return prices


def _costs(body) -> CostModel:
    return CostModel(
        commission_per_share=body.commission_per_share,
        commission_min=body.commission_min,
        half_spread_bps=body.half_spread_bps,
        slippage_bps=body.slippage_bps,
        annual_borrow_rate=body.annual_borrow_rate,
    )


def _cache_key(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def _remember(key: str, value: dict) -> dict:
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = value
    return value


# ── Models ───────────────────────────────────────────────────────────────────

class CostInputs(BaseModel):
    commission_per_share: float = Field(0.005, ge=0, le=1)
    commission_min: float = Field(1.0, ge=0, le=50)
    half_spread_bps: float = Field(2.0, ge=0, le=100)
    slippage_bps: float = Field(3.0, ge=0, le=100)
    annual_borrow_rate: float = Field(0.03, ge=0, le=0.5)


class BacktestRequest(CostInputs):
    start: Optional[str] = None
    end: Optional[str] = None
    initial_cash: float = Field(100_000.0, gt=0, le=10_000_000)
    benchmark_symbol: str = "VTI"
    max_new_per_bar: int = Field(2, ge=1, le=5)
    use_news: bool = True
    # Declaring how many variants were examined is what makes the significance
    # figure meaningful. Defaulting to 1 is the honest default, not a flattering
    # one -- it produces the *weakest* claim of the available options.
    n_trials: int = Field(1, ge=1, le=1000)


class WalkForwardRequest(BacktestRequest):
    split: str = "2022-01-01"


class ScanRequest(CostInputs):
    date: Optional[str] = None
    symbols: Optional[List[str]] = None
    benchmark_symbol: str = "VTI"
    use_news: bool = True
    include_flat: bool = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config(current_user: User = Depends(get_current_user)):
    """The desk's constitution: weights, thresholds, costs and hashes."""
    return {
        "live_trading_supported": LIVE_TRADING_SUPPORTED,
        "weights_version": decide.WEIGHTS_VERSION,
        "weights_hash": decide.weights_hash(),
        "policy_hash": policy.policy_hash(),
        "entry_threshold": decide.ENTRY_THRESHOLD,
        "short_threshold": decide.SHORT_THRESHOLD,
        "stop_atr_multiple": decide.STOP_ATR_MULTIPLE,
        "target_risk_reward": decide.TARGET_RR,
        "max_chase_atr": evaluate.MAX_CHASE_ATR,
        "regime_weights": {
            regime: w.as_dict() for regime, w in decide.REGIME_WEIGHTS.items()
        },
        "features": [
            {"name": "trend", "description": "Fast/slow EMA separation in ATR units"},
            {"name": "momentum", "description": "12-month return excluding the last month"},
            {"name": "reversion", "description": "Negated 20-day z-score; oversold reads positive"},
            {"name": "breakout", "description": "Distance from the prior 55-day high, in ATR units"},
            {"name": "news", "description": "Decay-weighted lexicon sentiment over a 10-day window"},
        ],
        "risk_limits": {
            "risk_per_trade": policy.RISK_PER_TRADE,
            "max_concentration": policy.MAX_CONCENTRATION,
            "max_open_risk": policy.MAX_OPEN_RISK,
            "max_positions": policy.MAX_POSITIONS,
            "min_risk_reward": policy.MIN_RISK_REWARD,
        },
        "default_costs": CostInputs().model_dump(),
        "disclaimer": DISCLAIMER,
    }


@router.post("/scan")
async def scan(body: ScanRequest, current_user: User = Depends(get_current_user)):
    """Score the universe on one bar and return the full evidence for each.

    This is the explainability view: every symbol's score, the five weighted
    contributions that sum to it, and the headlines behind the news line.
    """
    prices = _prices()
    dates = signals.tradable_dates(prices)

    if body.date:
        try:
            wanted = pd.Timestamp(body.date)
        except ValueError:
            raise HTTPException(422, "date must be ISO format, e.g. 2026-09-11")
        candidates = [d for d in dates if d <= wanted]
        if not candidates:
            raise HTTPException(422, f"no tradable bar on or before {body.date}")
        date = candidates[-1]
    else:
        date = dates[-1]

    feats = signals.features(prices)
    if body.benchmark_symbol not in prices.columns:
        raise HTTPException(422, f"unknown benchmark {body.benchmark_symbol!r}")
    regime = signals.classify_regime(prices[body.benchmark_symbol])
    label, stability = regime.at(date)

    provider = (news_mod.default_provider(prices) if body.use_news
                else news_mod.NullNewsProvider())
    costs = _costs(body)
    bar_close = pd.Timestamp(date).to_pydatetime().replace(
        hour=21, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )

    universe = body.symbols or list(prices.columns)
    proposals = []
    for sym in universe:
        if sym not in feats or date not in feats[sym].index:
            continue
        ns = news_mod.sentiment_at(provider, sym, bar_close) if body.use_news else None
        p = decide.decide(sym, feats[sym].loc[date], label, stability, ns,
                          costs=costs, as_of=bar_close)
        if p.proposes_trade or body.include_flat:
            proposals.append(p)

    proposals.sort(key=lambda p: -abs(p.score))

    return {
        "date": date.strftime("%Y-%m-%d"),
        "regime": label,
        "regime_stability": stability,
        "regime_weights": decide.REGIME_WEIGHTS[label].as_dict()
        if label in decide.REGIME_WEIGHTS else None,
        "news_source": provider.source,
        "news_is_synthetic": provider.source == "synthetic",
        "proposals": [p.to_dict() for p in proposals],
        "actionable": sum(1 for p in proposals if p.proposes_trade),
        "weights_hash": decide.weights_hash(),
        "policy_hash": policy.policy_hash(),
        "live_trading_supported": LIVE_TRADING_SUPPORTED,
        "disclaimer": DISCLAIMER,
    }


def _build_config(body: BacktestRequest) -> evaluate.RunConfig:
    return evaluate.RunConfig(
        initial_cash=body.initial_cash,
        benchmark_symbol=body.benchmark_symbol,
        costs=_costs(body),
        max_new_per_bar=body.max_new_per_bar,
        start=pd.Timestamp(body.start) if body.start else None,
        end=pd.Timestamp(body.end) if body.end else None,
        use_news=body.use_news,
        n_trials=body.n_trials,
    )


@router.post("/backtest")
async def backtest(body: BacktestRequest, current_user: User = Depends(get_current_user)):
    """Run the desk over a window and report it against buy-and-hold."""
    key = _cache_key({"kind": "backtest", **body.model_dump()})
    if key in _CACHE:
        return _CACHE[key]

    def _work() -> dict:
        prices = _prices()
        if body.benchmark_symbol not in prices.columns:
            raise ValueError(f"unknown benchmark {body.benchmark_symbol!r}")
        result = evaluate.run(prices, _build_config(body))
        report = evaluate.report(prices, result)
        report["journal_summary"] = result.journal.summary()
        report["recent_decisions"] = result.journal.recent(40)
        return report

    try:
        report = await asyncio.get_event_loop().run_in_executor(None, _work)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    return _remember(key, report)


@router.post("/walk-forward")
async def walk_forward(body: WalkForwardRequest, current_user: User = Depends(get_current_user)):
    """Same rules, run before and after a split date. Read the second one."""
    key = _cache_key({"kind": "wf", **body.model_dump()})
    if key in _CACHE:
        return _CACHE[key]

    def _work() -> dict:
        prices = _prices()
        return evaluate.walk_forward(prices, split=body.split, config=_build_config(body))

    try:
        out = await asyncio.get_event_loop().run_in_executor(None, _work)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    out["disclaimer"] = DISCLAIMER
    return _remember(key, out)


@router.get("/regime")
async def regime_history(
    days: int = Query(180, ge=30, le=2000),
    symbol: str = Query("VTI"),
    current_user: User = Depends(get_current_user),
):
    """Recent regime labels, for the strip above the desk."""
    prices = _prices()
    if symbol not in prices.columns:
        raise HTTPException(422, f"unknown symbol {symbol!r}")
    regime = signals.classify_regime(prices[symbol])
    tail = regime.label.iloc[-days:]
    stability = regime.stability.iloc[-days:]
    counts: Dict[str, int] = {}
    for v in tail:
        counts[str(v)] = counts.get(str(v), 0) + 1
    return {
        "symbol": symbol,
        "series": [
            {"date": d.strftime("%Y-%m-%d"), "regime": str(v), "stability": int(s)}
            for d, v, s in zip(tail.index, tail.values, stability.values)
        ],
        "current": str(tail.iloc[-1]),
        "current_stability": int(stability.iloc[-1]),
        "counts": counts,
        "min_stability_to_trade": 3,
    }
