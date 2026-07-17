"""
AI WealthPilot API — application entry point.

Run from the project root:
    uvicorn api.main:app --reload --port 8000

Interactive docs: http://localhost:8000/docs
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importing the api package first ensures the project-root sys.path guard
# in api/__init__.py runs before any `src.*` import below.
import api  # noqa: F401
from api.routers import cme, market
from api.schemas import HealthResponse
from src.config import APP_NAME, APP_VERSION

# The Next.js dev server runs on :3000. Extra origins can be injected via
# CORS_ORIGINS (comma-separated) without a code change.
DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{APP_NAME} API",
        version=APP_VERSION,
        description=(
            "Thin FastAPI shell exposing the AI WealthPilot quant core "
            "(portfolio optimization, CME engine, AI advisor) to the Next.js frontend."
        ),
    )

    cors_origins = os.getenv("CORS_ORIGINS")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins.split(",") if cors_origins else DEFAULT_CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(market.router, prefix="/api")
    app.include_router(cme.router, prefix="/api")

    @app.get("/api/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        return HealthResponse(app=APP_NAME, version=APP_VERSION)

    return app


app = create_app()
