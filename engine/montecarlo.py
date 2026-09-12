"""Forward projection by block bootstrap.

Why block bootstrap rather than drawing from a normal distribution: real
returns have fat tails and volatility clustering. Resampling contiguous
21-day blocks of actual history preserves both, for free. Drawing IID normals
would understate the chance of a bad decade, which is exactly the number a
user cares about.

This produces the fan chart. It is the best visual in the app.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252
BLOCK = 21  # one trading month


@dataclass
class Projection:
    months: list[int]
    p10: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p90: list[float]
    contributed: list[float]
    final_p10: float
    final_p50: float
    final_p90: float
    prob_beat_contributions: float
    prob_hit_goal: float | None

    def to_dict(self) -> dict:
        d = {
            "series": [
                {
                    "month": m,
                    "p10": round(a, 2), "p25": round(b, 2), "p50": round(c, 2),
                    "p75": round(e, 2), "p90": round(f, 2), "contributed": round(g, 2),
                }
                for m, a, b, c, e, f, g in zip(
                    self.months, self.p10, self.p25, self.p50,
                    self.p75, self.p90, self.contributed,
                )
            ],
            "final_p10": round(self.final_p10, 2),
            "final_p50": round(self.final_p50, 2),
            "final_p90": round(self.final_p90, 2),
            "prob_beat_contributions": round(self.prob_beat_contributions, 4),
        }
        if self.prob_hit_goal is not None:
            d["prob_hit_goal"] = round(self.prob_hit_goal, 4)
        return d


def project(
    historical_returns: pd.Series,
    initial: float,
    monthly_contribution: float,
    years: float,
    annual_fee: float = 0.0,
    n_paths: int = 2000,
    goal: float | None = None,
    seed: int = 42,
) -> Projection:
    r = historical_returns.dropna().to_numpy()
    if len(r) < BLOCK * 2:
        raise ValueError("not enough history to bootstrap")

    rng = np.random.default_rng(seed)
    n_months = max(1, int(round(years * 12)))
    n_blocks = n_months  # one 21-day block per projected month

    starts = rng.integers(0, len(r) - BLOCK, size=(n_paths, n_blocks))
    offsets = np.arange(BLOCK)
    # (paths, months, 21) -> monthly compounded growth factor
    sampled = r[starts[:, :, None] + offsets[None, None, :]]
    monthly_growth = np.prod(1.0 + sampled, axis=2)
    monthly_growth *= 1.0 - annual_fee / 12.0

    bal = np.full(n_paths, float(initial))
    contributed = float(initial)
    p10, p25, p50, p75, p90, con = [], [], [], [], [], []

    for m in range(n_months):
        bal = bal * monthly_growth[:, m] + monthly_contribution
        contributed += monthly_contribution
        q = np.quantile(bal, [0.10, 0.25, 0.50, 0.75, 0.90])
        p10.append(q[0]); p25.append(q[1]); p50.append(q[2])
        p75.append(q[3]); p90.append(q[4]); con.append(contributed)

    return Projection(
        months=list(range(1, n_months + 1)),
        p10=p10, p25=p25, p50=p50, p75=p75, p90=p90, contributed=con,
        final_p10=float(np.quantile(bal, 0.10)),
        final_p50=float(np.quantile(bal, 0.50)),
        final_p90=float(np.quantile(bal, 0.90)),
        prob_beat_contributions=float((bal > contributed).mean()),
        prob_hit_goal=float((bal >= goal).mean()) if goal else None,
    )
