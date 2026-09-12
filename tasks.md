# Tasks

Portfolio Strategy Simulator — v2  
Status: **DRAFT — awaiting review**

Execute tasks in order. Do not begin a task until the one above it is marked done. Each task ends with a specific verification step that must pass before moving on.

---

## Phase 1 — API foundation

### Task 1 — Restructure backend routes under `/api/` prefix

**What**: Move all existing routers to `/api/*` prefixes. Update `backend/app/main.py` to mount a top-level `api_router` with prefix `/api`. Update Vite proxy config and nginx config to match.

**Files touched**:
- `backend/app/main.py` — mount `api_router` at `/api`
- `backend/app/routers/auth.py` — prefix stays `/auth` (net result: `/api/auth/...`)
- `backend/app/routers/portfolio.py` — split into `allocate.py`, `questionnaire.py`, `savings.py`
- `backend/app/routers/market.py` → `backend/app/routers/universe.py`
- `backend/app/routers/scenarios.py` → `backend/app/routers/portfolios.py`
- `backend/app/routers/__init__.py` — new, exports `api_router`
- `frontend/vite.config.ts` — update proxy from `/auth,/portfolio,...` to `/api`
- `frontend/nginx.conf` — update location block

**Do not change**: any logic inside the routers. This is a mechanical rename.

**Verification**: `curl http://127.0.0.1:8000/api/health` returns `{"status":"ok",...}`. `curl http://127.0.0.1:8000/health` returns 404 (old path gone).

---

### Task 2 — Pydantic v2 request/response models

**What**: Replace all raw dict returns and bare `except Exception` handlers with typed Pydantic models and structured error responses. Every endpoint must have explicit `response_model=`.

**Files to create**:
- `backend/app/schemas/auth.py` — `RegisterRequest`, `LoginRequest`, `TokenResponse`, `UserOut`, `RefreshRequest`
- `backend/app/schemas/allocate.py` — `AllocateRequest`, `AllocateResponse`, `AllocationItem`, `BacktestOut`, `ProjectionOut`, `MetricsOut`
- `backend/app/schemas/compare.py` — `CompareRequest`, `CompareResponse`
- `backend/app/schemas/questionnaire.py` — `QuestionOut`, `ScoreRequest`, `ScoreResponse`
- `backend/app/schemas/savings.py` — `SavingsRequest`, `SavingsResponse`
- `backend/app/schemas/portfolios.py` — `PortfolioCreate`, `PortfolioOut`
- `backend/app/schemas/explain.py` — `ExplainRequest`, `ExplainKind`
- `backend/app/schemas/health.py` — `HealthResponse`
- `backend/app/schemas/__init__.py`

**Key constraint**: `AllocateRequest` must include `etf_only: bool = False` and `backtest_years: int | None = Field(default=None, ge=3, le=20)` and `purpose: Literal[...] | None`. These are pass-through for now (engine call unchanged); they are used in Step 5 and in the AI explain context.

**Key constraint on `RegisterRequest`**: field must be named `citizenship_attested: bool`, not `is_us_citizen`. Validator error text must say "attested" not "verified."

**Error handler**: add a global `@app.exception_handler(RequestValidationError)` that returns `{"detail": [{"field": e.loc[-1], "message": e.msg} for e in exc.errors()]}` — frontend can show per-field errors from this shape.

**Verification**: `POST /api/auth/register` with `{"email": "bad"}` returns 422 with `detail[0].field == "email"`. `POST /api/allocate` with `{"amount": -1, ...}` returns 422. `GET /api/health` returns a JSON object that validates against `HealthResponse`.

---

### Task 3 — Alembic migration

**What**: Create a migration that: renames `is_us_citizen` → `citizenship_attested`; changes `monthly_income` column type from TEXT to NUMERIC; renames table `scenarios` → `portfolios`; adds column `portfolios.purpose TEXT`; ensures indexes exist.

**Files touched**:
- `backend/alembic/versions/0002_v2_schema.py` — new migration file
- `backend/app/models/user.py` — rename field
- `backend/app/models/scenario.py` → `backend/app/models/portfolio.py` — rename file, rename class, rename table, add `purpose` field
- `backend/app/models/__init__.py` — update import

**Verification**: `alembic upgrade head` runs without error. `alembic downgrade -1` runs without error. `python3 -c "from backend.app.models import User, Portfolio; print('ok')"` (adjust path as needed).

---

### Task 4 — Engine additions: per-asset returns + correlation matrix

**What**: Implement the two changes documented in `design.md` Section 9. These are the **only** permitted engine changes.

**Files touched**:
- `engine/allocate.py` — add `daily_returns` to imports; add `return_1y`, `return_5y` to each allocation item; add `correlation_matrix` field to build() return dict
- `engine/metrics.py` — no change (function already exists)
- `test_engine.py` — add `t_build_returns_present` and `t_build_correlation_matrix`

**Exact code for `allocate.py` additions** (copy verbatim, do not alter logic):

In the import block, add `daily_returns` to the existing `from .data import ...` line.

