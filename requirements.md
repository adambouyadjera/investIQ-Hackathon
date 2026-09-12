# Requirements

Portfolio Strategy Simulator — v2 spec  
Status: **DRAFT — awaiting review**

---

## 1. Purpose and audience

The product is an educational portfolio simulator. A user enters how much they have, how long they are investing, and how much risk they can tolerate. The app returns a specific allocation — which securities, what percentage, what dollar amount — plus what that mix did historically and a probabilistic projection of where it might end up.

Target user: a retail investor who has used Robinhood or Fidelity and found both either too shallow or too dense. The product's job is to make a portfolio decision *legible* — to show the reasoning, not just the recommendation.

This is not a brokerage. No real money moves. No order execution. Every projection screen carries a non-dismissible disclaimer: "Simulated results based on historical data. Educational use only. Not financial advice."

---

## 2. What already exists

The following are **complete and tested** and must not be rewritten without a documented justification:

| Item | Location | Status |
|------|----------|--------|
| Analytics engine | `engine/` | ✅ 20 passing tests |
| FastAPI backend skeleton | `backend/` | ✅ runs on port 8000 |
| Auth endpoints (register, login, refresh, me) | `backend/app/routers/auth.py` | ✅ |
| Portfolio simulation endpoints | `backend/app/routers/portfolio.py` | ✅ |
| Market data cache + scheduler | `backend/app/services/market_data.py` | ✅ |
| Scenarios CRUD | `backend/app/routers/scenarios.py` | ✅ |
| React app skeleton | `frontend/` | ✅ builds cleanly |
| TypeScript type definitions | `frontend/src/types/index.ts` | ✅ matches engine |
| Auth store + API client | `frontend/src/store/`, `frontend/src/api/` | ✅ |
| Basic input form | `frontend/src/components/SimulateForm.tsx` | ⚠️ rebuild as stepped panel |
| Basic results panel | `frontend/src/components/ResultsPanel.tsx` | ⚠️ rebuild per spec |

The existing backend's URL prefix uses `/auth`, `/portfolio`, `/market`, `/scenarios`. This spec requires the prefix to be `/api/auth`, `/api/universe`, `/api/questionnaire`, etc. **The URL surface must be updated** — see Section 5.

---

## 3. Functional requirements

### 3.1 Input flow (stepped panel)

The input experience is a **progressive-disclosure stepped panel**, not a wall of form fields. Five numbered sections. Each section collapses to a compact summary once completed. Collapsed sections can be reopened without losing state. Advanced sections start collapsed.

All inputs persist to `localStorage`. A page refresh restores the form exactly. Every field carries an inline plain-English hint explaining what changing it does.

**Step 1 — Your money** (expanded on load)
- R-1.1: Starting amount (required, positive, ≥ $100).
- R-1.2: Monthly contribution (required, ≥ $0; default $0).
- R-1.3: Investment goal (optional; when provided, the projection shows a "probability of hitting goal" figure alongside the fan chart).

**Step 2 — Your timeline**
- R-2.1: Years invested, entered via a slider (range 1–40) with preset chips: 3, 5, 10, 20, 30 years. The chip sets the slider.
- R-2.2: What the money is for: Retirement, House, Education, General. This is a UI label only; it sets a sensible default horizon per purpose (Retirement: 30, House: 5, Education: 10, General: 20) and is shown back to the user in the AI explanation.

**Step 3 — Your risk** (user chooses one mode)
- R-3.1 Quick mode: Three clickable cards — Conservative, Balanced, Aggressive. Each card displays that tier's historical annualized volatility and worst 12-month loss drawn from engine metrics computed over the full price history. These numbers come from the engine; they are not estimated or made up.
- R-3.2 Guided mode: the 5-question assessment from `allocate.score_questionnaire()`. Questions are fetched from `/api/questionnaire`. After answering, the recommended tier is highlighted and the score breakdown is shown. The user can override the recommendation.

**Step 4 — Your income** (collapsed, optional)
- R-4.1: Monthly take-home pay.
- R-4.2: Monthly essential expenses (rent, food, utilities).
- R-4.3: Current emergency fund balance.
- R-4.4: High-interest debt toggle + balance.
- R-4.5: On submit, calls `/api/savings-capacity` and shows the recommended monthly contribution with any warnings from the engine.
- R-4.6: A single "Apply this amount" button writes the recommendation to Step 1's monthly contribution field.

**Step 5 — Advanced** (collapsed, default)
- R-5.1: Rebalancing frequency: Never / Quarterly / Annual (default Annual).
- R-5.2: Advisory fee drag: 0%–2% slider (default 0%).
- R-5.3: Backtest window: 3 / 5 / 10 / Max years chips.
- R-5.4: Exclude single stocks (ETFs only) toggle — when on, the allocation is drawn from VTI, VXUS, QQQ, VBR, BND, TLT, TIP, BIL, GLD, VNQ only. This is implemented by passing an `etf_only` flag; the engine does not need to change (the existing portfolios already have ETF-heavy tiers).

### 3.2 Results — Allocation

