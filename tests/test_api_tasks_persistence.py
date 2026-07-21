"""API tests for background-task persistence (write-through + SSE replay).

Tasks execute in-process, but every published event is mirrored to a
TaskRecord row: a finished task's stream must be replayable once the
in-memory registry has lost it (server restart), rows left 'running' by a
shutdown are reconciled to 'failed' on boot, and unknown task ids keep 404.
"""

import json

import pytest
from sqlmodel import Session

from api import db
from api.db import TaskRecord
from api.tasks import TaskRegistry, reconcile_interrupted_tasks
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
