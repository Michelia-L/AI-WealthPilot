"""
API tests for CME-sourced expected returns (expected_return_source="cme").

The optimizer runs for real on deterministic pseudo-returns; _fetch_returns
is monkeypatched (per test_api_cvar.py conventions) and compute_cme is
monkeypatched to a fabricated CMEReport with distinctive expected returns.
"""

import numpy as np
import pandas as pd
import pytest

from src.config import DEFAULT_ASSET_CLASSES
from src.portfolio.cme_models import AssetClassCME, CMEReport

ASSETS = ["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"]

STATS = {
    "US_EQUITY": (0.0010, 0.012),
    "INTL_EQUITY": (0.0008, 0.011),
    "US_BOND": (0.0001, 0.004),
    "GOLD": (0.0003, 0.010),
}

# Distinctive CME expectations: bonds wildly attractive, everything else dull.
CME_EXPECTED = {"AGG": 0.50, "EFA": 0.01, "GLD": 0.01}


def _fake_returns(n: int = 504, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            DEFAULT_ASSET_CLASSES[key]["name"]: rng.normal(mean, std, n)
            for key, (mean, std) in STATS.items()
        }
    )


def _fake_cme_report() -> CMEReport:
    return CMEReport(
        as_of_date="2026-08-13",
        data_lookback_years=5,
        risk_free_rate=0.02,
        risk_free_rate_source="test",
        inflation_assumption=0.025,
        asset_classes=[
            AssetClassCME(
                name=f"CME {ticker}",
                ticker=ticker,
                expected_return=er,
                volatility=0.10,
                sharpe_ratio=0.5,
                max_drawdown=-0.20,
                var_95=0.02,
                cvar_95=0.03,
            )
            for ticker, er in CME_EXPECTED.items()
        ],
        correlation_matrix={},
        methodology_notes="test",
    )


def _patch(monkeypatch, cme_impl=None) -> None:
    monkeypatch.setattr(
        "api.routers.portfolio._fetch_returns",
        lambda keys, period, locale="zh": _fake_returns(),
    )
    monkeypatch.setattr(
        "api.routers.portfolio.compute_cme",
        cme_impl or (lambda **_: (_fake_cme_report(), "fresh")),
    )
    # BL market-cap weights: no real yfinance AUM calls in tests.
    monkeypatch.setattr(
        "api.routers.portfolio.fetch_fund_aum", lambda tickers: None
    )


def _body(**overrides) -> dict:
    body = {
        "assets": ASSETS,
        "period": "5y",
        "risk_free_rate": 0.0,  # avoids the dynamic rf fetch
        "method": "mvo",
        "mode": "max-sharpe",
        "expected_return_source": "cme",
    }
    body.update(overrides)
    return body


def test_cme_source_happy_path(client, monkeypatch):
    """200: source echoed; unmapped assets disclosed as sample fallbacks."""
    _patch(monkeypatch)
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    params = resp.json()["params"]

    assert params["expected_return_source"] == "cme"
    # SPY has no CME counterpart — it must appear in the fallback list.
    assert params["cme_fallback_assets"] == [
        DEFAULT_ASSET_CLASSES["US_EQUITY"]["name"]
    ]


def test_cme_source_changes_allocation(client, monkeypatch):
    """A 50% CME bond expectation must visibly load the bond leg."""
    _patch(monkeypatch)
    bond_name = DEFAULT_ASSET_CLASSES["US_BOND"]["name"]

    sample_resp = client.post(
        "/api/portfolio/optimize", json=_body(expected_return_source="sample")
    )
    cme_resp = client.post("/api/portfolio/optimize", json=_body())
    assert sample_resp.status_code == cme_resp.status_code == 200

    w_sample = sample_resp.json()["selected"]["weights"][bond_name]
    w_cme = cme_resp.json()["selected"]["weights"][bond_name]
    assert w_cme > w_sample + 0.2


def test_cme_source_black_litterman_prior(client, monkeypatch):
    """BL accepts the CME vector as its prior; uncovered assets re-anchor
    to their equilibrium returns."""
    _patch(monkeypatch)
    body = _body(
        method="black-litterman",
        bl={
            "views": [
                {
                    "view_type": "absolute",
                    "asset_long": "US_EQUITY",
                    "expected_return": 0.1,
                    "confidence": 70,
                }
            ]
        },
    )
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    data = resp.json()
    bl = data["bl"]

    assert bl["prior_source"] == "cme"
    # Covered assets take the CME values as prior.
    bond_name = DEFAULT_ASSET_CLASSES["US_BOND"]["name"]
    assert bl["prior_returns"][bond_name] == pytest.approx(CME_EXPECTED["AGG"])
    # Uncovered SPY re-anchors to equilibrium and is disclosed.
    spy_name = DEFAULT_ASSET_CLASSES["US_EQUITY"]["name"]
    assert bl["prior_returns"][spy_name] == pytest.approx(
        bl["equilibrium_returns"][spy_name]
    )
    assert data["params"]["cme_fallback_assets"] == [spy_name]


def test_cme_source_black_litterman_equilibrium_default(client, monkeypatch):
    """BL without the source field keeps the equilibrium prior."""
    _patch(monkeypatch)
    body = _body(
        method="black-litterman",
        bl={
            "views": [
                {
                    "view_type": "absolute",
                    "asset_long": "US_EQUITY",
                    "expected_return": 0.1,
                    "confidence": 70,
                }
            ]
        },
    )
    del body["expected_return_source"]
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    bl = resp.json()["bl"]
    assert bl["prior_source"] == "equilibrium"
    assert bl["prior_returns"] is None


def test_cme_source_black_litterman_async_accepted(client, monkeypatch):
    """The async entry accepts BL + CME (prior mode) up front."""
    _patch(monkeypatch)
    body = _body(
        method="black-litterman",
        bl={
            "views": [
                {
                    "view_type": "absolute",
                    "asset_long": "US_EQUITY",
                    "expected_return": 0.1,
                    "confidence": 70,
                }
            ]
        },
    )
    resp = client.post("/api/portfolio/optimize/async", json=body)
    assert resp.status_code == 202


def test_cme_unavailable_502(client, monkeypatch):
    def boom(**_):
        raise RuntimeError("no cache, no fallback")

    _patch(monkeypatch, cme_impl=boom)
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 502


def test_default_sample_source_unchanged(client, monkeypatch):
    """Regression: no source field ⇒ sample means, no fallback disclosure."""
    _patch(monkeypatch)
    body = _body()
    del body["expected_return_source"]
    resp = client.post("/api/portfolio/optimize", json=body)
    assert resp.status_code == 200
    params = resp.json()["params"]
    assert params["expected_return_source"] == "sample"
    assert params["cme_fallback_assets"] is None
