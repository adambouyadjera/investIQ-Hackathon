"""Historical backtest with contributions, rebalancing and fee drag.

Positions drift with their own returns between rebalance dates, which is what
makes the rebalancing toggle show a real difference rather than a cosmetic one.
Fees are charged daily as (annual_fee / 252) on the whole balance.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import metrics as M
from .data import daily_returns
from .universe import expense_ratio

REBALANCE = {"never": None, "quarterly": "Q", "annual": "Y"}


@dataclass
class BacktestResult:
    dates: pd.DatetimeIndex
    balance: pd.Series
    contributed: pd.Series
    returns: pd.Series
    final_balance: float
    total_contributed: float
    profit: float
    profit_pct: float
    fees_paid: float
    metrics: M.Metrics

    def to_dict(self, downsample: int = 5) -> dict:
        """JSON-ready. Downsampled so the API doesn't ship 3,000 points."""
        idx = self.balance.iloc[::downsample]
        con = self.contributed.iloc[::downsample]
        dd = M.drawdown_series(self.returns).iloc[::downsample]
        return {
            "series": [
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "balance": round(float(b), 2),
                    "contributed": round(float(c), 2),
                    "drawdown": round(float(w), 5),
                }
                for d, b, c, w in zip(idx.index, idx.values, con.values, dd.values)
            ],
            "final_balance": round(self.final_balance, 2),
            "total_contributed": round(self.total_contributed, 2),
            "profit": round(self.profit, 2),
            "profit_pct": round(self.profit_pct, 5),
            "fees_paid": round(self.fees_paid, 2),
            "metrics": self.metrics.to_dict(),
        }


def run(
    prices: pd.DataFrame,
    weights: dict[str, float],
    initial: float = 10_000.0,
    monthly_contribution: float = 0.0,
    rebalance: str = "annual",
    extra_fee: float = 0.0,
    years: float | None = None,
) -> BacktestResult:
    """Simulate the portfolio over the available price history.

    `extra_fee` is an additional annual drag on top of the weighted expense
    ratio — this is the advisor-fee slider.
    """
    if rebalance not in REBALANCE:
        raise ValueError(f"rebalance must be one of {list(REBALANCE)}")

    rets = daily_returns(prices)
    if years is not None:
        rets = rets.iloc[-int(years * M.TRADING_DAYS):]
    tickers = [t for t in weights if t in rets.columns]

    R = rets[tickers].to_numpy()
    w0 = np.array([weights[t] for t in tickers], dtype=float)
    w0 = w0 / w0.sum()

    fee = expense_ratio(weights) + extra_fee
    daily_fee = fee / M.TRADING_DAYS

    dates = rets.index
    # First trading day of each month gets a contribution (skip day 0).
    month_starts = np.zeros(len(dates), dtype=bool)
    month_starts[1:] = dates[1:].to_period("M").to_numpy() != dates[:-1].to_period("M").to_numpy()

    freq = REBALANCE[rebalance]
    if freq:
        period = dates.to_period(freq).to_numpy()
        rebal_days = np.zeros(len(dates), dtype=bool)
        rebal_days[1:] = period[1:] != period[:-1]
    else:
        rebal_days = np.zeros(len(dates), dtype=bool)

    pos = w0 * initial
    balance = np.empty(len(dates))
    contributed = np.empty(len(dates))
    cum_contrib = initial
    fees_paid = 0.0

    for i in range(len(dates)):
        pos = pos * (1.0 + R[i])
        charge = pos.sum() * daily_fee
        fees_paid += charge
        pos *= 1.0 - daily_fee

        if month_starts[i] and monthly_contribution:
            pos += w0 * monthly_contribution
            cum_contrib += monthly_contribution

        if rebal_days[i]:
            pos = w0 * pos.sum()

        balance[i] = pos.sum()
        contributed[i] = cum_contrib

    bal = pd.Series(balance, index=dates, name="balance")
    con = pd.Series(contributed, index=dates, name="contributed")

    # Return series must exclude contribution inflows or metrics are garbage.
    gross = bal / bal.shift(1)
    inflow = pd.Series(0.0, index=dates)
    inflow[month_starts] = monthly_contribution
    adj = (bal - inflow) / bal.shift(1)
    port_rets = (adj.where(inflow > 0, gross) - 1.0).iloc[1:]

    final = float(bal.iloc[-1])
    profit = final - cum_contrib
    return BacktestResult(
        dates=dates,
        balance=bal,
        contributed=con,
        returns=port_rets,
        final_balance=final,
        total_contributed=cum_contrib,
        profit=profit,
        profit_pct=profit / cum_contrib if cum_contrib else 0.0,
        fees_paid=fees_paid,
        metrics=M.compute(port_rets),
    )
