# Portfolio Strategy Simulator — Engine

Day 1, hours 1–5. Pure Python. No web server, no database, no frontend.
If the numbers here are wrong, nothing built on top of it matters.

## Run it

```bash
pip install -r requirements.txt
python test_engine.py                      # 20 tests, should all pass
python scripts/fetch_data.py --years 12    # real data -> data/prices.csv
python run_demo.py --amount 25000 --horizon 20 --risk aggressive --monthly 500
python run_demo.py --compare --amount 25000 --horizon 20
python run_demo.py --income 5200 --essentials 2900
```

## Layout

| File | What it owns |
|---|---|
| `engine/universe.py` | The 15 tickers, asset classes, expense ratios |
| `engine/data.py` | Price loading: snapshot → yfinance → synthetic fallback |
| `engine/portfolios.py` | Three model portfolios + the horizon glide path |
| `engine/metrics.py` | CAGR, vol, Sharpe, Sortino, max drawdown, Calmar, VaR |
| `engine/backtest.py` | Contributions, rebalancing, fee drag |
| `engine/montecarlo.py` | Block-bootstrap forward projection |
| `engine/allocate.py` | Top-level `build()`, savings capacity, risk questionnaire |

## Three decisions worth defending in an interview

**Fixed universe, fixed weight vectors.** Every portfolio is a weight vector
over the same 15 assets. That makes comparison, rebalancing and backtesting
one code path instead of three. No optimizer, because a mean-variance
optimizer fit on 12 years of data produces confidently wrong answers.

**Horizon overrides stated risk tolerance.** `portfolios.target_weights`
blends the chosen tier toward a capital-preservation anchor as the horizon
shortens. Someone investing aggressively for a 2-year goal gets ~24% equity,
not 87%. This is the real finance in the project.

**Block bootstrap, not IID normals.** `montecarlo.project` resamples
contiguous 21-day blocks of actual history. That preserves fat tails and
volatility clustering. Drawing from a normal distribution would systematically
understate the odds of a bad decade — the exact number a user cares about.

## Data sourcing

One source (`yfinance`), snapshotted to CSV, with a deterministic synthetic
generator as a last resort. `load_prices()` returns the source it used so the
UI can label it. Reconciling multiple vendors' prices and ticker conventions
is days of work for no visible benefit at this scale.

## Deliberately not here

Per-second updates, LLM-generated numbers, options data, live trading.
Risk tiers are a function of volatility measured over years; recomputing them
every second produces identical output thousands of times an hour. When the
LLM goes in (day 2), it writes the plain-English explanation of a portfolio
that the deterministic code already chose. It never produces a number.

## Next

FastAPI over `allocate.build()` — `/universe`, `/allocate`, `/backtest`,
`/project`, `/compare`. `build()` already returns JSON-serializable output, so
the route handlers are near-trivial.

---

Simulated results based on historical data. Educational use only.
Not financial advice.
