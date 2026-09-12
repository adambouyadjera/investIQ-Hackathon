"""Allocation and comparison endpoints.

Thin wrappers over engine.allocate.build() and engine.allocate.compare().
No financial logic lives here — all computation is in the engine.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Literal

# Ensure engine package on path (project root is 3 levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine import allocate as _allocate  # noqa: E402
from engine.data import load_prices        # noqa: E402

from .auth import get_current_user
from ..models.user import User

router = APIRouter(tags=["simulation"])


# ── Request model ─────────────────────────────────────────────────────────────

class AllocateRequest(BaseModel):
    amount: float = Field(gt=0, le=10_000_000)
    horizon_years: float = Field(gt=0, le=50)
    risk: Literal["conservative", "balanced", "aggressive"]
    monthly_contribution: float = Field(ge=0, default=0.0)
    rebalance: Literal["never", "quarterly", "annual"] = "annual"
    extra_fee: float = Field(ge=0, le=0.05, default=0.0)
    goal: Optional[float] = Field(default=None, gt=0)
    etf_only: bool = False
    backtest_years: Optional[int] = Field(default=None, ge=3, le=20)
    purpose: Optional[Literal["retirement", "house", "education", "general"]] = None


class CompareRequest(BaseModel):
    amount: float = Field(gt=0, le=10_000_000)
    horizon_years: float = Field(gt=0, le=50)
    monthly_contribution: float = Field(ge=0, default=0.0)
    rebalance: Literal["never", "quarterly", "annual"] = "annual"
    extra_fee: float = Field(ge=0, le=0.05, default=0.0)
    goal: Optional[float] = Field(default=None, gt=0)
    etf_only: bool = False
    backtest_years: Optional[int] = Field(default=None, ge=3, le=20)
    tiers: list[Literal["conservative", "balanced", "aggressive"]] = [
        "conservative", "balanced", "aggressive"
    ]


# ── ETF-only filter ────────────────────────────────────────────────────────────

_ETF_TICKERS = {
    "VTI", "VXUS", "QQQ", "VBR", "BND", "TLT", "TIP", "BIL", "GLD", "VNQ"
}

# single-stock tickers that etf_only mode excludes
_SINGLE_STOCKS = {"AAPL", "MSFT", "NVDA", "JNJ", "JPM"}


def _build_kwargs(req: AllocateRequest | CompareRequest, risk: str | None = None) -> dict:
    """Translate request fields into allocate.build() kwargs."""
    kw: dict = dict(
        monthly_contribution=req.monthly_contribution,
        rebalance=req.rebalance,
        extra_fee=req.extra_fee,
        goal=req.goal,
    )
    if req.backtest_years is not None:
        kw["years"] = req.backtest_years  # passed through to backtest.run via build()
    if risk is not None:
        kw["risk"] = risk
    return kw


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/allocate")
async def allocate(
    body: AllocateRequest,
    current_user: User = Depends(get_current_user),
):
    """Main simulation endpoint. Returns allocation + backtest + projection."""
    try:
        prices, source = load_prices()
        result = _allocate.build(
            amount=body.amount,
            horizon_years=body.horizon_years,
            risk=body.risk,
            prices=prices,
            source=source,
            **_build_kwargs(body),
        )
        # Attach purpose so the explain endpoint can use it
        if body.purpose:
            result["purpose"] = body.purpose
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {e}")


@router.post("/compare")
async def compare(
    body: CompareRequest,
    current_user: User = Depends(get_current_user),
):
    """Run 2–3 risk tiers over identical inputs for side-by-side comparison."""
    try:
        prices, source = load_prices()
        results = {}
        shared_kw = dict(
            amount=body.amount,
            horizon_years=body.horizon_years,
            prices=prices,
            source=source,
            monthly_contribution=body.monthly_contribution,
            rebalance=body.rebalance,
            extra_fee=body.extra_fee,
            goal=body.goal,
        )
        for tier in body.tiers:
            results[tier] = _allocate.build(risk=tier, **shared_kw)
        return {"data_source": source, "results": results}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison error: {e}")
