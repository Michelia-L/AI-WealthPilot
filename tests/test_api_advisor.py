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


@pytest.fixture
def configured_reasoning(monkeypatch):
    """Stub a reasoning-capable streaming generator (event-dict protocol)."""
    monkeypatch.setattr("api.routers.advisor.is_api_configured", lambda: True)

    def fake_stream(profile):
        yield {"type": "reasoning", "text": "先分析客户画像。"}
        yield {"type": "reasoning", "text": "再测算投资目标。"}
        yield {"type": "token", "text": f"Report body for {profile.name}."}
        return AdvisorReport(
            content="full content",
            model="deepseek-reasoner",
            client_name=profile.name,
            success=True,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            reasoning_tokens=12,
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
    assert done["reasoning_tokens"] == 0  # string-yielding fake: no reasoning
    assert done["error_message"] == ""


def test_stream_emits_reasoning_then_tokens_then_done(client, configured_reasoning):
    """Reasoning events stream before token events; done carries their usage."""
    profile_id = _create_profile(client)

    resp = client.post("/api/advisor/report/stream", json={"profile_id": profile_id})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert [e["type"] for e in events] == ["reasoning", "reasoning", "token", "done"]
    assert events[0]["text"] == "先分析客户画像。"
    assert events[1]["text"] == "再测算投资目标。"
    assert events[2]["text"] == "Report body for John Doe."
    done = events[3]
    assert done["success"] is True
    assert done["model"] == "deepseek-reasoner"
    assert done["total_tokens"] == 30
    assert done["reasoning_tokens"] == 12
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


def _save_report(client) -> str:
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
    return saved.json()["report_id"]


def test_export_report_html_and_markdown(client):
    report_id = _save_report(client)

    html = client.get(f"/api/advisor/reports/{report_id}/export?format=html")
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert "attachment" in html.headers["content-disposition"]
    assert "投资咨询建议书" in html.text

    md = client.get(f"/api/advisor/reports/{report_id}/export?format=markdown")
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert md.text.startswith("# Investment Advisory Report")
    assert "Some advice." in md.text

    js = client.get(f"/api/advisor/reports/{report_id}/export?format=json")
    assert js.status_code == 200
    payload = js.json()
    assert payload["client_name"] == "John Doe"
    assert payload["content"] == "# Report\nSome advice."
    # internal paths never leave the API surface, even in exports
    assert "filepath" not in payload
    assert "profile_filepath" not in payload


def test_export_report_validation_and_missing(client):
    report_id = _save_report(client)
    assert (
        client.get(f"/api/advisor/reports/{report_id}/export?format=pdf").status_code
        == 422
    )
    assert (
        client.get("/api/advisor/reports/20990101_000000_000000/export").status_code
        == 404
    )


def test_export_report_cjk_client_name(client):
    """CJK client names must not crash the latin-1 Content-Disposition header."""
    saved = client.post(
        "/api/advisor/reports",
        json={
            "client_name": "张伟",
            "content": "# 建议\n一些建议内容。",
            "model": "deepseek-v4-pro",
            "prompt_tokens": 10,
            "completion_tokens": 20,
        },
    )
    assert saved.status_code == 201
    report_id = saved.json()["report_id"]

    for fmt in ("html", "markdown", "json"):
        resp = client.get(f"/api/advisor/reports/{report_id}/export?format={fmt}")
        assert resp.status_code == 200
        disposition = resp.headers["content-disposition"]
        assert "attachment" in disposition
        assert "filename*=" in disposition  # full UTF-8 name preserved by RFC 5987


def _save_rich_report(client) -> str:
    """Save a report with representative Markdown (headings/lists/table)."""
    saved = client.post(
        "/api/advisor/reports",
        json={
            "client_name": "张伟",
            "content": (
                "# 一、客户概况\n"
                "客户风险承受能力为 **稳健型**，投资期限 5 年。\n\n"
                "## 二、资产配置建议\n"
                "- 权益类资产：30%\n"
                "- 固收类资产：60%\n"
                "1. 优先考虑指数基金\n"
                "2. 每年再平衡一次\n\n"
                "| 资产类别 | 目标权重 |\n"
                "|----------|----------|\n"
                "| 股票 | 30% |\n"
                "| 债券 | 60% |\n\n"
                "本建议基于客户画像与当前市场环境生成，仅供参考。\n"
            ),
            "model": "deepseek-v4-pro",
            "prompt_tokens": 100,
            "completion_tokens": 200,
        },
    )
    assert saved.status_code == 201
    return saved.json()["report_id"]


def test_export_report_pdf(client):
    report_id = _save_rich_report(client)

    resp = client.get(f"/api/advisor/reports/{report_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert "attachment" in resp.headers["content-disposition"]
    # Valid PDF magic number, with real content (works on both the CJK-font
    # path and the latin-1 sanitize fallback path).
    assert resp.content.startswith(b"%PDF-")
    assert len(resp.content) > 1000


def test_export_report_pdf_not_found(client):
    assert (
        client.get("/api/advisor/reports/20990101_000000_000000/pdf").status_code
        == 404
    )
