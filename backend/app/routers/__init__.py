"""API router registry.

All sub-routers are collected here and mounted under the /api prefix
in main.py via a single include_router call.
"""
from fastapi import APIRouter

from .auth import router as auth_router
from .universe import router as universe_router
from .questionnaire import router as questionnaire_router
from .savings import router as savings_router
from .allocate import router as allocate_router
from .portfolios import router as portfolios_router
from .portfolio import router as portfolio_router
from .scenarios import router as scenarios_router
from .market import router as market_router
from .risk import router as risk_router
from .agent import router as agent_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)          # /api/auth/*
api_router.include_router(universe_router)       # /api/universe
api_router.include_router(questionnaire_router)  # /api/questionnaire*
api_router.include_router(savings_router)        # /api/savings-capacity
api_router.include_router(allocate_router)       # /api/allocate, /api/compare
api_router.include_router(portfolios_router)     # /api/portfolios*
api_router.include_router(portfolio_router)      # /api/portfolio/* (frontend)
api_router.include_router(scenarios_router)      # /api/scenarios*
api_router.include_router(market_router)         # /api/market/*
api_router.include_router(risk_router)           # /api/risk/*
api_router.include_router(agent_router)          # /api/agent/*

__all__ = ["api_router"]

from .research import router as research_router
api_router.include_router(research_router)
