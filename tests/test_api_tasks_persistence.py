"""API tests for background-task persistence (write-through + SSE replay).

Tasks execute in-process, but every published event is mirrored to a
TaskRecord row: a finished task's stream must be replayable once the
in-memory registry has lost it (server restart), a RUNNING task's stream
must survive a consumer disconnect (persisted replay + live tail, deduped
by seq), rows left 'running' by a shutdown are reconciled to 'failed' on
boot, and unknown task ids keep 404.
"""

import asyncio
import json

import pytest
from sqlmodel import Session

from api import db
from api.db import TaskRecord
from api.tasks import TaskRegistry, reconcile_interrupted_tasks, task_events_stream
from tests.test_api_advisor import _parse_sse

# Reuse the IPS fake-workflow fixture pattern (imported fixtures register in
# this module's namespace).
from tests.test_api_ips import FakeWorkflowApp, _create_profile


@pytest.fixture
def fake_workflow(monkeypatch):
    monkeypatch.setattr("api.routers.ips.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "src.agents.ips_workflow.load_ips_template", lambda: "TEMPLATE TEXT"
    )
    monkeypatch.setattr(
        "src.agents.ips_workflow.compile_ips_workflow", lambda **kw: FakeWorkflowApp()
    )


def _run_ips_task_to_completion(client) -> tuple[str, list[dict]]:
    """Create a profile, run one fake-workflow IPS task, drain its live SSE."""
    profile_id = _create_profile(client)
    created = client.post("/api/ips/generate", json={"profile_id": profile_id})
    assert created.status_code == 202
    task_id = created.json()["task_id"]
    resp = client.get(f"/api/ips/tasks/{task_id}/events")
    assert resp.status_code == 200
    return task_id, _parse_sse(resp.text)


def test_task_events_persisted_to_db(client, fake_workflow):
    task_id, live_events = _run_ips_task_to_completion(client)
    assert [e["type"] for e in live_events] == ["node", "node", "node", "done"]

    with Session(db.engine) as session:
        record = session.get(TaskRecord, task_id)
    assert record is not None
    assert record.kind == "ips"
    assert record.status == "completed"
    assert record.finished_at is not None
    meta = json.loads(record.meta_json)
    assert meta["client_name"] == "John Doe"

    # The persisted log matches the live stream event-for-event.
    assert json.loads(record.events_json) == live_events


def test_events_replayed_after_registry_reset(client, fake_workflow, monkeypatch):
    task_id, live_events = _run_ips_task_to_completion(client)

    # Simulate a restart: the in-memory registry no longer knows the task.
    monkeypatch.setattr("api.routers.ips.registry", TaskRegistry())

    resp = client.get(f"/api/ips/tasks/{task_id}/events")
    assert resp.status_code == 200
    assert _parse_sse(resp.text) == live_events


def test_finished_task_replays_for_second_consumer(client, fake_workflow):
    """A terminal in-memory task must replay from the store — its live queue
    was drained by the first consumer and would hang a second one."""
    task_id, live_events = _run_ips_task_to_completion(client)

    # The task is still in the registry (no reset) but already terminal.
    resp = client.get(f"/api/ips/tasks/{task_id}/events")
    assert resp.status_code == 200
    assert _parse_sse(resp.text) == live_events


def test_reconcile_marks_interrupted_tasks_failed(client):
    with Session(db.engine) as session:
        session.add(TaskRecord(task_id="interrupted1", kind="ips", status="running"))
        session.add(TaskRecord(task_id="finished1", kind="ips", status="completed"))
        session.commit()

    assert reconcile_interrupted_tasks() == 1

    with Session(db.engine) as session:
        interrupted = session.get(TaskRecord, "interrupted1")
        finished = session.get(TaskRecord, "finished1")
    assert interrupted.status == "failed"
    assert interrupted.finished_at is not None
    assert finished.status == "completed"  # untouched


def test_running_record_replays_with_trailing_error(client):
    """Defensive: a row still 'running' at replay time reads as interrupted."""
    with Session(db.engine) as session:
        session.add(
            TaskRecord(
                task_id="stuck1",
                kind="ips",
                status="running",
                events_json=json.dumps(
                    [{"type": "node", "node": "generate", "label": "生成 IPS 初稿"}],
                    ensure_ascii=False,
                ),
            )
        )
        session.commit()

    resp = client.get("/api/ips/tasks/stuck1/events")
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [e["type"] for e in events] == ["node", "error"]
    assert "重启" in events[-1]["message"]


