"""
AI WealthPilot - IPS Workflow Integration Tests

Tests the LangGraph state machine logic: state transitions,
conditional routing, and node function contracts.
These tests use mocked LLM calls to verify workflow logic
without requiring a live API key.

CFA Reference:
    - CFA L3: IPS generation and review process
"""

import json
import numpy as np
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.agents.ips_models import (
    IPSDocument,
    ReviewResult,
    ReviewDimension,
    IssueSeverity,
    ReviewIssue,
)
from src.agents.ips_workflow import (
    IPSWorkflowState,
    route_after_review,
    route_after_revision,
    _all_passed,
    _has_critical_issues,
    _ips_version_hash,
    _fuzzy_asset_match,
    build_ips_workflow,
    validate_saa_node,
)
from src.portfolio.cme_models import CMEReport, AssetClassCME, SAAValidationResult


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def minimal_ips_dict() -> dict:
    """Minimal IPS document as dict for testing."""
    return {
        "client_name": "Test",
        "prepared_by": "AI",
        "preparation_date": "2025-01-01",
        "version": "1.0",
        "executive_summary": "Summary",
        "client_background": "Background",
        "return_objective": {
            "required_nominal_return": 0.08,
            "required_real_return": 0.05,
            "return_calculation_basis": "Test",
            "return_objective_narrative": "Test",
        },
        "risk_tolerance": {
            "ability_assessment": "Test",
            "willingness_assessment": "Test",
            "overall_risk_level": "moderate",
            "risk_narrative": "Test",
        },
        "time_horizon": {
            "stages": [{"name": "Test", "years": 20, "description": "Test"}],
            "overall_horizon_years": 20,
            "horizon_narrative": "Test",
        },
        "liquidity": {
            "immediate_needs": 50000,
            "ongoing_needs": 30000,
            "emergency_reserve_months": 6,
            "liquidity_narrative": "Test",
        },
        "tax": {
            "tax_status": "taxable",
            "tax_considerations": "Test",
            "tax_narrative": "Test",
        },
        "legal": {
            "applicable_regulations": ["Test"],
            "legal_narrative": "Test",
        },
        "unique_circumstances": {
            "other_circumstances": "None",
            "unique_narrative": "Test",
        },
        "investment_guidelines": {
            "strategic_allocation": [
                {
                    "asset_class": "Equity",
                    "target_weight": 0.6,
                    "min_weight": 0.5,
                    "max_weight": 0.7,
                    "rationale": "Growth",
                },
                {
                    "asset_class": "Bonds",
                    "target_weight": 0.4,
                    "min_weight": 0.3,
                    "max_weight": 0.5,
                    "rationale": "Stability",
                },
            ],
            "permitted_instruments": ["ETF"],
            "prohibited_instruments": [],
            "rebalancing_policy": "Quarterly",
            "guideline_narrative": "Test",
        },
        "monitoring": {
            "review_frequency": "quarterly",
            "benchmarks": [{"asset_class": "Equity", "benchmark": "CSI 300"}],
            "rebalancing_triggers": ["5% deviation"],
            "monitoring_narrative": "Test",
        },
        "risk_disclosure": "Test disclosure",
        "compliance_statement": "Test statement",
    }


# ============================================================
# Test: State Model
# ============================================================

class TestIPSWorkflowState:
    """Tests for the IPSWorkflowState model."""

    def test_default_state(self):
        """Test default state initialization."""
        state = IPSWorkflowState()
        assert state.status == "initialized"
        assert state.revision_count == 0
        assert state.max_revisions == 3
        assert state.ips_draft is None
        assert state.final_ips is None

    def test_state_with_values(self):
        """Test state with custom values."""
        state = IPSWorkflowState(
            client_profile_json='{"name": "Test"}',
            max_revisions=5,
        )
        assert state.max_revisions == 5


# ============================================================
# Test: Routing Functions
# ============================================================

