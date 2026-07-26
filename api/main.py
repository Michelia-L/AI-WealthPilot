"""
AI WealthPilot API — application entry point.

Run from the project root:
    uvicorn api.main:app --reload --port 8000

Interactive docs: http://localhost:8000/docs
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

# Importing the api package first ensures the project-root sys.path guard
# in api/__init__.py runs before any `src.*` import below.
import api  # noqa: F401
from api import db
from api.db import ProfileRecord, init_db
from api.migrate_profiles import maybe_auto_import
from api.profile_convert import tolerance_level
from api.routers import advisor, cme, ips, market, monitoring, portfolio, profiles, retirement, settings
from api.schemas import HealthResponse
from api.tasks import reconcile_interrupted_tasks
from src.agents.demo_mode import is_demo_mode
from src.config import APP_NAME, APP_VERSION

# The Next.js dev server runs on :3000. Extra origins can be injected via
# CORS_ORIGINS (comma-separated) without a code change.
DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def _demo_profile_data() -> dict:
    """Fictional demo client profile in the asdict(ClientProfile) shape.

    Fully fictional seed for demo mode (P20): fresh clones get one complete
    Chinese client profile so every LLM feature has something to replay
    against. Numbers line up with the demo fixtures in
    src/agents/demo_fixtures/ (same client, same SAA context).
    """
    ability, willingness = 3.4, 3.0
    return {
        "name": "林晓兰",
        "age": 38,
        "marital_status": "married",
        "dependents": 1,
        "financial": {
            "annual_income": 800000.0,
            "annual_expenses": 420000.0,
            "investable_assets": 2600000.0,
            "total_liabilities": 900000.0,
            "emergency_fund_months": 6.0,
        },
        "goals": [
            {
                "name": "子女教育金",
                "target_amount": 1200000.0,
                "years": 10,
                "priority": "high",
            },
            {
                "name": "退休养老储备",
                "target_amount": 4000000.0,
                "years": 22,
                "priority": "high",
            },
        ],
        "time_horizon_years": 22,
        "is_multi_stage": True,
        "liquidity_needs": 0.0,
        "tax_status": "taxable",
        "esg_preference": False,
        "sector_restrictions": [],
        "notes": "演示模式种子客户（虚构）。房贷余额 90 万元，维持按揭还款；曾因浮亏恐慌赎回基金，需配合再平衡纪律。",
        "risk_profile": {
            "ability_score": ability,
            "willingness_score": willingness,
            "tolerance_level": tolerance_level(ability, willingness),
            "description": "",
        },
        "ability_answers": {},
        "willingness_answers": {},
        "created_at": "2026-07-20T09:00:00",
        "updated_at": "2026-07-20T09:00:00",
    }


def _seed_demo_profile(session: Session) -> bool:
    """Insert the fictional demo client; True when a row was inserted.

    Runs only in demo mode and only on an empty profiles table, so it is
    idempotent and never overwrites real user data.
    """
    if not is_demo_mode():
        return False
    if session.exec(select(ProfileRecord.id).limit(1)).first() is not None:
        return False
    data = _demo_profile_data()
    session.add(
        ProfileRecord(
            name=data["name"],
            age=data["age"],
            risk_level=data["risk_profile"]["tolerance_level"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            data=data,
        )
    )
    session.commit()
    return True


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()  # create SQLite tables on first boot (idempotent)
        maybe_auto_import()  # first boot: seed DB from legacy JSON if empty
        reconcile_interrupted_tasks()  # fail task rows cut off by a previous shutdown
        with Session(db.engine) as session:
            if _seed_demo_profile(session):  # demo mode only, no-op otherwise
                print("Demo mode (DEMO_MODE=1): seeded fictional demo client 林晓兰.")
        yield

    app = FastAPI(
        title=f"{APP_NAME} API",
        version=APP_VERSION,
        description=(
            "Thin FastAPI shell exposing the AI WealthPilot quant core "
            "(portfolio optimization, CME engine, AI advisor) to the Next.js frontend."
        ),
        lifespan=lifespan,
    )

    cors_origins = os.getenv("CORS_ORIGINS")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins.split(",") if cors_origins else DEFAULT_CORS_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(market.router, prefix="/api")
    app.include_router(cme.router, prefix="/api")
    app.include_router(monitoring.router, prefix="/api")
    app.include_router(portfolio.router, prefix="/api")
    app.include_router(retirement.router, prefix="/api")
    app.include_router(profiles.router, prefix="/api")
    app.include_router(advisor.router, prefix="/api")
    app.include_router(ips.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")

    @app.get("/api/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        return HealthResponse(app=APP_NAME, version=APP_VERSION)

    return app


app = create_app()
