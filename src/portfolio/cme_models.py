"""
AI WealthPilot - Capital Market Expectations (CME) Data Models

Pydantic schemas for structured CME reports used by the IPS generator.
CME provides the quantitative foundation (expected returns, volatilities,
correlations) that the LLM uses to construct data-driven asset allocations.

CFA Reference:
    - CFA L3: Setting Capital Market Expectations
    - CFA L3: Asset Allocation — integrating CME into IPS
    - CFA L3: Forecasting Asset Class Returns (historical, survey, model-based)
"""

from typing import Optional

from pydantic import BaseModel, Field


class AssetClassCME(BaseModel):
    """
    Capital Market Expectations for a single asset class.

    Contains historical-based return and risk metrics computed from
    market data, used as quantitative inputs for IPS asset allocation.

    CFA Reference:
        CFA L3: Each asset class in the IPS should have explicit
        expected return, volatility, and correlation assumptions.
    """
    name: str = Field(
        description="Asset class display name, e.g. '国内权益（A股/沪深300）'"
    )
    ticker: str = Field(
        description="Proxy ticker used for data, e.g. '000300.SS'"
    )
    expected_return: float = Field(
        description="Annualized expected return (arithmetic mean), e.g. 0.08 for 8%"
    )
    volatility: float = Field(
        ge=0,
        description="Annualized volatility (std dev), e.g. 0.22 for 22%. "
                    "Must be non-negative: a negative value is mathematically "
                    "invalid and breaks the covariance/sqrt chain downstream."
    )
    sharpe_ratio: float = Field(
        description="Historical Sharpe ratio"
    )
    max_drawdown: float = Field(
        description="Maximum drawdown (negative), e.g. -0.30 for -30%"
    )
    var_95: float = Field(
        description="95% daily Value at Risk (positive number)"
    )
    cvar_95: float = Field(
        description="95% daily Conditional VaR / Expected Shortfall"
    )
    data_points: int = Field(
        default=0,
        description="Number of trading days used in calculation"
    )

    # --- Forward-looking volatility fields
    implied_volatility: Optional[float] = Field(
        default=None,
        description="Market-implied annualized volatility from options/IV index "
                    "(e.g. VIX). None if no reliable IV proxy exists for this "
                    "asset class."
    )
    iv_source: Optional[str] = Field(
        default=None,
        description="Source of implied volatility, e.g. 'CBOE VIX (^VIX)' "
                    "or 'ICE BofAML MOVE (^MOVE)'"
    )
    blended_volatility: Optional[float] = Field(
        default=None,
        description="Bayesian-blended volatility: τ × σ_implied + (1-τ) × σ_hist. "
                    "Falls back to historical vol when IV is unavailable."
    )
    volatility_regime: Optional[str] = Field(
        default=None,
        description="Qualitative regime label: 'low', 'normal', 'elevated', 'high'. "
                    "Derived from IV/HV ratio."
    )


class CMEReport(BaseModel):
    """
    Complete Capital Market Expectations report.

    This is the top-level structured output of the CME engine.
    It aggregates per-asset-class expectations, correlation matrix,
    and macro assumptions into a single document that gets injected
    into the IPS generator's LLM context.

    CFA Reference:
        CFA L3: CME is a prerequisite for any asset allocation decision.
        The IPS must reference explicit, defensible market assumptions.
    """
    as_of_date: str = Field(
        description="Data as-of date, e.g. '2026-06-05'"
    )
    data_lookback_years: int = Field(
        description="Number of years of historical data used"
    )
    risk_free_rate: float = Field(
        description="Current annualized risk-free rate (dynamically fetched)"
    )
    risk_free_rate_source: str = Field(
        default="unknown",
        description="Source of risk-free rate: 'fred', 'yfinance', or 'static_fallback'"
    )
    inflation_assumption: float = Field(
        description="Long-term inflation rate assumption, e.g. 0.025 for 2.5%"
    )
    asset_classes: list[AssetClassCME] = Field(
        description="CME data for each asset class"
    )
    correlation_matrix: dict[str, dict[str, float]] = Field(
        description="Pairwise correlation matrix as nested dict {name: {name: corr}}"
    )
    methodology_notes: str = Field(
        default="",
        description="Notes on data sources, limitations, and methodology"
    )

    # --- Implied Volatility metadata
    iv_blending_tau: float = Field(
        default=0.5,
        description="Bayesian blending parameter τ: weight on implied volatility. "
                    "0.0 = pure historical, 1.0 = pure implied."
    )
    iv_data_available: bool = Field(
        default=False,
        description="Whether any implied volatility data was successfully fetched."
    )


class SAAValidationResult(BaseModel):
    """
    Result of quantitative SAA validation against CME data.

    Checks whether the LLM-generated SAA is consistent with
    the CME assumptions and lies near the efficient frontier.
    """
    portfolio_expected_return: float = Field(
        description="Weighted portfolio expected return based on CME"
    )
    portfolio_volatility: float = Field(
        description="Portfolio volatility based on CME covariance"
    )
    portfolio_sharpe: float = Field(
        description="Portfolio Sharpe ratio"
    )
    max_sharpe_return: float = Field(
        description="Expected return of the max-Sharpe (tangency) portfolio"
    )
    max_sharpe_volatility: float = Field(
        description="Volatility of the max-Sharpe portfolio"
    )
    gmv_return: float = Field(
        description="Expected return of the Global Minimum Variance portfolio"
    )
    gmv_volatility: float = Field(
        description="Volatility of the GMV portfolio"
    )
    is_return_feasible: bool = Field(
        description="Whether required return is achievable on the frontier"
    )
    is_volatility_acceptable: bool = Field(
        description="Whether portfolio vol is within risk tolerance band"
    )
    issues: list[str] = Field(
        default_factory=list,
        description="List of validation issue descriptions"
    )