def test_unknown_task_still_404(client):
    assert client.get("/api/ips/tasks/never-existed/events").status_code == 404
    assert client.get("/api/portfolio/tasks/never-existed/events").status_code == 404


# ---------------------------------------------------------------------------
# Reconnectable streams (seq-stamped DB replay + live tail)
# ---------------------------------------------------------------------------


def test_reconnecting_consumer_gets_full_stream(client):
    """Mid-task disconnect: the second consumer of a RUNNING task must see
    the complete ordered sequence — persisted replay, then the live tail —
    with no gaps and no duplicates."""
    registry = TaskRegistry()

    async def scenario():
        task = registry.create("ips", client_name="John Doe")
        await task.publish(
            {"type": "node", "node": "generate_cme", "label": "生成 CME"}
        )
        await task.publish(
            {"type": "node", "node": "generate", "label": "生成 IPS 初稿"}
        )

        # First consumer connects, reads one event, then disconnects.
        first = task_events_stream(registry, task.task_id)
        first_events = _parse_sse(await first.__anext__())
        await first.aclose()

        # The task keeps publishing while no one is listening.
        await task.publish({"type": "node", "node": "finalize", "label": "合规定稿"})

        # Second consumer reconnects while the task is still running, then
        # the task finishes (status flips before the terminal publish, as
        # the routers do).
        second = task_events_stream(registry, task.task_id)
        task.status = "completed"
        await task.publish({"type": "done", "success": True})
        second_events = _parse_sse("".join([chunk async for chunk in second]))
        return first_events, second_events

    first_events, second_events = asyncio.run(scenario())

    assert [e["type"] for e in first_events] == ["node"]
    assert first_events[0]["seq"] == 1
    # seq 1..4 exactly once, in order: 1-3 replayed from the DB, 4 live.
    assert [e["seq"] for e in second_events] == [1, 2, 3, 4]
    assert [e["type"] for e in second_events] == ["node", "node", "node", "done"]
    assert [e["node"] for e in second_events[:3]] == [
        "generate_cme",
        "generate",
        "finalize",
    ]


def test_reconnect_after_completion_replays_full_sequence(client):
    """A consumer connecting after completion gets the whole log from the
    DB — identical to what the live consumer saw, seq-stamped from 1."""
    registry = TaskRegistry()

    async def scenario():
        task = registry.create("optimize", method="resampled")
        live = task_events_stream(registry, task.task_id)  # still running
        await task.publish({"type": "node", "node": "fetch", "label": "获取行情数据"})
        await task.publish({"type": "node", "node": "solve", "label": "求解组合"})
        task.status = "completed"
        await task.publish({"type": "done", "result": {"ok": True}})
        live_events = _parse_sse("".join([chunk async for chunk in live]))

        # Reconnect after completion: terminal task → pure DB replay.
        stream = task_events_stream(registry, task.task_id)
        replayed = _parse_sse("".join([chunk async for chunk in stream]))
        return live_events, replayed

    live_events, replayed = asyncio.run(scenario())

    assert [e["seq"] for e in live_events] == [1, 2, 3]
    assert [e["type"] for e in live_events] == ["node", "node", "done"]
    assert replayed == live_events


def test_seqless_events_pass_through_untouched(client):
    """Pre-seq events (rows/queue items written before seq existed) still
    stream: replayed in stored order, counted as seq 0, never filtered."""
    registry = TaskRegistry()

    async def scenario():
        task = registry.create("ips", client_name="John Doe")
        # Simulate a pre-seq persisted row.
        with Session(db.engine) as session:
            record = session.get(TaskRecord, task.task_id)
            record.events_json = json.dumps(
                [{"type": "node", "node": "generate", "label": "生成 IPS 初稿"}],
                ensure_ascii=False,
            )
            session.add(record)
            session.commit()
        await task.queue.put({"type": "node", "node": "finalize", "label": "合规定稿"})
        await task.queue.put({"type": "done", "success": True})

        stream = task_events_stream(registry, task.task_id)
        return _parse_sse("".join([chunk async for chunk in stream]))

    events = asyncio.run(scenario())

    assert [e["type"] for e in events] == ["node", "node", "done"]
    assert [e.get("node") for e in events[:2]] == ["generate", "finalize"]
    assert all("seq" not in e for e in events)
