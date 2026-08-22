"""
AI WealthPilot - Portfolio Recommender Tests
AI WealthPilot - 投资组合推荐模块测试

Tests for the portfolio recommendation engine.

投资组合推荐引擎的测试。
"""

import copy

import numpy as np
import pandas as pd
import pytest

from src.agents.portfolio_recommender import (
    PortfolioRecommendation,
    _get_target_volatility,
    _solve_required_return,
    get_recommended_allocation_text,
    recommend_portfolio,
)
from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
    classify_risk_score,
)
from src.portfolio.optimizer import PortfolioOptimizer

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

    def test_recommendation_has_all_fields(self, moderate_profile, sample_returns):
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

    def test_rationale_contains_risk_level(self, moderate_profile, sample_returns):
        """Test that rationale mentions the risk level."""
        rec = recommend_portfolio(moderate_profile, sample_returns)
        assert "Moderate" in rec.rationale or "平衡型" in rec.rationale

    def test_recommendation_with_goals(self, profile_with_goals, sample_returns):
        """Test recommendation when profile has investment goals."""
        rec = recommend_portfolio(profile_with_goals, sample_returns)

        assert rec.risk_level == "Moderate"
        assert rec.expected_return > 0
        assert len(rec.suggested_allocation) > 0
        # Goal feasibility is always evaluated and disclosed.
        assert rec.goal_status in {"on_track", "constrained", "infeasible"}
        assert rec.goal_name == "Retirement"
        assert rec.goal_required_return is not None
        assert "Goal Feasibility" in rec.rationale

    def test_goal_beyond_risk_budget_keeps_risk_portfolio(
        self, conservative_profile, sample_returns
    ):
        """A goal requiring more return than the risk budget can fund must
        NOT override the risk-derived portfolio — the volatility budget is a
        hard cap, and the shortfall is reported as 'constrained'."""
        baseline = recommend_portfolio(conservative_profile, sample_returns)
        optimizer = PortfolioOptimizer(sample_returns)
        max_return = float(optimizer.mean_returns.max())
        # Required return above the risk-budget portfolio's return, but still
        # attainable within the asset universe.
        required = (baseline.expected_return + max_return) / 2

        profile = copy.deepcopy(conservative_profile)
        years = 10
        # Build the target amount with the same contribution-aware TVM the
        # engine solves, so the solved required return lands on `required`.
        savings = profile.financial.annual_income - profile.financial.annual_expenses
        growth = (1 + required) ** years
        target_amount = (
            profile.financial.investable_assets * growth
            + savings * (growth - 1) / required
        )
        profile.goals = [
            InvestmentGoal(
                name="Ambitious Goal",
                target_amount=target_amount,
                years=years,
                priority="high",
            )
        ]
        rec = recommend_portfolio(profile, sample_returns)

        assert rec.goal_status == "constrained"
        assert rec.goal_required_return == pytest.approx(required, rel=1e-6)
        # Same portfolio as the no-goal baseline: no extra risk is taken.
        assert rec.expected_volatility <= baseline.expected_volatility + 1e-6
        assert rec.expected_return == pytest.approx(baseline.expected_return, abs=1e-6)

    def test_goal_within_budget_on_track(self, moderate_profile, sample_returns):
        """An easily funded goal is met within the risk budget ('on_track');
        the portfolio may de-risk but must never exceed the baseline risk."""
        baseline = recommend_portfolio(moderate_profile, sample_returns)

        profile = copy.deepcopy(moderate_profile)
        profile.goals = [
            InvestmentGoal(
                name="Rainy Day",
                target_amount=profile.financial.investable_assets * 1.05,
                years=10,
                priority="high",
            )
        ]
        rec = recommend_portfolio(profile, sample_returns)

        assert rec.goal_status == "on_track"
        assert rec.goal_name == "Rainy Day"
        assert rec.expected_volatility <= baseline.expected_volatility + 1e-6

    def test_goal_below_gmv_return_not_dominated(
        self, moderate_profile, sample_returns
    ):
        """A required return below the GMV return must yield the GMV portfolio,
        not the dominated lower frontier branch (higher vol, lower return)."""
        profile = copy.deepcopy(moderate_profile)
        profile.goals = [
            InvestmentGoal(
                name="Tiny Goal",
                target_amount=profile.financial.investable_assets * 1.02,
                years=10,
                priority="high",
            )
        ]
        rec = recommend_portfolio(profile, sample_returns)

        gmv = PortfolioOptimizer(sample_returns).minimize_volatility()
        assert rec.goal_status == "on_track"
        assert rec.expected_volatility <= gmv["volatility"] + 1e-3
        assert rec.expected_return >= gmv["return"] - 1e-3

    def test_goal_beyond_universe_is_infeasible(
        self, conservative_profile, sample_returns
    ):
        """A required return above the best asset in the universe cannot be
        solved — reported as 'infeasible' while the risk portfolio stands."""
        baseline = recommend_portfolio(conservative_profile, sample_returns)

        profile = copy.deepcopy(conservative_profile)
        profile.goals = [
            InvestmentGoal(
                name="Moonshot",
                target_amount=profile.financial.investable_assets * 50,
                years=5,
                priority="high",
            )
        ]
        rec = recommend_portfolio(profile, sample_returns)

        assert rec.goal_status == "infeasible"
        assert rec.expected_volatility <= baseline.expected_volatility + 1e-6
        assert rec.expected_return == pytest.approx(baseline.expected_return, abs=1e-6)

    def test_no_goals_has_no_goal_status(self, moderate_profile, sample_returns):
        """Without goals, no feasibility evaluation is reported."""
        rec = recommend_portfolio(moderate_profile, sample_returns)
        assert rec.goal_status == ""
        assert rec.goal_required_return is None
        assert rec.goal_details == []

    def test_ongoing_savings_lower_required_return(
        self, profile_with_goals, sample_returns
    ):
        """Contribution-aware TVM: the required return sits below the
        lump-sum (FV/PV)^(1/n) − 1 figure whenever the client saves."""
        rec = recommend_portfolio(profile_with_goals, sample_returns)
        lump_sum_required = (2_000_000 / 200_000) ** (1 / 25) - 1
        assert 0 < rec.goal_required_return < lump_sum_required

    def test_multi_goal_capital_allocation(self, moderate_profile, sample_returns):
        """Capital and savings are split across goals proportionally to
        priority rank; every goal gets its own required return and status,
        and the primary (highest-priority) goal drives the recommendation."""
        profile = copy.deepcopy(moderate_profile)
        profile.goals = [
            InvestmentGoal(
                name="Retirement",
                target_amount=2_000_000,
                years=25,
                priority="high",
            ),
            InvestmentGoal(
                name="Education",
                target_amount=300_000,
                years=10,
                priority="low",
            ),
        ]
        rec = recommend_portfolio(profile, sample_returns)

        assert len(rec.goal_details) == 2
        # Ordered by priority: high first.
        retirement, education = rec.goal_details
        assert retirement["name"] == "Retirement"
        assert education["name"] == "Education"
        # Priority weights 3:1 → 75% / 25% of assets and savings.
        assert retirement["allocated_assets"] == pytest.approx(300_000)
        assert education["allocated_assets"] == pytest.approx(100_000)
        savings = 150_000 - 80_000
        assert retirement["annual_contribution"] == pytest.approx(savings * 0.75)
        assert education["annual_contribution"] == pytest.approx(savings * 0.25)
        # Every goal is classified; the primary is reported at top level.
        assert all(
            d["status"] in {"on_track", "constrained", "infeasible"}
            for d in rec.goal_details
        )
        assert rec.goal_name == "Retirement"
        assert rec.goal_status == retirement["status"]
        assert rec.goal_required_return == pytest.approx(retirement["required_return"])
        assert "All goals" in rec.rationale


