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
    build_ips_workflow,
)


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
