"""
AI WealthPilot - CME Engine Unit Tests

Tests for the Capital Market Expectations (CME) module, including:
    - Pydantic model validation (AssetClassCME, CMEReport, SAAValidationResult)
    - CME computation with mocked yfinance data
    - LLM prompt formatting
    - Static fallback loading
    - SAA validation logic (fuzzy matching, weight/return checks)

Usage:
    python -m pytest tests/test_cme_engine.py -v
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.portfolio.cme_models import AssetClassCME, CMEReport, SAAValidationResult
from src.portfolio.cme_engine import (
    compute_cme,
    format_cme_for_prompt,
    _load_fallback_cme,
    _fetch_risk_free_rate_with_source,
    _classify_vol_regime,
)
from src.data.implied_volatility import ImpliedVolData


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_asset_cme() -> AssetClassCME:
    """Create a sample AssetClassCME for testing."""
    return AssetClassCME(
        name="国内权益（A股/沪深300）",
        ticker="000300.SS",
        expected_return=0.065,
        volatility=0.22,
        sharpe_ratio=0.10,
        max_drawdown=-0.35,
        var_95=0.022,
        cvar_95=0.032,
        data_points=1200,
    )


@pytest.fixture
def sample_cme_report(sample_asset_cme) -> CMEReport:
    """Create a sample CMEReport for testing."""
    return CMEReport(
        as_of_date="2026-06-05",
        data_lookback_years=5,
        risk_free_rate=0.043,
        risk_free_rate_source="static_fallback",
        inflation_assumption=0.025,
        asset_classes=[
            sample_asset_cme,
            AssetClassCME(
                name="固定收益",
                ticker="AGG",
                expected_return=0.025,
                volatility=0.07,
                sharpe_ratio=-0.26,
                max_drawdown=-0.18,
                var_95=0.007,
                cvar_95=0.010,
                data_points=1250,
            ),
        ],
        correlation_matrix={
            "国内权益（A股/沪深300）": {
                "国内权益（A股/沪深300）": 1.0,
                "固定收益": -0.10,
            },
            "固定收益": {
                "国内权益（A股/沪深300）": -0.10,
                "固定收益": 1.0,
            },
        },
        methodology_notes="Test methodology notes",
    )


@pytest.fixture
def mock_price_data() -> pd.DataFrame:
    """Create mock price history data for testing."""
    dates = pd.date_range("2021-01-01", periods=1260, freq="B")  # ~5 years
    np.random.seed(42)

    # Simulate prices for multiple tickers
    tickers = ["000300.SS", "EFA", "EWH", "AGG", "GLD", "VNQ", "BIL"]
    data = {}
    for ticker in tickers:
        base_return = np.random.normal(0.0003, 0.015, len(dates))
        prices = 100 * np.cumprod(1 + base_return)
        data[ticker] = prices

    return pd.DataFrame(data, index=dates)


# ============================================================
# Test CME Models
# ============================================================

class TestCMEModels:
    """Test Pydantic model creation and validation."""

    def test_asset_class_cme_creation(self, sample_asset_cme: AssetClassCME):
        """AssetClassCME should create with valid data."""
        assert sample_asset_cme.name == "国内权益（A股/沪深300）"
        assert sample_asset_cme.ticker == "000300.SS"
        assert sample_asset_cme.expected_return == 0.065
        assert sample_asset_cme.volatility == 0.22

    def test_asset_class_cme_serialization(self, sample_asset_cme: AssetClassCME):
        """AssetClassCME should serialize to/from dict."""
        d = sample_asset_cme.model_dump()
        assert isinstance(d, dict)
        assert d["name"] == "国内权益（A股/沪深300）"

        # Round-trip
        restored = AssetClassCME(**d)
        assert restored.expected_return == sample_asset_cme.expected_return

    def test_cme_report_creation(self, sample_cme_report: CMEReport):
        """CMEReport should create with valid data."""
        assert sample_cme_report.as_of_date == "2026-06-05"
        assert sample_cme_report.data_lookback_years == 5
        assert len(sample_cme_report.asset_classes) == 2
        assert "国内权益（A股/沪深300）" in sample_cme_report.correlation_matrix

    def test_cme_report_serialization(self, sample_cme_report: CMEReport):
        """CMEReport should serialize to JSON and back."""
        json_str = sample_cme_report.model_dump_json()
        restored = CMEReport.model_validate_json(json_str)
        assert restored.risk_free_rate == sample_cme_report.risk_free_rate
        assert len(restored.asset_classes) == 2

    def test_saa_validation_result(self):
        """SAAValidationResult should create with valid data."""
        result = SAAValidationResult(
            portfolio_expected_return=0.065,
            portfolio_volatility=0.15,
            portfolio_sharpe=0.15,
            max_sharpe_return=0.10,
            max_sharpe_volatility=0.12,
            gmv_return=0.03,
            gmv_volatility=0.06,
            is_return_feasible=True,
            is_volatility_acceptable=True,
            issues=[],
        )
        assert result.is_return_feasible is True
        assert result.portfolio_expected_return == 0.065


# ============================================================
# Test CME Formatting
# ============================================================

class TestCMEFormatting:
    """Test format_cme_for_prompt output."""

    def test_format_contains_key_fields(self, sample_cme_report: CMEReport):
        """Formatted CME should contain essential fields."""
        text = format_cme_for_prompt(sample_cme_report)

        assert "2026-06-05" in text
        assert "5 年" in text
        assert "国内权益" in text
        assert "固定收益" in text
        assert "相关性矩阵" in text
        assert "使用说明" in text

    def test_format_contains_risk_free_rate(self, sample_cme_report: CMEReport):
        """Formatted CME should display risk-free rate."""
        text = format_cme_for_prompt(sample_cme_report)
        assert "4.30%" in text

    def test_format_not_empty(self, sample_cme_report: CMEReport):
        """Formatted CME should not be empty."""
        text = format_cme_for_prompt(sample_cme_report)
        assert len(text) > 200


# ============================================================
# Test Fallback CME
# ============================================================

class TestFallbackCME:
    """Test static fallback CME loading."""

    def test_fallback_file_exists(self):
        """The fallback CME JSON file should exist."""
        fallback_path = (
            Path(__file__).parent.parent
            / "docs" / "ips_reference" / "cme_fallback.json"
        )
        assert fallback_path.exists(), f"Fallback CME file not found: {fallback_path}"

    def test_fallback_loads_valid_cme(self):
        """Fallback should load into a valid CMEReport."""
        report = _load_fallback_cme()
        assert isinstance(report, CMEReport)
        assert len(report.asset_classes) >= 5
        assert report.risk_free_rate > 0
        assert report.risk_free_rate_source == "static_fallback"

    def test_fallback_has_correlation_matrix(self):
        """Fallback CME should have a complete correlation matrix."""
        report = _load_fallback_cme()
        n = len(report.asset_classes)
        assert len(report.correlation_matrix) == n
        for name, row in report.correlation_matrix.items():
            assert len(row) == n
            # Diagonal should be 1.0
            assert row[name] == 1.0


# ============================================================
# Test CME Computation
# ============================================================

class TestCMEComputation:
    """Test compute_cme with mocked market data."""

    @patch("src.portfolio.cme_engine.fetch_implied_volatility")
    @patch("src.portfolio.cme_engine.fetch_price_history")
    @patch("src.portfolio.cme_engine._fetch_risk_free_rate_with_source")
    @patch("src.portfolio.cme_engine.compute_correlation_matrix")
    def test_compute_cme_basic(
        self,
        mock_corr,
        mock_rf,
        mock_prices,
        mock_iv,
        mock_price_data,
    ):
        """compute_cme should return a valid CMEReport with mock data."""
        mock_prices.return_value = mock_price_data
        mock_rf.return_value = (0.043, "mock")
        # Return empty IV data (no IV available for test tickers)
        mock_iv.return_value = {
            "000300.SS": None,
            "AGG": None,
        }

        # Create a correlation matrix from the mock data
        returns = mock_price_data.pct_change().dropna()
        real_corr = returns.corr()
        mock_corr.return_value = real_corr

        # Use a small subset for speed
        test_tickers = {
            "domestic_equity": {"ticker": "000300.SS", "name": "国内权益"},
            "fixed_income": {"ticker": "AGG", "name": "固定收益"},
        }

        report, cache_status = compute_cme(
            asset_tickers=test_tickers, force_refresh=True,
        )

        assert isinstance(report, CMEReport)
        assert cache_status == "fresh"
        assert len(report.asset_classes) == 2
        assert report.risk_free_rate == 0.043
        assert report.risk_free_rate_source == "mock"
        # IV should not be available for these tickers
        assert report.iv_data_available is False
        for ac in report.asset_classes:
            assert ac.implied_volatility is None
            assert ac.blended_volatility == ac.volatility  # fallback to historical

    @patch("src.portfolio.cme_engine.fetch_price_history")
    def test_compute_cme_fallback_on_empty_data(self, mock_prices):
        """compute_cme should fall back to static when data is empty."""
        mock_prices.return_value = pd.DataFrame()

        report, cache_status = compute_cme(force_refresh=True)

        assert isinstance(report, CMEReport)
        assert cache_status in ("stale", "fallback")
        # When no data is available and no stale cache, falls back to static
        assert report.risk_free_rate > 0

    @patch("src.portfolio.cme_engine.fetch_price_history")
    def test_compute_cme_fallback_on_exception(self, mock_prices):
        """compute_cme should fall back to static on exception."""
        mock_prices.side_effect = Exception("Network error")

        report, cache_status = compute_cme(force_refresh=True)

        assert isinstance(report, CMEReport)
        assert cache_status in ("stale", "fallback")
        assert report.risk_free_rate > 0


# ============================================================
# Test Risk-Free Rate Fetching
# ============================================================

class TestRiskFreeRate:
    """Test risk-free rate fetching with source tracking."""

    @patch.dict("os.environ", {"FRED_API_KEY": ""}, clear=False)
    def test_fallback_returns_default(self):
        """Without API keys, should return static fallback."""
        # This will try FRED (no key), yfinance (may fail), then fallback
        rate, source = _fetch_risk_free_rate_with_source()
        assert rate > 0
        assert isinstance(source, str)
        assert source in ("fred_api", "yfinance_irx", "static_fallback")


# ============================================================
# Test Volatility Regime Classification
# ============================================================

class TestVolRegimeClassification:
    """Test _classify_vol_regime threshold logic."""

    def test_regime_low(self):
        """IV/HV < 0.8 should return 'low'."""
        assert _classify_vol_regime(0.10, 0.20) == "low"   # ratio = 0.5
        assert _classify_vol_regime(0.15, 0.20) == "low"   # ratio = 0.75

    def test_regime_normal(self):
        """0.8 ≤ IV/HV < 1.2 should return 'normal'."""
        # Use values clearly inside the range to avoid floating-point boundary issues
        assert _classify_vol_regime(0.18, 0.20) == "normal"  # ratio = 0.9
        assert _classify_vol_regime(0.20, 0.20) == "normal"  # ratio = 1.0
        assert _classify_vol_regime(0.22, 0.20) == "normal"  # ratio = 1.1

    def test_regime_elevated(self):
        """1.2 ≤ IV/HV < 1.6 should return 'elevated'."""
        assert _classify_vol_regime(0.24, 0.20) == "elevated"  # ratio = 1.2
        assert _classify_vol_regime(0.30, 0.20) == "elevated"  # ratio = 1.5

    def test_regime_high(self):
        """IV/HV ≥ 1.6 should return 'high'."""
        assert _classify_vol_regime(0.34, 0.20) == "high"    # ratio = 1.7
        assert _classify_vol_regime(0.50, 0.20) == "high"    # ratio = 2.5

    def test_regime_zero_historical_vol(self):
        """Should return 'normal' when historical vol is zero."""
        assert _classify_vol_regime(0.20, 0.0) == "normal"

    def test_regime_negative_historical_vol(self):
        """Should return 'normal' when historical vol is negative."""
        assert _classify_vol_regime(0.20, -0.05) == "normal"


# ============================================================
# Test CME Computation with IV Blending
# ============================================================

class TestCMEWithIVBlending:
    """Test compute_cme with implied volatility data available."""

    @patch("src.portfolio.cme_engine.fetch_implied_volatility")
    @patch("src.portfolio.cme_engine.fetch_price_history")
    @patch("src.portfolio.cme_engine._fetch_risk_free_rate_with_source")
    @patch("src.portfolio.cme_engine.compute_correlation_matrix")
    def test_iv_blending_applied_when_available(
        self, mock_corr, mock_rf, mock_prices, mock_iv, mock_price_data,
    ):
        """When IV data is available, blended_vol should differ from historical vol."""
        mock_prices.return_value = mock_price_data
        mock_rf.return_value = (0.043, "mock")

        returns = mock_price_data.pct_change().dropna()
        mock_corr.return_value = returns.corr()

        # Provide IV data for AGG (but not 000300.SS)
        mock_iv.return_value = {
            "000300.SS": None,
            "AGG": ImpliedVolData(
                ticker="AGG",
                iv_index_ticker="^MOVE",
                iv_index_name="ICE BofAML MOVE",
                implied_volatility=0.12,  # 12% implied vs ~7% historical
                fetch_date="2026-06-11",
            ),
        }

        test_tickers = {
            "domestic_equity": {"ticker": "000300.SS", "name": "国内权益"},
            "fixed_income": {"ticker": "AGG", "name": "固定收益"},
        }

        report, cache_status = compute_cme(
            asset_tickers=test_tickers, iv_blending_tau=0.5,
            force_refresh=True,
        )

        assert report.iv_data_available is True
        assert report.iv_blending_tau == 0.5

        # Find the AGG entry
        agg_cme = next(ac for ac in report.asset_classes if ac.ticker == "AGG")
        csi_cme = next(ac for ac in report.asset_classes if ac.ticker == "000300.SS")

        # AGG should have IV fields populated
        assert agg_cme.implied_volatility == 0.12
        assert agg_cme.iv_source is not None
        assert "MOVE" in agg_cme.iv_source
        assert agg_cme.volatility_regime is not None
        # blended = 0.5 * 0.12 + 0.5 * hist_vol
        hist_vol = agg_cme.volatility
        expected_blended = 0.5 * 0.12 + 0.5 * hist_vol
        assert agg_cme.blended_volatility == pytest.approx(expected_blended, rel=1e-5)

        # CSI 300 should have no IV data (graceful degradation)
        assert csi_cme.implied_volatility is None
        assert csi_cme.iv_source is None
        assert csi_cme.volatility_regime is None
        assert csi_cme.blended_volatility == csi_cme.volatility

    @patch("src.portfolio.cme_engine.fetch_implied_volatility")
    @patch("src.portfolio.cme_engine.fetch_price_history")
    @patch("src.portfolio.cme_engine._fetch_risk_free_rate_with_source")
    @patch("src.portfolio.cme_engine.compute_correlation_matrix")
    def test_pure_historical_when_tau_zero(
        self, mock_corr, mock_rf, mock_prices, mock_iv, mock_price_data,
    ):
        """τ=0 should give pure historical volatility (blended = hist)."""
        mock_prices.return_value = mock_price_data
        mock_rf.return_value = (0.043, "mock")

        returns = mock_price_data.pct_change().dropna()
        mock_corr.return_value = returns.corr()

        mock_iv.return_value = {
            "000300.SS": None,
            "AGG": ImpliedVolData(
                ticker="AGG",
                iv_index_ticker="^MOVE",
                iv_index_name="ICE BofAML MOVE",
                implied_volatility=0.20,
                fetch_date="2026-06-11",
            ),
        }

        test_tickers = {
            "fixed_income": {"ticker": "AGG", "name": "固定收益"},
        }

        report, cache_status = compute_cme(
            asset_tickers=test_tickers, iv_blending_tau=0.0,
            force_refresh=True,
        )
        agg_cme = report.asset_classes[0]

        # With τ=0, blended = 0*IV + 1*historical = historical
        assert agg_cme.blended_volatility == agg_cme.volatility

    @patch("src.portfolio.cme_engine.fetch_implied_volatility")
    @patch("src.portfolio.cme_engine.fetch_price_history")
    @patch("src.portfolio.cme_engine._fetch_risk_free_rate_with_source")
    @patch("src.portfolio.cme_engine.compute_correlation_matrix")
    def test_pure_implied_when_tau_one(
        self, mock_corr, mock_rf, mock_prices, mock_iv, mock_price_data,
    ):
        """τ=1.0 should give pure implied volatility (blended = IV)."""
        mock_prices.return_value = mock_price_data
        mock_rf.return_value = (0.043, "mock")

        returns = mock_price_data.pct_change().dropna()
        mock_corr.return_value = returns.corr()

        mock_iv.return_value = {
            "AGG": ImpliedVolData(
                ticker="AGG",
                iv_index_ticker="^MOVE",
                iv_index_name="ICE BofAML MOVE",
                implied_volatility=0.20,
                fetch_date="2026-06-11",
            ),
        }

        test_tickers = {
            "fixed_income": {"ticker": "AGG", "name": "固定收益"},
        }

        report, cache_status = compute_cme(
            asset_tickers=test_tickers, iv_blending_tau=1.0,
            force_refresh=True,
        )
        agg_cme = report.asset_classes[0]

        assert agg_cme.blended_volatility == 0.20  # pure IV

    @patch("src.portfolio.cme_engine.fetch_implied_volatility")
    @patch("src.portfolio.cme_engine.fetch_price_history")
    @patch("src.portfolio.cme_engine._fetch_risk_free_rate_with_source")
    @patch("src.portfolio.cme_engine.compute_correlation_matrix")
    def test_format_cme_with_iv_data(
        self, mock_corr, mock_rf, mock_prices, mock_iv, mock_price_data,
    ):
        """format_cme_for_prompt should include IV columns when IV data is available."""
        mock_prices.return_value = mock_price_data
        mock_rf.return_value = (0.043, "mock")

        returns = mock_price_data.pct_change().dropna()
        mock_corr.return_value = returns.corr()

        mock_iv.return_value = {
            "000300.SS": None,
            "AGG": ImpliedVolData(
                ticker="AGG",
                iv_index_ticker="^MOVE",
                iv_index_name="ICE BofAML MOVE",
                implied_volatility=0.10,
                fetch_date="2026-06-11",
            ),
        }

        test_tickers = {
            "domestic_equity": {"ticker": "000300.SS", "name": "国内权益"},
            "fixed_income": {"ticker": "AGG", "name": "固定收益"},
        }

        report, cache_status = compute_cme(
            asset_tickers=test_tickers, force_refresh=True,
        )
        text = format_cme_for_prompt(report)

        # Should include IV-related headers
        assert "隐含σ" in text
        assert "混合σ" in text
        assert "波动率方法论" in text
        assert "贝叶斯" in text
        # Should include regime info
        assert "volatility_regime" in text or "波动率环境" in text

    @patch("src.portfolio.cme_engine.fetch_implied_volatility")
    @patch("src.portfolio.cme_engine.fetch_price_history")
    @patch("src.portfolio.cme_engine._fetch_risk_free_rate_with_source")
    @patch("src.portfolio.cme_engine.compute_correlation_matrix")
    def test_format_cme_without_iv_data(
        self, mock_corr, mock_rf, mock_prices, mock_iv, mock_price_data,
    ):
        """format_cme_for_prompt should not show IV columns when no IV data."""
        mock_prices.return_value = mock_price_data
        mock_rf.return_value = (0.043, "mock")

        returns = mock_price_data.pct_change().dropna()
        mock_corr.return_value = returns.corr()

        # All IV data is None
        mock_iv.return_value = {
            "000300.SS": None,
            "AGG": None,
        }

        test_tickers = {
            "domestic_equity": {"ticker": "000300.SS", "name": "国内权益"},
            "fixed_income": {"ticker": "AGG", "name": "固定收益"},
        }

        report, cache_status = compute_cme(
            asset_tickers=test_tickers, force_refresh=True,
        )
        text = format_cme_for_prompt(report)

        # Should NOT include IV column headers in the asset table.
        # "混合σ" (column header, no brackets) only appears when IV is available.
        # Usage instructions use 「混合波动率」 with brackets — different text.
        assert "未获取到隐含波动率数据" in text
        assert "混合σ" not in text

    @patch("src.portfolio.cme_engine.fetch_implied_volatility")
    @patch("src.portfolio.cme_engine.fetch_price_history")
    @patch("src.portfolio.cme_engine._fetch_risk_free_rate_with_source")
    @patch("src.portfolio.cme_engine.compute_correlation_matrix")
    def test_blended_vol_between_iv_and_hist(
        self, mock_corr, mock_rf, mock_prices, mock_iv, mock_price_data,
    ):
        """Blended vol should be between IV and historical when 0 < τ < 1."""
        mock_prices.return_value = mock_price_data
        mock_rf.return_value = (0.043, "mock")

        returns = mock_price_data.pct_change().dropna()
        mock_corr.return_value = returns.corr()

        mock_iv.return_value = {
            "AGG": ImpliedVolData(
                ticker="AGG",
                iv_index_ticker="^MOVE",
                iv_index_name="ICE BofAML MOVE",
                implied_volatility=0.15,  # IV higher than hist
                fetch_date="2026-06-11",
            ),
        }

        test_tickers = {
            "fixed_income": {"ticker": "AGG", "name": "固定收益"},
        }

        report, cache_status = compute_cme(
            asset_tickers=test_tickers, iv_blending_tau=0.5,
            force_refresh=True,
        )
        agg_cme = report.asset_classes[0]

        hist = agg_cme.volatility
        blended = agg_cme.blended_volatility
        iv = agg_cme.implied_volatility

        # blended should be between hist and IV (or equal to one)
        assert min(hist, iv) <= blended <= max(hist, iv), (
            f"Expected {min(hist, iv):.6f} ≤ {blended:.6f} ≤ {max(hist, iv):.6f}"
        )
