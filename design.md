# Design

Portfolio Strategy Simulator — v2  
Status: **DRAFT — awaiting review**

---

## 1. Guiding principles

**Show the reasoning, not just the recommendation.** Every number on screen has a traceable path back to the engine. Every design decision answers the question: does this help a retail investor understand *why* this allocation was chosen?

**The engine is the source of truth.** The backend API is a thin authentication and routing layer. The frontend is a rendering layer. Neither computes anything financial.

**Degrade gracefully at every boundary.** yfinance unavailable → synthetic fallback with visible indicator. Anthropic unavailable → static template. Backend unreachable → cached state with error banner. No silent failures.

---

## 2. System architecture

```
Browser
  └── React SPA (Vite, port 5173 in dev)
        ├── TanStack Query  — server state, polling, caching
        ├── React Router    — client-side routing
        └── CSS variables   — theming (dark/light/system)

        ↕ HTTP/SSE  (proxied through Vite dev server → port 8000)

FastAPI app  (port 8000)
  ├── /api/auth/*          — JWT register/login/refresh/me
  ├── /api/universe        — 15-asset metadata + cached quotes
  ├── /api/questionnaire   — risk questions + scoring
  ├── /api/savings-capacity
  ├── /api/allocate        — wraps allocate.build()
  ├── /api/compare         — wraps allocate.build() × 3
  ├── /api/explain         — Anthropic prose (SSE stream)
  ├── /api/portfolios      — saved simulations CRUD
  └── /api/health          — source + last-refresh timestamp

  ├── APScheduler          — daily price refresh (once/day, not per-second)
  ├── in-process TTL cache — 60s quote cache (server-side, no client polling faster than 60s)
  └── SQLite (dev) / Postgres-compatible schema (prod)

engine/  (Python, fixed dependency)
  └── allocate.build() → all numbers
```

### What exists vs. what this spec builds

The prior session built a working prototype. This spec **rebuilds the surface layer** (API routes, frontend) to meet the quality bar. The engine is untouched except for the two additions documented in Section 9.

---

## 3. Backend design

### 3.1 URL structure

All routes move to `/api/` prefix. The existing routers are restructured into a single `api/` router tree. Frontend vite proxy and nginx config update accordingly.

```
/api/auth/register      POST
/api/auth/login         POST
/api/auth/refresh       POST
/api/auth/me            GET

/api/universe           GET   — 15 assets + cached quotes + data status
/api/questionnaire      GET   — QUESTIONS list
/api/questionnaire/score  POST — answers → {score, max_score, percentile, risk_tier}

/api/savings-capacity   POST  — income inputs → recommendation + warnings

/api/allocate           POST  — main simulation call
/api/compare            POST  — 2–3 tiers over identical inputs

/api/explain            POST  — SSE stream of AI prose (or static fallback)

/api/portfolios         GET   — saved portfolios for authed user
/api/portfolios         POST  — save a portfolio (cap 10)
/api/portfolios/{id}    GET   — load one saved portfolio
/api/portfolios/{id}    DELETE

/api/health             GET   — {status, data_source, last_price_refresh, last_quote_refresh, version}
```

### 3.2 Pydantic models (request/response)

Every endpoint has explicit Pydantic v2 request and response models. No endpoint returns a raw dict or passes a raw exception as a response. Validation errors return `422` with a structured `{detail: [{field, message}]}` shape. Internal errors return `500` with `{detail: "Internal error", request_id: str}` — no stack traces in production responses.

Key models:

**`AllocateRequest`**
```python
class AllocateRequest(BaseModel):
    amount: float = Field(gt=0, le=10_000_000)
    horizon_years: float = Field(gt=0, le=50)
    risk: Literal["conservative", "balanced", "aggressive"]
    monthly_contribution: float = Field(ge=0, default=0.0)
    rebalance: Literal["never", "quarterly", "annual"] = "annual"
    extra_fee: float = Field(ge=0, le=0.05, default=0.0)
    goal: float | None = Field(default=None, gt=0)
    etf_only: bool = False   # filters single stocks from allocation
    backtest_years: int | None = Field(default=None, ge=3, le=20)
    purpose: Literal["retirement", "house", "education", "general"] | None = None
```

**`AllocateResponse`** — typed wrapper around the engine's dict output, using `model_validate` on the raw dict. This gives the frontend OpenAPI-generated types for free and prevents any untyped dict from leaking out.

