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
    """profile_id derives k and duration from goals + investable assets.

    v2 convention: nominal goals are discounted at the risk-free leg
    (rf=0 in the body) and drift at μ_L = rf.
    """
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
    # sample_payload: single 2M goal at 30y, investable 200k; rf=0 ⇒ PV=2M
    expected_k = 2_000_000 / 200_000
    assert surplus["liability_ratio"] == pytest.approx(expected_k, rel=1e-4)
    assert surplus["liability_duration"] == pytest.approx(30.0)
    # Nominal goals drift at the discount rate, not the inflation growth.
    assert surplus["liability_growth"] == pytest.approx(0.0)
    assert surplus["discount_rate"] == pytest.approx(0.0)
    assert surplus["cash_flows"] == 1
    assert surplus["horizon_years"] == pytest.approx(30.0)
    # The profile channel must not trigger MVO risk caps.
    assert resp.json()["risk_constraints"] is None


def test_surplus_retirement_channel_age_suggests_elderly(client, monkeypatch):
    """A 65-year-old profile gets the CPI-E-uplifted stream growth."""
    _patch_returns(monkeypatch, _fake_returns())
    created = client.post("/api/profiles", json=sample_payload(age=65))
    pid = created.json()["id"]

    body = _body(profile_id=pid)
    body["surplus"] = {
        "growth_source": "inflation",
        "years_to_retirement": 5,
        "distribution_years": 20,
        "annual_income": 80000,
    }
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    surplus = resp.json()["surplus"]
    assert surplus["source"] == "retirement"
    assert surplus["liability_growth"] == pytest.approx(0.0325)


def test_surplus_retirement_channel_manual_base(client, monkeypatch):
    """Retirement stream with explicit asset_value: hand-checked PV and k.

    t0=5, n=20, income=80k, g=2.5% (standard), rf=0 ⇒
    PV = 80k × Σ_{t=6}^{25} 1.025^t, duration = Σ t·PV_t / PV.
    """
    _patch_returns(monkeypatch, _fake_returns())
    cfg = {
        "growth_source": "inflation",
        "years_to_retirement": 5,
        "distribution_years": 20,
        "annual_income": 80000,
        "asset_value": 1_000_000,
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg))
    assert resp.status_code == 200
    surplus = resp.json()["surplus"]

    pvs = {t: 80000 * 1.025**t for t in range(6, 26)}
    pv_total = sum(pvs.values())
    expected_duration = sum(t * p for t, p in pvs.items()) / pv_total

    assert surplus["source"] == "retirement"
    assert surplus["liability_ratio"] == pytest.approx(pv_total / 1_000_000, rel=1e-4)
    assert surplus["liability_duration"] == pytest.approx(expected_duration, rel=1e-4)
    assert surplus["liability_growth"] == pytest.approx(0.025)
    assert surplus["discount_rate"] == pytest.approx(0.0)
    assert surplus["cash_flows"] == 20
    assert surplus["horizon_years"] == pytest.approx(25.0)


def test_surplus_retirement_channel_requires_asset_base(client, monkeypatch):
    """No profile and no asset_value ⇒ 422."""
    _patch_returns(monkeypatch, _fake_returns())
    cfg = {
        "growth_source": "inflation",
        "years_to_retirement": 5,
        "distribution_years": 20,
        "annual_income": 80000,
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg))
    assert resp.status_code == 422


def test_surplus_china_treasury_curve_discounting(client, monkeypatch):
    """When the curve cascade yields data, each flow discounts at y(t).

    Fixed curve {1y: 1%, 30y: 3%}: t=6..25 flows interpolate between the
    two nodes; discount_source and the representative rate are disclosed.
    """
    from src.data.yield_curve import rate_at

    _patch_returns(monkeypatch, _fake_returns())
    curve = {1.0: 0.01, 30.0: 0.03}
    monkeypatch.setattr(
        "api.routers.portfolio._effective_discount_curve",
        lambda: (curve, "china_treasury_curve"),
    )
    cfg = {
        "growth_source": "inflation",
        "years_to_retirement": 5,
        "distribution_years": 20,
        "annual_income": 80000,
        "asset_value": 1_000_000,
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg))
    assert resp.status_code == 200
    surplus = resp.json()["surplus"]

    pvs = {
        t: 80000 * 1.025**t / (1.0 + rate_at(curve, t)) ** t
        for t in range(6, 26)
    }
    pv_total = sum(pvs.values())
    expected_duration = sum(t * p for t, p in pvs.items()) / pv_total

    assert surplus["discount_source"] == "china_treasury_curve"
    assert surplus["liability_ratio"] == pytest.approx(pv_total / 1_000_000, rel=1e-4)
    assert surplus["liability_duration"] == pytest.approx(expected_duration, rel=1e-4)
    assert surplus["discount_rate"] == pytest.approx(
        rate_at(curve, expected_duration), rel=1e-4
    )


def test_surplus_cn_treasury_proxy(client, monkeypatch):
    """The CN bond proxy is fetched alongside and split out of the universe."""
    rng = np.random.default_rng(7)
    names = [DEFAULT_ASSET_CLASSES[k]["name"] for k in ASSETS]
    data = {
        name: rng.normal(STATS[key][0], STATS[key][1], 504)
        for key, name in zip(ASSETS, names, strict=False)
    }
    data[DEFAULT_ASSET_CLASSES["CN_TREASURY"]["name"]] = rng.normal(0.0001, 0.002, 504)
    _patch_returns(monkeypatch, pd.DataFrame(data))

    cfg = {
        "liability_ratio": 1.0,
        "liability_duration": 10.0,
        "proxy": "CN_TREASURY",
    }
    resp = client.post("/api/portfolio/optimize", json=_body(surplus=cfg))
    assert resp.status_code == 200
    data_resp = resp.json()
    assert data_resp["surplus"]["proxy"] == "CN_TREASURY"
    # The proxy column must not leak into the optimized universe.
    assert set(data_resp["selected"]["weights"]) == set(names)


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


def _fake_returns_dated(n: int = 300, seed: int = 7) -> pd.DataFrame:
    """Fake returns on a business-day index, for curve-history alignment."""
    idx = pd.bdate_range("2025-01-06", periods=n)
    return _fake_returns(n, seed).set_axis(idx)


def _fake_curve_history(idx: pd.DatetimeIndex) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    y10 = 0.02 + np.cumsum(rng.normal(0.0, 0.0004, len(idx)))
    return pd.DataFrame({1.0: y10 - 0.005, 10.0: y10}, index=idx)


def test_surplus_sigma_from_curve(client, monkeypatch):
    """Curve history available → σ_L estimated from yield changes."""
    returns = _fake_returns_dated()
    _patch_returns(monkeypatch, returns)
    monkeypatch.setattr(
        "api.routers.portfolio._curve_history",
        lambda: _fake_curve_history(returns.index),
    )
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    surplus = resp.json()["surplus"]
    assert surplus["sigma_l_source"] == "china_treasury_curve"
    assert abs(sum(resp.json()["selected"]["weights"].values()) - 1.0) < 1e-6


def test_surplus_sigma_proxy_fallback(client, monkeypatch):
    """No curve history → duration-scaled proxy model, as before."""
    _patch_returns(monkeypatch, _fake_returns())
    monkeypatch.setattr("api.routers.portfolio._curve_history", lambda: None)
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    assert resp.json()["surplus"]["sigma_l_source"] == "bond_proxy"
