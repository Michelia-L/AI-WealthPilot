"""
AI WealthPilot - UI View Tests
AI WealthPilot - UI 视图模块测试

This module contains integration/smoke tests for the Streamlit view modules
using Streamlit's AppTest framework (introduced in Streamlit 1.28.0).
It tests each view rendering and basic state setup in isolation by dynamically
generating minimalist execution runners, thus avoiding cross-page state conflicts.
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from streamlit.testing.v1 import AppTest
from src.agents.profiler import ClientProfile, FinancialSituation, RiskProfile


@pytest.fixture
def mock_market_data():
    """Mock external market data fetches, API calls, and local storage to prevent network reliance."""
    mock_prices = pd.DataFrame(
        {
            "US Equity": [100.0, 101.0, 102.0],
            "Intl Equity": [100.0, 99.0, 101.0],
            "US Bond": [100.0, 100.2, 100.5],
            "Gold": [100.0, 102.0, 101.5],
        },
        index=pd.date_range(start="2025-01-01", periods=3)
    )
    
    mock_quotes = pd.DataFrame([
        {"ticker": "SPY", "name": "US Equity", "category": "Equities", "price": 102.0, "change": 1.0, "change_pct": 0.01},
        {"ticker": "VEU", "name": "Intl Equity", "category": "Equities", "price": 101.0, "change": 2.0, "change_pct": 0.01},
        {"ticker": "AGG", "name": "US Bond", "category": "Fixed Income", "price": 100.5, "change": 0.3, "change_pct": 0.003},
        {"ticker": "GLD", "name": "Gold", "category": "Commodities", "price": 101.5, "change": -0.5, "change_pct": -0.005},
    ])
    
    mock_report = MagicMock()
    mock_report.success = True
    mock_report.content = "Mocked advice for the client."
    mock_report.client_name = "Test Client"
    mock_report.model = "deepseek-v4-pro"
    mock_report.generated_at = "2025-01-01T00:00:00"
    mock_report.prompt_tokens = 100
    mock_report.completion_tokens = 200
    mock_report.total_tokens = 300

    mock_profile = ClientProfile(
        name="Test Client",
        age=30,
        financial=FinancialSituation(
            annual_income=100000,
            annual_expenses=60000,
            investable_assets=200000,
            total_liabilities=50000,
            emergency_fund_months=6.0
        ),
        goals=[],
        time_horizon_years=10,
        risk_profile=RiskProfile(
            ability_score=3.0,
            willingness_score=3.0,
            tolerance_level="Moderate / 平衡型"
        )
    )
    
    # Patch yfinance fetching and other external logic
    with patch("src.views.market_dashboard.fetch_price_history", return_value=mock_prices), \
         patch("src.views.market_dashboard.get_latest_quotes", return_value=mock_quotes), \
         patch("src.views.portfolio_optimizer.fetch_price_history", return_value=mock_prices), \
         patch("src.views.portfolio_optimizer.compute_returns", side_effect=lambda df, **kwargs: df.pct_change().dropna()), \
         patch("src.views.ai_advisor.is_api_configured", return_value=True), \
         patch("src.views.ai_advisor.stream_advice", return_value=(iter(["Advice"]), [mock_report])), \
         patch("src.views.ai_advisor.list_profiles", return_value=[{"name": "Test Client", "age": 30, "risk_level": "Moderate", "updated_at": "2025-01-01T00:00:00", "filepath": "dummy.json"}]), \
         patch("src.views.ai_advisor.load_profile", return_value=mock_profile), \
         patch("src.views.client_profiling.list_profiles", return_value=[]):
         
        yield


def test_market_dashboard_render(tmp_path, mock_market_data):
    """Test Market Dashboard view rendering."""
    runner = tmp_path / "run_market_dashboard.py"
    runner.write_text("import streamlit as st\nfrom src.views.market_dashboard import render\nrender()", encoding="utf-8")
    at = AppTest.from_file(str(runner))
    at.run()
    assert not at.exception, f"Market Dashboard rendering failed: {at.exception}"


def test_portfolio_optimizer_render(tmp_path, mock_market_data):
    """Test Portfolio Optimizer view rendering."""
    runner = tmp_path / "run_portfolio_optimizer.py"
    runner.write_text("import streamlit as st\nfrom src.views.portfolio_optimizer import render\nrender()", encoding="utf-8")
    at = AppTest.from_file(str(runner))
    at.run()
    assert not at.exception, f"Portfolio Optimizer rendering failed: {at.exception}"


def test_retirement_planner_render(tmp_path, mock_market_data):
    """Test Retirement Planner view rendering."""
    runner = tmp_path / "run_retirement_planner.py"
    runner.write_text("import streamlit as st\nfrom src.views.retirement_planner import render\nrender()", encoding="utf-8")
    at = AppTest.from_file(str(runner))
    at.run()
    assert not at.exception, f"Retirement Planner rendering failed: {at.exception}"


def test_client_profiling_render(tmp_path, mock_market_data):
    """Test Client Profiling view rendering."""
    runner = tmp_path / "run_client_profiling.py"
    runner.write_text("import streamlit as st\nfrom src.views.client_profiling import render\nrender()", encoding="utf-8")
    at = AppTest.from_file(str(runner))
    at.run()
    assert not at.exception, f"Client Profiling rendering failed: {at.exception}"


def test_ai_advisor_render(tmp_path, mock_market_data):
    """Test AI Advisor view rendering."""
    runner = tmp_path / "run_ai_advisor.py"
    runner.write_text("import streamlit as st\nfrom src.views.ai_advisor import render\nrender()", encoding="utf-8")
    at = AppTest.from_file(str(runner))
    at.run()
    assert not at.exception, f"AI Advisor rendering failed: {at.exception}"

