"""Portfolio simulation endpoints."""
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

# Allow importing the engine from the parent project
_ENGINE_PATH = Path(__file__).resolve().parents[3]
if str(_ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(_ENGINE_PATH))

from engine import allocate  # noqa: E402
from engine.data import load_prices  # noqa: E402

from ..routers.auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    amount: float
    horizon_years: float
    risk: str  # conservative | balanced | aggressive
    monthly_contribution: float = 0.0
    rebalance: str = "annual"
    extra_fee: float = 0.0
    goal: Optional[float] = None

    @field_validator("risk")
    @classmethod
    def valid_risk(cls, v: str) -> str:
        if v not in ("conservative", "balanced", "aggressive"):
            raise ValueError("risk must be conservative, balanced, or aggressive")
        return v

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("horizon_years")
    @classmethod
    def positive_horizon(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("horizon_years must be positive")
        return v

    @field_validator("rebalance")
    @classmethod
    def valid_rebalance(cls, v: str) -> str:
        if v not in ("never", "quarterly", "annual"):
            raise ValueError("rebalance must be never, quarterly, or annual")
        return v


class SavingsRequest(BaseModel):
    monthly_take_home: float
    monthly_essentials: Optional[float] = None
    high_interest_debt: float = 0.0
    emergency_fund: float = 0.0


class QuestionnaireAnswers(BaseModel):
    drop_reaction: int
    experience: int
    income_stability: int
    withdrawal_risk: int
    priority: int


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/simulate")
async def simulate(
    body: SimulateRequest,
    current_user: User = Depends(get_current_user),
):
    """Run a full simulation: allocation + backtest + Monte Carlo projection."""
    try:
        prices, source = load_prices()
        result = allocate.build(
            amount=body.amount,
            horizon_years=body.horizon_years,
            risk=body.risk,
            monthly_contribution=body.monthly_contribution,
            rebalance=body.rebalance,
            extra_fee=body.extra_fee,
            goal=body.goal,
            prices=prices,
            source=source,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare")
async def compare_all(
    body: SimulateRequest,
    current_user: User = Depends(get_current_user),
):
    """Run all three risk tiers over the same inputs for side-by-side comparison."""
    try:
        prices, source = load_prices()
        results = {}
        for tier in ("conservative", "balanced", "aggressive"):
            results[tier] = allocate.build(
                amount=body.amount,
                horizon_years=body.horizon_years,
                risk=tier,
                monthly_contribution=body.monthly_contribution,
                rebalance=body.rebalance,
                extra_fee=body.extra_fee,
                goal=body.goal,
                prices=prices,
                source=source,
            )
        return {"data_source": source, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/savings")
async def savings_capacity(
    body: SavingsRequest,
    current_user: User = Depends(get_current_user),
):
    """How much should I invest based on my income?"""
    try:
        return allocate.savings_capacity(
            monthly_take_home=body.monthly_take_home,
            monthly_essentials=body.monthly_essentials,
            high_interest_debt=body.high_interest_debt,
            emergency_fund=body.emergency_fund,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/questionnaire")
async def risk_questionnaire(
    body: QuestionnaireAnswers,
    current_user: User = Depends(get_current_user),
):
    """Score the risk questionnaire and return the recommended tier."""
    try:
        answers = body.model_dump()
        return allocate.score_questionnaire(answers)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/questions")
async def get_questions(current_user: User = Depends(get_current_user)):
    """Return the questionnaire questions for the frontend to render."""
    return allocate.QUESTIONS
