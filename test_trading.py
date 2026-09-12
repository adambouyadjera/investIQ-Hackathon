#!/usr/bin/env python3
"""Tests for the risk layer. Run: python test_trading.py

The boundary tests matter more than the rest. A cascade that fires at -2.9%
instead of -3.0% is a bug you find with real money, so the exact comparisons
are pinned here.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

from trading import checks, policy, protection, sizing
from trading.types import AccountState, Action, OrderIntent, Side, utcnow

passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  PASS  {name}")
    except Exception as e:
        failed += 1
        print(f"  FAIL  {name}: {e}")


def account(equity=2000.0, **kw):
    """Mia's worked example from the guide: a $2,000 paper account."""
    base = dict(
        equity=equity, peak_equity=equity, buying_power=equity * 2,
        day_start_equity=equity, week_start_equity=equity,
        month_start_equity=equity, open_positions={}, open_risk=0.0,
        as_of=utcnow(),
    )
    base.update(kw)
    return AccountState(**base)


def intent(**kw):
    base = dict(
        symbol="DEMO", side=Side.LONG, entry=50.0, stop=49.0,
        target_1=52.0, target_2=53.0, strategy="ema_cross",
        regime="calm", invalidation="below signal swing low",
    )
    base.update(kw)
    return OrderIntent(**base)


def nowhere() -> Path:
    """A block-file path guaranteed not to exist."""
    return Path(tempfile.gettempdir()) / "no_such_block_file_xyz"


# ── Sizing ───────────────────────────────────────────────────────────────────

def t_mia_worked_example():
    """$2,000 equity, $50 entry, $49 stop -> $20 budget, 20 shares."""
    r = sizing.calculate(intent(), account())
    assert r.quantity == 20, r.quantity
    assert abs(r.planned_loss - 20.0) < 1e-9, r.planned_loss


def t_half_size_breaker():
    r = sizing.calculate(intent(), account(), multiplier=0.5)
    assert r.quantity == 10, r.quantity


def t_zero_stop_distance_vetoes():
    r = sizing.calculate(intent(stop=50.0), account())
    assert r.veto_code == "VETO_INVALID_STOP_DISTANCE", r.veto_code
    assert r.quantity == 0


def t_quantity_always_rounds_down():
    """$20 budget / $0.30 stop distance = 66.67 -> 66, never 67.

    Checks raw_quantity: the final figure here is cut to 20 by the 50%
    concentration cap, which would hide the rounding behavior entirely.
    """
    r = sizing.calculate(intent(entry=50.0, stop=49.70, target_1=50.7, target_2=51.0),
                         account())
    assert r.raw_quantity == 66, r.raw_quantity
    assert r.quantity <= r.raw_quantity
    assert r.planned_loss <= 20.0 + 1e-9


def t_rounding_down_without_caps():
    """Same arithmetic on an account large enough that no cap binds."""
    a = account(equity=200_000.0)          # budget $2,000
    r = sizing.calculate(intent(entry=3.0, stop=2.70, target_1=3.6, target_2=3.9), a)
    assert r.raw_quantity == 6666, r.raw_quantity   # 2000 / 0.30 = 6666.67
    assert r.quantity == 6666, (r.quantity, r.caps_applied)
    assert r.planned_loss <= 2000.0 + 1e-9


def t_never_exceeds_one_percent():
    for equity in (500, 2_000, 17_450, 100_000):
        for dist in (0.25, 1.0, 3.75):
            a = account(equity)
            r = sizing.calculate(
                intent(entry=50.0, stop=50.0 - dist,
                       target_1=50 + 2 * dist, target_2=50 + 3 * dist), a)
            if r.ok:
                assert r.planned_loss <= equity * 0.01 + 1e-9, (equity, dist, r.planned_loss)


def t_concentration_cap():
    """50% ceiling: $1,000 of a $2,000 account at $50 = 20 shares max."""
    a = account(open_positions={"DEMO": 900.0})
    r = sizing.calculate(intent(), a)
    assert "concentration" in r.caps_applied, r.caps_applied
    assert r.quantity == 2, r.quantity  # ($1000 - $900) / $50


def t_open_risk_cap():
    a = account(open_risk=2000.0 * 0.06)  # budget fully consumed
    r = sizing.calculate(intent(), a)
    assert r.veto_code == "VETO_NO_ROOM", r.veto_code


def t_costs_reduce_size():
    free = sizing.calculate(intent(), account())
    costly = sizing.calculate(intent(), account(), cost_per_share=0.10)
    assert costly.quantity < free.quantity
    assert costly.planned_loss <= 20.0 + 1e-9


# ── Breaker boundaries ───────────────────────────────────────────────────────

def t_daily_exact_minus_3_does_not_flatten():
    """The rule is 'more than 3%'. Exactly -3.00% must not flatten."""
    a = account(equity=1940.0, day_start_equity=2000.0)   # exactly -3.00%
    action = policy.strictest(policy.evaluate_breakers(a, nowhere()))
    assert action is Action.HALF_SIZE, action