# ============================================================
# Test Contribution-Aware Required Return (TVM solver)
# ============================================================


class TestSolveRequiredReturn:
    """Tests for the contribution-aware TVM required-return solver."""

    def test_zero_contribution_reduces_to_lump_sum(self):
        """PMT = 0 must recover r = (FV/PV)^(1/n) − 1."""
        r = _solve_required_return(2_000_000, 500_000, 0.0, 10)
        assert r == pytest.approx((2_000_000 / 500_000) ** (1 / 10) - 1, rel=1e-6)

    def test_contributions_lower_required_return(self):
        """Ongoing savings fund part of the goal → less return needed."""
        lump = _solve_required_return(2_000_000, 500_000, 0.0, 10)
        with_savings = _solve_required_return(2_000_000, 500_000, 30_000, 10)
        assert 0 < with_savings < lump

    def test_fundable_without_growth_returns_zero(self):
        """PV + PMT·n already covers FV → no growth required."""
        assert _solve_required_return(500_000, 400_000, 30_000, 10) == 0.0

    def test_unattainable_goal_returns_sentinel(self):
        """A goal beyond any achievable rate hits the sentinel, which the
        goal evaluation maps to 'infeasible'."""
        assert _solve_required_return(1e12, 1_000.0, 0.0, 5) == 10.0

    def test_solution_satisfies_tvm_equation(self):
        """The solved rate actually funds the goal."""
        target, pv, pmt, years = 2_000_000, 500_000, 30_000, 10
        r = _solve_required_return(target, pv, pmt, years)
        growth = (1 + r) ** years
        funded = pv * growth + pmt * (growth - 1) / r
        assert funded == pytest.approx(target, rel=1e-6)

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


