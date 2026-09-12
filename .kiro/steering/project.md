---
inclusion: always
---

# Portfolio Strategy Simulator — Project Steering

## Hard constraints

These are **non-negotiable**. Any task or design decision that violates one is wrong and must be revised before proceeding.

### 1. No LLM output is ever used as a number
Every figure that appears in the UI — weights, dollar amounts, returns, volatility, probabilities — comes from the deterministic Python engine (`engine/`). The model writes prose only. If a design decision would route a number through a model, reject it unconditionally. The `/api/explain` endpoint passes pre-computed figures _into_ the prompt as structured JSON; it must not extract or transform those figures in any way.

### 2. No per-second data polling
Risk tiers are functions of volatility measured over years. Recomputing them every second returns identical output thousands of times an hour, burns rate limits, and costs money. Quotes refresh on a **60-second interval** while the browser tab is focused, pause when it is not (use `document.visibilitychange`), and are served from a **server-side in-process cache**. No client-side polling faster than 60 seconds anywhere in the codebase.

### 3. One market data provider, snapshotted
`yfinance` → cached to `data/prices.csv` → synthetic fallback. No other providers. The engine's `load_prices()` three-tier logic is the only place prices are fetched. The UI must display a data-status pill showing source name and last-refresh timestamp. When the synthetic fallback is active, the pill must be visually distinct (amber/warning color) and must use the word "synthetic" — not "estimated" or "simulated".

### 4. Disclaimer on every projection screen
Every screen showing projected or simulated figures must carry: **"Simulated results based on historical data. Educational use only. Not financial advice."** This disclaimer must be non-dismissible, must appear in the footer of every results view, and must also appear inline on the projection (Monte Carlo fan) chart.

### 5. Age and citizenship are self-attested, not verified
The registration checkboxes are self-attestation. The code and UI must never use the word "verification" or "verified" in reference to age or citizenship. Use "confirmed" or "attested." The User model field is `citizenship_attested`, not `is_us_citizen` (migration required for new schema going forward; existing backend code uses `is_us_citizen` — note this discrepancy when referencing the existing auth router).

### 6. Scope discipline
No live trading, no options chains, no order entry, no social feed, no news sentiment, no crypto. If a proposed feature does not directly serve the core loop — **inputs → allocation → evidence → projection** — cut it.

### 7. AI integration is server-side only and degrades gracefully
The Anthropic API key never reaches the browser. The `/api/explain` endpoint is the only place the model is called. The app must be fully usable with the Anthropic key absent: the explain endpoint falls back to a static template that is pre-written and ships with the codebase.

---

## Engine contract

The analytics engine at `engine/` has 20 passing tests (`python test_engine.py`). It is a **fixed dependency**. Do not modify it without:
1. Documenting the change in `design.md` with an explicit justification.
2. Confirming `python test_engine.py` still passes after the change.

Key invariants the rest of the codebase depends on:
- `allocate.build()` returns a fully JSON-serializable dict.
- `load_prices()` returns `(DataFrame, source_str)` where source is one of `"snapshot"`, `"yfinance"`, `"synthetic"`.
- All metrics are computed from the actual price series, not from `mu`/`sigma` parameters.
- `target_weights(risk, horizon_years)` always sums to 1.0 and all weights are positive.

---

## Stack constraints

| Layer | Required |
|---|---|
| Backend | FastAPI, Pydantic v2, SQLAlchemy async, SQLite (Postgres-compatible schema) |
| Auth | JWT (access + refresh), passlib bcrypt, bcrypt pinned to 4.0.1 for Python 3.9 compatibility |
| Frontend | React 18 + TypeScript + Vite, Recharts, TanStack Query, React Router |
| Styling | CSS custom properties only — no CSS-in-JS, no hardcoded hex values in component files |
| AI | Anthropic API, server-side only, streamed response |
| Tests | pytest (backend), Vitest + React Testing Library (frontend) |

---

## Theming invariant

Three states: `dark`, `light`, `system`. The chosen theme must be written to `localStorage` and read back before first paint via an inline `<script>` tag in `index.html`, setting `data-theme` on `<html>`. No white flash. Both themes must pass WCAG AA contrast.

---

## Data freshness model

- **Daily closes** drive all backtests and metrics. Refreshed by a scheduled job once per day. Do not imply finer resolution than this anywhere in the UI.
- **Live quotes** (universe page only): 60-second polling, tab-visibility-gated, server-side cache. The UI shows source + last-refresh timestamp.
- **Synthetic fallback**: app must run end-to-end offline and say so clearly.

---

## Path notes

- Project root: `/Users/myriambouayad/portfolio-simulator/`
- Engine: `engine/` (relative to root) — import as `from engine import allocate`
- Backend app: `backend/app/` — run from `backend/` with `python3 -m uvicorn app.main:app`
- Frontend: `frontend/` — run with `npm run dev` from `frontend/`
- Python command on this machine: `python3` (not `python`)
