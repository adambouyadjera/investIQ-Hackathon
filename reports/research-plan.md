# BTC research desk — preregistered first session

Research began: 2026-09-12 15:50 UTC. Initial research deadline: 16:50 UTC.
Paper execution implementation follows this first research session.

## Scope and assumptions

10,000 USDT simulated account, long-only BTC/USDT spot, no borrowing or leverage.
Bybit direct market API is geographically unavailable from this machine. Use the
accessible, documented Binance public market-data API for local research. This
is a different venue and instrument from the earlier Trader.dev perpetual test.
No exchange account or execution permission is required for public data.
Trader.dev reported 999 credits; its reset date is malformed. No credit purchases.
Until the user changes the budget, at most one Trader.dev credit per hourly run.

## Data and splits, fixed before viewing returns

Fetch hourly BTCUSDT OHLCV from 2022-01-01 through the last completed hour.
Use 2022–2024 for development, 2025-01-01–2026-03-31 for validation,
and 2026-04-01 onward as a sealed final holdout. Do not select parameters from
the final holdout. Once used, this period must be labelled previously inspected.
Use hourly and four-hour signals computed only from completed bars. Reject
missing/duplicate/nonfinite bars, future timestamps, and OHLC inconsistencies.
Cache source data with content hashes and request metadata. No synthetic filling.

## Bounded search

Compare trend crossover, channel breakout, and trend-filtered RSI pullback families.
Freeze a modest grid before evaluating it. Include cash and buy-and-hold benchmarks.
Select using development performance and multiple chronological subperiods;
use validation as an acceptance check. Log every attempted configuration.
Do not keep searching until the historical holdout happens to pass.

## Research execution model

Signals at a completed bar lead to entry at the next bar open; exits use the same
lag unless a resting stop/target is hit. Charge 10 basis points of commission and
5 basis points slippage per side as explicit modelling assumptions, not a quote
of this user's actual fee tier. Stress test doubled costs. Spot has no perpetual
funding. Risk no more than 0.5% equity per trade, cap BTC exposure at 50% equity,
use an ATR stop, and a 10% peak drawdown latch. Assume the stop fills first if both
stop and target could be touched inside a candle. Gaps fill at the worse opening
price. Model costs and adverse intrabar excursions; a stop is not a loss guarantee.

## Acceptance, fixed before results

At least 30 completed validation trades and 15 final holdout trades; positive net
return and profit factor >=1.10 in both validation and holdout; maximum marked
intrabar drawdown <10%; positive validation return under doubled costs; positive
returns in a majority of validation calendar quarters. Report sampling uncertainty,
parameter sensitivity, and buy-and-hold comparison. Passing is permission for a
paper experiment, never proof of future profitability. If none passes, stay in cash.

## Sources

- https://developers.binance.com/en/docs/products/spot/rest-api (public data API)
- https://github.com/binance/binance-public-data (archive format and checksums)
- https://bybit-exchange.github.io/docs/v5/market/kline (Bybit candle semantics)
- https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf (multiple testing risk)
- https://learn.chatgpt.com/docs/automations (local hourly scheduling requirements)

## User amendment
The user relaxed the one-hour deadline and requested free research with priority on integration into the supplied InvestIQ website. All future research uses free public data and local calculations; Trader.dev credits and paid APIs are disabled. Initial candidate failed validation, so the final holdout remains sealed.
