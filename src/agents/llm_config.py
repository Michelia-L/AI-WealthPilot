"""
Runtime LLM endpoint configuration resolver (FR-002).

User-saved LLM settings (base_url / api_key / model) live in the app
SQLite database (``app_settings`` table), so this module deliberately
imports ``api.db`` — one sanctioned ``src/`` → ``api/`` dependency, since
the settings store is owned by the API shell. ``api.db.engine`` is
resolved dynamically at call time (never captured at import) because
tests redirect it to a tmp-path SQLite via
``monkeypatch.setattr("api.db.engine", tmp_engine)``.

Resolution order is per-field: a non-empty DB value wins, otherwise the
env default from ``src.config`` (read as module attributes at call time
so tests can monkeypatch them). When no API key is available from either
source the config reports ``configured=False`` and LLM consumers keep
their existing 503/ValueError behavior.
"""

import logging
from dataclasses import dataclass

from sqlmodel import Session, select

from api import db
from src import (
    config as _env_config,  # attributes read at call time (tests monkeypatch)
)

logger = logging.getLogger(__name__)

# app_settings keys for the LLM endpoint triple.
KEY_BASE_URL = "llm_base_url"
KEY_API_KEY = "llm_api_key"
KEY_MODEL = "llm_model"
LLM_SETTING_KEYS = (KEY_BASE_URL, KEY_API_KEY, KEY_MODEL)


@dataclass(frozen=True)
class LlmConfig:
    """Effective LLM endpoint settings after DB-over-env resolution."""

    base_url: str
    api_key: str
    model: str
    configured: bool
    source: str  # "db" / "env" / "none"


def _read_db_settings() -> dict[str, str]:
    """Read the llm_* rows from app_settings; empty mapping on any failure.

    Defensive by design: scripts using src/ without init_db() (table
    missing) or before the DB file exists must not crash — they simply
    fall back to env configuration.
    """
    try:
        with Session(db.engine) as session:
            rows = session.exec(
                select(db.AppSettingRecord).where(
                    db.AppSettingRecord.key.in_(LLM_SETTING_KEYS)
                )
            ).all()
            return {row.key: row.value for row in rows}
    except Exception:
        logger.debug(
            "app_settings read failed; falling back to env LLM config",
            exc_info=True,
        )
        return {}


def get_llm_config() -> LlmConfig:
    """Resolve the effective LLM endpoint settings.

    Per-field fallback: DB value when non-empty, else the env default.
    ``source`` reflects where the effective API key came from ("db" only
    when the DB key is the effective one); with no key from either side
    the result is ``configured=False, source="none"``.
    """
    saved = _read_db_settings()

    db_base_url = (saved.get(KEY_BASE_URL) or "").strip()
    db_api_key = (saved.get(KEY_API_KEY) or "").strip()
    db_model = (saved.get(KEY_MODEL) or "").strip()

    base_url = db_base_url or (getattr(_env_config, "DEEPSEEK_BASE_URL", "") or "")
    api_key = db_api_key or (getattr(_env_config, "DEEPSEEK_API_KEY", "") or "")
    model = db_model or (getattr(_env_config, "DEEPSEEK_MODEL", "") or "")

    if not api_key:
        return LlmConfig(
            base_url=base_url,
            api_key="",
            model=model,
            configured=False,
            source="none",
        )
    return LlmConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        configured=True,
        source="db" if db_api_key else "env",
    )


def mask_api_key(key: str) -> str:
    """Mask an API key for display: "" stays "", short keys become
    "****", longer ones keep first 3 + last 4 chars (sk-****1234)."""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"
