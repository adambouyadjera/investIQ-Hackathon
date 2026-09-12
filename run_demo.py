#!/usr/bin/env python3
"""CLI for the engine. No web server, no database, no frontend.

    python run_demo.py --amount 25000 --horizon 20 --risk aggressive --monthly 500
    python run_demo.py --compare --amount 25000 --horizon 20
    python run_demo.py --income 5200 --essentials 2900
"""

from __future__ import annotations

import argparse

from engine import allocate, portfolios
from engine.data import load_prices


def money(x: float) -> str:
    return f"${x:,.0f}"


def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def print_result(r: dict) -> None:
    i = r["inputs"]
    print(f"\n{'=' * 74}")
    print(f"  {i['risk_label']}  |  {money(i['amount'])} lump sum  "
          f"+ {money(i['monthly_contribution'])}/mo  |  {i['horizon_years']:g}-year horizon")
    print(f"  data: {r['data_source']}  ({r['history_start']} to {r['history_end']})")
    print("=" * 74)

    print(f"\n  ALLOCATION   equity {pct(r['equity_share'])}   "
          f"blended expense ratio {pct(r['blended_expense_ratio'])}")
    print(f"  {'ticker':<7}{'name':<24}{'weight':>9}{'dollars':>13}{'shares':>11}")
    print("  " + "-" * 62)
    for a in r["allocation"]:
        print(f"  {a['ticker']:<7}{a['name'][:23]:<24}{pct(a['weight']):>9}"
              f"{money(a['dollars']):>13}{a['shares']:>11.2f}")

    b, m = r["backtest"], r["backtest"]["metrics"]
    print(f"\n  BACKTEST over available history")
    print(f"    contributed {money(b['total_contributed'])}   "
          f"ended {money(b['final_balance'])}   "
          f"profit {money(b['profit'])} ({pct(b['profit_pct'])})")
    print(f"    fees paid {money(b['fees_paid'])}")
    print(f"    CAGR {pct(m['cagr'])}   vol {pct(m['volatility'])}   "
          f"Sharpe {m['sharpe']:.2f}   Sortino {m['sortino']:.2f}")
    print(f"    max drawdown {pct(m['max_drawdown'])}   Calmar {m['calmar']:.2f}   "
          f"positive months {pct(m['positive_months'])}")
    print(f"    best year {pct(m['best_year'])}   worst year {pct(m['worst_year'])}")

    p = r["projection"]
    print(f"\n  PROJECTION  {i['horizon_years']:g} years, 2,000 bootstrapped paths")
    print(f"    contributed by then   {money(p['series'][-1]['contributed'])}")
    print(f"    bad case   (10th pct)  {money(p['final_p10'])}")
    print(f"    median     (50th pct)  {money(p['final_p50'])}")
    print(f"    good case  (90th pct)  {money(p['final_p90'])}")
    print(f"    P(ends above total contributed) = {pct(p['prob_beat_contributions'])}")
    if "prob_hit_goal" in p:
        print(f"    P(hits goal of {money(i['goal'])}) = {pct(p['prob_hit_goal'])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amount", type=float, default=10_000)
    ap.add_argument("--horizon", type=float, default=20)
    ap.add_argument("--risk", default="balanced",
                    choices=["conservative", "balanced", "aggressive"])
    ap.add_argument("--monthly", type=float, default=0)
    ap.add_argument("--rebalance", default="annual",
                    choices=["never", "quarterly", "annual"])
    ap.add_argument("--fee", type=float, default=0.0, help="extra annual fee, e.g. 0.01")
    ap.add_argument("--goal", type=float, default=None)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--income", type=float, default=None)
    ap.add_argument("--essentials", type=float, default=None)
    args = ap.parse_args()

    if args.income:
        s = allocate.savings_capacity(args.income, args.essentials)
        print(f"\n  SAVINGS CAPACITY")
        print(f"    take-home {money(s['monthly_take_home'])}/mo   "
              f"essentials {money(s['monthly_essentials'])}/mo   "
              f"surplus {money(s['monthly_surplus'])}/mo")
        print(f"    recommended: {money(s['recommended_monthly_investment'])}/mo "
              f"({money(s['recommended_annual_investment'])}/yr, "
              f"{pct(s['effective_savings_rate'])} of take-home)")
        print(f"    emergency fund target {money(s['emergency_fund_target'])}")
        for w in s["warnings"]:
            print(f"    ! {w}")
        if not args.compare:
            return

    prices, source = load_prices()
    kw = dict(monthly_contribution=args.monthly, rebalance=args.rebalance,
              extra_fee=args.fee, goal=args.goal)

    if args.compare:
        for tier in ("conservative", "balanced", "aggressive"):
            print_result(allocate.build(args.amount, args.horizon, tier,
                                        prices=prices, source=source, **kw))
    else:
        print_result(allocate.build(args.amount, args.horizon, args.risk,
                                    prices=prices, source=source, **kw))
    print()


if __name__ == "__main__":
    main()