The results view is organized as: **the answer, then the evidence, then the forecast**.

- R-6.1: Donut chart by security, with a second concentric ring grouping by asset class (equity / bond / real_asset). Clicking a slice highlights that asset's row in the table.
- R-6.2: Sortable allocation table: ticker, name, asset class, weight, dollars, share count, expense ratio, 1-year return, 5-year return, correlation to the full portfolio. The return columns require computing per-asset metrics from the engine's price series — see Section 6 for the one engine addition required.
- R-6.3: Equity / bond / real-asset split shown as a single horizontal stacked bar.
- R-6.4: Glide-path explanation panel — shows the `horizon_factor` from the build result as a plain-English sentence ("Because your horizon is N years, your allocation has been shifted N% toward capital preservation") and a small bar showing the blend between the target tier and the PRESERVATION anchor.

### 3.3 Results — Evidence (historical)

- R-7.1: Equity curve (area chart) with the cumulative-contributions line overlaid. The vertical gap between the two lines is the profit. X-axis is date; Y-axis is dollars.
- R-7.2: Drawdown chart (area chart, below the equity curve, sharing the x-axis). Shows the `drawdown` field from the backtest series.
- R-7.3: Metrics grid: CAGR, annualized volatility, Sharpe, Sortino, max drawdown, Calmar, best year, worst year, positive-month %, 95% daily VaR. Each metric has a tooltip — one sentence, no jargon, with a note on whether the user's value is above or below a typical range.
- R-7.4: Calendar-year return bar chart. Each bar is one calendar year; bars for positive years are the gain color, negative years the loss color.
- R-7.5: Correlation heatmap for the held assets. Color scale: negative correlation is one anchor, positive is the other, zero is neutral.
- R-7.6: Fee impact callout: total fees paid over the backtest period, and the counterfactual ending balance at zero additional advisory fee.

### 3.4 Results — Forecast

- R-8.1: Monte Carlo fan chart: five bands (p10, p25, p50, p75, p90) over the horizon. The contributions line overlaid. X-axis is year number; Y-axis is dollars.
- R-8.2: Three headline figures below the chart: bad case (p10), expected (p50), good case (p90).
- R-8.3: Probability of ending above total contributions.
- R-8.4: Probability of hitting stated goal (only shown when a goal was entered).
- R-8.5: Explicit label near the chart: "This is a bootstrap simulation over historical returns, not a prediction. Past performance does not guarantee future results."
- R-8.6: Non-dismissible disclaimer repeated inline on this chart view.

### 3.5 Compare

- R-9.1: The user can run any two or three risk tiers side-by-side over identical inputs.
- R-9.2: Metrics are aligned in rows so the user can scan vertically.
- R-9.3: Equity curves overlaid on a single chart, one line per tier.
- R-9.4: "What if I'd started 5 years earlier" toggle — re-runs the backtest starting 5 calendar years before the history start date; if that pre-dates the available data, the earliest available date is used and the UI notes this.

### 3.6 Universe page

- R-10.1: Shows all 15 assets with: ticker, name, asset class, expense ratio, live-ish price (from the 60-second server cache), and the day's price change if available.
- R-10.2: A data-status pill showing the data source ("snapshot", "yfinance", or "synthetic — offline") and the timestamp of the last successful quote refresh.
- R-10.3: When the synthetic fallback is active, the pill is amber/warning color and uses the word "synthetic". It must not use "estimated" or "simulated" to describe the data source.

### 3.7 AI explanations

- R-11.1: "Explain this portfolio" — given the allocation dict and computed metrics, the model writes 3–4 paragraphs: why this mix suits the horizon and risk tier, what the biggest risk is, and what the historical worst case would have felt like in dollars. References only the figures passed in.
- R-11.2: "Explain this metric" — user clicks any metric, a panel opens and the model writes one paragraph explaining what their specific value means relative to typical ranges.
- R-11.3: "Summarize this comparison" — when on the compare view with two or three tiers, the model writes 2–3 sentences describing the tradeoffs.
- R-11.4: All three calls are server-side only. The Anthropic key never reaches the browser.
- R-11.5: Responses stream to the UI. The user sees text appearing progressively.
- R-11.6: Every AI-generated block carries a visible label: "AI-generated · Educational only".
- R-11.7: Rate-limit `/api/explain` per user (10 calls per hour). Cache responses keyed by SHA-256 hash of the prompt inputs (same inputs, same explanation, no redundant API call).
- R-11.8: When the Anthropic API is unavailable or the key is absent, the endpoint falls back to a static template. The template must cover all three explanation types and reference the actual passed-in numbers via string substitution. The app is fully usable with AI disabled.

### 3.8 Auth and accounts

- R-12.1: Register with email, password (≥ 8 chars, ≥ 1 uppercase, ≥ 1 digit), birth date, self-attestation checkboxes for age (18+) and citizenship.
- R-12.2: Checkboxes are labeled "I confirm I am 18 or older" and "I confirm I am a US citizen or permanent resident." The word "verification" must not appear in the UI or code for this flow. Use "attested" or "confirmed."
- R-12.3: JWT access token (24h) + refresh token (30d). Auto-refresh in the API client before expiry.
- R-12.4: Saved portfolios: save a simulation with a user-defined name. Cap 10 per user. Load a saved portfolio and its full result_json back into the results view.
- R-12.5: Account page: change email, change password. No other account management in scope.

