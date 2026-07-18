"""
API tests for the client-profile CRUD (Phase 3c).

Each test runs against an isolated tmp-path SQLite database injected via
FastAPI dependency override; ``api.main.init_db`` is patched out so the
lifespan hook never touches the real data/wealthpilot.db.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from api.db import get_session
from api.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    # The lifespan hook would otherwise create the real data/wealthpilot.db.
    monkeypatch.setattr("api.main.init_db", lambda: None)

    app = create_app()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client


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
        "ability_answers": {"income_stability": "very_unstable"},
        "willingness_answers": {"loss_reaction": "buy_more"},
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
