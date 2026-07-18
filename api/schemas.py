"""
Response schemas for the AI WealthPilot API.

CME models are imported directly from the core (src.portfolio.cme_models)
so the API contract and the engine can never drift apart.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from src.portfolio.cme_models import CMEReport


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str


class AssetInfo(BaseModel):
    """Static display metadata for one asset in the universe."""

    name: str
    category: str
    color: str
    currency: str
    symbol: str


class UniverseResponse(BaseModel):
    assets: dict[str, AssetInfo]


class Quote(BaseModel):
    ticker: str
    name: str
    category: str
    price: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    # Display metadata copied from ASSET_UNIVERSE so the frontend can format
    # prices (currency symbol, decimal rules) without a second request.
    currency: str = "USD"
    symbol: str = ""
    color: str = "#D4AF37"


class QuotesResponse(BaseModel):
    as_of: datetime
    quotes: list[Quote]


class RiskFreeRateResponse(BaseModel):
    rate: float = Field(
        description="Annualized risk-free rate as a decimal, e.g. 0.045 for 4.5%"
    )
    as_of: datetime


class CMEResponse(BaseModel):
    cache_status: str = Field(
        description="Provenance of the report: 'fresh' | 'cached' | 'stale' | 'fallback'"
    )
    report: CMEReport


class RiskStat(BaseModel):
    """Per-asset risk/return statistics over the analysis window."""

    ticker: str
    name: str
    ann_return: float = Field(description="Annualized mean return (decimal)")
    ann_volatility: float = Field(description="Annualized volatility (decimal)")
    sharpe: float
    max_drawdown: float = Field(description="Largest peak-to-trough loss (negative decimal)")
    var_95: float = Field(description="Daily 95% Value at Risk (positive decimal)")


class AnalyticsResponse(BaseModel):
    """
    Aggregated dashboard analytics for a ticker set and time window.

    price_chart / correlation_chart are full Plotly figures serialized via
    plotly's fig.to_json() (numpy arrays encoded as base64 typed arrays,
    decoded natively by plotly.js on the client).
    """

    period: str
    tickers: list[str]
    as_of: datetime
    price_chart: dict[str, Any]
    correlation_chart: Optional[dict[str, Any]] = None
    stats: list[RiskStat] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Portfolio optimization
# ---------------------------------------------------------------------------


class AssetClassInfo(BaseModel):
    """An entry of DEFAULT_ASSET_CLASSES (optimization universe)."""

    ticker: str
    name: str


class AssetClassesResponse(BaseModel):
    asset_classes: dict[str, AssetClassInfo]


class BLViewInput(BaseModel):
    """One Black-Litterman investor view (asset keys, not display names)."""

    view_type: Literal["absolute", "relative"]
    asset_long: str = Field(description="Asset class key the view is bullish on")
    asset_short: Optional[str] = Field(
        default=None, description="Required for relative views"
    )
    expected_return: float = Field(
        description="Annualized decimal (0.15 = 15%); spread for relative views"
    )
    confidence: float = Field(default=70, ge=0, le=100)


class BLConfigInput(BaseModel):
    tau: float = 0.025
    delta: float = 2.5
    market_weights: Optional[dict[str, float]] = Field(
        default=None,
        description="Market-cap weights keyed by asset class key; None = equal weights",
    )
    views: list[BLViewInput] = Field(default_factory=list)


class OptimizeRequest(BaseModel):
    assets: list[str] = Field(
        default=["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"],
        description="DEFAULT_ASSET_CLASSES keys (>= 2)",
    )
    period: Literal["1y", "2y", "3y", "5y", "10y"] = "5y"
    risk_free_rate: Optional[float] = Field(
        default=None, description="Annualized decimal; None = fetch dynamically"
    )
    method: Literal["mvo", "resampled", "black-litterman"] = "mvo"
    mode: Literal["max-sharpe", "min-vol"] = "max-sharpe"
    allow_short: bool = False
    n_simulations: int = Field(default=200, ge=50, le=2000)
    bl: Optional[BLConfigInput] = None


class PortfolioResult(BaseModel):
    weights: dict[str, float]
    ann_return: float
    ann_volatility: float
    sharpe: float
    success: bool = True
    weight_std: Optional[dict[str, float]] = Field(
        default=None, description="Resampled MVO only: weight dispersion per asset"
    )


class AssetStat(BaseModel):
    key: str
    ticker: str
    name: str
    ann_return: float
    ann_volatility: float


class BLInsight(BaseModel):
    """Equilibrium (implied) vs posterior returns, per asset name."""

    equilibrium_returns: dict[str, float]
    posterior_returns: dict[str, float]


class OptimizeResponse(BaseModel):
    as_of: datetime
    params: dict[str, Any] = Field(description="Effective parameters used")
    selected: PortfolioResult
    max_sharpe: PortfolioResult
    min_vol: PortfolioResult
    frontier_chart: dict[str, Any]
    allocation_chart: dict[str, Any]
    asset_stats: list[AssetStat]
    bl: Optional[BLInsight] = None


# ---------------------------------------------------------------------------
# Retirement planning (two-phase Monte Carlo)
# ---------------------------------------------------------------------------


class RetirementRequest(BaseModel):
    current_age: int = Field(default=30, ge=18, le=80)
    retirement_age: int = Field(default=60, ge=19, le=90)
    life_expectancy: int = Field(default=85, ge=30, le=110)
    current_savings: float = Field(default=100000, ge=0)
    annual_savings: float = Field(default=50000, ge=0)
    desired_annual_income: float = Field(default=80000, ge=0)
    inflation_rate: float = Field(default=0.025, ge=0, le=0.2)
    expected_return: float = Field(default=0.07, ge=-0.1, le=0.4)
    volatility: float = Field(default=0.15, ge=0.01, le=0.8)
    n_simulations: int = Field(default=10000, ge=1000, le=50000)


class TerminalStats(BaseModel):
    """Terminal portfolio value distribution at the end of accumulation."""

    mean: float
    median: float
    p5: float
    p25: float
    p75: float
    p95: float


class DepletionAnalysis(BaseModel):
    never_depleted_pct: float = Field(description="Share of paths that never hit zero")
    depleted_within_10y_pct: float = Field(
        description="Share of paths depleted within the first 10 distribution years"
    )
    median_depletion_year: Optional[float] = Field(
        default=None, description="Median depletion year among depleted paths"
    )


class SensitivityRow(BaseModel):
    annual_savings: float
    is_current: bool
    survival_rate: float
    median_at_retirement: float


class RetirementResponse(BaseModel):
    as_of: datetime
    params: dict[str, Any]
    survival_rate: float = Field(
        description="Fraction of distribution paths that never hit zero"
    )
    accumulation_years: int
    distribution_years: int
    terminal_at_retirement: TerminalStats
    accumulation_chart: dict[str, Any]
    distribution_chart: dict[str, Any]
    depletion: DepletionAnalysis
    sensitivity: list[SensitivityRow]


# ---------------------------------------------------------------------------
# Client profiles (Phase 3c — SQLite persistence)
# ---------------------------------------------------------------------------

MARITAL_STATUSES = ("single", "married", "divorced", "widowed")
TAX_STATUSES = ("tax-exempt", "taxable", "tax-deferred")
GOAL_PRIORITIES = ("high", "medium", "low")


class FinancialSituationInput(BaseModel):
    annual_income: float = Field(default=0.0, ge=0)
    annual_expenses: float = Field(default=0.0, ge=0)
    investable_assets: float = Field(default=0.0, ge=0)
    total_liabilities: float = Field(default=0.0, ge=0)
    emergency_fund_months: float = Field(default=0.0, ge=0)


class InvestmentGoalInput(BaseModel):
    name: str = Field(default="", max_length=100)
    target_amount: float = Field(default=0.0, ge=0)
    years: int = Field(default=0, ge=0, le=80)
    priority: Literal["high", "medium", "low"] = "medium"


class RiskScoresInput(BaseModel):
    """Manual risk scores (0 = not assessed). The questionnaire that derives
    these from answers migrates in a later phase; answers are stored raw."""

    ability_score: float = Field(default=0.0, ge=0, le=5)
    willingness_score: float = Field(default=0.0, ge=0, le=5)


class ProfilePayload(BaseModel):
    """Editable client profile — mirrors src.agents.profiler.ClientProfile."""

    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=18, le=100)
    marital_status: Literal["single", "married", "divorced", "widowed"] = "single"
    dependents: int = Field(default=0, ge=0, le=20)
    financial: FinancialSituationInput = Field(default_factory=FinancialSituationInput)
    goals: list[InvestmentGoalInput] = Field(default_factory=list)
    time_horizon_years: int = Field(default=10, ge=1, le=60)
    is_multi_stage: bool = False
    liquidity_needs: float = Field(default=0.0, ge=0)
    tax_status: Literal["tax-exempt", "taxable", "tax-deferred"] = "taxable"
    esg_preference: bool = False
    sector_restrictions: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)
    risk_scores: RiskScoresInput = Field(default_factory=RiskScoresInput)
    ability_answers: dict[str, str] = Field(default_factory=dict)
    willingness_answers: dict[str, str] = Field(default_factory=dict)


class ProfileSummary(BaseModel):
    id: int
    name: str
    age: int
    risk_level: str
    updated_at: str


class ProfileListResponse(BaseModel):
    profiles: list[ProfileSummary]


class ProfileDerived(BaseModel):
    """Metrics derived from src/ dataclass properties (single source of truth)."""

    net_worth: float
    annual_savings: float
    savings_rate: float
    debt_to_asset_ratio: Optional[float] = None  # None = +inf (debt, no assets)
    final_risk_score: float
    tolerance_level: str


class ProfileDetailResponse(BaseModel):
    id: int
    created_at: str
    updated_at: str
    profile: dict[str, Any] = Field(description="Full stored ClientProfile dict")
    derived: ProfileDerived


class ProfileImportResponse(BaseModel):
    files_found: int
    imported: int
    skipped: int


# ---------------------------------------------------------------------------
# AI Advisor (Phase 4a — SSE streaming advisory reports)
# ---------------------------------------------------------------------------


class AdvisorStatusResponse(BaseModel):
    configured: bool = Field(description="Whether DEEPSEEK_API_KEY is set")
    model: str


class AdvisorStreamRequest(BaseModel):
    profile_id: int = Field(description="SQLite profile id to advise on")


class SaveReportRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, description="Report body in Markdown")
    model: str = ""
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=2000)


class ReportSummary(BaseModel):
    report_id: str
    client_name: str
    model: str
    generated_at: str
    total_tokens: int
    has_notes: bool


class ReportListResponse(BaseModel):
    reports: list[ReportSummary]


class ReportDetailResponse(ReportSummary):
    content: str
    prompt_tokens: int
    completion_tokens: int
    notes: str


# ---------------------------------------------------------------------------
# IPS workflow (Phase 4b — async generation tasks)
# ---------------------------------------------------------------------------


class IpsGenerateRequest(BaseModel):
    profile_id: int
    max_revisions: int = Field(default=3, ge=0, le=5)


class IpsTaskCreatedResponse(BaseModel):
    task_id: str
    profile_id: int


class IpsDocumentSummary(BaseModel):
    document_id: str
    client_name: str
    version: str
    risk_level: str
    status: str
    revision_rounds: int
    saved_at: str


class IpsListResponse(BaseModel):
    documents: list[IpsDocumentSummary]


class IpsDetailResponse(BaseModel):
    document_id: str
    markdown: str
    metadata: dict[str, Any]
