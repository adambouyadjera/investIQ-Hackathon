"""Universe endpoint — 15-asset metadata + cached live quotes.

Single endpoint: GET /api/universe
Returns asset metadata from engine/universe.py merged with the latest
quote cache. Also used by the frontend DataStatusPill.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.universe import UNIVERSE  # noqa: E402

from .auth import get_current_user
from ..models.user import User
from ..services.market_data import get_quotes, refresh_quotes

router = APIRouter(tags=["universe"])


@router.get("/universe")
async def universe(current_user: User = Depends(get_current_user)):
    """Return all 15 assets with metadata and live-ish quotes.

    Quotes come from the server-side cache (refreshed every 60s by scheduler).
    If the cache is empty (first call), populate it now.
    """
    quote_data = get_quotes()
    if not quote_data["quotes"]:
        await refresh_quotes()
        quote_data = get_quotes()

    quotes = quote_data["quotes"]
    assets = []
    for asset in UNIVERSE:
        q = quotes.get(asset.ticker, {})
        assets.append({
            "ticker": asset.ticker,
            "name": asset.name,
            "kind": asset.kind,
            "expense_ratio": asset.expense_ratio,
            "beta": asset.beta,
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
            "quote_source": q.get("source"),
        })

    return {
        "assets": assets,
        "data_source": quote_data.get("data_source", "unknown"),
        "last_updated": quote_data["last_updated"],
        "market_open": quote_data["market_open"],
    }
