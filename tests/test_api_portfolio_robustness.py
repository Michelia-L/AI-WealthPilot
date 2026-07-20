"""
Robustness tests for the portfolio optimize endpoint.

Two failure modes that previously surfaced as an unhandled 500:
- a transient upstream fetch failure (all-NaN instrument series) was cached
  for the whole TTL window, poisoning every subsequent request;
- an unsolvable efficient frontier propagated as a KeyError deep in the
  chart builder instead of a clean client-facing error.
"""

import numpy as np
import pandas as pd

from src.portfolio.optimizer import PortfolioOptimizer


def _prices_frame(tickers, nan_tickers=()):
    rng = np.random.default_rng(7)
    idx = pd.date_range("2023-01-02", periods=60, freq="B")
    data = {}
    for t in tickers:
        if t in nan_tickers:
            data[t] = np.nan
        else:
            rets = rng.normal(0.0005, 0.01, len(idx))
            data[t] = 100 * np.cumprod(1 + rets)
    return pd.DataFrame(data, index=idx)


def _body(**overrides):
    body = {
        "assets": ["US_EQUITY", "CRYPTO"],
        "period": "1y",
        "method": "mvo",
        "mode": "max-sharpe",
        "allow_short": False,
        "n_simulations": 50,
    }
    body.update(overrides)
    return body


def test_poisoned_price_frame_is_rejected_and_not_cached(client, monkeypatch):
    monkeypatch.setattr(
        "api.routers.portfolio.fetch_risk_free_rate", lambda: 0.045
    )
    calls = {"n": 0}

    def fake_fetch(tickers, period=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _prices_frame(tickers, nan_tickers=("BTC-USD",))
        return _prices_frame(tickers)

    monkeypatch.setattr("api.routers.portfolio.fetch_price_history", fake_fetch)

    first = client.post("/api/portfolio/optimize", json=_body())
    assert first.status_code == 502
    assert "BTC-USD" in first.json()["detail"]

    # The poisoned frame must never enter the TTL cache: the very next call
    # with healthy data succeeds instead of reusing the failure.
    second = client.post("/api/portfolio/optimize", json=_body())
    assert second.status_code == 200


def test_unsolvable_frontier_returns_422(client, monkeypatch):
    monkeypatch.setattr(
        "api.routers.portfolio.fetch_risk_free_rate", lambda: 0.045
    )
    rng = np.random.default_rng(3)
    idx = pd.date_range("2023-01-02", periods=60, freq="B")
    returns = pd.DataFrame(
        rng.normal(0, 0.01, (len(idx), 2)),
        index=idx,
        columns=["US Equities (S&P 500)", "Bitcoin"],
    )
    monkeypatch.setattr(
        "api.routers.portfolio._fetch_returns", lambda keys, period: returns
    )
    # Every frontier point failing produces an empty frame in practice.
    monkeypatch.setattr(
        PortfolioOptimizer,
        "efficient_frontier",
        lambda self, n_points=100, allow_short=False, mean_override=None: pd.DataFrame(),
    )

    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 422
    assert "有效前沿" in resp.json()["detail"]
