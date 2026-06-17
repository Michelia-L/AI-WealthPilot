"""
AI WealthPilot - Implied Volatility Module Unit Tests

Tests for the implied volatility data fetching module, including:
    - IV proxy mapping completeness and correctness
    - fetch_implied_volatility() with mocked yfinance data
    - Graceful degradation when IV data is unavailable
    - VIX/MOVE data parsing and scale conversion
    - Deduplication logic (same IV index used by multiple assets)
    - Error handling for network failures

Usage:
    python -m pytest tests/test_implied_volatility.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.implied_volatility import (
    IVProxyConfig,
    ImpliedVolData,
    IV_PROXY_MAP,
    IV_INDEX_NAMES,
    fetch_implied_volatility,
    _fetch_single_iv_index,
)


# ============================================================
# Test IVProxyConfig and ImpliedVolData Dataclasses
# ============================================================

class TestDataStructures:
    """Test data structure creation and defaults."""

    def test_iv_proxy_config_defaults(self):
        """IVProxyConfig should have sensible defaults."""
        cfg = IVProxyConfig(iv_ticker="^VIX")
        assert cfg.iv_ticker == "^VIX"
        assert cfg.scale == 0.01
        assert cfg.description == ""

    def test_iv_proxy_config_custom_scale(self):
        """IVProxyConfig should accept custom scale."""
        cfg = IVProxyConfig(iv_ticker="^CUSTOM", scale=0.001, description="Custom IV")
        assert cfg.scale == 0.001
        assert cfg.description == "Custom IV"

    def test_implied_vol_data_creation(self):
        """ImpliedVolData should hold all fields correctly."""
        iv = ImpliedVolData(
            ticker="SPY",
            iv_index_ticker="^VIX",
            iv_index_name="CBOE VIX",
            implied_volatility=0.20,
            fetch_date="2026-06-11",
        )
        assert iv.ticker == "SPY"
        assert iv.implied_volatility == 0.20
        assert iv.fetch_date == "2026-06-11"


# ============================================================
# Test IV Proxy Mapping
# ============================================================

class TestIVProxyMap:
    """Test the IV_PROXY_MAP completeness and consistency."""

    def test_vix_proxy_assets(self):
        """Equity-correlated assets should use VIX."""
        vix_assets = ["SPY", "EFA", "EEM", "EWH"]
        for asset in vix_assets:
            cfg = IV_PROXY_MAP.get(asset)
            assert cfg is not None, f"{asset} should have VIX proxy"
            assert cfg.iv_ticker == "^VIX"
            assert cfg.scale == 0.01

    def test_move_proxy_assets(self):
        """Fixed income assets should use MOVE."""
        move_assets = ["AGG", "TLT", "HYG", "EMB", "TIP"]
        for asset in move_assets:
            cfg = IV_PROXY_MAP.get(asset)
            assert cfg is not None, f"{asset} should have MOVE proxy"
            assert cfg.iv_ticker == "^MOVE"
            assert cfg.scale == 0.01

    def test_no_proxy_default(self):
        """Assets not in the map should return None by default."""
        # Assets like "GLD", "BIL", "VNQ" may or may not be in the map.
        # If they are not in IV_PROXY_MAP, dict.get() returns None.
        result = IV_PROXY_MAP.get("UNKNOWN_TICKER")
        assert result is None

    def test_iv_index_names_map(self):
        """IV_INDEX_NAMES should have entries for known indices."""
        assert IV_INDEX_NAMES["^VIX"] == "CBOE VIX"
        assert IV_INDEX_NAMES["^MOVE"] == "ICE BofAML MOVE"


# ============================================================
# Test Single IV Index Fetching
# ============================================================

class TestFetchSingleIVIndex:
    """Test _fetch_single_iv_index with mocked yfinance."""

    @patch("yfinance.Ticker")
    def test_fetch_vix_success(self, mock_ticker_cls):
        """Should return VIX close price when fetch succeeds."""
        mock_ticker = MagicMock()
        mock_ticker.fast_info.get.return_value = 22.50
        mock_ticker_cls.return_value = mock_ticker

        result = _fetch_single_iv_index("^VIX")
        assert result == 22.50

    @patch("yfinance.Ticker")
    def test_fetch_move_success(self, mock_ticker_cls):
        """Should return MOVE close price when fetch succeeds."""
        mock_ticker = MagicMock()
        mock_ticker.fast_info.get.return_value = 85.0
        mock_ticker_cls.return_value = mock_ticker

        result = _fetch_single_iv_index("^MOVE")
        assert result == 85.0

    @patch("yfinance.Ticker")
    def test_fetch_fast_info_none_fallback_to_history(self, mock_ticker_cls):
        """Should fall back to history when fast_info returns None."""
        mock_ticker = MagicMock()
        mock_ticker.fast_info.get.return_value = None

        # Setup history fallback
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist["Close"].iloc.__getitem__.return_value = 20.0
        mock_ticker.history.return_value = mock_hist

        mock_ticker_cls.return_value = mock_ticker

        result = _fetch_single_iv_index("^VIX")
        assert result == 20.0

    @patch("yfinance.Ticker")
    def test_fetch_returns_none_on_exception(self, mock_ticker_cls):
        """Should return None when yfinance raises an exception."""
        mock_ticker_cls.side_effect = Exception("Network error")

        result = _fetch_single_iv_index("^VIX")
        assert result is None

    @patch("yfinance.Ticker")
    def test_fetch_returns_none_on_zero_price(self, mock_ticker_cls):
        """Should return None when price is zero or negative."""
        mock_ticker = MagicMock()
        mock_ticker.fast_info.get.return_value = 0.0
        mock_ticker_cls.return_value = mock_ticker

        result = _fetch_single_iv_index("^VIX")
        assert result is None


# ============================================================
# Test fetch_implied_volatility — Main Function
# ============================================================

class TestFetchImpliedVolatility:
    """Test fetch_implied_volatility with mocked _fetch_single_iv_index."""

    @patch("src.data.implied_volatility._fetch_single_iv_index")
    def test_fetch_multiple_assets(self, mock_fetch):
        """Should return IV data for assets with configured proxies."""
        mock_fetch.return_value = 20.0  # VIX at 20

        tickers = ["SPY", "EFA", "AGG"]
        results = fetch_implied_volatility(tickers)

        # SPY and EFA should have VIX data
        assert results["SPY"] is not None
        assert results["SPY"].implied_volatility == pytest.approx(0.20)  # scale 0.01
        assert results["SPY"].iv_index_ticker == "^VIX"

        assert results["EFA"] is not None
        assert results["EFA"].implied_volatility == pytest.approx(0.20)

        # AGG should have MOVE data (but mock returns same value)
        # Actually, since mock_fetch returns 20.0 for any ticker,
        # AGG would also get 20.0 * 0.01 = 0.20 as its IV
        # This tests that the proxy mapping is correctly followed
        assert results["AGG"] is not None

    @patch("src.data.implied_volatility._fetch_single_iv_index")
    def test_assets_without_proxy_return_none(self, mock_fetch):
        """Assets not in IV_PROXY_MAP should return None."""
        mock_fetch.return_value = 20.0

        tickers = ["000300.SS", "GLD", "VNQ"]
        results = fetch_implied_volatility(tickers)

        for ticker in tickers:
            assert results[ticker] is None, (
                f"{ticker} should have no IV proxy"
            )

    @patch("src.data.implied_volatility._fetch_single_iv_index")
    def test_deduplication_same_iv_index(self, mock_fetch):
        """Same IV index should be fetched only once, even for multiple assets."""
        mock_fetch.return_value = 22.0

        # SPY, EFA, EEM all use ^VIX
        tickers = ["SPY", "EFA", "EEM"]
        results = fetch_implied_volatility(tickers)

        # ^VIX should have been fetched only once (deduplication)
        vix_fetch_count = sum(
            1 for call in mock_fetch.call_args_list
            if call[0][0] == "^VIX"
        )
        assert vix_fetch_count == 1, (
            f"^VIX should be fetched once, got {vix_fetch_count}"
        )

        # All three should get the same IV value
        for ticker in tickers:
            assert results[ticker] is not None
            assert results[ticker].implied_volatility == pytest.approx(0.22)

    @patch("src.data.implied_volatility._fetch_single_iv_index")
    def test_graceful_degradation_on_fetch_failure(self, mock_fetch):
        """Should return None for assets when IV index fetch fails."""
        mock_fetch.return_value = None  # Simulate fetch failure

        tickers = ["SPY", "AGG"]
        results = fetch_implied_volatility(tickers)

        assert results["SPY"] is None
        assert results["AGG"] is None

    @patch("src.data.implied_volatility._fetch_single_iv_index")
    def test_mixed_available_and_unavailable(self, mock_fetch):
        """Should handle mix of assets with and without IV proxies."""
        # Only ^VIX succeeds, ^MOVE fails
        def mock_fetch_side_effect(ticker):
            if ticker == "^VIX":
                return 18.0
            elif ticker == "^MOVE":
                return None
            return None

        mock_fetch.side_effect = mock_fetch_side_effect

        tickers = ["SPY", "AGG", "000300.SS"]
        results = fetch_implied_volatility(tickers)

        # SPY gets VIX data
        assert results["SPY"] is not None
        assert results["SPY"].implied_volatility == pytest.approx(0.18)

        # AGG's MOVE fetch failed
        assert results["AGG"] is None

        # CSI 300 has no proxy
        assert results["000300.SS"] is None

    @patch("src.data.implied_volatility._fetch_single_iv_index")
    def test_fetch_date_is_set(self, mock_fetch):
        """ImpliedVolData should include the fetch date."""
        mock_fetch.return_value = 20.0

        results = fetch_implied_volatility(["SPY"])
        assert results["SPY"] is not None
        assert results["SPY"].fetch_date is not None
        assert len(results["SPY"].fetch_date) == 10  # ISO format YYYY-MM-DD

    @patch("src.data.implied_volatility._fetch_single_iv_index")
    def test_scale_conversion(self, mock_fetch):
        """Raw VIX quote should be scaled by 0.01 to get decimal IV."""
        mock_fetch.return_value = 25.0  # VIX at 25

        results = fetch_implied_volatility(["SPY"])
        assert results["SPY"].implied_volatility == 0.25
        # Raw value 25.0 × scale 0.01 = 0.25 (25% annualized)

    @patch("src.data.implied_volatility._fetch_single_iv_index")
    def test_iv_index_name_populated(self, mock_fetch):
        """ImpliedVolData should have the correct human-readable IV index name."""
        mock_fetch.return_value = 15.0

        results = fetch_implied_volatility(["SPY", "AGG"])

        assert results["SPY"].iv_index_name == "CBOE VIX"  # type: ignore[union-attr]
        # AGG uses MOVE, but the mock returns 15.0 for everything
        # MOVE at 15 → IV = 0.15, index name should be "ICE BofAML MOVE"
        assert results["AGG"].iv_index_name == "ICE BofAML MOVE"  # type: ignore[union-attr]