**`ExplainRequest`**
```python
class ExplainRequest(BaseModel):
    kind: Literal["portfolio", "metric", "comparison"]
    # The figures below are ALL pre-computed by the engine. The LLM receives
    # exactly this dict as structured context; it does not compute anything.
    allocation_context: dict      # subset of AllocateResponse
    metric_name: str | None = None
    comparison_context: dict | None = None
    purpose: str | None = None    # "retirement" etc., shown in prose
```

**`HealthResponse`**
```python
class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    data_source: Literal["snapshot", "yfinance", "synthetic"]
    last_price_refresh: datetime | None
    last_quote_refresh: datetime | None
    quote_count: int
```

### 3.3 Auth

The existing auth logic is correct and reused. One field rename on the User model: `is_us_citizen` → `citizenship_attested`. This is a schema migration — one `ALTER TABLE` in an Alembic revision. The register endpoint's validator text changes from "verified" to "attested."

JWT access tokens: 24h. Refresh tokens: 30d. Both in `Authorization: Bearer` header. No token in URL. No token in localStorage for the access token — store in memory (React state) and use the refresh token in a `httpOnly` cookie if security is a concern in later iterations. For this build: keep the existing localStorage approach (it is what the existing API client already does), document the tradeoff.

Rate limiting on `/api/explain`: in-process sliding window counter keyed by `user_id`, 10 requests per hour. No external Redis needed for the traffic levels this app will see.

### 3.4 Data freshness implementation

**Daily price refresh** — APScheduler `cron` job at 06:00 UTC (after market close, before US market open). Calls `load_prices(allow_network=True)` which downloads via yfinance and writes `data/prices.csv`. On failure, the snapshot remains. The `last_price_refresh` timestamp in `/api/health` reflects the last successful write.

**Quote cache** — The 60-second quote cache from the prior session is largely correct. One change: the scheduler interval changes from 5 minutes to **60 seconds**, but the job only fires `_fetch_yfinance_batch()` (the non-rate-limited path). The multi-provider waterfall (Polygon → AlphaVantage) is removed — one provider, as required by the hard constraints. The `refresh_quotes()` function becomes a simple yfinance fast_info batch call.

**Tab-visibility gating** — This is a frontend responsibility. The React hook that polls the universe endpoint uses `document.addEventListener('visibilitychange', ...)` to pause polling when the tab is hidden and resume when it becomes visible.

### 3.5 AI explain endpoint

This is an SSE (Server-Sent Events) endpoint, not a WebSocket.

```
POST /api/explain
Content-Type: application/json
Authorization: Bearer <token>

→ text/event-stream
```

**Flow:**
1. Parse `ExplainRequest`. Validate that `allocation_context` is a dict (not a number, not a string).
2. Check rate limit (10/hour per user). If exceeded, return `429` before opening the stream.
3. Check response cache: SHA-256 hash of `ExplainRequest.model_dump_json()`. If hit, stream the cached response directly (no API call).
4. If `ANTHROPIC_API_KEY` is absent or the API call fails: stream the static fallback template.
5. Otherwise: call `anthropic.messages.stream(...)`, forwarding chunks as SSE `data:` events.
6. On completion: write result to cache (TTL: 24h, in-process dict). Close stream.

**System prompt (exact text, do not modify during implementation):**
```
You are an educational assistant for a portfolio simulator. Your only job is to explain,
in plain English, the investment data you are given. You must:
- Use only the numbers provided in the user message. Do not invent, estimate, or compute any figures.
- Never recommend buying or selling any specific security.
- Never predict future prices or returns.
- Frame everything as educational context, not financial advice.
- Keep your response to 3-4 short paragraphs.
- Reference the actual dollar amounts and percentages from the data.
```

**Static fallback template structure** — one per `kind`:

`portfolio`: "This {risk_label} allocation dedicates {equity_share}% to equities... Over the available history ({history_start} to {history_end}), it returned {cagr}% annually... The worst 12-month period in this history was {worst_year}%, which on a ${amount} portfolio would have meant seeing your balance fall by approximately ${worst_year_dollars}..."

`metric`: "Your {metric_name} of {value} means... Typical ranges for a {risk_label} portfolio are..."

`comparison`: "The main tradeoff between {tier_a} and {tier_b} is... {tier_a} returned {cagr_a}% annually with a worst year of {worst_year_a}%, while {tier_b} returned {cagr_b}% with {worst_year_b}%..."

All figures in the fallback are string-substituted from the request context — no hardcoded numbers.

### 3.6 Database schema

