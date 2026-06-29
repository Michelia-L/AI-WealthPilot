"""
AI WealthPilot - IPS Data Model Unit Tests

Tests the Pydantic schemas for IPS documents, review results,
and audit trail models. Verifies validation, serialization,
and constraint enforcement.


"""

import json
import pytest
from pydantic import ValidationError

from src.agents.ips_models import (
    # IPS Document models
    IPSDocument,
    GoalReturnRequirement,
    ReturnObjective,
    RiskToleranceAssessment,
    RiskToleranceLevel,
    TimeHorizonAnalysis,
    TimeHorizonStage,
    LiquidityConstraint,
    TaxConstraint,
    LegalConstraint,
    UniqueCircumstance,
    AssetAllocationTarget,
    InvestmentGuideline,
    BenchmarkSpec,
    MonitoringPolicy,
    CurrencyPolicy,
    FeeSchedule,
    # Review models
    ReviewResult,
    ReviewIssue,
    ReviewDimension,
    IssueSeverity,
    # Audit trail models
    RevisionRecord,
    AuditTrail,
)


# ============================================================
# Fixtures — Minimal Valid Data
# ============================================================

@pytest.fixture
def minimal_return_objective() -> dict:
    """Minimal valid ReturnObjective data."""
    return {
        "required_nominal_return": 0.08,
        "required_real_return": 0.05,
        "return_calculation_basis": "Based on retirement goal",
        "return_objective_narrative": "Target 8% nominal return",
    }


@pytest.fixture
def minimal_risk_tolerance() -> dict:
    """Minimal valid RiskToleranceAssessment data."""
    return {
        "ability_assessment": "High ability based on income and assets",
        "willingness_assessment": "Moderate willingness based on survey",
        "overall_risk_level": "moderate",
        "risk_narrative": "Overall moderate risk tolerance",
    }


@pytest.fixture
def minimal_time_horizon() -> dict:
    """Minimal valid TimeHorizonAnalysis data."""
    return {
        "stages": [
            {"name": "Accumulation", "years": 20, "description": "Wealth building phase"}
        ],
        "overall_horizon_years": 20,
        "horizon_narrative": "Long-term investment horizon",
    }


@pytest.fixture
def minimal_ips_data(
    minimal_return_objective,
    minimal_risk_tolerance,
    minimal_time_horizon,
) -> dict:
    """Minimal valid IPSDocument data."""
    return {
        "client_name": "Test Client",
        "executive_summary": "Test IPS summary",
        "client_background": "Test background",
        "return_objective": minimal_return_objective,
        "risk_tolerance": minimal_risk_tolerance,
        "time_horizon": minimal_time_horizon,
        "liquidity": {
            "immediate_needs": 50000.0,
            "ongoing_needs": 30000.0,
            "emergency_reserve_months": 6,
            "liquidity_narrative": "Adequate liquidity",
        },
        "tax": {
            "tax_status": "taxable",
            "tax_considerations": "Standard tax regime",
            "tax_narrative": "No special tax considerations",
        },
        "legal": {
            "applicable_regulations": ["Securities Law"],
            "legal_narrative": "Standard legal framework",
        },
        "unique_circumstances": {
            "other_circumstances": "None",
            "unique_narrative": "No special circumstances",
        },
        "investment_guidelines": {
            "strategic_allocation": [
                {
                    "asset_class": "Equity",
                    "target_weight": 0.60,
                    "min_weight": 0.50,
                    "max_weight": 0.70,
                    "rationale": "Growth",
                },
                {
                    "asset_class": "Fixed Income",
                    "target_weight": 0.30,
                    "min_weight": 0.20,
                    "max_weight": 0.40,
                    "rationale": "Stability",
                },
                {
                    "asset_class": "Cash",
                    "target_weight": 0.10,
                    "min_weight": 0.05,
                    "max_weight": 0.15,
                    "rationale": "Liquidity",
                },
            ],
            "permitted_instruments": ["ETF", "Mutual Funds"],
            "prohibited_instruments": ["Leveraged ETF"],
            "rebalancing_policy": "Quarterly rebalancing",
            "guideline_narrative": "Standard 60/30/10 allocation",
        },
        "monitoring": {
            "review_frequency": "quarterly",
            "benchmarks": [
                {"asset_class": "Equity", "benchmark": "CSI 300"},
            ],
            "rebalancing_triggers": ["5% deviation from target"],
            "monitoring_narrative": "Quarterly review cycle",
        },
        "risk_disclosure": "Past performance does not guarantee future results",
        "compliance_statement": "For educational purposes only",
    }


