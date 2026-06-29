"""
AI WealthPilot - Client Profiler Tests
AI WealthPilot - 客户画像模块测试

Tests for the IPS-based client profiling system, covering:
- Financial situation calculations (净资产, 储蓄率, 资产负债率)
- Risk profile scoring and classification (风险评分与分类)
- Questionnaire scoring logic (问卷评分逻辑)
- JSON persistence (JSON 持久化)
"""
import json
import pytest
from pathlib import Path

from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
    compute_ability_score,
    compute_willingness_score,
    assess_risk,
    save_profile,
    load_profile,
    list_profiles,
    RISK_ABILITY_QUESTIONS,
    RISK_WILLINGNESS_QUESTIONS,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_financial():
    """Sample financial situation with positive net worth."""
    return FinancialSituation(
        annual_income=100_000,
        annual_expenses=60_000,
        investable_assets=200_000,
        total_liabilities=50_000,
        emergency_fund_months=6.0,
    )


@pytest.fixture
def sample_profile():
    """A complete sample client profile."""
    return ClientProfile(
        name="Test User",
        age=30,
        marital_status="single",
        dependents=0,
        financial=FinancialSituation(
            annual_income=100_000,
            annual_expenses=60_000,
            investable_assets=200_000,
            total_liabilities=50_000,
            emergency_fund_months=6.0,
        ),
        goals=[
            InvestmentGoal(name="Retirement", target_amount=2_000_000, years=30, priority="high"),
            InvestmentGoal(name="House", target_amount=500_000, years=5, priority="medium"),
        ],
        time_horizon_years=30,
        risk_profile=RiskProfile(
            ability_score=3.6,
            willingness_score=3.0,
            tolerance_level="Moderate / 平衡型",
        ),
    )


@pytest.fixture
def all_ability_answers():
    """All ability questions answered with the highest option."""
    return {q_key: list(q_data["options"].keys())[-1]
            for q_key, q_data in RISK_ABILITY_QUESTIONS.items()}


@pytest.fixture
def all_willingness_answers():
    """All willingness questions answered with the highest option."""
    return {q_key: list(q_data["options"].keys())[-1]
            for q_key, q_data in RISK_WILLINGNESS_QUESTIONS.items()}


# ============================================================
# FinancialSituation Tests
# ============================================================

class TestFinancialSituation:

    def test_net_worth(self, sample_financial):
        """Net worth = investable_assets - total_liabilities."""
        assert sample_financial.net_worth == 150_000

    def test_net_worth_negative_liabilities(self):
        """Net worth can be negative when liabilities exceed assets."""
        fin = FinancialSituation(investable_assets=10_000, total_liabilities=50_000)
        assert fin.net_worth == -40_000

    def test_savings_rate(self, sample_financial):
        """Savings rate = (income - expenses) / income."""
        # (100k - 60k) / 100k = 0.4
        assert abs(sample_financial.savings_rate - 0.4) < 1e-6

    def test_savings_rate_zero_income(self):
        """Savings rate should be 0 when income is 0 (avoid division by zero)."""
        fin = FinancialSituation(annual_income=0, annual_expenses=10_000)
        assert fin.savings_rate == 0.0

    def test_debt_to_asset_ratio(self, sample_financial):
        """Debt-to-asset ratio = liabilities / investable_assets."""
        # 50k / 200k = 0.25
        assert abs(sample_financial.debt_to_asset_ratio - 0.25) < 1e-6

    def test_debt_to_asset_ratio_zero_assets(self):
        """Debt-to-asset ratio: inf when leveraged with no assets, 0.0 otherwise."""
        # Liabilities but no assets → max leverage (inf), triggers leverage-risk flag.
        fin = FinancialSituation(investable_assets=0, total_liabilities=10_000)
        assert fin.debt_to_asset_ratio == float("inf")
        # No liabilities and no assets → healthy (0.0), no false-positive flag.
        fin_zero = FinancialSituation(investable_assets=0, total_liabilities=0)
        assert fin_zero.debt_to_asset_ratio == 0.0

    def test_default_values(self):
        """Default FinancialSituation should have all zeros."""
        fin = FinancialSituation()
        assert fin.annual_income == 0.0
        assert fin.net_worth == 0.0
        assert fin.savings_rate == 0.0


# ============================================================
# RiskProfile Tests
# ============================================================

class TestRiskProfile:

    def test_final_score_uses_minimum(self):
        """Prudential principle: final score = min(ability, willingness)."""
        rp = RiskProfile(ability_score=4.0, willingness_score=2.5)
        assert rp.final_score == 2.5

    def test_final_score_equal(self):
        """When ability and willingness are equal, final score = either."""
        rp = RiskProfile(ability_score=3.0, willingness_score=3.0)
        assert rp.final_score == 3.0

    def test_final_score_zero_returns_zero(self):
        """Final score should be 0 when either score is 0 (unassessed)."""
        rp = RiskProfile(ability_score=0, willingness_score=3.0)
        assert rp.final_score == 0.0

    @pytest.mark.parametrize("score,expected", [
        (1.0, "Conservative / 保守型"),
        (1.5, "Conservative / 保守型"),
        (2.0, "Moderately Conservative / 稳健型"),
        (2.5, "Moderately Conservative / 稳健型"),
        (3.0, "Moderate / 平衡型"),
        (3.5, "Moderate / 平衡型"),
        (4.0, "Moderately Aggressive / 成长型"),
        (4.5, "Moderately Aggressive / 成长型"),
        (5.0, "Aggressive / 进取型"),
    ])
    def test_classify_levels(self, score, expected):
        """Risk classification should map scores to correct levels."""
        rp = RiskProfile(ability_score=score, willingness_score=score)
        assert rp.classify() == expected