In `build()`, after the `allocation = []` loop completes, add:
```python
_rets = daily_returns(prices)
for item in allocation:
    t = item["ticker"]
    if t in _rets.columns:
        item["return_1y"] = round(float((1 + _rets[t].iloc[-252:]).prod() - 1), 5)
        item["return_5y"] = round(float((1 + _rets[t].iloc[-1260:]).prod() - 1), 5)
    else:
        item["return_1y"] = None
        item["return_5y"] = None
```

After the `proj = montecarlo.project(...)` call, before the `return {...}` statement, add:
```python
held = [item["ticker"] for item in allocation]
_corr = metrics.correlation_matrix(_rets[held])
corr_dict = {
    row: {col: round(float(_corr.loc[row, col]), 4) for col in held}
    for row in held
}
```

In the `return {...}` dict, add `"correlation_matrix": corr_dict` as a top-level key.

**Verification**: `python3 test_engine.py` — **22 passing, 0 failing**. This number must be exact. If any existing test fails, stop and fix before proceeding.

---

### Task 5 — `/api/explain` endpoint with streaming and fallback

**What**: Implement the AI explanation endpoint as an SSE stream with a static fallback, rate limiter, and response cache.

**Files to create**:
- `backend/app/routers/explain.py`
- `backend/app/services/explain_service.py` — rate limiter, cache, Anthropic call, fallback templates
- `backend/app/services/fallback_templates.py` — static template strings with `{placeholder}` substitution

**`explain_service.py` responsibilities**:
- `RateLimiter` class: in-process dict `{user_id: deque[timestamp]}`. `check(user_id)` returns `(allowed: bool, retry_after_seconds: int)`. Window: 3600s, limit: 10.
- `ResponseCache` class: in-process dict `{hash: (text, expires_at)}`. TTL: 86400s. Key: `hashlib.sha256(request_json.encode()).hexdigest()`.
- `stream_explanation(request: ExplainRequest, user_id: str) -> AsyncGenerator[str, None]`: checks rate limit, checks cache, calls Anthropic or falls back, yields SSE `data: {chunk}\n\n` strings, writes to cache on completion.

**`fallback_templates.py`**: three functions — `portfolio_template(ctx: dict) -> str`, `metric_template(ctx: dict) -> str`, `comparison_template(ctx: dict) -> str`. Each uses only values from `ctx` (never hardcoded financial numbers). Implementation uses Python `.format(**ctx)` — no f-strings with computed values.

**`explain.py` router**:
```python
@router.post("/explain")
async def explain(
    body: ExplainRequest,
    current_user: User = Depends(get_current_user),
):
    return StreamingResponse(
        stream_explanation(body, str(current_user.id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

**Verification**: with `ANTHROPIC_API_KEY` unset, `POST /api/explain` with a valid body returns a streaming response whose text matches the fallback template. With a valid key, it streams. With the same inputs twice, the second call is served from cache (verify by adding a request counter to the service and checking it increments only once).

---

### Task 6 — Quote cache simplification

**What**: Remove the multi-provider waterfall (Polygon → AlphaVantage → yfinance) from `market_data.py`. The hard constraint requires one provider. Keep only the yfinance path. Change the scheduler interval from 5 minutes to 60 seconds.

**Files touched**:
- `backend/app/services/market_data.py` — delete `_fetch_polygon`, `_fetch_alpha_vantage`; simplify `refresh_quotes` to call only `_fetch_yfinance_batch`; change scheduler interval
- `backend/app/core/config.py` — remove `ALPHA_VANTAGE_KEY` and `POLYGON_KEY` settings
- `backend/requirements.txt` — remove `aiohttp` (no longer needed)
- `docker-compose.yml` — remove those env vars
- `backend/.env` — remove those env vars
- `backend/app/routers/universe.py` (formerly `market.py`) — remove `POST /market/refresh` (manual refresh is a dev affordance; it can stay as a hidden dev endpoint but should not be in the public API surface)

**Verification**: backend starts, `/api/universe` returns 15 quotes within 5 seconds of startup, no Polygon or AV keys referenced anywhere in the codebase (grep confirms).

---

## Phase 2 — Frontend foundation

### Task 7 — CSS token system + theme injection

**What**: Replace `frontend/src/index.css` with the token architecture from `design.md` Section 4.2. Add the theme-injection inline script to `index.html`. Implement `ThemeToggle` component and `useTheme` hook.

**Files to create/replace**:
- `frontend/src/tokens/colors.css` — all `--color-*` and `--chart-*` tokens, both themes
- `frontend/src/tokens/typography.css` — font families, scale, `--font-feature-tabular`
- `frontend/src/tokens/spacing.css` — spacing scale
- `frontend/src/index.css` — imports the three token files, global reset, `.num` utility class (tabular figures)
- `frontend/index.html` — add inline theme script before `<script type="module">` tag
- `frontend/src/store/theme.ts` — `getTheme()`, `setTheme()`, `subscribe()`
- `frontend/src/hooks/useTheme.ts` — returns `{theme, setTheme}`, subscribes to store
- `frontend/src/components/ui/ThemeToggle.tsx` — icon button cycling dark→light→system, accessible label

**Inline script** (add to `index.html` verbatim):
```html
<script>
  (function() {
    try {
      var t = localStorage.getItem('ps-theme') || 'system';
      var d = t === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : t;
      document.documentElement.setAttribute('data-theme', d);
    } catch(e) {}
  })();
