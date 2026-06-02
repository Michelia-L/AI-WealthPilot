"""
AI WealthPilot - Phase 3 Feature Tests
AI WealthPilot - Phase 3 功能测试

Tests for the new features added in Phase 3:
Phase 3 新增功能的测试：

1. Profile update/delete functionality
   画像更新/删除功能
2. Behavioral bias identification
   行为偏差识别
3. Report storage module
   报告存储模块
"""

import json
import pytest
from pathlib import Path
from datetime import datetime

from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
    BehavioralBias,
    update_profile,
    delete_profile,
    identify_behavioral_biases,
    save_profile,
    load_profile,
)
from src.agents.report_storage import (
    StoredReport,
    save_report,
    load_report,
    list_reports,
    delete_report,
    get_reports_for_profile,
    export_report_markdown,
    update_report_notes,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_profile():
    """Create a sample client profile for testing."""
    return ClientProfile(
        name="Test User",
        age=35,
        marital_status="married",
        dependents=2,
        financial=FinancialSituation(
            annual_income=150_000,
            annual_expenses=80_000,
            investable_assets=500_000,
            total_liabilities=200_000,
            emergency_fund_months=6.0,
        ),
        goals=[
            InvestmentGoal(name="Retirement", target_amount=3_000_000, years=25, priority="high"),
            InvestmentGoal(name="Education", target_amount=300_000, years=10, priority="medium"),
        ],
        time_horizon_years=25,
        risk_profile=RiskProfile(
            ability_score=3.8,
            willingness_score=3.2,
            tolerance_level="Moderate / 平衡型",
        ),
    )


@pytest.fixture
def high_ability_low_willingness_profile():
    """Profile with high ability but low willingness (loss aversion scenario)."""
    return ClientProfile(
        name="Cautious Investor",
        age=45,
        marital_status="single",
        dependents=0,
        financial=FinancialSituation(
            annual_income=200_000,
            annual_expenses=60_000,
            investable_assets=1_000_000,
            total_liabilities=50_000,
            emergency_fund_months=12.0,
        ),
        time_horizon_years=20,
        risk_profile=RiskProfile(
            ability_score=4.5,
            willingness_score=1.8,
            tolerance_level="Moderately Conservative / 稳健型",
        ),
    )


@pytest.fixture
def high_risk_profile():
    """Profile with very high risk tolerance (overconfidence scenario)."""
    return ClientProfile(
        name="Aggressive Trader",
        age=28,
        marital_status="single",
        dependents=0,
        financial=FinancialSituation(
            annual_income=100_000,
            annual_expenses=50_000,
            investable_assets=200_000,
            total_liabilities=180_000,  # High debt ratio
            emergency_fund_months=2.0,  # Low emergency fund
        ),
        time_horizon_years=5,
        risk_profile=RiskProfile(
            ability_score=4.2,
            willingness_score=4.8,
            tolerance_level="Aggressive / 进取型",
        ),
    )


@pytest.fixture
def sample_report_content():
    """Sample advisory report content."""
    return """# Investment Advisory Report

## Client Summary
The client is a 35-year-old married individual with two dependents.

## Risk Assessment
Based on the analysis, the client demonstrates moderate risk tolerance.

## Recommended Allocation
- US Equities: 40%
- International Equities: 20%
- Bonds: 30%
- Alternatives: 10%
"""


# ============================================================
# Test Profile Update/Delete
# ============================================================

class TestProfileUpdateDelete:
    """Tests for profile update and delete functionality."""

    def test_update_profile(self, sample_profile, tmp_path):
        """Test updating an existing profile."""
        # Save initial profile
        profile_path = tmp_path / "test_profile.json"
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump({
                "name": sample_profile.name,
                "age": sample_profile.age,
                "updated_at": datetime.now().isoformat(),
            }, f)

        # Update profile
        sample_profile.age = 36
        result_path = update_profile(profile_path, sample_profile)

        # Verify update
        assert result_path == profile_path
        loaded = load_profile(profile_path)
        assert loaded.age == 36

    def test_update_profile_not_found(self, sample_profile, tmp_path):
        """Test updating a non-existent profile raises error."""
        non_existent = tmp_path / "non_existent.json"
        with pytest.raises(FileNotFoundError):
            update_profile(non_existent, sample_profile)

    def test_delete_profile(self, tmp_path):
        """Test deleting a profile file."""
        # Create a test file
        test_file = tmp_path / "to_delete.json"
        test_file.write_text('{"test": true}')

        # Delete it
        result = delete_profile(test_file)
        assert result is True
        assert not test_file.exists()

    def test_delete_nonexistent_profile(self, tmp_path):
        """Test deleting a non-existent profile returns False."""
        non_existent = tmp_path / "non_existent.json"
        result = delete_profile(non_existent)
        assert result is False


# ============================================================
# Test Behavioral Bias Identification
# ============================================================

class TestBehavioralBiasIdentification:
    """Tests for behavioral bias identification."""

    def test_loss_aversion_detection(self, high_ability_low_willingness_profile):
        """Test detection of loss aversion bias."""
        biases = identify_behavioral_biases(high_ability_low_willingness_profile)

        # Should detect loss aversion
        loss_aversion = [b for b in biases if b.bias_type == "loss_aversion"]
        assert len(loss_aversion) == 1
        assert loss_aversion[0].severity == "high"

    def test_risk_mismatch_detection(self, high_ability_low_willingness_profile):
        """Test detection of risk tolerance mismatch."""
        biases = identify_behavioral_biases(high_ability_low_willingness_profile)

        # Should detect risk mismatch (ability 4.5 vs willingness 1.8 = diff 2.7)
        risk_mismatch = [b for b in biases if b.bias_type == "risk_mismatch"]
        assert len(risk_mismatch) == 1
        assert risk_mismatch[0].severity == "high"

    def test_overconfidence_detection(self, high_risk_profile):
        """Test detection of overconfidence bias."""
        biases = identify_behavioral_biases(high_risk_profile)

        # Should detect overconfidence
        overconfidence = [b for b in biases if b.bias_type == "overconfidence"]
        assert len(overconfidence) == 1

    def test_leverage_risk_detection(self, high_risk_profile):
        """Test detection of leverage risk behavior."""
        biases = identify_behavioral_biases(high_risk_profile)

        # Should detect leverage risk (high debt + high willingness)
        leverage = [b for b in biases if b.bias_type == "leverage_risk"]
        assert len(leverage) == 1
        assert leverage[0].severity == "high"

    def test_inadequate_safety_net_detection(self, high_risk_profile):
        """Test detection of inadequate emergency fund."""
        biases = identify_behavioral_biases(high_risk_profile)

        # Should detect inadequate safety net (2 months < 3, willingness >= 3)
        safety_net = [b for b in biases if b.bias_type == "inadequate_safety_net"]
        assert len(safety_net) == 1

    def test_balanced_profile_no_biases(self, sample_profile):
        """Test that a balanced profile has no major biases."""
        biases = identify_behavioral_biases(sample_profile)

        # Should not have high severity biases
        high_severity = [b for b in biases if b.severity == "high"]
        assert len(high_severity) == 0

    def test_bias_attributes(self, high_ability_low_willingness_profile):
        """Test that bias objects have all required attributes."""
        biases = identify_behavioral_biases(high_ability_low_willingness_profile)

        for bias in biases:
            assert isinstance(bias, BehavioralBias)
            assert bias.bias_type
            assert bias.name
            assert bias.description
            assert bias.severity in ["high", "medium", "low"]
            assert bias.recommendation


# ============================================================
# Test Report Storage
# ============================================================

class TestReportStorage:
    """Tests for advisory report storage module."""

    def test_save_and_load_report(self, sample_report_content):
        """Test saving and loading a report."""
        saved = save_report(
            content=sample_report_content,
            client_name="Test Client",
            model="deepseek-v4-pro",
            prompt_tokens=1000,
            completion_tokens=2000,
        )

        # Verify saved report
        assert saved.report_id
        assert saved.client_name == "Test Client"
        assert saved.total_tokens == 3000

        # Load and verify
        loaded = load_report(Path(saved.filepath))
        assert loaded.content == sample_report_content
        assert loaded.model == "deepseek-v4-pro"

    def test_list_reports(self, sample_report_content):
        """Test listing saved reports."""
        # Save a report
        saved = save_report(
            content=sample_report_content,
            client_name="List Test Client",
            model="test-model",
        )

        # List reports
        reports = list_reports()
        assert len(reports) > 0

        # Find our report
        found = [r for r in reports if r["report_id"] == saved.report_id]
        assert len(found) == 1

    def test_list_reports_filter_by_client(self, sample_report_content):
        """Test filtering reports by client name."""
        # Save reports for different clients
        saved1 = save_report(
            content=sample_report_content,
            client_name="Client A",
            model="test-model",
        )
        saved2 = save_report(
            content=sample_report_content,
            client_name="Client B",
            model="test-model",
        )

        # Filter by client name
        reports = list_reports(client_name="Client A")
        found = [r for r in reports if r["client_name"] == "Client A"]
        assert len(found) >= 1

    def test_delete_report(self, sample_report_content):
        """Test deleting a report."""
        saved = save_report(
            content=sample_report_content,
            client_name="Delete Test",
            model="test-model",
        )

        filepath = Path(saved.filepath)
        assert filepath.exists()

        # Delete
        result = delete_report(filepath)
        assert result is True
        assert not filepath.exists()

    def test_export_markdown(self, sample_report_content):
        """Test exporting report to Markdown format."""
        saved = save_report(
            content=sample_report_content,
            client_name="Export Test",
            model="test-model",
        )

        loaded = load_report(Path(saved.filepath))
        markdown = export_report_markdown(loaded)

        # Verify Markdown format
        assert "# Investment Advisory Report" in markdown
        assert "Export Test" in markdown
        assert sample_report_content in markdown

    def test_update_report_notes(self, sample_report_content):
        """Test updating report notes."""
        saved = save_report(
            content=sample_report_content,
            client_name="Notes Test",
            model="test-model",
        )

        filepath = Path(saved.filepath)

        # Update notes
        result = update_report_notes(filepath, "Test notes added")
        assert result is True

        # Verify notes
        loaded = load_report(filepath)
        assert loaded.notes == "Test notes added"


# ============================================================
# Integration Test
# ============================================================

class TestPhase3Integration:
    """Integration test for Phase 3 features."""

    def test_full_workflow(self, sample_profile, sample_report_content):
        """Test complete workflow: create profile, identify biases, save report."""
        # 1. Save profile
        profile_path = save_profile(sample_profile)
        assert profile_path.exists()

        # 2. Load and verify profile
        loaded = load_profile(profile_path)
        assert loaded.name == sample_profile.name

        # 3. Identify biases
        biases = identify_behavioral_biases(loaded)
        assert isinstance(biases, list)

        # 4. Save report with profile reference
        report = save_report(
            content=sample_report_content,
            client_name=loaded.name,
            model="deepseek-v4-pro",
            profile_filepath=str(profile_path),
        )
        assert report.client_name == loaded.name

        # 5. Get reports for this profile
        profile_reports = get_reports_for_profile(str(profile_path))
        assert len(profile_reports) >= 1

        # 6. Update profile
        loaded.age = 36
        update_profile(profile_path, loaded)
        updated = load_profile(profile_path)
        assert updated.age == 36
