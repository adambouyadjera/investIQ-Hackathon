# Portfolio Strategy Simulator

A full-stack investment strategy simulator with real market data, historical backtests, and Monte Carlo projections.

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python · FastAPI · SQLAlchemy (async) · APScheduler |
| Database | PostgreSQL (Docker) · SQLite (local dev) |
| Analytics engine | Python · NumPy · Pandas · yfinance |
| Market data | Polygon.io · Alpha Vantage · yfinance (3-source waterfall) |
| Frontend | React 18 · TypeScript · Tailwind CSS · Recharts |
| Auth | JWT (access + refresh tokens) · bcrypt |
| Infrastructure | Docker Compose |

## Features

- Portfolio simulation with allocation, historical backtest, and Monte Carlo projection
- Three risk tiers: Conservative · Balanced · Aggressive
- Side-by-side strategy comparison
- Income-based savings recommendation (50/30/20 rule)
- Risk tolerance questionnaire (5 questions → recommended tier)
- Saved scenarios (up to 10 per user)
- Export simulation results as JSON
- Live market quote refresh every 5 minutes (Polygon → Alpha Vantage → yfinance)
- Age + US citizenship verification on registration

### Risk desk (`trading/`)
- Pre-trade risk gate with a circuit-breaker cascade (1% per trade, daily/weekly/monthly/peak limits)
- Position sizing derived from stop distance — a strategy cannot name its own size

### Agent desk (`agent/`) — paper trading only
- Explainable scoring: five quantitative features + news sentiment, every contribution shown
- Point-in-time features and headlines, with a one-bar execution lag
- Realistic costs: commission, spread, slippage, borrow
- Benchmarked against buy-and-hold, with a deflated-Sharpe penalty for multiple testing
- Walk-forward split reporting in-sample and out-of-sample separately
- **No live mode.** No broker client, no credentials, no order submission

## Quick Start (Local Dev)

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
cp .env .env  # edit values if needed
python -m uvicorn app.main:app --reload --port 8000
```

The backend uses SQLite by default (`dev.db`) so no Postgres needed for local dev.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

App runs at http://localhost:5173

### 3. Full Stack with Docker (includes PostgreSQL)

```bash
# Copy and set env vars
cp backend/.env .env  # or set ALPHA_VANTAGE_KEY, POLYGON_KEY in environment

docker-compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Running the engines directly (no server needed)

```bash
python test_engine.py       # 20 tests — allocation, backtest, Monte Carlo
python test_trading.py      # 42 tests — the risk gate and its boundaries
python test_agent.py        # 49 tests — the paper desk, lookahead and honesty checks

python run_demo.py          # portfolio simulation walkthrough
python run_risk_demo.py     # 10 risk-gate scenarios
python run_agent_demo.py    # agent scan, backtest and walk-forward
```

See [TRADING.md](TRADING.md) for the risk layer and [AGENT.md](AGENT.md) for the
paper-trading desk.

## Market Data Sources

The platform uses a 3-source waterfall:

1. **Polygon.io** — real-time quotes (set `POLYGON_KEY`)
2. **Alpha Vantage** — 15-min delayed quotes (set `ALPHA_VANTAGE_KEY`)
3. **yfinance** — always-available fallback, best for historical data

Without API keys, yfinance is used exclusively — fully functional, just not real-time.

## API Reference

All endpoints (except `/health` and `/auth/*`) require `Authorization: Bearer <token>`.

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get tokens |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Current user |
| POST | `/portfolio/simulate` | Run simulation |
| POST | `/portfolio/compare` | All 3 tiers at once |
| POST | `/portfolio/savings` | Income → investment recommendation |
| POST | `/portfolio/questionnaire` | Score risk questionnaire |
| GET | `/portfolio/questions` | Get questionnaire questions |
| GET | `/market/quotes` | Live quote cache |
| GET | `/risk/policy` | The risk constitution |
| POST | `/risk/evaluate` | Run one proposal through the gate |
| GET | `/agent/config` | Agent weights, thresholds, risk limits |
| POST | `/agent/scan` | Today's proposals, fully decomposed |
| POST | `/agent/backtest` | One window vs benchmark, with significance |
| POST | `/agent/walk-forward` | In-sample and out-of-sample, reported apart |
| GET | `/agent/regime` | Recent market-regime labels |
| GET | `/scenarios/` | List saved scenarios |
| POST | `/scenarios/` | Save a scenario |
| DELETE | `/scenarios/{id}` | Delete a scenario |

## Disclaimer

This platform is for educational purposes only. All projections are based on
historical data and do not constitute financial advice. Past performance does
not guarantee future results. Available to US residents only.

**No real-money trading.** The agent desk is a simulation. There is no broker
connection, no API credential and no live mode anywhere in this codebase, and a
test enforces that (`test_agent.py::no_broker_imports_anywhere`). The
backtested strategy shipped here **does not beat buy-and-hold** over the tested
window, and its deflated Sharpe ratio does not clear the significance hurdle —
see [AGENT.md](AGENT.md) for the full numbers. No claim of predictive accuracy
is made or implied.
