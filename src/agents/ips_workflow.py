"""
AI WealthPilot - IPS LangGraph Workflow Engine

Orchestrates the multi-agent IPS generation workflow as a LangGraph
state machine. The workflow follows a Generate → Review → Revise
loop with conditional routing and audit trail tracking.

Workflow Graph:
    START → generate → select_docs → review_suitability →
    review_compliance → review_consistency →
        (all pass) → finalize → END
        (issues)   → revise → select_docs (loop, max 3)
        (max rounds) → finalize (escalate) → END

CFA Reference:
    - CFA L3 PWM: IPS generation and review process
    - CFA L3: Compliance and documentation requirements
"""

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

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

async def generate_ips_node(state: IPSWorkflowState) -> dict[str, Any]:
    """
    Node: Generate the initial IPS draft.

    Calls the IPS generator agent with client profile data and
    the IPS template reference injected as full-text context.

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

    Returns:
        Configured StateGraph (not yet compiled).
    """
    workflow = StateGraph(IPSWorkflowState)

    # Add nodes
    workflow.add_node("generate", generate_ips_node)
    workflow.add_node("select_docs", select_review_docs_node)
    workflow.add_node("review_suitability", review_suitability_node)
    workflow.add_node("review_compliance", review_compliance_node)
    workflow.add_node("review_consistency", review_consistency_node)
    workflow.add_node("revise", revise_ips_node)
    workflow.add_node("finalize", finalize_node)

    # Deterministic edges
    workflow.add_edge(START, "generate")
    workflow.add_edge("generate", "select_docs")
    workflow.add_edge("select_docs", "review_suitability")
    workflow.add_edge("review_suitability", "review_compliance")
    workflow.add_edge("review_compliance", "review_consistency")

    # Conditional edge: after all reviews
    workflow.add_conditional_edges(
        "review_consistency",
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
