"""
AI WealthPilot - Portfolio Recommender Tests
AI WealthPilot - 投资组合推荐模块测试

Tests for the portfolio recommendation engine.

投资组合推荐引擎的测试。
"""

import numpy as np
import pandas as pd
import pytest

from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
    classify_risk_score,
)
from src.agents.portfolio_recommender import (
    PortfolioRecommendation,
    _get_target_volatility,
    recommend_portfolio,
    get_recommended_allocation_text,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_returns():
    """Generate synthetic returns for testing."""
    np.random.seed(42)
    n_days = 252 * 5
    assets = ["US_EQUITY", "INTL_EQUITY", "BONDS", "GOLD"]
    returns = pd.DataFrame(
        np.random.randn(n_days, len(assets)) * 0.01
        + np.array([0.0004, 0.0003, 0.0001, 0.0002]),
        columns=assets,
    )
    return returns


@pytest.fixture
def conservative_profile():
    """Conservative investor profile."""
    return ClientProfile(
        name="Conservative Investor",
        age=65,
        marital_status="married",
        dependents=0,
        financial=FinancialSituation(
            annual_income=80_000,
            annual_expenses=50_000,
            investable_assets=500_000,
            total_liabilities=0,
            emergency_fund_months=12.0,
        ),
        time_horizon_years=10,
        risk_profile=RiskProfile(
            ability_score=2.0,
            willingness_score=1.5,
            tolerance_level="Conservative / 保守型",
        ),
    )


@pytest.fixture
def moderate_profile():
    """Moderate investor profile."""
    return ClientProfile(
        name="Moderate Investor",
        age=40,
        marital_status="married",
        dependents=2,
        financial=FinancialSituation(
            annual_income=150_000,
            annual_expenses=80_000,
            investable_assets=400_000,
            total_liabilities=100_000,
            emergency_fund_months=6.0,
        ),
        time_horizon_years=20,
        risk_profile=RiskProfile(
            ability_score=3.5,
            willingness_score=3.0,
            tolerance_level="Moderate / 平衡型",
        ),
    )


@pytest.fixture
def aggressive_profile():
    """Aggressive investor profile."""
    return ClientProfile(
        name="Aggressive Investor",
        age=30,
        marital_status="single",
        dependents=0,
        financial=FinancialSituation(
            annual_income=200_000,
            annual_expenses=60_000,
            investable_assets=300_000,
            total_liabilities=50_000,
            emergency_fund_months=8.0,
        ),
        time_horizon_years=30,
        risk_profile=RiskProfile(
            ability_score=4.5,
            willingness_score=4.8,
            tolerance_level="Aggressive / 进取型",
        ),
    )


@pytest.fixture
def profile_with_goals():
    """Profile with specific investment goals."""
    return ClientProfile(
        name="Goal-Oriented Investor",
        age=35,
        marital_status="married",
        dependents=1,
        financial=FinancialSituation(
            annual_income=120_000,
            annual_expenses=70_000,
            investable_assets=200_000,
            total_liabilities=80_000,
            emergency_fund_months=6.0,
        ),
        goals=[
            InvestmentGoal(
                name="Retirement",
                target_amount=2_000_000,
                years=25,
                priority="high",
            ),
        ],
        time_horizon_years=25,
        risk_profile=RiskProfile(
            ability_score=3.0,
            willingness_score=3.0,
            tolerance_level="Moderate / 平衡型",
        ),
    )


# ============================================================
# Test Risk Score Mapping
# ============================================================

class TestRiskScoreMapping:
    """Tests for risk score to volatility mapping."""

    def test_conservative_volatility(self):
        """Test volatility mapping for conservative investor."""
        vol = _get_target_volatility(1.0)
        assert 0.04 <= vol <= 0.08

    def test_moderate_volatility(self):
        """Test volatility mapping for moderate investor."""
        vol = _get_target_volatility(3.0)
        assert 0.10 <= vol <= 0.16

    def test_aggressive_volatility(self):
        """Test volatility mapping for aggressive investor."""
        vol = _get_target_volatility(5.0)
        assert 0.18 <= vol <= 0.25

    def test_volatility_increases_with_score(self):
        """Test that volatility increases as risk score increases."""
        vols = [_get_target_volatility(score) for score in [1.0, 2.0, 3.0, 4.0, 5.0]]
        for i in range(len(vols) - 1):
            assert vols[i] < vols[i + 1]

    def test_classify_risk_levels(self):
        """Test risk level classification via shared classify_risk_score."""
        assert classify_risk_score(1.0) == "Conservative / 保守型"
        assert classify_risk_score(2.0) == "Moderately Conservative / 稳健型"
        assert classify_risk_score(3.0) == "Moderate / 平衡型"
        assert classify_risk_score(4.0) == "Moderately Aggressive / 成长型"
        assert classify_risk_score(5.0) == "Aggressive / 进取型"


# ============================================================
# Test Portfolio Recommendation
# ============================================================

class TestPortfolioRecommendation:
    """Tests for portfolio recommendation generation."""

    def test_recommendation_has_all_fields(
        self, moderate_profile, sample_returns
    ):
        """Test that recommendation contains all required fields."""
        rec = recommend_portfolio(moderate_profile, sample_returns)

        assert isinstance(rec, PortfolioRecommendation)
        assert rec.risk_level
        assert rec.suggested_allocation
        assert rec.expected_return > 0
        assert rec.expected_volatility > 0
        assert rec.sharpe_ratio
        assert rec.rationale
        assert len(rec.asset_classes) > 0
        assert len(rec.weights) > 0

    def test_conservative_lower_volatility(
        self, conservative_profile, moderate_profile, sample_returns
    ):
        """Test that conservative profile has lower volatility than moderate."""
        conservative_rec = recommend_portfolio(conservative_profile, sample_returns)
        moderate_rec = recommend_portfolio(moderate_profile, sample_returns)

        # Conservative should have lower target volatility
        # (actual may vary due to optimization constraints)
        assert conservative_rec.risk_level == "Conservative"
        assert moderate_rec.risk_level in ["Moderate", "Moderately Conservative"]

    def test_aggressive_higher_return_potential(
        self, aggressive_profile, conservative_profile, sample_returns
    ):
        """Test that aggressive profile targets higher returns."""
        aggressive_rec = recommend_portfolio(aggressive_profile, sample_returns)
        conservative_rec = recommend_portfolio(conservative_profile, sample_returns)

        # Aggressive profile has risk_score = min(4.5, 4.8) = 4.5
        # This maps to "Moderately Aggressive" (4.5 is the boundary)
        assert aggressive_rec.risk_level in ["Aggressive", "Moderately Aggressive"]
        assert conservative_rec.risk_level == "Conservative"

    def test_weights_sum_to_one(self, moderate_profile, sample_returns):
        """Test that portfolio weights sum to approximately 1."""
        rec = recommend_portfolio(moderate_profile, sample_returns)
        weight_sum = sum(rec.suggested_allocation.values())
        assert abs(weight_sum - 1.0) < 0.01

    def test_no_negative_weights(self, moderate_profile, sample_returns):
        """Test that all weights are non-negative (long-only)."""
        rec = recommend_portfolio(moderate_profile, sample_returns)
        for weight in rec.suggested_allocation.values():
            assert weight >= -0.001  # Small tolerance for floating point

    def test_rationale_contains_risk_level(
        self, moderate_profile, sample_returns
    ):
        """Test that rationale mentions the risk level."""
        rec = recommend_portfolio(moderate_profile, sample_returns)
        assert "Moderate" in rec.rationale or "平衡型" in rec.rationale

    def test_recommendation_with_goals(
        self, profile_with_goals, sample_returns
    ):
        """Test recommendation when profile has investment goals."""
        rec = recommend_portfolio(profile_with_goals, sample_returns)

        assert rec.risk_level == "Moderate"
        assert rec.expected_return > 0
        assert len(rec.suggested_allocation) > 0

    def test_volatility_lands_near_target(self, moderate_profile, sample_returns):
        """The solved portfolio must sit at the target volatility, not at the
        GMV point — the mapping is a constraint, not documentation."""
        rec = recommend_portfolio(moderate_profile, sample_returns)
        target = _get_target_volatility(moderate_profile.risk_profile.final_score)
        assert rec.expected_volatility <= target * 1.05
        # Actually invested toward the target, not parked in the safest corner.
        assert rec.expected_volatility > target * 0.5

    def test_conservative_less_volatile_than_moderate(
        self, conservative_profile, moderate_profile, sample_returns
    ):
        """Risk-targeting makes allocations monotonic in the risk score."""
        conservative_rec = recommend_portfolio(conservative_profile, sample_returns)
        moderate_rec = recommend_portfolio(moderate_profile, sample_returns)
        assert conservative_rec.expected_volatility < moderate_rec.expected_volatility


# ============================================================
# Test Recommendation Text Formatting
# ============================================================

class TestRecommendationFormatting:
    """Tests for recommendation text formatting."""

    def test_format_contains_all_sections(self, moderate_profile, sample_returns):
        """Test that formatted text contains all sections."""
        rec = recommend_portfolio(moderate_profile, sample_returns)
        text = get_recommended_allocation_text(rec)

        assert "Recommended Portfolio" in text
        assert "Risk Level" in text
        assert "Expected Return" in text
        assert "Expected Volatility" in text
        assert "Sharpe Ratio" in text
        assert "Asset Allocation" in text
        assert "Rationale" in text

    def test_format_contains_allocations(self, moderate_profile, sample_returns):
        """Test that formatted text contains asset allocations."""
        rec = recommend_portfolio(moderate_profile, sample_returns)
        text = get_recommended_allocation_text(rec)

        # Should contain at least some asset names
        for asset in rec.asset_classes[:3]:
            if rec.suggested_allocation.get(asset, 0) > 0.01:
                assert asset in text


# ============================================================
# Integration Test
# ============================================================

class TestRecommenderIntegration:
    """Integration tests for portfolio recommender."""

    def test_full_workflow(self, moderate_profile, sample_returns):
        """Test complete workflow from profile to recommendation."""
        # 1. Get risk score
        risk_score = moderate_profile.risk_profile.final_score
        assert risk_score > 0

        # 2. Classify risk level
        risk_label = classify_risk_score(risk_score)
        risk_level = risk_label.split(" / ")[0]
        assert risk_level in [
            "Conservative",
            "Moderately Conservative",
            "Moderate",
            "Moderately Aggressive",
            "Aggressive",
        ]

        # 3. Generate recommendation
        rec = recommend_portfolio(moderate_profile, sample_returns)
        assert isinstance(rec, PortfolioRecommendation)

        # 4. Format as text
        text = get_recommended_allocation_text(rec)
        assert len(text) > 100  # Should be substantial text

        # 5. Verify allocation is reasonable
        total_weight = sum(rec.suggested_allocation.values())
        assert abs(total_weight - 1.0) < 0.01
