"""InvestIQ paper-trading research desk.

A transparent, simulation-only agent. It scores a fixed set of quantitative
features plus news sentiment into a single explainable number, proposes trades
that the existing `trading/` risk gate is free to refuse, fills them through a
paper broker that charges realistic costs, and reports the result against a
buy-and-hold benchmark with a multiple-testing penalty applied.

There is no live mode. `agent.paper.LIVE_TRADING_SUPPORTED` is False, there is
no broker client or credential anywhere in the package, and a test walks every
module to keep it that way.

Educational simulation. Not financial advice.
"""

__version__ = "0.1.0"

LIVE_TRADING_SUPPORTED = False