SQLite in dev, Postgres-compatible. One Alembic env with SQLite for test and Postgres for prod.

```sql
-- users (updated from prior session)
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    username    TEXT UNIQUE NOT NULL,  -- max 64 chars
    hashed_password TEXT NOT NULL,
    date_of_birth   DATE NOT NULL,
    citizenship_attested BOOLEAN NOT NULL,  -- renamed from is_us_citizen
    monthly_income  NUMERIC,               -- changed from TEXT to NUMERIC
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- portfolios (renamed from scenarios, one field added)
CREATE TABLE portfolios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,  -- max 120 chars
    risk_tier       TEXT NOT NULL,
    amount          NUMERIC NOT NULL,
    horizon_years   NUMERIC NOT NULL,
    monthly_contribution NUMERIC NOT NULL DEFAULT 0,
    extra_fee       NUMERIC NOT NULL DEFAULT 0,
    goal            NUMERIC,
    purpose         TEXT,                    -- new: "retirement"|"house"|"education"|"general"
    result_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX portfolios_user_id_idx ON portfolios(user_id);
```

Migration strategy: one Alembic revision that renames `is_us_citizen` → `citizenship_attested`, casts `monthly_income` to NUMERIC, renames `scenarios` → `portfolios`, and adds the `purpose` column.

---

## 4. Frontend design

### 4.1 File structure

```
frontend/src/
  index.css           — CSS custom properties (all tokens), global reset
  main.tsx            — theme injection script, React mount
  App.tsx             — router, QueryClient provider
  
  tokens/
    colors.css        — all color tokens (dark + light values)
    typography.css    — scale, families, tabular-nums
    spacing.css       — spacing scale
  
  components/
    ui/               — Button, Input, Select, Slider, Card, Badge, Tooltip,
                        Skeleton, DataStatusPill, Disclaimer
    layout/           — AppShell, Navbar, Sidebar (future)
    charts/           — EquityCurve, DrawdownChart, MonteCarloFan,
                        AllocationDonut, CorrelationHeatmap,
                        CalendarReturns, MetricsGrid
    input/            — SteppedPanel, Step, StepSummary,
                        MoneyStep, TimelineStep, RiskStep,
                        IncomeStep, AdvancedStep,
                        RiskCards, QuestionnaireFlow
    results/          — ResultsShell, AllocationSection, EvidenceSection,
                        ForecastSection, GlidepathPanel, FeeImpact
    explain/          — ExplainPanel, ExplainStream, StaticFallback
    compare/          — CompareShell, MetricsTable, OverlayChart
    auth/             — LoginForm, RegisterForm, AttestationCheckboxes
  
  pages/
    LandingPage.tsx
    SimulatorPage.tsx   — the main flow (input + results)
    ComparePage.tsx
    UniversePage.tsx
    PortfoliosPage.tsx  — saved simulations
    AccountPage.tsx
    AuthPage.tsx        — login/register shell
  
  hooks/
    useAuth.ts
    useSimulate.ts      — wraps TanStack mutation for /api/allocate
    useCompare.ts
    useUniverse.ts      — 60s polling, visibility-gated
    useExplain.ts       — SSE reader + fallback
    useTheme.ts
  
  api/
    client.ts           — axios instance, interceptors
    auth.ts
    simulator.ts        — allocate, compare, savings-capacity
    universe.ts
    questionnaire.ts
    explain.ts          — SSE fetch
    portfolios.ts
  
  store/
    auth.ts             — user state, pub/sub
    theme.ts            — theme state, localStorage sync
  
  types/
    index.ts            — all shared types (expand existing file)
    api.ts              — request/response types that mirror Pydantic models
```

### 4.2 Theming

**Three states**: `dark`, `light`, `system`. Stored in `localStorage` key `ps-theme`. On system, reads `window.matchMedia('(prefers-color-scheme: dark)')`.

**No flash**: `index.html` contains an inline `<script>` before the app bundle that reads localStorage and sets `document.documentElement.setAttribute('data-theme', ...)` synchronously. This runs before any React paint.

```html
<script>
  (function() {
    var t = localStorage.getItem('ps-theme') || 'system';
    var d = t === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : t;
    document.documentElement.setAttribute('data-theme', d);
  })();
</script>
```

**Token structure** — all values in `colors.css`, referenced everywhere else:

```css
:root, [data-theme="dark"] {
  /* Ground */
  --color-bg:           #0f1117;   /* deep blue-shifted charcoal, not pure black */
  --color-bg-elevated:  #161b27;
  --color-surface:      #1e2436;
  --color-surface-2:    #252d42;
  --color-border:       #2e3650;
  --color-border-subtle:#242a3d;

  /* Text */
  --color-text-primary:   #f0f2f7;
  --color-text-secondary: #8b96b0;
  --color-text-muted:     #4e5a72;
  --color-text-inverse:   #0f1117;

  /* Accent — one, used only for primary actions and active state */
  --color-accent:         #6c8ef7;
  --color-accent-hover:   #849af8;
  --color-accent-subtle:  rgba(108, 142, 247, 0.12);

  /* Semantic */
  --color-gain:     #3ecf8e;  /* green; also uses ↑ glyph */
  --color-loss:     #f46b6b;  /* red-orange; also uses ↓ glyph */
  --color-warning:  #e8a84a;  /* amber; used for synthetic pill */
  --color-info:     #60a5fa;

  /* Chart categorical ramp — 8 muted colors, distinct from accent */
  --chart-1: #6c8ef7;
  --chart-2: #3ecf8e;
  --chart-3: #e8a84a;
  --chart-4: #f46b6b;
  --chart-5: #a78bfa;
  --chart-6: #38bdf8;
  --chart-7: #fb923c;
  --chart-8: #4ade80;

  /* Allocation donut rings — asset class colors */
  --color-equity:     #6c8ef7;
  --color-bond:       #3ecf8e;
  --color-real-asset: #e8a84a;
}

[data-theme="light"] {
  --color-bg:           #f4f6fb;
  --color-bg-elevated:  #ffffff;
  --color-surface:      #ffffff;
  --color-surface-2:    #f0f2f7;
  --color-border:       #dde1ec;
  --color-border-subtle:#eaecf4;

  --color-text-primary:   #1a1f2e;
  --color-text-secondary: #4e5a72;
  --color-text-muted:     #8b96b0;
  --color-text-inverse:   #f0f2f7;

  --color-accent:         #4f72f5;
  --color-accent-hover:   #3d62e8;
  --color-accent-subtle:  rgba(79, 114, 245, 0.10);

  --color-gain:     #16a36a;
  --color-loss:     #dc3545;
  --color-warning:  #c97b0a;
  --color-info:     #1d6fa8;

  --chart-1: #4f72f5;
  --chart-2: #16a36a;
  --chart-3: #c97b0a;
  --chart-4: #dc3545;
  --chart-5: #7c3aed;
  --chart-6: #0284c7;
  --chart-7: #ea580c;
  --chart-8: #15803d;

  --color-equity:     #4f72f5;
  --color-bond:       #16a36a;
  --color-real-asset: #c97b0a;
}
```

**No hardcoded hex anywhere in component files.** Chart components read axis/grid/tooltip colors from CSS variables via `getComputedStyle(document.documentElement)` called once per render, not per tick.

**Typography** — `typography.css`:
```css
:root {
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;

  /* Tabular figures for all numeric content */
  --font-feature-tabular: "tnum" 1, "kern" 1;

  /* Type scale */
  --text-xs:   0.75rem;   /* 12px */
  --text-sm:   0.875rem;  /* 14px */
  --text-base: 1rem;      /* 16px */
  --text-lg:   1.125rem;  /* 18px */
  --text-xl:   1.25rem;   /* 20px */
  --text-2xl:  1.5rem;    /* 24px */
  --text-3xl:  2rem;      /* 32px */
}
```

All metric figures in tables and grids use `font-variant-numeric: tabular-nums` — applied via a utility class `.num`, not inline styles.

### 4.3 Stepped input panel

The panel lives in `components/input/SteppedPanel.tsx`. It is a controlled component: all state lives in a `useReducer` in `SimulatorPage.tsx`, passed down as props. This makes the full form state serializable for localStorage persistence.

**State shape:**
```typescript
interface FormState {
  // Step 1
  amount: number;
  monthly_contribution: number;
  goal: number | null;
  // Step 2
  horizon_years: number;
  purpose: 'retirement' | 'house' | 'education' | 'general';
  // Step 3
  risk: 'conservative' | 'balanced' | 'aggressive';
  risk_mode: 'quick' | 'guided';
  questionnaire_answers: Record<string, number>;
  // Step 4
  monthly_take_home: number | null;
  monthly_essentials: number | null;
  emergency_fund: number | null;
  has_high_interest_debt: boolean;
  high_interest_debt_balance: number | null;
  // Step 5
  rebalance: 'never' | 'quarterly' | 'annual';
  extra_fee: number;
  backtest_years: number | null;
  etf_only: boolean;
  // UI state
  open_step: 1 | 2 | 3 | 4 | 5;
  step_complete: Record<1|2|3|4|5, boolean>;
}
```

