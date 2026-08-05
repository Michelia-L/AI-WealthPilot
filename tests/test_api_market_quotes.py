"""
Tests for GET /api/market/quotes sparkline attachment (Phase 19).

The router-level spark logic lives in api.routers.market._attach_sparks:
one batched 1mo history fetch, per-ticker defensive degradation to an
empty spark list. Quotes are TTL-cached for 5 minutes, so every test
clears the module cache to stay isolated.
"""

import pandas as pd
import pytest

from api.routers import market as market_router


@pytest.fixture(autouse=True)
def _clear_quotes_cache():
    market_router._quotes_cache.invalidate("quotes:GC=F,SI=F")
    yield
    market_router._quotes_cache.invalidate("quotes:GC=F,SI=F")


def _stub_quotes(monkeypatch):
    df = pd.DataFrame(
        [
            {"ticker": "GC=F", "name": "Gold Futures", "category": "Commodity",
             "price": 4068.0, "previous_close": 4031.0,
             "change": 37.0, "change_pct": 0.9178},
            {"ticker": "SI=F", "name": "Silver Futures", "category": "Commodity",
             "price": 58.66, "previous_close": 57.55,
             "change": 1.11, "change_pct": 1.9288},
        ]
    )
    monkeypatch.setattr(market_router, "get_latest_quotes", lambda tickers: df)
    return df


def _closes_frame(tickers, n=30):
    idx = pd.date_range("2026-06-15", periods=n, freq="B")
    return pd.DataFrame(
        {t: [100.0 + i for i in range(n)] for t in tickers}, index=idx
    )


def test_quotes_include_sparklines(client, monkeypatch):
    _stub_quotes(monkeypatch)
    monkeypatch.setattr(
        market_router, "fetch_price_history",
        lambda **_: _closes_frame(["GC=F", "SI=F"]),
    )

    res = client.get("/api/market/quotes?tickers=GC=F,SI=F")
    assert res.status_code == 200
    quotes = {q["ticker"]: q for q in res.json()["quotes"]}
    assert len(quotes["GC=F"]["spark"]) == 22  # trimmed to ~1 trading month
    assert quotes["GC=F"]["spark"][-1] == 129.0
    assert all(isinstance(v, float) for v in quotes["SI=F"]["spark"])


def test_quotes_spark_degrades_on_history_failure(client, monkeypatch):
    _stub_quotes(monkeypatch)

    def _boom(**_):
        raise RuntimeError("provider down")

    monkeypatch.setattr(market_router, "fetch_price_history", _boom)

    res = client.get("/api/market/quotes?tickers=GC=F,SI=F")
    assert res.status_code == 200
    for q in res.json()["quotes"]:
        assert q["spark"] == []
        assert q["price"] is not None  # quote payload itself unaffected


def test_quotes_spark_handles_missing_ticker_column(client, monkeypatch):
    _stub_quotes(monkeypatch)
    # History returns only GC=F; SI=F must degrade to an empty spark.
    monkeypatch.setattr(
        market_router, "fetch_price_history",
        lambda **_: _closes_frame(["GC=F"]),
    )

    res = client.get("/api/market/quotes?tickers=GC=F,SI=F")
    assert res.status_code == 200
    quotes = {q["ticker"]: q for q in res.json()["quotes"]}
    assert len(quotes["GC=F"]["spark"]) == 22
    assert quotes["SI=F"]["spark"] == []


def test_universe_includes_vix(client):
    """The fear index ships in the asset universe as a Volatility index."""
    res = client.get("/api/market/universe")
    assert res.status_code == 200
    vix = res.json()["assets"]["^VIX"]
    assert vix["name"] == "CBOE VIX"
    assert vix["category"] == "Volatility"
    assert vix["currency"] == "Index"
    assert vix["symbol"] == ""