def t_daily_below_minus_3_flattens():
    a = account(equity=1939.0, day_start_equity=2000.0)   # -3.05%
    action = policy.strictest(policy.evaluate_breakers(a, nowhere()))
    assert action is Action.FLATTEN, action


def t_daily_exact_minus_2_halves():
    a = account(equity=1960.0, day_start_equity=2000.0)   # exactly -2.00%
    action = policy.strictest(policy.evaluate_breakers(a, nowhere()))
    assert action is Action.HALF_SIZE, action


def t_daily_just_above_minus_2_is_normal():
    a = account(equity=1961.0, day_start_equity=2000.0)   # -1.95%
    action = policy.strictest(policy.evaluate_breakers(a, nowhere()))
    assert action is Action.NORMAL, action


def t_weekly_boundaries():
    half = account(equity=1900.0, week_start_equity=2000.0)   # -5.00%
    assert policy.strictest(policy.evaluate_breakers(half, nowhere())) is Action.HALF_SIZE
    stop = account(equity=1880.0, week_start_equity=2000.0)   # -6.00%
    assert policy.strictest(policy.evaluate_breakers(stop, nowhere())) is Action.NO_NEW_ENTRIES


def t_monthly_boundary():
    a = account(equity=1800.0, month_start_equity=2000.0, peak_equity=2000.0)
    names = [b.name for b in policy.evaluate_breakers(a, nowhere())]
    assert "monthly_stop" in names, names


def t_peak_drawdown_blocks():
    a = account(equity=1800.0, peak_equity=2000.0)            # -10.00%
    action = policy.strictest(policy.evaluate_breakers(a, nowhere()))
    assert action is Action.BLOCKED, action


def t_strictest_wins():
    """Daily flatten and weekly half-size active together -> flatten."""
    a = account(equity=1900.0, day_start_equity=1980.0, week_start_equity=2000.0)
    breakers = policy.evaluate_breakers(a, nowhere())
    assert len(breakers) >= 2, [b.name for b in breakers]
    assert policy.strictest(breakers) is Action.FLATTEN


# ── Protection ───────────────────────────────────────────────────────────────

def t_stop_may_not_widen():
    r = protection.can_replace_stop(Side.LONG, 50.0, 49.0, 48.0)
    assert not r.valid and r.code == "VETO_STOP_WIDENING", r


def t_stop_may_tighten():
    assert protection.can_replace_stop(Side.LONG, 50.0, 49.0, 49.5).valid
    assert protection.can_replace_stop(Side.SHORT, 50.0, 51.0, 50.5).valid


def t_short_widening_refused():
    r = protection.can_replace_stop(Side.SHORT, 50.0, 51.0, 52.0)
    assert not r.valid and r.code == "VETO_STOP_WIDENING"


def t_reward_below_2r_refused():
    r = protection.validate(intent(target_1=50.5, target_2=51.0))  # 1R
    assert not r.valid and r.code == "VETO_INSUFFICIENT_REWARD", r


def t_stop_on_wrong_side_refused():
    r = protection.validate(intent(stop=51.0))
    assert not r.valid and r.code == "VETO_STOP_WRONG_SIDE", r


def t_unordered_targets_refused():
    r = protection.validate(intent(target_1=53.0, target_2=52.0))
    assert not r.valid and r.code == "VETO_TARGETS_UNORDERED", r


def t_partial_exit_split():
    assert protection.partial_exit_plan(20) == (10, 10)
    assert protection.partial_exit_plan(21) == (10, 11)
    assert protection.partial_exit_plan(1) == (0, 1)


def t_break_even_is_entry():
    assert protection.break_even_stop(50.0) == 50.0


# ── The gate ─────────────────────────────────────────────────────────────────

def gate(i=None, a=None, **kw):
    base = dict(regime="calm", regime_stability=3, strategy_permitted=True,
                bar_closed=True, block_file=nowhere())
    base.update(kw)
    return checks.evaluate(i or intent(), a or account(), **base)


def t_clean_proposal_clears():
    d = gate()
    assert d.approved, d.summary()
    assert d.quantity == 20, d.quantity
    assert abs(d.planned_loss - 20.0) < 1e-9


def t_unfinished_bar_vetoed():
    d = gate(bar_closed=False)
    assert not d.approved and d.veto_code == "VETO_UNFINISHED_BAR", d.veto_code


def t_unstable_regime_vetoed():
    d = gate(regime_stability=1)
    assert not d.approved and d.veto_code == "VETO_REGIME_UNSTABLE", d.veto_code


def t_unvalidated_strategy_vetoed():
    d = gate(strategy_permitted=False)
    assert d.veto_code == "VETO_STRATEGY_NOT_PERMITTED", d.veto_code


def t_stale_state_fails_closed():
    old = account(as_of=utcnow() - timedelta(hours=2))
    d = gate(a=old)
    assert d.veto_code == "VETO_STALE_STATE", d.veto_code


