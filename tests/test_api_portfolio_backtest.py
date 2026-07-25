"""
API tests for POST /api/portfolio/backtest — backtesting arbitrary weight
maps (e.g. optimizer results) against the 60/40 benchmark.

Market data and the risk-free rate are stubbed with the same helpers the
IPS-anchored backtest tests use.
"""

import pytest

from tests.test_api_backtest import _stub_market


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
