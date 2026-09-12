"""Saved scenario CRUD — up to 10 per user."""
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.scenario import Scenario
from ..routers.auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

MAX_SCENARIOS = 10


class ScenarioCreate(BaseModel):
    name: str
    risk_tier: str
    amount: float
    horizon_years: float
    monthly_contribution: float = 0.0
    extra_fee: float = 0.0
    goal: Optional[float] = None
    result_json: Optional[dict] = None


class ScenarioOut(BaseModel):
    id: str
    name: str
    risk_tier: str
    amount: float
    horizon_years: float
    monthly_contribution: float
    extra_fee: float
    goal: Optional[float]
    result_json: Optional[dict]
    created_at: str

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ScenarioOut])
async def list_scenarios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Scenario)
        .where(Scenario.user_id == current_user.id)
        .order_by(Scenario.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        ScenarioOut(
            id=str(s.id),
            name=s.name,
            risk_tier=s.risk_tier,
            amount=s.amount,
            horizon_years=s.horizon_years,
            monthly_contribution=s.monthly_contribution,
            extra_fee=s.extra_fee,
            goal=s.goal,
            result_json=s.result_json,
            created_at=s.created_at.isoformat(),
        )
        for s in rows
    ]


@router.post("/", response_model=ScenarioOut, status_code=201)
async def save_scenario(
    body: ScenarioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Enforce cap
    count_result = await db.execute(
        select(Scenario).where(Scenario.user_id == current_user.id)
    )
    count = len(count_result.scalars().all())
    if count >= MAX_SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"You can save up to {MAX_SCENARIOS} scenarios. Delete one first.",
        )

    s = Scenario(
        user_id=current_user.id,
        name=body.name,
        risk_tier=body.risk_tier,
        amount=body.amount,
        horizon_years=body.horizon_years,
        monthly_contribution=body.monthly_contribution,
        extra_fee=body.extra_fee,
        goal=body.goal,
        result_json=body.result_json,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return ScenarioOut(
        id=str(s.id),
        name=s.name,
        risk_tier=s.risk_tier,
        amount=s.amount,
        horizon_years=s.horizon_years,
        monthly_contribution=s.monthly_contribution,
        extra_fee=s.extra_fee,
        goal=s.goal,
        result_json=s.result_json,
        created_at=s.created_at.isoformat(),
    )


@router.delete("/{scenario_id}", status_code=204)
async def delete_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = uuid.UUID(scenario_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scenario id")

    result = await db.execute(
        select(Scenario).where(Scenario.id == sid, Scenario.user_id == current_user.id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Scenario not found")
    await db.delete(s)
    await db.commit()
