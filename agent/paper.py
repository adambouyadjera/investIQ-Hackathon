"""A simulated broker. There is no live mode, and adding one is not a setting.

`LIVE_TRADING_SUPPORTED` is False and nothing reads it as a switch -- it exists
so the answer is greppable. There is no credential, no order endpoint and no
network import anywhere in this package, and
`test_agent.py::no_broker_imports_anywhere` walks every module and fails if one
appears, extending the same test that already guards `trading/`.

Modelling choices that make the equity curve honest rather than flattering:

* **Fills cross the spread.** `CostModel.fill_price` moves every fill against
  the order, and commission is charged on top. Nothing fills at the mid.
* **Stops fill at the close, not at the stop price.** Daily closes are all the
  data there is, so an intrabar touch is unobservable. Assuming a fill at the
  stop price would silently hand the backtest a guaranteed exit at a level that
  a gapping market would never have given it. Filling at the close that broke
  the level is worse, which is the correct direction for an unobservable.
* **A signal on bar `t` is acted on at bar `t+1`.** Enforced by the harness,
  which passes yesterday's proposal to today's `open_position`.
* **Shorts pay borrow daily**, and are marked with the same adverse fills.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from trading.protection import break_even_stop, partial_exit_plan
from trading.types import AccountState, OrderIntent, Side

from .costs import CostModel

LIVE_TRADING_SUPPORTED = False


@dataclass(frozen=True)
class Fill:
    date: pd.Timestamp
    symbol: str
    side: str            # "buy" | "sell" | "short" | "cover"
    quantity: int
    price: float         # after spread and slippage
    reference: float     # the close it was derived from
    commission: float
    reason: str

    @property
    def slippage_cost(self) -> float:
        return abs(self.price - self.reference) * self.quantity

    def to_dict(self) -> dict:
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": round(self.price, 4),
            "reference_close": round(self.reference, 4),
            "commission": round(self.commission, 2),
            "slippage_cost": round(self.slippage_cost, 2),
            "reason": self.reason,
        }


@dataclass
class Position:
    symbol: str
    side: Side
    quantity: int
    entry_price: float       # actual fill, not the signal close
    stop: float
    target_1: float
    target_2: float
    opened: pd.Timestamp
    strategy: str
    took_partial: bool = False
    entry_cost: float = 0.0  # commission paid to get in

    @property
    def is_long(self) -> bool:
        return self.side is Side.LONG

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def unrealized(self, price: float) -> float:
        d = price - self.entry_price
        return self.quantity * (d if self.is_long else -d)

    def planned_loss(self) -> float:
        return self.quantity * abs(self.entry_price - self.stop)

    def stop_breached(self, close: float) -> bool:
        return close <= self.stop if self.is_long else close >= self.stop

    def target_1_reached(self, close: float) -> bool:
        return close >= self.target_1 if self.is_long else close <= self.target_1

    def target_2_reached(self, close: float) -> bool:
        return close >= self.target_2 if self.is_long else close <= self.target_2


@dataclass
class ClosedTrade:
    symbol: str
    side: str
    opened: pd.Timestamp
    closed: pd.Timestamp
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float            # net of all costs
    costs: float
    reason: str
    strategy: str

    @property
    def holding_days(self) -> int:
        return int((self.closed - self.opened).days)

    @property
    def r_multiple_basis(self) -> float:
        return abs(self.entry_price - self.exit_price)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "opened": self.opened.strftime("%Y-%m-%d"),
            "closed": self.closed.strftime("%Y-%m-%d"),
            "holding_days": self.holding_days,
            "quantity": self.quantity,
            "entry_price": round(self.entry_price, 4),
            "exit_price": round(self.exit_price, 4),
            "pnl": round(self.pnl, 2),
            "costs": round(self.costs, 2),
            "reason": self.reason,
            "strategy": self.strategy,
        }


class PaperBroker:
    """Cash, positions and an equity curve. Simulation only."""

    def __init__(self, initial_cash: float = 100_000.0, costs: CostModel = CostModel.retail()):
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.costs = costs

        self.positions: Dict[str, Position] = {}
        self.fills: List[Fill] = []
        self.closed: List[ClosedTrade] = []

        self.equity_dates: List[pd.Timestamp] = []
        self.equity_values: List[float] = []

        self.peak_equity = float(initial_cash)
        self._day_start = float(initial_cash)
        self._week_start = float(initial_cash)
        self._month_start = float(initial_cash)
        self._last_date: Optional[pd.Timestamp] = None
        self.total_costs = 0.0
        self.borrow_paid = 0.0

    # ── State ────────────────────────────────────────────────────────────────

    def equity(self, prices: pd.Series) -> float:
        held = sum(p.market_value(float(prices[p.symbol])) if p.is_long
                   else -p.market_value(float(prices[p.symbol]))
                   for p in self.positions.values())
        return self.cash + held

    def _exposure(self, prices: pd.Series) -> Dict[str, float]:
        return {
            p.symbol: abs(p.market_value(float(prices[p.symbol])))
            for p in self.positions.values()
        }

    def account_state(self, date: pd.Timestamp, prices: pd.Series) -> AccountState:
        """The reconciled state the risk gate demands.

        `as_of` is stamped with the wall clock rather than the bar date because
        `trading.checks` vetoes state older than five minutes -- a freshness
        rule written for a live desk. In a backtest the bar date is always
        years stale, so the honest translation of "this state is current" is
        the current time. The rule is still exercised; it is just not being
        asked a question about the past that it was not written to answer.
        """
        eq = self.equity(prices)
        return AccountState(
            equity=eq,
            peak_equity=max(self.peak_equity, eq),
            buying_power=max(0.0, self.cash),
            day_start_equity=self._day_start,
            week_start_equity=self._week_start,
            month_start_equity=self._month_start,
            open_positions=self._exposure(prices),
            open_risk=sum(p.planned_loss() for p in self.positions.values()),
            as_of=datetime.now(timezone.utc),
        )

    # ── Marking ──────────────────────────────────────────────────────────────

    def mark(self, date: pd.Timestamp, prices: pd.Series) -> float:
        """Roll baselines, charge borrow, and record the day's equity."""
        date = pd.Timestamp(date)

        if self._last_date is not None:
            prev = self._last_date
            eq_before = self.equity_values[-1] if self.equity_values else self.initial_cash
            if date.date() != prev.date():
                self._day_start = eq_before
            if date.isocalendar()[1] != prev.isocalendar()[1] or date.year != prev.year:
                self._week_start = eq_before
            if (date.year, date.month) != (prev.year, prev.month):
                self._month_start = eq_before

        for p in self.positions.values():
            if not p.is_long:
                charge = self.costs.daily_borrow(p.market_value(float(prices[p.symbol])))
                self.cash -= charge
                self.borrow_paid += charge
                self.total_costs += charge

        eq = self.equity(prices)
        self.peak_equity = max(self.peak_equity, eq)
        self.equity_dates.append(date)
        self.equity_values.append(eq)
        self._last_date = date
        return eq

    # ── Orders ───────────────────────────────────────────────────────────────

    def open_position(
        self, date: pd.Timestamp, intent: OrderIntent, quantity: int, close: float
    ) -> Optional[Fill]:
        """Enter at `close`, adjusted for spread, slippage and commission."""
        if quantity <= 0:
            return None
        if intent.symbol in self.positions:
            return None

        buying = intent.side is Side.LONG
        price = self.costs.fill_price(close, buying, quantity)
        commission = self.costs.commission(close, quantity)
        notional = price * quantity

        if buying and notional + commission > self.cash:
            return None

        self.cash += (-notional if buying else notional) - commission
        self.total_costs += commission

        # The stop travels with the fill, not the signal price: entering 3c
        # worse than the close must not quietly widen the risk on the position.
        drift = price - close
        self.positions[intent.symbol] = Position(
            symbol=intent.symbol,
            side=intent.side,
            quantity=quantity,
            entry_price=price,
            stop=intent.stop + drift,
            target_1=intent.target_1 + drift,
            target_2=intent.target_2 + drift,
            opened=pd.Timestamp(date),
            strategy=intent.strategy,
            entry_cost=commission,
        )

        fill = Fill(pd.Timestamp(date), intent.symbol, "buy" if buying else "short",
                    quantity, price, close, commission, "entry")
        self.fills.append(fill)
        return fill

    def _exit(
        self, date: pd.Timestamp, pos: Position, quantity: int, close: float, reason: str
    ) -> Fill:
        selling = pos.is_long
        price = self.costs.fill_price(close, not selling, quantity)
        commission = self.costs.commission(close, quantity)
        notional = price * quantity

        self.cash += (notional if selling else -notional) - commission
        self.total_costs += commission

        d = price - pos.entry_price
        gross = quantity * (d if pos.is_long else -d)
        share_of_entry = pos.entry_cost * (quantity / pos.quantity) if pos.quantity else 0.0

        self.closed.append(ClosedTrade(
            symbol=pos.symbol,
            side=pos.side.value,
            opened=pos.opened,
            closed=pd.Timestamp(date),
            quantity=quantity,
            entry_price=pos.entry_price,
            exit_price=price,
            pnl=gross - commission - share_of_entry,
            costs=commission + share_of_entry,
            reason=reason,
            strategy=pos.strategy,
        ))

        fill = Fill(pd.Timestamp(date), pos.symbol, "sell" if selling else "cover",
                    quantity, price, close, commission, reason)
        self.fills.append(fill)
        return fill

    def close_position(
        self, date: pd.Timestamp, symbol: str, close: float, reason: str
    ) -> Optional[Fill]:
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        fill = self._exit(date, pos, pos.quantity, close, reason)
        del self.positions[symbol]
        return fill

    def flatten_all(self, date: pd.Timestamp, prices: pd.Series, reason: str) -> List[Fill]:
        out = []
        for symbol in list(self.positions):
            f = self.close_position(date, symbol, float(prices[symbol]), reason)
            if f:
                out.append(f)
        return out

    # ── Per-bar exit processing ──────────────────────────────────────────────

    def process_exits(self, date: pd.Timestamp, prices: pd.Series) -> List[Fill]:
        """Stops first, then targets. Order matters on a bar that does both.

        When a close is beyond both the stop and a target, the stop wins. Only
        the two endpoints of the bar are observable, so the path between them
        is unknown, and resolving an ambiguous bar in the loss's favour is the
        only assumption that cannot flatter the result.
        """
        out: List[Fill] = []

        for symbol in list(self.positions):
            pos = self.positions[symbol]
            close = float(prices[symbol])

            if pos.stop_breached(close):
                f = self.close_position(date, symbol, close,
                                        "stop" if not pos.took_partial else "stop_after_partial")
                if f:
                    out.append(f)
                continue

            if pos.target_2_reached(close):
                f = self.close_position(date, symbol, close, "target_2")
                if f:
                    out.append(f)
                continue

            if not pos.took_partial and pos.target_1_reached(close):
                first, _ = partial_exit_plan(pos.quantity)
                if first > 0:
                    out.append(self._exit(date, pos, first, close, "target_1_partial"))
                    pos.quantity -= first
                    pos.entry_cost *= (pos.quantity / (pos.quantity + first))
                pos.took_partial = True
                # Never widens: break-even is always tighter than the original
                # stop, in both directions.
                pos.stop = break_even_stop(pos.entry_price)

        return out

    # ── Results ──────────────────────────────────────────────────────────────

    def equity_curve(self) -> pd.Series:
        return pd.Series(self.equity_values, index=pd.DatetimeIndex(self.equity_dates),
                         name="equity")

    def returns(self) -> pd.Series:
        return self.equity_curve().pct_change().dropna()

    def stats(self) -> dict:
        curve = self.equity_curve()
        final = float(curve.iloc[-1]) if len(curve) else self.initial_cash
        wins = [t for t in self.closed if t.pnl > 0]
        losses = [t for t in self.closed if t.pnl <= 0]
        gross_win = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        return {
            "initial_cash": round(self.initial_cash, 2),
            "final_equity": round(final, 2),
            "net_profit": round(final - self.initial_cash, 2),
            "return_pct": round(final / self.initial_cash - 1.0, 6),
            "closed_trades": len(self.closed),
            "win_rate": round(len(wins) / len(self.closed), 4) if self.closed else 0.0,
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
            "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
            "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
            "total_costs": round(self.total_costs, 2),
            "borrow_paid": round(self.borrow_paid, 2),
            "cost_drag_pct": round(self.total_costs / self.initial_cash, 6),
            "open_positions": len(self.positions),
            "live_trading_supported": LIVE_TRADING_SUPPORTED,
        }
