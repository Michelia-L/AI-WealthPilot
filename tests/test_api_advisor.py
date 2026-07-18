"""
API tests for the AI advisor SSE streaming and report library (Phase 4a).

The LLM call is mocked out — tests assert the SSE event protocol and the
report-store CRUD, not model output.
"""

import json

import pytest

from src.agents.advisor import AdvisorReport
from tests.test_api_profiles import sample_payload


def _parse_sse(body: str) -> list[dict]:
    """Parse a `data: {json}\\n\\n` SSE body into event dicts."""
    events = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


@pytest.fixture
def configured(monkeypatch):
    """Pretend DEEPSEEK_API_KEY is set and stub the streaming generator."""
    monkeypatch.setattr("api.routers.advisor.is_api_configured", lambda: True)

    def fake_stream(profile):
        yield "## 1. Client Summary / 客户概况\n"
        yield f"Report body for {profile.name}."
        return AdvisorReport(
            content="full content",
            model="deepseek-v4-pro",
            client_name=profile.name,
            success=True,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

    monkeypatch.setattr("api.routers.advisor.generate_advice_stream", fake_stream)


def _create_profile(client) -> int:
    resp = client.post("/api/profiles", json=sample_payload())
    assert resp.status_code == 201
    return resp.json()["id"]


def test_status_endpoint(client):
    body = client.get("/api/advisor/status").json()
    assert "configured" in body and "model" in body


def test_stream_emits_tokens_then_done(client, configured):
    profile_id = _create_profile(client)

    resp = client.post("/api/advisor/report/stream", json={"profile_id": profile_id})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert [e["type"] for e in events] == ["token", "token", "done"]
    assert events[0]["text"].startswith("## 1.")
    assert events[1]["text"] == "Report body for John Doe."
    done = events[2]
    assert done["success"] is True
    assert done["total_tokens"] == 30
    assert done["error_message"] == ""


def test_stream_profile_not_found(client, configured):
    resp = client.post("/api/advisor/report/stream", json={"profile_id": 999})
    assert resp.status_code == 404


def test_stream_requires_api_key(client, monkeypatch):
    monkeypatch.setattr("api.routers.advisor.is_api_configured", lambda: False)
    profile_id = _create_profile(client)
    resp = client.post("/api/advisor/report/stream", json={"profile_id": profile_id})
    assert resp.status_code == 503
    assert "DEEPSEEK_API_KEY" in resp.json()["detail"]


def test_save_list_get_delete_report(client):
    saved = client.post(
        "/api/advisor/reports",
        json={
            "client_name": "John Doe",
            "content": "# Report\nSome advice.",
            "model": "deepseek-v4-pro",
            "prompt_tokens": 10,
            "completion_tokens": 20,
        },
    )
    assert saved.status_code == 201
    summary = saved.json()
    assert summary["total_tokens"] == 30
    assert "filepath" not in summary  # internal paths never leave the API

    listing = client.get("/api/advisor/reports").json()["reports"]
    assert len(listing) == 1
    assert "filepath" not in listing[0]

    detail = client.get(f"/api/advisor/reports/{summary['report_id']}")
    assert detail.status_code == 200
    assert detail.json()["content"] == "# Report\nSome advice."

    assert client.delete(f"/api/advisor/reports/{summary['report_id']}").status_code == 204
    assert client.get(f"/api/advisor/reports/{summary['report_id']}").status_code == 404


def test_report_not_found(client):
    assert client.get("/api/advisor/reports/20990101_000000_000000").status_code == 404
    assert client.delete("/api/advisor/reports/20990101_000000_000000").status_code == 404
    # Malformed ids are 404 too, never a path traversal.
    assert client.get("/api/advisor/reports/..%2F..%2Fetc").status_code == 404
