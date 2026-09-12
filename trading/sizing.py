"""Position sizing.

    quantity = floor((equity * 1%) / |entry - stop|)

Then every cap is applied and the smallest survivor wins. Confidence scores,
conviction, and model output never enter this calculation. The stop distance
and the account balance are the only inputs that set size.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import policy
from .types import AccountState, OrderIntent


@dataclass
class SizingResult:
    quantity: int
    planned_loss: float
    veto_code: str = ""
    veto_reason: str = ""
    caps_applied: list[str] = field(default_factory=list)
    raw_quantity: int = 0

    @property
    def ok(self) -> bool:
        return self.quantity > 0 and not self.veto_code


def calculate(
    intent: OrderIntent,
    state: AccountState,
    multiplier: float = 1.0,
    cost_per_share: float = 0.0,
) -> SizingResult:
    """Size the position, or explain why it can't be sized."""
    if state.equity <= 0:
        return SizingResult(0, 0.0, "VETO_NO_EQUITY", "account equity is zero or negative")

    distance = intent.stop_distance
    if distance <= 0:
        return SizingResult(
            0, 0.0, "VETO_INVALID_STOP_DISTANCE",
            f"entry {intent.entry} and stop {intent.stop} give a stop distance of zero",
        )

    budget = state.equity * policy.RISK_PER_TRADE
    raw = math.floor(budget / distance)
    if raw <= 0:
        return SizingResult(
            0, 0.0, "VETO_SIZE_ROUNDS_TO_ZERO",
            f"${budget:,.2f} risk budget buys less than one share at a "
            f"${distance:,.2f} stop distance",
        )

    qty = raw
    caps: list[str] = []

    # Circuit-breaker multiplier comes first so later caps see the reduced size.
    if multiplier != 1.0:
        reduced = math.floor(qty * multiplier)
        if reduced < qty:
            qty = reduced
            caps.append(f"breaker_multiplier_{multiplier}")

    # Buying power
    affordable = math.floor(state.buying_power / intent.entry) if intent.entry > 0 else 0
    if affordable < qty:
        qty = affordable
        caps.append("buying_power")

    # Single-position concentration
    max_value = state.equity * policy.MAX_CONCENTRATION
    existing = state.open_positions.get(intent.symbol, 0.0)
    room = max_value - existing
    by_concentration = math.floor(room / intent.entry) if intent.entry > 0 else 0
    if by_concentration < qty:
        qty = max(0, by_concentration)
        caps.append("concentration")

    # Total open risk across every live stop
    risk_room = state.equity * policy.MAX_OPEN_RISK - state.open_risk
    by_open_risk = math.floor(risk_room / distance) if distance > 0 else 0
    if by_open_risk < qty:
        qty = max(0, by_open_risk)
        caps.append("open_risk")

    if qty <= 0:
        return SizingResult(
            0, 0.0, "VETO_NO_ROOM",
            f"caps reduced quantity to zero ({', '.join(caps) or 'none'})",
            caps, raw,
        )

    # Recompute planned loss after rounding and costs, then re-check the ceiling.
    planned_loss = qty * (distance + cost_per_share)
    if planned_loss > budget:
        qty = math.floor(budget / (distance + cost_per_share))
        caps.append("cost_adjusted")
        if qty <= 0:
            return SizingResult(
                0, 0.0, "VETO_COSTS_EXCEED_BUDGET",
                "estimated costs push planned loss past the 1% ceiling at any size",
                caps, raw,
            )
        planned_loss = qty * (distance + cost_per_share)

    return SizingResult(qty, planned_loss, caps_applied=caps, raw_quantity=raw)
