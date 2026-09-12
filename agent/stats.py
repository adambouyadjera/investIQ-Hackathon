"""Statistics the harness needs and the standard library does not have.

No scipy in this project's dependency set, so the two distribution functions
are implemented here. `norm_cdf` is `math.erf` rearranged; `norm_ppf` inverts
it by bisection rather than a rational approximation, because sixty iterations
of bisection is instant at this call volume and is obviously correct on
inspection, which a table of fitted constants is not.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

SQRT2 = math.sqrt(2.0)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def norm_ppf(p: float, tol: float = 1e-12) -> float:
    """Inverse standard normal CDF by bisection."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must lie strictly between 0 and 1")
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def sharpe_per_period(returns: np.ndarray, risk_free_per_period: float = 0.0) -> float:
    """Non-annualized Sharpe. The deflated ratio below is defined on this scale."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    if sd == 0:
        return 0.0
    return float((r.mean() - risk_free_per_period) / sd)


def skewness(returns: np.ndarray) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return 0.0
    sd = r.std(ddof=1)
    if sd == 0:
        return 0.0
    return float((((r - r.mean()) / sd) ** 3).mean())


def kurtosis(returns: np.ndarray) -> float:
    """Non-excess (normal = 3.0), which is the convention the DSR formula uses."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 4:
        return 3.0
    sd = r.std(ddof=1)
    if sd == 0:
        return 3.0
    return float((((r - r.mean()) / sd) ** 4).mean())


EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe(n_trials: int, variance_of_trials: float) -> float:
    """The Sharpe you should expect from the *best* of N worthless strategies.

    This is the number the video's leaderboard is missing. Generate 185
    strategies against one price history, keep the best-looking one, and its
    backtest Sharpe is a maximum drawn from a distribution -- not an estimate
    of an edge. The expected maximum grows with the number of trials, so the
    hurdle a strategy must clear has to grow with it too.

    Uses the standard extreme-value approximation for the expected maximum of
    N draws from a normal distribution.
    """
    if n_trials < 1:
        raise ValueError("n_trials must be at least 1")
    if n_trials == 1 or variance_of_trials <= 0:
        return 0.0
    g = EULER_MASCHERONI
    a = norm_ppf(1.0 - 1.0 / n_trials)
    b = norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(variance_of_trials) * ((1.0 - g) * a + g * b)


def deflated_sharpe(
    returns: Sequence[float],
    n_trials: int = 1,
    variance_of_trials: float = 0.0,
    risk_free_per_period: float = 0.0,
) -> dict:
    """Probability the observed Sharpe reflects skill rather than selection.

    Implements the deflated Sharpe ratio of Bailey and Lopez de Prado: correct
    the observed Sharpe for non-normal returns, sample length, *and* the number
    of strategies that were tried before this one was chosen.

    Read the output as: given that I looked at `n_trials` strategies over this
    many observations, how confident can I be that this one's Sharpe is above
    the threshold a lucky strategy would have reached anyway? A value below
    ~0.95 is not evidence of an edge.
    """
    r = np.asarray(list(returns), dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    sr = sharpe_per_period(r, risk_free_per_period)

    if n < 8:
        return {
            "sharpe_per_period": round(sr, 6),
            "sharpe_annualized": round(sr * math.sqrt(252), 4),
            "n_observations": n,
            "n_trials": n_trials,
            "threshold_sharpe": None,
            "deflated_sharpe": None,
            "verdict": "too few observations to deflate",
        }

    sk = skewness(r)
    ku = kurtosis(r)
    sr0 = expected_max_sharpe(n_trials, variance_of_trials)

    denom_sq = 1.0 - sk * sr + ((ku - 1.0) / 4.0) * sr * sr
    if denom_sq <= 0:
        return {
            "sharpe_per_period": round(sr, 6),
            "sharpe_annualized": round(sr * math.sqrt(252), 4),
            "n_observations": n,
            "n_trials": n_trials,
            "threshold_sharpe": round(sr0, 6),
            "deflated_sharpe": None,
            "verdict": "return distribution too extreme to deflate reliably",
        }

    z = (sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom_sq)
    dsr = norm_cdf(z)

    if dsr >= 0.95:
        verdict = "clears the selection-adjusted hurdle at 95%"
    elif dsr >= 0.80:
        verdict = "suggestive, below the 95% hurdle"
    else:
        verdict = "indistinguishable from selection luck"

    return {
        "sharpe_per_period": round(sr, 6),
        "sharpe_annualized": round(sr * math.sqrt(252), 4),
        "skew": round(sk, 4),
        "kurtosis": round(ku, 4),
        "n_observations": n,
        "n_trials": n_trials,
        "threshold_sharpe": round(sr0, 6),
        "threshold_sharpe_annualized": round(sr0 * math.sqrt(252), 4),
        "deflated_sharpe": round(dsr, 4),
        "verdict": verdict,
    }


def ols_alpha_beta(strategy: np.ndarray, benchmark: np.ndarray) -> tuple:
    """Least squares of strategy on benchmark. Returns (alpha_per_period, beta)."""
    s = np.asarray(strategy, dtype=float)
    b = np.asarray(benchmark, dtype=float)
    mask = np.isfinite(s) & np.isfinite(b)
    s, b = s[mask], b[mask]
    if len(s) < 3:
        return 0.0, 0.0
    var = b.var(ddof=1)
    if var == 0:
        return float(s.mean()), 0.0
    beta = float(np.cov(s, b, ddof=1)[0, 1] / var)
    return float(s.mean() - beta * b.mean()), beta
