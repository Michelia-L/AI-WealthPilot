"""
API tests for BL diagnostics: relative-view cycle warnings, per-view
impact disclosure, and market-weights source (equal / AUM / custom).

The optimizer runs for real on deterministic pseudo-returns; market
fetches (_fetch_returns) and the AUM probe (fetch_fund_aum) are
monkeypatched. Mirrors tests/test_api_cme_source.py conventions.
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


def _patch(monkeypatch, aum=None) -> None:
    monkeypatch.setattr(
        "api.routers.portfolio._fetch_returns",
        lambda keys, period, locale="zh": _fake_returns(),
    )
    monkeypatch.setattr(
        "api.routers.portfolio.fetch_fund_aum", lambda tickers: aum
    )


def _body(**overrides) -> dict:
    body = {
        "assets": ASSETS,
        "period": "5y",
        "risk_free_rate": 0.0,
        "method": "black-litterman",
        "mode": "max-sharpe",
        "bl": {
            "views": [
                {
                    "view_type": "absolute",
                    "asset_long": "US_EQUITY",
                    "expected_return": 0.08,
                    "confidence": 60,
                }
            ]
        },
    }
    body.update(overrides)
    return body


def test_cycle_warning_and_impacts(client, monkeypatch):
    """A>B, B>A relative views produce a cycle warning; every view gets an impact."""
    _patch(monkeypatch)
    body = _body(
        bl={
            "views": [
                {
                    "view_type": "relative",
                    "asset_long": "US_EQUITY",
                    "asset_short": "GOLD",
                    "expected_return": 0.02,
                    "confidence": 50,
                },
                {
                    "view_type": "relative",
                    "asset_long": "GOLD",
                    "asset_short": "US_EQUITY",
                    "expected_return": 0.01,
                    "confidence": 50,
                },
            ]
        }
    )
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    bl = resp.json()["bl"]

    assert len(bl["warnings"]) == 1
    assert "循环矛盾" in bl["warnings"][0]
    assert len(bl["view_impacts"]) == 2
    assert all(v["impact"] >= 0 for v in bl["view_impacts"])
    assert bl["market_weights_source"] == "equal"


def test_aum_market_weights(client, monkeypatch):
    """AUM figures available → equilibrium prior uses AUM weights, disclosed."""
    aum = {"SPY": 600e9, "EFA": 50e9, "AGG": 120e9, "GLD": 70e9}
    _patch(monkeypatch, aum=aum)
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    bl = resp.json()["bl"]
    assert bl["market_weights_source"] == "aum"
    # SPY-heavy AUM tilts the equilibrium prior toward equities
    eq_name = DEFAULT_ASSET_CLASSES["US_EQUITY"]["name"]
    bond_name = DEFAULT_ASSET_CLASSES["US_BOND"]["name"]
    assert bl["equilibrium_returns"][eq_name] != pytest.approx(
        bl["equilibrium_returns"][bond_name]
    )
    weights = resp.json()["selected"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_custom_market_weights_source(client, monkeypatch):
    """User-provided market weights take precedence and are disclosed."""
    _patch(monkeypatch)
    body = _body(
        bl={
            "market_weights": {"US_EQUITY": 0.25, "INTL_EQUITY": 0.25,
                               "US_BOND": 0.25, "GOLD": 0.25},
            "views": [
                {
                    "view_type": "absolute",
                    "asset_long": "US_EQUITY",
                    "expected_return": 0.08,
                    "confidence": 60,
                }
            ],
        }
    )
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    assert resp.json()["bl"]["market_weights_source"] == "custom"


def test_no_warnings_for_consistent_views(client, monkeypatch):
    """A sane single view produces no warnings."""
    _patch(monkeypatch)
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    assert resp.json()["bl"]["warnings"] == []
