#!/usr/bin/env python3
"""Backend API tests. Run from backend/:  python test_api.py

Uses httpx ASGITransport against the real app with a throwaway SQLite file,
so routing, Pydantic validation, JWT handling and SQLAlchemy all execute for
real. No mocking of the layers under test.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

_TMP_DB = Path(tempfile.gettempdir()) / "investiq_test.db"
_TMP_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ.setdefault("SECRET_KEY", "test_only_not_a_real_secret")

import httpx  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Portfolio, Scenario, User  # noqa: E402  (register mappers)

passed = failed = 0
BASE = "http://test"

GOOD_USER = {
    "email": "ada@example.com",
    "username": "ada",
    "password": "Passw0rd!23",
    "date_of_birth": "1995-06-14",
    "citizenship_attested": True,
    "age_attested": True,
    "terms_attested": True,
    "monthly_income": 5200,
}


def check(name, coro):
    global passed, failed
    try:
        asyncio.run(coro())
        passed += 1
        print(f"  PASS  {name}")
    except Exception as e:
        failed += 1
        print(f"  FAIL  {name}: {type(e).__name__}: {e}")


async def client() -> httpx.AsyncClient:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url=BASE)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def register(c: httpx.AsyncClient, **overrides) -> str:
    body = {**GOOD_USER, **overrides}
    r = await c.post("/api/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def guest(c: httpx.AsyncClient) -> str:
    r = await c.post("/api/auth/guest")
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


# ── Health ───────────────────────────────────────────────────────────────────

async def t_health_reports_data_source():
    async with await client() as c:
        r = await c.get("/api/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert "data_source" in body, body


# ── Auth ─────────────────────────────────────────────────────────────────────

async def t_register_and_me():
    async with await client() as c:
        token = await register(c, email="reg1@example.com", username="reg1")
        r = await c.get("/api/auth/me", headers=auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "reg1@example.com"
        assert r.json()["is_guest"] is False


async def t_password_is_never_returned():
    async with await client() as c:
        token = await register(c, email="reg2@example.com", username="reg2")
        r = await c.get("/api/auth/me", headers=auth(token))
        body = r.text.lower()
        assert "password" not in body, "response leaks a password field"
        assert GOOD_USER["password"].lower() not in body


async def t_password_is_hashed_at_rest():
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    async with await client() as c:
        await register(c, email="hash@example.com", username="hashuser")
    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(User).where(User.email == "hash@example.com"))).scalar_one()
        assert row.hashed_password != GOOD_USER["password"]
        assert row.hashed_password.startswith("$2"), row.hashed_password[:8]


async def t_duplicate_email_rejected():
    async with await client() as c:
        await register(c, email="dupe@example.com", username="dupe1")
        r = await c.post("/api/auth/register",
                         json={**GOOD_USER, "email": "dupe@example.com", "username": "dupe2"})
        assert r.status_code == 409, r.status_code


async def t_under_18_rejected():
    async with await client() as c:
        r = await c.post("/api/auth/register",
                         json={**GOOD_USER, "email": "kid@example.com",
                               "username": "kid", "date_of_birth": "2015-01-01"})
        assert r.status_code == 422, r.text


async def t_unattested_terms_rejected():
    async with await client() as c:
        r = await c.post("/api/auth/register",
                         json={**GOOD_USER, "email": "no@example.com",
                               "username": "noterms", "terms_attested": False})
        assert r.status_code == 422, r.text


async def t_login_wrong_password_401():
    async with await client() as c:
        await register(c, email="login@example.com", username="loginuser")
        r = await c.post("/api/auth/login",
                         data={"username": "login@example.com", "password": "wrong"})
        assert r.status_code == 401, r.status_code


async def t_protected_routes_require_a_token():
    async with await client() as c:
        for method, path in [("get", "/api/auth/me"), ("get", "/api/scenarios/"),
                             ("get", "/api/universe"), ("get", "/api/risk/policy")]:
            r = await getattr(c, method)(path)
            assert r.status_code == 401, f"{path} returned {r.status_code}"


async def t_garbage_token_rejected():
    async with await client() as c:
        r = await c.get("/api/auth/me", headers=auth("not.a.jwt"))
        assert r.status_code == 401, r.status_code


# ── Guest sessions ───────────────────────────────────────────────────────────

async def t_guest_session_works_without_credentials():
    async with await client() as c:
        token = await guest(c)
        r = await c.get("/api/auth/me", headers=auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["is_guest"] is True, r.json()


async def t_guest_can_run_a_simulation():
    async with await client() as c:
        token = await guest(c)
        r = await c.post("/api/portfolio/simulate", headers=auth(token), json={
            "amount": 10000, "horizon_years": 15, "risk": "balanced",
            "monthly_contribution": 300, "rebalance": "annual", "extra_fee": 0,
        })
        assert r.status_code == 200, r.text
        assert len(r.json()["allocation"]) > 0


# ── User isolation ───────────────────────────────────────────────────────────

async def t_scenarios_are_isolated_per_user():
    async with await client() as c:
        a = await register(c, email="iso_a@example.com", username="iso_a")
        b = await register(c, email="iso_b@example.com", username="iso_b")

        r = await c.post("/api/scenarios/", headers=auth(a), json={
            "name": "A's plan", "risk_tier": "balanced", "amount": 10000,
            "horizon_years": 15, "monthly_contribution": 0, "extra_fee": 0,
        })
        assert r.status_code == 201, r.text
        scenario_id = r.json()["id"]

        mine = await c.get("/api/scenarios/", headers=auth(a))
        theirs = await c.get("/api/scenarios/", headers=auth(b))
        assert len(mine.json()) == 1, mine.json()
        assert theirs.json() == [], theirs.json()

        # B must not be able to delete A's record
        r = await c.delete(f"/api/scenarios/{scenario_id}", headers=auth(b))
        assert r.status_code in (403, 404), r.status_code
        still = await c.get("/api/scenarios/", headers=auth(a))
        assert len(still.json()) == 1, "another user deleted this record"


async def t_guests_are_isolated_from_each_other():
    async with await client() as c:
        g1 = await guest(c)
        g2 = await guest(c)
        await c.post("/api/scenarios/", headers=auth(g1), json={
            "name": "G1", "risk_tier": "aggressive", "amount": 5000,
            "horizon_years": 10, "monthly_contribution": 0, "extra_fee": 0,
        })
        assert len((await c.get("/api/scenarios/", headers=auth(g1))).json()) == 1
        assert (await c.get("/api/scenarios/", headers=auth(g2))).json() == []


# ── Validation ───────────────────────────────────────────────────────────────

async def t_invalid_simulation_returns_field_errors():
    async with await client() as c:
        token = await register(c, email="val@example.com", username="valuser")
        r = await c.post("/api/portfolio/simulate", headers=auth(token),
                         json={"amount": -5, "horizon_years": 20, "risk": "yolo"})
        assert r.status_code == 422, r.status_code
        detail = r.json()["detail"]
        fields = {d["field"] for d in detail}
        assert "amount" in fields and "risk" in fields, detail
        assert "Traceback" not in r.text


async def t_simulation_returns_disclaimer():
    async with await client() as c:
        token = await register(c, email="disc@example.com", username="discuser")
        r = await c.post("/api/portfolio/simulate", headers=auth(token), json={
            "amount": 25000, "horizon_years": 20, "risk": "aggressive",
            "monthly_contribution": 500, "rebalance": "annual", "extra_fee": 0,
        })
        body = r.json()
        assert "not financial advice" in body["disclaimer"].lower(), body["disclaimer"]
        assert body["data_source"] in ("snapshot", "yfinance", "synthetic")


# ── Risk gate over HTTP ──────────────────────────────────────────────────────

async def t_risk_gate_clears_a_clean_proposal():
    async with await client() as c:
        token = await guest(c)
        r = await c.post("/api/risk/evaluate", headers=auth(token), json={
            "equity": 2000, "entry": 50, "stop": 49, "target_1": 52, "target_2": 53,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["approved"] is True, body
        assert body["quantity"] == 20, body["quantity"]
        assert abs(body["risk_pct"] - 0.01) < 1e-9, body["risk_pct"]


async def t_risk_gate_refuses_on_breaker():
    async with await client() as c:
        token = await guest(c)
        r = await c.post("/api/risk/evaluate", headers=auth(token), json={
            "equity": 1930, "day_start_equity": 2000,
            "entry": 50, "stop": 49, "target_1": 52, "target_2": 53,
        })
        body = r.json()
        assert body["approved"] is False
        assert body["veto_code"] == "VETO_FLATTEN_DAY", body["veto_code"]
        assert body["quantity"] == 0


async def t_risk_gate_refuses_insufficient_reward():
    async with await client() as c:
        token = await guest(c)
        r = await c.post("/api/risk/evaluate", headers=auth(token), json={
            "equity": 2000, "entry": 50, "stop": 49, "target_1": 50.3, "target_2": 51,
        })
        assert r.json()["veto_code"] == "VETO_INSUFFICIENT_REWARD", r.json()


async def t_stateless_risk_eval_leaves_no_block_file():
    """Regression: a drawdown scenario once wrote a real block file."""
    async with await client() as c:
        token = await guest(c)
        await c.post("/api/risk/evaluate", headers=auth(token), json={
            "equity": 1800, "peak_equity": 2000, "day_start_equity": 1800,
            "week_start_equity": 1800, "month_start_equity": 1800,
            "entry": 50, "stop": 49, "target_1": 52, "target_2": 53,
        })
        # A later clean proposal must still clear.
        r = await c.post("/api/risk/evaluate", headers=auth(token), json={
            "equity": 2000, "entry": 50, "stop": 49, "target_1": 52, "target_2": 53,
        })
        assert r.json()["approved"] is True, r.json()
        assert not Path("state/TRADING_BLOCKED").exists()


async def t_risk_policy_exposes_the_cascade():
    async with await client() as c:
        token = await guest(c)
        r = await c.get("/api/risk/policy", headers=auth(token))
        body = r.json()
        assert body["risk_per_trade"] == 0.01
        assert len(body["cascade"]) == 7, len(body["cascade"])
        assert len(body["policy_hash"]) == 16


if __name__ == "__main__":
    print(f"\ndatabase: {_TMP_DB}\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and asyncio.iscoroutinefunction(fn):
            check(name[2:], fn)
    print(f"\n{passed} passed, {failed} failed\n")
    _TMP_DB.unlink(missing_ok=True)
    raise SystemExit(1 if failed else 0)
