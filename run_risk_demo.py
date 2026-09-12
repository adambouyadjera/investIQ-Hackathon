#!/usr/bin/env python3
"""Walk proposals through the risk gate. Run: python run_risk_demo.py

Nothing here connects to a broker. It shows how a proposal is sized, and how
each breaker changes or refuses that decision.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from trading import policy
from trading.checks import evaluate
from trading.types import AccountState, OrderIntent, Side, utcnow

NO_BLOCK = Path(tempfile.gettempdir()) / "demo_no_block_file"


def account(equity=2000.0, **kw) -> AccountState:
    base = dict(
        equity=equity, peak_equity=2000.0, buying_power=equity * 2,
        day_start_equity=2000.0, week_start_equity=2000.0,
        month_start_equity=2000.0, open_positions={}, open_risk=0.0,
        as_of=utcnow(),
    )
    base.update(kw)
    return AccountState(**base)


PROPOSAL = OrderIntent(
    symbol="DEMO", side=Side.LONG, entry=50.0, stop=49.0,
    target_1=52.0, target_2=53.0, strategy="ema_cross",
    regime="calm", invalidation="below signal swing low",
)


def run(label: str, state: AccountState, intent=PROPOSAL, **kw):
    opts = dict(regime="calm", regime_stability=3, strategy_permitted=True,
                bar_closed=True, block_file=NO_BLOCK)
    opts.update(kw)
    d = evaluate(intent, state, **opts)

    print(f"\n{label}")
    print("-" * 68)
    print(f"  equity ${state.equity:,.2f}   day {state.daily_pct:+.2%}   "
          f"week {state.weekly_pct:+.2%}   peak {state.drawdown_pct:+.2%}")
    for c in d.checks:
        print(f"    {c}")
    print(f"  -> {d.summary()}")
    if d.approved:
        value = d.quantity * intent.entry
        print(f"     {d.quantity} shares, ${value:,.2f} position "
              f"({value / state.equity:.1%} of equity), "
              f"risking {d.planned_loss / state.equity:.2%}")
    return d


def main() -> None:
    print("=" * 68)
    print("  RISK GATE — paper only, no broker connection exists")
    print(f"  policy hash {policy.policy_hash()}")
    print("=" * 68)

    run("1. Clean proposal, flat account", account())
    run("2. Down 2% today — half size", account(1960.0))
    run("3. Down 3.5% today — flatten, no new entries", account(1930.0))
    run("4. Down 6% this week", account(1880.0, day_start_equity=1880.0))
    run("5. Signal from an unfinished bar", account(), bar_closed=False)
    run("6. Regime only 1 of 3 bars stable", account(), regime_stability=1)
    run("7. Strategy not validated for this regime", account(), strategy_permitted=False)
    run("8. Reward below 2R",
        account(),
        intent=OrderIntent(
            symbol="DEMO", side=Side.LONG, entry=50.0, stop=49.0,
            target_1=50.3, target_2=51.0, strategy="ema_cross",
            regime="calm", invalidation="swing low"),
        )

    with tempfile.TemporaryDirectory() as tmp:
        bf = Path(tmp) / "state" / "TRADING_BLOCKED"
        run("9. Down 10% from peak — writes the block file",
            account(1800.0, day_start_equity=1800.0, week_start_equity=1800.0,
                    month_start_equity=1800.0),
            block_file=bf)
        if bf.exists():
            print("\n  block file written:")
            for line in bf.read_text().splitlines()[:6]:
                print(f"    {line}")
            run("10. Same proposal, block file now present",
                account(), block_file=bf)

    print("\n" + "=" * 68)
    print("  Educational simulation. Not financial advice. You can lose money.")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
