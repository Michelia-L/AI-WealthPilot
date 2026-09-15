"""
SQLite persistence layer (SQLModel).

Single database for API-side profiles, identity, sessions, settings, background
tasks and holding snapshots. Local-first: one file under DATA_DIR,
volume-mounted in Docker Compose (./data:/app/data).

The full ClientProfile is stored as a JSON column (the dataclass shape is
owned by src/ and may evolve); index columns duplicate the fields the list
UI filters/sorts on. Every profile belongs to one Client, which belongs to
one Organization. Login identity and organization roles are separate.
"""

import os
from collections.abc import Iterator
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    event,
)
from sqlmodel import Field, Session, SQLModel, create_engine

from src.config import DATA_DIR

DEFAULT_DB_PATH = DATA_DIR / "wealthpilot.db"


def get_db_url() -> str:
    """Database URL, overridable via env (tests inject a tmp-path SQLite)."""
    return os.getenv("AIWP_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")


def make_engine(url: Optional[str] = None):
    # check_same_thread=False: FastAPI serves requests from a threadpool.
    db_engine = create_engine(
        url or get_db_url(), connect_args={"check_same_thread": False}
    )

    @event.listens_for(db_engine, "connect")
    def enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return db_engine


engine = make_engine()


class UserRecord(SQLModel, table=True):
    """Login identity only; roles live on organization memberships."""

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


class MembershipRole(StrEnum):
    CLIENT = "client"
    ADVISOR = "advisor"
    ADMIN = "admin"


class OrganizationRecord(SQLModel, table=True):
    __tablename__ = "organizations"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str


class OrganizationMembershipRecord(SQLModel, table=True):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint("role IN ('client', 'advisor', 'admin')"),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    organization_id: str = Field(foreign_key="organizations.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    # Store enum values, not Python enum member names.
    role: MembershipRole = Field(sa_column=Column(String, nullable=False))


CLIENT_ORGANIZATION_INDEX = Index(
    "ux_clients_organization_id_id", "organization_id", "id", unique=True
)


class ClientRecord(SQLModel, table=True):
    """Business client, optionally linked to a login identity."""

    __tablename__ = "clients"
    __table_args__ = (CLIENT_ORGANIZATION_INDEX,)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    organization_id: str = Field(foreign_key="organizations.id", index=True)
    user_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)


class AdvisorClientAssignmentRecord(SQLModel, table=True):
    """An explicit assignment within one organization; not a role grant."""

    __tablename__ = "advisor_client_assignments"
    __table_args__ = (
        UniqueConstraint("organization_id", "advisor_user_id", "client_id"),
        ForeignKeyConstraint(
            ["organization_id", "advisor_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "client_id"], ["clients.organization_id", "clients.id"]
        ),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    organization_id: str
    advisor_user_id: str = Field(index=True)
    client_id: str = Field(index=True)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ProfileRecord(SQLModel, table=True):
    """One client profile row: JSON payload + queryable index columns."""

    __tablename__ = "client_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: str = Field(foreign_key="clients.id", unique=True, index=True)
    # Legacy provenance only. Never use this column to authorize access.
    user_id: Optional[str] = Field(default=None, index=True)
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
    """Create tables and atomically migrate legacy SQLite profile ownership."""
    from api.migrate_ownership import migrate_ownership

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        # Explicit BEGIN includes SQLite DDL in the transaction and serializes
        # concurrent startup migrations before inspecting the schema.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            SQLModel.metadata.create_all(connection)
            # create_all does not add indexes to an existing #73 clients table.
            # SQLite needs this composite parent key for assignment tenant FKs.
            CLIENT_ORGANIZATION_INDEX.create(connection, checkfirst=True)
            migrate_ownership(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session
