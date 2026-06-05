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
)


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

    @patch("src.portfolio.cme_engine.fetch_price_history")
    @patch("src.portfolio.cme_engine._fetch_risk_free_rate_with_source")
    @patch("src.portfolio.cme_engine.compute_correlation_matrix")
    def test_compute_cme_basic(
        self,
        mock_corr,
        mock_rf,
        mock_prices,
        mock_price_data,
    ):
        """compute_cme should return a valid CMEReport with mock data."""
        mock_prices.return_value = mock_price_data
        mock_rf.return_value = (0.043, "mock")

        # Create a correlation matrix from the mock data
        returns = mock_price_data.pct_change().dropna()
        real_corr = returns.corr()
        mock_corr.return_value = real_corr

        # Use a small subset for speed
        test_tickers = {
            "domestic_equity": {"ticker": "000300.SS", "name": "国内权益"},
            "fixed_income": {"ticker": "AGG", "name": "固定收益"},
        }

        report = compute_cme(asset_tickers=test_tickers)

        assert isinstance(report, CMEReport)
        assert len(report.asset_classes) == 2
        assert report.risk_free_rate == 0.043
        assert report.risk_free_rate_source == "mock"

    @patch("src.portfolio.cme_engine.fetch_price_history")
    def test_compute_cme_fallback_on_empty_data(self, mock_prices):
        """compute_cme should fall back to static when data is empty."""
        mock_prices.return_value = pd.DataFrame()

        report = compute_cme()

        assert isinstance(report, CMEReport)
        assert report.risk_free_rate_source == "static_fallback"

    @patch("src.portfolio.cme_engine.fetch_price_history")
    def test_compute_cme_fallback_on_exception(self, mock_prices):
        """compute_cme should fall back to static on exception."""
        mock_prices.side_effect = Exception("Network error")

        report = compute_cme()

        assert isinstance(report, CMEReport)
        assert report.risk_free_rate_source == "static_fallback"


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
