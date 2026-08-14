"""
API tests for risk parity optimization (method="risk-parity").

The optimizer runs for real on deterministic pseudo-returns — only the
market fetch (_fetch_returns) is monkeypatched. Mirrors the conventions
of tests/test_api_cvar.py.
"""

import numpy as np
import pandas as pd
import pytest

from src.config import DEFAULT_ASSET_CLASSES

ASSETS = ["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"]

STATS = {
    "US_EQUITY": (0.0010, 0.012),
    "INTL_EQUITY": (0.0008, 0.011),
    "US_BOND": (0.0001, 0.004),
    "GOLD": (0.0003, 0.010),
}


def _fake_returns(n: int = 504, seed: int = 7) -> pd.DataFrame:
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
        "method": "risk-parity",
        "mode": "max-sharpe",
        "allow_short": False,
    }
    body.update(overrides)
    return body


def test_risk_parity_happy_path(client, monkeypatch):
    """200: selected carries ≈ equal risk contributions; MVO benchmarks stay."""
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    data = resp.json()

    assert data["params"]["method"] == "risk-parity"
    rc = data["selected"]["risk_contributions"]
    assert rc is not None
    assert sum(rc.values()) == pytest.approx(1.0, abs=1e-6)
    # ERC identity: each of the 4 assets contributes ≈ 25%.
    for share in rc.values():
        assert share == pytest.approx(0.25, abs=0.02)

    assert abs(sum(data["selected"]["weights"].values()) - 1.0) < 1e-6
    # max_sharpe / min_vol slots remain populated as classic MVO benchmarks.
    for slot in ("max_sharpe", "min_vol"):
        assert data[slot]["weights"]
        assert data[slot]["risk_contributions"] is None


def test_risk_parity_rejects_shorting(client, monkeypatch):
    """ERC is long-only by construction (Spinu log-barrier)."""
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post(
        "/api/portfolio/optimize", json=_body(allow_short=True)
    )
    assert resp.status_code == 422


def test_risk_parity_rejects_shorting_async(client, monkeypatch):
    """The async entry applies the same long-only validation up front."""
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post(
        "/api/portfolio/optimize/async", json=_body(allow_short=True)
    )
    assert resp.status_code == 422


def test_other_methods_have_no_risk_contributions(client, monkeypatch):
    """Regression: classic MVO responses carry no risk_contributions."""
    _patch_returns(monkeypatch, _fake_returns())
    resp = client.post("/api/portfolio/optimize", json=_body(method="mvo"))
    assert resp.status_code == 200
    assert resp.json()["selected"]["risk_contributions"] is None
