"""Savings-capacity endpoint.

Wraps engine.allocate.savings_capacity() — a pure financial calculation.
No LLM involvement. No numbers invented here.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine import allocate as _allocate  # noqa: E402

from .auth import get_current_user
from ..models.user import User

router = APIRouter(tags=["savings"])


class SavingsRequest(BaseModel):
    monthly_take_home: float = Field(gt=0)
    monthly_essentials: Optional[float] = Field(default=None, ge=0)
    high_interest_debt: float = Field(default=0.0, ge=0)
    emergency_fund: float = Field(default=0.0, ge=0)


@router.post("/savings-capacity")
async def savings_capacity(
    body: SavingsRequest,
    current_user: User = Depends(get_current_user),
):
    """Return recommended monthly investment amount and any warnings."""
    try:
        return _allocate.savings_capacity(
            monthly_take_home=body.monthly_take_home,
            monthly_essentials=body.monthly_essentials,
            high_interest_debt=body.high_interest_debt,
            emergency_fund=body.emergency_fund,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
