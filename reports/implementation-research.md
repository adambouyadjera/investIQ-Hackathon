# Website integration design from research findings

This is the existing InvestIQ React/FastAPI website, not a new hosted site.
Add an authenticated Research desk page at /research and navigation beside Risk desk.
No source credentials from the ZIP should enter the delivered project.

## What the user should see

- BTC/USDT spot, free research, paper mode, and the actual age of market data.
- Separate development and validation results. Missing validation is shown as
  untested, not zero. Never style a development winner as a proven strategy.
- Six selected validation candidates, their base/stressed returns, drawdown,
  completed trades, profit factor, and failed checks.
- A cash-only decision while no candidate passes. The final holdout stays sealed.
- Per-user paper balance, exposure, open position, event history, and start/pause/
  close controls. Starting monitoring does not bypass strategy qualification.
- A research journal with the complete test count and reasons for rejection.
- Cost assumptions next to the results and a clear spot/futures distinction.

## Operational design

The hourly Codex heartbeat researches and edits hypotheses using the existing
account allowance. It makes no paid model/API calls from the website. The
website's local scheduler monitors paper accounts and public BTC data while the
backend is running. Public deployment is not part of this request. A future
hosted service requires a persistent worker and durable storage; a static page
alone cannot run a trading bot.

Per-user state lives under state/accounts/<authenticated-user-uuid>, with file
locking and atomic replacement. Public research reports are shared; paper
balances and control actions are isolated. The execution module exposes no live
exchange endpoints and accepts no broker credentials.

Research backtests fill at next bar open, while paper orders fill at the price
actually observed when the service runs. Record that difference. Model resting
stops on fully observed bars after entry; never retroactively use the high/low
from before an intrabar paper entry. A stale or malformed data feed must prevent
new entries. A 10% drawdown stop stays latched; there is no UI override.

## Evidence needed before delivery

- Original 42 risk tests and portfolio/API checks relevant to the integration.
- No-lookahead and training-label-purge tests for linear and nonlinear models.
- Paper account isolation, risk sizing, ledger reconciliation, duplicate-bar
  prevention, restart persistence, stale-data veto, and pause/close behaviour.
- Auth-required API responses, multi-user isolation, and error-state handling.
- Frontend production build and browser inspection of desktop/mobile layout.
- Working local preview and packaged source without node_modules, virtualenv,
  secrets, or personal paper-account state.
