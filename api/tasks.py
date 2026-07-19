"""Generic in-process background task registry + SSE drain (Phase 5c).

Generalized from the 4b IPS task framework so other long computations
(resampled MVO) can reuse it. Per the migration plan there is no
Celery/Redis: tasks are process-local and lost on restart — durable results
are persisted by the workers themselves (IPS JSON store, etc.).
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional


@dataclass
class BackgroundTask:
    task_id: str
    kind: str  # "ips" / "optimize"
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    status: str = "running"  # running / completed / failed
    meta: dict[str, Any] = field(default_factory=dict)


class TaskRegistry:
    """Process-local task registry (single-user deployment; no persistence)."""

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}

    def create(self, kind: str, **meta: Any) -> BackgroundTask:
        task = BackgroundTask(task_id=uuid.uuid4().hex[:12], kind=kind, meta=meta)
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> Optional[BackgroundTask]:
        return self._tasks.get(task_id)


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_task_events(task: BackgroundTask) -> AsyncIterator[str]:
    """Drain a task's queue as SSE until the terminal done/error event."""
    while True:
        event = await task.queue.get()
        yield sse(event)
        if event.get("type") in ("done", "error"):
            break
