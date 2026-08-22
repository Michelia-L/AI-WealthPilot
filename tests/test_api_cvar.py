"""
API tests for Mean-CVaR optimization (method="mean-cvar").

The optimizer runs for real on deterministic pseudo-returns — only the
market fetch (_fetch_returns) is monkeypatched. Mirrors the conventions
of tests/test_api_risk_constraints.py.
"""

import numpy as np
import pandas as pd

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
        "method": "mean-cvar",
        "mode": "max-sharpe",
    }
    body.update(overrides)
    return body


def test_mean_cvar_happy_path(client, monkeypatch):
    """200: selected/max_sharpe/min_vol all carry an annualized cvar."""
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    data = resp.json()

    assert data["params"]["method"] == "mean-cvar"
    assert data["params"]["cvar_confidence"] == 0.95

    for slot in ("selected", "max_sharpe", "min_vol"):
        assert data[slot]["cvar"] is not None
        assert data[slot]["cvar"] > 0
        assert abs(sum(data[slot]["weights"].values()) - 1.0) < 1e-6

    # min_vol slot = global min-CVaR: no frontier point may beat it.
    assert data["min_vol"]["cvar"] <= data["max_sharpe"]["cvar"] + 1e-9


def test_mean_cvar_min_vol_mode_selects_min_cvar(client, monkeypatch):
    """mode=min-vol ⇒ the selected portfolio is the min-CVaR one."""
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post("/api/portfolio/optimize", json=_body(mode="min-vol"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected"]["cvar"] <= data["max_sharpe"]["cvar"] + 1e-9


def test_mean_cvar_confidence_echoed(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post("/api/portfolio/optimize", json=_body(cvar_confidence=0.99))
    assert resp.status_code == 200
    assert resp.json()["params"]["cvar_confidence"] == 0.99


def test_mean_cvar_confidence_out_of_range_422(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post("/api/portfolio/optimize", json=_body(cvar_confidence=0.995))
    assert resp.status_code == 422


def test_mean_cvar_rejects_profile_risk_constraints(client, monkeypatch):
    """Risk-level group caps remain a classic-MVO-only feature."""
    _patch_returns(monkeypatch, _fake_returns())
    created = client.post("/api/profiles", json=sample_payload())
    assert created.status_code == 201
    pid = created.json()["id"]

    resp = client.post("/api/portfolio/optimize", json=_body(profile_id=pid))
    assert resp.status_code == 422


def test_other_methods_have_no_cvar(client, monkeypatch):
    """Regression: classic MVO results carry no cvar field value."""
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post("/api/portfolio/optimize", json=_body(method="mvo"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected"]["cvar"] is None
    assert data["params"]["cvar_confidence"] is None
