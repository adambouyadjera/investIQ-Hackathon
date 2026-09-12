# Agent desk

An explainable, simulation-only paper-trading research desk. It scores a fixed
set of quantitative features plus news sentiment into one auditable number,
proposes trades the existing `trading/` risk gate is free to refuse, fills them
through a paper broker that charges realistic costs, and reports the result
against buy-and-hold with a multiple-testing penalty applied.

```bash
python run_agent_demo.py          # scan + backtest + walk forward
python run_agent_demo.py --scan   # just today's proposals, decomposed
python test_agent.py              # 49 tests
```

In the app: **Agent desk** in the navbar, or `/agent`.

---

## There is no live mode

`agent.paper.LIVE_TRADING_SUPPORTED` is `False`. There is no broker client, no
credential, no order endpoint and no webhook anywhere in the package.
`test_agent.py::no_broker_imports_anywhere` walks every module and fails if one
appears, extending the test that already guards `trading/`.

This is a structural property, not a setting. Nothing in the codebase reads
that constant as a switch — it exists so the answer is greppable.

---

## What's here

| Module | Owns |
|---|---|
| `agent/signals.py` | Five point-in-time quantitative features + regime classification |
| `agent/news.py` | Headline sentiment, scored term-by-term, read strictly point-in-time |
| `agent/decide.py` | The weighted evidence sum. Emits `OrderIntent`, never a size |
| `agent/costs.py` | Commission, spread, slippage, borrow — realised vs marginal |
| `agent/paper.py` | Simulated broker: fills, stops, partial exits, equity curve |
| `agent/evaluate.py` | The harness: execution lag, risk gate, benchmark, walk-forward |
| `agent/stats.py` | Deflated Sharpe, alpha/beta, inverse normal (no scipy) |
| `agent/journal.py` | The audit trail — every proposal, veto and fill, with evidence |

---

## The explainability contract

Every decision satisfies, exactly and not approximately:

```
sum(e.contribution for e in proposal.evidence) == proposal.raw_score
score == raw_score * conviction
```

`test_agent.py::evidence_sums_to_score` asserts it to within 1e-12 across a
full backtest. An explanation that cannot reconstruct the number it claims to
explain is decoration, so the invariant is a test rather than a convention.

The model is a hand-written linear sum, not a learned one. For a signal that
has to be auditable line-by-line, a transparent weighting is the better
engineering choice — and every weight is versioned and hashed, so a silent edit
shows up in the API response as a changed `weights_hash`.

The five evidence lines, weighted per regime:

| Feature | What it measures |
|---|---|
| `trend` | Fast/slow EMA separation, in ATR units |
| `momentum` | 12-month return excluding the last month |
| `reversion` | Negated 20-day z-score; oversold reads positive |
| `breakout` | Distance from the *prior* 55-day high, in ATR units |
| `news` | Decay-weighted lexicon sentiment over a 10-day window |

Weights shift with the regime: `calm` favours continuation, `volatile` leans on
reversion and damps everything, `bear` gives news a *lower* weight — in a
drawdown the tape is saturated with alarming headlines that are already priced.

---

## The agent cannot size its own position

`OrderIntent` has no quantity field, and `decide.py` contains no identifier
named `quantity`, `qty`, `size` or `shares` — checked over the parsed syntax
tree, so the module is free to discuss sizing in its docstring while failing if
any executable line references one.

Size is computed by `trading/sizing.py` from the stop distance and account
equity, then capped by the breaker multiplier, buying power, concentration and
open-risk budget. A high score buys conviction in the journal and nothing else.

---

## Five ways this refuses to flatter itself

**1. A signal on bar `t` executes on bar `t+1`.** Proposals sit in a pending
queue and are repriced to the next bar's close. No decision acts on the price
that produced it. Pinned by `execution_lags_the_signal`.

**2. Features are point-in-time.** `no_lookahead_in_any_feature` re-derives
every feature on truncated history and asserts the value at `t` is bit-for-bit
unchanged. That is what catches a full-sample z-score or an EMA computed with
`adjust=True`.

**3. Every fill pays.** Spread, slippage, commission and borrow. Stops fill at
the close that broke them, not at the stop price — daily closes are all the
data there is, so an intrabar touch is unobservable, and assuming a fill at the
level a gapping market would never have given you is the wrong direction to be
wrong in. When a bar breaches both a stop and a target, the stop wins.

**4. Nothing is reported without a benchmark.** Buy-and-hold over the identical
window, paying the identical costs, in whole shares with the leftover cash left
idle. An absolute return figure on its own says nothing.

**5. Out-of-sample is reported separately.** The weights and thresholds were
written by someone who had seen this price history. That is a fit, however
informal, and the only honest response is to split the sample and label which
half is contaminated.

---

## The number the leaderboards leave out

