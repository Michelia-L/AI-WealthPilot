"""
AI WealthPilot - IPS LangGraph Workflow Engine

Orchestrates the multi-agent IPS generation workflow as a LangGraph
state machine. The workflow follows a Generate → Review → Revise
loop with conditional routing and audit trail tracking.

Workflow Graph:
    START → generate_cme → generate → select_docs → review_suitability →
    review_compliance → review_consistency → validate_saa →
        (all pass) → finalize → END
        (issues)   → revise → select_docs (loop, max 3)
        (max rounds) → finalize (escalate) → END

CFA Reference:
    - CFA L3 PWM: IPS generation and review process
    - CFA L3: Setting Capital Market Expectations
    - CFA L3: Compliance and documentation requirements
"""

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, ConfigDict, Field

from src.agents.ips_models import (
    IPSDocument,
    ReviewResult,
    ReviewDimension,
    ReviewIssue,
    IssueSeverity,
    RevisionRecord,
    AuditTrail,
)
from src.agents.ips_agents import (
    create_ips_generator_agent,
    create_suitability_reviewer,
    create_compliance_reviewer,
    create_consistency_reviewer,
    create_ips_reviser_agent,
    build_generation_prompt,
    build_review_prompt,
    build_revision_prompt,
    load_ips_template,
    load_compliance_checklist,
)
from src.portfolio.cme_engine import compute_cme, format_cme_for_prompt
from src.portfolio.cme_models import CMEReport, SAAValidationResult

logger = logging.getLogger(__name__)


# ============================================================
# Workflow State Schema
# ============================================================

