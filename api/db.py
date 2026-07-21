"""
SQLite persistence layer (SQLModel).

Single database for all API-side state — client profiles now, IPS workflow
and advisor tables in later phases. Local-first: one file under DATA_DIR,
volume-mounted in Docker Compose (./data:/app/data).

The full ClientProfile is stored as a JSON column (the dataclass shape is
owned by src/ and may evolve); index columns duplicate the fields the list
UI filters/sorts on. ``user_id`` is reserved for the multi-user future and
stays NULL in the single-user local deployment.
"""

import os
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine

from src.config import DATA_DIR

DEFAULT_DB_PATH = DATA_DIR / "wealthpilot.db"


def get_db_url() -> str:
    """Database URL, overridable via env (tests inject a tmp-path SQLite)."""
    return os.getenv("AIWP_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")


def make_engine(url: Optional[str] = None):
    # check_same_thread=False: FastAPI serves requests from a threadpool.
    return create_engine(url or get_db_url(), connect_args={"check_same_thread": False})


engine = make_engine()


class ProfileRecord(SQLModel, table=True):
    """One client profile row: JSON payload + queryable index columns."""

    __tablename__ = "client_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[str] = Field(default=None, index=True)  # reserved
    name: str = Field(index=True)
    age: int
    risk_level: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(), index=True
    )
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class TaskRecord(SQLModel, table=True):
    """One background task row: metadata plus the full SSE event log.

    Write-through mirror of the in-process BackgroundTask (api/tasks.py):
    the registry inserts the row on create, ``publish()`` appends each event
    to ``events_json`` and flips status on the terminal done/error event, and
    boot reconciliation fails rows left 'running' by a server restart. The
    JSON columns are plain text — the event vocabulary is owned by the
    routers and may evolve per task kind.
    """

    __tablename__ = "background_tasks"

    task_id: str = Field(primary_key=True)
    kind: str = Field(index=True)  # "ips" / "optimize"
    status: str = Field(default="running", index=True)  # running/completed/failed
    meta_json: str = "{}"
    events_json: str = "[]"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None


def init_db() -> None:
    """Create tables that don't exist yet (idempotent)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session
