"""
Tests for the Tushare Pro provider and the market-data routing layer.

The tushare client and the yfinance fetch are both stubbed — no network.
"""

import pandas as pd
import pytest

from src.data import market_data, tushare_provider


@pytest.fixture
def cn_frame() -> pd.DataFrame:
    # Now-relative so the router's freshness guard never goes stale.
    dates = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=5)
    return pd.DataFrame(
        {"000300.SS": [4000.0, 4010.0, 4005.0, 4020.0, 4015.0]}, index=dates
    )


@pytest.fixture
def us_frame() -> pd.DataFrame:
    dates = pd.bdate_range("2026-07-01", periods=5)
    return pd.DataFrame({"SPY": [500.0, 501.0, 502.0, 501.5, 503.0]}, index=dates)


class TestProvider:
    def test_is_configured(self, monkeypatch):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")
        assert tushare_provider.is_configured() is True
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "")
        assert tushare_provider.is_configured() is False

    def test_fetch_index_history(self, monkeypatch, cn_frame):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")

        class FakePro:
            def index_daily(self, ts_code, start_date, end_date):
                assert ts_code == "000300.SH"
                return pd.DataFrame(
                    {
                        "trade_date": ["20260701", "20260702", "20260703"],
                        "close": [4000.0, 4010.0, 4005.0],
                    }
                )

        monkeypatch.setattr(tushare_provider, "_get_pro", lambda: FakePro())
        panel = tushare_provider.fetch_index_history(["000300.SS"], "1y")
        assert list(panel.columns) == ["000300.SS"]
        assert len(panel) == 3
        assert panel.index.is_monotonic_increasing
        assert panel["000300.SS"].iloc[0] == 4000.0

    def test_fetch_index_history_empty_becomes_nan_column(self, monkeypatch):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")

        class FakePro:
            def index_daily(self, ts_code, start_date, end_date):
                return pd.DataFrame()

        monkeypatch.setattr(tushare_provider, "_get_pro", lambda: FakePro())
        panel = tushare_provider.fetch_index_history(["000300.SS"], "1y")
        assert "000300.SS" in panel.columns
        assert panel["000300.SS"].isna().all()

    def test_unknown_ticker_rejected(self):
        with pytest.raises(ValueError):
            tushare_provider.fetch_index_history(["SPY"], "1y")


class TestRouter:
    def test_routes_cn_to_tushare_when_configured(
        self, monkeypatch, cn_frame, us_frame
    ):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")
        calls = {"tushare": [], "yf": []}
        monkeypatch.setattr(
            tushare_provider,
            "fetch_index_history",
            lambda tickers, period: calls["tushare"].extend(tickers) or cn_frame,
        )
        monkeypatch.setattr(
            market_data,
            "_fetch_price_history_yf",
            lambda tickers, period, interval, base_currency, adjust_currency: (
                calls["yf"].extend(tickers) or us_frame
            ),
        )
        out = market_data.fetch_price_history(["SPY", "000300.SS"], period="1y")
        assert calls["tushare"] == ["000300.SS"]
        assert calls["yf"] == ["SPY"]
        assert list(out.columns) == ["SPY", "000300.SS"]
        assert out["000300.SS"].dropna().iloc[0] == 4000.0

    def test_falls_back_to_yfinance_on_tushare_error(self, monkeypatch, us_frame):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")

        def _boom(tickers, period):
            raise RuntimeError("tushare exploded")

        monkeypatch.setattr(tushare_provider, "fetch_index_history", _boom)
        monkeypatch.setattr(
            market_data,
            "_fetch_price_history_yf",
            lambda tickers, period, interval, base_currency, adjust_currency: us_frame[
                ["SPY"]
            ].rename(columns={"SPY": tickers[0]}),
        )
        out = market_data.fetch_price_history(["000300.SS"], period="1y")
        assert out["000300.SS"].dropna().iloc[0] == 500.0

    def test_no_routing_without_token(self, monkeypatch, us_frame):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "")
        called = {"yf": 0}
        monkeypatch.setattr(
            market_data,
            "_fetch_price_history_yf",
            lambda *a, **k: (
                called.__setitem__("yf", called["yf"] + 1)
                or us_frame.rename(columns={"SPY": "000300.SS"})
            ),
        )
        monkeypatch.setattr(
            tushare_provider,
            "fetch_index_history",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应走 Tushare")),
        )
        out = market_data.fetch_price_history(["000300.SS"], period="1y")
        assert called["yf"] == 1
        assert not out.empty

    def test_no_routing_for_intraday(self, monkeypatch, us_frame):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")
        monkeypatch.setattr(
            market_data,
            "_fetch_price_history_yf",
            lambda *a, **k: us_frame.rename(columns={"SPY": "000300.SS"}),
        )
        monkeypatch.setattr(
            tushare_provider,
            "fetch_index_history",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应走 Tushare")),
        )
        out = market_data.fetch_price_history(["000300.SS"], period="1y", interval="1h")
        assert not out.empty
