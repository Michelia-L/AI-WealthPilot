"""
Retirement planning endpoint — two-phase Monte Carlo simulation.

POST /api/retirement/simulate wraps MonteCarloSimulator.retirement_planning
(accumulation with savings injection, then distribution with inflation-
adjusted withdrawals) and mirrors the Streamlit planner's depletion and
sensitivity analyses. Runs are seeded (42) so identical parameters yield
identical results — reproducibility beats novelty for financial plans.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from api.db import ProfileRecord, get_session
from api.routers.market import _fig_json
from api.i18n import get_request_locale, msg
from api.schemas import (
    CmeSuggestionResponse,
    DepletionAnalysis,
    RetirementRequest,
    RetirementResponse,
    SensitivityRow,
    StrategyComparison,
    TerminalStats,
)
from src.portfolio.cme_engine import (
    compute_cme,
    reference_allocation_for_level,
    reference_portfolio_suggestion,
)
from src.portfolio.inflation import resolve_personal_inflation
from src.portfolio.simulator import MonteCarloSimulator
from src.visualization.charts import plot_monte_carlo_paths

router = APIRouter(prefix="/retirement", tags=["retirement"])

SEED = 42  # Fixed seed for reproducibility (same as the Streamlit planner)
SAVINGS_MULTIPLIERS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
SENSITIVITY_SIMULATIONS = 5_000
CHART_DISPLAY_PATHS = 200


@router.get(
    "/cme-suggestion",
    response_model=CmeSuggestionResponse,
    summary="CME-derived μ/σ suggestion for the retirement planner",
)
def cme_suggestion(
    request: Request,
    profile_id: Optional[int] = None,
    session: Session = Depends(get_session),
) -> CmeSuggestionResponse:
    """Reference-portfolio expected return and volatility from the CME report.

    With ``profile_id``, the reference allocation is keyed to the client's
    risk tolerance level (derived from RISK_LEVEL_CAPS); without it, the
    static balanced allocation is used. No extra market fetches — computed
    from the cached CMEReport's blended expected returns, blended
    volatilities and correlation matrix.
    """
    locale = get_request_locale(request)

    allocation: Optional[dict[str, float]] = None
    risk_level: Optional[str] = None
    if profile_id is not None:
        record = session.get(ProfileRecord, profile_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=msg("common.profile_not_found", locale, id=profile_id),
            )
        if record.risk_level:
            allocation = reference_allocation_for_level(record.risk_level)
            if allocation is not None:
                risk_level = record.risk_level

    try:
        report, cache_status = compute_cme()
    except RuntimeError:
        raise HTTPException(
            status_code=502, detail=msg("portfolio.cme_unavailable", locale)
        ) from None
    suggestion = reference_portfolio_suggestion(report, allocation)
    if suggestion is None:
        raise HTTPException(
            status_code=502, detail=msg("portfolio.cme_unavailable", locale)
        )
    return CmeSuggestionResponse(
        expected_return=suggestion["expected_return"],
        volatility=suggestion["volatility"],
        allocation=suggestion["allocation"],
        as_of_date=report.as_of_date,
        cache_status=cache_status,
        risk_level=risk_level,
    )


def _distribution_inflation(req: RetirementRequest) -> float:
    """Effective distribution-phase inflation from the client's segment.

    Retirees spend out of an elderly basket (CPI-E style), so the
    distribution phase may carry a higher rate than the accumulation
    phase's generic CPI; no preset means the legacy single rate.
    """
    return resolve_personal_inflation(
        base_rate=req.inflation_rate,
        preset=req.inflation_preset,
        custom_rate=req.custom_inflation_rate,
    )


def _run_plan(req: RetirementRequest, annual_savings: float, n_simulations: int) -> dict:
    sim = MonteCarloSimulator(
        expected_return=req.expected_return,
        volatility=req.volatility,
        n_simulations=n_simulations,
        seed=SEED,
    )
    return sim.retirement_planning(
        current_age=req.current_age,
        retirement_age=req.retirement_age,
        life_expectancy=req.life_expectancy,
        current_savings=req.current_savings,
        annual_savings=annual_savings,
        desired_annual_income=req.desired_annual_income,
        inflation_rate=req.inflation_rate,
        distribution_inflation_rate=_distribution_inflation(req),
        withdrawal_strategy=req.withdrawal_strategy,
        guardrail_band=req.guardrail_band,
        guardrail_adjust=req.guardrail_adjust,
    )


def _depletion_analysis(dist_paths: np.ndarray) -> DepletionAnalysis:
    """Mirror the Streamlit planner's depletion metrics (vectorized)."""
    n_sims, n_periods = dist_paths.shape
    hits_zero = dist_paths <= 0
    ever_depleted = hits_zero.any(axis=1)
    first_depleted = hits_zero.argmax(axis=1)  # index of first year <= 0
    depletion_years = np.where(ever_depleted, first_depleted, n_periods)

    depleted_mask = depletion_years < n_periods
    return DepletionAnalysis(
        never_depleted_pct=float(np.mean(depletion_years >= n_periods)),
        depleted_within_10y_pct=float(np.mean(depletion_years <= 10)),
        median_depletion_year=(
            float(np.median(depletion_years[depleted_mask]))
            if depleted_mask.any()
            else None
        ),
    )