localStorage key: `ps-form-v1`. Serialized on every `dispatch`. Read on mount via `useEffect` (not synchronously, to avoid hydration issues).

Each step has a **summary line** shown when collapsed:
- Step 1: "$10,000 starting · $500/mo · Goal: $500,000"
- Step 2: "20 years · Retirement"
- Step 3: "Balanced · guided"
- Step 4: "Income on file" or "Not provided"
- Step 5: "Annual rebalance · 0% fee · Max history"

**Risk cards** (Step 3 quick mode): The historical volatility and worst-year figures shown on the cards are fetched once on mount from `/api/universe` (which already computes them server-side from the engine). They are not hardcoded. If the fetch fails, the cards show "--" with a "data unavailable" note and are still selectable.

**Questionnaire flow** (Step 3 guided mode): Questions fetched from `/api/questionnaire`. Rendered as radio groups. After the final answer, `POST /api/questionnaire/score` runs. The result panel shows "Based on your answers: Balanced (score 9/17)" with a small bar. The user can then either accept ("Use Balanced") or override by clicking a different quick card.

### 4.4 Results layout

`SimulatorPage.tsx` shows the stepped panel on the left (sticky, scrollable independently) and the results on the right when a simulation result exists. On mobile (<768px), the panel is full-width and the results render below after "Run Simulation" is clicked, with a back button.

Results are divided into three named sections with visible section headers:

**Section A — The Allocation** (rendered immediately, ~400ms after submit):
- Donut chart (outer ring: individual assets, inner ring: asset class aggregate)
- Allocation table (sortable, sticky header)
- Equity/bond/real-asset stacked bar
- Glide-path explanation panel

**Section B — The Evidence** (same response, collapsible on mobile):
- Equity curve + drawdown chart (shared x-axis, linked hover)
- Calendar-year returns bar chart
- Metrics grid (10 metrics, each with tooltip)
- Correlation heatmap
- Fee impact callout

**Section C — The Forecast** (same response, collapsible on mobile):
- Monte Carlo fan chart with inline disclaimer
- Three headline figures
- Probability stats
- "Explain this portfolio" button → triggers `/api/explain`

### 4.5 Chart implementation details

All charts use **Recharts**. Chart colors come from CSS variables read at render time:

```typescript
// Pattern used in every chart component
function useChartColors() {
  const root = document.documentElement;
  const s = getComputedStyle(root);
  return {
    gain:    s.getPropertyValue('--color-gain').trim(),
    loss:    s.getPropertyValue('--color-loss').trim(),
    accent:  s.getPropertyValue('--color-accent').trim(),
    muted:   s.getPropertyValue('--color-text-muted').trim(),
    border:  s.getPropertyValue('--color-border').trim(),
    chart:   [1,2,3,4,5,6,7,8].map(n =>
               s.getPropertyValue(`--chart-${n}`).trim()),
  };
}
```

This hook is called inside the component, so when the theme changes (data-theme attribute swaps), the next render picks up new values. The hook itself is cheap — `getComputedStyle` is synchronous and fast.

**Skeleton loading**: chart containers have fixed heights. Before data arrives, a `<ChartSkeleton>` component fills the space with an animated shimmer using CSS `@keyframes`. The shimmer uses `--color-surface-2` and `--color-border` only.

**Responsive reflow**: charts use `<ResponsiveContainer width="100%" height={...}>`. On viewports ≤ 480px, chart heights are reduced by 30% via a `useWindowWidth` hook. No horizontal scrolling.

**Equity curve + drawdown shared x-axis**: both charts use the same `data` array (the backtest `series`). They share a `<ReferenceArea>` highlight: hovering over one syncs a `syncId` prop on both `AreaChart` components to show the same x-position tooltip.

**Correlation heatmap**: Recharts does not have a native heatmap. Implement as a positioned grid of `<rect>` elements via a custom `<ComposedChart>` with `Cell` fill mapped to a diverging color scale (interpolated between `--color-loss` at −1 and `--color-gain` at +1, with `--color-surface-2` at 0). The correlation matrix data comes from a new `/api/allocate` response field — see Section 9.

