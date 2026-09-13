"""Shared research, authenticated and isolated simulated accounts."""
import asyncio
import json
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from .auth import get_current_user
from desk.paper import ROOT, PaperDesk, snapshot, locked, atomic_json

router = APIRouter(prefix="/research", tags=["research"])
ACCOUNTS = ROOT / "state/accounts"

def account(user):
    return PaperDesk(ACCOUNTS / str(UUID(str(user.id))))

def public_state(state):
    return {**state, "events": state["events"][-50:], "trades": state.get("trades", [])[-200:]}

def run_cycle(desk):
    try:
        return desk.tick(snapshot())
    except (RuntimeError, OSError, ValueError):
        with locked(desk.lock):
            state = desk._read()
            state["status"] = "data_unavailable"
            state["error"] = "Public market data is unavailable. No new entry was placed; retry when connectivity returns."
            atomic_json(desk.file, state)
            return state

@router.get("")
async def overview(user=Depends(get_current_user)):
    report = await asyncio.to_thread(lambda: json.loads((ROOT / "reports/summary.json").read_text()))
    state = await asyncio.to_thread(account(user).read)
    return {"research": report, "paper": public_state(state)}

class Control(BaseModel):
    action: Literal["start", "pause", "close"]

class Plan(BaseModel):
    capital: float | None = None
    risk_pct: float | None = None
    horizon_months: int | None = None

@router.post("/paper/control")
async def control(body: Control, user=Depends(get_current_user)):
    desk = account(user)
    try:
        state = await asyncio.to_thread(desk.control, body.action)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if body.action == "close":
        state = await asyncio.to_thread(run_cycle, desk)
    return public_state(state)

@router.post("/paper/check")
async def check(user=Depends(get_current_user)):
    return public_state(await asyncio.to_thread(run_cycle, account(user)))

class Setup(BaseModel):
    capital: float
    risk_pct: float | None = None

@router.post('/paper/setup')
async def setup(body: Setup, user=Depends(get_current_user)):
    desk = account(user)
    try:
        await asyncio.to_thread(desk.setup, body.capital, body.risk_pct)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return public_state(await asyncio.to_thread(run_cycle, desk))

@router.post('/paper/plan')
async def plan(body: Plan, user=Depends(get_current_user)):
    try:
        return public_state(await asyncio.to_thread(account(user).configure, body.capital, body.risk_pct, body.horizon_months))
    except ValueError as exc:
        raise HTTPException(409, str(exc))

def portfolio_bot(user):
    from desk.portfolio_bot import PortfolioBot
    return PortfolioBot(ACCOUNTS / str(UUID(str(user.id))))

class PortfolioSetup(BaseModel):
    amount: float
    risk: Literal["low", "medium", "high"]
    months: int = Field(ge=1, le=120)

class PortfolioSettings(PortfolioSetup):
    confirm: bool = False
    reset: bool = False

class PortfolioBackfill(PortfolioSetup):
    days: int = Field(default=30, ge=5, le=90)
    confirm: bool = False

class PortfolioControl(BaseModel):
    action: Literal["pause", "resume", "review"]

MARKET_UNAVAILABLE = "Market data is unavailable right now. Nothing was traded; try again in a few minutes."

@router.get("/portfolio")
async def portfolio(user=Depends(get_current_user)):
    return await asyncio.to_thread(portfolio_bot(user).refresh, False)

@router.post("/portfolio/setup")
async def portfolio_setup(body: PortfolioSetup, user=Depends(get_current_user)):
    try:
        return await asyncio.to_thread(portfolio_bot(user).setup, body.amount, body.risk, body.months)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError:
        raise HTTPException(503, MARKET_UNAVAILABLE)

