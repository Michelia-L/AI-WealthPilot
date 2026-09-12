"""
SQLite persistence layer (SQLModel).

Single database for API-side profiles, identity, sessions, settings, background
tasks and holding snapshots. Local-first: one file under DATA_DIR,
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
from uuid import uuid4

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


class UserRecord(SQLModel, table=True):
    """Login identity only; organization/membership belongs to issue #73."""

    __tablename__ = "users"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    email: str = Field(unique=True, index=True, repr=False)
    password_hash: Optional[str] = Field(default=None, repr=False)
    is_active: bool = True  # Temporary authentication pause, not session revocation.
    is_demo: bool = False
    failed_logins: int = 0
    locked_until: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class AuthSessionRecord(SQLModel, table=True):
    """Opaque bearer sessions. Only the SHA-256 digest is persisted."""

    __tablename__ = "auth_sessions"

    token_hash: str = Field(primary_key=True, repr=False)
    user_id: str = Field(foreign_key="users.id", index=True)
    created_at: int
    expires_at: int = Field(index=True)


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


class AppSettingRecord(SQLModel, table=True):
    """One app-setting row: key-value store (LLM config, feature flags…)."""

    __tablename__ = "app_settings"

    key: str = Field(primary_key=True)
    value: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class HoldingSnapshotRecord(SQLModel, table=True):
    """Append-only, complete valuations for an IPS; same-day corrections append."""

    __tablename__ = "holding_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: str = Field(index=True)
    as_of: str = Field(index=True)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


def init_db() -> None:
    """Create tables that don't exist yet (idempotent)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session
