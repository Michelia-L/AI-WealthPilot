"""
API tests for the client-profile CRUD (Phase 3c).

Uses the shared `client` fixture from conftest.py (isolated tmp-path
SQLite injected via dependency override; lifespan init patched out).
"""

import json

import pytest


def sample_payload(**overrides) -> dict:
    payload = {
        "name": "John Doe",
        "age": 30,
        "marital_status": "single",
        "dependents": 0,
        "financial": {
            "annual_income": 100000,
            "annual_expenses": 60000,
            "investable_assets": 200000,
            "total_liabilities": 0,
            "emergency_fund_months": 6.0,
        },
        "goals": [
            {
                "name": "Retirement / 退休",
                "target_amount": 2000000,
                "years": 30,
                "priority": "high",
            }
        ],
        "time_horizon_years": 30,
        "is_multi_stage": False,
        "liquidity_needs": 0.0,
        "tax_status": "taxable",
        "esg_preference": False,
        "sector_restrictions": [],
        "notes": "",
        "risk_scores": {"ability_score": 1.0, "willingness_score": 3.5},
        # Answers default to empty: non-empty answers derive scores via the
        # src questionnaire rules and override manual risk_scores on save.
        "ability_answers": {},
        "willingness_answers": {},
    }
    payload.update(overrides)
    return payload


def test_create_and_get_profile(client):
    resp = client.post("/api/profiles", json=sample_payload())
    assert resp.status_code == 201
    body = resp.json()

    assert body["id"] >= 1
    assert body["created_at"] and body["updated_at"]
    stored = body["profile"]
    assert stored["name"] == "John Doe"
    # asdict(ClientProfile) shape preserved for downstream phases
    assert stored["financial"]["investable_assets"] == 200000
    assert stored["risk_profile"]["tolerance_level"] == "Conservative / 保守型"

    derived = body["derived"]
    assert derived["net_worth"] == 200000
    assert derived["annual_savings"] == 40000
    assert derived["savings_rate"] == pytest.approx(0.4)
    assert derived["final_risk_score"] == pytest.approx(1.0)  # min(1.0, 3.5)

    got = client.get(f"/api/profiles/{body['id']}")
    assert got.status_code == 200
    assert got.json()["profile"] == stored


def test_list_profiles_ordered_by_updated_desc(client):
    client.post("/api/profiles", json=sample_payload(name="Alice"))
    client.post("/api/profiles", json=sample_payload(name="Bob"))

    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    profiles = resp.json()["profiles"]
    assert [p["name"] for p in profiles] == ["Bob", "Alice"]
    assert profiles[0]["risk_level"] == "Conservative / 保守型"


