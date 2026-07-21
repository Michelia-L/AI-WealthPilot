"""
API tests for the AI rebalancing advice SSE endpoint (POST /monitoring/advice).

The LLM call and the monitoring engine are mocked out — tests assert the
SSE event protocol (identical to /advisor/report/stream) and the HTTP
status mapping (404 / 422 / 503), not model output or monitoring math.
"""

import pytest

from src.agents.advisor import AdvisorReport
from tests.test_api_advisor import _parse_sse
from tests.test_api_profiles import sample_payload

DOC_ID = "ips_test_20260601_093000"

FAKE_MONITORING = {
    "document_id": DOC_ID,
    "client_name": "测试客户",
    "saved_at": "2026-06-01T09:30:00",
    "as_of": "2026-07-20",
    "cme_cache_status": "cached",
    "portfolio": {"expected_return": 0.059, "volatility": 0.135, "sharpe": 0.215},
    "drifted_portfolio": {
        "expected_return": 0.0612,
        "volatility": 0.1438,
        "sharpe": 0.217,
    },
    "holdings": [
        {
            "key": "domestic_equity",
            "name": "国内权益（A股/沪深300）",
            "ticker": "000300.SS",
            "target_weight": 0.5,
            "min_weight": 0.4,
            "max_weight": 0.6,
            "drifted_weight": 0.6667,
            "drift_pp": 0.1667,
            "band_status": "above",
            "period_return": 0.80,
            "metrics": None,
        },
        {
            "key": "fixed_income",
            "name": "固定收益",
            "ticker": "AGG",
            "target_weight": 0.5,
            "min_weight": 0.4,
            "max_weight": 0.6,
            "drifted_weight": 0.3333,
            "drift_pp": -0.1667,
            "band_status": "below",
            "period_return": -0.10,
            "metrics": None,
        },
    ],
    "rebalance": {
        "needed": True,
        "trades": [
            {
                "key": "domestic_equity",
                "name": "国内权益（A股/沪深300）",
                "action": "sell",
                "weight_pp": -0.1667,
            },
            {
                "key": "fixed_income",
                "name": "固定收益",
                "action": "buy",
                "weight_pp": 0.1667,
            },
        ],
    },
    "notes": ["测试备注。"],
}


def _fake_stream(monitoring, profile=None):
    """Two token chunks, then a successful AdvisorReport."""
    yield "## 1. 漂移诊断 / Drift Diagnosis\n"
    name = profile.name if profile is not None else monitoring["client_name"]
    yield f"Rebalancing advice for {name}."
    return AdvisorReport(
        content="full content",
        model="deepseek-v4-pro",
        client_name=monitoring["client_name"],
        success=True,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
    )


@pytest.fixture
def configured(monkeypatch):
    """Pretend DEEPSEEK_API_KEY is set; stub the LLM stream and the engine."""
    monkeypatch.setattr("api.routers.monitoring.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "api.routers.monitoring.generate_rebalance_advice_stream", _fake_stream
    )
    monkeypatch.setattr(
        "api.routers.monitoring.compute_monitoring",
        lambda document_id: dict(FAKE_MONITORING),
    )


def _create_profile(client) -> int:
    resp = client.post("/api/profiles", json=sample_payload())
    assert resp.status_code == 201
    return resp.json()["id"]


def test_advice_emits_tokens_then_done(client, configured):
    resp = client.post("/api/monitoring/advice", json={"document_id": DOC_ID})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert [e["type"] for e in events] == ["token", "token", "done"]
    assert events[0]["text"].startswith("## 1.")
    assert events[1]["text"] == "Rebalancing advice for 测试客户."
    done = events[2]
    assert done["success"] is True
    assert done["model"] == "deepseek-v4-pro"
    assert done["prompt_tokens"] == 10
    assert done["completion_tokens"] == 20
    assert done["total_tokens"] == 30
    assert done["error_message"] == ""


def test_advice_document_not_found(client, configured, monkeypatch):
    def _raise_keyerror(document_id):
        raise KeyError(document_id)

    monkeypatch.setattr(
        "api.routers.monitoring.compute_monitoring", _raise_keyerror
    )
    resp = client.post(
        "/api/monitoring/advice", json={"document_id": "ips_nobody_20260101_000000"}
    )
    assert resp.status_code == 404
    assert "IPS 文档不存在" in resp.json()["detail"]


def test_advice_invalid_document_id_charset(client, configured):
    """Path-traversal-shaped ids are rejected before the engine runs."""
    resp = client.post("/api/monitoring/advice", json={"document_id": "../../etc"})
    assert resp.status_code == 404


def test_advice_missing_saa_returns_422(client, configured, monkeypatch):
    def _raise_valueerror(document_id):
        raise ValueError("IPS 文档缺少战略性资产配置（strategic_allocation），无法执行组合监控。")

    monkeypatch.setattr(
        "api.routers.monitoring.compute_monitoring", _raise_valueerror
    )
    resp = client.post("/api/monitoring/advice", json={"document_id": DOC_ID})
    assert resp.status_code == 422
    assert "战略性资产配置" in resp.json()["detail"]


def test_advice_requires_api_key(client, monkeypatch):
    monkeypatch.setattr("api.routers.monitoring.is_api_configured", lambda: False)
    resp = client.post("/api/monitoring/advice", json={"document_id": DOC_ID})
    assert resp.status_code == 503
    assert "DEEPSEEK_API_KEY" in resp.json()["detail"]


def test_advice_profile_not_found(client, configured):
    resp = client.post(
        "/api/monitoring/advice",
        json={"document_id": DOC_ID, "profile_id": 999},
    )
    assert resp.status_code == 404
    assert "画像不存在" in resp.json()["detail"]


def test_advice_with_profile(client, configured):
    profile_id = _create_profile(client)

    resp = client.post(
        "/api/monitoring/advice",
        json={"document_id": DOC_ID, "profile_id": profile_id},
    )
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    assert [e["type"] for e in events] == ["token", "token", "done"]
    # The fake stream prefers the profile name, proving the profile was
    # loaded from SQLite and passed through to the generator.
    assert events[1]["text"] == "Rebalancing advice for John Doe."
    assert events[2]["success"] is True
    assert events[2]["total_tokens"] == 30
