"""
API tests for demo mode (P20): fixture replay for LLM features.

With DEMO_MODE on and no DEEPSEEK_API_KEY, the three LLM endpoints replay
recorded fictional fixtures from src/agents/demo_fixtures/ instead of
calling DeepSeek — zero network calls, so the suite runs offline. Also
covers fixture integrity (downstream monitoring/backtest compatibility)
and the boot-time demo client seeding.
"""

import json
import re
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from api.db import ProfileRecord
from api.main import _demo_profile_data, _seed_demo_profile
from api.profile_convert import profile_from_data
from src.agents import demo_mode, ips_storage
from src.agents.demo_mode import DEMO_CLIENT_NAME, DEMO_CLIENT_NAME_EN, FIXTURES_DIR
from src.agents.profiler import InvestmentGoal
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
        i < first_token_idx for i, e in enumerate(events) if e["type"] == "reasoning"
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

    task_id = client.post("/api/ips/generate", json={"profile_id": profile_id}).json()[
        "task_id"
    ]
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
        lambda document_id, locale="zh": {
            "client_name": DEMO_CLIENT_NAME,
            "document_id": document_id,
        },
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
        i < first_token_idx for i, e in enumerate(events) if e["type"] == "reasoning"
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

    monkeypatch.setattr("api.routers.monitoring.compute_monitoring", _raise_keyerror)
    resp = client.post(
        "/api/monitoring/advice",
        json={"document_id": "ips_nobody_20260101_000000"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Locale-aware fixture replay (en locale → English *_en fixtures)
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r"[一-鿿]")


def test_fixture_name_selects_en_suffix_only_for_english():
    assert demo_mode._fixture_name("advisor_report.md", "en") == "advisor_report_en.md"
    assert demo_mode._fixture_name("ips_document.json", "en") == "ips_document_en.json"
    assert demo_mode._fixture_name("advisor_report.md", "zh") == "advisor_report.md"
    assert demo_mode._fixture_name("advisor_report.md", "") == "advisor_report.md"


def test_advisor_stream_demo_en_locale_replays_english_fixture(bare_client, demo_on):
    """No X-Locale header → API default en → the English fixtures replay."""
    profile_id = _create_profile(bare_client)  # sample client "John Doe"

    resp = bare_client.post(
        "/api/advisor/report/stream", json={"profile_id": profile_id}
    )
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    reasoning_text = "".join(e["text"] for e in events if e["type"] == "reasoning")
    text = "".join(e["text"] for e in events if e["type"] == "token")

    # English fixture headings; no CJK anywhere in the replayed stream.
    assert "Client Summary" in text
    assert "Asset Allocation" in text
    assert "Risk Disclosure" in text
    assert not _CJK_RE.search(text)
    assert not _CJK_RE.search(reasoning_text)
    # The English placeholder name is substituted with the profile name.
    assert "John Doe" in text
    assert "John Doe" in reasoning_text
    assert DEMO_CLIENT_NAME_EN not in text
    assert DEMO_CLIENT_NAME_EN not in reasoning_text

    done = events[-1]
    assert done["type"] == "done"
    assert done["success"] is True
    assert "demo" in done["model"]


def test_monitoring_advice_demo_en_locale_replays_english_fixture(
    bare_client, demo_on, monkeypatch
):
    monkeypatch.setattr(
        "api.routers.monitoring.compute_monitoring",
        lambda document_id, locale="zh": {
            "client_name": "John Doe",
            "document_id": document_id,
        },
    )
    profile_id = _create_profile(bare_client)

    resp = bare_client.post(
        "/api/monitoring/advice",
        json={"document_id": DOC_ID, "profile_id": profile_id},
    )
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    reasoning_text = "".join(e["text"] for e in events if e["type"] == "reasoning")
    text = "".join(e["text"] for e in events if e["type"] == "token")
    assert "Drift Diagnosis" in text
    assert "Rebalancing Recommendation" in text
    assert not _CJK_RE.search(text)
    assert not _CJK_RE.search(reasoning_text)
    assert "John Doe" in text
    assert DEMO_CLIENT_NAME_EN not in text

    done = events[-1]
    assert done["type"] == "done" and done["success"] is True


def test_ips_generate_demo_en_locale_replays_english_fixture(
    bare_client, demo_on, ips_dir, monkeypatch
):
    monkeypatch.setattr("src.agents.demo_mode.NODE_DELAY_RANGE", (0.0, 0.0))
    profile_id = _create_profile(bare_client)  # "John Doe"

    created = bare_client.post("/api/ips/generate", json={"profile_id": profile_id})
    assert created.status_code == 202
    task_id = created.json()["task_id"]

    resp = bare_client.get(f"/api/ips/tasks/{task_id}/events")
    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    node_events = [e for e in events if e["type"] == "node"]
    assert [e["node"] for e in node_events] == EXPECTED_NODES
    assert all(e["label"] for e in node_events)  # English labels attached

    done = events[-1]
    assert done["type"] == "done" and done["success"] is True

    # The English fixture document really landed in the (tmp) IPS store.
    path = ips_dir / f"{done['document_id']}.json"
    assert path.exists()
    record = ips_storage.load_ips(path)
    ips = record["ips"]
    blob = json.dumps(ips, ensure_ascii=False)
    assert ips["client_name"] == "John Doe"
    assert "John Doe" in ips["executive_summary"]
    assert DEMO_CLIENT_NAME_EN not in blob
    assert not _CJK_RE.search(blob)

    saa = ips["investment_guidelines"]["strategic_allocation"]
    assert len(saa) >= 5
    assert sum(a["target_weight"] for a in saa) == pytest.approx(1.0)


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


def test_fixture_en_ips_document_mirrors_zh_structure():
    """The English IPS fixture keeps the zh key structure and values shape."""

    def _assert_same_shape(a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            assert set(a) == set(b)
            for key in a:
                _assert_same_shape(a[key], b[key])
        elif isinstance(a, list) and isinstance(b, list):
            assert len(a) == len(b)
            for x, y in zip(a, b, strict=True):
                _assert_same_shape(x, y)

    zh_record = ips_storage.load_ips(FIXTURES_DIR / "ips_document.json")
    en_record = ips_storage.load_ips(FIXTURES_DIR / "ips_document_en.json")
    assert {"ips", "audit_trail", "metadata"} <= set(en_record)
    _assert_same_shape(zh_record, en_record)

    ips = en_record["ips"]
    saa = ips["investment_guidelines"]["strategic_allocation"]
    assert sum(a["target_weight"] for a in saa) == pytest.approx(1.0)
    for alloc in saa:
        assert alloc["min_weight"] <= alloc["target_weight"] <= alloc["max_weight"]
    fee = ips["fee_schedule"]
    assert fee["total_expense_ratio"] == pytest.approx(
        fee["management_fee_rate"]
        + fee["custody_fee_rate"]
        + fee["transaction_cost_estimate"],
        abs=1e-9,
    )
    assert ips["risk_tolerance"]["overall_risk_level"] == "moderate"
    assert en_record["audit_trail"]["final_status"] == "approved"
    # The English placeholder name is what run_demo_ips_task substitutes.
    blob = json.dumps(en_record, ensure_ascii=False)
    assert DEMO_CLIENT_NAME_EN in blob
    assert not _CJK_RE.search(blob)


def test_fixture_en_reports_pass_content_validation():
    """English fixtures face the same validators as real LLM output."""
    from src.agents.advisor import validate_report_content
    from src.agents.rebalance_advisor import validate_rebalance_content

    advisor_text = (FIXTURES_DIR / "advisor_report_en.md").read_text(encoding="utf-8")
    rebalance_text = (FIXTURES_DIR / "rebalance_advice_en.md").read_text(
        encoding="utf-8"
    )
    reasoning_text = (FIXTURES_DIR / "advisor_reasoning_en.txt").read_text(
        encoding="utf-8"
    )

    ok, err = validate_report_content(advisor_text)
    assert ok, err
    ok, err = validate_rebalance_content(rebalance_text)
    assert ok, err

    assert 2000 <= len(advisor_text) <= 8000
    assert 800 <= len(rebalance_text) <= 5000
    # Purely English fixtures with the English placeholder name.
    for text in (advisor_text, rebalance_text, reasoning_text):
        assert not _CJK_RE.search(text)
    assert DEMO_CLIENT_NAME_EN in advisor_text
    assert DEMO_CLIENT_NAME_EN in rebalance_text
    assert DEMO_CLIENT_NAME_EN in reasoning_text


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
    events, report = _collect_events(demo_mode.demo_rebalance_stream(monitoring, None))
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


# ---------------------------------------------------------------------------
# Fixture personalization (#39): profile values replace persona literals
# ---------------------------------------------------------------------------

# A profile deliberately different from the fixture persona on every field
# the replay personalizes (GitHub issue #39's scenario, extended with
# liabilities / emergency fund so every substitution pair is exercised).
ISSUE_FINANCIAL = {
    "annual_income": 900000,
    "annual_expenses": 450000,
    "investable_assets": 3600000,
    "total_liabilities": 500000,
    "emergency_fund_months": 8.0,
}
ISSUE_GOALS = [
    {"name": "教育金", "target_amount": 900000, "years": 12, "priority": "high"},
    {"name": "退休", "target_amount": 3500000, "years": 23, "priority": "high"},
]
ISSUE_RISK_SCORES = {"ability_score": 4.0, "willingness_score": 3.3}

# Persona literals that must not survive replay against the issue profile.
# "90 万" / "CNY 900,000" are excluded on purpose: they are the persona's
# mortgage but also the issue profile's income, so absence is unprovable —
# the tests assert the mortgage *contexts* instead.
ZH_STALE = [
    "林晓兰",
    "女士",
    "38 岁",
    "80 万",
    "42 万",
    "38 万",
    "260 万",
    "170 万",
    "120 万",
    "400 万",
    "47.5%",
    "34.6%",
    "9.15%",
    "2.97%",
    "4.4%",
    "6 个月",
    "10 年",
    "22 年",
    "20 年",
    "48 岁",
    "已婚",
    "一子",
    "相差 0.4 分",
    "3.4",
]
EN_STALE = [
    "Evelyn",
    "Ms.",
    "800,000",
    "420,000",
    "380,000",
    "2.6 million",
    "1.7 million",
    "1.2 million",
    "4.0 million",
    "47.5%",
    "34.6%",
    "9.15%",
    "2.97%",
    "4.4%",
    "six month",
    "10-year",
    "22-year",
    "10 years",
    "22 years",
    "20 years",
    "Ages 38",
    "to age 60",
    "0.4-point",
    "3.4",
    "married",
    "one child",
]


def _issue_profile_data() -> dict:
    """asdict(ClientProfile) shape for the issue #39 scenario."""
    ability, willingness = 4.0, 3.3
    return {
        "name": "Andrew Zhang",
        "age": 42,
        "marital_status": "single",
        "dependents": 0,
        "financial": dict(ISSUE_FINANCIAL),
        "goals": [dict(g) for g in ISSUE_GOALS],
        "time_horizon_years": 23,
        "is_multi_stage": True,
        "liquidity_needs": 0.0,
        "tax_status": "taxable",
        "esg_preference": False,
        "sector_restrictions": [],
        "notes": "",
        "risk_profile": {
            "ability_score": ability,
            "willingness_score": willingness,
            "tolerance_level": "Moderate / 平衡型",
            "description": "",
        },
        "ability_answers": {},
        "willingness_answers": {},
        "created_at": "2026-09-05T09:00:00",
        "updated_at": "2026-09-05T09:00:00",
    }


def _create_issue_profile(client) -> int:
    resp = client.post(
        "/api/profiles",
        json=sample_payload(
            name="Andrew Zhang",
            age=42,
            marital_status="single",
            dependents=0,
            financial=dict(ISSUE_FINANCIAL),
            goals=[dict(g) for g in ISSUE_GOALS],
            risk_scores=dict(ISSUE_RISK_SCORES),
        ),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_advisor_stream_demo_personalizes_fixture_to_profile(client, demo_on):
    """#39 zh: the replay swaps the persona's figures for the profile's."""
    profile_id = _create_issue_profile(client)

    resp = client.post("/api/advisor/report/stream", json={"profile_id": profile_id})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    text = "".join(e["text"] for e in events if e["type"] == "token")
    reasoning = "".join(e["text"] for e in events if e["type"] == "reasoning")

    for stale in ZH_STALE:
        assert stale not in text, f"stale persona literal in report: {stale}"
        assert stale not in reasoning, f"stale persona literal in reasoning: {stale}"
    assert "2026-07-20" not in text
    today = date.today().isoformat()
    assert today in text  # report date is the generation day

    for want in [
        "Andrew Zhang",
        "42 岁",
        "未婚，无子女",
        "收入合计 90 万元",
        "年支出 45 万元",
        "50.0%",
        "360 万元",
        "贷款余额 50 万元",
        "310 万元",
        "13.9%",
        "8 个月",
        "教育金（优先级：高）",
        "目标金额 90 万元，期限 12 年",
        "目标金额 350 万元，期限 23 年（至 65 岁）",
        "(90/50)^(1/12)",
        "(350/210)^(1/23)",
        "5.02%",
        "2.25%",
        "2.8%",
        "2.6 个百分点",
        "意愿 3.3",
        "最终评分 3.3",
        "相差 0.7 分",
    ]:
        assert want in text, f"missing personalized value: {want}"


def test_advisor_stream_demo_personalizes_en_fixture(bare_client, demo_on):
    """#39 en: same personalization against the English fixture set."""
    profile_id = _create_issue_profile(bare_client)

    resp = bare_client.post(
        "/api/advisor/report/stream", json={"profile_id": profile_id}
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    text = "".join(e["text"] for e in events if e["type"] == "token")
    reasoning = "".join(e["text"] for e in events if e["type"] == "reasoning")

    for stale in EN_STALE:
        assert stale not in text, f"stale persona literal in report: {stale}"
        assert stale not in reasoning, f"stale persona literal in reasoning: {stale}"
    assert "2026-07-20" not in text
    assert date.today().isoformat() in text
    # CJK goal names stay as the fixture's English labels (no CJK leak).
    assert not _CJK_RE.search(text)

    for want in [
        "Andrew Zhang",
        ", 42,",
        "is single with no children",
        "income is CNY 900,000",
        "CNY 450,000",
        "50.0%",
        "CNY 3.6 million",
        "mortgage balance is CNY 500,000",
        "CNY 3.1 million",
        "13.9%",
        "eight months",
        "CNY 900,000 over a 12-year horizon",
        "CNY 3.5 million over a 23-year horizon (to age 65)",
        "(90/50)^(1/12)",
        "(350/210)^(1/23)",
        "5.02%",
        "2.25%",
        "2.8%",
        "2.6 percentage points",
        "willingness of 3.3",
        "final score of 3.3",
        "0.7-point gap",
    ]:
        assert want in text, f"missing personalized value: {want}"


def test_ips_generate_demo_personalizes_document(client, demo_on, ips_dir, monkeypatch):
    """#39: the persisted IPS document carries the profile's figures."""
    monkeypatch.setattr("src.agents.demo_mode.NODE_DELAY_RANGE", (0.0, 0.0))
    profile_id = _create_issue_profile(client)

    created = client.post("/api/ips/generate", json={"profile_id": profile_id})
    assert created.status_code == 202
    task_id = created.json()["task_id"]
    events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)
    done = events[-1]
    assert done["type"] == "done" and done["success"] is True

    record = ips_storage.load_ips(ips_dir / f"{done['document_id']}.json")
    ips = record["ips"]
    assert ips["preparation_date"] == date.today().isoformat()

    goals = ips["return_objective"]["goal_level_requirements"]
    assert goals[0]["goal_name"] == "教育金"
    assert goals[0]["target_amount"] == 900000.0
    assert goals[0]["time_horizon_years"] == 12
    assert goals[0]["required_return"] == pytest.approx(0.0502, abs=1e-4)
    assert goals[1]["goal_name"] == "退休"
    assert goals[1]["target_amount"] == 3500000.0
    assert goals[1]["time_horizon_years"] == 23
    assert goals[1]["required_return"] == pytest.approx(0.0225, abs=1e-4)
    assert ips["time_horizon"]["overall_horizon_years"] == 23
    assert [s["years"] for s in ips["time_horizon"]["stages"]] == [12, 11]
    assert ips["liquidity"]["emergency_reserve_months"] == 8

    summary = ips["executive_summary"]
    assert "Andrew Zhang" in summary
    assert "42 岁" in summary
    assert "教育金（12 年 90 万元）" in summary
    assert "退休（23 年 350 万元）" in summary

    blob = json.dumps(record, ensure_ascii=False)
    for stale in ZH_STALE + [
        "2026-07-20",
        "约 21 万",
        "55 岁",
        "1.85%",
        '"required_nominal_return": 0.044',
        '"required_real_return": 0.0185',
        "1200000.0",
        "4000000.0",
    ]:
        assert stale not in blob, f"stale persona literal in IPS document: {stale}"


# ---------------------------------------------------------------------------
# Personalization unit tests (no API)
# ---------------------------------------------------------------------------


def test_personalize_without_profile_swaps_only_date_and_name():
    text = "编制日期 2026-07-20，客户林晓兰 38 岁，收入 80 万"
    out = demo_mode._personalize_fixture_text(text, "王小明", "zh", None)
    assert "2026-07-20" not in out
    assert date.today().isoformat() in out
    assert "王小明" in out and "林晓兰" not in out
    # Without a profile the persona's figures stay as recorded.
    assert "38 岁" in out and "80 万" in out


def test_personalize_skips_risk_pairs_when_unassessed():
    data = _issue_profile_data()
    data["risk_profile"] = {
        "ability_score": 0.0,
        "willingness_score": 0.0,
        "tolerance_level": "",
        "description": "",
    }
    profile = profile_from_data(data)
    text = demo_mode._load_fixture_text(
        "advisor_report.md", profile.name, "zh", profile
    )
    # Unassessed questionnaire: the persona's scores/level stay as recorded…
    assert "3.4 / 5.0" in text and "平衡型" in text
    # …while the rest of the personalization still applies.
    assert "42 岁" in text and "360 万元" in text


def test_personalize_risk_level_change():
    """A growth-grade profile rewrites the level labels in both locales."""
    data = _issue_profile_data()
    data["risk_profile"] = {
        "ability_score": 4.4,
        "willingness_score": 4.6,
        "tolerance_level": "Moderately Aggressive / 成长型",
        "description": "",
    }
    profile = profile_from_data(data)
    zh = demo_mode._load_fixture_text("advisor_report.md", profile.name, "zh", profile)
    en = demo_mode._load_fixture_text("advisor_report.md", profile.name, "en", profile)
    assert "成长型（Moderately Aggressive）" in zh
    assert "平衡型" not in zh
    assert "意愿 4.6" in zh and "最终评分 4.4" in zh
    assert "**Moderately Aggressive**" in en
    assert "willingness of 4.6" in en and "final score of 4.4" in en

    record = json.loads(
        (FIXTURES_DIR / "ips_document_en.json").read_text(encoding="utf-8")
    )
    out = json.loads(
        demo_mode._personalize_fixture_text(
            json.dumps(record, ensure_ascii=False), profile.name, "en", profile
        )
    )
    assert out["ips"]["risk_tolerance"]["overall_risk_level"] == "moderately_aggressive"


def test_personalize_single_goal_leaves_other_slot_untouched():
    """A lone retirement goal maps to the retirement slot; the fixture's
    education goal cannot be fabricated, so its figures stay as recorded."""
    data = _issue_profile_data()
    data["goals"] = [dict(ISSUE_GOALS[1])]
    profile = profile_from_data(data)
    text = demo_mode._load_fixture_text(
        "advisor_report.md", profile.name, "zh", profile
    )
    assert "350 万" in text and "23 年" in text
    assert "120 万" in text and "10 年" in text  # education slot: fixture stays


def test_match_fixture_goals_keyword_and_positional():
    edu, ret = demo_mode._match_fixture_goals(
        profile_from_data(_issue_profile_data()).goals
    )
    assert edu.name == "教育金" and ret.name == "退休"

    # No keywords, exactly two goals: the shorter horizon takes education.
    goals = [
        InvestmentGoal(name="Goal A", target_amount=1, years=5),
        InvestmentGoal(name="Goal B", target_amount=1, years=25),
    ]
    edu, ret = demo_mode._match_fixture_goals(goals)
    assert edu.name == "Goal A" and ret.name == "Goal B"

    # A single goal only fills the slot it keyword-matches.
    edu, ret = demo_mode._match_fixture_goals([InvestmentGoal(name="购房", years=5)])
    assert edu is None and ret is None


def test_demo_rebalance_stream_personalizes_date_and_reasoning():
    profile = profile_from_data(_issue_profile_data())
    monitoring = {"client_name": "Andrew Zhang", "document_id": "ips_x"}
    events, report = _collect_events(
        demo_mode.demo_rebalance_stream(monitoring, profile)
    )
    text = "".join(e["text"] for e in events if e["type"] == "token")
    reasoning = "".join(e["text"] for e in events if e["type"] == "reasoning")
    assert date.today().isoformat() in text
    assert "2026-07-20" not in text
    assert "Andrew Zhang" in text
    # The shared reasoning preamble is personalized too.
    assert "90 万" in reasoning and "80 万" not in reasoning


def test_demo_persona_profile_round_trips_fixture_values():
    """The seeded demo client matches the persona: figures survive verbatim,
    only the report date moves to the generation day."""
    profile = profile_from_data(_demo_profile_data())
    text, report = _collect(demo_mode.demo_advice_stream(profile))
    assert "80 万元" in text and "9.15%" in text and "38 岁" in text
    assert "2026-07-20" not in text
    assert date.today().isoformat() in text