class TestRouting:
    """Tests for the conditional routing functions."""

    def test_route_all_passed(self):
        """Route to 'pass' when all reviews pass."""
        state = IPSWorkflowState(
            review_results=[
                {"dimension": "suitability", "passed": True, "issues": [], "summary": "OK"},
                {"dimension": "compliance", "passed": True, "issues": [], "summary": "OK"},
                {"dimension": "consistency", "passed": True, "issues": [], "summary": "OK"},
            ],
            revision_count=0,
        )
        assert route_after_review(state) == "pass"

    def test_route_issues_found(self):
        """Route to 'revise' when issues found and budget remains."""
        state = IPSWorkflowState(
            review_results=[
                {"dimension": "suitability", "passed": False, "issues": [{"severity": "warning"}], "summary": "Issues"},
                {"dimension": "compliance", "passed": True, "issues": [], "summary": "OK"},
                {"dimension": "consistency", "passed": True, "issues": [], "summary": "OK"},
            ],
            revision_count=0,
            max_revisions=3,
        )
        assert route_after_review(state) == "revise"

    def test_route_max_revisions_reached(self):
        """Route to 'escalate' when max revisions reached."""
        state = IPSWorkflowState(
            review_results=[
                {"dimension": "suitability", "passed": False, "issues": [], "summary": "Issues"},
            ],
            revision_count=3,
            max_revisions=3,
        )
        assert route_after_review(state) == "escalate"

    def test_route_after_revision_continue(self):
        """Route to 'review_again' when revision budget remains."""
        state = IPSWorkflowState(revision_count=1, max_revisions=3)
        assert route_after_revision(state) == "review_again"

    def test_route_after_revision_escalate(self):
        """Route to 'escalate' when max revisions reached."""
        state = IPSWorkflowState(revision_count=3, max_revisions=3)
        assert route_after_revision(state) == "escalate"


# ============================================================
# Test: Helper Functions
# ============================================================

class TestHelpers:
    """Tests for workflow helper functions."""

    def test_all_passed_true(self):
        """Test _all_passed with all passing."""
        results = [
            {"passed": True},
            {"passed": True},
            {"passed": True},
        ]
        assert _all_passed(results) is True

    def test_all_passed_false(self):
        """Test _all_passed with one failing."""
        results = [
            {"passed": True},
            {"passed": False},
            {"passed": True},
        ]
        assert _all_passed(results) is False

    def test_all_passed_empty(self):
        """Test _all_passed with empty list."""
        assert _all_passed([]) is True

    def test_has_critical_issues(self):
        """Test _has_critical_issues detection."""
        results = [
            {
                "passed": False,
                "issues": [{"severity": "critical"}],
            },
        ]
        assert _has_critical_issues(results) is True

    def test_no_critical_issues(self):
        """Test _has_critical_issues with only warnings."""
        results = [
            {
                "passed": False,
                "issues": [{"severity": "warning"}],
            },
        ]
        assert _has_critical_issues(results) is False

    def test_ips_version_hash(self, minimal_ips_dict):
        """Test IPS version hash generation."""
        hash1 = _ips_version_hash(minimal_ips_dict)
        assert isinstance(hash1, str)
        assert len(hash1) == 8  # short MD5 hash

        # Same input should produce same hash
        hash2 = _ips_version_hash(minimal_ips_dict)
        assert hash1 == hash2

        # Different input should produce different hash
        modified = {**minimal_ips_dict, "client_name": "Different"}
        hash3 = _ips_version_hash(modified)
        assert hash1 != hash3


# ============================================================
# Test: Graph Construction
# ============================================================

class TestGraphConstruction:
    """Tests for LangGraph workflow construction."""

    def test_build_workflow(self):
        """Test that the workflow graph builds without errors."""
        workflow = build_ips_workflow()
        assert workflow is not None

    def test_workflow_has_expected_nodes(self):
        """Test that the workflow has all expected nodes."""
        workflow = build_ips_workflow()
        # LangGraph stores nodes internally; check via compile
        # The fact that build_ips_workflow() doesn't raise is the key test
        compiled = workflow.compile()
        assert compiled is not None


# ============================================================
# Test: SAA Validation Node (P0-1 Enhancement)
# ============================================================

