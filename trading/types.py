"""Data types for the risk layer.

An OrderIntent is what a strategy is allowed to produce. Note what it does NOT
contain: a quantity. Size is not the strategy's decision — the risk service
computes it from the stop distance and current equity. A strategy that could
name its own size could bypass every limit below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class Action(str, Enum):
    """What an active circuit breaker forces. Ordered by severity."""
    NORMAL = "normal"
    HALF_SIZE = "half_size"
    NO_NEW_ENTRIES = "no_new_entries"
    FLATTEN = "flatten"
    BLOCKED = "blocked"


SEVERITY = {
    Action.NORMAL: 0,
    Action.HALF_SIZE: 1,
    Action.NO_NEW_ENTRIES: 2,
    Action.FLATTEN: 3,
    Action.BLOCKED: 4,
}


@dataclass(frozen=True)
class OrderIntent:
    """A strategy's proposal. Never an order."""
    symbol: str
    side: Side
    entry: float
    stop: float
    target_1: float
    target_2: float
    strategy: str
    regime: str
    invalidation: str
    signal_time: datetime = field(default_factory=utcnow)

    @property
    def stop_distance(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def risk_reward(self) -> float:
        """Reward at target_2 expressed in R (multiples of planned loss)."""
        if self.stop_distance == 0:
            return 0.0
        return abs(self.target_2 - self.entry) / self.stop_distance


@dataclass(frozen=True)
class AccountState:
    """Reconciled broker state. Every field is required — see VETO_STALE_STATE."""
    equity: float
    peak_equity: float
    buying_power: float
    day_start_equity: float
    week_start_equity: float
    month_start_equity: float
    open_positions: dict[str, float] = field(default_factory=dict)  # symbol -> $ value
    open_risk: float = 0.0  # sum of planned loss across live stops
    as_of: datetime = field(default_factory=utcnow)

    def pct_from(self, baseline: float) -> float:
        if baseline <= 0:
            raise ValueError("baseline equity must be positive")
        return (self.equity - baseline) / baseline

    @property
    def daily_pct(self) -> float:
        return self.pct_from(self.day_start_equity)

    @property
    def weekly_pct(self) -> float:
        return self.pct_from(self.week_start_equity)

    @property
    def monthly_pct(self) -> float:
        return self.pct_from(self.month_start_equity)

    @property
    def drawdown_pct(self) -> float:
        return self.pct_from(self.peak_equity)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    code: str
    reason: str
    inputs_used: dict = field(default_factory=dict)
    at: datetime = field(default_factory=utcnow)

    def __str__(self) -> str:
        mark = "PASS" if self.passed else "VETO"
        return f"{mark}  {self.name:<22} {self.code}"


@dataclass
class RiskDecision:
    """The only thing an execution layer would be allowed to accept."""
    approved: bool
    quantity: int = 0
    planned_loss: float = 0.0
    veto_code: str = ""
    veto_reason: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    active_breakers: list[str] = field(default_factory=list)
    decided_at: datetime = field(default_factory=utcnow)

    def summary(self) -> str:
        if self.approved:
            return f"CLEARED qty={self.quantity} planned_loss=${self.planned_loss:,.2f}"
        return f"VETO {self.veto_code}: {self.veto_reason}"
