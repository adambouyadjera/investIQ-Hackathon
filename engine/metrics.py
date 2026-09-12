"""Performance and risk metrics computed from a daily return series.

Every number the dashboard displays comes from here. Deterministic, testable,
no model calls anywhere near it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252
RISK_FREE = 0.03  # annualized; swap for a BIL-derived series if you want


@dataclass
class Metrics:
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    best_year: float
    worst_year: float
    positive_months: float
    var_95: float  # worst 5% of daily returns

    def to_dict(self) -> dict[str, float]:
        return {k: round(float(v), 6) for k, v in asdict(self).items()}


def equity_curve(returns: pd.Series, start: float = 1.0) -> pd.Series:
    return start * (1.0 + returns).cumprod()


def drawdown_series(returns: pd.Series) -> pd.Series:
    curve = equity_curve(returns)
    return curve / curve.cummax() - 1.0


def compute(returns: pd.Series, risk_free: float = RISK_FREE) -> Metrics:
    r = returns.dropna()
    if len(r) < 2:
        raise ValueError("need at least two return observations")

    years = len(r) / TRADING_DAYS
    total = float((1.0 + r).prod())
    cagr = total ** (1.0 / years) - 1.0
    vol = float(r.std(ddof=1)) * np.sqrt(TRADING_DAYS)

    downside = r[r < 0]
    downside_vol = float(downside.std(ddof=1)) * np.sqrt(TRADING_DAYS) if len(downside) > 1 else np.nan

    dd = float(drawdown_series(r).min())

    annual = (1.0 + r).groupby(r.index.year).prod() - 1.0
    monthly = (1.0 + r).groupby([r.index.year, r.index.month]).prod() - 1.0

    return Metrics(
        cagr=cagr,
        volatility=vol,
        sharpe=(cagr - risk_free) / vol if vol > 0 else 0.0,
        sortino=(cagr - risk_free) / downside_vol if downside_vol and downside_vol > 0 else 0.0,
        max_drawdown=dd,
        calmar=cagr / abs(dd) if dd < 0 else 0.0,
        best_year=float(annual.max()),
        worst_year=float(annual.min()),
        positive_months=float((monthly > 0).mean()),
        var_95=float(r.quantile(0.05)),
    )


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr()