@router.post("/portfolio/backfill")
async def portfolio_backfill(body: PortfolioBackfill, user=Depends(get_current_user)):
    from desk.portfolio_bot import ConfirmationRequired
    try:
        return await asyncio.to_thread(portfolio_bot(user).backfill, body.amount, body.risk, body.months, body.days, body.confirm)
    except ConfirmationRequired as exc:
        raise HTTPException(409, {"code": "confirmation_required", "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError:
        raise HTTPException(503, MARKET_UNAVAILABLE)

@router.post("/portfolio/settings")
async def portfolio_settings(body: PortfolioSettings, user=Depends(get_current_user)):
    from desk.portfolio_bot import ConfirmationRequired
    try:
        return await asyncio.to_thread(portfolio_bot(user).update_settings, body.amount, body.risk, body.months, body.confirm, body.reset)
    except ConfirmationRequired as exc:
        raise HTTPException(409, {"code": "confirmation_required", "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError:
        raise HTTPException(503, MARKET_UNAVAILABLE)

@router.post("/portfolio/control")
async def portfolio_control(body: PortfolioControl, user=Depends(get_current_user)):
    try:
        return await asyncio.to_thread(portfolio_bot(user).control, body.action)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError:
        raise HTTPException(503, MARKET_UNAVAILABLE)

class SimulatorPlan(BaseModel):
    initial: float = Field(ge=0, le=1_000_000)
    monthly: float = Field(ge=0, le=100_000)
    risk: Literal["low", "medium", "high"]
    months: int = Field(ge=1, le=120)
    include: list[str] = Field(default_factory=list, max_length=5)

@router.post("/simulator/plan")
async def simulator_plan(body: SimulatorPlan, user=Depends(get_current_user)):
    from desk.simulator import build_plan
    try:
        return await asyncio.to_thread(lambda: build_plan(body.initial, body.monthly, body.risk, body.months, include=body.include))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError:
        raise HTTPException(503, MARKET_UNAVAILABLE)

@router.get("/simulator/leaderboard")
async def simulator_leaderboard(risk: Literal["low", "medium", "high"] = "medium", months: int = Query(12, ge=1, le=120), user=Depends(get_current_user)):
    from desk.simulator import watch
    try:
        return await asyncio.to_thread(watch, risk, months)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError:
        raise HTTPException(503, MARKET_UNAVAILABLE)

async def monitor_live_boards():
    import logging
    from desk.simulator import live_tick
    try:
        await asyncio.to_thread(live_tick)
    except Exception as exc:  # market data outages must not stop the scheduler
        logging.getLogger(__name__).warning("Live Top-rated update failed: %s", exc)

async def monitor_portfolios():
    from desk.portfolio_bot import PortfolioBot
    for path in ACCOUNTS.glob("*/portfolio.json"):
        try:
            await asyncio.to_thread(PortfolioBot(path.parent).refresh)
        except (RuntimeError, OSError, ValueError):
            continue

@router.get("/journal", response_class=PlainTextResponse)
async def journal(user=Depends(get_current_user)):
    return await asyncio.to_thread((ROOT / "reports/research-journal.md").read_text)

async def monitor_accounts():
    paths = list(ACCOUNTS.glob("*/paper.json"))
    if not paths:
        return
    try:
        data = await asyncio.to_thread(snapshot)
    except (RuntimeError, OSError, ValueError):
        for path in paths:
            desk = PaperDesk(path.parent)
            with locked(desk.lock):
                state = desk._read()
                state["status"] = "data_unavailable"
                state["error"] = "Public market data unavailable; automatic checks will retry."
                atomic_json(desk.file, state)
        return
    for path in paths:
        await asyncio.to_thread(PaperDesk(path.parent).tick, data)

@router.get('/news')
async def news(user=Depends(get_current_user)):
    from desk.news import get_news
    return await asyncio.to_thread(get_news)

@router.get('/yahoo')
async def yahoo_quotes(user=Depends(get_current_user)):
    from desk.yahoo import get_quotes
    return await asyncio.to_thread(get_quotes)

@router.get('/yahoo/stream')
async def yahoo_stream(user=Depends(get_current_user)):
    from desk.yahoo_stream import STREAM
    async def events():
        queue = STREAM.subscribe()
        try:
            for tick in list(STREAM.latest.values()):
                yield f"data: {json.dumps(tick)}\n\n"
            while True:
                try:
                    tick = await asyncio.wait_for(queue.get(), 15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(tick)}\n\n"
        finally:
            STREAM.unsubscribe(queue)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
