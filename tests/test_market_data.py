"""
AI WealthPilot - Market Data Module Tests
AI WealthPilot - 市场数据模块测试

Unit tests for the market data acquisition, returns, and correlation computation.
市场数据获取、收益率计算及相关性分析的单元测试。
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from src.data.market_data import (
    fetch_price_history,
    compute_returns,
    compute_correlation_matrix,
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

        result = fetch_price_history(tickers=None, period="5y", interval="1d", adjust_currency=False)

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
            [[100.0, 200.0, 99.0, 199.0],
             [110.0, 210.0, 109.0, 209.0],
             [120.0, 220.0, 119.0, 219.0]],
            index=dates,
            columns=columns,
        )
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, period="1y", interval="1d", adjust_currency=False)

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
            {"Close": [100.0, 110.0, 120.0], "Open": [99.0, 109.0, 119.0]},
            index=dates
        )
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, period="2y", interval="1d", adjust_currency=False)

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
            [[100.0, 200.0],
             [np.nan, np.nan],
             [120.0, 220.0]],
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
            ("Close", "CNY=X"): [7.0, 7.1, 7.2]
        }
        mock_df = pd.DataFrame(mock_data, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, base_currency="USD", adjust_currency=True)

        called_args = mock_download.call_args[0][0]
        assert set(called_args) == set(expected_download)
        assert list(result.columns) == tickers
        
        np.testing.assert_array_almost_equal(result["^GSPC"].values, [100.0, 101.0, 102.0])
        np.testing.assert_array_almost_equal(result["000300.SS"].values, [1000.0, 1000.0, 1000.0])

    @patch("src.data.market_data.yf.download")
    def test_fetch_price_history_with_currency_adjustment_cny(self, mock_download):
        """Should convert USD and other prices to CNY correctly using downloaded exchange rates."""
        tickers = ["000300.SS", "^GSPC"]
        expected_download = ["000300.SS", "^GSPC", "CNY=X"]
        
        dates = pd.date_range(start="2026-06-01", periods=3)
        mock_data = {
            ("Close", "^GSPC"): [100.0, 101.0, 102.0],
            ("Close", "000300.SS"): [7000.0, 7100.0, 7200.0],
            ("Close", "CNY=X"): [7.0, 7.1, 7.2]
        }
        mock_df = pd.DataFrame(mock_data, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_download.return_value = mock_df

        result = fetch_price_history(tickers, base_currency="CNY", adjust_currency=True)

        called_args = mock_download.call_args[0][0]
        assert set(called_args) == set(expected_download)
        assert list(result.columns) == tickers
        
        np.testing.assert_array_almost_equal(result["000300.SS"].values, [7000.0, 7100.0, 7200.0])
        np.testing.assert_array_almost_equal(result["^GSPC"].values, [700.0, 717.1, 734.4])


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
        prices = pd.DataFrame({
            "A": [100.0, 101.0, 99.99, 100.9899],
            "B": [100.0, 101.0, 99.99, 100.9899],
            "C": [100.0, 99.0, 99.99, 98.9901]
        })
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
        expected_cols = ["ticker", "name", "category", "price", "previous_close", "change", "change_pct"]
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
        mock_fast_info.get.side_effect = lambda key, default=None: {"lastPrice": 150.0, "previousClose": 150.0}.get(key, default)
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
