"""
Tests for the akshare provider and the CN fallback chain
(Tushare Pro → akshare → yfinance).
"""

import pandas as pd
import pytest

from src.data import akshare_provider, market_data, tushare_provider


def _cn_frame() -> pd.DataFrame:
    # Now-relative so the freshness guard never turns the fixture stale.
    dates = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=3)
    return pd.DataFrame({"000300.SS": [4000.0, 4010.0, 4005.0]}, index=dates)


class TestAkshareProvider:
    def test_supports(self):
        assert akshare_provider.supports("000300.SS") is True
        assert akshare_provider.supports("SPY") is False

    def test_fetch_index_history(self, monkeypatch):
        raw = pd.DataFrame(
            {
                "date": ["2025-01-02", "2026-07-21", "2026-07-22"],
                "close": [3900.0, 4000.0, 4010.0],
            }
        )
        monkeypatch.setattr(akshare_provider, "_fetch_symbol_close", lambda symbol: raw)
        panel = akshare_provider.fetch_index_history(["000300.SS"], "1y")
        assert list(panel.columns) == ["000300.SS"]
        # The old row outside the lookback window is sliced away.
        assert len(panel) == 2
        assert panel.index.is_monotonic_increasing

    def test_unknown_ticker_rejected(self):
        with pytest.raises(ValueError):
            akshare_provider.fetch_index_history(["SPY"], "1y")

    def test_bad_period_rejected(self):
        with pytest.raises(ValueError):
            akshare_provider.fetch_index_history(["000300.SS"], "7y")


class TestFetchCgbYield1y:
    """CNY risk-free leg: latest 1Y treasury yield from the ChinaBond frame."""

    def _stacked_frame(self) -> pd.DataFrame:
        # Mirrors ak.bond_china_yield: several curve families stacked under
        # 曲线名称, ascending dates, newest treasury 1Y quote NaN (holiday).
        return pd.DataFrame(
            {
                "曲线名称": [
                    "中债国债收益率曲线",
                    "中债国债收益率曲线",
                    "中债商业银行普通债收益率曲线(AAA)",
                    "中债国债收益率曲线",
                ],
                "日期": ["2026-07-29", "2026-07-30", "2026-07-31", "2026-07-31"],
                "1年": [1.50, 1.60, 9.99, None],
            }
        )

    def test_latest_non_null_treasury_quote(self, monkeypatch):
        monkeypatch.setattr(
            akshare_provider,
            "_fetch_bond_china_yield",
            lambda start_date, end_date: self._stacked_frame(),
        )
        # Non-treasury curve (9.99) and NaN tail are both skipped.
        assert akshare_provider.fetch_cgb_yield_1y() == pytest.approx(1.60)

    def test_empty_frame_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            akshare_provider,
            "_fetch_bond_china_yield",
            lambda start_date, end_date: pd.DataFrame(),
        )
        assert akshare_provider.fetch_cgb_yield_1y() is None

    def test_missing_1y_column_returns_none(self, monkeypatch):
        frame = pd.DataFrame(
            {"曲线名称": ["中债国债收益率曲线"], "日期": ["2026-07-31"], "10年": [1.7]}
        )
        monkeypatch.setattr(
            akshare_provider,
            "_fetch_bond_china_yield",
            lambda start_date, end_date: frame,
        )
        assert akshare_provider.fetch_cgb_yield_1y() is None


class TestFallbackChain:
    def test_tushare_success_skips_akshare(self, monkeypatch):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")
        monkeypatch.setattr(
            tushare_provider, "fetch_index_history", lambda t, p: _cn_frame()
        )
        monkeypatch.setattr(akshare_provider, "is_available", lambda: True)
        monkeypatch.setattr(
            akshare_provider,
            "fetch_index_history",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应走到 akshare")),
        )
        out = market_data._fetch_cn_routed(["000300.SS"], "1y", "1d", None, False)
        assert out["000300.SS"].iloc[0] == 4000.0

    def test_akshare_serves_when_tushare_fails(self, monkeypatch):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")

        def _boom(t, p):
            raise RuntimeError("tushare exploded")

        monkeypatch.setattr(tushare_provider, "fetch_index_history", _boom)
        monkeypatch.setattr(akshare_provider, "is_available", lambda: True)
        monkeypatch.setattr(
            akshare_provider, "fetch_index_history", lambda t, p: _cn_frame()
        )
        out = market_data._fetch_cn_routed(["000300.SS"], "1y", "1d", None, False)
        assert out["000300.SS"].iloc[0] == 4000.0

    def test_akshare_serves_when_no_token(self, monkeypatch):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "")
        monkeypatch.setattr(akshare_provider, "is_available", lambda: True)
        monkeypatch.setattr(
            akshare_provider, "fetch_index_history", lambda t, p: _cn_frame()
        )
        out = market_data._fetch_cn_routed(["000300.SS"], "1y", "1d", None, False)
        assert out["000300.SS"].iloc[0] == 4000.0

    def test_yfinance_is_last_resort(self, monkeypatch):
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "tok")

        def _boom(t, p):
            raise RuntimeError("boom")

        monkeypatch.setattr(tushare_provider, "fetch_index_history", _boom)
        monkeypatch.setattr(akshare_provider, "is_available", lambda: True)
        monkeypatch.setattr(akshare_provider, "fetch_index_history", _boom)
        monkeypatch.setattr(
            market_data,
            "_fetch_price_history_yf",
            lambda *a, **k: pd.DataFrame(
                {"000300.SS": [1.0]},
                index=pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=1),
            ),
        )
        out = market_data._fetch_cn_routed(["000300.SS"], "1y", "1d", None, False)
        assert out["000300.SS"].iloc[0] == 1.0

    def test_stale_akshare_frame_falls_through(self, monkeypatch):
        """A silently week-stale snapshot counts as failure, not success."""
        monkeypatch.setattr(tushare_provider, "TUSHARE_TOKEN", "")
        monkeypatch.setattr(akshare_provider, "is_available", lambda: True)
        stale = pd.DataFrame(
            {"000300.SS": [1.0]}, index=pd.bdate_range("2020-01-02", periods=1)
        )
        monkeypatch.setattr(akshare_provider, "fetch_index_history", lambda t, p: stale)
        monkeypatch.setattr(
            market_data,
            "_fetch_price_history_yf",
            lambda *a, **k: pd.DataFrame(
                {"000300.SS": [2.0]},
                index=pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=1),
            ),
        )
        out = market_data._fetch_cn_routed(["000300.SS"], "1y", "1d", None, False)
        assert out["000300.SS"].iloc[0] == 2.0