**Monte Carlo fan chart**: Five `<Area>` components (p10, p25, p50, p75, p90) stacked. The p25–p75 band uses `--chart-1` at 20% opacity. The p50 line uses `--chart-1` at full opacity (2px stroke). The p10 and p90 lines use `--color-text-muted` at 1px. Contributions line uses `--color-bond` dashed.

### 4.6 AI explain flow

`useExplain(kind, context)` hook:

1. User clicks "Explain this portfolio" / metric tooltip / "Explain comparison".
2. `ExplainPanel` opens as a right-side drawer (or inline panel below the relevant section).
3. `useExplain` initiates a `fetch` to `/api/explain` with `Accept: text/event-stream`.
4. As SSE `data:` events arrive, each chunk is appended to a `useState` string.
5. The `ExplainPanel` renders the string progressively via `dangerouslySetInnerHTML` — no, via a simple `<pre>` with `white-space: pre-wrap` to avoid XSS.
6. A visible label "AI-generated · Educational only" appears above the text from the first character.
7. If the fetch returns `429`: show "You've reached the hourly limit (10 explanations). Try again in N minutes."
8. If the stream returns a `fallback: true` SSE field: the label changes to "Pre-written explanation · Educational only".

### 4.7 Compare page

Three columns (or two, user-selected). Each column: summary card (risk tier, CAGR, max drawdown, final_p50). Below: a shared metrics table where rows are metric names and columns are tiers — so the user reads left-to-right to compare. Below that: equity curves overlaid on one chart (three lines, one per tier, one color per tier from `--chart-1/2/3`).

"What if I'd started 5 years earlier" toggle: sends `backtest_years: null` (max history) to the first call, `backtest_years: max_available - 5` to the second. The backend computes both; the toggle switches which result is displayed. If 5 years of additional history is not available, a note appears: "Full history used — insufficient data for 5-year counterfactual."

### 4.8 Universe page

Table of all 15 assets. Columns: ticker, name, asset class (badge), expense ratio, last price, day change (signed with ↑/↓ glyph and gain/loss color). Data comes from `GET /api/universe`. The page polls every 60 seconds using TanStack Query's `refetchInterval`, but only when `document.visibilityState === 'visible'`.

```typescript
useQuery({
  queryKey: ['universe'],
  queryFn: fetchUniverse,
  refetchInterval: 60_000,
  refetchIntervalInBackground: false,  // pauses when tab hidden
})
```

`DataStatusPill` component appears in the top-right of the page. Props: `source: 'snapshot' | 'yfinance' | 'synthetic'`, `lastUpdated: Date | null`. When `source === 'synthetic'`, the pill is amber (`--color-warning` background) and reads "synthetic · offline". When live, it reads "snapshot · updated 12s ago" (relative timestamp using `Date.now() - lastUpdated`).

### 4.9 Saved portfolios page

Grid of cards, one per saved portfolio. Each card: name, risk badge, amount, horizon, creation date, median projected outcome (from stored `result_json.projection.final_p50`). Clicking "Load" re-hydrates the full result into `SimulatorPage` (sets form state from `result_json.inputs`, loads `result_json` into results pane). Rename and delete inline.

### 4.10 Landing page

Single screen. Above the fold: headline ("See exactly how your portfolio would have performed"), subheadline ("Enter your amount, timeline, and risk tolerance — we'll show you the historical evidence and a range of possible futures"), CTA button. Below the fold: four feature callouts matching the four result sections. No testimonials, no pricing, no "powered by AI" marketing copy — the tool should speak for itself.

---

## 5. Data flows

### 5.1 Main simulation flow

```
User submits form
  → POST /api/allocate (AllocateRequest)
  → backend: load_prices() [from cache] → allocate.build() → AllocateResponse
  → frontend: TanStack mutation.onSuccess → set result state
  → React renders ResultsShell with three sections
  → User may click "Save" → POST /api/portfolios
  → User may click "Explain" → POST /api/explain → SSE stream
```

### 5.2 Quote refresh flow

```
UniversePage mounts
  → TanStack query, refetchInterval=60000, refetchIntervalInBackground=false
  → every 60s (while tab visible): GET /api/universe
  → backend returns cached quotes (updated by APScheduler every 60s)
  → frontend updates prices in table
  → DataStatusPill updates relative timestamp
```

### 5.3 Theme flow

```
index.html inline script runs before React
  → reads localStorage('ps-theme')
  → sets data-theme on <html>
  → no flash

ThemeToggle click
  → updates localStorage
  → updates data-theme attribute
  → CSS variables swap instantly
  → chart color hook returns new values on next render
```

