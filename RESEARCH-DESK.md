# InvestIQ research desk

The website now includes a BTC/USDT research dashboard, strategy comparisons, local machine-learning experiments, and an isolated paper account for each user. Its design follows your dark sidebar reference.

**Current decision: wait in cash.** Seventy configurations and six validation candidates were examined; none passed all checks. The paper bot is built, but there is no qualified strategy to trade. Its funds and fills are simulated. No live exchange account is connected.

## Open locally
On this Mac, the running preview is http://localhost:5173/research. If asked to sign in, choose “Try the guest demo”, then “Research” in the navigation. The page offers Overview, Autopilot, Journal, Your brief, Limits and Markets. “Backtest” shows actual validation curves; “Paper” shows your virtual account. Start/pause and market checks work against the local service.

## Run a fresh copy
Requires Python 3.12+, Node 22+ and npm. From the app folder:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt -r requirements-research.txt
cd backend
CORS_ORIGINS=http://localhost:5173,http://localhost:5173 ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, from the app folder:

```sh
cd frontend
npm ci
INVESTIQ_API_URL=http://localhost:8000 npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

No API key is needed for the BTC desk. The source package excludes credentials and user databases. This is a local development application; public deployment is a separate step.

## Hourly research
The Codex task on this Mac is configured to continue hourly. It needs the Mac and Codex to be available and consumes the existing Codex account allowance. The desk uses free public data and local models, with no paid LLM calls or Trader.dev credits. To run data/paper maintenance manually, from the app root:

```sh
.venv/bin/python -m desk.hourly
```

The web service monitors paper accounts every minute while running. Automated strategy research is handled by the Codex task, not by a paid AI service embedded in the website.

The full methodology and failed tests are in `reports/research-journal.md`. Frozen development/validation evidence is preserved; the final holdout has not been opened. Backtests include fees and slippage. Historical performance does not establish future profitability.
