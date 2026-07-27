"""
API tests for demo mode (P20): fixture replay for LLM features.

With DEMO_MODE on and no DEEPSEEK_API_KEY, the three LLM endpoints replay
recorded fictional fixtures from src/agents/demo_fixtures/ instead of
calling DeepSeek — zero network calls, so the suite runs offline. Also
covers fixture integrity (downstream monitoring/backtest compatibility)
and the boot-time demo client seeding.
"""

import json

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from api.db import ProfileRecord
from api.main import _demo_profile_data, _seed_demo_profile
from api.profile_convert import profile_from_data
from src.agents import demo_mode, ips_storage
from src.agents.demo_mode import DEMO_CLIENT_NAME, FIXTURES_DIR
from src.portfolio.monitoring import resolve_saa_weights
from tests.test_api_advisor import _parse_sse
from tests.test_api_profiles import sample_payload

DOC_ID = "ips_demo_20260720_093000"

EXPECTED_NODES = [
    "generate_cme",
    "generate",
    "select_docs",
    "review_suitability",
    "review_compliance",
    "review_consistency",
    "validate_saa",
    "revise",
    "finalize",
]


@pytest.fixture
def no_api_key(monkeypatch):
    """Guarantee the 'no DeepSeek key' precondition regardless of local .env."""
    monkeypatch.setattr("src.config.DEEPSEEK_API_KEY", "")


@pytest.fixture
def demo_on(no_api_key, monkeypatch):
    """Enable demo mode with no API key (conftest pins DEMO_MODE off)."""
    monkeypatch.setattr("src.config.DEMO_MODE", True)


@pytest.fixture
def ips_dir(tmp_path):
    """The tmp IPS_DIR installed by conftest.isolate_storage_dirs."""
    return tmp_path / "data" / "ips"


def _create_profile(client, **overrides) -> int:
    resp = client.post("/api/profiles", json=sample_payload(**overrides))
    assert resp.status_code == 201
    return resp.json()["id"]


def _collect(gen):
    """Drain a Generator[dict, None, AdvisorReport]; return (token_text, report).

    Only token event text is joined (reasoning events are dropped), so the
    result compares directly against report.content. Plain-string chunks are
    tolerated as token text.
    """
    texts = []
    try:
        while True:
            event = next(gen)
            if isinstance(event, dict):
                if event.get("type") == "token":
                    texts.append(event["text"])
            else:
                texts.append(event)
    except StopIteration as stop:
        return "".join(texts), stop.value


def _collect_events(gen):
    """Drain a Generator[dict, None, AdvisorReport]; return (events, report)."""
    events = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        return events, stop.value


# ---------------------------------------------------------------------------
# Gate matrix
# ---------------------------------------------------------------------------


def test_gate_demo_off_no_key_returns_503(client, no_api_key):
    profile_id = _create_profile(client)

    resp = client.post("/api/advisor/report/stream", json={"profile_id": profile_id})
    assert resp.status_code == 503

    resp = client.post("/api/ips/generate", json={"profile_id": profile_id})
    assert resp.status_code == 503

    resp = client.post("/api/monitoring/advice", json={"document_id": DOC_ID})
    assert resp.status_code == 503


def test_advisor_status_demo_on(client, demo_on):
    body = client.get("/api/advisor/status").json()
    assert body["configured"] is True
    assert body["demo"] is True


def test_advisor_status_demo_off_no_key(client, no_api_key):
    body = client.get("/api/advisor/status").json()
    assert body["configured"] is False
    assert body["demo"] is False


# ---------------------------------------------------------------------------
# Advisor stream (POST /advisor/report/stream)
# ---------------------------------------------------------------------------


