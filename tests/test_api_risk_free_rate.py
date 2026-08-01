"""
Tests for GET /api/market/risk-free-rate (phase 23).

The endpoint feeds the optimizer page's rf auto-fill. Optimizer returns are
FX-adjusted to the base currency, so the endpoint must serve the
base-currency (CNY) leg of fetch_risk_free_rate.
"""

import pytest

from api.routers import market as market_router
from src.config import BASE_CURRENCY


@pytest.fixture(autouse=True)
def _clear_rf_cache():
    market_router._rf_cache.invalidate("rf")
    yield
    market_router._rf_cache.invalidate("rf")


def test_risk_free_rate_uses_base_currency_leg(client, monkeypatch):
    seen = {}

    def fake_fetch(*args, **kwargs):
        seen.update(kwargs)
        return 0.0185

    monkeypatch.setattr(market_router, "fetch_risk_free_rate", fake_fetch)

    res = client.get("/api/market/risk-free-rate")

    assert res.status_code == 200
    body = res.json()
    assert body["rate"] == 0.0185
    assert "as_of" in body
    assert seen.get("currency") == BASE_CURRENCY == "CNY"
