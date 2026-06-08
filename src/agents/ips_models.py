"""
AI WealthPilot - IPS Data Models (Pydantic Schemas)

Defines the complete, CFA-aligned Investment Policy Statement (IPS)
data models using Pydantic BaseModel. These schemas guarantee
structured, validated LLM outputs for the IPS generator workflow.

CFA Reference:
    - CFA L3 Private Wealth Management: Investment Policy Statement
    - CFA L3: RRTTLLU constraint framework
    - CFA L3: Risk Tolerance = min(Ability, Willingness)
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# Enums — Risk & Review Classification
# ============================================================

class RiskToleranceLevel(str, Enum):
    """Risk tolerance level enumeration aligned with CFA framework."""
    CONSERVATIVE = "conservative"
    MODERATELY_CONSERVATIVE = "moderately_conservative"
    MODERATE = "moderate"
    MODERATELY_AGGRESSIVE = "moderately_aggressive"
    AGGRESSIVE = "aggressive"


class IssueSeverity(str, Enum):
    """Severity level for review issues."""
    CRITICAL = "critical"   # Must fix before approval
    WARNING = "warning"     # Should fix, but not blocking
    INFO = "info"           # Optional improvement


class ReviewDimension(str, Enum):
    """Review dimension enumeration."""
    SUITABILITY = "suitability"    # Client-IPS fit
    COMPLIANCE = "compliance"      # Regulatory compliance
    CONSISTENCY = "consistency"    # Internal logic consistency


# ============================================================
# IPS Section Models — CFA Framework
# ============================================================

class GoalReturnRequirement(BaseModel):
    """
    Per-goal return requirement for multi-objective portfolios.

    CFA Reference:
        CFA L3 PWM: Each client goal may have distinct required return,
        time horizon, and priority. The IPS should decompose the aggregate
        required return into per-goal requirements when multiple goals exist.
    """
    goal_name: str = Field(
        description="Goal name, e.g. 'Retirement', 'Child Education', 'House Purchase'"
    )
    target_amount: float = Field(
        description="Target amount needed for this goal in base currency"
    )
    current_allocation: float = Field(
        default=0.0,
        description="Capital currently allocated toward this goal"
    )
    time_horizon_years: int = Field(
        description="Years until this goal needs to be funded"
    )
    priority: str = Field(
        description="Goal priority: 'high', 'medium', or 'low'"
    )
    required_return: float = Field(
        description="Required annual return for this specific goal, "
                    "e.g. 0.08 for 8%. Derived via TVM: r = (FV/PV)^(1/n) - 1"
    )
    calculation_basis: str = Field(
        default="",
        description="Derivation formula for this goal's required return"
    )


class ReturnObjective(BaseModel):
    """
    IPS Section: Return Objectives.

    CFA Reference:
        Quantify required return to meet client goals.
        Distinguish nominal vs real returns.
        When multiple goals exist, decompose into per-goal requirements.
    """
    required_nominal_return: float = Field(
        description="Required nominal annual return rate, e.g. 0.08 for 8%. "
                    "When multiple goals exist, this is the capital-weighted composite rate."
    )
    required_real_return: float = Field(
        description="Required real annual return rate after inflation"
    )
    return_calculation_basis: str = Field(
        description="Derivation logic for the required return"
    )
    return_objective_narrative: str = Field(
        description="Narrative explanation of return objectives"
    )
    goal_level_requirements: list[GoalReturnRequirement] = Field(
        default_factory=list,
        description="Per-goal return requirements for multi-objective portfolios. "
                    "Each goal specifies its own target amount, time horizon, and required return."
    )
    return_methodology: str = Field(
        default="",
        description="Calculation methodology used to derive return requirements, "
                    "e.g. 'TVM: r = (FV/PV)^(1/n) - 1' or 'Annuity: PMT-based'"
    )


class RiskToleranceAssessment(BaseModel):
    """
    IPS Section: Risk Tolerance.

    CFA Dual-Track Assessment:
        - Ability: objective, based on financial facts
        - Willingness: subjective, based on psychological comfort
        - Final = min(Ability, Willingness)
    """
    ability_assessment: str = Field(
        description="Objective risk ability assessment narrative"
    )
    willingness_assessment: str = Field(
        description="Subjective risk willingness assessment narrative"
    )
    conflict_resolution: Optional[str] = Field(
        default=None,
        description="Conflict resolution explanation (only when ability != willingness)"
    )
    overall_risk_level: RiskToleranceLevel = Field(
        description="Final risk tolerance classification"
    )
    risk_narrative: str = Field(
        description="Comprehensive risk tolerance narrative"
    )


class TimeHorizonStage(BaseModel):
    """A single stage in a multi-stage time horizon."""
    name: str = Field(description="Stage name, e.g. 'Accumulation' or 'Distribution'")
    years: int = Field(description="Duration of this stage in years")
    description: str = Field(description="Description of this stage's characteristics")


class TimeHorizonAnalysis(BaseModel):
    """
    IPS Section: Time Horizon.

    CFA Reference:
        Longer horizons generally permit higher equity allocation.
        Multi-stage horizons require distinct strategies per stage.
    """
    stages: list[TimeHorizonStage] = Field(
        description="Investment stages with durations"
    )
    overall_horizon_years: int = Field(
        description="Total investment horizon in years"
    )
    horizon_narrative: str = Field(
        description="Time horizon analysis narrative"
    )


class LiquidityConstraint(BaseModel):
    """
    IPS Section: Liquidity Constraints.

    CFA Reference:
        Ensure portfolio can meet cash needs without forced liquidation.
    """
    immediate_needs: float = Field(
        description="Cash needed within 12 months"
    )
    ongoing_needs: float = Field(
        description="Annual ongoing cash withdrawal needs"
    )
    emergency_reserve_months: int = Field(
        description="Recommended emergency fund in months of expenses"
    )
    liquidity_narrative: str = Field(
        description="Liquidity constraint analysis narrative"
    )


class TaxConstraint(BaseModel):
    """
    IPS Section: Tax Constraints.

    CFA Reference:
        Tax status affects asset location and after-tax returns.
    """
    tax_status: str = Field(
        description="Client tax status: taxable, tax-exempt, or tax-deferred"
    )
    tax_considerations: str = Field(
        description="Specific tax optimization strategies"
    )
    tax_narrative: str = Field(
        description="Tax constraint analysis narrative"
    )


class LegalConstraint(BaseModel):
    """
    IPS Section: Legal & Regulatory Constraints.

    CFA Reference:
        External legal constraints on investment decisions.
    """
    applicable_regulations: list[str] = Field(
        description="List of applicable regulations"
    )
    legal_narrative: str = Field(
        description="Legal constraint analysis narrative"
    )


class UniqueCircumstance(BaseModel):
    """
    IPS Section: Unique Circumstances.

    CFA Reference:
        Any factor not covered by other constraints that
        affects investment decisions.
    """
    esg_preferences: Optional[str] = Field(
        default=None,
        description="ESG investment preferences if any"
    )
    sector_restrictions: list[str] = Field(
        default_factory=list,
        description="Excluded sectors or industries"
    )
    concentrated_positions: Optional[str] = Field(
        default=None,
        description="Concentrated position risks if any"
    )
    other_circumstances: str = Field(
        default="",
        description="Other unique factors"
    )
    unique_narrative: str = Field(
        description="Unique circumstances narrative"
    )


class AssetAllocationTarget(BaseModel):
    """A single asset class allocation target with range constraints."""
    asset_class: str = Field(description="Asset class name")
    target_weight: float = Field(description="Target allocation weight, e.g. 0.30 for 30%")
    min_weight: float = Field(description="Minimum allowed weight")
    max_weight: float = Field(description="Maximum allowed weight")
    rationale: str = Field(description="Allocation rationale for this asset class")


class InvestmentGuideline(BaseModel):
    """
    IPS Section: Investment Guidelines & Policy.

    CFA Reference:
        Translates objectives and constraints into actionable allocation.
    """
    strategic_allocation: list[AssetAllocationTarget] = Field(
        description="Strategic Asset Allocation (SAA) targets"
    )
    permitted_instruments: list[str] = Field(
        description="Permitted investment instruments"
    )
    prohibited_instruments: list[str] = Field(
        description="Prohibited investment instruments"
    )
    rebalancing_policy: str = Field(
        description="Rebalancing policy and trigger conditions"
    )
    guideline_narrative: str = Field(
        description="Investment guidelines narrative"
    )


class BenchmarkSpec(BaseModel):
    """Benchmark specification for an asset class."""
    asset_class: str = Field(description="Asset class name")
    benchmark: str = Field(description="Benchmark index name")


class MonitoringPolicy(BaseModel):
    """
    IPS Section: Monitoring & Evaluation.

    CFA Reference:
        Ongoing monitoring ensures portfolio stays aligned with IPS.
    """
    review_frequency: str = Field(
        description="Review frequency, e.g. 'quarterly' or 'semi-annual'"
    )
    benchmarks: list[BenchmarkSpec] = Field(
        description="Performance benchmarks per asset class"
    )
    rebalancing_triggers: list[str] = Field(
        description="Conditions that trigger rebalancing"
    )
    monitoring_narrative: str = Field(
        description="Monitoring and evaluation narrative"
    )


class CurrencyPolicy(BaseModel):
    """
    Currency management policy for multi-currency portfolios.

    CFA Reference:
        CFA L3: Currency management policy, base currency definition,
        and currency hedging strategy for foreign exposure.
    """
    base_currency: str = Field(default="CNY", description="Client's base/reporting currency")
    foreign_exposure_pct: float = Field(default=0.0, description="Estimated foreign currency exposure as pct of portfolio")
    hedging_strategy: str = Field(default="", description="Currency hedging approach, e.g. 'Unhedged', 'Partial hedge via forward contracts'")
    hedging_ratio: float = Field(default=0.0, description="Target hedge ratio for foreign exposure")
    currency_narrative: str = Field(default="", description="Narrative on currency risk and management")


# ============================================================
# Top-Level IPS Document Model
# ============================================================

class IPSDocument(BaseModel):
    """
    Complete Investment Policy Statement (IPS).

    This is the top-level structured output for the IPS generator.
    Each field maps to a CFA-defined IPS section, ensuring the LLM
    produces a complete, validated document with no missing sections.

    CFA Reference:
        CFA L3 PWM: IPS is the governing document for the
        investment management relationship.
    """
    # Metadata
    client_name: str = Field(description="Client full name")
    prepared_by: str = Field(
        default="AI WealthPilot IPS Generator",
        description="Who prepared this IPS"
    )
    preparation_date: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d"),
        description="IPS preparation date"
    )
    version: str = Field(default="1.0", description="IPS version")

    # IPS Sections (CFA Framework)
    executive_summary: str = Field(
        description="Executive summary of the IPS (max 300 chars)"
    )
    client_background: str = Field(
        description="Client personal and financial background"
    )
    return_objective: ReturnObjective = Field(
        description="Return objectives section"
    )
    risk_tolerance: RiskToleranceAssessment = Field(
        description="Risk tolerance assessment section"
    )
    time_horizon: TimeHorizonAnalysis = Field(
        description="Time horizon analysis section"
    )
    liquidity: LiquidityConstraint = Field(
        description="Liquidity constraints section"
    )
    tax: TaxConstraint = Field(
        description="Tax constraints section"
    )
    legal: LegalConstraint = Field(
        description="Legal and regulatory constraints section"
    )
    unique_circumstances: UniqueCircumstance = Field(
        description="Unique circumstances section"
    )
    investment_guidelines: InvestmentGuideline = Field(
        description="Investment guidelines and policy section"
    )
    monitoring: MonitoringPolicy = Field(
        description="Monitoring and evaluation section"
    )
    currency_policy: Optional[CurrencyPolicy] = Field(
        default=None,
        description="Currency management policy (required when foreign exposure > 10%)"
    )

    # Compliance
    risk_disclosure: str = Field(
        description="Risk disclosure statement"
    )
    compliance_statement: str = Field(
        description="Compliance and legal disclaimer"
    )


# ============================================================
# Review Data Models
# ============================================================

class ReviewIssue(BaseModel):
    """A single issue found during IPS review."""
    section: str = Field(
        description="Which IPS section has the issue"
    )
    dimension: ReviewDimension = Field(
        description="Review dimension this issue belongs to"
    )
    severity: IssueSeverity = Field(
        description="Issue severity level"
    )
    description: str = Field(
        description="Detailed description of the issue"
    )
    regulation_reference: Optional[str] = Field(
        default=None,
        description="Cited regulation or CFA principle if applicable"
    )
    suggestion: str = Field(
        description="Suggested fix for the issue"
    )


class ReviewResult(BaseModel):
    """
    Structured output of a review agent.

    Each review agent (suitability, compliance, consistency)
    returns one ReviewResult per invocation.
    """
    dimension: ReviewDimension = Field(
        description="Which dimension was reviewed"
    )
    passed: bool = Field(
        description="Whether this dimension passed review"
    )
    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="List of issues found (empty if passed)"
    )
    summary: str = Field(
        description="Overall review summary for this dimension"
    )


# ============================================================
# Audit Trail Models
# ============================================================

class RevisionRecord(BaseModel):
    """Audit trail record for a single revision round."""
    round_number: int = Field(description="Revision round number (1-based)")
    review_results: list[ReviewResult] = Field(
        description="Review results that triggered this revision"
    )
    changes_made: list[str] = Field(
        description="List of changes made in this revision"
    )
    ips_version_before: str = Field(
        description="IPS version identifier before revision"
    )
    ips_version_after: str = Field(
        description="IPS version identifier after revision"
    )


class AuditTrail(BaseModel):
    """
    Complete audit trail for the IPS generation process.

    Records every review and revision step for regulatory compliance
    and transparency requirements.
    """
    revision_history: list[RevisionRecord] = Field(
        default_factory=list,
        description="Chronological list of revision records"
    )
    total_rounds: int = Field(
        default=0,
        description="Total number of revision rounds executed"
    )
    final_status: str = Field(
        default="pending",
        description="Final status: 'approved' or 'escalated_to_human'"
    )
    generation_metadata: dict = Field(
        default_factory=dict,
        description="Model name, token usage, timestamps, etc."
    )