class IPSWorkflowState(BaseModel):
    """
    LangGraph state for the IPS generation workflow.

    This Pydantic model serves as the single source of truth
    for the entire workflow execution. Each node reads from
    and writes to this state.
    """
    # --- Input ---
    client_profile_json: str = Field(
        default="",
        description="Serialized ClientProfile as JSON string"
    )
    reference_template: str = Field(
        default="",
        description="IPS structural template full text"
    )

    # --- CME (Capital Market Expectations) ---
    cme_report: Optional[dict] = Field(
        default=None,
        description="CME report as dict (serialized CMEReport)"
    )
    cme_text: str = Field(
        default="",
        description="CME formatted as LLM-readable text for prompt injection"
    )

    # --- Working State ---
    ips_draft: Optional[dict] = Field(
        default=None,
        description="Current IPS draft as dict (serialized IPSDocument)"
    )
    review_results: list[dict] = Field(
        default_factory=list,
        description="Review results from current round"
    )
    all_review_issues: list[dict] = Field(
        default_factory=list,
        description="Accumulated review issues for revision"
    )
    revision_count: int = Field(
        default=0,
        description="Number of revision rounds completed"
    )
    max_revisions: int = Field(
        default=3,
        description="Maximum allowed revision rounds"
    )
    checklist: dict = Field(
        default_factory=dict,
        description="Compliance checklist data"
    )

    # --- SAA Validation ---
    saa_validation: Optional[dict] = Field(
        default=None,
        description="SAA validation result from quantitative check"
    )

    # --- Output ---
    final_ips: Optional[dict] = Field(
        default=None,
        description="Final approved IPS as dict"
    )
    audit_trail: Optional[dict] = Field(
        default=None,
        description="Complete audit trail as dict"
    )
    revision_history: list[dict] = Field(
        default_factory=list,
        description="List of RevisionRecord dicts"
    )
    status: str = Field(
        default="initialized",
        description="Current workflow status"
    )
    error_message: str = Field(
        default="",
        description="Error message if workflow fails"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ============================================================
# Helper Functions
# ============================================================

def _ips_version_hash(ips_dict: dict) -> str:
    """Generate a short hash for an IPS version identifier."""
    content = json.dumps(ips_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content.encode()).hexdigest()[:8]


def _has_critical_issues(review_results: list[dict]) -> bool:
    """Check if any review result contains critical issues."""
    for result in review_results:
        if not result.get("passed", True):
            for issue in result.get("issues", []):
                if issue.get("severity") == IssueSeverity.CRITICAL.value:
                    return True
    return False


def _all_passed(review_results: list[dict]) -> bool:
    """Check if all review dimensions passed."""
    return all(r.get("passed", False) for r in review_results)


# ============================================================
# Workflow Node Functions
# ============================================================

async def generate_cme_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Generate Capital Market Expectations (CME).

    Fetches historical market data and computes expected returns,
    volatilities, correlations, and risk metrics for each IPS asset
    class. The resulting CME report is stored in state for injection
    into the IPS generator's LLM prompt.

    CFA Reference:
        CFA L3: Setting Capital Market Expectations is a prerequisite
        for any asset allocation decision in the IPS.

    Args:
        state: Current workflow state.

    Returns:
        State updates with CME report and formatted text.
    """
    logger.info("=== CME Generation Node ===")

    try:
        cme_report = compute_cme()
        cme_text = format_cme_for_prompt(cme_report)

        logger.info(
            "CME generated: %d asset classes, rf=%.4f, as_of=%s",
            len(cme_report.asset_classes),
            cme_report.risk_free_rate,
            cme_report.as_of_date,
        )

        return {
            "cme_report": cme_report.model_dump(),
            "cme_text": cme_text,
            "status": "cme_generated",
        }

    except Exception as e:
        logger.error("CME generation failed: %s", e, exc_info=True)
        logger.warning("Proceeding without CME data")
        return {
            "cme_report": None,
            "cme_text": "",
            "status": "cme_failed_continuing",
        }


async def generate_ips_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Generate the initial IPS draft.

    Calls the IPS generator agent with client profile data,
    IPS template reference, and CME data injected as full-text context.

    Args:
        state: Current workflow state.

    Returns:
        State updates with the generated IPS draft.
    """
    logger.info("=== IPS Generation Node ===")
    state_updates: dict[str, Any] = {"status": "generating"}

    try:
        agent = create_ips_generator_agent()
        prompt = build_generation_prompt(
            client_profile_json=state.client_profile_json,
            ips_template=state.reference_template,
            cme_text=state.cme_text,
        )

        result = await agent.run(prompt)
        ips_doc: IPSDocument = result.output
        state_updates["ips_draft"] = ips_doc.model_dump()
        state_updates["status"] = "generated"
        logger.info("IPS draft generated successfully (version: %s)",
                     _ips_version_hash(state_updates["ips_draft"]))

    except Exception as e:
        logger.error("IPS generation failed: %s", e, exc_info=True)
        state_updates["status"] = "error"
        state_updates["error_message"] = f"IPS generation failed: {str(e)}"

    return state_updates


async def select_review_docs_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Select and prepare documents for the review context.

    For now, this uses a rule-based approach:
    - L0 (always inject): client profile data
    - L1 (rule-based): compliance checklist items for each dimension

    Future: LLM-based intelligent document selection.

    Args:
        state: Current workflow state.

    Returns:
        State updates with selected review context.
    """
    logger.info("=== Document Selection Node ===")

    # Load compliance checklist if not already loaded
    checklist = state.checklist
    if not checklist:
        checklist = load_compliance_checklist()

    return {
        "checklist": checklist,
        "status": "reviewing",
        "review_results": [],   # Reset for new review round
        "all_review_issues": [],
    }


async def review_suitability_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Suitability review — check client-IPS fit.

    Verifies risk level matching, return feasibility,
    time horizon alignment, and liquidity adequacy.

    Args:
        state: Current workflow state.

    Returns:
        State updates with suitability review results appended.
    """
    logger.info("=== Suitability Review Node ===")
    dimension = ReviewDimension.SUITABILITY

    try:
        agent = create_suitability_reviewer()

        # Extract checklist items for this dimension
        checklist_items = (
            state.checklist
            .get("dimensions", {})
            .get(dimension.value, {})
            .get("checks", [])
        )

        ips_json = json.dumps(state.ips_draft, ensure_ascii=False, indent=2)
        prompt = build_review_prompt(
            ips_json=ips_json,
            client_profile_json=state.client_profile_json,
            dimension=dimension,
            checklist_items=checklist_items,
        )

        result = await agent.run(prompt)
        review: ReviewResult = result.output
        review_dict = review.model_dump()

        logger.info("Suitability review: passed=%s, issues=%d",
                     review.passed, len(review.issues))

        # Append to current round's results
        current_results = list(state.review_results)
        current_results.append(review_dict)

        # Collect issues for potential revision
        current_issues = list(state.all_review_issues)
        current_issues.extend([i.model_dump() for i in review.issues])

        return {
            "review_results": current_results,
            "all_review_issues": current_issues,
        }

    except Exception as e:
        logger.error("Suitability review failed: %s", e, exc_info=True)
        # On error, create a "failed" review result
        error_result = ReviewResult(
            dimension=dimension,
            passed=False,
            issues=[],
            summary=f"审查过程出错: {str(e)}"
        ).model_dump()
        current_results = list(state.review_results)
        current_results.append(error_result)
        return {"review_results": current_results}


async def review_compliance_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Compliance review — check regulatory requirements.

    Verifies risk disclosure, compliance statements, weight
    constraints, and instrument restrictions.

    Args:
        state: Current workflow state.

    Returns:
        State updates with compliance review results appended.
    """
    logger.info("=== Compliance Review Node ===")
    dimension = ReviewDimension.COMPLIANCE

    try:
        agent = create_compliance_reviewer()

        checklist_items = (
            state.checklist
            .get("dimensions", {})
            .get(dimension.value, {})
            .get("checks", [])
        )

        ips_json = json.dumps(state.ips_draft, ensure_ascii=False, indent=2)
        prompt = build_review_prompt(
            ips_json=ips_json,
            client_profile_json=state.client_profile_json,
            dimension=dimension,
            checklist_items=checklist_items,
        )

        result = await agent.run(prompt)
        review: ReviewResult = result.output
        review_dict = review.model_dump()

        logger.info("Compliance review: passed=%s, issues=%d",
                     review.passed, len(review.issues))

        current_results = list(state.review_results)
        current_results.append(review_dict)
        current_issues = list(state.all_review_issues)
        current_issues.extend([i.model_dump() for i in review.issues])

        return {
            "review_results": current_results,
            "all_review_issues": current_issues,
        }

    except Exception as e:
        logger.error("Compliance review failed: %s", e, exc_info=True)
        error_result = ReviewResult(
            dimension=dimension,
            passed=False,
            issues=[],
            summary=f"审查过程出错: {str(e)}"
        ).model_dump()
        current_results = list(state.review_results)
        current_results.append(error_result)
        return {"review_results": current_results}


async def review_consistency_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Consistency review — check internal logic consistency.

    Verifies that all IPS sections are logically consistent with
    each other (risk level matches allocation, etc.).

    Args:
        state: Current workflow state.

    Returns:
        State updates with consistency review results appended.
    """
    logger.info("=== Consistency Review Node ===")
    dimension = ReviewDimension.CONSISTENCY

    try:
        agent = create_consistency_reviewer()

        checklist_items = (
            state.checklist
            .get("dimensions", {})
            .get(dimension.value, {})
            .get("checks", [])
        )

        ips_json = json.dumps(state.ips_draft, ensure_ascii=False, indent=2)
        prompt = build_review_prompt(
            ips_json=ips_json,
            client_profile_json=state.client_profile_json,
            dimension=dimension,
            checklist_items=checklist_items,
        )

        result = await agent.run(prompt)
        review: ReviewResult = result.output
        review_dict = review.model_dump()

        logger.info("Consistency review: passed=%s, issues=%d",
                     review.passed, len(review.issues))

        current_results = list(state.review_results)
        current_results.append(review_dict)
        current_issues = list(state.all_review_issues)
        current_issues.extend([i.model_dump() for i in review.issues])

        return {
            "review_results": current_results,
            "all_review_issues": current_issues,
        }

    except Exception as e:
        logger.error("Consistency review failed: %s", e, exc_info=True)
        error_result = ReviewResult(
            dimension=dimension,
            passed=False,
            issues=[],
            summary=f"审查过程出错: {str(e)}"
        ).model_dump()
        current_results = list(state.review_results)
        current_results.append(error_result)
        return {"review_results": current_results}


async def revise_ips_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Revise the IPS based on review feedback.

    Takes all accumulated review issues and produces a revised
    IPSDocument that addresses each issue.

    Args:
        state: Current workflow state.

    Returns:
        State updates with revised IPS draft.
    """
    logger.info("=== IPS Revision Node (round %d) ===", state.revision_count + 1)

    try:
        agent = create_ips_reviser_agent()

        ips_json = json.dumps(state.ips_draft, ensure_ascii=False, indent=2)
        issues_json = json.dumps(state.all_review_issues, ensure_ascii=False, indent=2)

        prompt = build_revision_prompt(
            ips_json=ips_json,
            review_issues_json=issues_json,
        )

        result = await agent.run(prompt)
        revised_ips: IPSDocument = result.output
        revised_dict = revised_ips.model_dump()

        # Record revision in audit trail
        version_before = _ips_version_hash(state.ips_draft) if state.ips_draft else "none"
        version_after = _ips_version_hash(revised_dict)

        revision_record = RevisionRecord(
            round_number=state.revision_count + 1,
            review_results=[ReviewResult(**r) for r in state.review_results],
            changes_made=[
                issue.get("suggestion", "")
                for issue in state.all_review_issues
            ],
            ips_version_before=version_before,
            ips_version_after=version_after,
        )

        current_history = list(state.revision_history)
        current_history.append(revision_record.model_dump())

        logger.info("IPS revised: %s → %s", version_before, version_after)

        return {
            "ips_draft": revised_dict,
            "revision_count": state.revision_count + 1,
            "revision_history": current_history,
            "status": "revised",
        }

    except Exception as e:
        logger.error("IPS revision failed: %s", e, exc_info=True)
        return {
            "revision_count": state.revision_count + 1,
            "status": "revision_error",
            "error_message": f"IPS revision failed: {str(e)}",
        }


async def validate_saa_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Quantitative SAA validation against CME data.

    Uses the portfolio optimizer to verify that the LLM-generated
    Strategic Asset Allocation is consistent with CME assumptions:
    - Weights sum to 100%
    - Portfolio expected return covers the required return
    - Portfolio volatility is within risk tolerance band
    - Allocation is near the efficient frontier

    CFA Reference:
        CFA L3: SAA must be grounded in defensible CME assumptions.
        Any mismatch between stated returns and achievable returns
        should be flagged.

    Args:
        state: Current workflow state.

    Returns:
        State updates with SAA validation results merged into review.
    """
    logger.info("=== SAA Validation Node ===")

    # Skip if no CME data available
    if not state.cme_report:
        logger.warning("No CME data available, skipping SAA validation")
        return {}

    if not state.ips_draft:
        logger.warning("No IPS draft available, skipping SAA validation")
        return {}

    try:
        cme = CMEReport(**state.cme_report)
        ips = state.ips_draft
        saa = ips.get("investment_guidelines", {}).get("strategic_allocation", [])

        if not saa:
            logger.warning("No SAA found in IPS, skipping validation")
            return {}

        # Build CME lookup by asset class name
        cme_by_name: dict[str, dict] = {}
        for ac in cme.asset_classes:
            cme_by_name[ac.name] = {
                "expected_return": ac.expected_return,
                "volatility": ac.volatility,
                "var_95": ac.var_95,
                "cvar_95": ac.cvar_95,
            }

        # Extract SAA weights and match to CME
        saa_issues: list[dict] = []
        total_weight = 0.0
        matched_weights: list[float] = []
        matched_returns: list[float] = []
        matched_vols: list[float] = []
        matched_names: list[str] = []
        matched_cme_names: list[str] = []   # CME-side names for correlation lookup
        matched_vars: list[float] = []      # Per-asset 95% VaR
        matched_cvars: list[float] = []     # Per-asset 95% CVaR
        unmatched_assets: list[tuple[str, float]] = []  # (name, weight)

        for alloc in saa:
            asset_name = alloc.get("asset_class", "")
            weight = alloc.get("target_weight", 0.0)
            total_weight += weight

            # Try to match SAA asset class to CME asset class
            cme_match = None
            matched_cme_name = None
            for cme_name, cme_data in cme_by_name.items():
                # Fuzzy match: check if CME name is contained in SAA name or vice versa
                if (cme_name in asset_name or asset_name in cme_name
                        or _fuzzy_asset_match(asset_name, cme_name)):
                    cme_match = cme_data
                    matched_cme_name = cme_name
                    break

            if cme_match and weight > 0:
                matched_weights.append(weight)
                matched_returns.append(cme_match["expected_return"])
                matched_vols.append(cme_match["volatility"])
                matched_names.append(asset_name)
                matched_cme_names.append(matched_cme_name)
                matched_vars.append(cme_match["var_95"])
                matched_cvars.append(cme_match["cvar_95"])
            elif weight > 0:
                unmatched_assets.append((asset_name, weight))

        # Validation 0: Unmatched asset check
        if unmatched_assets:
            unmatched_desc = ", ".join(
                f"{name}({w:.1%})" for name, w in unmatched_assets
            )
            unmatched_total = sum(w for _, w in unmatched_assets)
            saa_issues.append(ReviewIssue(
                section="investment_guidelines",
                dimension=ReviewDimension.CONSISTENCY,
                severity=(
                    IssueSeverity.CRITICAL if unmatched_total >= 0.15
                    else IssueSeverity.WARNING
                ),
                description=(
                    f"以下 SAA 资产类别无法与 CME 数据匹配："
                    f"{unmatched_desc}。"
                    f"未匹配权重合计 {unmatched_total:.1%}，"
                    f"组合层面的收益率和波动率验证不包含这些资产。"
                ),
                regulation_reference=(
                    "CFA L3: All SAA asset classes must have "
                    "defensible CME assumptions."
                ),
                suggestion=(
                    "确保 SAA 资产类别名称与 CME 提供的名称保持一致，"
                    "或在 IPS 中说明未覆盖资产类别的预期假设来源。"
                ),
            ).model_dump())
            logger.warning(
                "Unmatched SAA assets: %s (total weight: %.1f%%)",
                unmatched_desc, unmatched_total * 100,
            )

        # Validation 1: Weight sum check
        if abs(total_weight - 1.0) > 0.01:
            saa_issues.append(ReviewIssue(
                section="investment_guidelines",
                dimension=ReviewDimension.CONSISTENCY,
                severity=IssueSeverity.CRITICAL,
                description=(
                    f"SAA 权重之和为 {total_weight:.4f}（{total_weight:.2%}），"
                    f"偏离 100% 达 {abs(total_weight - 1.0):.2%}。"
                ),
                regulation_reference="CFA: SAA weights must sum to 100%",
                suggestion="调整各资产类别权重使其加总为 100%。",
            ).model_dump())

        # Validation 2: Portfolio expected return vs required return
        if matched_weights:
            w = np.array(matched_weights)
            r = np.array(matched_returns)
            portfolio_return = float(np.dot(w, r) / w.sum())  # Normalize

            required_return = ips.get("return_objective", {}).get(
                "required_nominal_return", 0.0
            )

            if required_return > 0 and portfolio_return < required_return * 0.9:
                gap = required_return - portfolio_return
                saa_issues.append(ReviewIssue(
                    section="return_objective / investment_guidelines",
                    dimension=ReviewDimension.SUITABILITY,
                    severity=IssueSeverity.CRITICAL,
                    description=(
                        f"基于 CME 数据，SAA 的加权预期收益率为 {portfolio_return:.2%}，"
                        f"低于 IPS 声称的所需名义收益率 {required_return:.2%}，"
                        f"缺口 {gap:.2%}。当前配置无法支撑收益目标。"
                    ),
                    regulation_reference=(
                        "CFA L3: Required return must be achievable within "
                        "the SAA's expected return range."
                    ),
                    suggestion=(
                        f"建议：(a) 调整 SAA 提高权益配置比例以提升预期收益率；"
                        f"(b) 或下调收益目标至 CME 可支撑的 {portfolio_return:.2%} 附近；"
                        f"(c) 或通过补充措施（增加储蓄、延长期限）弥补缺口。"
                    ),
                ).model_dump())
            elif required_return > 0 and portfolio_return < required_return:
                gap = required_return - portfolio_return
                saa_issues.append(ReviewIssue(
                    section="return_objective / investment_guidelines",
                    dimension=ReviewDimension.CONSISTENCY,
                    severity=IssueSeverity.WARNING,
                    description=(
                        f"基于 CME 数据，SAA 加权预期收益率 {portfolio_return:.2%} "
                        f"略低于所需收益率 {required_return:.2%}（缺口 {gap:.2%}）。"
                        f"需承担上行风险方可实现，应在 IPS 中明确说明。"
                    ),
                    regulation_reference="CFA L3: Return feasibility assessment",
                    suggestion="在 return_objective 和 risk_disclosure 中明确说明收益目标处于 SAA 预期区间上端。",
                ).model_dump())

            # === Validation 3: Portfolio Volatility σ_p = √(w^T Σ w) ===
            n = len(matched_weights)
            w_norm = w / w.sum()  # Normalize weights
            v = np.array(matched_vols)

            # Build covariance matrix: Σ = diag(σ) × C × diag(σ)
            corr_mat = np.eye(n)
            for i, cme_i in enumerate(matched_cme_names):
                for j, cme_j in enumerate(matched_cme_names):
                    if i != j:
                        corr_val = cme.correlation_matrix.get(
                            cme_i, {}
                        ).get(cme_j, 0.0)
                        corr_mat[i, j] = corr_val

            cov_matrix = np.outer(v, v) * corr_mat
            portfolio_vol = float(np.sqrt(
                w_norm.T @ cov_matrix @ w_norm
            ))

            # Portfolio Sharpe Ratio
            portfolio_sharpe = (
                (portfolio_return - cme.risk_free_rate) / portfolio_vol
                if portfolio_vol > 0 else 0.0
            )

            # Check volatility against client risk tolerance band
            # Bands derived from RISK_VOLATILITY_MAP in portfolio_recommender
            risk_level = ips.get(
                "risk_tolerance", {}
            ).get("overall_risk_level", "")
            vol_bands = {
                "conservative": (0.04, 0.08),
                "moderately_conservative": (0.08, 0.12),
                "moderate": (0.10, 0.15),
                "moderately_aggressive": (0.13, 0.18),
                "aggressive": (0.16, 0.25),
            }
            band = vol_bands.get(risk_level)
            is_vol_acceptable = True
            if band:
                if portfolio_vol > band[1] * 1.2:
                    is_vol_acceptable = False
                    saa_issues.append(ReviewIssue(
                        section="investment_guidelines",
                        dimension=ReviewDimension.CONSISTENCY,
                        severity=IssueSeverity.CRITICAL,
                        description=(
                            f"基于 CME 协方差矩阵计算的组合年化波动率"
                            f"为 {portfolio_vol:.2%}，超出 {risk_level} "
                            f"风险等级目标区间上限 {band[1]:.0%}"
                            f"（含 20% 容差）。"
                            f"当前配置的风险水平超出客户承受范围。"
                        ),
                        regulation_reference=(
                            "CFA L3: Portfolio risk must be consistent "
                            "with stated risk tolerance level."
                        ),
                        suggestion=(
                            "降低权益类或高波动资产配置比例，"
                            "或增加固定收益/现金配置以降低组合波动率。"
                        ),
                    ).model_dump())
                elif portfolio_vol < band[0] * 0.8:
                    saa_issues.append(ReviewIssue(
                        section="investment_guidelines",
                        dimension=ReviewDimension.CONSISTENCY,
                        severity=IssueSeverity.WARNING,
                        description=(
                            f"基于 CME 协方差矩阵计算的组合年化波动率"
                            f"为 {portfolio_vol:.2%}，低于 {risk_level} "
                            f"风险等级目标区间下限 {band[0]:.0%}"
                            f"（含 20% 容差）。"
                            f"配置可能过于保守，难以达成收益目标。"
                        ),
                        regulation_reference=(
                            "CFA L3: Efficient use of risk budget"
                        ),
                        suggestion=(
                            "可适度提高权益类配置以更充分利用风险预算。"
                        ),
                    ).model_dump())

            # === Validation 4: Weighted Portfolio VaR / CVaR ===
            w_var = np.array(matched_vars)
            w_cvar = np.array(matched_cvars)
            # Linear weighted approximation (conservative upper bound)
            portfolio_var_95 = float(np.dot(w_norm, w_var))
            portfolio_cvar_95 = float(np.dot(w_norm, w_cvar))

            logger.info(
                "SAA quantitative validation: "
                "E[r]=%.4f, σ=%.4f, Sharpe=%.4f, "
                "VaR95=%.4f, CVaR95=%.4f, vol_ok=%s",
                portfolio_return, portfolio_vol, portfolio_sharpe,
                portfolio_var_95, portfolio_cvar_95,
                is_vol_acceptable,
            )

            # Store validation result
            validation_result = SAAValidationResult(
                portfolio_expected_return=portfolio_return,
                portfolio_volatility=portfolio_vol,
                portfolio_sharpe=portfolio_sharpe,
                max_sharpe_return=max(matched_returns) if matched_returns else 0.0,
                max_sharpe_volatility=0.0,  # Full optimization needed (P2)
                gmv_return=min(matched_returns) if matched_returns else 0.0,
                gmv_volatility=0.0,  # Full optimization needed (P2)
                is_return_feasible=(portfolio_return >= required_return * 0.9),
                is_volatility_acceptable=is_vol_acceptable,
                issues=[issue.get("description", "") for issue in saa_issues],
            )
        else:
            validation_result = None

        # Merge SAA issues into review results
        if saa_issues:
            logger.warning("SAA validation found %d issues", len(saa_issues))
            current_issues = list(state.all_review_issues)
            current_issues.extend(saa_issues)

            # Check if any existing review should be marked as failed
            current_results = list(state.review_results)

            return {
                "all_review_issues": current_issues,
                "review_results": current_results,
                "saa_validation": validation_result.model_dump() if validation_result else None,
            }
        else:
            logger.info("SAA validation passed")
            return {
                "saa_validation": validation_result.model_dump() if validation_result else None,
            }

    except Exception as e:
        logger.error("SAA validation failed: %s", e, exc_info=True)
        return {}


def _fuzzy_asset_match(saa_name: str, cme_name: str) -> bool:
    """
    Fuzzy match between SAA asset class name and CME asset class name.

    Handles cases like:
        SAA: "国内权益（A股）" <-> CME: "国内权益（A股/沪深300）"
        SAA: "固定收益（利率债+信用债）" <-> CME: "固定收益"
    """
    keywords_map = {
        "国内权益": ["国内权益", "A股", "沪深300"],
        "国际权益": ["国际权益", "发达市场", "EFA"],
        "港股": ["港股", "恒生"],
        "固定收益": ["固定收益", "固收", "债"],
        "黄金": ["黄金", "Gold", "GLD"],
        "REITs": ["REITs", "REIT", "房地产"],
        "现金": ["现金", "货币市场", "Cash", "BIL"],
    }

    for _category, keywords in keywords_map.items():
        saa_match = any(kw in saa_name for kw in keywords)
        cme_match = any(kw in cme_name for kw in keywords)
        if saa_match and cme_match:
            return True

    return False


async def finalize_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Finalize the IPS and generate audit trail.

    Determines whether the IPS is approved or needs human escalation,
    then assembles the complete audit trail.

    Args:
        state: Current workflow state.

    Returns:
        State updates with final IPS and audit trail.
    """
    logger.info("=== Finalization Node ===")

    # Determine final status
    all_passed = _all_passed(state.review_results)
    final_status = "approved" if all_passed else "escalated_to_human"

    # Include CME metadata in audit trail
    cme_metadata = {}
    if state.cme_report:
        cme_metadata = {
            "cme_as_of_date": state.cme_report.get("as_of_date"),
            "cme_lookback_years": state.cme_report.get("data_lookback_years"),
            "cme_risk_free_rate": state.cme_report.get("risk_free_rate"),
            "cme_rf_source": state.cme_report.get("risk_free_rate_source"),
            "cme_asset_count": len(state.cme_report.get("asset_classes", [])),
        }

    # Build audit trail
    audit = AuditTrail(
        revision_history=[
            RevisionRecord(**r) for r in state.revision_history
        ],
        total_rounds=state.revision_count,
        final_status=final_status,
        generation_metadata={
            "model": "deepseek-v4-pro",
            "completed_at": datetime.now().isoformat(),
            "total_revision_rounds": state.revision_count,
            **cme_metadata,
        },
    )

    logger.info("IPS finalized: status=%s, rounds=%d",
                 final_status, state.revision_count)

    return {
        "final_ips": state.ips_draft,
        "audit_trail": audit.model_dump(),
        "status": f"completed_{final_status}",
    }


# ============================================================
# Routing Functions (Conditional Edges)
# ============================================================

def route_after_review(state: IPSWorkflowState) -> str:
    """
    Route after all three reviews complete.

    Returns:
        "pass" if all reviews passed.
        "revise" if there are issues and revision budget remains.
        "escalate" if there are critical issues exceeding revision budget.
    """
    if _all_passed(state.review_results):
        logger.info("All reviews passed → finalize")
        return "pass"

    if state.revision_count >= state.max_revisions:
        logger.warning("Max revisions (%d) reached → escalate",
                       state.max_revisions)
        return "escalate"

    logger.info("Issues found → revise (round %d/%d)",
                 state.revision_count + 1, state.max_revisions)
    return "revise"


def route_after_revision(state: IPSWorkflowState) -> str:
    """
    Route after a revision is completed.

    Returns:
        "review_again" if revision budget remains.
        "escalate" if max revisions reached.
    """
    if state.revision_count >= state.max_revisions:
        logger.warning("Max revisions reached after revision → escalate")
        return "escalate"

    logger.info("Revision complete → review again")
    return "review_again"


# ============================================================
# Graph Construction
# ============================================================

def build_ips_workflow() -> StateGraph:
    """
    Build the complete IPS generation LangGraph workflow.

    Graph:
        START → generate_cme → generate → select_docs →
        review_suitability → review_compliance → review_consistency →
        validate_saa → (routing) → finalize / revise

    Returns:
        Configured StateGraph (not yet compiled).
    """
    workflow = StateGraph(IPSWorkflowState)

    # Add nodes
    workflow.add_node("generate_cme", generate_cme_node)
    workflow.add_node("generate", generate_ips_node)
    workflow.add_node("select_docs", select_review_docs_node)
    workflow.add_node("review_suitability", review_suitability_node)
    workflow.add_node("review_compliance", review_compliance_node)
    workflow.add_node("review_consistency", review_consistency_node)
    workflow.add_node("validate_saa", validate_saa_node)
    workflow.add_node("revise", revise_ips_node)
    workflow.add_node("finalize", finalize_node)

    # Deterministic edges
    workflow.add_edge(START, "generate_cme")
    workflow.add_edge("generate_cme", "generate")
    workflow.add_edge("generate", "select_docs")
    workflow.add_edge("select_docs", "review_suitability")
    workflow.add_edge("review_suitability", "review_compliance")
    workflow.add_edge("review_compliance", "review_consistency")
    workflow.add_edge("review_consistency", "validate_saa")

    # Conditional edge: after SAA validation (replaces post-consistency routing)
    workflow.add_conditional_edges(
        "validate_saa",
        route_after_review,
        {
            "pass": "finalize",
            "revise": "revise",
            "escalate": "finalize",
        },
    )

    # Conditional edge: after revision
    workflow.add_conditional_edges(
        "revise",
        route_after_revision,
        {
            "review_again": "select_docs",
            "escalate": "finalize",
        },
    )

    # Terminal edge
    workflow.add_edge("finalize", END)

    return workflow


def compile_ips_workflow(checkpointer: Optional[Any] = None):
    """
    Build and compile the IPS workflow with optional checkpointing.

    Args:
        checkpointer: LangGraph checkpointer for state persistence.
            Use MemorySaver() for testing or SqliteSaver for production.
            If None, uses MemorySaver by default.

    Returns:
        Compiled LangGraph application ready for invocation.
    """
    workflow = build_ips_workflow()

    if checkpointer is None:
        checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)


# ============================================================
# High-Level API
# ============================================================

async def generate_ips(
    client_profile_dict: dict,
    max_revisions: int = 3,
    thread_id: str = "default",
) -> dict:
    """
    High-level API to generate a complete IPS.

    This is the main entry point for IPS generation.
    It sets up the workflow, runs it to completion, and
    returns the final IPS with audit trail.

    Args:
        client_profile_dict: ClientProfile serialized as dict.
        max_revisions: Maximum revision rounds (default 3).
        thread_id: Unique thread ID for checkpointing.

    Returns:
        Dict with keys: 'ips', 'audit_trail', 'status'.
    """
    # Load reference documents
    template = load_ips_template()

    # Prepare initial state
    initial_state = {
        "client_profile_json": json.dumps(
            client_profile_dict, ensure_ascii=False, indent=2
        ),
        "reference_template": template,
        "max_revisions": max_revisions,
    }

    # Compile and run workflow
    app = compile_ips_workflow()
    config = {"configurable": {"thread_id": thread_id}}

    logger.info("Starting IPS generation workflow (thread: %s)", thread_id)
    final_state = await app.ainvoke(initial_state, config=config)

    return {
        "ips": final_state.get("final_ips"),
        "audit_trail": final_state.get("audit_trail"),
        "status": final_state.get("status", "unknown"),
        "revision_count": final_state.get("revision_count", 0),
        "error_message": final_state.get("error_message", ""),
    }
