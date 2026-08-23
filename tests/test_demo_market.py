"""Tests for DEMO_MODE synthetic market data (KI-002).

With DEMO_MODE on, the market data layer serves deterministic synthetic
series (src/data/demo_market.py) instead of hitting yfinance/akshare, so
the demo and the e2e suite run fully offline. conftest pins DEMO_MODE off
by default; the demo_on fixture flips it the same way test_api_demo_mode
does.
"""

import pandas as pd
import pytest

from src.config import (
    ASSET_UNIVERSE,
    DEFAULT_RISK_FREE_RATE,
    DEFAULT_RISK_FREE_RATE_CNY,
)
from src.data import demo_market, market_data
from src.data.market_data import (
    fetch_price_history,
    fetch_risk_free_rate_detailed,
    get_latest_quotes,
)


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr("src.config.DEMO_MODE", True)


def _poison_network(monkeypatch):
    """Make every external market call fail loudly if it is attempted."""

    def _boom(*args, **kwargs):
        raise AssertionError("network call attempted under DEMO_MODE")

    monkeypatch.setattr(market_data.yf, "download", _boom)
    monkeypatch.setattr(market_data.yf, "Ticker", _boom)
    monkeypatch.setattr(
        market_data.akshare_provider, "fetch_cgb_yield_1y", _boom, raising=False
    )
    monkeypatch.setattr(market_data.akshare_provider, "is_available", lambda: True)


class TestDemoPriceHistory:
    def test_deterministic_across_calls(self):
        t1 = demo_market.demo_price_history(["GC=F", "^GSPC"], period="6mo")
        t2 = demo_market.demo_price_history(["GC=F", "^GSPC"], period="6mo")
        pd.testing.assert_frame_equal(t1, t2)

    def test_shape_columns_and_grid(self):
        tickers = ["BTC-USD", "GC=F", "000300.SS"]
        df = demo_market.demo_price_history(tickers, period="1y")
        assert df.columns.tolist() == tickers
        assert len(df) == 260
        assert df.index[-1] == demo_market.REFERENCE_END
        assert (df > 0).all().all()

    def test_unknown_period_falls_back_to_1y(self):
        df = demo_market.demo_price_history(["GC=F"], period="13mo")
        assert len(df) == 260

    def test_volatility_series_stays_in_band(self):
        df = demo_market.demo_price_history(["^VIX"], period="5y")
        lo, hi = demo_market._VOLATILITY_CLAMP
        assert df["^VIX"].min() >= lo
        assert df["^VIX"].max() <= hi

    def test_quote_record_shape(self):
        rec = demo_market.demo_quote_record("GC=F")
        assert rec["ticker"] == "GC=F"
        assert rec["name"] == ASSET_UNIVERSE["GC=F"]["name"]
        assert rec["category"] == ASSET_UNIVERSE["GC=F"]["category"]
        assert rec["price"] > 0
        assert rec["previous_close"] > 0


class TestDemoHooksOffline:
    """Demo branches must serve data with the network fully poisoned."""

    def test_fetch_price_history_offline(self, demo_on, monkeypatch):
        _poison_network(monkeypatch)
        df = fetch_price_history(["GC=F", "SI=F"], period="3mo")
        assert df.columns.tolist() == ["GC=F", "SI=F"]
        assert len(df) == 66

    def test_get_latest_quotes_offline_full_universe(self, demo_on, monkeypatch):
        _poison_network(monkeypatch)
        df = get_latest_quotes()
        assert len(df) == len(ASSET_UNIVERSE)
        assert set(df.columns) >= {"ticker", "price", "previous_close", "change_pct"}
        assert (df["price"] > 0).all()

    def test_risk_free_rate_offline_cny(self, demo_on, monkeypatch):
        _poison_network(monkeypatch)
        rate, source = fetch_risk_free_rate_detailed(currency="CNY")
        assert rate == DEFAULT_RISK_FREE_RATE_CNY
        assert source == "static_fallback"

    def test_risk_free_rate_offline_usd(self, demo_on, monkeypatch):
        _poison_network(monkeypatch)
        rate, source = fetch_risk_free_rate_detailed(currency="USD")
        assert rate == DEFAULT_RISK_FREE_RATE
        assert source == "static_fallback"


class TestDemoOffRegression:
    """With DEMO_MODE off (conftest default), the real path must be taken."""

    def test_fetch_price_history_real_path(self, monkeypatch):
        sentinel = pd.DataFrame(
            {"GC=F": [1.0, 2.0]}, index=pd.bdate_range("2026-08-20", periods=2)
        )
        monkeypatch.setattr(
            market_data, "_fetch_price_history_yf", lambda *a, **k: sentinel
        )
        df = fetch_price_history(["GC=F"], period="1mo")
        pd.testing.assert_frame_equal(df, sentinel)

    def test_get_latest_quotes_real_path(self, monkeypatch):
        monkeypatch.setattr(
            market_data,
            "_fetch_quote_record",
            lambda t: {
                "ticker": t,
                "name": t,
                "category": "Unknown",
                "price": 1.0,
                "previous_close": 1.0,
            },
        )
        df = get_latest_quotes(["GC=F"])
        assert df["ticker"].tolist() == ["GC=F"]


class TestDemoMarketApi:
    """API end-to-end: demo mode + poisoned network must still serve data."""

    @pytest.fixture(autouse=True)
    def _clear_caches(self):
        from api.routers import market as market_router

        keys = [
            "quotes:GC=F,SI=F",
            "analytics:1y|GC=F,SI=F",
        ]
        for key in keys:
            market_router._quotes_cache.invalidate(key)
            market_router._analytics_cache.invalidate(key)
        yield
        for key in keys:
            market_router._quotes_cache.invalidate(key)
            market_router._analytics_cache.invalidate(key)

    def test_quotes_endpoint_offline(self, client, demo_on, monkeypatch):
        _poison_network(monkeypatch)
        resp = client.get("/api/market/quotes?tickers=GC=F,SI=F")
        assert resp.status_code == 200
        quotes = resp.json()["quotes"]
        assert [q["ticker"] for q in quotes] == ["GC=F", "SI=F"]
        assert all(q["price"] > 0 for q in quotes)
        # Sparklines derive from the same synthetic history (1mo = 22 bars).
        assert all(len(q["spark"]) == 22 for q in quotes)

    def test_analytics_endpoint_offline(self, client, demo_on, monkeypatch):
        _poison_network(monkeypatch)
        resp = client.get("/api/market/analytics?period=1y&tickers=GC=F,SI=F")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["price_chart"] is not None
        assert payload["correlation_chart"] is not None
        assert len(payload["stats"]) == 2