---

## 6. Error handling

| Scenario | Backend | Frontend |
|----------|---------|----------|
| Invalid form input | 422 with field-level detail | Inline field error, form not submitted |
| Engine raises ValueError | 400 with detail | Error banner in results area with "try different inputs" |
| Engine raises unexpected exception | 500 with request_id | Generic error banner with request_id for support |
| Auth token expired | 401 | API client auto-refreshes; on refresh failure, redirect to /login |
| Rate limit exceeded (explain) | 429 with retry_after | ExplainPanel shows time until reset |
| Anthropic API unavailable | 200 (stream static fallback) | Fallback label shown, no error state |
| yfinance unavailable | 200 (synthetic data) | Synthetic pill shown |
| Network completely offline | fetch error | "Unable to connect — check your connection" banner; cached results remain visible |

---

## 7. Testing strategy

### Backend (pytest)

Location: `backend/tests/`

Coverage target: every endpoint, all validation paths, auth failures.

Key test cases:
- `test_auth.py`: register happy path, duplicate email, underage, citizenship not attested, wrong password, expired token, refresh, me.
- `test_allocate.py`: valid request, amount ≤ 0, invalid risk, bad horizon, etf_only flag, backtest_years param, goal present/absent.
- `test_compare.py`: 2 tiers, 3 tiers, identical data source across tiers.
- `test_explain.py`: valid request, rate limit, no API key (fallback), cache hit.
- `test_portfolios.py`: save, list, load one, delete, cap exceeded.
- `test_universe.py`: returns all 15 assets, data_source in response.
- `test_health.py`: structure, data_source field.

All tests run with `PS_NO_NETWORK=1` (synthetic data, no network calls). The existing 20 engine tests continue to pass unchanged.

### Frontend (Vitest + RTL)

Location: `frontend/src/**/__tests__/` or `frontend/src/**/*.test.tsx`

Key test cases:
- `SteppedPanel`: step navigation, localStorage persistence, summary line render.
- `RiskCards`: renders tier names and metric values, selection state.
- `QuestionnaireFlow`: renders questions, submits answers, shows result.
- `AllocationTable`: renders and sorts.
- `MonteCarloFan`: renders with data, shows disclaimer.
- `DataStatusPill`: correct color for synthetic source.
- `useTheme`: toggle cycles through states, persists to localStorage.
- `useExplain`: SSE mock, fallback path, rate-limit path.
- `ExplainPanel`: label shows, streams text.
- `ThemeToggle`: no white flash (test that data-theme is set before paint).
- Auth forms: validation messages, attestation checkboxes required.

---

## 8. Build order

The required build sequence (from requirements.md Section 7) maps to these concrete steps:

1. **API skeleton** — restructure existing routers under `/api/` prefix, add `/api/health` with data status, write Pydantic request/response models for all endpoints.

2. **Engine additions** — add `return_1y`, `return_5y` to allocation items; add `correlation_matrix` field to build output; add `asset_portfolio_correlation` to `metrics.py`. Add two new tests to `test_engine.py`.

3. **Alembic migration** — rename fields, add `portfolios.purpose`, add missing indexes.

4. **Frontend skeleton** — replace existing CSS with token files, add theme-injection script to `index.html`, implement `ThemeToggle`, verify no flash.

5. **Stepped input panel** — `SteppedPanel` + five Step components, localStorage persistence, form validation with React Hook Form + Zod.

6. **Wiring to /api/allocate** — `useSimulate` hook, TanStack Query mutation, loading skeleton for results area.

7. **Allocation section** — donut chart, table, stacked bar, glide-path panel.

8. **Evidence section** — equity curve + drawdown (shared x-axis), calendar returns, metrics grid with tooltips, correlation heatmap, fee impact.

9. **Forecast section** — Monte Carlo fan chart with inline disclaimer, headline figures, probability stats.

10. **Auth pages** — register with attestation checkboxes (not "verification"), login, JWT flow, ProtectedRoute.

11. **Explain endpoint + UI** — SSE endpoint with system prompt, rate limiter, cache, static fallback; `ExplainPanel`, `useExplain` hook.

12. **Compare page** — metrics table, overlay chart, counterfactual toggle.

13. **Universe page** — table, `DataStatusPill`, 60s polling with visibility gate.

14. **Portfolios page** — save, list, load, delete, cap enforcement.

15. **Export + print** — CSV download, `@media print` stylesheet.

16. **Backend tests** — `pytest backend/tests/`.