Generate 185 strategies against one price history, keep the best-looking one,
and its backtest Sharpe is a *maximum drawn from a distribution* — not an
estimate of an edge. The expected maximum grows with the number of trials, so
the hurdle has to grow with it.

`agent/stats.py` implements the deflated Sharpe ratio (Bailey & López de Prado):
it corrects the observed Sharpe for non-normal returns, sample length, **and**
how many strategies were tried before this one was chosen.

```
n_trials=  1   hurdle 0.00 annualised Sharpe
n_trials= 12   hurdle 0.77
n_trials=185   hurdle 1.27
```

Searching harder does not find more edge. It raises the score you need before
anyone should believe you. Declaring `n_trials` honestly is the entire point,
and the default of `1` produces the *weakest* available claim rather than a
flattering one.

---

## What the desk actually did

Reproducible across processes — `backtest_is_reproducible` pins it.

| | In sample (2015-09 → 2021-12) | **Out of sample (2022-01 → 2026-09)** |
|---|---|---|
| Strategy | +38.50% | **+14.89%** |
| Buy & hold | +167.62% | **+64.97%** |
| Excess CAGR | −11.61% | **−8.30%** |
| Alpha / beta | +3.34% / 0.13 | **+2.86% / 0.03** |
| Max drawdown | −8.45% | **−10.41%** |
| Benchmark drawdown | −34.99% | **−25.21%** |
| Trades / win rate | 489 / 54% | **146 / 55%** |
| Profit factor | 1.293 | **1.306** |
| Deflated Sharpe (6 trials) | 0.642 | **0.360** |
| Verdict | indistinguishable from selection luck | **indistinguishable from selection luck** |

**This strategy does not beat buy-and-hold, and the harness says so.** It
captures a small positive alpha with about a third of the drawdown at a beta
near zero — the profile of something mostly sitting in cash — but the deflated
Sharpe does not clear the hurdle in either window, so the honest reading is
that no edge has been demonstrated.

That the two windows agree closely is mild evidence the rules were *not*
overfit. It is not evidence that they work.

---

## News

Point-in-time by construction: `sentiment_at` filters on `published_at <
bar_close`, strictly. A headline timestamped at the close of the day you are
trading is not information you had.

Sentiment is a lexicon, not a language model — every score decomposes into the
exact terms that matched, including negation ("fails to beat" scores negative),
and multi-word phrases are matched before single words so "guidance cut" scores
once rather than twice.

Three providers:

- **`JsonlNewsProvider`** — real archived headlines from `data/news.jsonl`.
  One JSON object per line: `{"symbol", "published_at", "text", "source"}`,
  with an explicit UTC offset. Drop the file in and every score in the app
  switches over.
- **`SyntheticNewsProvider`** — the offline default. Generated from *past*
  returns plus a seeded noise term, so it is **non-predictive by construction**.
  `synthetic_news_is_not_predictive` asserts its correlation with next-day
  returns stays under 0.08. A synthetic corpus that knew the future would
  manufacture alpha and the harness would report it in good faith.
- **`NullNewsProvider`** — neutral, flagged.

The source is carried on every score to the API response and the UI, and a run
using synthetic news is labelled as such in the report's caveats.

---

## Notes on two decisions that look arbitrary

**Entry threshold, 0.35.** Near the 92nd percentile of the historical score
distribution, so roughly one symbol-day in thirteen qualifies. Chosen for
*selectivity* — how often a desk holding at most eight positions should find
something to do — not by sweeping thresholds against returns. The first is a
capacity decision; only the second would need declaring to `n_trials`.

**Minimum stop-to-cost ratio, 2.0.** Without it the desk proposes
cash-equivalents. BIL moves about 1.4¢ a day, so a 2×ATR stop sits 2.8¢ from
entry while costing ~10¢ to get in and out — the stop is a quarter of the
friction, and the geometry check passes on a trade that is pure cost. Stated
against the cost ratio rather than a list of banned tickers, because the thing
that makes the trade unviable is the ratio, not the symbol. BND and TIP are low
volatility but clear it comfortably, and are not excluded.

---

## API

All endpoints require `Authorization: Bearer <token>`.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/agent/config` | Weights, thresholds, risk limits, hashes |
| POST | `/api/agent/scan` | Today's proposals, fully decomposed |
| POST | `/api/agent/backtest` | One window vs benchmark, with significance |
| POST | `/api/agent/walk-forward` | In-sample and out-of-sample, reported apart |
| GET | `/api/agent/regime` | Recent regime labels and stability |

Backtests run in a worker thread and are cached by request signature, so a
repeated call returns in milliseconds rather than seconds.

---

Educational simulation. Not financial advice. No real-money trading is
supported by this software. You can lose money trading; most retail algorithmic
strategies do not beat a low-cost index fund after costs.