def t_ten_times_size_is_reduced_not_honored():
    """The hard separation test: a strategy asking for a huge position.

    Size is never the strategy's to name, so a tiny stop distance produces a
    large raw quantity that the caps must cut down.
    """
    greedy = intent(entry=50.0, stop=49.99, target_1=50.03, target_2=50.05)
    d = gate(i=greedy)
    if d.approved:
        assert d.planned_loss <= 2000.0 * 0.01 + 1e-9, d.planned_loss
        assert d.quantity * 50.0 <= 2000.0 * 0.50 + 1e-9, d.quantity
    else:
        assert d.veto_code.startswith("VETO_"), d.veto_code


def t_block_file_stops_everything():
    with tempfile.TemporaryDirectory() as tmp:
        bf = Path(tmp) / "TRADING_BLOCKED"
        bf.write_text("blocked")
        d = gate(block_file=bf)
        assert not d.approved and d.veto_code == "VETO_TRADING_BLOCKED", d.veto_code


def t_drawdown_writes_block_file():
    with tempfile.TemporaryDirectory() as tmp:
        bf = Path(tmp) / "state" / "TRADING_BLOCKED"
        a = account(equity=1800.0, peak_equity=2000.0)
        d = gate(a=a, block_file=bf)
        assert d.veto_code == "VETO_MAX_DRAWDOWN", d.veto_code
        assert bf.exists(), "block file must persist to disk"
        assert "peak_drawdown" in bf.read_text()


def t_flatten_day_blocks_entry():
    a = account(equity=1930.0, day_start_equity=2000.0)  # -3.5%
    d = gate(a=a)
    assert d.veto_code == "VETO_FLATTEN_DAY", d.veto_code


def t_half_size_day_still_trades_at_half():
    a = account(equity=1960.0, day_start_equity=2000.0)  # exactly -2%
    d = gate(a=a)
    assert d.approved, d.summary()
    assert d.quantity == 9, d.quantity  # 1% of $1,960 = $19.60 -> 19 -> half -> 9


def t_position_count_cap():
    a = account(open_positions={f"SYM{i}": 10.0 for i in range(policy.MAX_POSITIONS)})
    d = gate(a=a)
    assert d.veto_code == "VETO_TOO_MANY_POSITIONS", d.veto_code


def t_every_check_recorded():
    d = gate()
    names = [c.name for c in d.checks]
    for expected in ("block_state", "fresh_state", "closed_bar", "regime_stable",
                     "strategy_permitted", "protection", "breakers", "sizing",
                     "final_ceiling"):
        assert expected in names, (expected, names)


def t_veto_keeps_prior_results():
    """A veto mid-gate must not discard the checks that already ran."""
    d = gate(strategy_permitted=False)
    assert len(d.checks) >= 4, [c.name for c in d.checks]
    assert d.checks[-1].passed is False


# ── Isolation ────────────────────────────────────────────────────────────────

def t_stateless_eval_never_writes_a_block():
    """block_file=None must not create a block file anywhere.

    Regression: a stateless what-if endpoint passed a sentinel path, the
    drawdown rule wrote to it for real, and every later request was refused
    with VETO_TRADING_BLOCKED until the file was deleted by hand.
    """
    a = account(equity=1800.0, peak_equity=2000.0)
    d = checks.evaluate(intent(), a, regime="calm", regime_stability=3,
                        strategy_permitted=True, bar_closed=True, block_file=None)
    assert d.veto_code == "VETO_MAX_DRAWDOWN", d.veto_code
    assert policy.write_block(a, "peak_drawdown", None) is None
    assert not Path("state/TRADING_BLOCKED").exists()


def t_stateless_eval_ignores_existing_block():
    with tempfile.TemporaryDirectory() as tmp:
        bf = Path(tmp) / "TRADING_BLOCKED"
        bf.write_text("blocked")
        d = gate(block_file=None)
        assert d.approved, d.summary()


def t_no_broker_imports_anywhere():
    """The structural guarantee: this package cannot reach a broker."""
    banned = ("alpaca", "ccxt", "ib_insync", "requests", "urllib", "httpx", "socket")
    for path in Path("trading").glob("*.py"):
        src = path.read_text()
        for name in banned:
            assert f"import {name}" not in src, f"{path.name} imports {name}"
            assert f"from {name}" not in src, f"{path.name} imports from {name}"


def t_policy_hash_is_stable():
    assert policy.policy_hash() == policy.policy_hash()
    assert len(policy.policy_hash()) == 16


if __name__ == "__main__":
    print(f"\nrisk policy hash: {policy.policy_hash()}")
    print(f"1% ceiling | daily -2%/-3% | weekly -5%/-6% | monthly -10% | peak -10%\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("t_"):
            check(name[2:], fn)
    print(f"\n{passed} passed, {failed} failed\n")
    raise SystemExit(1 if failed else 0)