# ============================================================
# Test: Rationale locale
# ============================================================


class TestRationaleLocale:
    """locale switches rationale language; zh keeps the bilingual wording."""

    @staticmethod
    def _has_cjk(text: str) -> bool:
        return any("一" <= ch <= "鿿" for ch in text)

    @staticmethod
    def _with_goal(profile) -> "ClientProfile":
        p = copy.deepcopy(profile)
        p.goals = [
            InvestmentGoal(
                name="Rainy Day",
                target_amount=p.financial.investable_assets * 1.05,
                years=10,
                priority="high",
            )
        ]
        return p

    def test_zh_default_stays_bilingual(self, moderate_profile, sample_returns):
        rec = recommend_portfolio(self._with_goal(moderate_profile), sample_returns)
        assert "Goal Feasibility / 目标可行性" in rec.rationale

    def test_en_rationale_english_only(self, moderate_profile, sample_returns):
        rec = recommend_portfolio(
            self._with_goal(moderate_profile), sample_returns, locale="en"
        )
        assert "**Goal Feasibility**:" in rec.rationale
        assert not self._has_cjk(rec.rationale)

    def test_en_multi_goal_lines_english_only(self, moderate_profile, sample_returns):
        p = copy.deepcopy(moderate_profile)
        p.goals = [
            InvestmentGoal(
                name="Rainy Day",
                target_amount=p.financial.investable_assets * 1.05,
                years=10,
                priority="high",
            ),
            InvestmentGoal(
                name="Education",
                target_amount=p.financial.investable_assets * 0.8,
                years=8,
                priority="medium",
            ),
        ]
        rec = recommend_portfolio(p, sample_returns, locale="en")
        assert len(rec.goal_details) == 2
        assert "All goals, by priority:" in rec.rationale
        assert not self._has_cjk(rec.rationale)

    def test_allocation_text_en(self, moderate_profile, sample_returns):
        rec = recommend_portfolio(moderate_profile, sample_returns)
        text = get_recommended_allocation_text(rec, locale="en")
        assert "## Recommended Portfolio" in text
        assert not self._has_cjk(text)
        zh_text = get_recommended_allocation_text(rec)
        assert "## Recommended Portfolio / 推荐投资组合" in zh_text
