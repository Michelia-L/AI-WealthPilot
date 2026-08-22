"""
IPS LangGraph workflow engine.

Orchestrates the multi-agent IPS generation workflow:
START → CME → generate → review(×3) → validate_saa → finalize/revise.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional

import numpy as np
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from src import config
from src.agents.ips_agents import (
    build_generation_prompt,
    build_review_prompt,
    build_revision_prompt,
    create_compliance_reviewer,
    create_consistency_reviewer,
    create_ips_generator_agent,
    create_ips_reviser_agent,
    create_suitability_reviewer,
    load_compliance_checklist,
    load_ips_template,
)
from src.agents.ips_models import (
    AuditTrail,
    IPSDocument,
    IssueSeverity,
    ReviewDimension,
    ReviewIssue,
    ReviewResult,
    RevisionRecord,
)
from src.agents.llm_config import get_llm_config
from src.config import CME_INFLATION_ASSUMPTION
from src.portfolio.cme_engine import compute_cme, format_cme_for_prompt
from src.portfolio.cme_models import CMEReport, SAAValidationResult
from src.portfolio.inflation import resolve_personal_inflation, suggest_inflation_preset

logger = logging.getLogger(__name__)


class TokenBudgetExceeded(RuntimeError):
    """Raised when an IPS workflow run exceeds its per-task token budget (P24).

    Nodes re-raise it past their generic error handling so the overrun
    aborts the whole workflow instead of degrading into revision loops;
    the API task runner turns it into a localized terminal error event.
    """

    def __init__(self, spent: int, budget: int):
        super().__init__(f"IPS token budget exceeded: spent {spent} > budget {budget}")
        self.spent = spent
        self.budget = budget


def _check_token_budget(state: "IPSWorkflowState") -> None:
    """Raise TokenBudgetExceeded when accumulated usage exceeds the budget.

    Checked before every LLM call; the budget is read dynamically from
    src.config so tests can monkeypatch it (same pattern as
    demo_mode.is_demo_mode).
    """
    budget = int(config.LLM_TASK_TOKEN_BUDGET)
    spent = _aggregate_usage(state.llm_usage)["total_tokens"]
    if spent > budget:
        raise TokenBudgetExceeded(spent, budget)


class IPSWorkflowState(BaseModel):
    """
    LangGraph state for the IPS generation workflow.

    This Pydantic model serves as the single source of truth
    for the entire workflow execution. Each node reads from
    and writes to this state.
    """

    # --- Input ---
    client_profile_json: str = Field(
        default="", description="Serialized ClientProfile as JSON string"
    )
    reference_template: str = Field(
        default="", description="IPS structural template full text"
    )

    # --- CME (Capital Market Expectations) ---
    cme_report: Optional[dict] = Field(
        default=None, description="CME report as dict (serialized CMEReport)"
    )
    cme_text: str = Field(
        default="",
        description="CME formatted as LLM-readable text for prompt injection",
    )

    # --- Working State ---
    ips_draft: Optional[dict] = Field(
        default=None, description="Current IPS draft as dict (serialized IPSDocument)"
    )
    review_results: list[dict] = Field(
        default_factory=list, description="Review results from current round"
    )
    all_review_issues: list[dict] = Field(
        default_factory=list, description="Accumulated review issues for revision"
    )
    revision_count: int = Field(
        default=0, description="Number of revision rounds completed"
    )
    max_revisions: int = Field(default=3, description="Maximum allowed revision rounds")
    checklist: dict = Field(
        default_factory=dict, description="Compliance checklist data"
    )

    # --- SAA Validation ---
    saa_validation: Optional[dict] = Field(
        default=None, description="SAA validation result from quantitative check"
    )

    # --- LLM Usage (P24) ---
    llm_usage: list[dict] = Field(
        default_factory=list,
        description="Per-node LLM token usage records (node, requests, "
        "input/output/total tokens), aggregated into the audit trail",
    )

    # --- Output ---
    final_ips: Optional[dict] = Field(
        default=None, description="Final approved IPS as dict"
    )
    audit_trail: Optional[dict] = Field(
        default=None, description="Complete audit trail as dict"
    )
    revision_history: list[dict] = Field(
        default_factory=list, description="List of RevisionRecord dicts"
    )
    status: str = Field(default="initialized", description="Current workflow status")
    error_message: str = Field(
        default="", description="Error message if workflow fails"
    )
    locale: str = Field(
        default="zh",
        description="Language of the generated IPS and review findings (zh/en)",
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


# Bilingual user-facing strings produced inside the workflow (SAA validation
# findings and review error summaries — they surface through the audit trail
# and the SSE error event). zh keeps the pre-i18n wording verbatim; routers
# resolve the request locale into the workflow state, direct callers default
# to zh. Kept here rather than in api/i18n.py because src/ must not import
# from the api/ transport shell (same pattern as src/portfolio/monitoring).
_SAA_STRINGS: dict[str, dict[str, str]] = {
    "unmatched_desc": {
        "zh": "以下 SAA 资产类别无法与 CME 数据匹配：{unmatched_desc}。未匹配权重合计 {unmatched_total:.1%}，组合层面的收益率和波动率验证不包含这些资产。",
        "en": "The following SAA asset classes could not be matched to CME data: {unmatched_desc}. Their combined weight is {unmatched_total:.1%}; these assets are excluded from the portfolio-level return and volatility validation.",
    },
    "unmatched_suggestion": {
        "zh": "确保 SAA 资产类别名称与 CME 提供的名称保持一致，或在 IPS 中说明未覆盖资产类别的预期假设来源。",
        "en": "Align the SAA asset class names with those provided by the CME, or state in the IPS the source of the expected-return assumptions for the uncovered asset classes.",
    },
    "weight_sum_desc": {
        "zh": "SAA 权重之和为 {total:.4f}（{total:.2%}），偏离 100% 达 {deviation:.2%}。",
        "en": "The SAA weights sum to {total:.4f} ({total:.2%}), deviating from 100% by {deviation:.2%}.",
    },
    "weight_sum_suggestion": {
        "zh": "调整各资产类别权重使其加总为 100%。",
        "en": "Adjust the asset-class weights so they sum to 100%.",
    },
    "return_gap_critical_desc": {
        "zh": "基于 CME 数据，SAA 的加权预期收益率为 {portfolio_return:.2%}，低于 IPS 声称的所需名义收益率 {required_return:.2%}，缺口 {gap:.2%}。当前配置无法支撑收益目标。",
        "en": "Based on CME data, the SAA's weighted expected return is {portfolio_return:.2%}, below the IPS's stated required nominal return of {required_return:.2%} — a gap of {gap:.2%}. The current allocation cannot support the return objective.",
    },
    "return_gap_critical_suggestion": {
        "zh": "建议：(a) 调整 SAA 提高权益配置比例以提升预期收益率；(b) 或下调收益目标至 CME 可支撑的 {portfolio_return:.2%} 附近；(c) 或通过补充措施（增加储蓄、延长期限）弥补缺口。",
        "en": "Suggested actions: (a) adjust the SAA toward a higher equity allocation to raise the expected return; (b) or lower the return objective to around the {portfolio_return:.2%} the CME can support; (c) or close the gap through supplementary measures (higher savings, a longer horizon).",
    },
    "return_gap_warning_desc": {
        "zh": "基于 CME 数据，SAA 加权预期收益率 {portfolio_return:.2%} 略低于所需收益率 {required_return:.2%}（缺口 {gap:.2%}）。需承担上行风险方可实现，应在 IPS 中明确说明。",
        "en": "Based on CME data, the SAA's weighted expected return of {portfolio_return:.2%} is slightly below the required return of {required_return:.2%} (a gap of {gap:.2%}). Achieving it requires upside risk; this must be stated explicitly in the IPS.",
    },
    "return_gap_warning_suggestion": {
        "zh": "在 return_objective 和 risk_disclosure 中明确说明收益目标处于 SAA 预期区间上端。",
        "en": "State explicitly in return_objective and risk_disclosure that the return objective sits at the upper end of the SAA's expected range.",
    },
    "vol_above_desc": {
        "zh": "基于 CME 协方差矩阵计算的组合年化波动率为 {portfolio_vol:.2%}，超出 {risk_level} 风险等级目标区间上限 {band_max:.0%}（含 20% 容差）。当前配置的风险水平超出客户承受范围。",
        "en": "The portfolio's annualized volatility computed from the CME covariance matrix is {portfolio_vol:.2%}, above the {risk_level} risk-level target band ceiling of {band_max:.0%} (including a 20% tolerance). The allocation's risk level exceeds what the client can bear.",
    },
    "vol_above_suggestion": {
        "zh": "降低权益类或高波动资产配置比例，或增加固定收益/现金配置以降低组合波动率。",
        "en": "Reduce the allocation to equities or other high-volatility assets, or increase fixed-income/cash allocations to lower the portfolio volatility.",
    },
    "vol_below_desc": {
        "zh": "基于 CME 协方差矩阵计算的组合年化波动率为 {portfolio_vol:.2%}，低于 {risk_level} 风险等级目标区间下限 {band_min:.0%}（含 20% 容差）。配置可能过于保守，难以达成收益目标。",
        "en": "The portfolio's annualized volatility computed from the CME covariance matrix is {portfolio_vol:.2%}, below the {risk_level} risk-level target band floor of {band_min:.0%} (including a 20% tolerance). The allocation may be too conservative to achieve the return objective.",
    },
    "vol_below_suggestion": {
        "zh": "可适度提高权益类配置以更充分利用风险预算。",
        "en": "Consider a moderately higher equity allocation to make fuller use of the risk budget.",
    },
    "saa_summary": {
        "zh": "SAA 量化验证发现 {n_issues} 个问题（含 {n_critical} 个 critical），详见 issues 列表。",
        "en": "Quantitative SAA validation found {n_issues} issue(s) ({n_critical} critical); see the issues list for details.",
    },
    "review_error_summary": {
        "zh": "审查过程出错: {error}",
        "en": "The review process failed: {error}",
    },
    # Node exception messages: surface in state.error_message and leak into the
    # SSE error event (api/routers/ips.py prefers it over the i18n fallback).
    "generation_error": {
        "zh": "IPS 生成失败: {error}",
        "en": "IPS generation failed: {error}",
    },
    "revision_error": {
        "zh": "IPS 修订失败: {error}",
        "en": "IPS revision failed: {error}",
    },
}


def _t(key: str, locale: str, **fmt) -> str:
    """Render one bilingual workflow string; unknown locales fall back to zh."""
    entry = _SAA_STRINGS[key]
    template = entry.get(locale) or entry["zh"]
    return template.format(**fmt) if fmt else template


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
    """Check if all review dimensions passed.

    An empty review list is treated as a fail-safe: returning True would
    auto-approve an IPS that was never actually reviewed. Gating sites
    (finalize_node, route_after_review) escalate such cases to a human.
    """
    return bool(review_results) and all(r.get("passed", False) for r in review_results)


async def generate_cme_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: generate Capital Market Expectations for prompt injection."""
    logger.info("=== CME Generation Node ===")

    # Client-segment inflation: elderly clients spend out of a healthcare-
    # tilted basket (CPI-E style), so their CME inflation assumption is
    # adjusted upward from the generic-CPI base before prompt injection.
    try:
        profile = (
            json.loads(state.client_profile_json) if state.client_profile_json else {}
        )
    except (json.JSONDecodeError, TypeError):
        profile = {}
    inflation = resolve_personal_inflation(
        CME_INFLATION_ASSUMPTION, suggest_inflation_preset(profile.get("age"))
    )

    try:
        cme_report, cache_status = compute_cme(inflation=inflation)
        cme_text = format_cme_for_prompt(cme_report)

        logger.info(
            "CME ready: %d asset classes, rf=%.4f, inflation=%.4f, as_of=%s, source=%s",
            len(cme_report.asset_classes),
            cme_report.risk_free_rate,
            cme_report.inflation_assumption,
            cme_report.as_of_date,
            cache_status,
        )

        cme_dict = cme_report.model_dump()
        cme_dict["_cache_status"] = cache_status

        return {
            "cme_report": cme_dict,
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


def _usage_entry(node: str, result: Any) -> dict[str, Any]:
    """Build one per-node LLM token usage record from an agent run result.

    ``result.usage`` is a property on pydantic-ai's AgentRunResult; totals
    are aggregated in ``finalize_node`` for the audit trail (P24).
    """
    usage = result.usage
    return {
        "node": node,
        "requests": usage.requests,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


async def generate_ips_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: generate the initial IPS draft via LLM."""
    logger.info("=== IPS Generation Node ===")
    state_updates: dict[str, Any] = {"status": "generating"}

    try:
        _check_token_budget(state)
        agent = create_ips_generator_agent(locale=state.locale)
        prompt = build_generation_prompt(
            client_profile_json=state.client_profile_json,
            ips_template=state.reference_template,
            cme_text=state.cme_text,
            locale=state.locale,
        )

        result = await agent.run(prompt)
        ips_doc: IPSDocument = result.output
        state_updates["ips_draft"] = ips_doc.model_dump()
        state_updates["llm_usage"] = [
            *state.llm_usage,
            _usage_entry("generate", result),
        ]
        state_updates["status"] = "generated"
        logger.info(
            "IPS draft generated successfully (version: %s)",
            _ips_version_hash(state_updates["ips_draft"]),
        )

    except TokenBudgetExceeded:
        raise

    except Exception as e:
        logger.error("IPS generation failed: %s", e, exc_info=True)
        state_updates["status"] = "error"
        state_updates["error_message"] = _t(
            "generation_error", state.locale, error=str(e)
        )

    return state_updates


async def select_review_docs_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: load compliance checklist and reset review state for new round."""
    logger.info("=== Document Selection Node ===")

    checklist = state.checklist
    if not checklist:
        checklist = load_compliance_checklist()

    return {
        "checklist": checklist,
        "status": "reviewing",
        "review_results": [],
        "all_review_issues": [],
    }


# Map dimension → agent factory for the parameterized review node
_REVIEWER_FACTORIES = {
    ReviewDimension.SUITABILITY: create_suitability_reviewer,
    ReviewDimension.COMPLIANCE: create_compliance_reviewer,
    ReviewDimension.CONSISTENCY: create_consistency_reviewer,
}


async def _run_review_node(
    state: IPSWorkflowState,
    dimension: ReviewDimension,
) -> dict[str, Any]:
    """Shared implementation for all review dimension nodes.

    Args:
        state: Current workflow state.
        dimension: Which review dimension to execute.

    Returns:
        State updates with review results and issues appended.
    """
    logger.info("=== %s Review Node ===", dimension.value.title())

    try:
        _check_token_budget(state)
        agent = _REVIEWER_FACTORIES[dimension](locale=state.locale)

        checklist_items = (
            state.checklist.get("dimensions", {})
            .get(dimension.value, {})
            .get("checks", [])
        )

        ips_json = json.dumps(state.ips_draft, ensure_ascii=False, indent=2)
        prompt = build_review_prompt(
            ips_json=ips_json,
            client_profile_json=state.client_profile_json,
            dimension=dimension,
            checklist_items=checklist_items,
            locale=state.locale,
        )

        result = await agent.run(prompt)
        review: ReviewResult = result.output

        logger.info(
            "%s review: passed=%s, issues=%d",
            dimension.value.title(),
            review.passed,
            len(review.issues),
        )

        current_results = list(state.review_results)
        current_results.append(review.model_dump())

        current_issues = list(state.all_review_issues)
        current_issues.extend([i.model_dump() for i in review.issues])

        return {
            "review_results": current_results,
            "all_review_issues": current_issues,
            "llm_usage": [
                *state.llm_usage,
                _usage_entry(f"review_{dimension.value}", result),
            ],
        }

    except TokenBudgetExceeded:
        raise

    except Exception as e:
        logger.error("%s review failed: %s", dimension.value.title(), e, exc_info=True)
        error_result = ReviewResult(
            dimension=dimension,
            passed=False,
            issues=[],
            summary=_t("review_error_summary", state.locale, error=e),
        ).model_dump()
        current_results = list(state.review_results)
        current_results.append(error_result)
        return {"review_results": current_results}


async def review_suitability_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: suitability review — check client-IPS fit."""
    return await _run_review_node(state, ReviewDimension.SUITABILITY)


async def review_compliance_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: compliance review — check regulatory requirements."""
    return await _run_review_node(state, ReviewDimension.COMPLIANCE)


async def review_consistency_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: consistency review — check internal logic consistency."""
    return await _run_review_node(state, ReviewDimension.CONSISTENCY)


async def revise_ips_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: revise the IPS based on accumulated review feedback."""
    logger.info("=== IPS Revision Node (round %d) ===", state.revision_count + 1)

    try:
        _check_token_budget(state)
        agent = create_ips_reviser_agent(locale=state.locale)

        ips_json = json.dumps(state.ips_draft, ensure_ascii=False, indent=2)
        issues_json = json.dumps(state.all_review_issues, ensure_ascii=False, indent=2)

        prompt = build_revision_prompt(
            ips_json=ips_json,
            review_issues_json=issues_json,
            locale=state.locale,
        )

        result = await agent.run(prompt)
        revised_ips: IPSDocument = result.output
        revised_dict = revised_ips.model_dump()

        version_before = (
            _ips_version_hash(state.ips_draft) if state.ips_draft else "none"
        )
        version_after = _ips_version_hash(revised_dict)

        revision_record = RevisionRecord(
            round_number=state.revision_count + 1,
            review_results=[ReviewResult(**r) for r in state.review_results],
            changes_made=[
                issue.get("suggestion", "") for issue in state.all_review_issues
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
            "llm_usage": [
                *state.llm_usage,
                _usage_entry(f"revise_r{state.revision_count + 1}", result),
            ],
            "status": "revised",
        }

    except TokenBudgetExceeded:
        raise

    except Exception as e:
        logger.error("IPS revision failed: %s", e, exc_info=True)
        return {
            "revision_count": state.revision_count + 1,
            "status": "revision_error",
            "error_message": _t("revision_error", state.locale, error=str(e)),
        }


async def validate_saa_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: quantitative SAA validation against CME data."""
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

        # Extract SAA weights and match to CME.
        # saa_issues keeps live ReviewIssue objects (not dicts) so we can
        # synthesize a ReviewResult below that makes SAA critical findings
        # influence routing — otherwise route_after_review only sees the
        # three LLM reviewer results and would silently approve an IPS whose
        # SAA fails weight-sum / volatility / return-feasibility checks (#A‑1).
        saa_issues: list[ReviewIssue] = []
        total_weight = 0.0
        matched_weights: list[float] = []
        matched_returns: list[float] = []
        matched_vols: list[float] = []
        matched_names: list[str] = []
        matched_cme_names: list[str] = []  # CME-side names for correlation lookup
        matched_vars: list[float] = []  # Per-asset 95% VaR
        matched_cvars: list[float] = []  # Per-asset 95% CVaR
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
                if (
                    cme_name in asset_name
                    or asset_name in cme_name
                    or _fuzzy_asset_match(asset_name, cme_name)
                ):
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
            saa_issues.append(
                ReviewIssue(
                    section="investment_guidelines",
                    dimension=ReviewDimension.CONSISTENCY,
                    severity=(
                        IssueSeverity.CRITICAL
                        if unmatched_total >= 0.15
                        else IssueSeverity.WARNING
                    ),
                    description=_t(
                        "unmatched_desc",
                        state.locale,
                        unmatched_desc=unmatched_desc,
                        unmatched_total=unmatched_total,
                    ),
                    regulation_reference=(
                        "All SAA asset classes must have defensible CME assumptions."
                    ),
                    suggestion=_t("unmatched_suggestion", state.locale),
                )
            )
            logger.warning(
                "Unmatched SAA assets: %s (total weight: %.1f%%)",
                unmatched_desc,
                unmatched_total * 100,
            )

        # Validation 1: Weight sum check
        if abs(total_weight - 1.0) > 0.01:
            saa_issues.append(
                ReviewIssue(
                    section="investment_guidelines",
                    dimension=ReviewDimension.CONSISTENCY,
                    severity=IssueSeverity.CRITICAL,
                    description=_t(
                        "weight_sum_desc",
                        state.locale,
                        total=total_weight,
                        deviation=abs(total_weight - 1.0),
                    ),
                    regulation_reference="SAA weights must sum to 100%",
                    suggestion=_t("weight_sum_suggestion", state.locale),
                )
            )

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
                saa_issues.append(
                    ReviewIssue(
                        section="return_objective / investment_guidelines",
                        dimension=ReviewDimension.SUITABILITY,
                        severity=IssueSeverity.CRITICAL,
                        description=_t(
                            "return_gap_critical_desc",
                            state.locale,
                            portfolio_return=portfolio_return,
                            required_return=required_return,
                            gap=gap,
                        ),
                        regulation_reference=(
                            "Required return must be achievable within "
                            "the SAA's expected return range."
                        ),
                        suggestion=_t(
                            "return_gap_critical_suggestion",
                            state.locale,
                            portfolio_return=portfolio_return,
                        ),
                    )
                )
            elif required_return > 0 and portfolio_return < required_return:
                gap = required_return - portfolio_return
                saa_issues.append(
                    ReviewIssue(
                        section="return_objective / investment_guidelines",
                        dimension=ReviewDimension.CONSISTENCY,
                        severity=IssueSeverity.WARNING,
                        description=_t(
                            "return_gap_warning_desc",
                            state.locale,
                            portfolio_return=portfolio_return,
                            required_return=required_return,
                            gap=gap,
                        ),
                        regulation_reference="Return feasibility assessment",
                        suggestion=_t("return_gap_warning_suggestion", state.locale),
                    )
                )

            n = len(matched_weights)
            w_norm = w / w.sum()  # Normalize weights
            v = np.array(matched_vols)

            # Build covariance matrix: Σ = diag(σ) × C × diag(σ)
            corr_mat = np.eye(n)
            for i, cme_i in enumerate(matched_cme_names):
                for j, cme_j in enumerate(matched_cme_names):
                    if i != j:
                        corr_val = cme.correlation_matrix.get(cme_i, {}).get(cme_j, 0.0)
                        corr_mat[i, j] = corr_val

            cov_matrix = np.outer(v, v) * corr_mat
            portfolio_vol = float(np.sqrt(w_norm.T @ cov_matrix @ w_norm))

            # Portfolio Sharpe Ratio
            portfolio_sharpe = (
                (portfolio_return - cme.risk_free_rate) / portfolio_vol
                if portfolio_vol > 0
                else 0.0
            )

            # Check volatility against client risk tolerance band
            # Canonical per-level bands live in config.RISK_VOLATILITY_BANDS
            # (P25 single source, shared with the recommender and prompts).
            risk_level = ips.get("risk_tolerance", {}).get("overall_risk_level", "")
            band = config.RISK_VOLATILITY_BANDS.get(risk_level)
            is_vol_acceptable = True
            if band:
                if portfolio_vol > band[1] * 1.2:
                    is_vol_acceptable = False
                    saa_issues.append(
                        ReviewIssue(
                            section="investment_guidelines",
                            dimension=ReviewDimension.CONSISTENCY,
                            severity=IssueSeverity.CRITICAL,
                            description=_t(
                                "vol_above_desc",
                                state.locale,
                                portfolio_vol=portfolio_vol,
                                risk_level=risk_level,
                                band_max=band[1],
                            ),
                            regulation_reference=(
                                "Portfolio risk must be consistent "
                                "with stated risk tolerance level."
                            ),
                            suggestion=_t("vol_above_suggestion", state.locale),
                        )
                    )
                elif portfolio_vol < band[0] * 0.8:
                    saa_issues.append(
                        ReviewIssue(
                            section="investment_guidelines",
                            dimension=ReviewDimension.CONSISTENCY,
                            severity=IssueSeverity.WARNING,
                            description=_t(
                                "vol_below_desc",
                                state.locale,
                                portfolio_vol=portfolio_vol,
                                risk_level=risk_level,
                                band_min=band[0],
                            ),
                            regulation_reference=("Efficient use of risk budget"),
                            suggestion=_t("vol_below_suggestion", state.locale),
                        )
                    )

            w_var = np.array(matched_vars)
            w_cvar = np.array(matched_cvars)
            # Linear weighted approximation (conservative upper bound)
            portfolio_var_95 = float(np.dot(w_norm, w_var))
            portfolio_cvar_95 = float(np.dot(w_norm, w_cvar))

            logger.info(
                "SAA quantitative validation: "
                "E[r]=%.4f, σ=%.4f, Sharpe=%.4f, "
                "VaR95=%.4f, CVaR95=%.4f, vol_ok=%s",
                portfolio_return,
                portfolio_vol,
                portfolio_sharpe,
                portfolio_var_95,
                portfolio_cvar_95,
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
                issues=[issue.description for issue in saa_issues],
            )
        else:
            validation_result = None

        # Merge SAA issues into review state. Crucially, also synthesize a
        # ReviewResult and append it to review_results so that
        # route_after_review's _all_passed check reflects SAA findings —
        # otherwise CRITICAL SAA issues (weight sum ≠ 100%, vol out of band,
        # return infeasible) are silently dropped and the IPS is approved
        # despite failing quantitative validation (#A‑1).
        if saa_issues:
            logger.warning("SAA validation found %d issues", len(saa_issues))
            current_issues = list(state.all_review_issues)
            current_issues.extend([i.model_dump() for i in saa_issues])

            current_results = list(state.review_results)
            current_results.append(
                ReviewResult(
                    dimension=ReviewDimension.CONSISTENCY,
                    passed=False,
                    issues=saa_issues,
                    summary=_t(
                        "saa_summary",
                        state.locale,
                        n_issues=len(saa_issues),
                        n_critical=sum(
                            1
                            for i in saa_issues
                            if i.severity == IssueSeverity.CRITICAL
                        ),
                    ),
                ).model_dump()
            )

            return {
                "all_review_issues": current_issues,
                "review_results": current_results,
                "saa_validation": validation_result.model_dump()
                if validation_result
                else None,
            }
        else:
            logger.info("SAA validation passed")
            return {
                "saa_validation": validation_result.model_dump()
                if validation_result
                else None,
            }

    except Exception as e:
        logger.error("SAA validation failed: %s", e, exc_info=True)
        return {}


def _fuzzy_asset_match(saa_name: str, cme_name: str) -> bool:
    """Fuzzy match SAA asset class name against CME asset class name.

    Both names are resolved against the shared ``ASSET_CLASS_ALIASES``
    table (P25 config single source; bilingual aliases — CME asset names
    are always Chinese, SAA names follow the generation locale): hitting
    the same category key counts as a match. Read via the config module
    attribute so tests can monkeypatch the table.
    """
    for aliases in config.ASSET_CLASS_ALIASES.values():
        saa_match = any(alias in saa_name for alias in aliases)
        cme_match = any(alias in cme_name for alias in aliases)
        if saa_match and cme_match:
            return True

    return False


def _aggregate_usage(records: list[dict]) -> dict[str, Any]:
    """Aggregate per-node token usage records into an audit-trail summary (P24)."""
    keys = ("requests", "input_tokens", "output_tokens", "total_tokens")
    by_node: dict[str, dict[str, int]] = {}
    for rec in records:
        stats = by_node.setdefault(rec["node"], dict.fromkeys(keys, 0))
        for key in keys:
            stats[key] += int(rec.get(key) or 0)
    totals = {key: sum(stats[key] for stats in by_node.values()) for key in keys}
    return {**totals, "by_node": by_node}


async def finalize_node(state: IPSWorkflowState) -> dict[str, Any]:
    """Node: finalize the IPS and assemble audit trail."""
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
            "cme_cache_status": state.cme_report.get("_cache_status", "unknown"),
        }

    # Build audit trail
    audit = AuditTrail(
        revision_history=[RevisionRecord(**r) for r in state.revision_history],
        total_rounds=state.revision_count,
        final_status=final_status,
        generation_metadata={
            "model": get_llm_config().model,
            "completed_at": datetime.now().isoformat(),
            "total_revision_rounds": state.revision_count,
            "token_usage": _aggregate_usage(state.llm_usage),
            **cme_metadata,
        },
    )

    logger.info(
        "IPS finalized: status=%s, rounds=%d", final_status, state.revision_count
    )

    return {
        "final_ips": state.ips_draft,
        "audit_trail": audit.model_dump(),
        "status": f"completed_{final_status}",
    }


def route_after_review(state: IPSWorkflowState) -> str:
    """Route after all reviews: 'pass', 'revise', or 'escalate'."""
    if _all_passed(state.review_results):
        logger.info("All reviews passed → finalize")
        return "pass"

    if state.revision_count >= state.max_revisions:
        logger.warning("Max revisions (%d) reached → escalate", state.max_revisions)
        return "escalate"

    logger.info(
        "Issues found → revise (round %d/%d)",
        state.revision_count + 1,
        state.max_revisions,
    )
    return "revise"


def route_after_revision(state: IPSWorkflowState) -> str:
    """Route after revision: 'review_again' or 'escalate'."""
    if state.revision_count >= state.max_revisions:
        logger.warning("Max revisions reached after revision → escalate")
        return "escalate"

    logger.info("Revision complete → review again")
    return "review_again"


def build_ips_workflow() -> StateGraph:
    """Build the complete IPS generation LangGraph workflow."""
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
    """Build and compile the IPS workflow with optional checkpointing."""
    workflow = build_ips_workflow()

    if checkpointer is None:
        checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)


async def generate_ips(
    client_profile_dict: dict,
    max_revisions: int = 3,
    thread_id: str = "default",
    locale: str = "zh",
) -> dict:
    """High-level API: generate a complete IPS with audit trail.

    ``locale`` selects the language of the generated IPS, review findings,
    and SAA validation messages ("zh" / "en").
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
        "locale": locale,
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
        "token_usage": _aggregate_usage(final_state.get("llm_usage", [])),
    }