def test_advisor_stream_demo_replays_fixture(client, demo_on):
    profile_id = _create_profile(client)  # sample client "John Doe"

    resp = client.post("/api/advisor/report/stream", json={"profile_id": profile_id})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    tokens = [e for e in events if e["type"] == "token"]
    assert len(tokens) > 5  # real chunk stream, not a single blob

    # Demo mode replays a reasoning phase before the first content token.
    reasoning = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning) >= 1
    first_token_idx = next(i for i, e in enumerate(events) if e["type"] == "token")
    assert all(
        i < first_token_idx
        for i, e in enumerate(events)
        if e["type"] == "reasoning"
    )
    # Client-name placeholder is substituted in the reasoning preamble too.
    reasoning_text = "".join(e["text"] for e in reasoning)
    assert "John Doe" in reasoning_text
    assert DEMO_CLIENT_NAME not in reasoning_text

    text = "".join(e["text"] for e in tokens)
    assert "客户概况" in text  # fixture section headings survive the stream
    assert "资产配置" in text
    # Client-name placeholder is substituted with the actual profile name.
    assert "John Doe" in text
    assert DEMO_CLIENT_NAME not in text

    done = events[-1]
    assert done["type"] == "done"
    assert done["success"] is True
    assert "demo" in done["model"]
    assert done["total_tokens"] > 0
    assert done["reasoning_tokens"] > 0
    assert done["error_message"] == ""


def test_advisor_stream_demo_profile_not_found(client, demo_on):
    resp = client.post("/api/advisor/report/stream", json={"profile_id": 999})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# IPS generation (POST /ips/generate)
# ---------------------------------------------------------------------------


def test_ips_generate_demo_replays_fixture(client, demo_on, ips_dir, monkeypatch):
    monkeypatch.setattr("src.agents.demo_mode.NODE_DELAY_RANGE", (0.0, 0.0))
    profile_id = _create_profile(client, name="王小明")

    created = client.post("/api/ips/generate", json={"profile_id": profile_id})
    assert created.status_code == 202
    task_id = created.json()["task_id"]

    resp = client.get(f"/api/ips/tasks/{task_id}/events")
    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    node_events = [e for e in events if e["type"] == "node"]
    assert [e["node"] for e in node_events] == EXPECTED_NODES
    assert all(e["label"] for e in node_events)  # Chinese labels attached

    done = events[-1]
    assert done["type"] == "done" and done["success"] is True
    assert done["status"] == "approved"
    assert done["revision_count"] == 1
    document_id = done["document_id"]

    # The fixture document really landed in the (tmp) IPS document store.
    path = ips_dir / f"{document_id}.json"
    assert path.exists()
    record = ips_storage.load_ips(path)
    ips = record["ips"]
    saa = ips["investment_guidelines"]["strategic_allocation"]
    assert len(saa) >= 5
    assert sum(a["target_weight"] for a in saa) == pytest.approx(1.0)
    assert ips["fee_schedule"]["total_expense_ratio"] > 0
    # Client-name substitution reached the persisted document.
    assert ips["client_name"] == "王小明"
    assert "王小明" in ips["executive_summary"]
    assert DEMO_CLIENT_NAME not in json.dumps(ips, ensure_ascii=False)

    # And it is listable through the document library.
    listing = client.get("/api/ips").json()["documents"]
    assert [d["document_id"] for d in listing] == [document_id]
    assert listing[0]["client_name"] == "王小明"


def test_ips_generate_demo_error_path(client, demo_on, monkeypatch):
    """A fixture-store failure surfaces as a terminal error event."""
    monkeypatch.setattr("src.agents.demo_mode.NODE_DELAY_RANGE", (0.0, 0.0))

    def _boom(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("src.agents.demo_mode.ips_storage.save_ips", _boom)
    profile_id = _create_profile(client)

    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()["task_id"]
    events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)

    assert events[-1]["type"] == "error"
    assert "disk full" in events[-1]["message"]
    assert client.get("/api/ips").json()["documents"] == []


# ---------------------------------------------------------------------------
# Rebalancing advice (POST /monitoring/advice)
# ---------------------------------------------------------------------------


