"""Saved portfolios CRUD — up to 10 per user.

Renamed from scenarios.py. Same logic, updated paths and field names.
"""
from __future__ import annotations

import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.portfolio import Portfolio
from .auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

MAX_PORTFOLIOS = 10


# ── Schemas ───────────────────────────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    risk_tier: str
    amount: float = Field(gt=0)
    horizon_years: float = Field(gt=0)
    monthly_contribution: float = Field(ge=0, default=0.0)
    extra_fee: float = Field(ge=0, default=0.0)
    goal: Optional[float] = None
    purpose: Optional[str] = None
    result_json: Optional[dict] = None


class PortfolioOut(BaseModel):
    id: str
    name: str
    risk_tier: str
    amount: float
    horizon_years: float
    monthly_contribution: float
    extra_fee: float
    goal: Optional[float]
    purpose: Optional[str]
    result_json: Optional[dict]
    created_at: str

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[PortfolioOut])
async def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.created_at.desc())
    )
    rows = result.scalars().all()
    return [_to_out(p) for p in rows]


@router.post("", response_model=PortfolioOut, status_code=201)
async def save_portfolio(
    body: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Efficient count check
    count_result = await db.execute(
        select(func.count()).select_from(Portfolio).where(
            Portfolio.user_id == current_user.id
        )
    )
    count = count_result.scalar_one()
    if count >= MAX_PORTFOLIOS:
        raise HTTPException(
            status_code=400,
            detail=f"You have reached the {MAX_PORTFOLIOS}-portfolio limit. Delete one to save a new one.",
        )

    p = Portfolio(
        user_id=current_user.id,
        name=body.name,
        risk_tier=body.risk_tier,
        amount=body.amount,
        horizon_years=body.horizon_years,
        monthly_contribution=body.monthly_contribution,
        extra_fee=body.extra_fee,
        goal=body.goal,
        purpose=body.purpose,
        result_json=body.result_json,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _to_out(p)


@router.get("/{portfolio_id}", response_model=PortfolioOut)
async def get_portfolio(
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_or_404(portfolio_id, current_user.id, db)
    return _to_out(p)


@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_or_404(portfolio_id, current_user.id, db)
    await db.delete(p)
    await db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(portfolio_id: str, user_id, db: AsyncSession) -> Portfolio:
    try:
        pid = uuid.UUID(portfolio_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid portfolio id")
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == pid,
            Portfolio.user_id == user_id,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return p


def _to_out(p: Portfolio) -> PortfolioOut:
    return PortfolioOut(
        id=str(p.id),
        name=p.name,
        risk_tier=p.risk_tier,
        amount=p.amount,
        horizon_years=p.horizon_years,
        monthly_contribution=p.monthly_contribution,
        extra_fee=p.extra_fee,
        goal=p.goal,
        purpose=p.purpose,
        result_json=p.result_json,
        created_at=p.created_at.isoformat(),
    )
