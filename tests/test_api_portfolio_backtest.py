"""
API tests for POST /api/portfolio/backtest — backtesting arbitrary weight
maps (e.g. optimizer results) against the 60/40 benchmark.

Market data and the risk-free rate are stubbed with the same helpers the
IPS-anchored backtest tests use.
"""

import pytest

from tests.test_api_backtest import _price_frame, _stub_market


def _body(**overrides):
    body = {
        "weights": {"SPY": 0.6, "AGG": 0.3, "000300.SS": 0.1},
        "period": "3y",
    }
    body.update(overrides)
    return body


def test_backtest_weights_happy_path(client, monkeypatch):
    _stub_market(monkeypatch)
    resp = client.post("/api/portfolio/backtest", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "3y"
    assert body["as_of"]
    # Sparse-free inputs survive normalization with their weights intact.
    assert set(body["weights"]) == {"SPY", "AGG", "000300.SS"}
    assert abs(sum(body["weights"].values()) - 1.0) < 1e-6
    for key in (
        "total_return",
        "cagr",
        "ann_volatility",
        "max_drawdown",
        "best_day",
        "worst_day",
    ):
        assert key in body["metrics"]
    assert body["benchmark"]["name"]
    assert body["equity_chart"]["data"]
    assert body["drawdown_chart"]["data"]
    assert isinstance(body["yearly"], list)
    assert isinstance(body["stress"], list)


def test_backtest_weights_rejects_short_selling(client, monkeypatch):
    _stub_market(monkeypatch)
    resp = client.post(
        "/api/portfolio/backtest",
        json=_body(weights={"SPY": 1.2, "AGG": -0.2}),
    )
    assert resp.status_code == 422
    assert "多头" in resp.json()["detail"]


def test_backtest_weights_rejects_bad_total(client, monkeypatch):
    _stub_market(monkeypatch)
    resp = client.post(
        "/api/portfolio/backtest",
        json=_body(weights={"SPY": 3.0, "AGG": 2.0}),
    )
    assert resp.status_code == 422
    assert "合计" in resp.json()["detail"]


def test_backtest_weights_rejects_bad_period(client, monkeypatch):
    _stub_market(monkeypatch)
    resp = client.post("/api/portfolio/backtest", json=_body(period="7y"))
    assert resp.status_code == 422


def test_backtest_weights_rejects_empty_map(client):
    resp = client.post("/api/portfolio/backtest", json=_body(weights={}))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Manual fee drag (P18)
# ---------------------------------------------------------------------------


def test_backtest_weights_with_manual_fee(client, monkeypatch):
    _stub_market(monkeypatch)
    resp = client.post("/api/portfolio/backtest", json=_body(annual_fee_rate=0.02))
    assert resp.status_code == 200
    body = resp.json()
    assert body["fee"]["annual_rate"] == pytest.approx(0.02)
    assert body["fee"]["source"] == "manual"
    assert body["fee"]["gross_total_return"] > body["fee"]["net_total_return"]
    assert body["fee"]["cumulative_impact_pp"] == pytest.approx(
        body["fee"]["gross_total_return"] - body["fee"]["net_total_return"]
    )
    assert body["metrics"]["total_return"] == pytest.approx(
        body["fee"]["net_total_return"]
    )
    names = [t["name"] for t in body["equity_chart"]["data"]]
    assert "Portfolio (net)" in names
    assert "Portfolio (gross)" in names


def test_backtest_weights_default_has_no_fee(client, monkeypatch):
    _stub_market(monkeypatch)
    resp = client.post("/api/portfolio/backtest", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["fee"]["annual_rate"] == 0.0
    assert body["fee"]["source"] == "none"
    assert body["fee"]["gross_total_return"] == body["fee"]["net_total_return"]
    assert len(body["equity_chart"]["data"]) == 2


def test_backtest_weights_rejects_negative_fee(client):
    resp = client.post("/api/portfolio/backtest", json=_body(annual_fee_rate=-0.01))
    assert resp.status_code == 422


def test_backtest_weights_rejects_fee_above_cap(client):
    resp = client.post("/api/portfolio/backtest", json=_body(annual_fee_rate=0.5))
    assert resp.status_code == 422


def test_backtest_weights_fee_cache_isolation(client, monkeypatch):
    """Different fee rates must not share a cached backtest result."""
    calls = []
    df = _price_frame()

    def fake_fetch(**kw):
        calls.append(kw)
        return df

    monkeypatch.setattr("src.portfolio.backtest.fetch_price_history", fake_fetch)
    monkeypatch.setattr("src.portfolio.backtest.fetch_risk_free_rate", lambda: 0.03)

    # Distinct weights from the other tests so no earlier cache entry matches.
    body = _body(weights={"SPY": 0.7, "AGG": 0.2, "000300.SS": 0.1})
    r_zero = client.post("/api/portfolio/backtest", json=body)
    r_fee = client.post(
        "/api/portfolio/backtest", json={**body, "annual_fee_rate": 0.02}
    )
    r_fee_again = client.post(
        "/api/portfolio/backtest", json={**body, "annual_fee_rate": 0.02}
    )
    assert r_zero.status_code == r_fee.status_code == r_fee_again.status_code == 200

    zero, fee = r_zero.json(), r_fee.json()
    assert zero["fee"]["source"] == "none"
    assert fee["fee"]["annual_rate"] == pytest.approx(0.02)
    assert fee["fee"]["source"] == "manual"
    assert zero["metrics"]["total_return"] != pytest.approx(
        fee["metrics"]["total_return"]
    )
    # The repeat request is served from cache: exactly two price fetches.
    assert len(calls) == 2
    assert r_fee_again.json()["fee"]["annual_rate"] == pytest.approx(0.02)