# ============================================================
# Risk Scoring Tests
# ============================================================

class TestRiskScoring:

    def test_ability_score_highest_all(self, all_ability_answers):
        """All highest answers should yield score 5.0."""
        score = compute_ability_score(all_ability_answers)
        assert score == 5.0

    def test_ability_score_lowest_all(self):
        """All lowest answers should yield score 1.0."""
        answers = {q_key: list(q_data["options"].keys())[0]
                   for q_key, q_data in RISK_ABILITY_QUESTIONS.items()}
        score = compute_ability_score(answers)
        assert score == 1.0

    def test_ability_score_empty(self):
        """Empty answers should yield score 0.0."""
        assert compute_ability_score({}) == 0.0

    def test_willingness_score_highest_all(self, all_willingness_answers):
        """All highest answers should yield score 5.0."""
        score = compute_willingness_score(all_willingness_answers)
        assert score == 5.0

    def test_willingness_score_lowest_all(self):
        """All lowest answers should yield score 1.0."""
        answers = {q_key: list(q_data["options"].keys())[0]
                   for q_key, q_data in RISK_WILLINGNESS_QUESTIONS.items()}
        score = compute_willingness_score(answers)
        assert score == 1.0

    def test_willingness_score_empty(self):
        """Empty answers should yield score 0.0."""
        assert compute_willingness_score({}) == 0.0

    def test_ability_score_partial_answers(self):
        """Partial answers should still compute average of answered questions."""
        # Answer only the first question with score 3
        first_q_key = list(RISK_ABILITY_QUESTIONS.keys())[0]
        first_q = RISK_ABILITY_QUESTIONS[first_q_key]
        mid_option = list(first_q["options"].keys())[2]  # 3rd option = score 3
        answers = {first_q_key: mid_option}
        score = compute_ability_score(answers)
        assert score == 3.0

    def test_assess_risk_integration(self, all_ability_answers, all_willingness_answers):
        """assess_risk should return a valid RiskProfile."""
        # Set ability to all 5s, willingness to all 3s (mixed)
        mixed_willingness = {}
        for q_key, q_data in RISK_WILLINGNESS_QUESTIONS.items():
            options = list(q_data["options"].keys())
            mixed_willingness[q_key] = options[2]  # middle option

        profile = assess_risk(all_ability_answers, mixed_willingness)
        assert profile.ability_score == 5.0
        assert profile.willingness_score == 3.0
        assert profile.final_score == 3.0  # min(5, 3)
        assert "Moderate" in profile.tolerance_level or "平衡" in profile.tolerance_level


# ============================================================
# ClientProfile Tests
# ============================================================

class TestClientProfile:

    def test_default_profile(self):
        """Default profile should have reasonable defaults."""
        profile = ClientProfile()
        assert profile.age == 30
        assert profile.marital_status == "single"
        assert profile.dependents == 0
        assert profile.created_at != ""

    def test_summary_format(self, sample_profile):
        """Summary should contain key information."""
        summary = sample_profile.summary()
        assert "Test User" in summary
        assert "30" in summary
        assert "Retirement" in summary
        assert "House" in summary

    def test_goals_list(self, sample_profile):
        """Profile should store multiple goals."""
        assert len(sample_profile.goals) == 2
        assert sample_profile.goals[0].name == "Retirement"
        assert sample_profile.goals[1].target_amount == 500_000


# ============================================================
# JSON Persistence Tests
# ============================================================

class TestProfilePersistence:

    def test_save_and_load(self, sample_profile):
        """Saved profile should be loadable and match original."""
        filepath = save_profile(sample_profile)
        assert filepath.exists()

        loaded = load_profile(filepath)
        assert loaded.name == sample_profile.name
        assert loaded.age == sample_profile.age
        assert loaded.financial.annual_income == sample_profile.financial.annual_income
        assert loaded.financial.net_worth == sample_profile.financial.net_worth
        assert len(loaded.goals) == len(sample_profile.goals)
        assert loaded.risk_profile.ability_score == sample_profile.risk_profile.ability_score

    def test_save_and_load_with_answers(self, sample_profile):
        """Should save and load raw questionnaire answers correctly."""
        sample_profile.ability_answers = {"income_stability": "stable"}
        sample_profile.willingness_answers = {"loss_reaction": "do_nothing"}
        filepath = save_profile(sample_profile)
        assert filepath.exists()

        loaded = load_profile(filepath)
        assert loaded.ability_answers == {"income_stability": "stable"}
        assert loaded.willingness_answers == {"loss_reaction": "do_nothing"}

    def test_save_creates_directory(self, monkeypatch, tmp_path):
        """save_profile should create the profiles directory if it doesn't exist."""
        new_dir = tmp_path / "nonexistent" / "profiles"
        monkeypatch.setattr("src.agents.profiler.PROFILES_DIR", new_dir)

        profile = ClientProfile(name="Dir Test")
        filepath = save_profile(profile)
        assert new_dir.exists()
        assert filepath.exists()

    def test_list_profiles(self):
        """list_profiles should return saved profiles sorted by date."""
        # Save two profiles
        p1 = ClientProfile(name="Alice", age=25)
        p2 = ClientProfile(name="Bob", age=40)
        save_profile(p1)
        save_profile(p2)

        profiles = list_profiles()
        assert len(profiles) == 2
        names = [p["name"] for p in profiles]
        assert "Alice" in names
        assert "Bob" in names

    def test_json_is_valid(self, sample_profile):
        """Saved JSON should be valid and contain all expected fields."""
        filepath = save_profile(sample_profile)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "name" in data
        assert "financial" in data
        assert "risk_profile" in data
        assert "goals" in data
        assert isinstance(data["goals"], list)
