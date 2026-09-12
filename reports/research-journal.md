# InvestIQ BTC research journal

Initial research window: September 12, 2026, 15:50–17:50 UTC (two hours requested).
Status: initial two-hour study complete; hourly follow-up active. Work is local and uses free public market data. No paid APIs,
Trader.dev backtest credits, exchange orders, or external alert subscriptions.

## Protocol and data

The original InvestIQ archive is a portfolio simulator with a separate tested risk
layer. Its 42 risk tests pass. This work adds BTC research without changing those
existing modules. Cryptocurrency sizing uses fractional quantities; the original
whole-share sizing is unsuitable for BTC.

Data source is Binance BTCUSDT spot, not Bybit perpetual futures. The direct
Bybit market endpoint is geographically unavailable from this machine. The
previous Trader.dev perpetual baseline is therefore a separate experiment.
The initial local snapshot contains 41,173 completed hourly candles, beginning
January 1, 2022 and ending September 12, 2026 at 15:00 UTC. One shortened March
2023 candle was rejected; one other hour was absent. The resulting two-hour gap
is recorded. Indicators reset after the gap; missing prices are not fabricated.
The API snapshot matches all 744 hourly candles in Binance's January 2024
archive, whose published SHA-256 checksum was verified.

Development: 2022–2024. Validation: January 2025–March 2026. Final holdout:
April 2026 onward, still sealed. Validation was reused for the later hypotheses
and is explicitly labelled exploratory. Public BTC history is not an unknown
market to researchers, so even a sealed local file is not perfect independence.

Each backtest assumes 10,000 USDT capital, long-only spot, no leverage, 0.5%
maximum planned trade risk, and 50% maximum BTC exposure. Signals execute at the
next open after a completed candle. Commission is 0.10% per side and slippage
0.05% per side. These are cost assumptions, not a quote of an account's fee tier.
Doubled costs are also tested. Stop losses account for adverse gaps. If stop and
target are both possible within a bar, the stop is assumed first. A separate
hourly audit found no ambiguous four-hour stop/target exits in the selected
validation runs. Drawdown uses adverse intrabar marks against closing equity
peaks; it is not tick-level exchange execution. Spot has no funding payments.

## Experiments

1. **Frozen baseline grid — 48 configurations.** EMA crossover, channel breakout,
   and trend-filtered RSI pullbacks on one-hour and four-hour candles. Parameter
   choices and ranking score were saved before results. The development winner
   was the 20/10 four-hour breakout, ATR stop 2, target 2R. Development return
   +10.08%; validation -3.02%, drawdown 6.43%, 55 trades, profit factor 0.80.
   Doubled-cost validation -5.22%. Rejected.

2. **Neighbourhood and cost sensitivity — 27 local training configurations.**
   All sampled neighbours made positive development returns, but that did not
   rescue the frozen candidate in later data. Its zero-cost validation return
   was only +0.83%. Under ordinary costs it became negative. A seven-day-block
   bootstrap of validation daily returns put the descriptive 2.5–97.5 percentile
   range around -11.03% to +5.74%. This is not a predictive interval, formal
   significance claim, or adjustment for the strategy search.

3. **Rising-trend filter — 12 configurations.** Require price above a rising
   200-period EMA and test 2R/3R targets. The training winner was a 40/20 four-hour
   breakout with a 3-ATR stop and 3R target. Reused validation +0.11%, drawdown
   2.24%, only 19 trades, profit factor 1.03. Negative under doubled costs.
   Rejected.

4. **Local ridge forecasting — 6 configurations.** Ten causal price/volume
   features predict the next 24-hour return. Monthly refits use a trailing year,
   purge six four-hour labels, and standardize only on past training data. The
   selected configuration lost 5.92% in validation, drawdown 8.38%, 107 trades,
   profit factor 0.62. A gap-handling defect was corrected and results re-run;
   the validation outcome was unchanged. Rejected.

5. **Training stability filter — existing configurations, no new parameters.**
   Require at least 60 development trades, a majority of positive training
   quarters, positive development return, and drawdown below 8%. Evaluate the
   best training candidate per qualifying original family. EMA 50/200 on one
   hour: validation -2.12%, 36 trades. Breakout 40/20 on four hours with ATR 3:
   validation +0.93%, drawdown 2.71%, 24 trades, profit factor 1.17. It fails the
   trade-count and doubled-cost requirements. Both rejected.

6. **Local nonlinear model — 4 configurations.** Histogram gradient boosting,
   shallow trees, fixed iteration count, no randomly shuffled early stopping,
   the same monthly rolling/purged forecasting design and risk limits. The
   selected model lost 0.29% in validation, drawdown 2.73%, 43 trades, profit
   factor 0.96. Doubled costs: -1.60%. Rejected.

## Cross-checks

