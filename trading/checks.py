"""The pre-trade gate.

Checks run in a fixed order and stop at the first veto, but every completed
result is kept so the journal shows exactly how far a proposal got.

Nothing here silently passes on missing data. An absent value is a veto, not a
default — that is the difference between a risk system and a suggestion.

This module is import-safe from anywhere. It has no broker client, and by
design it cannot acquire one.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from . import policy, protection, sizing
from .types import AccountState, Action, CheckResult, OrderIntent, RiskDecision, utcnow

MAX_STATE_AGE = timedelta(minutes=5)
REGIME_STABILITY_BARS = 3
VALID_REGIMES = {"calm", "volatile", "bear"}


def evaluate(
    intent: OrderIntent,
    state: AccountState,
    *,
    regime: str,
    regime_stability: int,
    strategy_permitted: bool,
    bar_closed: bool,
    cost_per_share: float = 0.0,
    block_file: Path | None = policy.BLOCK_FILE,
) -> RiskDecision:
    """Run the gate. Returns a cleared decision with a quantity, or a veto."""
    checks: list[CheckResult] = []

    def record(name: str, passed: bool, code: str, reason: str = "", **inputs) -> bool:
        checks.append(CheckResult(name, passed, code, reason, inputs))
        return passed

    def veto(code: str, reason: str, breakers: list[str] | None = None) -> RiskDecision:
        return RiskDecision(
            approved=False, veto_code=code, veto_reason=reason,
            checks=checks, active_breakers=breakers or [],
        )

    # 1. Block state. None = stateless what-if; there is no desk to block.
    if block_file is not None and block_file.exists():
        record("block_state", False, "VETO_TRADING_BLOCKED", str(block_file))
        return veto("VETO_TRADING_BLOCKED",
                    f"{block_file} exists; a human must review and remove it")
    record("block_state", True, "OK" if block_file is not None
           else "OK_NO_PERSISTENT_STATE")

    # 2. Fresh data
    age = utcnow() - state.as_of
    if age > MAX_STATE_AGE:
        record("fresh_state", False, "VETO_STALE_STATE", f"state is {age} old")
        return veto("VETO_STALE_STATE", f"account state is {age} old; fail closed")
    record("fresh_state", True, "OK", age_seconds=age.total_seconds())

    # 3. Closed bar
    if not bar_closed:
        record("closed_bar", False, "VETO_UNFINISHED_BAR", "signal came from a live bar")
        return veto("VETO_UNFINISHED_BAR",
                    "signal derived from an unfinished candle")
    record("closed_bar", True, "OK")

    # 4. Regime validity and stability
    if regime not in VALID_REGIMES:
        record("regime_known", False, "VETO_UNKNOWN_REGIME", regime)
        return veto("VETO_UNKNOWN_REGIME", f"regime {regime!r} is not a known label")
    if regime_stability < REGIME_STABILITY_BARS:
        record("regime_stable", False, "VETO_REGIME_UNSTABLE",
               f"{regime_stability}/{REGIME_STABILITY_BARS} bars")
        return veto("VETO_REGIME_UNSTABLE",
                    f"regime has held {regime_stability} of {REGIME_STABILITY_BARS} bars")
    record("regime_stable", True, "OK", regime=regime, bars=regime_stability)

    # 5. Strategy permission for this regime
    if not strategy_permitted:
        record("strategy_permitted", False, "VETO_STRATEGY_NOT_PERMITTED",
               f"{intent.strategy} is not validated for {regime}")
        return veto("VETO_STRATEGY_NOT_PERMITTED",
                    f"{intent.strategy} has no passing unseen window for {regime}")
    record("strategy_permitted", True, "OK")

    # 6. Protective geometry and reward
    prot = protection.validate(intent, cost_per_share)
    if not prot.valid:
        record("protection", False, prot.code, prot.reason)
        return veto(prot.code, prot.reason)
    record("protection", True, "OK", risk_reward=round(intent.risk_reward, 2))

    # 7. Circuit breakers
    breakers = policy.evaluate_breakers(state, block_file)
    names = [b.name for b in breakers]
    action = policy.strictest(breakers)

    if action is Action.BLOCKED:
        record("breakers", False, "VETO_MAX_DRAWDOWN", f"drawdown {state.drawdown_pct:.2%}")
        policy.write_block(state, "peak_drawdown", block_file)
        return veto("VETO_MAX_DRAWDOWN",
                    f"down {state.drawdown_pct:.2%} from peak; block file written", names)
    if action is Action.FLATTEN:
        record("breakers", False, "VETO_FLATTEN_DAY", f"daily {state.daily_pct:.2%}")
        return veto("VETO_FLATTEN_DAY",
                    f"down {state.daily_pct:.2%} today; close everything", names)
    if policy.blocks_new_entries(action):
        record("breakers", False, "VETO_NO_NEW_ENTRIES", ", ".join(names))
        return veto("VETO_NO_NEW_ENTRIES",
                    f"active breaker: {', '.join(names)}", names)
    record("breakers", True, "OK", active=names, action=action.value)

    # 8. Position count
    if intent.symbol not in state.open_positions and \
            len(state.open_positions) >= policy.MAX_POSITIONS:
        record("position_count", False, "VETO_TOO_MANY_POSITIONS",
               f"{len(state.open_positions)} open")
        return veto("VETO_TOO_MANY_POSITIONS",
                    f"already holding {len(state.open_positions)} positions", names)
    record("position_count", True, "OK", open=len(state.open_positions))

    # 9. Size it
    result = sizing.calculate(intent, state, policy.size_multiplier(action), cost_per_share)
    if not result.ok:
        record("sizing", False, result.veto_code, result.veto_reason)
        return veto(result.veto_code, result.veto_reason, names)
    record("sizing", True, "OK", quantity=result.quantity,
           raw=result.raw_quantity, caps=result.caps_applied)

    # 10. Final ceiling re-check after every reduction
    ceiling = state.equity * policy.RISK_PER_TRADE
    if result.planned_loss > ceiling + 1e-9:
        record("final_ceiling", False, "VETO_EXCEEDS_RISK_CEILING",
               f"${result.planned_loss:,.2f} > ${ceiling:,.2f}")
        return veto("VETO_EXCEEDS_RISK_CEILING",
                    f"planned loss ${result.planned_loss:,.2f} exceeds the 1% ceiling", names)
    record("final_ceiling", True, "OK",
           planned_loss=round(result.planned_loss, 2), ceiling=round(ceiling, 2))

    return RiskDecision(
        approved=True,
        quantity=result.quantity,
        planned_loss=result.planned_loss,
        checks=checks,
        active_breakers=names,
    )
