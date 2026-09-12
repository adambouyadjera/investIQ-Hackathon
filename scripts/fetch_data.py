#!/usr/bin/env python3
"""Download real price history into data/prices.csv.

    pip install yfinance
    python scripts/fetch_data.py --years 12

Run this once on your own machine. After it succeeds every other part of the
project reads the snapshot and never touches the network — which is what you
want five minutes before a demo.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data import SNAPSHOT, _try_yfinance, DATA_DIR
from engine.universe import TICKERS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=12)
    args = ap.parse_args()

    print(f"downloading {len(TICKERS)} tickers, {args.years}y of daily closes...")
    df = _try_yfinance(args.years)
    if df is None:
        print("FAILED. Check that yfinance is installed and you have a connection.")
        print("The app still runs — it will fall back to synthetic data.")
        return 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(SNAPSHOT)
    print(f"wrote {SNAPSHOT}  ({len(df)} rows, "
          f"{df.index[0].date()} -> {df.index[-1].date()})")
    print("\nlatest closes:")
    for t, v in df.iloc[-1].items():
        print(f"  {t:<6} {v:>10.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
