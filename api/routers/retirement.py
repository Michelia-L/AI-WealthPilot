"""
Retirement planning endpoint — two-phase Monte Carlo simulation.

POST /api/retirement/simulate wraps MonteCarloSimulator.retirement_planning
(accumulation with savings injection, then distribution with inflation-
adjusted withdrawals) and mirrors the Streamlit planner's depletion and
sensitivity analyses. Runs are seeded (42) so identical parameters yield
identical results — reproducibility beats novelty for financial plans.
"""

from datetime import datetime, timezone
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException

from api.routers.market import _fig_json
from api.schemas import (
    DepletionAnalysis,
    RetirementRequest,
    RetirementResponse,
    SensitivityRow,
    TerminalStats,
)
from src.portfolio.simulator import MonteCarloSimulator
from src.visualization.charts import plot_monte_carlo_paths

router = APIRouter(prefix="/retirement", tags=["retirement"])

SEED = 42  # Fixed seed for reproducibility (same as the Streamlit planner)
SAVINGS_MULTIPLIERS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
SENSITIVITY_SIMULATIONS = 5_000
CHART_DISPLAY_PATHS = 200


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
    )
