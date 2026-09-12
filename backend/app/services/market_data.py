"""Real-time market data service.

Priority order:
  1. Polygon.io  — real-time (needs paid key for streaming; free tier = delayed)
  2. Alpha Vantage — 15-min delayed quotes, 25 req/day free
  3. yfinance    — always works, best for batch history refresh

Cache: in-memory dict, refreshed every 5 minutes during market hours.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timezone
from typing import Optional

import aiohttp

from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory quote cache: { ticker: { price, change_pct, last_updated } }
_quote_cache: dict[str, dict] = {}
_last_refresh: Optional[datetime] = None
_refresh_lock = asyncio.Lock()

MARKET_TICKERS = [
    "VTI", "VXUS", "QQQ", "VBR", "AAPL", "MSFT", "NVDA",
    "JNJ", "JPM", "BND", "TLT", "TIP", "BIL", "GLD", "VNQ",
]


def _is_market_hours() -> bool:
    """Rough check: NYSE hours Mon–Fri 9:30–16:00 ET (UTC-4 in summer)."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:  # weekend
        return False
    market_open = time(13, 30)   # 9:30 ET = 13:30 UTC
    market_close = time(20, 0)   # 16:00 ET = 20:00 UTC
    return market_open <= now.time() <= market_close


async def _fetch_polygon(session: aiohttp.ClientSession, ticker: str) -> Optional[dict]:
    if not settings.POLYGON_KEY:
        return None
    url = f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={settings.POLYGON_KEY}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                data = await resp.json()
                result = data.get("results", {})
                price = result.get("p")
                if price:
                    return {"price": price, "source": "polygon"}
    except Exception as e:
        logger.debug("Polygon error for %s: %s", ticker, e)
    return None


async def _fetch_alpha_vantage(session: aiohttp.ClientSession, ticker: str) -> Optional[dict]:
    if settings.ALPHA_VANTAGE_KEY == "demo":
        return None
    url = (
        f"https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE&symbol={ticker}&apikey={settings.ALPHA_VANTAGE_KEY}"
    )
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                quote = data.get("Global Quote", {})
                price = quote.get("05. price")
                change_pct = quote.get("10. change percent", "0%").replace("%", "")
                if price:
                    return {
                        "price": float(price),
                        "change_pct": float(change_pct),
                        "source": "alphavantage",
                    }
    except Exception as e:
        logger.debug("AlphaVantage error for %s: %s", ticker, e)
    return None


async def _fetch_yfinance_batch() -> dict[str, dict]:
    """Fallback: fetch all tickers at once via yfinance (blocking, run in thread)."""
    import pandas as pd

    def _sync():
        try:
            import yfinance as yf
            tickers = yf.Tickers(" ".join(MARKET_TICKERS))
            out = {}
            for t in MARKET_TICKERS:
                try:
                    info = tickers.tickers[t].fast_info
                    out[t] = {
                        "price": round(float(info.last_price), 2),
                        "change_pct": 0.0,
                        "source": "yfinance",
                    }
                except Exception:
                    pass
            return out
        except Exception:
            return {}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def refresh_quotes() -> None:
    """Refresh the in-memory quote cache. Called by the APScheduler job."""
    global _last_refresh
    async with _refresh_lock:
        logger.info("Refreshing market quotes...")
        async with aiohttp.ClientSession() as session:
            results: dict[str, dict] = {}

            # Try Polygon first for each ticker
            if settings.POLYGON_KEY:
                tasks = [_fetch_polygon(session, t) for t in MARKET_TICKERS]
                polygon_results = await asyncio.gather(*tasks, return_exceptions=True)
                for ticker, res in zip(MARKET_TICKERS, polygon_results):
                    if isinstance(res, dict):
                        results[ticker] = res

            # Fill missing with Alpha Vantage (rate-limited, so only fill gaps)
            missing = [t for t in MARKET_TICKERS if t not in results]
            if missing and settings.ALPHA_VANTAGE_KEY != "demo":
                # AV has strict rate limits; fetch sequentially with delay
                for ticker in missing[:10]:  # stay under free tier limit
                    res = await _fetch_alpha_vantage(session, ticker)
                    if res:
                        results[ticker] = res
                    await asyncio.sleep(0.5)

        # Fall back to yfinance for anything still missing
        still_missing = [t for t in MARKET_TICKERS if t not in results]
        if still_missing:
            yf_results = await _fetch_yfinance_batch()
            results.update(yf_results)

        _quote_cache.update(results)
        _last_refresh = datetime.now(timezone.utc)
        logger.info("Quote cache updated: %d tickers", len(_quote_cache))


def get_quotes() -> dict:
    """Return the current cached quotes.

    data_source: 'yfinance' when quotes came from a live fetch;
                 'synthetic' when the cache is empty (e.g. offline / first boot).
    """
    # Determine source from the first cached quote, or fall back to synthetic label.
    source = "synthetic"
    if _quote_cache:
        first = next(iter(_quote_cache.values()))
        source = first.get("source", "yfinance")

    return {
        "quotes": _quote_cache,
        "data_source": source,
        "last_updated": _last_refresh.isoformat() if _last_refresh else None,
        "market_open": _is_market_hours(),
    }


def get_quote(ticker: str) -> Optional[dict]:
    return _quote_cache.get(ticker.upper())