</script>
```

**No hardcoded hex** in any `.tsx` or `.ts` file after this task. Run `grep -r '#[0-9a-fA-F]\{3,6\}' frontend/src/` — result must be empty.

**Verification**: start `npm run dev`, open browser. Toggle the theme three times. Check that `data-theme` attribute on `<html>` changes. Hard-reload — theme is preserved. Switch OS to dark mode, set theme to "system" — app follows. No white flash on load (test by throttling CPU in DevTools and reloading).

---

### Task 8 — Install new frontend dependencies

**What**: Add the packages required by this spec that are not already installed.

**Install**:
```bash
cd frontend
npm install @tanstack/react-query@5 @tanstack/react-query-devtools@5
```

TanStack Query replaces the existing direct `axios` calls in hooks. The existing `axios` instance in `api/client.ts` is kept as the fetch transport.

**Update `App.tsx`**: wrap the router in `<QueryClientProvider client={queryClient}>`.

**Verification**: `npm run build` completes with 0 errors after the change.

---

### Task 9 — Stepped input panel

**What**: Build the five-step collapsible input panel from scratch. Replace `frontend/src/components/SimulateForm.tsx` entirely.

**Files to create**:
- `frontend/src/components/input/SteppedPanel.tsx` — outer shell, step management
- `frontend/src/components/input/Step.tsx` — collapsible wrapper, summary line
- `frontend/src/components/input/MoneyStep.tsx` — Step 1
- `frontend/src/components/input/TimelineStep.tsx` — Step 2 (slider + chips + purpose select)
- `frontend/src/components/input/RiskStep.tsx` — Step 3 (mode toggle + RiskCards or QuestionnaireFlow)
- `frontend/src/components/input/IncomeStep.tsx` — Step 4
- `frontend/src/components/input/AdvancedStep.tsx` — Step 5
- `frontend/src/components/input/RiskCards.tsx` — three tier cards with historical stats
- `frontend/src/components/input/QuestionnaireFlow.tsx` — radio groups + score result
- `frontend/src/hooks/useFormPersistence.ts` — reads/writes `FormState` to localStorage on every dispatch

**Inline hints**: every `<Input>` or `<Slider>` must have a `hint` prop rendered as `<p class="field-hint">` below the control. The text is specified in this task's detail below.

**Hint copy** (use these verbatim):
- Starting amount: "How much you're investing today. This is your lump-sum deposit."
- Monthly contribution: "Additional money you'll add each month. Even small amounts compound significantly over time."
- Goal: "Optional. If you have a target balance (e.g. $500,000 for retirement), we'll show the probability of reaching it."
- Years invested: "How long you plan to leave this money invested without needing it."
- Purpose: "Helps frame the AI explanation. Doesn't change the numbers."
- Risk (quick): "These volatility and worst-year figures are from actual historical data, not estimates."
- Monthly take-home: "Your actual after-tax pay each month."
- Monthly essentials: "Rent, food, utilities, insurance — the non-negotiables. Leave blank to use 50% of income as a default."
- Emergency fund: "Liquid savings you can access immediately. Recommended: 4 months of essentials."
- High-interest debt: "Credit cards or loans above ~7% APR. Paying these down is almost always a better return than investing."
- Rebalancing: "How often weights are reset to targets. Annual is usually right for taxable accounts."
- Advisory fee drag: "An additional annual cost on top of the ETF expense ratios. 0.5% is typical for a robo-advisor."
- Backtest window: "How many years of price history to run the simulation over. 'Max' uses all available data."
- ETFs only: "Excludes individual stocks (AAPL, MSFT, NVDA, JNJ, JPM) from the allocation."

**State persistence**: `useFormPersistence` hook debounces localStorage writes by 300ms. Reads on mount via `useEffect` (after React hydration). Key: `ps-form-v1`.

**Verification**: fill in all five steps. Hard-reload the page — all values are restored. Navigate away and back — values are restored. Close Step 3, reopen it — previously selected risk tier is still selected.

---

### Task 10 — `useSimulate` hook and results skeleton

**What**: Wire the stepped panel to `/api/allocate` using TanStack Query. Show loading skeletons while the result is pending.

**Files to create/update**:
- `frontend/src/hooks/useSimulate.ts` — `useMutation` wrapping `POST /api/allocate`; `useCompare.ts` wrapping `POST /api/compare`
- `frontend/src/api/simulator.ts` — update to use new `/api/` paths
- `frontend/src/components/results/ResultsShell.tsx` — three-section container; shows skeleton when `isPending`; shows error banner when `isError`
- `frontend/src/components/ui/ChartSkeleton.tsx` — shimmer placeholder, accepts `height` prop
- `frontend/src/components/ui/ErrorBanner.tsx` — shows `message`, optional `requestId`, "Try again" button

**Mutation error handling**: on 400, extract `detail` from response and display in an error banner inside the results area (not a global toast). On 422, surface per-field errors back to the form step that owns those fields. On 500, show generic error with request_id.

**Loading skeleton layout**: the results area shows three `<ChartSkeleton>` components of heights 300px, 200px, 120px while the mutation is pending.

**Verification**: submit the form. The results area shows skeletons for ~1–3 seconds (depending on machine speed), then renders the allocation section. Network tab shows exactly one POST to `/api/allocate`.

---

## Phase 3 — Results views

### Task 11 — Allocation section

**What**: Build the three allocation visuals and the glide-path panel.

**Files to create**:
- `frontend/src/components/results/AllocationSection.tsx`
- `frontend/src/components/charts/AllocationDonut.tsx`
- `frontend/src/components/results/AllocationTable.tsx`
- `frontend/src/components/results/AssetClassBar.tsx`
- `frontend/src/components/results/GlidepathPanel.tsx`

**Donut chart**: outer ring — one slice per asset, colored from `--chart-1` through `--chart-8` cycling. Inner ring — three slices, one per asset class, colored `--color-equity`, `--color-bond`, `--color-real-asset`. Clicking an outer slice scrolls the table to that row and highlights it. Legend below the chart.

**Allocation table**: columns — Ticker, Name, Asset Class (badge), Weight, Amount ($), Shares, Exp. Ratio, 1Y Return, 5Y Return, Portfolio Correlation. Sortable by any column (click header). Default sort: weight descending. All numeric columns use `.num` class (tabular figures). Return cells: positive values use `--color-gain` with ↑ glyph; negative use `--color-loss` with ↓ glyph and parentheses around the value (e.g. `↓ (12.3%)`). Signed value + glyph pattern applied to every signed number in the app, not just this table.

**Asset class bar**: single `<div>` with three `<span>` children, widths proportional to equity_share, bond_share, real_asset_share. Three colors. Percentage labels inside each segment when wide enough (>8% of total width), outside otherwise. Tooltip on hover shows exact percentages.

**Glide-path panel**: a short text block using the `horizon_factor` from the response. Example: "Your 5-year horizon shifts 67% of the weight toward capital preservation. A 15-year horizon would give the full Balanced target." Plus a small two-segment bar: left segment (width = `horizon_factor`) labeled "Target tier", right segment labeled "Preservation anchor". Both use CSS variables for color.

**Verification**: allocation items sum display sums to 100% (rounding to integers may give 99% or 101% — add a note if total ≠ 100%). Table sorts correctly. Donut click highlights table row. Glide-path bar shows correct proportions for a 5-year horizon (horizon_factor ≈ 0.33, so preservation segment is 67% of the bar).

---

### Task 12 — Evidence section

**What**: Build the historical evidence views.

**Files to create**:
- `frontend/src/components/results/EvidenceSection.tsx`
- `frontend/src/components/charts/EquityCurve.tsx` — area chart, balance + contributed lines
- `frontend/src/components/charts/DrawdownChart.tsx` — area chart, shares x-axis sync with EquityCurve
- `frontend/src/components/charts/CalendarReturns.tsx` — vertical bar chart per calendar year
- `frontend/src/components/results/MetricsGrid.tsx` — 10 metric tiles with tooltips
- `frontend/src/components/charts/CorrelationHeatmap.tsx` — custom grid of colored cells
- `frontend/src/components/results/FeeImpact.tsx` — callout with fees paid + counterfactual

**Equity curve**: `<AreaChart>` with `syncId="backtest"`. Area: `balance` in `--chart-1` at 30% fill opacity. Line: `contributed` in `--color-bond` dashed. X-axis: year labels. Y-axis: dollar formatting with K/M suffixes. Hover tooltip shows both values + the gap ("Profit: $X").

**Drawdown**: `<AreaChart syncId="backtest">` directly below the equity curve, sharing the x-axis tick labels (the equity curve's x-axis is hidden; the drawdown chart's is visible). Fill: `--color-loss` at 40% opacity. Y-axis: percentage format, inverted scale. Hover shows worst drawdown to date.

**Calendar returns**: one bar per year. Fill: `--color-gain` for positive, `--color-loss` for negative. Value labels above/below each bar. X-axis: year. Data derived from the backtest series by grouping to calendar year — this computation happens in a utility function `groupByYear(series: BacktestPoint[]): {year: number, return: number}[]` in `frontend/src/utils/finance.ts`.

**Metrics grid**: 2×5 or 5×2 responsive grid. Each cell: metric name (small, muted), value (large, tabular), one-sentence tooltip. Tooltip trigger: `?` icon button (accessible, shows `<Tooltip>` on hover/focus). Tooltip copy for all 10 metrics:

| Metric | Tooltip |
|--------|---------|
| CAGR | "Compound Annual Growth Rate — the steady annual return that would produce the same end result as the actual bumpy path." |
| Volatility | "Annualized standard deviation of daily returns. Higher means larger typical swings, both up and down." |
| Sharpe Ratio | "Return above the risk-free rate (3%), divided by volatility. Above 1.0 is generally considered good; above 2.0 is strong." |
| Sortino Ratio | "Like Sharpe, but only penalizes downside volatility. Better reflects risk that investors actually care about." |
| Max Drawdown | "The largest peak-to-trough decline in the portfolio's history. This is the gut-check number: could you have held on?" |
| Calmar Ratio | "CAGR divided by the absolute max drawdown. Measures return earned per unit of worst-case loss." |
| Best Year | "The single best calendar-year return in the backtest period." |
| Worst Year | "The single worst calendar-year return. On a $10,000 portfolio at this rate, that year would have felt like losing $X." (substitute actual dollar amount)" |
| Positive Months | "Fraction of months where the portfolio gained value. Helps understand the typical experience, not just the extremes." |
| 95% Daily VaR | "On the worst 5% of trading days in this history, the portfolio lost at least this much in a single day." |

The "Worst Year" tooltip substitutes the actual dollar loss using the `inputs.amount` from the result. This is pure string arithmetic on client-side numbers already in the response — not an LLM output.

**Correlation heatmap**: `N×N` grid where N = number of held assets. Each cell is a colored `<div>`. Color: linear interpolation between `--color-loss` (at −1), `--color-surface-2` (at 0), and `--color-gain` (at +1). Ticker labels on both axes. Diagonal cells show "1.00" in `--color-text-muted`. Cell hover shows "AAPL ↔ MSFT: 0.72".

**Fee impact**: a highlighted callout box. Line 1: "Fees paid over {N} years: **${fees_paid}**". Line 2: "Your portfolio without advisory fees would have ended at **${counterfactual}**." Counterfactual: re-run is not needed — this is shown only when `extra_fee > 0`; the counterfactual is approximated as `final_balance * (1 + extra_fee)^horizon_years` (a rough upper bound, clearly labeled "approximate"). If `extra_fee === 0`, show only the ETF expense ratio impact: "ETF expense ratios cost approximately ${fees_paid} over this period."

**Verification**: equity curve renders with two lines. Clicking on the equity curve shows a tooltip that also highlights the same date on the drawdown chart. Calendar returns bar chart shows correct sign (positive = gain color). All 10 metrics render with correct values from the response. Correlation heatmap diagonal is all "1.00". Fee impact callout shows only when extra_fee > 0 (or always for ETF fees).

---

### Task 13 — Forecast section

**What**: Build the Monte Carlo fan chart and the disclaimer infrastructure.

**Files to create**:
- `frontend/src/components/results/ForecastSection.tsx`
- `frontend/src/components/charts/MonteCarloFan.tsx`
- `frontend/src/components/ui/Disclaimer.tsx` — non-dismissible disclaimer component

**Monte Carlo fan**: five `<Area>` layers. p25–p75 band: `--chart-1` at 20% opacity, no stroke. p10–p90 outer lines: `--color-text-muted` at 1px stroke, transparent fill. p50 median: `--chart-1` at 2px stroke, transparent fill. Contributions line: `--color-bond` dashed 1px. X-axis: year labels (month ÷ 12, rounded). Y-axis: K/M dollar format.

Goal reference line: if `prob_hit_goal` is present in the response, draw a `<ReferenceLine>` at `y={goal}` in `--color-warning` dashed. Label: "Goal: $X".

**Inline disclaimer**: appears immediately below the chart, in a visually distinct box (border: `--color-border`, background: `--color-surface-2`). Text: "Simulated results based on historical data. Educational use only. Not financial advice." Non-dismissible — no close button, no collapse. This same `<Disclaimer>` component is also placed in the footer of `ResultsShell`.

**Headline figures**: three tiles below the chart. Bad case (p10): red-tinted. Expected (p50): accent-tinted. Good case (p90): green-tinted. All values in `--font-mono` with `.num` class.

**Probability stats**: two stat tiles. "Probability ends above invested amount: XX%" (always shown). "Probability of reaching goal: XX%" (only when `prob_hit_goal` is present). Both use signed formatting — percentage is plain text, no glyph needed here.

**Verification**: fan chart renders all five bands. Contributions line is dashed. Disclaimer is visible and has no close/dismiss affordance. When a goal is set (e.g. $500,000), goal reference line appears on the chart and `prob_hit_goal` tile appears below. Hard-coded check: disclaimer text matches exactly "Simulated results based on historical data. Educational use only. Not financial advice."

---

## Phase 4 — Auth, AI, and secondary pages

### Task 14 — Auth pages rebuild

**What**: Replace the existing `LoginPage.tsx` and `RegisterPage.tsx` with implementations that meet the spec. Key changes: attestation language (not "verification"), field rename (`citizenship_attested`), send to `/api/auth/register`.

**Files to update**:
- `frontend/src/pages/AuthPage.tsx` — shell with login/register tab switch
- `frontend/src/pages/LoginPage.tsx` — update API path to `/api/auth/login`
- `frontend/src/pages/RegisterPage.tsx` — rename field, fix label text

**Checkbox labels** (exact text, do not vary):
- "I confirm I am at least 18 years of age"
- "I confirm I am a US citizen or permanent resident"
- "I understand this is an educational simulator and not financial advice"

No occurrence of the word "verification", "verified", or "verify" anywhere on these pages or in the form submission code.

**Verification**: grep the entire `frontend/src/` for "verif" (case-insensitive) — result must be zero matches in auth-related components. Registration form cannot be submitted without all three checkboxes checked. Age validation: birth date that makes user exactly 17 years old today → form error "You must be at least 18."

---

### Task 15 — Explain panel + useExplain hook

**What**: Build the UI for AI explanations. The backend endpoint was built in Task 5.

**Files to create**:
- `frontend/src/components/explain/ExplainPanel.tsx` — drawer/inline panel
- `frontend/src/components/explain/ExplainStream.tsx` — renders streaming text progressively
- `frontend/src/hooks/useExplain.ts` — manages SSE fetch, fallback detection, error states

**`useExplain` hook**:
```typescript
function useExplain(kind: 'portfolio' | 'metric' | 'comparison') {
  // Returns: { trigger, text, isStreaming, isFallback, error, rateLimitInfo }
  // trigger(context): initiates the fetch
  // text: accumulated string from SSE chunks
  // isFallback: true when 'fallback: true' SSE field received
  // rateLimitInfo: { limited: true, retryAfterSeconds: number } when 429
}
```

SSE parsing: use `fetch` with `ReadableStream`. Parse lines: `data: {chunk}` appends to text. `event: fallback` sets `isFallback = true`. `event: done` marks streaming complete.

**ExplainPanel**: opened by buttons in `ForecastSection` ("Explain this portfolio"), each cell in `MetricsGrid` ("What does this mean?"), and `CompareShell` ("Explain the tradeoff").

Panel header: "AI-generated · Educational only" in `--color-text-muted` when streaming or complete. When fallback: "Pre-written explanation · Educational only".

Panel body: `<ExplainStream text={text} isStreaming={isStreaming} />`. The stream component renders text as plain paragraphs (no markdown parsing — the system prompt does not produce markdown). A blinking cursor appears at the end while `isStreaming`.

Rate limit state: "You've reached the hourly limit (10 explanations). Available again in N minutes."

**Verification**: with `ANTHROPIC_API_KEY` unset, clicking "Explain this portfolio" opens the panel and shows the fallback text (populated with real numbers from the response). Label reads "Pre-written explanation". With the key set, text streams progressively. Clicking a metric "?" opens the panel with that metric's context. Second identical click on same metric should serve from cache (no new network request — verify in network tab).

---

### Task 16 — Compare page

**What**: Build the compare page.

**Files to update/create**:
- `frontend/src/pages/ComparePage.tsx`
- `frontend/src/components/compare/CompareShell.tsx`
- `frontend/src/components/compare/TierSummaryCard.tsx`
- `frontend/src/components/compare/MetricsComparisonTable.tsx`
- `frontend/src/components/compare/OverlayEquityCurves.tsx`
- `frontend/src/hooks/useCompare.ts`

**Compare form**: same `SteppedPanel` minus Step 3 (risk tier is not relevant — all tiers are run). Or reuse the panel and ignore the risk selection. Simpler: a minimal form — amount, horizon, monthly, advanced options — then "Compare all three tiers" button.

**MetricsComparisonTable**: rows are metrics; columns are Conservative, Balanced, Aggressive. Each cell shows the metric value. Cells in the "best" column for each row are highlighted with `--color-accent-subtle` background. "Best" is defined per metric: for CAGR, best_year, Sharpe, Sortino, Calmar, positive_months → highest value. For volatility, max_drawdown, var_95 → closest to zero (least negative / least volatile). The worst column is highlighted with `--color-loss` at 10% opacity.

**OverlayEquityCurves**: single `<LineChart>` with three `<Line>` components. Colors: `--chart-1`, `--chart-2`, `--chart-3`. Legend. Shared tooltip shows all three values at hovered date. The three series may have slightly different lengths if backtest_years differs — use the longest common x-axis.

**Counterfactual toggle**: a toggle switch labeled "What if I'd started 5 years earlier?" When on, re-submits the compare request with `backtest_years` set to the maximum available minus 5 years (computed from `history_start` in the response). If the existing history is < 6 years, toggle is disabled with tooltip "Insufficient data for this counterfactual."

**Verification**: compare page submits one POST to `/api/compare`. Metrics table renders with 10 rows × 3 columns. Best cells are highlighted. Overlay chart shows three distinct colored lines. Counterfactual toggle changes the chart when enabled.

---

### Task 17 — Universe page

**What**: Build the universe page with 60-second polling and the data status pill.

**Files to create/update**:
- `frontend/src/pages/UniversePage.tsx`
- `frontend/src/components/ui/DataStatusPill.tsx`
- `frontend/src/hooks/useUniverse.ts`
- `frontend/src/api/universe.ts` — update to `/api/universe`

**useUniverse hook**:
```typescript
useQuery({
  queryKey: ['universe'],
  queryFn: () => api.get('/api/universe').then(r => r.data),
  refetchInterval: 60_000,
  refetchIntervalInBackground: false,
  staleTime: 55_000,
})
```

**DataStatusPill**: props `source: 'snapshot' | 'yfinance' | 'synthetic'`, `lastUpdated: string | null`. Visual states:
- `snapshot` or `yfinance`: small green dot + "snapshot · Xs ago" or "live · Xs ago". Background: `--color-accent-subtle`. Text: `--color-text-secondary`.
- `synthetic`: amber warning icon + "synthetic · offline". Background: `rgba(var(--color-warning-rgb), 0.15)`. Text: `--color-warning`. Border: `--color-warning` at 40% opacity.

Must use the word "synthetic" for the synthetic state. Must not use "estimated", "simulated", or "demo" for the data source label.

**Universe table**: columns — Ticker, Name, Asset Class (badge), Expense Ratio, Last Price, Day Change. Price and change use tabular figures (`.num`). Change: `+1.23%` in gain color with ↑ glyph, `-0.45%` in loss color with ↓ glyph. If `change_pct` is absent (yfinance fast_info doesn't always have it), show "—".

**Verification**: page loads with data from `/api/universe`. Network tab shows a request every 60s while the tab is active. Switch to a different browser tab — requests stop. Switch back — requests resume within 60s. If `source === 'synthetic'`, pill is amber with "synthetic · offline" text.

---

### Task 18 — Portfolios (saved simulations) page

**What**: Build the saved portfolios page.

**Files to create/update**:
- `frontend/src/pages/PortfoliosPage.tsx`
- `frontend/src/api/portfolios.ts` — update to `/api/portfolios`

**Page layout**: page header with "Saved Portfolios" and "You can save up to 10 simulations." Grid of cards. Each card:
- Name (editable inline on click)
- Risk tier badge
- Amount + horizon + purpose
- Median projected outcome from `result_json.projection.final_p50`
- Created date (relative: "3 days ago")
- "Load" button — navigates to `/simulator` and hydrates form + result state
- "Delete" button with a confirmation popover ("Delete this portfolio? This cannot be undone.")

Empty state: illustration (SVG or CSS) + "No saved portfolios yet. Run a simulation and click Save."

Cap enforcement: when the user has 10 portfolios, the Save button on the results page is disabled with tooltip "You have reached the 10-portfolio limit. Delete one to save a new one."

**Verification**: save a simulation from the results page. Navigate to portfolios. Card appears. Click "Load" — simulator page opens with the correct inputs pre-filled and the result rendered. Delete the portfolio — card disappears. Attempt to save an 11th — save button is disabled.

---

### Task 19 — Export and print stylesheet

**What**: Add CSV export and a print stylesheet.

**Files to create/update**:
- `frontend/src/utils/export.ts` — `exportAllocationCSV(result)`, `exportBacktestCSV(result)`
- `frontend/src/components/results/ExportButtons.tsx`
- `frontend/src/index.css` — add `@media print` block

**Export**: two separate CSV downloads triggered by two buttons ("Export allocation" and "Export history"). No third-party library — use `Blob` and `URL.createObjectURL`. Allocation CSV columns: Ticker, Name, Asset Class, Weight, Dollars, Shares, Expense Ratio, 1Y Return, 5Y Return. Backtest CSV columns: Date, Balance, Contributed, Drawdown.

**Print stylesheet**: `@media print { nav, .btn, .stepped-panel, .explain-panel { display: none; } .results-shell { width: 100%; } }`. Charts must be visible in print. Page breaks before each results section. Footer disclaimer must print.

**Verification**: "Export allocation" downloads a CSV with the correct headers and correct number of rows (matching allocation.length). "Export history" downloads a CSV. `Ctrl+P` in browser shows a clean print preview with no nav, no buttons, and the disclaimer visible.

---

## Phase 5 — Tests, README, polish

### Task 20 — Backend tests

**What**: Write pytest tests for all endpoints.

**Files to create**:
- `backend/tests/__init__.py`
- `backend/tests/conftest.py` — async test client, test DB (SQLite in-memory), mock engine (patches `load_prices` to return synthetic data)
- `backend/tests/test_auth.py`
- `backend/tests/test_allocate.py`
- `backend/tests/test_compare.py`
- `backend/tests/test_questionnaire.py`
- `backend/tests/test_savings.py`
- `backend/tests/test_explain.py`
- `backend/tests/test_portfolios.py`
- `backend/tests/test_universe.py`
- `backend/tests/test_health.py`

**Install**: `pip install pytest pytest-asyncio httpx` (httpx is already in requirements.txt).

**`conftest.py`** key fixture:
```python
@pytest.fixture
async def client():
    # Override DATABASE_URL to sqlite+aiosqlite:///:memory:
    # Override PS_NO_NETWORK=1
    # Use httpx.AsyncClient with the FastAPI app
    # Yield client
    # Teardown: drop all tables
