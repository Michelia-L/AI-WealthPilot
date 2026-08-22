"""API tests for request-locale handling (Phase 22 — backend i18n).

The ``client`` fixture sends ``X-Locale: zh`` so the legacy Chinese
assertions are unchanged; these tests cover the English path: the
``bare_client`` fixture (no header), explicit ``X-Locale: en``, invalid
values, and locale-aware notes/SSE labels at both API and function level.
External calls (market data, LLM) are stubbed as usual.
"""

import json

import pytest

from api.i18n import get_request_locale, msg
from api.routers.monitoring import _resolve_annual_fee_rate
from src.portfolio.monitoring import compute_fleet_status, resolve_saa_weights
from tests.test_api_advisor import _parse_sse
from tests.test_api_profiles import sample_payload


@pytest.fixture
def ips_dir(tmp_path):
    """The tmp IPS_DIR installed by conftest.isolate_storage_dirs."""
    return tmp_path / "data" / "ips"


def _write_doc_without_saa(ips_dir, doc_id: str) -> None:
    """Persist a minimal IPS record with no strategic_allocation."""
    record = {
        "ips": {"client_name": "En Client", "version": "1.0"},
        "audit_trail": {},
        "metadata": {"client_name": "En Client", "saved_at": "2026-06-01T09:30:00"},
    }
    (ips_dir / f"{doc_id}.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Locale resolution
# ---------------------------------------------------------------------------


def test_msg_renders_and_formats():
    assert msg("common.task_not_found", "en") == "Task not found"
    assert msg("common.task_not_found", "zh") == "任务不存在"
    assert msg("common.profile_not_found", "en", id=7) == "Profile not found (id=7)"
    # Unsupported locale falls back to English; unknown keys fail loudly.
    assert msg("common.task_not_found", "fr") == "Task not found"
    with pytest.raises(KeyError):
        msg("nope.missing", "en")


def test_get_request_locale_parsing():
    from starlette.requests import Request

    def _request_with(headers: dict[str, str]) -> Request:
        return Request(
            {
                "type": "http",
                "headers": [
                    (k.lower().encode("latin-1"), v.encode("latin-1"))
                    for k, v in headers.items()
                ],
            }
        )

    assert get_request_locale(_request_with({"X-Locale": "zh"})) == "zh"
    assert get_request_locale(_request_with({"X-Locale": "en"})) == "en"
    assert get_request_locale(_request_with({"X-Locale": "EN"})) == "en"
    assert get_request_locale(_request_with({"X-Locale": "fr"})) == "en"
    assert get_request_locale(_request_with({})) == "en"


# ---------------------------------------------------------------------------
# HTTPException details
# ---------------------------------------------------------------------------


def test_missing_header_defaults_to_english(bare_client):
    resp = bare_client.get("/api/profiles/999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Profile not found (id=999)"


def test_invalid_header_falls_back_to_english(bare_client):
    resp = bare_client.get("/api/profiles/999", headers={"X-Locale": "fr"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Profile not found (id=999)"


def test_explicit_zh_keeps_verbatim_chinese(bare_client):
    resp = bare_client.get("/api/profiles/999", headers={"X-Locale": "zh"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "画像不存在（id=999）"


def test_client_fixture_sends_zh(client):
    """Sanity: the shared fixture pins Chinese for the legacy assertions."""
    resp = client.get("/api/profiles/999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "画像不存在（id=999）"


def test_report_404_english(bare_client):
    resp = bare_client.get("/api/advisor/reports/20990101_000000_000000")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Report not found"


def test_ips_doc_404_english(bare_client):
    resp = bare_client.get("/api/ips/ips_nobody_20260101_000000")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "IPS document not found"


def test_task_404_english(bare_client):
    resp = bare_client.get("/api/ips/tasks/no_such_task/events")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


def test_llm_503_english(bare_client, monkeypatch):
    """Unconfigured LLM endpoint -> 503 worded in English for en requests."""
    monkeypatch.setattr("api.routers.advisor.is_api_configured", lambda: False)
    resp = bare_client.post("/api/advisor/report/stream", json={"profile_id": 1})
    assert resp.status_code == 503
    assert resp.json()["detail"].startswith("DEEPSEEK_API_KEY is not configured")


def test_llm_503_chinese_via_zh_header(bare_client, monkeypatch):
    monkeypatch.setattr("api.routers.advisor.is_api_configured", lambda: False)
    resp = bare_client.post(
        "/api/advisor/report/stream", json={"profile_id": 1}, headers={"X-Locale": "zh"}
    )
    assert resp.status_code == 503
    assert "DEEPSEEK_API_KEY 未配置" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Monitoring notes (src/ functions + fleet API)
# ---------------------------------------------------------------------------


def test_resolve_saa_weights_error_english(ips_dir):
    doc_id = "ips_en_nosaa_20260601_093000"
    _write_doc_without_saa(ips_dir, doc_id)
    with pytest.raises(ValueError, match="strategic asset allocation"):
        resolve_saa_weights(doc_id, locale="en")
    with pytest.raises(ValueError, match="战略性资产配置"):
        resolve_saa_weights(doc_id)  # default stays Chinese


def test_fleet_note_english_function_level(ips_dir):
    doc_id = "ips_en_fleet_20260601_093000"
    _write_doc_without_saa(ips_dir, doc_id)
    item = next(
        i
        for i in compute_fleet_status(locale="en")["items"]
        if i["document_id"] == doc_id
    )
    assert item["status"] == "unknown"
    assert "strategic asset allocation" in item["note"]
    assert not any("一" <= ch <= "鿿" for ch in item["note"])


def test_fleet_note_english_via_api(bare_client, ips_dir, monkeypatch):
    doc_id = "ips_en_fleet_api_20260601_093000"
    _write_doc_without_saa(ips_dir, doc_id)
    try:
        resp = bare_client.get("/api/monitoring/status")
        assert resp.status_code == 200
        item = next(i for i in resp.json()["items"] if i["document_id"] == doc_id)
        assert "strategic asset allocation" in item["note"]
    finally:
        # The fleet TTL cache is process-level: do not leak the en entry
        # into other test files.
        from datetime import date

        from api.routers import monitoring as monitoring_router

        monitoring_router._fleet_status_cache.invalidate(
            f"fleet-status:{date.today().isoformat()}:en"
        )


def test_backtest_fee_note_english():
    rate, notes = _resolve_annual_fee_rate({}, "en")
    assert rate == 0.0
    assert notes == [
        "The IPS has no fee disclosure; no fee drag was applied in the backtest."
    ]
    _, zh_notes = _resolve_annual_fee_rate({})
    assert zh_notes == ["IPS 未包含费用披露，回测未计费用拖累。"]


# ---------------------------------------------------------------------------
# SSE labels & error events (demo replay drives the full SSE chain)
# ---------------------------------------------------------------------------


@pytest.fixture
def demo_on(monkeypatch):
    """Demo mode with fast pacing and no API key preconditions."""
    monkeypatch.setattr("src.config.DEEPSEEK_API_KEY", "")
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    monkeypatch.setattr("src.agents.demo_mode.NODE_DELAY_RANGE", (0.0, 0.0))


def _create_profile(client) -> int:
    resp = client.post("/api/profiles", json=sample_payload())
    assert resp.status_code == 201
    return resp.json()["id"]


def test_ips_sse_node_labels_english(bare_client, demo_on):
    profile_id = _create_profile(bare_client)
    created = bare_client.post("/api/ips/generate", json={"profile_id": profile_id})
    assert created.status_code == 202
    task_id = created.json()["task_id"]

    events = _parse_sse(bare_client.get(f"/api/ips/tasks/{task_id}/events").text)
    labels = [e["label"] for e in events if e["type"] == "node"]
    assert labels == [
        "Generate capital market expectations (CME)",
        "Generate IPS draft",
        "Select review reference documents",
        "Review: suitability",
        "Review: compliance",
        "Review: consistency",
        "Quantitative SAA validation",
        "Revise IPS",
        "Finalize",
    ]
    assert events[-1]["type"] == "done"


def test_ips_sse_error_message_english(bare_client, demo_on, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("src.agents.demo_mode.ips_storage.save_ips", _boom)
    profile_id = _create_profile(bare_client)
    task_id = bare_client.post(
        "/api/ips/generate", json={"profile_id": profile_id}
    ).json()["task_id"]

    events = _parse_sse(bare_client.get(f"/api/ips/tasks/{task_id}/events").text)
    assert events[-1]["type"] == "error"
    assert events[-1]["message"] == "IPS generation failed: disk full"


def test_ips_sse_labels_chinese_via_zh_header(bare_client, demo_on):
    profile_id = _create_profile(bare_client)
    created = bare_client.post(
        "/api/ips/generate",
        json={"profile_id": profile_id},
        headers={"X-Locale": "zh"},
    )
    task_id = created.json()["task_id"]
    events = _parse_sse(bare_client.get(f"/api/ips/tasks/{task_id}/events").text)
    labels = [e["label"] for e in events if e["type"] == "node"]
    assert labels[0] == "生成资本市场预期 (CME)"
    assert labels[-1] == "定稿"