### 3.9 Export and print

- R-13.1: Export CSV of the allocation table and the backtest series as two sheets in a single download (or two separate CSV files).
- R-13.2: Print-friendly stylesheet: a `@media print` CSS that collapses navigation, removes buttons, and ensures charts are visible.

### 3.10 Non-functional

- R-14.1: Responsive to 375px minimum viewport. Charts reflow; no horizontal scroll on any chart.
- R-14.2: Keyboard navigable end-to-end. Visible focus rings in both themes.
- R-14.3: WCAG AA contrast in both dark and light themes.
- R-14.4: Loading skeletons (not spinners) for chart regions while data fetches.
- R-14.5: Empty and error states for every network call: say what happened, offer a recovery action.
- R-14.6: Every network failure has a user-visible, recoverable path — no silent failures.
- R-14.7: `python3 test_engine.py` passes with zero engine modifications, or any modification is documented in `design.md`.
- R-14.8: The app runs fully offline using the synthetic fallback and says so.
- R-14.9: Theme toggle persists across reloads with no flash of the wrong theme (inline script before first paint).
- R-14.10: `prefers-reduced-motion` respected — no entrance animations on cards, no motion beyond state-change transitions.

---

## 4. Out of scope

The following are explicitly out of scope and must not be added even if they seem like natural extensions:

- Live trading, order entry, brokerage integration
- Options, futures, crypto, fixed-income ladder tools
- Social features, sharing, public portfolios
- News sentiment, earnings calendars, macro data feeds
- Portfolio rebalancing alerts or push notifications
- Tax-loss harvesting calculations
- Margin or leverage modeling
- Multiple market data providers (one provider, snapshotted — see hard constraints)

---

## 5. API surface delta

The existing backend uses unprefixed routes (`/auth/...`, `/portfolio/...`). The spec requires `/api/` prefixes and some renamed paths. The delta:

| Existing | New | Notes |
|----------|-----|-------|
| `POST /auth/register` | `POST /api/auth/register` | field rename: `is_us_citizen` → `citizenship_attested` |
| `POST /auth/login` | `POST /api/auth/login` | unchanged |
| `GET /auth/me` | `GET /api/auth/me` | unchanged |
| `GET /portfolio/questions` | `GET /api/questionnaire` | moved |
| `POST /portfolio/questionnaire` | `POST /api/questionnaire/score` | moved |
| `POST /portfolio/savings` | `POST /api/savings-capacity` | moved |
| `POST /portfolio/simulate` | `POST /api/allocate` | renamed |
| `POST /portfolio/compare` | `POST /api/compare` | renamed |
| *(new)* | `POST /api/explain` | AI prose endpoint |
| `GET /market/quotes` | `GET /api/universe` | combines universe metadata + live quotes |
| `GET /scenarios/` | `GET /api/portfolios` | renamed |
| `POST /scenarios/` | `POST /api/portfolios` | renamed |
| `GET /health` | `GET /api/health` | add data source + last refresh time |

The existing router files will be restructured but their logic reused.

---

## 6. One required engine addition

The allocation table (R-6.2) requires per-asset 1-year and 5-year returns. These are not in the current `allocate.build()` output.

**Proposed addition to `engine/allocate.py`** (the only engine change):

In `build()`, after computing `latest = prices.iloc[-1]`, compute:

```python
from .data import daily_returns as _dr
_rets = _dr(prices)

for allocation item:
    r1 = (_rets[ticker].iloc[-252:] + 1).prod() - 1   # ~1 year
    r5 = (_rets[ticker].iloc[-1260:] + 1).prod() - 1  # ~5 years
    # clip to available history silently
    add "return_1y": round(r1, 5), "return_5y": round(r5, 5) to each allocation item
```

This is deterministic, uses only data already loaded, adds no dependencies, and is coverable by a test. Full justification and test case to be written in `design.md`.

The correlation-to-portfolio figure also needs a new helper. Proposed: `engine/metrics.py` gets a public `asset_portfolio_correlation(asset_returns, portfolio_returns)` function — a one-liner wrapping `pd.concat(...).corr()`. No behavior change to existing functions.

---

## 7. Definition of done

A build is **done** when all of the following are true:

1. `python3 test_engine.py` — 20/20 pass (no regressions, or any change documented).
2. `pytest backend/tests/` — all endpoint tests pass, including auth failures and validation errors.
3. `npx vitest run` — all component tests pass.
4. A user can go from the landing page to a saved, AI-explained portfolio without reading documentation.
5. Theme toggle persists across hard reloads with no flash.
6. The app runs end-to-end with `ANTHROPIC_API_KEY` unset — static fallback text appears.
7. The app runs end-to-end with `PS_NO_NETWORK=1` — synthetic pill visible, all numbers valid.
8. README contains setup instructions and screenshots of both themes.
