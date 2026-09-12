"""What a trade actually costs.

The single most common way a backtest lies is by filling at the closing price
with no commission, no spread and no impact. Every fill in this package goes
through `CostModel`, and the harness refuses to report a result that was
produced with `CostModel.zero()` unless it is explicitly labelled as such.

Costs are expressed per share so they compose with `trading.sizing`, which
already accepts a `cost_per_share` and re-checks the 1% ceiling after adding it.
"""

from __future__ import annotations

from dataclasses import dataclass

BPS = 1e-4


@dataclass(frozen=True)
class CostModel:
    """Per-share cost of crossing the spread once.

    commission_per_share  broker's per-share charge
    commission_min        floor per order, spread over the order's shares
    half_spread_bps       half the quoted bid-ask, in basis points of price
    slippage_bps          market impact + queue position, in basis points
    annual_borrow_rate    cost of holding a short, charged daily on notional
    """

    commission_per_share: float = 0.005
    commission_min: float = 1.00
    half_spread_bps: float = 2.0
    slippage_bps: float = 3.0
    annual_borrow_rate: float = 0.03

    # A retail-realistic default for liquid US equities and ETFs.
    @classmethod
    def retail(cls) -> "CostModel":
        return cls()

    @classmethod
    def zero(cls) -> "CostModel":
        """Frictionless. Only for isolating the effect of costs in a test."""
        return cls(0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def is_frictionless(self) -> bool:
        return (
            self.commission_per_share == 0.0
            and self.commission_min == 0.0
            and self.half_spread_bps == 0.0
            and self.slippage_bps == 0.0
        )

    def per_share(self, price: float, quantity: int = 1) -> float:
        """Realised cost of one share on one side, for an order of `quantity`.

        The commission minimum is an order-level fixed cost, so it is spread
        over the order. At quantity=1 this returns the worst case, which is
        correct for reporting and wrong for planning -- see `marginal_per_share`.
        """
        if price <= 0:
            raise ValueError("price must be positive")
        qty = max(1, int(quantity))
        commission = max(self.commission_per_share * qty, self.commission_min) / qty
        return commission + price * (self.half_spread_bps + self.slippage_bps) * BPS

    def marginal_per_share(self, price: float) -> float:
        """Cost of one *additional* share, one side. Independent of order size.

        This is the number to plan with, and the distinction matters. The
        decision layer is not allowed to know the order quantity -- sizing owns
        that -- so it cannot amortise the commission minimum, and charging the
        whole $1 floor to a single share overstates the per-share cost of a
        $376 ETF by roughly five times. Planning on that figure rejects
        perfectly tradable instruments.

        Spread and slippage are genuinely proportional and are charged in full;
        only the fixed floor is excluded, because it is recovered at order
        level by `commission()` when the fill is actually priced.
        """
        if price <= 0:
            raise ValueError("price must be positive")
        return self.commission_per_share + price * (self.half_spread_bps + self.slippage_bps) * BPS

    def round_trip_per_share(self, price: float, quantity: int = 1) -> float:
        """Both sides, realised. Worst case at quantity=1."""
        return 2.0 * self.per_share(price, quantity)

    def round_trip_marginal(self, price: float) -> float:
        """Both sides, size-independent. What planning and sizing should use."""
        return 2.0 * self.marginal_per_share(price)

    def fill_price(self, price: float, buying: bool, quantity: int = 1) -> float:
        """Where the order actually fills: always worse than the mid.

        Spread and slippage move the price against you. Commission is charged
        separately because it is not a price effect.
        """
        drift = price * (self.half_spread_bps + self.slippage_bps) * BPS
        return price + drift if buying else price - drift

    def commission(self, price: float, quantity: int) -> float:
        """Total commission on an order, in dollars."""
        if quantity <= 0:
            return 0.0
        return max(self.commission_per_share * quantity, self.commission_min)

    def daily_borrow(self, notional: float) -> float:
        return abs(notional) * self.annual_borrow_rate / 252.0


RETAIL = CostModel.retail()