```

Minimum test count per file:
- `test_auth.py`: 8 tests (register happy, duplicate email, underage, citizenship not attested, wrong password, expired token, refresh, me-requires-auth)
- `test_allocate.py`: 6 tests (happy path, amount ≤ 0, invalid risk, goal present, etf_only, backtest_years)
- `test_compare.py`: 3 tests (all tiers, 2 tiers, data source in response)
- `test_explain.py`: 4 tests (no API key → fallback, rate limit, cache hit, streaming)
- `test_portfolios.py`: 5 tests (save, list, load, delete, cap exceeded)
- Other files: 2+ tests each

**Verification**: `cd backend && pytest tests/ -v` — all tests pass. Zero failures. `python3 test_engine.py` — still 22 passing.

---

### Task 21 — Frontend tests

**What**: Write Vitest + React Testing Library tests.

**Files to create** (co-located as `*.test.tsx`):
- `SteppedPanel.test.tsx` — step navigation, localStorage persistence
- `RiskCards.test.tsx` — renders tier names, metric values, selection
- `QuestionnaireFlow.test.tsx` — renders 5 questions, submits, shows result
- `AllocationTable.test.tsx` — renders rows, sorts on column click
- `MonteCarloFan.test.tsx` — renders with mock data, disclaimer present
- `DataStatusPill.test.tsx` — amber color and "synthetic" text for synthetic source
- `useTheme.test.ts` — cycles states, persists
- `ExplainPanel.test.tsx` — fallback label visible, streams mock text
- `RegisterForm.test.tsx` — checkboxes required, no "verif*" text in DOM

**Install**: `npm install -D vitest @vitest/ui @testing-library/react @testing-library/user-event jsdom`

Add to `frontend/vite.config.ts`:
```typescript
test: {
  environment: 'jsdom',
  globals: true,
  setupFiles: ['./src/test-setup.ts'],
}
```

**Verification**: `npx vitest run` — all tests pass. No snapshot tests (snapshots are fragile; prefer behavior assertions).

---

### Task 22 — README and screenshots

**What**: Replace the existing `README.md` with a complete setup guide and both-theme screenshots.

**README must contain**:
1. One-paragraph description of what the app does and who it's for.
2. Architecture diagram (ASCII or Mermaid).
3. Prerequisites: Python 3.9+, Node 18+, no other system dependencies for dev.
4. Setup steps:
   ```
   # Clone
   cd portfolio-simulator
   # Backend
   cd backend
   pip3 install -r requirements.txt
   cp .env.example .env  # edit ANTHROPIC_API_KEY if desired
   python3 -m uvicorn app.main:app --reload --port 8000
   # Frontend (new terminal)
   cd frontend
   npm install
   npm run dev
   # Open http://localhost:5173
   ```
5. Environment variables table: `ANTHROPIC_API_KEY` (optional, explain fallback), `PS_NO_NETWORK` (set to 1 for fully offline mode), `DATABASE_URL` (default: SQLite).
6. Running tests: `python3 test_engine.py`, `cd backend && pytest tests/`, `cd frontend && npx vitest run`.
7. Two screenshots: dark theme (results page showing fan chart), light theme (same page). Screenshots stored at `docs/screenshot-dark.png` and `docs/screenshot-light.png`.
8. Data sources section: explains the three-tier loading model and what the synthetic fallback is.
9. Disclaimer: "This is an educational simulator. Not financial advice."

**Verification**: a person who has never seen this repo can follow the README and have the app running in under 10 minutes. The README mentions `python3` not `python` (per hard constraint). No Windows-specific path syntax.

---

## Completion checklist

Before declaring the build done, verify every item:

- [ ] `python3 test_engine.py` → 22/22 passing
- [ ] `cd backend && pytest tests/ -v` → all passing
- [ ] `cd frontend && npx vitest run` → all passing
- [ ] `npm run build` → 0 errors, 0 TypeScript errors
- [ ] `grep -r '#[0-9a-fA-F]\{3,6\}' frontend/src/` → 0 results (no hardcoded hex)
- [ ] `grep -ri "verif" frontend/src/pages/AuthPage.tsx frontend/src/pages/RegisterPage.tsx` → 0 results
- [ ] `grep -ri "per-second\|every second\|setInterval.*1000\|refetchInterval.*< 60" frontend/src/` → 0 results
- [ ] Theme toggle persists across hard reload, no white flash
- [ ] App runs with `PS_NO_NETWORK=1` — synthetic pill visible, all calculations work
- [ ] App runs with `ANTHROPIC_API_KEY` unset — explain panel shows fallback text
- [ ] Disclaimer text "Simulated results based on historical data. Educational use only. Not financial advice." appears in the Monte Carlo chart view (grep DOM in test)
- [ ] All 15 assets appear on universe page
- [ ] Allocation weights in results sum to 100% (±1% due to rounding)
- [ ] No console errors in browser on first load, after theme toggle, after simulation
