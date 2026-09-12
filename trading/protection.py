"""Protective order rules.

Two invariants:
  * An entry without a stop and both targets is not a valid entry.
  * A stop may tighten. It may never widen. This is the rule that stops a
    losing position from quietly becoming a much larger losing position.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import policy
from .types import OrderIntent, Side


@dataclass(frozen=True)
class ProtectionCheck:
    valid: bool
    code: str = ""
    reason: str = ""


def validate(intent: OrderIntent, cost_per_share: float = 0.0) -> ProtectionCheck:
    """Geometry and reward checks on a proposal."""
    if intent.stop_distance <= 0:
        return ProtectionCheck(False, "VETO_INVALID_STOP_DISTANCE", "stop equals entry")

    if intent.side is Side.LONG:
        if intent.stop >= intent.entry:
            return ProtectionCheck(
                False, "VETO_STOP_WRONG_SIDE", "long stop must sit below entry")
        if not (intent.entry < intent.target_1 < intent.target_2):
            return ProtectionCheck(
                False, "VETO_TARGETS_UNORDERED",
                "long targets must rise above entry, target_1 then target_2")
    else:
        if intent.stop <= intent.entry:
            return ProtectionCheck(
                False, "VETO_STOP_WRONG_SIDE", "short stop must sit above entry")
        if not (intent.entry > intent.target_1 > intent.target_2):
            return ProtectionCheck(
                False, "VETO_TARGETS_UNORDERED",
                "short targets must fall below entry, target_1 then target_2")

    # Reward measured after costs, in R.
    effective_risk = intent.stop_distance + cost_per_share
    reward = abs(intent.target_2 - intent.entry) - cost_per_share
    rr = reward / effective_risk if effective_risk > 0 else 0.0
    if rr < policy.MIN_RISK_REWARD:
        return ProtectionCheck(
            False, "VETO_INSUFFICIENT_REWARD",
            f"{rr:.2f}R after costs is below the {policy.MIN_RISK_REWARD:.1f}R minimum",
        )

    return ProtectionCheck(True)


def can_replace_stop(side: Side, entry: float, current_stop: float, new_stop: float) -> ProtectionCheck:
    """Tightening allowed, widening refused."""
    if side is Side.LONG:
        widening = new_stop < current_stop
    else:
        widening = new_stop > current_stop

    if widening:
        return ProtectionCheck(
            False, "VETO_STOP_WIDENING",
            f"moving the stop from {current_stop} to {new_stop} increases risk",
        )
    return ProtectionCheck(True)


def partial_exit_plan(quantity: int) -> tuple[int, int]:
    """Close about half at target_1, hold the rest for target_2.

    Odd sizes round the first tranche down so the runner is never short-changed.
    """
    first = quantity // 2
    return first, quantity - first


def break_even_stop(entry: float) -> float:
    """After the target_1 partial confirms, the remaining stop moves to entry."""
    return entry
