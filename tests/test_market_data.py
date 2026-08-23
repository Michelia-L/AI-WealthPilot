"""
AI WealthPilot - Market Data Module Tests
AI WealthPilot - 市场数据模块测试

Unit tests for the market data acquisition, returns, and correlation computation.
市场数据获取、收益率计算及相关性分析的单元测试。
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data.market_data import (
    compute_correlation_matrix,
    compute_returns,
    fetch_price_history,
    fetch_risk_free_rate,
    fetch_risk_free_rate_detailed,
    get_latest_quotes,
)

# ============================================================
# Test Cases — 单元测试用例
# ============================================================


class TestFetchPriceHistory:
    """
    Test suite for fetch_price_history.
    测试获取价格历史数据。
    """

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_default_tickers(self, mock_download):
        """Should use default tickers from config when no tickers specified."""
        from src.config import ASSET_UNIVERSE

        default_tickers = list(ASSET_UNIVERSE.keys())

        # Mock yf.download return value
        # It returns a MultiIndex DataFrame when multiple tickers are downloaded
        dates = pd.date_range(start="2026-06-01", periods=3)
        columns = pd.MultiIndex.from_product([["Close"], default_tickers])
        mock_df = pd.DataFrame(
            np.random.randn(3, len(default_tickers)),
            index=dates,
            columns=columns,
        )
        mock_download.return_value = mock_df

        result = fetch_price_history(
            tickers=None, period="5y", interval="1d", adjust_currency=False
        )

        # Verify yf.download was called correctly
        mock_download.assert_called_once_with(
            default_tickers, period="5y", interval="1d", auto_adjust=True
        )
        # Verify result contains the default tickers
        assert list(result.columns) == default_tickers
        assert len(result) == 3

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_multiple_tickers(self, mock_download):
        """Should download and process MultiIndex column DataFrame for multiple tickers."""
        tickers = ["SPY", "GLD"]
        dates = pd.date_range(start="2026-06-01", periods=3)
        columns = pd.MultiIndex.from_product([["Close", "Open"], tickers])
        mock_df = pd.DataFrame(
            [
                [100.0, 200.0, 99.0, 199.0],
                [110.0, 210.0, 109.0, 209.0],
                [120.0, 220.0, 119.0, 219.0],
            ],
            index=dates,
            columns=columns,
        )
        mock_download.return_value = mock_df

        result = fetch_price_history(
            tickers, period="1y", interval="1d", adjust_currency=False
        )

        mock_download.assert_called_once_with(
            tickers, period="1y", interval="1d", auto_adjust=True
        )
        assert list(result.columns) == tickers
        assert result.iloc[0]["SPY"] == 100.0
        assert result.iloc[0]["GLD"] == 200.0

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_single_ticker(self, mock_download):
        """Should rename the single column correctly when yf returns a single-level column DataFrame."""
        tickers = ["SPY"]
        dates = pd.date_range(start="2026-06-01", periods=3)
        mock_df = pd.DataFrame(
            {"Close": [100.0, 110.0, 120.0], "Open": [99.0, 109.0, 119.0]}, index=dates
        )
        mock_download.return_value = mock_df

        result = fetch_price_history(
            tickers, period="2y", interval="1d", adjust_currency=False
        )

        mock_download.assert_called_once_with(
            tickers, period="2y", interval="1d", auto_adjust=True
        )
        assert list(result.columns) == ["SPY"]
        assert result.iloc[0]["SPY"] == 100.0

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_drops_nan_rows(self, mock_download):
        """Should drop rows where all values are NaN."""
        tickers = ["SPY", "GLD"]
        dates = pd.date_range(start="2026-06-01", periods=3)
        columns = pd.MultiIndex.from_product([["Close"], tickers])
        mock_df = pd.DataFrame(
            [[100.0, 200.0], [np.nan, np.nan], [120.0, 220.0]],
            index=dates,
            columns=columns,
        )
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, adjust_currency=False)

        assert len(result) == 2
        # The index at pos 1 should be the third day (index date 2026-06-03)
        assert result.index[1] == dates[2]

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_with_currency_adjustment_usd(self, mock_download):
        """Should convert non-USD prices to USD correctly using downloaded exchange rates."""
        tickers = ["000300.SS", "^GSPC"]
        expected_download = ["000300.SS", "^GSPC", "CNY=X"]

        dates = pd.date_range(start="2026-06-01", periods=3)
        mock_data = {
            ("Close", "^GSPC"): [100.0, 101.0, 102.0],
            ("Close", "000300.SS"): [7000.0, 7100.0, 7200.0],
            ("Close", "CNY=X"): [7.0, 7.1, 7.2],
        }
        mock_df = pd.DataFrame(mock_data, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, base_currency="USD", adjust_currency=True)

        called_args = mock_download.call_args[0][0]
        assert set(called_args) == set(expected_download)
        assert list(result.columns) == tickers

        np.testing.assert_array_almost_equal(
            result["^GSPC"].values, [100.0, 101.0, 102.0]
        )
        np.testing.assert_array_almost_equal(
            result["000300.SS"].values, [1000.0, 1000.0, 1000.0]
        )

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_with_currency_adjustment_cny(self, mock_download):
        """Should convert USD and other prices to CNY correctly using downloaded exchange rates."""
        tickers = ["000300.SS", "^GSPC"]
        expected_download = ["000300.SS", "^GSPC", "CNY=X"]

        dates = pd.date_range(start="2026-06-01", periods=3)
        mock_data = {
            ("Close", "^GSPC"): [100.0, 101.0, 102.0],
            ("Close", "000300.SS"): [7000.0, 7100.0, 7200.0],
            ("Close", "CNY=X"): [7.0, 7.1, 7.2],
        }
        mock_df = pd.DataFrame(mock_data, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, base_currency="CNY", adjust_currency=True)

        called_args = mock_download.call_args[0][0]
        assert set(called_args) == set(expected_download)
        assert list(result.columns) == tickers

        np.testing.assert_array_almost_equal(
            result["000300.SS"].values, [7000.0, 7100.0, 7200.0]
        )
        np.testing.assert_array_almost_equal(
            result["^GSPC"].values, [700.0, 717.1, 734.4]
        )

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_with_currency_adjustment_gbp_to_usd(
        self, mock_download
    ):
        """GBP=X is quoted USD-per-GBP, so GBP prices must be multiplied, not divided."""
        tickers = ["^FTSE"]
        expected_download = ["^FTSE", "GBP=X"]

        dates = pd.date_range(start="2026-06-01", periods=3)
        mock_data = {
            ("Close", "^FTSE"): [8000.0, 8100.0, 8200.0],
            ("Close", "GBP=X"): [1.25, 1.25, 1.25],
        }
        mock_df = pd.DataFrame(mock_data, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, base_currency="USD", adjust_currency=True)

        called_args = mock_download.call_args[0][0]
        assert set(called_args) == set(expected_download)
        assert list(result.columns) == tickers

        np.testing.assert_array_almost_equal(
            result["^FTSE"].values, [10000.0, 10125.0, 10250.0]
        )

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_with_currency_adjustment_eur_to_cny(
        self, mock_download
    ):
        """EUR prices convert via the USD-per-EUR rate, then USD to CNY via the units-per-USD rate."""
        tickers = ["^GDAXI"]
        expected_download = ["^GDAXI", "EUR=X", "CNY=X"]

        dates = pd.date_range(start="2026-06-01", periods=3)
        mock_data = {
            ("Close", "^GDAXI"): [1000.0, 1100.0, 1200.0],
            ("Close", "EUR=X"): [1.10, 1.10, 1.10],
            ("Close", "CNY=X"): [7.0, 7.0, 7.0],
        }
        mock_df = pd.DataFrame(mock_data, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, base_currency="CNY", adjust_currency=True)

        called_args = mock_download.call_args[0][0]
        assert set(called_args) == set(expected_download)
        assert list(result.columns) == tickers

        np.testing.assert_array_almost_equal(
            result["^GDAXI"].values, [7700.0, 8470.0, 9240.0]
        )

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_with_currency_adjustment_usd_to_gbp_base(
        self, mock_download
    ):
        """A USD-per-unit base currency converts USD prices by dividing, not multiplying."""
        tickers = ["^GSPC"]
        expected_download = ["^GSPC", "GBP=X"]

        dates = pd.date_range(start="2026-06-01", periods=3)
        mock_data = {
            ("Close", "^GSPC"): [100.0, 200.0, 400.0],
            ("Close", "GBP=X"): [1.25, 1.25, 1.25],
        }
        mock_df = pd.DataFrame(mock_data, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, base_currency="GBP", adjust_currency=True)

        called_args = mock_download.call_args[0][0]
        assert set(called_args) == set(expected_download)
        assert list(result.columns) == tickers

        np.testing.assert_array_almost_equal(
            result["^GSPC"].values, [80.0, 160.0, 320.0]
        )


class TestComputeReturns:
    """
    Test suite for compute_returns.
    测试计算收益率。
    """

    def test_compute_returns_simple(self):
        """Should calculate arithmetic/simple returns: (P_t - P_{t-1}) / P_{t-1}."""
        prices = pd.DataFrame({"Asset": [100.0, 110.0, 121.0]})
        returns = compute_returns(prices, method="simple")
        # Row 0 (100.0) is dropped because of diff.
        # Row 1 simple return = (110 - 100) / 100 = 0.10
        # Row 2 simple return = (121 - 110) / 110 = 0.10
        assert len(returns) == 2
        np.testing.assert_array_almost_equal(returns["Asset"].values, [0.1, 0.1])

    def test_compute_returns_log(self):
        """Should calculate logarithmic returns: ln(P_t / P_{t-1})."""
        prices = pd.DataFrame({"Asset": [100.0, 110.0, 121.0]})
        returns = compute_returns(prices, method="log")
        expected_returns = np.log([1.1, 1.1])
        assert len(returns) == 2
        np.testing.assert_array_almost_equal(returns["Asset"].values, expected_returns)


class TestComputeCorrelationMatrix:
    """
    Test suite for compute_correlation_matrix.
    测试计算相关性矩阵。
    """

    def test_compute_correlation_matrix(self):
        """Should compute Pearson correlation matrix correctly from price DataFrame."""
        prices = pd.DataFrame(
            {
                "A": [100.0, 101.0, 99.99, 100.9899],
                "B": [100.0, 101.0, 99.99, 100.9899],
                "C": [100.0, 99.0, 99.99, 98.9901],
            }
        )
        corr = compute_correlation_matrix(prices)

        assert corr.shape == (3, 3)
        assert list(corr.columns) == ["A", "B", "C"]
        # Perfectly correlated A and B
        np.testing.assert_almost_equal(corr.loc["A", "A"], 1.0)
        np.testing.assert_almost_equal(corr.loc["A", "B"], 1.0)
        # Negatively correlated A and C
        assert corr.loc["A", "C"] < -0.9


class TestGetLatestQuotes:
    """
    Test suite for get_latest_quotes.
    测试获取最新行情。
    """

    @patch("src.data.market_data.yf.Ticker")
    def test_get_latest_quotes_success(self, mock_ticker_class):
        """Should retrieve latest quotes and compute change metrics successfully."""
        mock_ticker = MagicMock()
        mock_ticker_class.return_value = mock_ticker

        mock_fast_info = MagicMock()

        # Mock fast_info behavior for ticker calls
        # We need mock_fast_info.get to return appropriate values
        def get_side_effect(key, default=None):
            data = {"lastPrice": 105.0, "previousClose": 100.0}
            return data.get(key, default)

        mock_fast_info.get.side_effect = get_side_effect
        mock_ticker.fast_info = mock_fast_info

        tickers = ["BTC-USD", "GC=F"]
        df = get_latest_quotes(tickers)

        # Assert correct columns
        expected_cols = [
            "ticker",
            "name",
            "category",
            "price",
            "previous_close",
            "change",
            "change_pct",
        ]
        assert list(df.columns) == expected_cols
        assert len(df) == 2

        # Assert calculated metrics
        # change = 105.0 - 100.0 = 5.0
        # change_pct = (5.0 / 100.0) * 100 = 5.0
        for i in range(2):
            assert df.iloc[i]["price"] == 105.0
            assert df.iloc[i]["previous_close"] == 100.0
            assert df.iloc[i]["change"] == 5.0
            assert df.iloc[i]["change_pct"] == 5.0

    @patch("src.data.market_data.yf.Ticker")
    def test_get_latest_quotes_handling_failures(self, mock_ticker_class):
        """Should handle ticker lookup exceptions gracefully and skip failed tickers."""
        # Success ticker mock
        mock_ticker_success = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = lambda key, default=None: {
            "lastPrice": 150.0,
            "previousClose": 150.0,
        }.get(key, default)
        mock_ticker_success.fast_info = mock_fast_info

        # Raising exception on specific ticker
        def ticker_side_effect(ticker):
            if ticker == "FAIL":
                raise Exception("API failure or connection error")
            return mock_ticker_success

        mock_ticker_class.side_effect = ticker_side_effect

        tickers = ["SUCCESS", "FAIL"]
        df = get_latest_quotes(tickers)

        # FAIL ticker should be skipped, only SUCCESS should be returned
        assert len(df) == 1
        assert df.iloc[0]["ticker"] == "SUCCESS"
        assert df.iloc[0]["price"] == 150.0

    def test_get_latest_quotes_preserves_ticker_order(self, monkeypatch):
        """Concurrent fetching must preserve the requested ticker order."""
        from src.data import market_data

        def fake_fetch(ticker):
            return {
                "ticker": ticker,
                "name": ticker,
                "category": "Unknown",
                "price": float(len(ticker)),  # distinct per ticker
                "previous_close": 1.0,
            }

        monkeypatch.setattr(market_data, "_fetch_quote_record", fake_fetch)
        tickers = ["AAAA", "B", "CCC", "DD"]
        df = get_latest_quotes(tickers)
        assert df["ticker"].tolist() == tickers
        assert df["price"].tolist() == [4.0, 1.0, 3.0, 2.0]

    def test_get_latest_quotes_skips_none_records(self, monkeypatch):
        """A None from the per-ticker fetcher (any failure) drops the ticker."""
        from src.data import market_data

        def fake_fetch(ticker):
            if ticker == "GONE":
                return None
            return {
                "ticker": ticker,
                "name": ticker,
                "category": "Unknown",
                "price": 10.0,
                "previous_close": 9.0,
            }

        monkeypatch.setattr(market_data, "_fetch_quote_record", fake_fetch)
        df = get_latest_quotes(["KEEP", "GONE", "KEEP2"])
        assert df["ticker"].tolist() == ["KEEP", "KEEP2"]


class TestFetchRiskFreeRate:
    """
    Test suite for fetch_risk_free_rate.
    测试动态获取无风险利率。
    """

    @patch("src.data.market_data.requests.get")
    def test_fetch_risk_free_rate_fred_success(self, mock_get):
        """Should return FRED rate when api key is provided and request succeeds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"observations": [{"value": "3.85"}]}
        mock_get.return_value = mock_response

        rate = fetch_risk_free_rate(fred_api_key="mock_key", default_rate=0.045)
        # Expected: 3.85 / 100 = 0.0385
        assert rate == 0.0385
        mock_get.assert_called_once()
        assert "DGS3MO" in mock_get.call_args[1]["params"]["series_id"]

    @patch("src.data.market_data.requests.get")
    def test_fetch_risk_free_rate_fred_missing_value(self, mock_get):
        """Should fall back to yfinance when FRED returns invalid data (e.g. '.')."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"observations": [{"value": "."}]}
        mock_get.return_value = mock_response

        # Mock yfinance to fail to verify it reaches yfinance then falls back
        with patch("src.data.market_data.yf.Ticker") as mock_ticker_class:
            mock_ticker_class.side_effect = Exception("yfinance error")
            rate = fetch_risk_free_rate(fred_api_key="mock_key", default_rate=0.045)
            # Should fall back to default_rate
            assert rate == 0.045

    @patch("src.data.market_data.requests.get")
    @patch("src.data.market_data.yf.Ticker")
    def test_fetch_risk_free_rate_yfinance_fast_info(self, mock_ticker_class, mock_get):
        """Should return yfinance rate using fast_info when FRED key is not provided."""
        # Mock FRED request to not be called (since no key)
        # Mock yfinance fast_info
        mock_ticker = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = lambda key, default=None: {
            "lastPrice": 3.62
        }.get(key, default)
        mock_ticker.fast_info = mock_fast_info
        mock_ticker_class.return_value = mock_ticker

        rate = fetch_risk_free_rate(fred_api_key=None, default_rate=0.045)
        # Expected: 3.62 / 100 = 0.0362
        assert rate == 0.0362
        mock_get.assert_not_called()
        mock_ticker_class.assert_called_once_with("^IRX")

    @patch("src.data.market_data.requests.get")
    @patch("src.data.market_data.yf.Ticker")
    def test_fetch_risk_free_rate_yfinance_history_fallback(
        self, mock_ticker_class, mock_get
    ):
        """Should fall back to ticker.history when fast_info returns None or empty."""
        mock_ticker = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.get.return_value = None  # fast_info fails
        mock_ticker.fast_info = mock_fast_info

        # Mock history DataFrame
        mock_hist = pd.DataFrame(
            {"Close": [3.55]}, index=pd.date_range("2026-06-01", periods=1)
        )
        mock_ticker.history.return_value = mock_hist
        mock_ticker_class.return_value = mock_ticker

        rate = fetch_risk_free_rate(fred_api_key=None, default_rate=0.045)
        # Expected: 3.55 / 100 = 0.0355
        assert rate == 0.0355

    @patch("src.data.market_data.requests.get")
    @patch("src.data.market_data.yf.Ticker")
    def test_fetch_risk_free_rate_all_fail_fallback(self, mock_ticker_class, mock_get):
        """Should return default_rate when all sources fail."""
        mock_ticker_class.side_effect = Exception("yf connection failure")

        rate = fetch_risk_free_rate(fred_api_key=None, default_rate=0.045)
        assert rate == 0.045


class TestFetchRiskFreeRateCNY:
    """
    Test suite for the CNY leg of fetch_risk_free_rate (phase 23).
    akshare 中债国债 1 年期收益率 → 静态 2% 回退。
    """

    def _enable_akshare(self, monkeypatch, yield_value):
        monkeypatch.setattr(
            "src.data.market_data.akshare_provider.is_available", lambda: True
        )
        monkeypatch.setattr(
            "src.data.market_data.akshare_provider.fetch_cgb_yield_1y",
            lambda: yield_value,
        )

    def test_cny_leg_akshare_success(self, monkeypatch):
        """CNY leg converts the akshare 1Y CGB yield (percent) to decimal."""
        self._enable_akshare(monkeypatch, 1.85)

        rate = fetch_risk_free_rate(currency="CNY")

        assert rate == pytest.approx(0.0185)

    def test_cny_leg_source_label(self, monkeypatch):
        """Detailed variant reports the akshare source label."""
        self._enable_akshare(monkeypatch, 1.85)

        rate, source = fetch_risk_free_rate_detailed(currency="CNY")

        assert rate == pytest.approx(0.0185)
        assert source == "akshare_cgb_1y"

    def test_cny_leg_akshare_none_falls_back(self, monkeypatch):
        """No usable yield -> static CNY fallback (2%)."""
        self._enable_akshare(monkeypatch, None)

        rate, source = fetch_risk_free_rate_detailed(currency="CNY")

        assert rate == 0.02
        assert source == "static_fallback"

    def test_cny_leg_akshare_error_falls_back(self, monkeypatch):
        """Provider exception degrades silently to the static CNY fallback."""
        monkeypatch.setattr(
            "src.data.market_data.akshare_provider.is_available", lambda: True
        )

        def _boom():
            raise RuntimeError("chinabond unreachable")

        monkeypatch.setattr(
            "src.data.market_data.akshare_provider.fetch_cgb_yield_1y", _boom
        )

        rate = fetch_risk_free_rate(currency="CNY")

        assert rate == 0.02

    def test_cny_leg_akshare_unavailable_falls_back(self, monkeypatch):
        """Without the optional akshare package the static fallback applies
        (is_available is already patched off by conftest)."""
        rate = fetch_risk_free_rate(currency="CNY")
        assert rate == 0.02

    def test_cny_leg_custom_default(self, monkeypatch):
        """An explicit default_rate overrides the CNY static fallback."""
        rate = fetch_risk_free_rate(currency="CNY", default_rate=0.03)
        assert rate == 0.03

    @patch("src.data.market_data.requests.get")
    def test_usd_leg_source_label(self, mock_get):
        """USD leg is unchanged: FRED DGS3MO with its source label."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"observations": [{"value": "3.85"}]}
        mock_get.return_value = mock_response

        rate, source = fetch_risk_free_rate_detailed(
            fred_api_key="mock_key", default_rate=0.045, currency="USD"
        )

        assert rate == 0.0385
        assert source == "fred_api"