17. **Frontend tests** — Vitest + RTL.

18. **README + screenshots** — setup steps, both themes.

---

## 9. Engine additions (the only permitted changes)

This section documents every change to `engine/`. Zero changes to existing functions. Two additions only.

### 9.1 Per-asset historical returns in `allocate.build()`

**Why**: The allocation table (R-6.2) needs 1-year and 5-year return for each held asset. These cannot be added on the frontend without re-downloading price data. The engine already has the prices loaded.

**Change**: In `engine/allocate.py`, in `build()`, after the `latest = prices.iloc[-1]` line:

```python
_rets = daily_returns(prices)  # already computed implicitly in backtest.run; explicit here

for item in allocation:
    t = item["ticker"]
    if t in _rets.columns:
        r1_series = _rets[t].iloc[-252:]
        r5_series = _rets[t].iloc[-1260:]
        item["return_1y"] = round(float((1 + r1_series).prod() - 1), 5)
        item["return_5y"] = round(float((1 + r5_series).prod() - 1), 5)
    else:
        item["return_1y"] = None
        item["return_5y"] = None
```

`daily_returns()` is already imported in `allocate.py` via `from .data import load_prices, portfolio_returns`. We add `daily_returns` to that import.

**Effect on existing tests**: `t_build_allocation_sums` passes unchanged (it checks `weight`, `dollars`, `shares`, `price` — not per-asset returns). `t_json_serializable` passes because `None` is JSON-serializable. All other tests unaffected.

**New test**: `t_build_returns_present` — asserts that every allocation item has `"return_1y"` and `"return_5y"` keys, and that both values are floats (not None) when using full synthetic price history (which has enough data).

### 9.2 Correlation matrix in `allocate.build()`

**Why**: The correlation heatmap (R-7.5) requires pairwise correlations among held assets. Computing this client-side would require shipping the raw price series to the browser, which is unnecessary bandwidth.

**Change**: In `engine/allocate.py`, add to the `build()` return dict:

```python
from .metrics import correlation_matrix  # already defined in metrics.py

held_tickers = [item["ticker"] for item in allocation]
corr = correlation_matrix(_rets[held_tickers])
# convert to a JSON-serializable nested dict
corr_dict = {
    row: {col: round(float(corr.loc[row, col]), 4) for col in held_tickers}
    for row in held_tickers
}
# add to return dict:
"correlation_matrix": corr_dict
```

`correlation_matrix()` is already defined in `engine/metrics.py`. This change just calls it and formats the output.

**Effect on existing tests**: `t_json_serializable` passes because the dict is fully serializable. All other tests unaffected.

**New test**: `t_build_correlation_matrix` — asserts the matrix is square, diagonal values are 1.0 (within 1e-9), and all values are in [−1, 1].

### 9.3 Confirmation that engine tests still pass

After both additions, run `python3 test_engine.py`. Expected: 22 passing (20 original + 2 new). This must be verified before any frontend work begins that depends on the new fields.

---

## 10. Decisions and tradeoffs

| Decision | Alternative considered | Reason chosen |
|----------|----------------------|---------------|
| SSE for explain endpoint | WebSocket | SSE is unidirectional, simpler, HTTP-native, works with standard `fetch` |
| In-process rate limiter | Redis | Avoids infrastructure dependency; adequate for the traffic level |
| In-process explain cache | Redis / DB | Same reasoning; cache is warm-per-process, acceptable for this scale |
| localStorage for form state | sessionStorage / URL params | Survives page refresh, survives navigation; user can return to their inputs |
| TanStack Query | SWR / manual fetch | More capable (mutations, background refetch, retry), already in spec |
| Recharts | D3 / Nivo | Simpler React integration, sufficient feature set, no canvas |
| Correlation heatmap as custom Recharts | third-party heatmap lib | Avoids a dependency; relatively small implementation |
| SQLite dev / Postgres prod | SQLite only | Postgres column types (JSONB, UUID, TIMESTAMPTZ) are better; schema is identical |
| Token in localStorage | httpOnly cookie | Cookie approach is more secure; localStorage is simpler; noted as upgrade path |
| `bcrypt==4.0.1` pin | latest bcrypt | Python 3.9 + passlib 1.7.4 compatibility; see existing backend notes |

---

## 11. What is explicitly not designed here

- Email verification / SMTP (noted in existing code as future work)
- Push notifications
- Multiple market data providers
- Any financial calculation outside the engine
- Any LLM output used as a number
- Any polling faster than 60 seconds
