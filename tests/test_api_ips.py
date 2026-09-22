"""
API tests for the IPS async generation tasks (Phase 4b).

The LangGraph workflow is replaced with a fake astream() — tests cover the
task lifecycle, SSE progress protocol, persistence and document library,
not the LLM-driven workflow itself (covered by src tests).
"""

import json

import pytest

from api import db
from src.agents import ips_storage
from src.agents.ips_models import IPSDocument
from src.agents.ips_workflow import IPSWorkflowState, TokenBudgetExceeded, finalize_node
from tests.test_api_access import workspace as access_workspace
from tests.test_api_advisor import _parse_sse
from tests.test_api_profiles import sample_payload
from tests.test_ips_workflow import minimal_ips_dict as ips_fixture

workspace = access_workspace
minimal_ips_dict = ips_fixture


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
    assert listing[0]["profile_id"] == profile_id
    assert listing[0]["status"] == "approved"
    drafts = client.get("/api/documents").json()["documents"]
    assert len(drafts) == 1
    assert drafts[0]["source_artifact_id"] == document_id
    assert drafts[0]["status"] == "draft"
    assert drafts[0]["approved_by"] is None

    detail = client.get(f"/api/ips/{document_id}")
    assert detail.status_code == 200
    assert detail.json()["metadata"]["profile_id"] == profile_id
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

    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()[
        "task_id"
    ]
    events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)

    assert events[-1]["type"] == "error"
    assert "LLM exploded" in events[-1]["message"]
    assert client.get("/api/ips").json()["documents"] == []


def test_task_and_document_not_found(client):
    assert client.get("/api/ips/tasks/nonexistent/events").status_code == 404
    assert client.get("/api/ips/ips_nobody_20260101_000000").status_code == 404
    assert client.get("/api/ips/..%2F..%2Fsecret").status_code == 404


def test_legacy_document_has_no_inferred_client_association(client):
    from src.agents import ips_storage

    _create_profile(client)  # a matching name must not imply ownership
    ips_storage.IPS_DIR.mkdir(parents=True, exist_ok=True)
    path = ips_storage.IPS_DIR / "ips_legacy_20260906_123456.json"
    path.write_text(json.dumps({"ips": {"client_name": "John Doe"}, "metadata": {}}))
    listing = client.get("/api/ips").json()["documents"]
    assert listing == []
    assert client.get(f"/api/ips/{path.stem}").status_code == 404


def test_pdf_export(client, fake_workflow):
    profile_id = _create_profile(client)
    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()[
        "task_id"
    ]
    events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)
    document_id = events[-1]["document_id"]

    resp = client.get(f"/api/ips/{document_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    assert len(resp.content) > 1000  # a real multi-section document, not an error stub
    assert "attachment" in resp.headers["content-disposition"]

    assert client.get("/api/ips/ips_nobody_20260101_000000/pdf").status_code == 404


def test_markdown_export(client, fake_workflow):
    profile_id = _create_profile(client)
    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()[
        "task_id"
    ]
    events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)
    document_id = events[-1]["document_id"]

    resp = client.get(f"/api/ips/{document_id}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment" in resp.headers["content-disposition"]
    assert "投资政策声明书" in resp.text

    assert client.get("/api/ips/ips_nobody_20260101_000000/export").status_code == 404


class BudgetExceededWorkflowApp:
    """Fake compiled graph whose run trips the token budget gate mid-stream."""

    async def astream(self, initial_state, config=None, stream_mode=None):
        yield {"generate": {"status": "generating"}}
        raise TokenBudgetExceeded(spent=12345, budget=10000)


def test_token_budget_exceeded_emits_localized_error(client, monkeypatch):
    """The budget gate aborts the task with a dedicated error event (P24)."""
    monkeypatch.setattr("api.routers.ips.is_api_configured", lambda: True)
    monkeypatch.setattr("src.agents.ips_workflow.load_ips_template", lambda: "T")
    monkeypatch.setattr(
        "src.agents.ips_workflow.compile_ips_workflow",
        lambda **kw: BudgetExceededWorkflowApp(),
    )
    profile_id = _create_profile(client)

    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()[
        "task_id"
    ]
    events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)

    # zh copy (the client fixture sends X-Locale: zh) carrying spent/budget.
    assert events[-1]["type"] == "error"
    assert "token 预算" in events[-1]["message"]
    assert "12345" in events[-1]["message"]
    assert "10000" in events[-1]["message"]


