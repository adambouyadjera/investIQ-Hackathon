#!/usr/bin/env python3
"""Tests for the analytics engine. Run: python test_engine.py

No pytest dependency — plain asserts so this runs anywhere.
"""

import os

import numpy as np
import pandas as pd

os.environ["PS_NO_NETWORK"] = "1"

from engine import allocate, backtest, metrics, montecarlo, portfolios
from engine.data import load_prices, portfolio_returns
from engine.universe import BY_TICKER, TICKERS

PRICES, SOURCE = load_prices()
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


# -- data -------------------------------------------------------------------
def t_prices_shape():
    assert list(PRICES.columns) == list(TICKERS)
    assert not PRICES.isna().any().any()
    assert (PRICES > 0).all().all()
    assert PRICES.index.is_monotonic_increasing


def t_returns_finite():
    r = portfolio_returns(PRICES, portfolios.TARGETS["balanced"])
    assert np.isfinite(r).all()
    assert r.abs().max() < 0.5, "implausible single-day move"


# -- portfolios -------------------------------------------------------------
def t_targets_sum_to_one():
    for tier, w in portfolios.TARGETS.items():
        assert abs(sum(w.values()) - 1.0) < 1e-9, tier
        assert all(t in BY_TICKER for t in w), tier
    assert abs(sum(portfolios.PRESERVATION.values()) - 1.0) < 1e-9


def t_blended_sum_to_one():
    for tier in portfolios.TARGETS:
        for h in (0.5, 2, 5, 10, 15, 40):
            w = portfolios.target_weights(tier, h)
            assert abs(sum(w.values()) - 1.0) < 1e-9, (tier, h)
            assert all(v > 0 for v in w.values())


def t_glide_path_monotonic():
    """Longer horizon must never mean less equity."""
    for tier in portfolios.TARGETS:
        eq = [portfolios.equity_share(portfolios.target_weights(tier, h))
              for h in (1, 3, 5, 10, 15, 30)]
        assert all(b >= a - 1e-9 for a, b in zip(eq, eq[1:])), (tier, eq)


def t_risk_ordering():
    """Aggressive must hold more equity and be more volatile than conservative."""
    eq = {t: portfolios.equity_share(portfolios.target_weights(t, 20))
          for t in portfolios.TARGETS}
    assert eq["conservative"] < eq["balanced"] < eq["aggressive"], eq
    vol = {t: metrics.compute(portfolio_returns(PRICES, portfolios.target_weights(t, 20))).volatility
           for t in portfolios.TARGETS}
    assert vol["conservative"] < vol["balanced"] < vol["aggressive"], vol


# -- metrics ----------------------------------------------------------------
def t_cagr_known_series():
    """Exactly 10% per year for 3 years must give CAGR 10%."""
    n = metrics.TRADING_DAYS * 3
    daily = 1.10 ** (1 / metrics.TRADING_DAYS) - 1
    r = pd.Series([daily] * n, index=pd.bdate_range("2020-01-01", periods=n))
    m = metrics.compute(r)
    assert abs(m.cagr - 0.10) < 1e-4, m.cagr
    assert abs(m.max_drawdown) < 1e-9
    assert m.volatility < 1e-9


def t_drawdown_bounds():
    m = metrics.compute(portfolio_returns(PRICES, portfolios.TARGETS["aggressive"]))
    assert -1.0 < m.max_drawdown < 0.0
    assert 0.0 <= m.positive_months <= 1.0


# -- backtest ---------------------------------------------------------------
def t_contributions_counted():
    w = portfolios.target_weights("balanced", 20)
    r = backtest.run(PRICES, w, initial=10_000, monthly_contribution=500)
    months = len(PRICES.index.to_period("M").unique()) - 1
    assert abs(r.total_contributed - (10_000 + 500 * months)) <= 500
    assert abs(r.profit - (r.final_balance - r.total_contributed)) < 1e-6


def t_contributions_not_counted_as_return():
    """Adding cash must not inflate CAGR."""
    w = portfolios.target_weights("balanced", 20)
    a = backtest.run(PRICES, w, 10_000, 0)
    b = backtest.run(PRICES, w, 10_000, 2_000)
    assert abs(a.metrics.cagr - b.metrics.cagr) < 0.01, (a.metrics.cagr, b.metrics.cagr)