def test_monitoring_advice_demo_replays_fixture(client, demo_on, monkeypatch):
    monkeypatch.setattr(
        "api.routers.monitoring.compute_monitoring",
        lambda document_id, locale="zh": {"client_name": DEMO_CLIENT_NAME, "document_id": document_id},
    )
    profile_id = _create_profile(client)

    resp = client.post(
        "/api/monitoring/advice",
        json={"document_id": DOC_ID, "profile_id": profile_id},
    )
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    tokens = [e for e in events if e["type"] == "token"]
    assert len(tokens) > 5

    # Demo mode replays a reasoning phase before the first content token.
    reasoning = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning) >= 1
    first_token_idx = next(i for i, e in enumerate(events) if e["type"] == "token")
    assert all(
        i < first_token_idx
        for i, e in enumerate(events)
        if e["type"] == "reasoning"
    )

    text = "".join(e["text"] for e in tokens)
    assert "漂移诊断" in text  # rebalance fixture content
    assert "调衡建议" in text

    done = events[-1]
    assert done["type"] == "done"
    assert done["success"] is True
    assert "demo" in done["model"]
    assert done["total_tokens"] > 0
    assert done["reasoning_tokens"] > 0


def test_monitoring_advice_demo_document_not_found(client, demo_on, monkeypatch):
    def _raise_keyerror(document_id, locale="zh"):
        raise KeyError(document_id)

    monkeypatch.setattr(
        "api.routers.monitoring.compute_monitoring", _raise_keyerror
    )
    resp = client.post(
        "/api/monitoring/advice",
        json={"document_id": "ips_nobody_20260101_000000"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Fixture integrity (no API, no network)
# ---------------------------------------------------------------------------


def test_fixture_ips_document_integrity():
    record = ips_storage.load_ips(FIXTURES_DIR / "ips_document.json")
    assert {"ips", "audit_trail", "metadata"} <= set(record)

    saa = record["ips"]["investment_guidelines"]["strategic_allocation"]
    assert len(saa) >= 5
    total = sum(a["target_weight"] for a in saa)
    assert 0.99 <= total <= 1.01
    for alloc in saa:
        assert alloc["min_weight"] <= alloc["target_weight"] <= alloc["max_weight"]

    fee = record["ips"]["fee_schedule"]
    components = (
        fee["management_fee_rate"]
        + fee["custody_fee_rate"]
        + fee["transaction_cost_estimate"]
    )
    assert fee["total_expense_ratio"] == pytest.approx(components, abs=1e-9)
    assert record["ips"]["risk_tolerance"]["overall_risk_level"]
    assert record["audit_trail"]["final_status"]


def test_fixture_saa_resolves_to_proxy_weights(ips_dir):
    """The fixture SAA must be usable by monitoring/backtest downstream."""
    (ips_dir / f"{DOC_ID}.json").write_text(
        (FIXTURES_DIR / "ips_document.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    resolved = resolve_saa_weights(DOC_ID)
    assert resolved["weights"]  # every SAA class mapped to a proxy ticker
    assert sum(resolved["weights"].values()) == pytest.approx(1.0)
    assert resolved["client_name"] == DEMO_CLIENT_NAME
    assert resolved["fee_schedule"]["total_expense_ratio"] > 0


def test_fixture_reports_pass_content_validation():
    """Fixtures must satisfy the same validators real LLM output faces."""
    from src.agents.advisor import validate_report_content
    from src.agents.rebalance_advisor import validate_rebalance_content

    advisor_text = (FIXTURES_DIR / "advisor_report.md").read_text(encoding="utf-8")
    rebalance_text = (FIXTURES_DIR / "rebalance_advice.md").read_text(encoding="utf-8")

    ok, err = validate_report_content(advisor_text)
    assert ok, err
    ok, err = validate_rebalance_content(rebalance_text)
    assert ok, err

    assert 2000 <= len(advisor_text) <= 3000
    assert 800 <= len(rebalance_text) <= 1200


def test_demo_advice_stream_generator_contract():
    profile = profile_from_data(_demo_profile_data())
    text, report = _collect(demo_mode.demo_advice_stream(profile))
    assert report.success is True
    assert report.model == "demo-fixture"
    assert report.client_name == DEMO_CLIENT_NAME
    assert report.content == text
    assert report.total_tokens == report.prompt_tokens + report.completion_tokens
    assert report.completion_tokens > 0
    assert report.reasoning_tokens > 0


def test_demo_advice_stream_emits_reasoning_before_tokens():
    """The reasoning preamble streams as reasoning events ahead of tokens."""
    profile = profile_from_data(_demo_profile_data())
    events, report = _collect_events(demo_mode.demo_advice_stream(profile))
    types = [e["type"] for e in events]
    assert "reasoning" in types
    assert types.index("reasoning") < types.index("token")
    reasoning_text = "".join(e["text"] for e in events if e["type"] == "reasoning")
    assert reasoning_text.strip()
    # The demo profile is 林晓兰 herself, so the fixture name stays as-is.
    assert DEMO_CLIENT_NAME in reasoning_text


def test_demo_rebalance_stream_generator_contract():
    monitoring = {"client_name": "王小明"}
    text, report = _collect(demo_mode.demo_rebalance_stream(monitoring, None))
    assert report.success is True
    assert report.client_name == "王小明"
    assert "王小明" in text  # placeholder substituted from monitoring dict
    assert DEMO_CLIENT_NAME not in text
    assert report.reasoning_tokens > 0


def test_demo_rebalance_stream_emits_reasoning_before_tokens():
    """The shared reasoning fixture precedes the rebalance token replay."""
    monitoring = {"client_name": "王小明"}
    events, report = _collect_events(
        demo_mode.demo_rebalance_stream(monitoring, None)
    )
    types = [e["type"] for e in events]
    assert "reasoning" in types
    assert types.index("reasoning") < types.index("token")
    reasoning_text = "".join(e["text"] for e in events if e["type"] == "reasoning")
    assert "王小明" in reasoning_text  # placeholder substituted here too
    assert DEMO_CLIENT_NAME not in reasoning_text


# ---------------------------------------------------------------------------
# Demo client seeding (api.main._seed_demo_profile)
# ---------------------------------------------------------------------------


def _tmp_session(tmp_path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path}/seed.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_seed_demo_profile_inserts_on_empty_table(tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    with _tmp_session(tmp_path) as session:
        assert _seed_demo_profile(session) is True

        rows = session.exec(select(ProfileRecord)).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.name == "林晓兰"
        assert row.age == 38
        assert "平衡型" in row.risk_level

        # Stored data round-trips through the profile converter.
        profile = profile_from_data(row.data)
        assert profile.name == "林晓兰"
        assert profile.risk_profile.final_score == pytest.approx(3.0)
        assert profile.financial.investable_assets == 2600000.0
        assert profile.financial.total_liabilities == 900000.0
        assert len(profile.goals) == 2

        # Idempotent: a second call leaves the table untouched.
        assert _seed_demo_profile(session) is False
        assert len(session.exec(select(ProfileRecord)).all()) == 1


def test_seed_demo_profile_skips_non_empty_table(tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    with _tmp_session(tmp_path) as session:
        session.add(ProfileRecord(name="既有客户", age=45, risk_level="", data={}))
        session.commit()

        assert _seed_demo_profile(session) is False
        rows = session.exec(select(ProfileRecord)).all()
        assert len(rows) == 1
        assert rows[0].name == "既有客户"


def test_seed_demo_profile_noop_outside_demo_mode(tmp_path):
    # conftest autouse pins DEMO_MODE to False.
    with _tmp_session(tmp_path) as session:
        assert _seed_demo_profile(session) is False
        assert session.exec(select(ProfileRecord)).all() == []
