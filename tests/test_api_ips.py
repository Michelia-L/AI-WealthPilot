"""
API tests for the IPS async generation tasks (Phase 4b).

The LangGraph workflow is replaced with a fake astream() — tests cover the
task lifecycle, SSE progress protocol, persistence and document library,
not the LLM-driven workflow itself (covered by src tests).
"""

import json

import pytest

from tests.test_api_advisor import _parse_sse
from tests.test_api_profiles import sample_payload


class FakeWorkflowApp:
    """Mimics a compiled LangGraph: yields per-node updates, then a final state."""

    _DEFAULT_IPS = object()  # sentinel: distinguish "omitted" from explicit None

    def __init__(self, final_ips=_DEFAULT_IPS, error_message: str = ""):
        self.final_ips = (
            {
                "client_name": "John Doe",
                "version": "1.0",
                "risk_tolerance": {"overall_risk_level": "Moderate / 平衡型"},
            }
            if final_ips is self._DEFAULT_IPS
            else final_ips
        )
        self.error_message = error_message

    async def astream(self, initial_state, config=None, stream_mode=None):
        yield {"generate_cme": {"status": "cme_generated"}}
        yield {"generate": {"status": "generating"}}
        yield {
            "finalize": {
                "final_ips": self.final_ips,
                "audit_trail": {"final_status": "approved", "total_rounds": 0},
                "status": "completed" if self.final_ips else "failed",
                "revision_count": 0,
                "error_message": self.error_message,
            }
        }


@pytest.fixture
def fake_workflow(monkeypatch):
    monkeypatch.setattr("api.routers.ips.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "src.agents.ips_workflow.load_ips_template", lambda: "TEMPLATE TEXT"
    )
    monkeypatch.setattr(
        "src.agents.ips_workflow.compile_ips_workflow", lambda **kw: FakeWorkflowApp()
    )


def _create_profile(client) -> int:
    resp = client.post("/api/profiles", json=sample_payload())
    assert resp.status_code == 201
    return resp.json()["id"]


def test_generate_streams_progress_and_saves_document(client, fake_workflow):
    profile_id = _create_profile(client)

    created = client.post("/api/ips/generate", json={"profile_id": profile_id})
    assert created.status_code == 202
    task_id = created.json()["task_id"]

    resp = client.get(f"/api/ips/tasks/{task_id}/events")
    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    node_events = [e for e in events if e["type"] == "node"]
    assert [e["node"] for e in node_events] == ["generate_cme", "generate", "finalize"]
    assert node_events[0]["label"]  # Chinese label attached

    done = events[-1]
    assert done["type"] == "done" and done["success"] is True
    document_id = done["document_id"]

    # The generated IPS landed in the (tmp) document library.
    listing = client.get("/api/ips").json()["documents"]
    assert len(listing) == 1
    assert listing[0]["document_id"] == document_id
    assert listing[0]["client_name"] == "John Doe"
    assert listing[0]["status"] == "approved"

    detail = client.get(f"/api/ips/{document_id}")
    assert detail.status_code == 200
    assert "投资政策声明书" in detail.json()["markdown"]


def test_generate_requires_api_key(client, monkeypatch):
    monkeypatch.setattr("api.routers.ips.is_api_configured", lambda: False)
    profile_id = _create_profile(client)
    resp = client.post("/api/ips/generate", json={"profile_id": profile_id})
    assert resp.status_code == 503


def test_generate_profile_not_found(client, fake_workflow):
    resp = client.post("/api/ips/generate", json={"profile_id": 999})
    assert resp.status_code == 404


def test_workflow_failure_emits_error_event(client, monkeypatch):
    monkeypatch.setattr("api.routers.ips.is_api_configured", lambda: True)
    monkeypatch.setattr("src.agents.ips_workflow.load_ips_template", lambda: "T")
    monkeypatch.setattr(
        "src.agents.ips_workflow.compile_ips_workflow",
        lambda **kw: FakeWorkflowApp(final_ips=None, error_message="LLM exploded"),
    )
    profile_id = _create_profile(client)

    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()["task_id"]
    events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)

    assert events[-1]["type"] == "error"
    assert "LLM exploded" in events[-1]["message"]
    assert client.get("/api/ips").json()["documents"] == []


def test_task_and_document_not_found(client):
    assert client.get("/api/ips/tasks/nonexistent/events").status_code == 404
    assert client.get("/api/ips/ips_nobody_20260101_000000").status_code == 404
    assert client.get("/api/ips/..%2F..%2Fsecret").status_code == 404
