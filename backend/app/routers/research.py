"""Shared research, authenticated and isolated simulated accounts."""
import asyncio
import json
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from .auth import get_current_user
from desk.paper import ROOT, PaperDesk, snapshot, locked, atomic_json

router = APIRouter(prefix="/research", tags=["research"])
ACCOUNTS = ROOT / "state/accounts"

def account(user):
    return PaperDesk(ACCOUNTS / str(UUID(str(user.id))))

def public_state(state):
    return {**state, "events": state["events"][-50:]}

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

@router.post('/paper/plan')
async def plan(body: Plan, user=Depends(get_current_user)):
    try:
        return public_state(await asyncio.to_thread(account(user).configure, body.capital, body.risk_pct, body.horizon_months))
    except ValueError as exc:
        raise HTTPException(409, str(exc))

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
