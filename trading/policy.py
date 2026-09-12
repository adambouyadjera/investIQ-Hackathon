"""The risk constitution. Thresholds live here as constants and nowhere else.

Three rules govern this file:

1. No strategy imports it to modify it. It is read-only to everything upstream.
2. No AI text decides whether a line has been crossed. These are `<=` and `<`
   comparisons on floats, and the boundary tests below pin the exact behavior.
3. When two breakers are active, the strictest wins. Never the most recent,
   never the average.

The thresholds themselves come from the build guide's cascade table.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .types import Action, AccountState, SEVERITY

# ── Constants ────────────────────────────────────────────────────────────────

RISK_PER_TRADE = 0.01          # 1% of current equity, max planned loss

DAILY_HALF_SIZE = -0.02        # at or below -2% in a day  -> half size
DAILY_FLATTEN = -0.03          # strictly below -3%        -> flatten
WEEKLY_HALF_SIZE = -0.05       # at or below -5% in a week -> half size
WEEKLY_STOP = -0.06            # at or below -6%           -> no new entries
MONTHLY_STOP = -0.10           # at or below -10%          -> no new entries
PEAK_DRAWDOWN_BLOCK = -0.10    # at or below -10% from peak-> full stop

MAX_CONCENTRATION = 0.50       # one position as a share of equity
MAX_OPEN_RISK = 0.06           # summed planned loss across all live stops
MAX_POSITIONS = 8
MIN_RISK_REWARD = 2.0          # reward at target_2, in R

BLOCK_FILE = Path("state/TRADING_BLOCKED")


# ── Breaker evaluation ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Breaker:
    name: str
    action: Action
    detail: str


def evaluate_breakers(
    state: AccountState, block_file: Path | None = BLOCK_FILE
) -> list[Breaker]:
    """Every currently active breaker, in no particular order.

    `block_file=None` means this evaluation has no persistent desk behind
    it — a what-if scenario rather than a live account. The drawdown rule
    still fires; it just has no file to consult or create.
    """
    active: list[Breaker] = []

    if block_file is not None and block_file.exists():
        active.append(Breaker(
            "peak_drawdown_block", Action.BLOCKED,
            f"{block_file} present — only a human can remove it",
        ))

    dd = state.drawdown_pct
    if dd <= PEAK_DRAWDOWN_BLOCK:
        active.append(Breaker(
            "peak_drawdown", Action.BLOCKED,
            f"down {dd:.2%} from peak equity of ${state.peak_equity:,.2f}",
        ))

    day = state.daily_pct
    if day < DAILY_FLATTEN:
        active.append(Breaker("daily_flatten", Action.FLATTEN, f"down {day:.2%} today"))
    elif day <= DAILY_HALF_SIZE:
        active.append(Breaker("daily_half_size", Action.HALF_SIZE, f"down {day:.2%} today"))

    week = state.weekly_pct
    if week <= WEEKLY_STOP:
        active.append(Breaker("weekly_stop", Action.NO_NEW_ENTRIES, f"down {week:.2%} this week"))
    elif week <= WEEKLY_HALF_SIZE:
        active.append(Breaker("weekly_half_size", Action.HALF_SIZE, f"down {week:.2%} this week"))

    month = state.monthly_pct
    if month <= MONTHLY_STOP:
        active.append(Breaker("monthly_stop", Action.NO_NEW_ENTRIES, f"down {month:.2%} this month"))

    return active


def strictest(breakers: list[Breaker]) -> Action:
    """Collision rule: flatten beats stop-new-entries beats half size."""
    if not breakers:
        return Action.NORMAL
    return max((b.action for b in breakers), key=lambda a: SEVERITY[a])


def size_multiplier(action: Action) -> float:
    """How an active breaker scales a computed quantity."""
    return 0.5 if action is Action.HALF_SIZE else 1.0


def blocks_new_entries(action: Action) -> bool:
    return SEVERITY[action] >= SEVERITY[Action.NO_NEW_ENTRIES]


# ── Block file ───────────────────────────────────────────────────────────────

def write_block(
    state: AccountState, rule: str, block_file: Path | None = BLOCK_FILE
) -> Path | None:
    """Persist the stop. Deliberately has no counterpart `clear_block()`.

    Returns None when there is no persistent desk (block_file=None). A
    stateless what-if must never leave a real block behind — doing so once
    wedged every subsequent request until the file was removed by hand.
    """
    if block_file is None:
        return None
    block_file.parent.mkdir(parents=True, exist_ok=True)
    block_file.write_text(
        f"TRADING BLOCKED\n"
        f"rule: {rule}\n"
        f"at: {state.as_of.isoformat()}\n"
        f"equity: {state.equity:.2f}\n"
        f"peak_equity: {state.peak_equity:.2f}\n"
        f"drawdown: {state.drawdown_pct:.4%}\n"
        f"open_positions: {len(state.open_positions)}\n\n"
        f"No program may remove this file. Complete a written review, then\n"
        f"delete it by hand and restart in paper mode at half size.\n"
    )
    return block_file


def policy_hash() -> str:
    """Fingerprint of this file, logged at startup so silent edits are visible."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