# ============================================================
# Test: IPS Document Section Models
# ============================================================

class TestReturnObjective:
    """Tests for the ReturnObjective model."""

    def test_valid_creation(self, minimal_return_objective):
        """Test creating a valid ReturnObjective."""
        obj = ReturnObjective(**minimal_return_objective)
        assert obj.required_nominal_return == 0.08
        assert obj.required_real_return == 0.05

    def test_missing_required_field(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            ReturnObjective(
                required_nominal_return=0.08,
                # missing required_real_return and others
            )

    def test_backward_compatible_without_goals(self, minimal_return_objective):
        """Test that existing code without goal_level_requirements still works."""
        obj = ReturnObjective(**minimal_return_objective)
        assert obj.goal_level_requirements == []
        assert obj.return_methodology == ""

    def test_with_single_goal(self):
        """Test ReturnObjective with a single goal requirement."""
        goal = GoalReturnRequirement(
            goal_name="Retirement",
            target_amount=5_000_000.0,
            current_allocation=2_000_000.0,
            time_horizon_years=20,
            priority="high",
            required_return=0.0469,  # (5M/2M)^(1/20) - 1
            calculation_basis="TVM: r = (5000000/2000000)^(1/20) - 1 = 4.69%",
        )
        obj = ReturnObjective(
            required_nominal_return=0.0469,
            required_real_return=0.0219,
            return_calculation_basis="Single-goal TVM derivation",
            return_objective_narrative="Retirement-focused return target",
            goal_level_requirements=[goal],
            return_methodology="TVM: r = (FV/PV)^(1/n) - 1",
        )
        assert len(obj.goal_level_requirements) == 1
        assert obj.goal_level_requirements[0].goal_name == "Retirement"
        assert obj.return_methodology == "TVM: r = (FV/PV)^(1/n) - 1"

    def test_with_multiple_goals_composite_return(self):
        """Test multi-goal return with capital-weighted composite rate."""
        goals = [
            GoalReturnRequirement(
                goal_name="Retirement",
                target_amount=5_000_000.0,
                current_allocation=1_500_000.0,
                time_horizon_years=20,
                priority="high",
                required_return=0.0627,
                calculation_basis="TVM: (5M/1.5M)^(1/20)-1",
            ),
            GoalReturnRequirement(
                goal_name="Child Education",
                target_amount=1_000_000.0,
                current_allocation=500_000.0,
                time_horizon_years=10,
                priority="high",
                required_return=0.0718,
                calculation_basis="TVM: (1M/0.5M)^(1/10)-1",
            ),
        ]
        # Capital-weighted composite: (1.5M*6.27% + 0.5M*7.18%) / 2M = 6.50%
        composite = (1_500_000 * 0.0627 + 500_000 * 0.0718) / 2_000_000
        obj = ReturnObjective(
            required_nominal_return=round(composite, 4),
            required_real_return=round(composite - 0.025, 4),
            return_calculation_basis="Capital-weighted composite of 2 goals",
            return_objective_narrative="Multi-goal return decomposition",
            goal_level_requirements=goals,
            return_methodology="TVM: r = (FV/PV)^(1/n) - 1",
        )
        assert len(obj.goal_level_requirements) == 2
        assert abs(obj.required_nominal_return - composite) < 1e-4

    def test_goal_serialization_roundtrip(self):
        """Test that goals survive JSON serialization roundtrip."""
        goal = GoalReturnRequirement(
            goal_name="House",
            target_amount=3_000_000.0,
            current_allocation=1_000_000.0,
            time_horizon_years=5,
            priority="medium",
            required_return=0.2457,
            calculation_basis="TVM: (3M/1M)^(1/5)-1",
        )
        obj = ReturnObjective(
            required_nominal_return=0.2457,
            required_real_return=0.2207,
            return_calculation_basis="Single goal",
            return_objective_narrative="House purchase",
            goal_level_requirements=[goal],
            return_methodology="TVM",
        )
        json_str = obj.model_dump_json()
        obj2 = ReturnObjective.model_validate_json(json_str)
        assert len(obj2.goal_level_requirements) == 1
        assert obj2.goal_level_requirements[0].target_amount == 3_000_000.0
        assert obj2.return_methodology == "TVM"


class TestRiskToleranceAssessment:
    """Tests for the RiskToleranceAssessment model."""

    def test_valid_creation(self, minimal_risk_tolerance):
        """Test creating a valid RiskToleranceAssessment."""
        obj = RiskToleranceAssessment(**minimal_risk_tolerance)
        assert obj.overall_risk_level == RiskToleranceLevel.MODERATE
        assert obj.conflict_resolution is None  # optional

    def test_all_risk_levels(self):
        """Test all valid risk tolerance levels."""
        for level in RiskToleranceLevel:
            data = {
                "ability_assessment": "test",
                "willingness_assessment": "test",
                "overall_risk_level": level.value,
                "risk_narrative": "test",
            }
            obj = RiskToleranceAssessment(**data)
            assert obj.overall_risk_level == level

    def test_invalid_risk_level(self):
        """Test that invalid risk level raises ValidationError."""
        with pytest.raises(ValidationError):
            RiskToleranceAssessment(
                ability_assessment="test",
                willingness_assessment="test",
                overall_risk_level="ultra_aggressive",  # invalid
                risk_narrative="test",
            )

    def test_with_conflict_resolution(self):
        """Test creating assessment with conflict resolution."""
        obj = RiskToleranceAssessment(
            ability_assessment="High ability",
            willingness_assessment="Low willingness",
            conflict_resolution="Use lower score (willingness)",
            overall_risk_level="moderately_conservative",
            risk_narrative="Conflict resolved using prudential principle",
        )
        assert obj.conflict_resolution is not None

    def test_quantitative_anchors_default_none(self, minimal_risk_tolerance):
        """Test that quantitative risk anchors default to None."""
        obj = RiskToleranceAssessment(**minimal_risk_tolerance)
        assert obj.max_acceptable_annual_loss is None
        assert obj.target_volatility_min is None
        assert obj.target_volatility_max is None
        assert obj.var_tolerance_95 is None
        assert obj.max_drawdown_tolerance is None

    def test_with_quantitative_anchors(self):
        """Test creating assessment with quantitative risk anchors."""
        obj = RiskToleranceAssessment(
            ability_assessment="Moderate ability",
            willingness_assessment="Moderate willingness",
            overall_risk_level="moderate",
            risk_narrative="Balanced risk profile",
            max_acceptable_annual_loss=-0.15,
            target_volatility_min=0.10,
            target_volatility_max=0.15,
            var_tolerance_95=-0.20,
            max_drawdown_tolerance=-0.25,
        )
        assert obj.max_acceptable_annual_loss == -0.15
        assert obj.target_volatility_min == 0.10
        assert obj.target_volatility_max == 0.15
        assert obj.var_tolerance_95 == -0.20
        assert obj.max_drawdown_tolerance == -0.25
        # Verify volatility range is coherent
        assert obj.target_volatility_min < obj.target_volatility_max

    def test_quantitative_anchors_serialization(self):
        """Test JSON roundtrip for quantitative risk anchors."""
        obj = RiskToleranceAssessment(
            ability_assessment="test",
            willingness_assessment="test",
            overall_risk_level="aggressive",
            risk_narrative="test",
            max_acceptable_annual_loss=-0.30,
            target_volatility_min=0.16,
            target_volatility_max=0.25,
            var_tolerance_95=-0.35,
            max_drawdown_tolerance=-0.40,
        )
        json_str = obj.model_dump_json()
        obj2 = RiskToleranceAssessment.model_validate_json(json_str)
        assert obj2.max_acceptable_annual_loss == obj.max_acceptable_annual_loss
        assert obj2.target_volatility_min == obj.target_volatility_min
        assert obj2.max_drawdown_tolerance == obj.max_drawdown_tolerance


class TestTimeHorizonAnalysis:
    """Tests for the TimeHorizonAnalysis model."""

    def test_single_stage(self, minimal_time_horizon):
        """Test single-stage time horizon."""
        obj = TimeHorizonAnalysis(**minimal_time_horizon)
        assert len(obj.stages) == 1
        assert obj.overall_horizon_years == 20

    def test_multi_stage(self):
        """Test multi-stage time horizon."""
        obj = TimeHorizonAnalysis(
            stages=[
                TimeHorizonStage(name="Accumulation", years=20, description="Building"),
                TimeHorizonStage(name="Distribution", years=25, description="Spending"),
            ],
            overall_horizon_years=45,
            horizon_narrative="Multi-stage horizon",
        )
        assert len(obj.stages) == 2
        assert obj.overall_horizon_years == 45


class TestCurrencyPolicy:
    """Tests for the CurrencyPolicy model."""

    def test_default_creation(self):
        """Test default values of CurrencyPolicy."""
        policy = CurrencyPolicy()
        assert policy.base_currency == "CNY"
        assert policy.foreign_exposure_pct == 0.0
        assert policy.hedging_strategy == ""
        assert policy.hedging_ratio == 0.0

    def test_custom_creation(self):
        """Test customized values of CurrencyPolicy."""
        policy = CurrencyPolicy(
            base_currency="CNY",
            foreign_exposure_pct=0.35,
            hedging_strategy="Partial hedge via forward contracts",
            hedging_ratio=0.50,
            currency_narrative="Hedging 50% of USD exposure to mitigate RMB appreciation risk.",
        )
        assert policy.base_currency == "CNY"
        assert policy.foreign_exposure_pct == 0.35
        assert policy.hedging_strategy == "Partial hedge via forward contracts"
        assert policy.hedging_ratio == 0.50


class TestFeeSchedule:
    """Tests for the FeeSchedule model."""

    def test_default_creation(self):
        """Test default values of FeeSchedule."""
        fee = FeeSchedule()
        assert fee.management_fee_rate == 0.0
        assert fee.custody_fee_rate == 0.0
        assert fee.transaction_cost_estimate == 0.0
        assert fee.total_expense_ratio == 0.0
        assert fee.net_return_impact == ""
        assert fee.fee_narrative == ""

    def test_custom_creation(self):
        """Test FeeSchedule with realistic wealth management fees."""
        fee = FeeSchedule(
            management_fee_rate=0.01,
            custody_fee_rate=0.002,
            transaction_cost_estimate=0.003,
            total_expense_ratio=0.015,
            net_return_impact="Gross return 8.00% - TER 1.50% = Net return 6.50%",
            fee_narrative=(
                "Management fee covers portfolio construction and ongoing monitoring. "
                "Custody fee covers safekeeping of assets. Transaction costs estimated "
                "based on quarterly rebalancing."
            ),
        )
        assert fee.management_fee_rate == 0.01
        assert fee.custody_fee_rate == 0.002
        assert fee.transaction_cost_estimate == 0.003
        assert fee.total_expense_ratio == 0.015
        # Verify TER = sum of component fees
        computed_ter = fee.management_fee_rate + fee.custody_fee_rate + fee.transaction_cost_estimate
        assert abs(fee.total_expense_ratio - computed_ter) < 0.0001

    def test_serialization_roundtrip(self):
        """Test JSON roundtrip for FeeSchedule."""
        fee = FeeSchedule(
            management_fee_rate=0.012,
            custody_fee_rate=0.001,
            transaction_cost_estimate=0.002,
            total_expense_ratio=0.015,
            net_return_impact="Net impact: -1.5% per annum",
            fee_narrative="Standard fee structure.",
        )
        json_str = fee.model_dump_json()
        fee2 = FeeSchedule.model_validate_json(json_str)
        assert fee2.management_fee_rate == fee.management_fee_rate
        assert fee2.total_expense_ratio == fee.total_expense_ratio
        assert fee2.fee_narrative == fee.fee_narrative


# ============================================================
# Test: Complete IPSDocument
# ============================================================

class TestIPSDocument:
    """Tests for the complete IPSDocument model."""

    def test_valid_creation(self, minimal_ips_data):
        """Test creating a complete, valid IPSDocument."""
        doc = IPSDocument(**minimal_ips_data)
        assert doc.client_name == "Test Client"
        assert doc.version == "1.0"  # default
        assert doc.prepared_by == "AI WealthPilot IPS Generator"  # default
        assert doc.currency_policy is None
        assert doc.fee_schedule is None

    def test_with_fee_schedule(self, minimal_ips_data):
        """Test IPSDocument with fee schedule."""
        data = minimal_ips_data.copy()
        data["fee_schedule"] = {
            "management_fee_rate": 0.01,
            "custody_fee_rate": 0.002,
            "transaction_cost_estimate": 0.003,
            "total_expense_ratio": 0.015,
            "net_return_impact": "Gross return 8.00% - TER 1.50% = Net return 6.50%",
            "fee_narrative": "Full fee disclosure for transparency.",
        }
        doc = IPSDocument(**data)
        assert doc.fee_schedule is not None
        assert doc.fee_schedule.management_fee_rate == 0.01
        assert doc.fee_schedule.total_expense_ratio == 0.015
        assert "TER" in doc.fee_schedule.net_return_impact

    def test_with_currency_policy(self, minimal_ips_data):
        """Test IPSDocument with currency policy."""
        data = minimal_ips_data.copy()
        data["currency_policy"] = {
            "base_currency": "CNY",
            "foreign_exposure_pct": 0.25,
            "hedging_strategy": "Unhedged",
            "hedging_ratio": 0.0,
            "currency_narrative": "Foreign exposure consists of global equities, unhedged.",
        }
        doc = IPSDocument(**data)
        assert doc.currency_policy is not None
        assert doc.currency_policy.base_currency == "CNY"
        assert doc.currency_policy.foreign_exposure_pct == 0.25

    def test_serialization_roundtrip(self, minimal_ips_data):
        """Test JSON serialization and deserialization roundtrip."""
        doc = IPSDocument(**minimal_ips_data)
        json_str = doc.model_dump_json()
        doc2 = IPSDocument.model_validate_json(json_str)
        assert doc2.client_name == doc.client_name
        assert doc2.return_objective.required_nominal_return == 0.08

    def test_dict_roundtrip(self, minimal_ips_data):
        """Test dict serialization and deserialization roundtrip."""
        doc = IPSDocument(**minimal_ips_data)
        d = doc.model_dump()
        doc2 = IPSDocument(**d)
        assert doc2.client_name == doc.client_name

    def test_allocation_weights(self, minimal_ips_data):
        """Test that allocation weights can be validated."""
        doc = IPSDocument(**minimal_ips_data)
        total = sum(
            a.target_weight
            for a in doc.investment_guidelines.strategic_allocation
        )
        assert abs(total - 1.0) < 0.01  # Weights should sum to ~100%


# ============================================================
# Test: Review Models
# ============================================================

class TestReviewModels:
    """Tests for review-related models."""

    def test_review_issue_creation(self):
        """Test creating a ReviewIssue."""
        issue = ReviewIssue(
            section="risk_tolerance",
            dimension=ReviewDimension.SUITABILITY,
            severity=IssueSeverity.CRITICAL,
            description="Risk level does not match profile",
            regulation_reference="IPS Framework",
            suggestion="Adjust risk level to moderate",
        )
        assert issue.severity == IssueSeverity.CRITICAL
        assert issue.dimension == ReviewDimension.SUITABILITY

    def test_review_result_passed(self):
        """Test a passing review result."""
        result = ReviewResult(
            dimension=ReviewDimension.COMPLIANCE,
            passed=True,
            issues=[],
            summary="All compliance checks passed",
        )
        assert result.passed is True
        assert len(result.issues) == 0

    def test_review_result_with_issues(self):
        """Test a review result with issues."""
        issues = [
            ReviewIssue(
                section="investment_guidelines",
                dimension=ReviewDimension.CONSISTENCY,
                severity=IssueSeverity.WARNING,
                description="Allocation inconsistent with risk level",
                suggestion="Reduce equity to below 60%",
            ),
        ]
        result = ReviewResult(
            dimension=ReviewDimension.CONSISTENCY,
            passed=False,
            issues=issues,
            summary="Found 1 consistency issue",
        )
        assert result.passed is False
        assert len(result.issues) == 1

    def test_review_dimension_enum(self):
        """Test ReviewDimension enum values."""
        assert ReviewDimension.SUITABILITY.value == "suitability"
        assert ReviewDimension.COMPLIANCE.value == "compliance"
        assert ReviewDimension.CONSISTENCY.value == "consistency"


# ============================================================
# Test: Audit Trail Models
# ============================================================

class TestAuditTrailModels:
    """Tests for audit trail models."""

    def test_revision_record(self):
        """Test creating a RevisionRecord."""
        record = RevisionRecord(
            round_number=1,
            review_results=[
                ReviewResult(
                    dimension=ReviewDimension.SUITABILITY,
                    passed=False,
                    issues=[],
                    summary="Failed",
                ),
            ],
            changes_made=["Adjusted risk level"],
            ips_version_before="abc123",
            ips_version_after="def456",
        )
        assert record.round_number == 1
        assert len(record.changes_made) == 1

    def test_audit_trail(self):
        """Test creating a complete AuditTrail."""
        trail = AuditTrail(
            revision_history=[],
            total_rounds=0,
            final_status="approved",
            generation_metadata={
                "model": "deepseek-v4-pro",
                "total_tokens": 50000,
            },
        )
        assert trail.final_status == "approved"
        assert trail.total_rounds == 0

    def test_audit_trail_defaults(self):
        """Test AuditTrail default values."""
        trail = AuditTrail()
        assert trail.final_status == "pending"
        assert trail.total_rounds == 0
        assert len(trail.revision_history) == 0

    def test_audit_trail_serialization(self):
        """Test AuditTrail JSON roundtrip."""
        trail = AuditTrail(
            total_rounds=2,
            final_status="escalated_to_human",
            generation_metadata={"model": "deepseek-v4-pro"},
        )
        json_str = trail.model_dump_json()
        trail2 = AuditTrail.model_validate_json(json_str)
        assert trail2.total_rounds == 2
        assert trail2.final_status == "escalated_to_human"