The selected ridge and tree forecasts were compared with a zero-return forecast
on 2,724 validation observations. Their mean squared errors were respectively
1.015 and 1.060 times the zero-forecast error; directional accuracy was about
50%. No convincing predictive advantage is established.

An exploratory CSCV-style diagnostic used 924 six-quarter/six-quarter partitions
of the 12 development quarters across 70 configurations. Winners averaged +1.07%
per quarter in their selected halves and -0.05% in the other halves. About 33.9%
ranked below the median in the other halves. This uses mean-return selection,
not the production ranking score, and only 12 independent-start quarters; it
must not be presented as a calibrated probability about the future bot.

The paper-account prototype passes checks for fractional risk sizing, fee
accounting, stale data, price gaps, paused entries, state persistence, account
isolation, duplicate-bar prevention, latched drawdown stops, and no live mode.
These tests use synthetic fixtures exclusively; their results are not market
performance. The production website integration still follows the research phase.

## Decision and next hypotheses

No candidate qualifies. Keep the paper account in cash, preserve the final
holdout, and do not lower the thresholds to promote a winner. The next research
cycle should test a single new hypothesis, preferably aimed at stronger
forecast calibration or economically meaningful trade filtering. It should
record failed experiments and use genuinely new forward data when enough has
accumulated. An hour adds very little independent evidence to a slow strategy.

## Source notes

Binance documents a dedicated public market-data endpoint and its historical
archive/checksum format. These establish data provenance, not trading quality.
https://developers.binance.com/en/docs/products/spot/rest-api
https://github.com/binance/binance-public-data

Bailey et al. discuss how repeated strategy selection can overfit historical
returns, and introduce combinatorial methods to examine selection degradation.
Our small-quarter diagnostic is exploratory and does not reproduce their full
empirical analysis.
https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf

Bysik and Ślepaczuk examine the distinction between BTC forecasting and trading
after costs. Their reported model results are not ours. We used the general
idea of cost-aware execution with independently written, simpler local models.
https://arxiv.org/abs/2606.00060

Scikit-learn documents histogram gradient boosting and its early-stopping
behaviour. This implementation disables random internal validation and uses
strictly chronological monthly training instead.
https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html

## Integration baseline checks

The supplied website builds successfully before modification. Original backend
checks: 21 passed. Original portfolio engine checks: 20 passed. Original risk
checks: 42 passed. New research/model/paper checks: 29 passed. A separate causal
check confirmed that changing later prices leaves earlier nonlinear model
forecasts unchanged. Test fixtures never submit exchange orders.

Initial research outputs are guarded against accidental overwriting. Future
experiments should use new dated directories and retain the original frozen
configuration files and validation failures.


## Website integration and reference design — 2026-09-12
Initial research window completed at 17:50 UTC. Integrated authenticated shared research and isolated paper accounts into the supplied React/FastAPI website. The UI follows the user's dark sidebar reference: Overview, Autopilot, Journal, Your brief, Limits and Markets; paper/backtest chart switch; real validation results; cash-only decision panel. No synthetic profits or sample trade proposals are presented as real results. A successful public-feed paper check and hourly maintenance run were recorded at approximately 18:31 UTC. The frozen research dataset remains unchanged.

Validation: 36 research/model/paper/API tests passed, including authenticated account isolation and network-failure handling; original backend API suite 21 passed; frontend production build passed. Browser checked desktop at 1106px and mobile at 390px with no document overflow, guest access, candidate chart selection and paper start/market check.


## Hourly check and main navigation — 2026-09-12 19:17 UTC
Hourly maintenance succeeded; completed public candles extend through 19:00 UTC. Both paper accounts remain in cash with no error or risk stop. Frozen data hash is unchanged; no new candidate or holdout evaluation. User requested one primary trading interface: moved the desk to homepage / and consolidated navigation to Overview, Autopilot, Journal, Limits and Markets. Existing old URLs redirect into the desk. Frontend build and navigation check passed.


## News integration — 2026-09-12 19:24 UTC
User requested major-outlet news in the current app. Added attributed RSS headlines with links and publication dates to Overview and Markets, source/topic filters, ten-minute caching and unavailable/stale status. BBC Business, Guardian Business and CoinDesk returned usable feeds; CNBC did not. Four tests passed for feed parsing, link restrictions, entity rejection, cache TTL and stale fallback; frontend build passed. No news-based trading rule, sentiment score or historical profitability claim was introduced.


## Yahoo Finance integration — 2026-09-12 19:30 UTC
User requested Yahoo Finance. Added five reference quotes to Markets with links, USD denomination, daily change and quote time. All five feeds succeeded; stock/ETF times correctly show the preceding trading session on Saturday. Yahoo news returned 429 and is marked unavailable; normal scheduled feed checks can retry. Three quote tests and four news tests passed; production build passed; browser confirmed actual quotes. These reference prices do not replace Binance BTCUSDT inputs or create a new trading signal.
