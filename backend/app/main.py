"""FastAPI application entry point.

All routes live under /api/* via api_router.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure engine package (project root) is importable before any router imports.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .core.config import get_settings
from .core.database import Base, engine
from .models import User, Portfolio       # register models with SQLAlchemy
from .routers import api_router
from .services.market_data import get_quotes, refresh_quotes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables (Alembic handles prod migrations; this covers dev/test).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    # Prime the quote cache on startup.
    try:
        await refresh_quotes()
    except Exception as exc:
        logger.warning("Initial quote fetch failed: %s", exc)

    # Refresh quotes every 60 seconds (hard constraint: no faster than 60s).
    scheduler.add_job(refresh_quotes, "interval", seconds=60, id="quote_refresh")
    # Refresh price history once per day at 06:00 UTC (after market close).
    scheduler.add_job(
        _refresh_prices_daily,
        "cron",
        hour=6,
        minute=0,
        id="price_refresh",
    )
    from .routers.research import monitor_accounts
    scheduler.add_job(monitor_accounts, "interval", seconds=60, id="paper_monitor", max_instances=1, coalesce=True)
    scheduler.start()
    logger.info("Scheduler started (quote: 60s, price: daily 06:00 UTC)")

    yield

    scheduler.shutdown()


async def _refresh_prices_daily() -> None:
    """Download fresh price history from yfinance and overwrite the CSV snapshot."""
    import asyncio

    def _sync():
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from engine.data import load_prices
        _, source = load_prices(allow_network=True)
        logger.info("Daily price refresh complete — source: %s", source)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Portfolio Strategy Simulator",
    version="2.0.0",
    description="Educational portfolio simulation. Not financial advice.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Error handlers ────────────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Return structured per-field validation errors (no raw stack traces)."""
    errors = []
    for error in exc.errors():
        field = error["loc"][-1] if error["loc"] else "body"
        errors.append({"field": str(field), "message": error["msg"]})
    return JSONResponse(status_code=422, content={"detail": errors})


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(api_router)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
async def health():
    """Service health + data freshness status."""
    q = get_quotes()
    return {
        "status": "ok",
        "version": "2.0.0",
        "data_source": q.get("data_source", "unknown"),
        "last_price_refresh": None,        # populated by Task 3 (Alembic + state tracking)
        "last_quote_refresh": q["last_updated"],
        "quote_count": len(q["quotes"]),
    }
