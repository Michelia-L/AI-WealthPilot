"""API tests for the personalized allocation endpoint (P12).

Market data and the risk-free rate are stubbed; the real recommender runs
on deterministic fake returns.
"""

import numpy as np
import pandas as pd
import pytest

from tests.test_api_profiles import sample_payload


@pytest.fixture
def fake_market(monkeypatch):
    rng = np.random.default_rng(11)
    idx = pd.date_range("2021-01-04", periods=260, freq="B")
    columns = [
        "US Equities (S&P 500)",
        "International Developed Equities",
        "Emerging Market Equities",
        "China A-Shares (ASHR)",
        "US Aggregate Bonds",
        "Long-Term US Treasuries (TLT)",
        "High Yield Bonds (HYG)",
        "Emerging Market Bonds (EMB)",
        "Treasury Inflation-Protected",
        "Gold",
        "Broad Commodities (DBC)",
        "Real Estate (REITs)",
        "Bitcoin",
        "Cash Equivalents (BIL)",
    ]
    returns = pd.DataFrame(
        rng.normal(0.0003, 0.01, (len(idx), len(columns))), index=idx, columns=columns
    )
    # Cash is near-deterministic — keep the optimizer well-behaved.
    returns["Cash Equivalents (BIL)"] = 0.0001
    monkeypatch.setattr(
        "api.routers.portfolio._fetch_returns", lambda keys, period: returns
    )
    monkeypatch.setattr(
        "api.routers.portfolio.fetch_risk_free_rate", lambda: 0.045
    )


def _create_profile(client) -> int:
    resp = client.post("/api/profiles", json=sample_payload())
    assert resp.status_code == 201
    return resp.json()["id"]


def test_recommendation_happy_path(client, fake_market):
    profile_id = _create_profile(client)
    resp = client.get(f"/api/portfolio/recommendation?profile_id={profile_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == profile_id
    assert body["profile_name"] == sample_payload()["name"]
    assert body["risk_level"]
    total = sum(body["allocation"].values())
    assert abs(total - 1.0) < 1e-4
    assert all(w >= -1e-6 for w in body["allocation"].values())  # long-only
    assert body["expected_volatility"] > 0
    assert body["rationale"]


def test_recommendation_profile_not_found(client):
    assert client.get("/api/portfolio/recommendation?profile_id=999").status_code == 404
