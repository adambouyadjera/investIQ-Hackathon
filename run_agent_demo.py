#!/usr/bin/env python3
"""Walk the paper desk end to end and print what it did. No server needed.

    python run_agent_demo.py              # scan + backtest + walk forward
    python run_agent_demo.py --scan       # just today's proposals
    python run_agent_demo.py --years 3

Everything printed here is a simulation on historical prices. No broker is
connected, no order is placed, and this software has no live mode.
"""

from __future__ import annotations

import argparse
from datetime import timezone

import pandas as pd

from agent import decide, evaluate, news as news_mod, signals
from agent.costs import CostModel
from engine.data import load_prices
from trading import policy

BAR = "─" * 78


def h(title: str) -> None:
    print(f"\n{BAR}\n{title}\n{BAR}")


def show_scan(prices: pd.DataFrame, top: int = 6) -> None:
    h("1. TODAY'S SCAN — every symbol scored, with the reasoning")

    feats = signals.features(prices)
    regime = signals.classify_regime(prices["VTI"])
    date = signals.tradable_dates(prices)[-1]
    label, stability = regime.at(date)
    provider = news_mod.default_provider(prices)
    costs = CostModel.retail()
    bar_close = pd.Timestamp(date).to_pydatetime().replace(
        hour=21, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

    print(f"bar {date.date()}   regime {label} (held {stability} bars)   "
          f"news source: {provider.source}")
    if provider.source == "synthetic":
        print("NOTE: synthetic headlines — built from past returns and seeded noise,")
        print("      non-predictive by construction. Drop data/news.jsonl in for real ones.")

    proposals = []
    for sym in prices.columns:
        if sym not in feats or date not in feats[sym].index:
            continue
        ns = news_mod.sentiment_at(provider, sym, bar_close)
        proposals.append(decide.decide(sym, feats[sym].loc[date], label, stability,
                                       ns, costs=costs, as_of=bar_close))
    proposals.sort(key=lambda p: -abs(p.score))

    print(f"\n{'sym':<6}{'score':>8}  {'action':<7}reason")
    for p in proposals[:top]:
        reason = (p.skip_reason or "")[:46] if not p.proposes_trade else \
            f"entry {p.intent.entry:.2f} stop {p.intent.stop:.2f} {p.intent.risk_reward:.1f}R"
        print(f"{p.symbol:<6}{p.score:>+8.3f}  {p.action:<7}{reason}")

    winner = next((p for p in proposals if p.proposes_trade), proposals[0])
    print(f"\nfull decomposition for {winner.symbol}:")
    for e in winner.evidence:
        bar = "█" * int(abs(e.contribution) * 60)
        print(f"  {e.name:<10} raw {e.raw:+.3f} × w {e.weight:.2f} = "
              f"{e.contribution:+.4f}  {bar}")
    print(f"  {'':<10} {'sum of contributions':<28} {winner.raw_score:+.4f}")
    print(f"  {'':<10} {'× volatility conviction':<28} {winner.conviction:.4f}")
    print(f"  {'':<10} {'= score':<28} {winner.score:+.4f}")

    if winner.news is not None and winner.news.coverage:
        print(f"\n  news line, {winner.news.coverage} headline(s):")
        for s in winner.news.top_drivers(3):
            print(f"    {s.contribution:+.3f}  {s.headline.text[:56]}")
            print(f"            matched: {s.explain()}")


def show_report(rep: dict, title: str) -> None:
    b, s, br = rep["benchmark"], rep["significance"], rep["broker"]
    w = rep["window"]
    print(f"\n{title}   {w['start']} → {w['end']}  ({w['years']} years)")
    print(f"  strategy        {b['strategy_total_return']*100:+8.2f}%")
    print(f"  buy & hold      {b['benchmark_total_return']*100:+8.2f}%   <- the comparison that matters")
    print(f"  excess CAGR     {b['excess_cagr']*100:+8.2f}%   alpha {b['alpha_annualized']*100:+.2f}%  beta {b['beta']:.2f}")
    print(f"  max drawdown    {b['strategy']['max_drawdown']*100:8.2f}%   benchmark {b['benchmark']['max_drawdown']*100:.2f}%")
    pf = "—" if br["profit_factor"] is None else f"{br['profit_factor']:.3f}"
    print(f"  {br['closed_trades']} trades, {br['win_rate']*100:.0f}% win rate, "
          f"profit factor {pf}, costs ${br['total_costs']:,.0f}")
    print(f"  annualised Sharpe {s['sharpe_annualized']:.2f} vs a "
          f"{s.get('threshold_sharpe_annualized', 0):.2f} hurdle for {s['n_trials']} declared trial(s)")
    print(f"  VERDICT: {s['verdict']}")
    if rep["risk"]["vetoes"]:
        top = list(rep["risk"]["vetoes"].items())[:4]
        print(f"  risk engine refused {rep['risk']['veto_total']} proposals: "
              + ", ".join(f"{k}×{v}" for k, v in top))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true", help="only the scan")
    ap.add_argument("--years", type=float, default=None, help="limit the backtest window")
    ap.add_argument("--trials", type=int, default=6,
                    help="how many strategy variants you examined (raises the bar)")
    ap.add_argument("--split", default="2022-01-01", help="walk-forward split date")
    args = ap.parse_args()

    prices, source = load_prices()
    print(f"\nInvestIQ paper desk — price source: {source}, "
          f"{len(prices)} bars to {prices.index[-1].date()}")
    print(f"policy {policy.policy_hash()}  weights {decide.weights_hash()}")
    print("PAPER ONLY — no broker, no credentials, no live mode.")

    show_scan(prices)
    if args.scan:
        return

    start = None
    if args.years:
        start = prices.index[-1] - pd.Timedelta(days=int(args.years * 365.25))

    h("2. BACKTEST — against buy-and-hold, with costs and the risk gate live")
    cfg = evaluate.RunConfig(start=start, n_trials=args.trials)
    result = evaluate.run(prices, cfg)
    show_report(evaluate.report(prices, result), "full window")

    h("3. WALK FORWARD — the same rules before and after a split")
    wf = evaluate.walk_forward(prices, split=args.split,
                               config=evaluate.RunConfig(n_trials=args.trials))
    show_report(wf["in_sample"], "IN SAMPLE  (contaminated)")
    show_report(wf["out_of_sample"], "OUT OF SAMPLE  (the one that counts)")

    h("4. WHAT THE HARNESS WANTS YOU TO KNOW")
    for c in wf["out_of_sample"]["caveats"]:
        print(f"  • {c}")
    print(f"\n  {wf['reading_guide']}")
    print(f"\n  {wf['out_of_sample']['disclaimer']}\n")


if __name__ == "__main__":
    main()