def test_update_profile_preserves_created_at(client):
    created = client.post("/api/profiles", json=sample_payload()).json()

    resp = client.put(
        f"/api/profiles/{created['id']}",
        json=sample_payload(
            name="Jane Doe",
            financial={
                "annual_income": 120000,
                "annual_expenses": 60000,
                "investable_assets": 300000,
                "total_liabilities": 50000,
                "emergency_fund_months": 6.0,
            },
        ),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"]["name"] == "Jane Doe"
    assert body["created_at"] == created["created_at"]
    assert body["derived"]["net_worth"] == 250000


def test_delete_profile(client):
    created = client.post("/api/profiles", json=sample_payload()).json()

    assert client.delete(f"/api/profiles/{created['id']}").status_code == 204
    assert client.get(f"/api/profiles/{created['id']}").status_code == 404
    assert client.get("/api/profiles").json()["profiles"] == []


def test_get_missing_profile_404(client):
    assert client.get("/api/profiles/999").status_code == 404
    assert client.delete("/api/profiles/999").status_code == 404


def test_validation_rejects_bad_payload(client):
    assert client.post("/api/profiles", json=sample_payload(name="")).status_code == 422
    assert client.post("/api/profiles", json=sample_payload(age=10)).status_code == 422
    assert (
        client.post("/api/profiles", json=sample_payload(marital_status="complicated")).status_code
        == 422
    )


def test_risk_level_classification(client):
    resp = client.post(
        "/api/profiles",
        json=sample_payload(risk_scores={"ability_score": 4.5, "willingness_score": 4.0}),
    )
    assert resp.json()["derived"]["tolerance_level"] == "Moderately Aggressive / 成长型"

    # Unassessed (zero scores) must not be mislabeled as Conservative.
    resp = client.post(
        "/api/profiles",
        json=sample_payload(risk_scores={"ability_score": 0, "willingness_score": 0}),
    )
    assert resp.json()["derived"]["tolerance_level"] == ""


def test_infinite_debt_ratio_serialized_as_none(client):
    resp = client.post(
        "/api/profiles",
        json=sample_payload(
            financial={
                "annual_income": 50000,
                "annual_expenses": 40000,
                "investable_assets": 0,
                "total_liabilities": 100000,
                "emergency_fund_months": 0,
            }
        ),
    )
    assert resp.status_code == 201
    assert resp.json()["derived"]["debt_to_asset_ratio"] is None


# ---------------------------------------------------------------------------
# Risk questionnaire (Phase 5b)
# ---------------------------------------------------------------------------


def test_questionnaire_endpoint_mirrors_src(client):
    from src.agents.profiler import RISK_ABILITY_QUESTIONS, RISK_WILLINGNESS_QUESTIONS

    resp = client.get("/api/profiles/questionnaire")
    assert resp.status_code == 200
    body = resp.json()

    assert [q["key"] for q in body["ability"]] == list(RISK_ABILITY_QUESTIONS)
    assert [q["key"] for q in body["willingness"]] == list(RISK_WILLINGNESS_QUESTIONS)

    # Option keys/scores round-trip so the client can preview live.
    first = body["ability"][0]
    src_first = RISK_ABILITY_QUESTIONS[first["key"]]
    assert {o["key"]: o["score"] for o in first["options"]} == {
        k: o["score"] for k, o in src_first["options"].items()
    }
    assert all(1 <= o["score"] <= 5 for q in body["ability"] for o in q["options"])


def test_answers_derive_scores_and_override_manual(client):
    """Non-empty answers win over manual risk_scores on save."""
    resp = client.post(
        "/api/profiles",
        json=sample_payload(
            risk_scores={"ability_score": 4.5, "willingness_score": 4.0},
            ability_answers={"income_stability": "very_unstable"},  # score 1
            willingness_answers={"loss_reaction": "buy_more"},  # score 4
        ),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["profile"]["risk_profile"]["ability_score"] == pytest.approx(1.0)
    assert body["profile"]["risk_profile"]["willingness_score"] == pytest.approx(4.0)
    assert body["derived"]["tolerance_level"] == "Conservative / 保守型"
    # Answers are stored for form prefill.
    assert body["profile"]["ability_answers"] == {"income_stability": "very_unstable"}


def test_partial_answers_average_over_answered_only(client):
    resp = client.post(
        "/api/profiles",
        json=sample_payload(
            ability_answers={
                "income_stability": "very_stable",  # 5
                "investment_knowledge": "moderate",  # 3
            },
            willingness_answers={
                "loss_reaction": "aggressively_buy",  # 5
                "gambling_scenario": "definitely_no",  # 1
            },
        ),
    )
    body = resp.json()
    assert body["profile"]["risk_profile"]["ability_score"] == pytest.approx(4.0)
    assert body["profile"]["risk_profile"]["willingness_score"] == pytest.approx(3.0)
    assert body["derived"]["tolerance_level"] == "Moderate / 平衡型"


def test_invalid_answer_keys_ignored(client):
    """Keys unknown to the src questionnaire contribute nothing (0 = unassessed)."""
    resp = client.post(
        "/api/profiles",
        json=sample_payload(
            risk_scores={"ability_score": 0, "willingness_score": 0},
            ability_answers={"not_a_question": "very_stable"},
        ),
    )
    assert resp.status_code == 201
    assert resp.json()["derived"]["tolerance_level"] == ""


# ---------------------------------------------------------------------------
# Profile comparison + behavioral biases (Phase 5c)
# ---------------------------------------------------------------------------


def _create(client, **overrides) -> int:
    resp = client.post("/api/profiles", json=sample_payload(**overrides))
    assert resp.status_code == 201
    return resp.json()["id"]


def test_compare_profiles_with_biases(client):
    alice = _create(
        client,
        name="Alice",
        risk_scores={"ability_score": 4.5, "willingness_score": 4.0},
    )
    bob = _create(
        client,
        name="Bob",
        risk_scores={"ability_score": 4.5, "willingness_score": 1.5},
        financial={
            "annual_income": 80000,
            "annual_expenses": 70000,
            "investable_assets": 100000,
            "total_liabilities": 0,
            "emergency_fund_months": 6.0,
        },
    )

    resp = client.get(f"/api/profiles/compare?ids={alice},{bob}")
    assert resp.status_code == 200
    body = resp.json()

    assert [p["name"] for p in body["profiles"]] == ["Alice", "Bob"]
    alice_entry, bob_entry = body["profiles"]
    assert alice_entry["id"] == alice
    assert alice_entry["financial_summary"]["net_worth"] == 200000
    assert alice_entry["financial_summary"]["risk_level"] == "Moderately Aggressive / 成长型"
    assert alice_entry["bias_count"] == 0

    # Bob: willingness 1.5 vs ability 4.5 → loss aversion + risk mismatch.
    assert bob_entry["bias_count"] == 2
    bias_types = {b["bias_type"] for b in bob_entry["biases"]}
    assert bias_types == {"loss_aversion", "risk_mismatch"}
    assert all(b["severity"] in ("high", "medium", "low") for b in bob_entry["biases"])

    assert body["insights"]  # risk/net-worth divergence produces insights
    assert body["comparison_date"]


def test_compare_validation(client):
    a = _create(client, name="Alice")
    b = _create(client, name="Bob")

    assert client.get(f"/api/profiles/compare?ids={a}").status_code == 422
    assert client.get("/api/profiles/compare?ids=x,y").status_code == 422
    assert client.get(f"/api/profiles/compare?ids={a},999").status_code == 404

    # Above the 6-profile cap.
    more = [_create(client, name=f"P{i}") for i in range(6)]
    assert client.get(f"/api/profiles/compare?ids={a},{b},{','.join(map(str, more))}").status_code == 422


def test_compare_rejects_duplicate_names(client):
    a = _create(client, name="Same Name")
    b = _create(client, name="Same Name")
    resp = client.get(f"/api/profiles/compare?ids={a},{b}")
    assert resp.status_code == 422
    assert "重名" in resp.json()["detail"]


def _write_legacy_profile(profiles_dir, name, created_at, **extra):
    data = sample_payload(name=name)
    # Convert the API payload back to the legacy asdict(ClientProfile) shape.
    scores = data.pop("risk_scores")
    data["risk_profile"] = {
        "ability_score": scores["ability_score"],
        "willingness_score": scores["willingness_score"],
        "tolerance_level": "Conservative / 保守型",
        "description": "",
    }
    data["created_at"] = created_at
    data["updated_at"] = created_at
    data.update(extra)
    path = profiles_dir / f"{name.lower().replace(' ', '_')}_20260608_120000.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_import_legacy_json_idempotent(client, isolate_storage_dirs):
    profiles_dir, _ = isolate_storage_dirs
    _write_legacy_profile(profiles_dir, "Legacy One", "2026-06-01T10:00:00")
    _write_legacy_profile(profiles_dir, "Legacy Two", "2026-06-02T10:00:00")

    first = client.post("/api/profiles/import")
    assert first.status_code == 200
    assert first.json() == {"files_found": 2, "imported": 2, "skipped": 0}

    second = client.post("/api/profiles/import")
    assert second.json() == {"files_found": 2, "imported": 0, "skipped": 2}

    profiles = client.get("/api/profiles").json()["profiles"]
    assert {p["name"] for p in profiles} == {"Legacy One", "Legacy Two"}
    # Original timestamps survive the import.
    detail = client.get(f"/api/profiles/{profiles[0]['id']}").json()
    assert detail["created_at"].startswith("2026-06-0")


def test_maybe_auto_import_only_seeds_empty_db(tmp_path, monkeypatch, isolate_storage_dirs):
    """maybe_auto_import seeds legacy JSON on first boot, never overwrites."""
    from sqlmodel import Session, SQLModel, create_engine, select

    from api.db import ProfileRecord
    from api.migrate_profiles import maybe_auto_import

    profiles_dir, _ = isolate_storage_dirs
    _write_legacy_profile(profiles_dir, "Legacy One", "2026-06-01T10:00:00")

    engine = create_engine(
        f"sqlite:///{tmp_path}/auto.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("api.db.engine", engine)
    monkeypatch.setattr("api.db.init_db", lambda: None)

    maybe_auto_import()
    with Session(engine) as session:
        names = session.exec(select(ProfileRecord.name)).all()
    assert names == ["Legacy One"]

    # Second boot with a non-empty DB: no re-import, no duplication.
    maybe_auto_import()
    with Session(engine) as session:
        assert len(session.exec(select(ProfileRecord.name)).all()) == 1
