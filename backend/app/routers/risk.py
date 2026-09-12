"""Risk desk endpoints — expose the trading risk gate over HTTP.

Every number returned here comes from `trading/`, which is deterministic and
unit-tested. No model output reaches these figures.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from ..models.user import User
from ..routers.auth import get_current_user

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from trading import policy                                    # noqa: E402
from trading.checks import evaluate                           # noqa: E402
from trading.types import AccountState, OrderIntent, Side     # noqa: E402

router = APIRouter(prefix="/risk", tags=["risk"])

# These are what-if evaluations, not a live desk. Passing None means the gate
# neither reads nor writes a persistent block file — an earlier version used a
# sentinel path, and a drawdown scenario created it for real, wedging every
# later request.
_NO_BLOCK = None


class RiskRequest(BaseModel):
    equity: float = Field(2000, gt=0)
    peak_equity: Optional[float] = Field(None, gt=0)
    day_start_equity: Optional[float] = Field(None, gt=0)
    week_start_equity: Optional[float] = Field(None, gt=0)
    month_start_equity: Optional[float] = Field(None, gt=0)
    open_risk: float = Field(0, ge=0)
    open_position_count: int = Field(0, ge=0)

    symbol: str = "DEMO"
    side: Literal["long", "short"] = "long"
    entry: float = Field(50, gt=0)
    stop: float = Field(49, gt=0)
    target_1: float = Field(52, gt=0)
    target_2: float = Field(53, gt=0)
    strategy: str = "ema_cross"

    regime: Literal["calm", "volatile", "bear"] = "calm"
    regime_stability: int = Field(3, ge=0, le=10)
    strategy_permitted: bool = True
    bar_closed: bool = True
    cost_per_share: float = Field(0, ge=0)

    @field_validator("stop")
    @classmethod
    def stop_differs(cls, v: float, info):
        if info.data.get("entry") == v:
            raise ValueError("stop must differ from entry")
        return v


@router.get("/policy")
async def get_policy(current_user: User = Depends(get_current_user)):
    """The risk constitution, as the engine actually holds it."""
    return {
        "policy_hash": policy.policy_hash(),
        "risk_per_trade": policy.RISK_PER_TRADE,
        "max_concentration": policy.MAX_CONCENTRATION,
        "max_open_risk": policy.MAX_OPEN_RISK,
        "max_positions": policy.MAX_POSITIONS,
        "min_risk_reward": policy.MIN_RISK_REWARD,
        "cascade": [
            {"scope": "Every trade", "trigger": "Planned loss at stop",
             "threshold": policy.RISK_PER_TRADE,
             "action": "Risk at most 1% of current equity"},
            {"scope": "Day", "trigger": "Down 2% today",
             "threshold": policy.DAILY_HALF_SIZE, "action": "Half size"},
            {"scope": "Day", "trigger": "Down more than 3% today",
             "threshold": policy.DAILY_FLATTEN, "action": "Flatten, no new entries"},
            {"scope": "Week", "trigger": "Down 5% this week",
             "threshold": policy.WEEKLY_HALF_SIZE, "action": "Half size"},
            {"scope": "Week", "trigger": "Down 6% this week",
             "threshold": policy.WEEKLY_STOP, "action": "No new entries"},
            {"scope": "Month", "trigger": "Down 10% this month",
             "threshold": policy.MONTHLY_STOP, "action": "No new entries"},
            {"scope": "Peak", "trigger": "Down 10% from peak equity",
             "threshold": policy.PEAK_DRAWDOWN_BLOCK,
             "action": "Full stop, human review required"},
        ],
    }


@router.post("/evaluate")
async def evaluate_proposal(
    body: RiskRequest, current_user: User = Depends(get_current_user)
):
    """Run one proposal through the gate. Returns every check, in order."""
    equity = body.equity
    state = AccountState(
        equity=equity,
        peak_equity=body.peak_equity or equity,
        buying_power=equity * 2,
        day_start_equity=body.day_start_equity or equity,
        week_start_equity=body.week_start_equity or equity,
        month_start_equity=body.month_start_equity or equity,
        open_positions={f"HELD{i}": 0.0 for i in range(body.open_position_count)},
        open_risk=body.open_risk,
        as_of=datetime.now(timezone.utc),
    )

    intent = OrderIntent(
        symbol=body.symbol,
        side=Side(body.side),
        entry=body.entry,
        stop=body.stop,
        target_1=body.target_1,
        target_2=body.target_2,
        strategy=body.strategy,
        regime=body.regime,
        invalidation="below signal swing low",
    )

    decision = evaluate(
        intent, state,
        regime=body.regime,
        regime_stability=body.regime_stability,
        strategy_permitted=body.strategy_permitted,
        bar_closed=body.bar_closed,
        cost_per_share=body.cost_per_share,
        block_file=_NO_BLOCK,
    )

    breakers = policy.evaluate_breakers(state, _NO_BLOCK)
    position_value = decision.quantity * body.entry

    return {
        "approved": decision.approved,
        "quantity": decision.quantity,
        "planned_loss": round(decision.planned_loss, 2),
        "position_value": round(position_value, 2),
        "risk_pct": round(decision.planned_loss / equity, 6) if equity else 0,
        "concentration_pct": round(position_value / equity, 6) if equity else 0,
        "risk_reward": round(intent.risk_reward, 2),
        "stop_distance": round(intent.stop_distance, 4),
        "veto_code": decision.veto_code,
        "veto_reason": decision.veto_reason,
        "checks": [
            {"name": c.name, "passed": c.passed, "code": c.code, "reason": c.reason}
            for c in decision.checks
        ],
        "active_breakers": [
            {"name": b.name, "action": b.action.value, "detail": b.detail}
            for b in breakers
        ],
        "account": {
            "equity": equity,
            "daily_pct": round(state.daily_pct, 6),
            "weekly_pct": round(state.weekly_pct, 6),
            "monthly_pct": round(state.monthly_pct, 6),
            "drawdown_pct": round(state.drawdown_pct, 6),
        },
        "policy_hash": policy.policy_hash(),
        "disclaimer": (
            "Simulated risk evaluation. No broker is connected and no order is "
            "placed. Educational use only. Not financial advice."
        ),
    }
