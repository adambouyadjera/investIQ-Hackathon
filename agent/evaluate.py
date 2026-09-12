"""The harness: run the desk over history and report it against a benchmark.

Five rules, each one a direct answer to a way backtests mislead.

1. **A signal on bar t is executed on bar t+1.** The proposal is carried in a
   pending queue and repriced to the next bar's close. No decision ever acts on
   the price that produced it.
2. **Every entry passes the risk gate.** `trading.checks.evaluate` sizes the
   position and can veto it outright. Vetoes are counted and reported by code,
   because a strategy whose returns depend on trades the gate would have
   refused is not the strategy you would have run.
3. **Every fill pays.** Spread, slippage, commission and borrow, via `CostModel`.
   The report carries the total and a frictionless counterfactual so the reader
   can see how much of the edge the costs ate.
4. **Nothing is reported without a benchmark.** Buy-and-hold over the identical
   window, paying the identical entry cost. An absolute return figure on its
   own -- the video's "+3,130%" -- says nothing about whether the strategy beat
   owning the index.
5. **Out-of-sample is reported separately and is the number that counts.** The
   weights and thresholds in `decide.py` were written by a person who had seen
   this price history. That is a fit, however informal, and the only honest
   response is to split the sample and label which half is contaminated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timezone
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from engine import metrics as M
from trading import policy
from trading.checks import evaluate as gate_evaluate
from trading.types import Action, OrderIntent, Side

from . import decide, news as news_mod, signals, stats
from .costs import CostModel
from .journal import Journal, JournalEntry

TRADING_DAYS = 252
# A proposal is abandoned if the price moves this far, in either direction,
# between the signal close and the next bar's execution close. Entering after
# an unusual move means filling into a setup that is no longer the one that was
# scored, at a stop distance the move has already made stale.
#
# Calibrated against the data rather than guessed: the ATR proxy is the *mean*
# absolute daily move, so the median one-bar displacement is 0.81 ATR and a
# threshold of 1.0 would cancel 42% of proposals as "gaps". 2.0 ATR sits at the
# 87th percentile, which is the point at which a move is genuinely unusual.
MAX_CHASE_ATR = 2.0


@dataclass
class RunConfig:
    initial_cash: float = 100_000.0
    benchmark_symbol: str = "VTI"
    costs: CostModel = field(default_factory=CostModel.retail)
    max_new_per_bar: int = 2
    universe: Optional[Sequence[str]] = None
    start: Optional[pd.Timestamp] = None
    end: Optional[pd.Timestamp] = None
    use_news: bool = True
    strategy_name: str = "evidence_v1"
    # Strategies examined before settling on this one. Feeds the deflated
    # Sharpe. Honestly declaring 1 is fine; the point is that it is declared.
    n_trials: int = 1
    seed: int = 20260912

    def to_dict(self) -> dict:
        return {
            "initial_cash": self.initial_cash,
            "benchmark_symbol": self.benchmark_symbol,
            "max_new_per_bar": self.max_new_per_bar,
            "use_news": self.use_news,
            "strategy_name": self.strategy_name,
            "n_trials": self.n_trials,
            "costs": {
                "commission_per_share": self.costs.commission_per_share,
                "commission_min": self.costs.commission_min,
                "half_spread_bps": self.costs.half_spread_bps,
                "slippage_bps": self.costs.slippage_bps,
                "annual_borrow_rate": self.costs.annual_borrow_rate,
                "frictionless": self.costs.is_frictionless,
            },
        }


@dataclass
class RunResult:
    equity: pd.Series
    returns: pd.Series
    broker_stats: dict
    journal: Journal
    veto_counts: Dict[str, int]
    breaker_events: List[dict]
    config: RunConfig
    news_source: str
    start: pd.Timestamp
    end: pd.Timestamp

    def metrics(self) -> Optional[M.Metrics]:
        if len(self.returns) < 2:
            return None
        return M.compute(self.returns)


# ── Benchmark ────────────────────────────────────────────────────────────────

def buy_and_hold(
    prices: pd.Series, initial_cash: float, costs: CostModel
) -> pd.Series:
    """Whole shares bought on the first bar, paying the same spread and fee.

    Leftover cash sits idle, which is what actually happens -- pretending the
    benchmark compounds fractional shares gives it a small free advantage.
    """
    px = prices.dropna().astype(float)
    if px.empty:
        raise ValueError("benchmark series is empty over this window")

    first = float(px.iloc[0])
    fill = costs.fill_price(first, buying=True, quantity=1)
    shares = int(initial_cash // (fill + costs.commission_per_share))
    if shares <= 0:
        raise ValueError("initial cash buys less than one share of the benchmark")
    commission = costs.commission(first, shares)
    cash = initial_cash - shares * fill - commission
    return (px * shares + cash).rename("benchmark")


def compare(strategy: pd.Series, benchmark: pd.Series) -> dict:
    """Side-by-side, plus the relative statistics that matter more than either."""
    idx = strategy.index.intersection(benchmark.index)
    s_curve, b_curve = strategy.reindex(idx), benchmark.reindex(idx)
    s_ret = s_curve.pct_change().dropna()
    b_ret = b_curve.pct_change().dropna()
    common = s_ret.index.intersection(b_ret.index)
    s_ret, b_ret = s_ret.reindex(common), b_ret.reindex(common)

    if len(s_ret) < 3:
        return {"error": "not enough overlapping observations to compare"}

    s_m, b_m = M.compute(s_ret), M.compute(b_ret)
    alpha_d, beta = stats.ols_alpha_beta(s_ret.to_numpy(), b_ret.to_numpy())
    active = s_ret - b_ret
    te = float(active.std(ddof=1) * np.sqrt(TRADING_DAYS))

    up = b_ret > 0
    down = b_ret < 0
    up_capture = float(s_ret[up].mean() / b_ret[up].mean()) if up.any() and b_ret[up].mean() != 0 else None
    down_capture = float(s_ret[down].mean() / b_ret[down].mean()) if down.any() and b_ret[down].mean() != 0 else None

    return {
        "strategy": s_m.to_dict(),
        "benchmark": b_m.to_dict(),
        "strategy_total_return": round(float(s_curve.iloc[-1] / s_curve.iloc[0] - 1.0), 6),
        "benchmark_total_return": round(float(b_curve.iloc[-1] / b_curve.iloc[0] - 1.0), 6),
        "excess_cagr": round(s_m.cagr - b_m.cagr, 6),
        "alpha_annualized": round(alpha_d * TRADING_DAYS, 6),
        "beta": round(beta, 4),
        "tracking_error": round(te, 6),
        "information_ratio": round(float(active.mean() * TRADING_DAYS / te), 4) if te > 0 else None,
        "up_capture": round(up_capture, 4) if up_capture is not None else None,
        "down_capture": round(down_capture, 4) if down_capture is not None else None,
        "drawdown_advantage": round(s_m.max_drawdown - b_m.max_drawdown, 6),
        "beat_benchmark": bool(s_m.cagr > b_m.cagr),
    }


# ── The run loop ─────────────────────────────────────────────────────────────

def run(
    prices: pd.DataFrame,
    config: Optional[RunConfig] = None,
    news_provider: Optional[news_mod.NewsProvider] = None,
) -> RunResult:
    """Drive signals -> decision -> risk gate -> paper broker over the window."""
    from .paper import PaperBroker  # local import keeps the module graph flat

    cfg = config or RunConfig()
    universe = list(cfg.universe) if cfg.universe else list(prices.columns)
    if cfg.benchmark_symbol not in prices.columns:
        raise ValueError(f"benchmark {cfg.benchmark_symbol!r} is not in the price data")

    feats = signals.features(prices)
    regime = signals.classify_regime(prices[cfg.benchmark_symbol])

    provider = news_provider or (
        news_mod.default_provider(prices) if cfg.use_news else news_mod.NullNewsProvider()
    )

    dates = [d for d in signals.tradable_dates(prices)
             if (cfg.start is None or d >= cfg.start) and (cfg.end is None or d <= cfg.end)]
    if len(dates) < 30:
        raise ValueError("need at least 30 tradable bars after warmup")

    broker = PaperBroker(cfg.initial_cash, cfg.costs)
    journal = Journal()
    veto_counts: Dict[str, int] = {}
    breaker_events: List[dict] = []
    pending: List[decide.Proposal] = []
    halted = False

    for date in dates:
        row_prices = prices.loc[date]

        broker.mark(date, row_prices)
        broker.process_exits(date, row_prices)

        state = broker.account_state(date, row_prices)
        breakers = policy.evaluate_breakers(state, block_file=None)
        action = policy.strictest(breakers)

        # The cascade has to *act*, not merely refuse new entries. A flatten
        # rule that only blocks entries is not a flatten rule.
        if action in (Action.FLATTEN, Action.BLOCKED) and broker.positions:
            broker.flatten_all(date, row_prices, f"breaker_{action.value}")
            breaker_events.append({
                "date": date.strftime("%Y-%m-%d"),
                "action": action.value,
                "breakers": [b.name for b in breakers],
                "detail": "; ".join(b.detail for b in breakers),
                "equity": round(state.equity, 2),
            })
        if action is Action.BLOCKED:
            halted = True

        if halted:
            pending = []
            continue

        # ── Execute yesterday's proposals at today's close ────────────────
        opened = 0
        for proposal in pending:
            if opened >= cfg.max_new_per_bar:
                break
            sym = proposal.symbol
            if sym in broker.positions or sym not in prices.columns:
                continue

            exec_close = float(row_prices[sym])
            signal_close = proposal.intent.entry
            atr = abs(signal_close - proposal.intent.stop) / decide.STOP_ATR_MULTIPLE
            if atr <= 0:
                continue

            displacement = (exec_close - signal_close) / atr
            if abs(displacement) > MAX_CHASE_ATR:
                journal.record(JournalEntry(
                    date=date, symbol=sym, stage="execution",
                    outcome="cancelled", code="MOVED_TOO_FAR",
                    detail=(
                        f"price moved {displacement:+.2f} ATR between the signal "
                        f"close and execution; the scored setup no longer holds"
                    ),
                    proposal=proposal,
                ))
                _bump(veto_counts, "MOVED_TOO_FAR")
                continue

            intent = _reprice(proposal.intent, exec_close, cfg.costs)
            state = broker.account_state(date, row_prices)
            cps = cfg.costs.round_trip_marginal(exec_close)

            decision = gate_evaluate(
                intent, state,
                regime=proposal.regime,
                regime_stability=proposal.regime_stability,
                strategy_permitted=True,
                bar_closed=True,
                cost_per_share=cps,
                block_file=None,
            )

            if not decision.approved:
                _bump(veto_counts, decision.veto_code)
                journal.record(JournalEntry(
                    date=date, symbol=sym, stage="risk_gate",
                    outcome="vetoed", code=decision.veto_code,
                    detail=decision.veto_reason, proposal=proposal,
                    checks=[(c.name, c.passed, c.code) for c in decision.checks],
                ))
                continue

            fill = broker.open_position(date, intent, decision.quantity, exec_close)
            if fill is None:
                _bump(veto_counts, "INSUFFICIENT_CASH")
                journal.record(JournalEntry(
                    date=date, symbol=sym, stage="execution",
                    outcome="cancelled", code="INSUFFICIENT_CASH",
                    detail="cash could not cover the approved quantity",
                    proposal=proposal,
                ))
                continue

            opened += 1
            journal.record(JournalEntry(
                date=date, symbol=sym, stage="execution", outcome="filled",
                code="OK",
                detail=(
                    f"{decision.quantity} @ {fill.price:.2f} "
                    f"(close {exec_close:.2f}), planned loss "
                    f"${decision.planned_loss:,.2f}"
                ),
                proposal=proposal, quantity=decision.quantity,
                planned_loss=decision.planned_loss,
                checks=[(c.name, c.passed, c.code) for c in decision.checks],
            ))

        # ── Form tomorrow's proposals from today's close ──────────────────
        pending = []
        if policy.blocks_new_entries(action):
            continue

        label, stability = regime.at(date)
        if label == "unknown":
            continue

        bar_close = pd.Timestamp(date).to_pydatetime().replace(
            hour=21, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
        candidates: List[decide.Proposal] = []
        for sym in universe:
            if sym not in feats or sym in broker.positions:
                continue
            frame = feats[sym]
            if date not in frame.index:
                continue
            ns = news_mod.sentiment_at(provider, sym, bar_close) if cfg.use_news else None
            candidates.append(decide.decide(
                sym, frame.loc[date], label, stability, ns,
                costs=cfg.costs, as_of=bar_close, strategy_name=cfg.strategy_name,
            ))

        pending = decide.rank(candidates, cfg.max_new_per_bar)
        for p in pending:
            journal.record(JournalEntry(
                date=date, symbol=p.symbol, stage="proposal", outcome="proposed",
                code="OK", detail=p.rationale(), proposal=p,
            ))

    final_prices = prices.loc[dates[-1]]
    broker.flatten_all(dates[-1], final_prices, "end_of_test")

    return RunResult(
        equity=broker.equity_curve(),
        returns=broker.returns(),
        broker_stats=broker.stats(),
        journal=journal,
        veto_counts=veto_counts,
        breaker_events=breaker_events,
        config=cfg,
        news_source=provider.source,
        start=dates[0],
        end=dates[-1],
    )


def _bump(counter: Dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _reprice(intent: OrderIntent, new_entry: float, costs: CostModel) -> OrderIntent:
    """Shift the whole geometry to the execution bar, preserving stop distance.

    Targets are recomputed rather than shifted so the post-cost reward ratio is
    still satisfied at the new price -- costs scale with price, so a parallel
    shift would quietly erode the ratio the gate is about to check.
    """
    distance = intent.stop_distance
    stop = new_entry - distance if intent.side is Side.LONG else new_entry + distance
    cps = costs.round_trip_marginal(new_entry)
    t1, t2 = decide._targets(new_entry, stop, intent.side, cps)
    return OrderIntent(
        symbol=intent.symbol, side=intent.side, entry=new_entry, stop=stop,
        target_1=t1, target_2=t2, strategy=intent.strategy, regime=intent.regime,
        invalidation=intent.invalidation, signal_time=intent.signal_time,
    )


# ── Reporting ────────────────────────────────────────────────────────────────

def report(prices: pd.DataFrame, result: RunResult) -> dict:
    """Everything a reader needs to judge the run, including the bad news."""
    cfg = result.config
    bench_prices = prices[cfg.benchmark_symbol].loc[result.equity.index]
    bench = buy_and_hold(bench_prices, cfg.initial_cash, cfg.costs)

    comparison = compare(result.equity, bench)
    dsr = stats.deflated_sharpe(
        result.returns.to_numpy(),
        n_trials=cfg.n_trials,
        variance_of_trials=_trial_variance(cfg.n_trials, result.returns),
    )

    caveats = [
        "Simulated on historical prices. No broker is connected and no order "
        "was placed. Past results do not predict future results.",
        "Execution is modelled at the next daily close after the signal. "
        "Intraday fills, partial fills and queue position are not modelled.",
        "Stops are checked against daily closes, so an intrabar touch that "
        "reversed is invisible and a gap through the stop fills at the close.",
    ]
    if result.news_source == "synthetic":
        caveats.append(
            "News sentiment came from the synthetic provider, which is built "
            "from past returns and seeded noise and carries no real "
            "information. Any contribution it appears to make is noise."
        )
    if result.news_source == "none":
        caveats.append("No news provider was configured; the news evidence line was 0.0 throughout.")
    if cfg.costs.is_frictionless:
        caveats.append(
            "COSTS DISABLED. This run is a frictionless counterfactual and is "
            "not a forecast of anything achievable."
        )
    if cfg.n_trials <= 1:
        caveats.append(
            "n_trials=1 was declared, so the deflated Sharpe assumes this "
            "strategy was the only one considered. If variants were tried and "
            "discarded, raise n_trials and re-read the verdict."
        )

    m = result.metrics()
    return {
        "window": {
            "start": result.start.strftime("%Y-%m-%d"),
            "end": result.end.strftime("%Y-%m-%d"),
            "bars": len(result.equity),
            "years": round(len(result.equity) / TRADING_DAYS, 2),
        },
        "config": cfg.to_dict(),
        "news_source": result.news_source,
        "broker": result.broker_stats,
        "metrics": m.to_dict() if m else None,
        "benchmark": comparison,
        "significance": dsr,
        "risk": {
            "policy_hash": policy.policy_hash(),
            "weights_hash": decide.weights_hash(),
            "vetoes": dict(sorted(result.veto_counts.items(), key=lambda kv: -kv[1])),
            "veto_total": sum(result.veto_counts.values()),
            "breaker_events": result.breaker_events,
        },
        "equity_curve": [
            {"date": d.strftime("%Y-%m-%d"),
             "strategy": round(float(s), 2),
             "benchmark": round(float(b), 2)}
            for d, s, b in zip(result.equity.index, result.equity.values,
                               bench.reindex(result.equity.index).values)
        ],
        "caveats": caveats,
        "disclaimer": (
            "Educational simulation. Not financial advice. No real-money "
            "trading is supported by this software."
        ),
    }


def _trial_variance(n_trials: int, returns: pd.Series) -> float:
    """Dispersion of Sharpe across the trials that were run.

    With a single declared trial there is no dispersion to measure, so the
    deflation term is zero and the DSR reduces to the probabilistic Sharpe
    ratio. With several, the caller should pass the real dispersion; absent
    that, the sampling variance of a Sharpe estimate, 1/(T-1), is the
    conventional stand-in and is used here.
    """
    if n_trials <= 1:
        return 0.0
    n = max(2, len(returns))
    return 1.0 / (n - 1)


# ── Walk forward ─────────────────────────────────────────────────────────────

def walk_forward(
    prices: pd.DataFrame,
    split: str = "2022-01-01",
    config: Optional[RunConfig] = None,
    news_provider: Optional[news_mod.NewsProvider] = None,
) -> dict:
    """Run the same desk twice: before the split, and after it.

    Nothing is fitted between the two halves -- the weights are hand-written
    and identical in both. The split exists because the *author* saw the whole
    history before writing them, which is a fit that no amount of code
    discipline removes. The out-of-sample half is the one to read.
    """
    cutoff = pd.Timestamp(split)
    base = config or RunConfig()

    def _cfg(start, end):
        return RunConfig(
            initial_cash=base.initial_cash, benchmark_symbol=base.benchmark_symbol,
            costs=base.costs, max_new_per_bar=base.max_new_per_bar,
            universe=base.universe, start=start, end=end, use_news=base.use_news,
            strategy_name=base.strategy_name, n_trials=base.n_trials, seed=base.seed,
        )

    is_result = run(prices, _cfg(base.start, cutoff - pd.Timedelta(days=1)), news_provider)
    oos_result = run(prices, _cfg(cutoff, base.end), news_provider)

    return {
        "split": cutoff.strftime("%Y-%m-%d"),
        "in_sample": report(prices, is_result),
        "out_of_sample": report(prices, oos_result),
        "reading_guide": (
            "The in-sample window is contaminated: the rules were written by "
            "someone who had already seen it. Judge the strategy on the "
            "out-of-sample window, and treat a large gap between the two as "
            "evidence the rules were shaped to fit the past."
        ),
    }
