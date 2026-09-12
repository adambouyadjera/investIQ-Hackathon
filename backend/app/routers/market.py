"""Market data endpoints — live quotes and universe info."""
from fastapi import APIRouter, Depends

from ..routers.auth import get_current_user
from ..models.user import User
from ..services.market_data import get_quotes, get_quote, refresh_quotes
from ..core.config import get_settings

router = APIRouter(prefix="/market", tags=["market"])
settings = get_settings()


@router.get("/quotes")
async def quotes(current_user: User = Depends(get_current_user)):
    """Return the latest cached quotes for all universe tickers."""
    data = get_quotes()
    if not data["quotes"]:
        # First call — populate cache synchronously
        await refresh_quotes()
        data = get_quotes()
    return data


@router.get("/quote/{ticker}")
async def single_quote(ticker: str, current_user: User = Depends(get_current_user)):
    q = get_quote(ticker.upper())
    if not q:
        await refresh_quotes()
        q = get_quote(ticker.upper())
    return q or {"error": "ticker not found"}


@router.post("/refresh")
async def manual_refresh(current_user: User = Depends(get_current_user)):
    """Manually trigger a quote refresh (for testing/dev)."""
    await refresh_quotes()
    return {"status": "ok", "quotes": len(get_quotes()["quotes"])}
