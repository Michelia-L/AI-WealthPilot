"""
API tests for LDI surplus optimization (method="surplus").

The optimizer runs for real on deterministic pseudo-returns — only the
market fetch (_fetch_returns) is monkeypatched. Mirrors the conventions
of tests/test_api_risk_constraints.py / tests/test_api_cvar.py.
"""

import numpy as np
import pandas as pd
import pytest

from src.config import DEFAULT_ASSET_CLASSES
from tests.test_api_profiles import sample_payload

ASSETS = ["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"]

STATS = {
    "US_EQUITY": (0.0010, 0.012),
    "INTL_EQUITY": (0.0008, 0.011),
    "US_BOND": (0.0001, 0.004),
    "GOLD": (0.0003, 0.010),
}


def _fake_returns(n: int = 504, seed: int = 7) -> pd.DataFrame:
    """Deterministic pseudo-returns with asset display names as columns."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            DEFAULT_ASSET_CLASSES[key]["name"]: rng.normal(mean, std, n)
            for key, (mean, std) in STATS.items()
        }
    )


def _patch_returns(monkeypatch, returns: pd.DataFrame) -> None:
    monkeypatch.setattr(
        "api.routers.portfolio._fetch_returns",
        lambda keys, period, locale="zh": returns,
    )


def _body(**overrides) -> dict:
    body = {
        "assets": ASSETS,
        "period": "5y",
        "risk_free_rate": 0.0,  # avoids the dynamic rf fetch
        "method": "surplus",
        "mode": "max-sharpe",
        "surplus": {
            "liability_ratio": 1.2,
            "liability_duration": 12.0,
            "proxy": "US_BOND",
            "growth_source": "inflation",
        },
    }
    body.update(overrides)
    return body


def test_surplus_manual_happy_path(client, monkeypatch):
    """Explicit ratio + duration: 200 with the assumptions echoed back."""
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    data = resp.json()

    surplus = data["surplus"]
    assert surplus["source"] == "manual"
    assert surplus["liability_ratio"] == pytest.approx(1.2)
    assert surplus["funding_ratio"] == pytest.approx(1 / 1.2)
    assert surplus["liability_duration"] == pytest.approx(12.0)
    assert surplus["proxy"] == "US_BOND"
    # inflation growth source, standard preset (no profile age in play)
    assert surplus["liability_growth"] == pytest.approx(0.025)

    assert abs(sum(data["selected"]["weights"].values()) - 1.0) < 1e-6
    assert data["risk_constraints"] is None


def test_surplus_growth_sources(client, monkeypatch):
    """risk_free uses the request rf; custom uses custom_growth."""
    _patch_returns(monkeypatch, _fake_returns())

    cfg_rf = {
        "liability_ratio": 1.0, "liability_duration": 10.0,
        "growth_source": "risk_free",
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg_rf))
    assert resp.status_code == 200
    assert resp.json()["surplus"]["liability_growth"] == pytest.approx(0.0)

    cfg_custom = {
        "liability_ratio": 1.0, "liability_duration": 10.0,
        "growth_source": "custom", "custom_growth": 0.04,
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg_custom))
    assert resp.status_code == 200
    assert resp.json()["surplus"]["liability_growth"] == pytest.approx(0.04)


def test_surplus_elderly_inflation_preset(client, monkeypatch):
    """Elderly (CPI-E style) preset uplifts the liability growth rate."""
    _patch_returns(monkeypatch, _fake_returns())
    cfg = {
        "liability_ratio": 1.0, "liability_duration": 10.0,
        "growth_source": "inflation", "inflation_preset": "elderly",
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg))
    assert resp.status_code == 200
    assert resp.json()["surplus"]["liability_growth"] == pytest.approx(0.0325)


def test_surplus_profile_channel(client, monkeypatch):
    """profile_id derives k and duration from goals + investable assets."""
    _patch_returns(monkeypatch, _fake_returns())
    created = client.post("/api/profiles", json=sample_payload())
    assert created.status_code == 201
    pid = created.json()["id"]

    body = _body(profile_id=pid)
    body["surplus"] = {"proxy": "US_BOND", "growth_source": "inflation"}
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    surplus = resp.json()["surplus"]

    assert surplus["source"] == "profile"
    # sample_payload: single 2M goal at 30y, investable 200k, age 30
    expected_k = (2_000_000 / 1.025**30) / 200_000
    assert surplus["liability_ratio"] == pytest.approx(expected_k, rel=1e-4)
    assert surplus["liability_duration"] == pytest.approx(30.0)
    # age 30 → standard preset
    assert surplus["liability_growth"] == pytest.approx(0.025)
    # The profile channel must not trigger MVO risk caps.
    assert resp.json()["risk_constraints"] is None


def test_surplus_profile_age_suggests_elderly(client, monkeypatch):
    """A 65-year-old profile gets the CPI-E-uplifted liability growth."""
    _patch_returns(monkeypatch, _fake_returns())
    created = client.post("/api/profiles", json=sample_payload(age=65))
    pid = created.json()["id"]

    body = _body(profile_id=pid)
    body["surplus"] = {"growth_source": "inflation"}
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    assert resp.json()["surplus"]["liability_growth"] == pytest.approx(0.0325)


def test_surplus_profile_without_goals_422(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns())
    created = client.post("/api/profiles", json=sample_payload(goals=[]))
    pid = created.json()["id"]

    body = _body(profile_id=pid)
    body["surplus"] = {}
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 422


def test_surplus_profile_zero_assets_422(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns())
    financial = {
        "annual_income": 100000, "annual_expenses": 60000,
        "investable_assets": 0, "total_liabilities": 0,
        "emergency_fund_months": 6.0,
    }
    created = client.post(
        "/api/profiles", json=sample_payload(financial=financial)
    )
    pid = created.json()["id"]

    body = _body(profile_id=pid)
    body["surplus"] = {}
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 422


def test_surplus_requires_any_liability_input(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns())
    body = _body()
    body["surplus"] = {}  # no ratio/duration, no profile_id
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 422


def test_surplus_invalid_proxy_422(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns())
    cfg = {
        "liability_ratio": 1.0, "liability_duration": 10.0, "proxy": "GOLD",
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg))
    assert resp.status_code == 422


def test_surplus_custom_growth_missing_422(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns())
    cfg = {
        "liability_ratio": 1.0, "liability_duration": 10.0,
        "growth_source": "custom",
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg))
    assert resp.status_code == 422


def test_surplus_proxy_outside_universe(client, monkeypatch):
    """A proxy not in the asset list is fetched alongside, then split out."""
    _patch_returns(monkeypatch, _fake_returns())
    cfg = {"liability_ratio": 1.0, "liability_duration": 10.0, "proxy": "US_BOND"}
    body = _body(assets=["US_EQUITY", "INTL_EQUITY", "GOLD"], surplus=cfg)
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    weights = resp.json()["selected"]["weights"]
    assert set(weights) == {
        DEFAULT_ASSET_CLASSES[k]["name"]
        for k in ("US_EQUITY", "INTL_EQUITY", "GOLD")
    }


def test_other_methods_have_no_surplus(client, monkeypatch):
    """Regression: classic MVO responses carry no surplus block."""
    _patch_returns(monkeypatch, _fake_returns())
    body = _body(method="mvo")
    del body["surplus"]
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    assert resp.json()["surplus"] is None
