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
    profile_id: Optional[int] = Field(
        default=None,
        description="Client profile id; applies the profile's risk-level group "
        "caps to the selected portfolio (classic MVO only)",
    )


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


class RiskConstraintsInfo(BaseModel):
    """Risk-level group caps resolved from a client profile, when applied."""

    profile_id: int
    profile_name: str
    risk_level: str
    caps: dict[str, float]


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
    risk_constraints: Optional[RiskConstraintsInfo] = None


class PortfolioTaskCreatedResponse(BaseModel):
    """202 body for POST /portfolio/optimize/async (Phase 5c)."""

    task_id: str


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
    """Manual risk scores (0 = not assessed). On save, non-empty
    questionnaire answers take precedence and these are overwritten by
    the derived scores (see profile_convert.payload_to_data)."""

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


class QuestionnaireOption(BaseModel):
    """One answer option; score lets the client preview live — the server
    still recomputes authoritatively from the submitted answers."""

    key: str
    label: str = Field(description="Bilingual 'English / 中文' label")
    score: int = Field(ge=1, le=5)


class QuestionnaireQuestion(BaseModel):
    key: str
    question: str = Field(description="Bilingual 'English / 中文' question text")
    options: list[QuestionnaireOption]


class QuestionnaireResponse(BaseModel):
    """The 9-question dual-track risk questionnaire (src/agents/profiler.py):
    5 objective ability questions + 4 subjective willingness questions."""

    ability: list[QuestionnaireQuestion]
    willingness: list[QuestionnaireQuestion]


class BiasItem(BaseModel):
    """One detected behavioral bias (src BehavioralBias dataclass)."""

    bias_type: str
    name: str = Field(description="Bilingual 'English / 中文' label")
    description: str
    severity: str = Field(description="high / medium / low")
    recommendation: str


class ProfileCompareEntry(BaseModel):
    """One profile's column in the comparison, plus its biases."""

    id: int
    name: str
    financial_summary: dict[str, Any] = Field(
        description="src financial_summary: income/net_worth/savings/risk…"
    )
    bias_count: int
    biases: list[BiasItem]


class ProfileCompareResponse(BaseModel):
    """src compare_profiles result keyed back to SQLite profile ids."""

    comparison_date: str
    insights: list[str] = Field(description="Bilingual analytical insights")
    profiles: list[ProfileCompareEntry]


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
    # 与列表一致的摘要字段，便于查看页直接渲染头部信息
    client_name: str = ""
    version: str = "?"
    risk_level: str = "?"
    status: str = "?"
    revision_rounds: int = 0
    saved_at: str = ""


# ---------------------------------------------------------------------------
# Portfolio monitoring & rebalancing (P10 — src/portfolio/monitoring.py)
# ---------------------------------------------------------------------------


class MonitoringPortfolioMetrics(BaseModel):
    """Portfolio-level metrics under one weight set (target or drifted)."""

    expected_return: Optional[float] = None
    volatility: Optional[float] = None
    sharpe: Optional[float] = None


class MonitoringHoldingMetrics(BaseModel):
    """CME metrics attached to one SAA holding (null when unmapped)."""

    expected_return: float
    volatility: float = Field(description="Blended vol preferred, historical fallback")
    sharpe: float
    max_drawdown: float
    var_95: float
    cvar_95: float


class MonitoringHolding(BaseModel):
    key: Optional[str] = Field(
        default=None, description="IPS_ASSET_CLASS_TICKERS key; None when unmapped"
    )
    name: str = Field(description="SAA asset class display name")
    ticker: Optional[str] = None
    target_weight: float
    min_weight: float
    max_weight: float
    drifted_weight: Optional[float] = None
    drift_pp: Optional[float] = None
    band_status: Literal["within", "above", "below", "unknown"]
    period_return: Optional[float] = None
    metrics: Optional[MonitoringHoldingMetrics] = None


class MonitoringTrade(BaseModel):
    key: Optional[str] = None
    name: str
    action: Literal["buy", "sell"]
    weight_pp: float = Field(
        description="target - drifted as a decimal; positive = buy, negative = sell"
    )


class MonitoringRebalance(BaseModel):
    needed: bool
    trades: list[MonitoringTrade] = Field(default_factory=list)


class MonitoringResponse(BaseModel):
    document_id: str
    client_name: str
    saved_at: str
    as_of: str
    cme_cache_status: str = Field(
        description="CME provenance: 'fresh' | 'cached' | 'stale' | 'fallback'"
    )
    portfolio: MonitoringPortfolioMetrics
    drifted_portfolio: MonitoringPortfolioMetrics
    holdings: list[MonitoringHolding]
    rebalance: MonitoringRebalance
    notes: list[str] = Field(default_factory=list)


class RebalanceAdviceRequest(BaseModel):
    """Request body for POST /monitoring/advice (SSE rebalancing advice)."""

    document_id: str = Field(description="IPS document id (filename stem)")
    profile_id: Optional[int] = Field(
        default=None,
        description="Optional SQLite profile id; personalizes the advice",
    )


# ---------------------------------------------------------------------------
# Portfolio backtesting & stress testing (P13 — src/portfolio/backtest.py)
# ---------------------------------------------------------------------------


class BacktestMetrics(BaseModel):
    """Risk/return metrics for one NAV series (portfolio or benchmark)."""

    total_return: float
    cagr: float
    ann_volatility: float
    sharpe: Optional[float] = Field(
        default=None, description="Null when annualized volatility is zero"
    )
    max_drawdown: float
    max_drawdown_peak: Optional[str] = None
    max_drawdown_trough: Optional[str] = None
    best_day: float
    worst_day: float


class BacktestBenchmark(BaseModel):
    name: str = Field(description="e.g. '60% SPY / 40% AGG'")
    metrics: BacktestMetrics


class BacktestYearlyReturn(BaseModel):
    year: int
    portfolio: float
    benchmark: float


class BacktestStressResult(BaseModel):
    scenario: str
    window: str = Field(description="Fixed window, e.g. '2020-02-19~2020-03-23'")
    portfolio_return: float
    benchmark_return: float


class BacktestResponse(BaseModel):
    document_id: str
    client_name: str
    period: str
    as_of: str = Field(description="Last trading day of the aligned price panel")
    weights: dict[str, float] = Field(
        description="Display name -> actual backtest weight (sparse assets dropped, renormalized)"
    )
    metrics: BacktestMetrics
    benchmark: BacktestBenchmark
    yearly: list[BacktestYearlyReturn] = Field(default_factory=list)
    equity_chart: dict[str, Any] = Field(description="Plotly figure JSON")
    drawdown_chart: dict[str, Any] = Field(description="Plotly figure JSON")
    stress: list[BacktestStressResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    """Personalized allocation from src portfolio_recommender (P12)."""

    profile_id: int
    profile_name: str
    risk_level: str
    as_of: datetime
    allocation: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    rationale: str
