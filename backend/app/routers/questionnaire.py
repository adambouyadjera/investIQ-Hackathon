"""Risk questionnaire endpoints.

Questions and scoring are entirely delegated to engine.allocate.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine import allocate as _allocate  # noqa: E402

from .auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/questionnaire", tags=["questionnaire"])


class ScoreRequest(BaseModel):
    drop_reaction: int
    experience: int
    income_stability: int
    withdrawal_risk: int
    priority: int


@router.get("")
async def get_questions(current_user: User = Depends(get_current_user)):
    """Return the 5 risk-assessment questions."""
    return _allocate.QUESTIONS


@router.post("/score")
async def score(
    body: ScoreRequest,
    current_user: User = Depends(get_current_user),
):
    """Score questionnaire answers and return the recommended risk tier."""
    try:
        return _allocate.score_questionnaire(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