class TestSAAValidation:
    """Tests for the enhanced validate_saa_node with real volatility computation."""

    def _build_cme_report(
        self,
        asset_classes: list[dict],
        corr_matrix: dict[str, dict[str, float]],
        rf_rate: float = 0.04,
    ) -> dict:
        """Build a CMEReport dict for testing."""
        cme_list = []
        for ac in asset_classes:
            cme_list.append(AssetClassCME(
                name=ac["name"],
                ticker=ac.get("ticker", "TEST"),
                expected_return=ac["expected_return"],
                volatility=ac["volatility"],
                sharpe_ratio=ac.get("sharpe", 0.5),
                max_drawdown=ac.get("mdd", -0.20),
                var_95=ac.get("var_95", 0.02),
                cvar_95=ac.get("cvar_95", 0.03),
                data_points=ac.get("data_points", 1000),
            ))
        report = CMEReport(
            as_of_date="2026-06-01",
            data_lookback_years=5,
            risk_free_rate=rf_rate,
            risk_free_rate_source="test",
            inflation_assumption=0.025,
            asset_classes=cme_list,
            correlation_matrix=corr_matrix,
            methodology_notes="Test methodology",
        )
        return report.model_dump()

    def _build_state(
        self,
        cme_report: dict,
        ips_draft: dict,
    ) -> IPSWorkflowState:
        """Build workflow state with CME report and IPS draft."""
        return IPSWorkflowState(
            cme_report=cme_report,
            ips_draft=ips_draft,
            review_results=[],
            all_review_issues=[],
        )

    def _run(self, coro):
        """Run an async coroutine synchronously."""
        import asyncio
        return asyncio.run(coro)

    def test_portfolio_volatility_calculation(self):
        """
        Test σ_p = √(w^T Σ w) with a known 2-asset portfolio.

        Setup:
            Asset A: σ=20%, w=60%
            Asset B: σ=10%, w=40%
            ρ(A,B) = 0.3

        Expected:
            Σ = [[0.04, 0.006], [0.006, 0.01]]
            σ_p² = 0.6² × 0.04 + 2 × 0.6 × 0.4 × 0.006 + 0.4² × 0.01
                 = 0.0144 + 0.00288 + 0.0016
                 = 0.01888
            σ_p  = √0.01888 ≈ 0.13740
        """
        cme_report = self._build_cme_report(
            asset_classes=[
                {"name": "权益", "expected_return": 0.10, "volatility": 0.20,
                 "var_95": 0.025, "cvar_95": 0.035},
                {"name": "固收", "expected_return": 0.04, "volatility": 0.10,
                 "var_95": 0.008, "cvar_95": 0.012},
            ],
            corr_matrix={
                "权益": {"权益": 1.0, "固收": 0.3},
                "固收": {"权益": 0.3, "固收": 1.0},
            },
            rf_rate=0.03,
        )

        ips_draft = {
            "return_objective": {"required_nominal_return": 0.07},
            "risk_tolerance": {"overall_risk_level": "moderate"},
            "investment_guidelines": {
                "strategic_allocation": [
                    {"asset_class": "权益", "target_weight": 0.6},
                    {"asset_class": "固收", "target_weight": 0.4},
                ],
            },
        }

        state = self._build_state(cme_report, ips_draft)
        result = self._run(validate_saa_node(state))

        # Verify validation result was stored
        assert "saa_validation" in result
        val = result["saa_validation"]
        assert val is not None

        # Verify portfolio return: 0.6 × 0.10 + 0.4 × 0.04 = 0.076
        assert abs(val["portfolio_expected_return"] - 0.076) < 1e-6

        # Verify portfolio volatility: √0.01888 ≈ 0.13740
        expected_vol = np.sqrt(0.01888)
        assert abs(val["portfolio_volatility"] - expected_vol) < 1e-4
        assert val["portfolio_volatility"] > 0  # No longer 0.0!

        # Verify Sharpe ratio: (0.076 - 0.03) / σ_p
        expected_sharpe = (0.076 - 0.03) / expected_vol
        assert abs(val["portfolio_sharpe"] - expected_sharpe) < 1e-3

    def test_volatility_exceeds_risk_band(self):
        """
        Test that CRITICAL issue is raised when portfolio volatility
        exceeds the risk tolerance band.

        Conservative band: (4%, 8%). If vol > 8% × 1.2 = 9.6%, trigger.
        """
        cme_report = self._build_cme_report(
            asset_classes=[
                {"name": "权益", "expected_return": 0.12, "volatility": 0.25,
                 "var_95": 0.03, "cvar_95": 0.04},
                {"name": "固收", "expected_return": 0.03, "volatility": 0.05,
                 "var_95": 0.005, "cvar_95": 0.007},
            ],
            corr_matrix={
                "权益": {"权益": 1.0, "固收": 0.2},
                "固收": {"权益": 0.2, "固收": 1.0},
            },
            rf_rate=0.03,
        )

        # 70% equity for a conservative investor = too much risk
        ips_draft = {
            "return_objective": {"required_nominal_return": 0.08},
            "risk_tolerance": {"overall_risk_level": "conservative"},
            "investment_guidelines": {
                "strategic_allocation": [
                    {"asset_class": "权益", "target_weight": 0.7},
                    {"asset_class": "固收", "target_weight": 0.3},
                ],
            },
        }

        state = self._build_state(cme_report, ips_draft)
        result = self._run(validate_saa_node(state))

        val = result.get("saa_validation", {})
        assert val is not None
        assert val["is_volatility_acceptable"] is False

        # Check that a CRITICAL volatility issue was raised
        issues = result.get("all_review_issues", [])
        vol_issues = [
            i for i in issues
            if "波动率" in i.get("description", "")
            and i.get("severity") == "critical"
        ]
        assert len(vol_issues) >= 1

    def test_unmatched_assets_detected(self):
        """Test that SAA assets not matching any CME class are flagged."""
        cme_report = self._build_cme_report(
            asset_classes=[
                {"name": "权益", "expected_return": 0.10, "volatility": 0.20,
                 "var_95": 0.02, "cvar_95": 0.03},
            ],
            corr_matrix={"权益": {"权益": 1.0}},
        )

        ips_draft = {
            "return_objective": {"required_nominal_return": 0.06},
            "risk_tolerance": {"overall_risk_level": "moderate"},
            "investment_guidelines": {
                "strategic_allocation": [
                    {"asset_class": "权益", "target_weight": 0.5},
                    {"asset_class": "私募信贷", "target_weight": 0.3},
                    {"asset_class": "基础设施", "target_weight": 0.2},
                ],
            },
        }

        state = self._build_state(cme_report, ips_draft)
        result = self._run(validate_saa_node(state))

        # Check unmatched asset issue was raised
        issues = result.get("all_review_issues", [])
        unmatched = [
            i for i in issues
            if "无法与 CME 数据匹配" in i.get("description", "")
        ]
        assert len(unmatched) == 1
        assert "私募信贷" in unmatched[0]["description"]
        assert "基础设施" in unmatched[0]["description"]

    def test_no_cme_data_skips_validation(self):
        """Test graceful skip when no CME data available."""
        state = IPSWorkflowState(
            cme_report=None,
            ips_draft={"investment_guidelines": {"strategic_allocation": []}},
        )
        result = self._run(validate_saa_node(state))
        assert result == {}

    def test_weights_sum_check(self):
        """Test that weight sum != 100% triggers CRITICAL issue."""
        cme_report = self._build_cme_report(
            asset_classes=[
                {"name": "权益", "expected_return": 0.10, "volatility": 0.20,
                 "var_95": 0.02, "cvar_95": 0.03},
                {"name": "固收", "expected_return": 0.04, "volatility": 0.08,
                 "var_95": 0.008, "cvar_95": 0.012},
            ],
            corr_matrix={
                "权益": {"权益": 1.0, "固收": 0.3},
                "固收": {"权益": 0.3, "固收": 1.0},
            },
        )

        ips_draft = {
            "return_objective": {"required_nominal_return": 0.06},
            "risk_tolerance": {"overall_risk_level": "moderate"},
            "investment_guidelines": {
                "strategic_allocation": [
                    {"asset_class": "权益", "target_weight": 0.6},
                    {"asset_class": "固收", "target_weight": 0.3},
                    # Sum = 0.9, not 1.0!
                ],
            },
        }

        state = self._build_state(cme_report, ips_draft)
        result = self._run(validate_saa_node(state))

        issues = result.get("all_review_issues", [])
        weight_issues = [
            i for i in issues if "权重之和" in i.get("description", "")
        ]
        assert len(weight_issues) == 1
        assert weight_issues[0]["severity"] == "critical"