def test_invalid_publication_content_does_not_leak_to_sse(
    client, fake_workflow, monkeypatch
):
    monkeypatch.setattr(
        "src.agents.ips_workflow.compile_ips_workflow",
        lambda **kw: FakeWorkflowApp(
            final_ips={
                "client_name": "John Doe",
                "executive_summary": {"private": "SYNTHETIC_SENSITIVE_TEXT"},
            }
        ),
    )
    profile_id = _create_profile(client)
    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()[
        "task_id"
    ]
    response = client.get(f"/api/ips/tasks/{task_id}/events")
    events = _parse_sse(response.text)
    assert events[-1]["type"] == "error"
    assert "SYNTHETIC_SENSITIVE_TEXT" not in response.text
    assert client.get("/api/documents").json() == {"documents": []}
    assert client.get("/api/ips").json() == {"documents": []}
    assert list(ips_storage.IPS_DIR.glob("ips_*.json")) == []

    # Startup scans unindexed raw artifacts. A failed generation must not leave
    # a file that can become visible after that recovery pass.
    db.init_db()
    assert client.get("/api/ips").json() == {"documents": []}


@pytest.mark.parametrize("bond_weight", [0.399, 0.3])
def test_human_review_retains_unpublishable_ips(
    workspace, fake_workflow, minimal_ips_dict, monkeypatch, bond_weight
):
    client, _, _, profiles, _, headers = workspace
    raw = minimal_ips_dict
    allocation = raw["investment_guidelines"]["strategic_allocation"]
    allocation[1]["target_weight"] = bond_weight
    allocation[1]["min_weight"] = 0.0
    raw["executive_summary"] = "SYNTHETIC_REVIEW_ONLY"
    raw = IPSDocument.model_validate(raw).model_dump()

    class EscalatedWorkflowApp:
        async def astream(self, *args, **kwargs):
            yield {"finalize": await finalize_node(IPSWorkflowState(ips_draft=raw))}

    monkeypatch.setattr(
        "src.agents.ips_workflow.compile_ips_workflow",
        lambda **kw: EscalatedWorkflowApp(),
    )
    staff = headers("advisor")
    task_id = client.post(
        "/api/ips/generate", json={"profile_id": profiles["own"]}, headers=staff
    ).json()["task_id"]
    response = client.get(f"/api/ips/tasks/{task_id}/events", headers=staff)
    done = _parse_sse(response.text)[-1]
    assert done["type"] == "done" and done["success"] is True
    assert done["status"] == "completed_escalated_to_human"
    assert "SYNTHETIC_REVIEW_ONLY" not in response.text
    url = f"/api/ips/{done['document_id']}"
    response = client.get(url, headers=staff)
    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == "escalated_to_human"
    assert "SYNTHETIC_REVIEW_ONLY" in detail["markdown"]
    saved = ips_storage.load_ips(ips_storage.IPS_DIR / f"{done['document_id']}.json")
    assert saved["ips"] == raw
    assert saved["audit_trail"]["final_status"] == "escalated_to_human"
    assert client.get(url + "/export", headers=staff).status_code == 200
    assert client.get(url, headers=headers("client")).status_code == 403
    assert client.get("/api/documents", headers=staff).json() == {"documents": []}
    assert client.get("/api/me/reports", headers=headers("client")).json() == {
        "reports": []
    }
    adoption = client.post(url + "/documents", headers=staff)
    assert adoption.status_code == 422
    assert "SYNTHETIC_REVIEW_ONLY" not in adoption.text
    db.init_db()
    assert client.get(url, headers=staff).json() == detail


def test_publication_database_failure_removes_task_artifact(
    client, fake_workflow, monkeypatch
):
    def fail_draft(*args, **kwargs):
        raise RuntimeError("Synthetic database failure")

    monkeypatch.setattr("api.documents.create_draft", fail_draft)
    profile_id = _create_profile(client)
    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()[
        "task_id"
    ]
    events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)
    assert events[-1]["type"] == "error"
    assert client.get("/api/documents").json() == {"documents": []}
    assert client.get("/api/ips").json() == {"documents": []}
    assert list(ips_storage.IPS_DIR.glob("*.json")) == []
    db.init_db()
    assert client.get("/api/ips").json() == {"documents": []}