@router.post(
    "/simulate",
    response_model=RetirementResponse,
    summary="Two-phase retirement Monte Carlo (accumulation → distribution)",
)
def simulate(req: RetirementRequest) -> RetirementResponse:
    if req.retirement_age <= req.current_age:
        raise HTTPException(
            status_code=422, detail="retirement_age must be greater than current_age."
        )
    if req.life_expectancy <= req.retirement_age:
        raise HTTPException(
            status_code=422, detail="life_expectancy must be greater than retirement_age."
        )

    result = _run_plan(req, req.annual_savings, req.n_simulations)
    accum = result["accumulation"]
    dist_paths = result["distribution_paths"]

    accum_fig = plot_monte_carlo_paths(
        accum.paths, n_display=CHART_DISPLAY_PATHS, percentiles=True
    )
    dist_fig = plot_monte_carlo_paths(
        dist_paths, n_display=CHART_DISPLAY_PATHS, percentiles=True, goal_amount=0
    )

    sensitivity = [
        SensitivityRow(
            annual_savings=float(int(req.annual_savings * mult)),
            is_current=mult == 1.0,
            survival_rate=float(scenario["survival_rate"]),
            median_at_retirement=float(scenario["accumulation"].median_terminal),
        )
        for mult in SAVINGS_MULTIPLIERS
        for scenario in [
            _run_plan(req, int(req.annual_savings * mult), SENSITIVITY_SIMULATIONS)
        ]
    ]

    params: dict[str, Any] = req.model_dump()
    params["seed"] = SEED
    # Echo the effective distribution-phase rate so the UI can show the
    # client-segment adjustment actually applied (None → same as base).
    params["distribution_inflation_rate"] = _distribution_inflation(req)

    # Guardrails vs fixed on identical draws (only for the guardrails run).
    comparison = None
    if req.withdrawal_strategy == "guardrails":
        fixed_sr = float(result["baseline_survival_rate"])
        guard_sr = float(result["survival_rate"])
        comparison = StrategyComparison(
            fixed_survival_rate=fixed_sr,
            guardrails_survival_rate=guard_sr,
            survival_lift=guard_sr - fixed_sr,
            guardrail_band=req.guardrail_band,
            guardrail_adjust=req.guardrail_adjust,
        )

    return RetirementResponse(
        as_of=datetime.now(timezone.utc),
        params=params,
        survival_rate=float(result["survival_rate"]),
        accumulation_years=int(result["accumulation_years"]),
        distribution_years=int(result["distribution_years"]),
        terminal_at_retirement=TerminalStats(
            mean=float(accum.mean_terminal),
            median=float(accum.median_terminal),
            p5=float(accum.percentile_5),
            p25=float(accum.percentile_25),
            p75=float(accum.percentile_75),
            p95=float(accum.percentile_95),
        ),
        accumulation_chart=_fig_json(accum_fig),
        distribution_chart=_fig_json(dist_fig),
        depletion=_depletion_analysis(dist_paths),
        sensitivity=sensitivity,
        comparison=comparison,
    )
