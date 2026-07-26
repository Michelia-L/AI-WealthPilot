"""Background task registry + SSE drain with write-through persistence.

Generalized from the 4b IPS task framework so other long computations
(resampled MVO) can reuse it. There is still no Celery/Redis: tasks execute
in-process and the live stream drains an asyncio.Queue, but every published
event is mirrored to a ``TaskRecord`` row (api/db.py) so a finished task's
SSE stream can be replayed after a server restart. Rows left 'running' by a
shutdown are reconciled to 'failed' on boot (``reconcile_interrupted_tasks``).

Every event carries a per-task ``seq`` counter, so the stream of a RUNNING
task is reconnectable: a consumer that disconnected mid-task first replays
the persisted log, then resumes the live queue, skipping queued events at or
below the max replayed seq — the full sequence, no gaps, no duplicates.

All DB access opens a short session per call and resolves ``api.db.engine``
dynamically (tests redirect it to a tmp-path SQLite). Persistence failures
are logged and swallowed — they must never interrupt the task itself.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from sqlmodel import Session, select

from api import db

logger = logging.getLogger(__name__)

# Defensive cap on the persisted event log (read-modify-write per event).
MAX_PERSISTED_EVENTS = 500


@dataclass
class BackgroundTask:
    task_id: str
    kind: str  # "ips" / "optimize"
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    status: str = "running"  # running / completed / failed
    meta: dict[str, Any] = field(default_factory=dict)
    _seq: int = 0  # per-task event counter, stamped by publish()

    async def publish(self, event: dict[str, Any]) -> None:
        """Write the event through to the DB record, then to the live queue.

        The event is stamped with ``seq`` (counting from 1) so reconnecting
        SSE consumers can dedupe the persisted replay against the live
        queue. Persistence runs first so a terminal done/error event is
        already durable by the time the SSE drain can observe it.
        """
        self._seq += 1
        sequenced = {"seq": self._seq, **event}
        _persist_event(self.task_id, sequenced)
        await self.queue.put(sequenced)


class TaskRegistry:
    """Process-local task registry; each task is mirrored to a TaskRecord row."""

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}

    def create(self, kind: str, **meta: Any) -> BackgroundTask:
        task = BackgroundTask(task_id=uuid.uuid4().hex[:12], kind=kind, meta=meta)
        self._tasks[task.task_id] = task
        try:
            with Session(db.engine) as session:
                session.add(
                    db.TaskRecord(
                        task_id=task.task_id,
                        kind=kind,
                        status="running",
                        meta_json=json.dumps(meta, ensure_ascii=False, default=str),
                    )
                )
                session.commit()
        except Exception:
            logger.exception("Failed to persist task record %s", task.task_id)
        return task

    def get(self, task_id: str) -> Optional[BackgroundTask]:
        return self._tasks.get(task_id)


def _persist_event(task_id: str, event: dict[str, Any]) -> None:
    """Append one event to the row's events_json (read-modify-write).

    A terminal done/error event also flips status to completed/failed and
    stamps finished_at. Never raises: a broken DB must not kill the task.
    """
    try:
        with Session(db.engine) as session:
            record = session.get(db.TaskRecord, task_id)
            if record is None:
                return
            events = json.loads(record.events_json)
            events.append(event)
            record.events_json = json.dumps(
                events[-MAX_PERSISTED_EVENTS:], ensure_ascii=False
            )
            event_type = event.get("type")
            if event_type in ("done", "error"):
                record.status = "completed" if event_type == "done" else "failed"
                record.finished_at = datetime.now().isoformat()
            session.add(record)
            session.commit()
    except Exception:
        logger.exception("Failed to persist event for task %s", task_id)


def _read_persisted_events(task_id: str) -> list[dict[str, Any]]:
    """Raw persisted event log for a task; [] when unknown or unreadable.

    Unlike ``load_task_events`` this never appends the synthetic
    'interrupted' error event — the caller is streaming a task that is still
    running in this process, so the row's 'running' status is expected.
    """
    try:
        with Session(db.engine) as session:
            record = session.get(db.TaskRecord, task_id)
            if record is None:
                return []
            return list(json.loads(record.events_json))
    except Exception:
        logger.exception("Failed to load persisted events for task %s", task_id)
        return []


def load_task_events(task_id: str) -> Optional[list[dict[str, Any]]]:
    """Persisted event log for a task unknown to the in-memory registry.

    Returns None when no record exists (the caller maps that to 404). A row
    still marked 'running' — boot reconciliation should have failed it — is
    replayed defensively with a synthetic trailing error event.
    """
    try:
        with Session(db.engine) as session:
            record = session.get(db.TaskRecord, task_id)
            if record is None:
                return None
            events: list[dict[str, Any]] = json.loads(record.events_json)
            status = record.status
    except Exception:
        logger.exception("Failed to load persisted events for task %s", task_id)
        return None
    if status == "running":
        events.append(
            {
                "type": "error",
                "message": "服务已重启，任务被中断（以上为重启前的进度回放）",
            }
        )
    return events


def reconcile_interrupted_tasks() -> int:
    """Mark persisted 'running' tasks as failed (interrupted by a restart)."""
    now = datetime.now().isoformat()
    with Session(db.engine) as session:
        rows = session.exec(
            select(db.TaskRecord).where(db.TaskRecord.status == "running")
        ).all()
        for row in rows:
            row.status = "failed"
            row.finished_at = now
            session.add(row)
        session.commit()
    return len(rows)


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_task_events(task: BackgroundTask) -> AsyncIterator[str]:
    """Stream a running task as SSE: persisted replay first, then live events.

    Reconnect-safe. The persisted log is replayed in stored order (events
    published before this consumer connected — including any an earlier
    consumer already pulled off the live queue), then the live queue is
    drained, skipping queued events whose seq is at or below the max
    replayed seq. Events without a seq (persisted before seq existed) replay
    normally and count as seq 0; seq-less queued events pass through
    untouched.
    """
    max_seq = 0
    for event in _read_persisted_events(task.task_id):
        seq = event.get("seq")
        if isinstance(seq, int):
            max_seq = max(max_seq, seq)
        yield sse(event)
        if event.get("type") in ("done", "error"):
            # The task finished between the registry check and this replay:
            # every queued event was just replayed, so draining would hang.
            return
    while True:
        event = await task.queue.get()
        seq = event.get("seq")
        if isinstance(seq, int) and seq <= max_seq:
            continue  # already replayed from the store
        yield sse(event)
        if event.get("type") in ("done", "error"):
            break


async def replay_task_events(events: list[dict[str, Any]]) -> AsyncIterator[str]:
    """Replay a persisted event log as one SSE batch (already terminal)."""
    for event in events:
        yield sse(event)


def task_events_stream(
    registry: TaskRegistry, task_id: str
) -> Optional[AsyncIterator[str]]:
    """Merged replay+live stream for running tasks; replay for terminal ones.

    Returns None when the task is unknown to both the registry and the
    store. A running task yields its persisted log first, then live queue
    events past the max replayed seq, so a reconnecting consumer sees the
    full sequence with no gaps or duplicates. A terminal in-memory task
    replays from the store instead of the live queue — that queue was
    drained by the first consumer and would hang any subsequent one.
    """
    task = registry.get(task_id)
    if task is not None and task.status == "running":
        return stream_task_events(task)
    events = load_task_events(task_id)
    if events is None:
        return None
    return replay_task_events(events)