def t_fees_reduce_balance():
    w = portfolios.target_weights("balanced", 20)
    lo = backtest.run(PRICES, w, 10_000, 0, extra_fee=0.0)
    hi = backtest.run(PRICES, w, 10_000, 0, extra_fee=0.02)
    assert hi.final_balance < lo.final_balance
    assert hi.fees_paid > lo.fees_paid


def t_zero_return_preserves_capital():
    flat = pd.DataFrame(100.0, index=PRICES.index, columns=PRICES.columns)
    r = backtest.run(flat, {"VTI": 0.5, "BND": 0.5}, initial=10_000, extra_fee=0.0)
    # only the funds' own expense ratios apply
    assert 9_500 < r.final_balance <= 10_000, r.final_balance


# -- monte carlo ------------------------------------------------------------
def t_projection_ordered():
    r = portfolio_returns(PRICES, portfolios.TARGETS["balanced"])
    p = montecarlo.project(r, 10_000, 500, years=15)
    assert p.final_p10 < p.final_p50 < p.final_p90
    assert len(p.months) == 180
    assert 0.0 <= p.prob_beat_contributions <= 1.0


def t_projection_deterministic():
    r = portfolio_returns(PRICES, portfolios.TARGETS["balanced"])
    a = montecarlo.project(r, 10_000, 0, years=10, seed=7)
    b = montecarlo.project(r, 10_000, 0, years=10, seed=7)
    assert a.final_p50 == b.final_p50


def t_zero_contribution_zero_growth():
    flat = pd.Series(0.0, index=PRICES.index[1:])
    p = montecarlo.project(flat, 10_000, 0, years=5)
    assert abs(p.final_p50 - 10_000) < 1e-6


# -- allocate ---------------------------------------------------------------
def t_build_allocation_sums():
    r = allocate.build(50_000, 20, "aggressive", prices=PRICES, source=SOURCE)
    assert abs(sum(a["weight"] for a in r["allocation"]) - 1.0) < 1e-6
    assert abs(sum(a["dollars"] for a in r["allocation"]) - 50_000) < 0.5
    for a in r["allocation"]:
        assert a["shares"] > 0 and a["price"] > 0


def t_build_rejects_bad_input():
    for bad in (lambda: allocate.build(-1, 10, "balanced", prices=PRICES),
                lambda: allocate.build(1000, 0, "balanced", prices=PRICES),
                lambda: allocate.build(1000, 10, "yolo", prices=PRICES)):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


def t_savings_capacity():
    s = allocate.savings_capacity(5_000, 2_500)
    assert s["recommended_monthly_investment"] == 1_000
    tight = allocate.savings_capacity(5_000, 4_700)
    assert tight["recommended_monthly_investment"] == 300
    assert tight["warnings"]
    debt = allocate.savings_capacity(5_000, 2_500, high_interest_debt=8_000)
    assert debt["recommended_monthly_investment"] < 1_000


def t_questionnaire_tiers():
    lo = {q["id"]: 0 for q in allocate.QUESTIONS}
    hi = {q["id"]: len(q["options"]) - 1 for q in allocate.QUESTIONS}
    assert allocate.score_questionnaire(lo)["risk_tier"] == "conservative"
    assert allocate.score_questionnaire(hi)["risk_tier"] == "aggressive"
    mid = {"drop_reaction": 2, "experience": 1, "income_stability": 2,
           "withdrawal_risk": 2, "priority": 2}
    assert allocate.score_questionnaire(mid)["risk_tier"] == "balanced"


def t_json_serializable():
    import json
    json.dumps(allocate.build(10_000, 10, "balanced", monthly_contribution=250,
                              prices=PRICES, source=SOURCE))


if __name__ == "__main__":
    print(f"\ndata source: {SOURCE}   rows: {len(PRICES)}   "
          f"span: {PRICES.index[0].date()} -> {PRICES.index[-1].date()}\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("t_"):
            check(name[2:], fn)
    print(f"\n{passed} passed, {failed} failed\n")
    raise SystemExit(1 if failed else 0)
