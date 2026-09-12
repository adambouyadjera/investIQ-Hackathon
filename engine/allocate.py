"""Top-level orchestration: the one function the API actually calls.

Also holds the two "personal finance" pieces from the brief:
  * savings_capacity -- how much you should invest given your income
  * score_questionnaire -- derive a risk tier instead of asking the user to
    self-diagnose, which people are famously bad at
"""

from __future__ import annotations

import math

import pandas as pd

from . import backtest, metrics, montecarlo, portfolios
from .data import daily_returns, load_prices, portfolio_returns
from .universe import BY_TICKER, expense_ratio

EMERGENCY_MONTHS = 4.0
DEFAULT_SAVINGS_RATE = 0.20


# --------------------------------------------------------------------------
# How much should I be investing?
# --------------------------------------------------------------------------
def savings_capacity(
    monthly_take_home: float,
    monthly_essentials: float | None = None,
    high_interest_debt: float = 0.0,
    emergency_fund: float = 0.0,
    target_rate: float = DEFAULT_SAVINGS_RATE,
) -> dict:
    """50/30/20 baseline with debt and emergency-fund gates in front of it."""
    if monthly_take_home <= 0:
        raise ValueError("monthly_take_home must be positive")
    if monthly_essentials is None:
        monthly_essentials = monthly_take_home * 0.50

    surplus = max(0.0, monthly_take_home - monthly_essentials)
    baseline = monthly_take_home * target_rate
    recommended = min(surplus, baseline)

    warnings: list[str] = []
    ef_target = monthly_essentials * EMERGENCY_MONTHS
    ef_gap = max(0.0, ef_target - emergency_fund)

    if high_interest_debt > 0:
        warnings.append(
            "You listed high-interest debt. Paying it down is a guaranteed "
            "return at the interest rate, which almost certainly beats this "
            "portfolio's expected return. Clear it first."
        )
        recommended *= 0.5
    if ef_gap > 0:
        warnings.append(
            f"Your emergency fund is ${ef_gap:,.0f} short of {EMERGENCY_MONTHS:.0f} "
            f"months of essentials (${ef_target:,.0f}). Consider directing part of "
            "your surplus there before investing it."
        )
    if surplus < baseline:
        warnings.append(
            "Your surplus is below the 20% baseline, so the recommendation is "
            "capped at what's actually left over."
        )

    return {
        "monthly_take_home": round(monthly_take_home, 2),
        "monthly_essentials": round(monthly_essentials, 2),
        "monthly_surplus": round(surplus, 2),
        "recommended_monthly_investment": round(recommended, 2),
        "recommended_annual_investment": round(recommended * 12, 2),
        "effective_savings_rate": round(recommended / monthly_take_home, 4),
        "emergency_fund_target": round(ef_target, 2),
        "emergency_fund_gap": round(ef_gap, 2),
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# Risk questionnaire
# --------------------------------------------------------------------------
QUESTIONS = [
    {
        "id": "drop_reaction",
        "prompt": "Your portfolio falls 25% in three months. You:",
        "options": [
            ("Sell everything and wait it out in cash", 0),
            ("Sell some of it", 1),
            ("Do nothing", 3),
            ("Buy more", 4),
        ],
    },
    {
        "id": "experience",
        "prompt": "How long have you been investing?",
        "options": [("Never", 0), ("Under 2 years", 1), ("2-10 years", 2), ("10+ years", 3)],
    },
    {
        "id": "income_stability",
        "prompt": "How stable is your income?",
        "options": [("Irregular", 0), ("Somewhat variable", 1), ("Stable", 2), ("Very stable", 3)],
    },
    {
        "id": "withdrawal_risk",
        "prompt": "Might you need this money before your stated horizon?",
        "options": [("Very likely", 0), ("Possibly", 1), ("Unlikely", 2), ("Definitely not", 3)],
    },
    {
        "id": "priority",
        "prompt": "Which matters more to you?",
        "options": [
            ("Not losing money", 0),
            ("Keeping up with inflation", 1),
            ("Steady growth", 2),
            ("Maximum growth", 4),
        ],
    },
]

MAX_SCORE = sum(max(s for _, s in q["options"]) for q in QUESTIONS)


def score_questionnaire(answers: dict[str, int]) -> dict:
    """answers maps question id -> selected option index."""
    total = 0
    for q in QUESTIONS:
        idx = answers.get(q["id"])
        if idx is None or not (0 <= idx < len(q["options"])):
            raise ValueError(f"missing or invalid answer for {q['id']!r}")
        total += q["options"][idx][1]

    pct = total / MAX_SCORE
    tier = "conservative" if pct < 0.45 else "balanced" if pct < 0.75 else "aggressive"
    return {"score": total, "max_score": MAX_SCORE, "percentile": round(pct, 3), "risk_tier": tier}


# --------------------------------------------------------------------------
# The main call
# --------------------------------------------------------------------------
def build(
    amount: float,
    horizon_years: float,
    risk: str,
    monthly_contribution: float = 0.0,
    rebalance: str = "annual",
    extra_fee: float = 0.0,
    goal: float | None = None,
    prices: pd.DataFrame | None = None,
    source: str = "unknown",
) -> dict:
    """(amount, horizon, risk) -> allocation + historical stats + projection."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    if prices is None:
        prices, source = load_prices()

    weights = portfolios.target_weights(risk, horizon_years)
    latest = prices.iloc[-1]

    allocation = []
    for ticker, w in weights.items():
        asset = BY_TICKER[ticker]
        dollars = amount * w
        price = float(latest[ticker])
        allocation.append({
            "ticker": ticker,
            "name": asset.name,
            "kind": asset.kind,
            "weight": round(w, 4),
            "dollars": round(dollars, 2),
            "price": round(price, 2),
            "shares": round(dollars / price, 4),
            "whole_shares": int(dollars // price),
            "expense_ratio": asset.expense_ratio,
        })

    _rets = daily_returns(prices)
    for item in allocation:
        t = item["ticker"]
        if t in _rets.columns:
            item["return_1y"] = round(float((1 + _rets[t].iloc[-252:]).prod() - 1), 5)
            item["return_5y"] = round(float((1 + _rets[t].iloc[-1260:]).prod() - 1), 5)
        else:
            item["return_1y"] = None
            item["return_5y"] = None

    bt = backtest.run(
        prices, weights,
        initial=amount,
        monthly_contribution=monthly_contribution,
        rebalance=rebalance,
        extra_fee=extra_fee,
    )
    proj = montecarlo.project(
        portfolio_returns(prices, weights),
        initial=amount,
        monthly_contribution=monthly_contribution,
        years=horizon_years,
        annual_fee=expense_ratio(weights) + extra_fee,
        goal=goal,
    )
    held = [item["ticker"] for item in allocation]
    _corr = metrics.correlation_matrix(_rets[held])
    corr_dict = {
        row: {col: round(float(_corr.loc[row, col]), 4) for col in held}
        for row in held
    }

    return {
        "inputs": {
            "amount": amount,
            "horizon_years": horizon_years,
            "risk": risk,
            "risk_label": portfolios.LABELS[risk],
            "monthly_contribution": monthly_contribution,
            "rebalance": rebalance,
            "extra_fee": extra_fee,
            "goal": goal,
        },
        "data_source": source,
        "history_start": prices.index[0].strftime("%Y-%m-%d"),
        "history_end": prices.index[-1].strftime("%Y-%m-%d"),
        "allocation": allocation,
        "equity_share": round(portfolios.equity_share(weights), 4),
        "horizon_factor": round(portfolios.horizon_factor(horizon_years), 3),
        "blended_expense_ratio": round(expense_ratio(weights), 5),
        "correlation_matrix": corr_dict,
        "backtest": bt.to_dict(),
        "projection": proj.to_dict(),
        "disclaimer": (
            "Simulated results based on historical data. Educational use only. "
            "Not financial advice."
        ),
    }


def compare(
    amount: float, horizon_years: float, tiers: list[str] | None = None, **kw
) -> dict:
    """Run several tiers over identical data for side-by-side comparison."""
    prices, source = load_prices()
    tiers = tiers or ["conservative", "balanced", "aggressive"]
    return {
        "data_source": source,
        "results": {
            t: build(amount, horizon_years, t, prices=prices, source=source, **kw)
            for t in tiers
        },
    }
