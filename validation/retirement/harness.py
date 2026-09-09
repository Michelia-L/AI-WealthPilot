"""Run multiple return processes through the production cash-flow rules."""

import hashlib
import platform

import numpy as np

from src.portfolio.retirement_paths import distribution_from_growth, gbm_growth
from src.portfolio.simulator import MonteCarloSimulator

from .bootstrap import HistoricalReturns, bootstrap_growth
from .report import RetirementRun, summarize
from .scenarios import EngineConfig, RetirementScenario, RetirementStress


def _growth_hash(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def evaluate_paths(
    scenario: RetirementScenario,
    accumulation_growth: np.ndarray,
    distribution_growth: np.ndarray,
    *,
    stress: RetirementStress | None = None,
) -> RetirementRun:
    """Replay supplied annual gross returns; no MC error claimed for a fixture."""
    return _evaluate(
        scenario,
        accumulation_growth,
        distribution_growth,
        {
            "engine": "supplied_paths",
            "accumulation_growth": np.asarray(
                accumulation_growth, dtype=float
            ).tolist(),
            "distribution_growth": np.asarray(
                distribution_growth, dtype=float
            ).tolist(),
        },
        {},
        stress,
        stochastic=False,
    )


def _evaluate(
    scenario,
    accumulation_growth,
    distribution_growth,
    engine,
    diagnostics,
    stress,
    *,
    stochastic,
):
    scenario = RetirementScenario.model_validate(scenario.model_dump())
    accumulation_growth = np.array(accumulation_growth, dtype=float, copy=True)
    distribution_growth = np.array(distribution_growth, dtype=float, copy=True)
    if distribution_growth.shape != (
        scenario.n_simulations,
        scenario.distribution_years,
    ):
        raise ValueError("distribution growth shape does not match scenario")
    if not np.isfinite(distribution_growth).all() or (distribution_growth < 0).any():
        raise ValueError("invalid supplied distribution growth")
    inflation_schedule = None
    if stress is not None:
        stress = RetirementStress.model_validate(stress.model_dump())
        if (
            max(len(stress.retirement_returns), len(stress.retirement_inflation))
            > scenario.distribution_years
        ):
            raise ValueError("stress exceeds retirement horizon")
        distribution_growth[:, : len(stress.retirement_returns)] = 1 + np.array(
            stress.retirement_returns
        )
        if stress.retirement_inflation:
            inflation_schedule = np.full(
                scenario.distribution_years, scenario.retirement_inflation
            )
            inflation_schedule[: len(stress.retirement_inflation)] = (
                stress.retirement_inflation
            )
    accumulation = MonteCarloSimulator(
        scenario.expected_return,
        scenario.volatility,
        scenario.n_simulations,
        scenario.accumulation_years,
        scenario.seed,
    ).simulate(
        scenario.current_savings,
        scenario.annual_savings,
        growth_factors=accumulation_growth,
    )
    trace = distribution_from_growth(
        accumulation.terminal_values,
        distribution_growth,
        scenario.desired_annual_income,
        scenario.accumulation_years,
        scenario.inflation_rate,
        scenario.retirement_inflation,
        scenario.withdrawal_strategy,
        scenario.guardrail_band,
        scenario.guardrail_adjust,
        inflation_schedule=inflation_schedule,
    )
    metadata = {
        "schema_version": "1.0",
        "scenario": scenario.model_dump(mode="json"),
        "effective_distribution_inflation_rate": scenario.retirement_inflation,
        "engine": engine,
        "stress": stress.model_dump(mode="json") if stress else None,
        "numpy_version": np.__version__,
        "python_version": platform.python_version(),
        "annual_step_frequency": 1,
        "accumulation_growth_sha256": _growth_hash(accumulation_growth),
        "distribution_growth_sha256": _growth_hash(distribution_growth),
        "success_definition": "strictly positive wealth at retirement and every year end",
        "spending_timing": "returns first; nominal contribution or withdrawal at year end",
        "guardrail_convention": "production v1: initial withdrawal includes one inflation step; first tentative includes another",
        "real_spending_deflator": "accumulation inflation to retirement, then cumulative distribution inflation including stress",
        "mc_error_scope": "conditional simulation sampling only; excludes historical sample uncertainty and model risk"
        if stochastic
        else "not applicable to deterministic supplied paths",
    }
    diagnostics = diagnostics | {
        "median_retirement_wealth": float(np.median(accumulation.terminal_values))
    }
    return summarize(scenario, trace, metadata, diagnostics, stochastic=stochastic)


def run_retirement(
    scenario: RetirementScenario,
    engine: EngineConfig | None = None,
    *,
    history: HistoricalReturns | None = None,
    stress: RetirementStress | None = None,
) -> RetirementRun:
    scenario = RetirementScenario.model_validate(scenario.model_dump())
    engine = EngineConfig.model_validate((engine or EngineConfig()).model_dump())
    rng = np.random.default_rng(scenario.seed)
    # Exact production seed splitting, including a zero-year accumulation phase.
    seeds = [int(rng.integers(0, 2**31)) for _ in range(2)]
    diagnostics = {"phase_seeds": seeds}
    metadata = engine.model_dump(mode="json")
    if engine.engine == "gbm":
        if history is not None:
            raise ValueError("GBM does not use historical input")
        accumulation = gbm_growth(
            scenario.expected_return,
            scenario.volatility,
            scenario.n_simulations,
            scenario.accumulation_years,
            seeds[0],
        )
        distribution = gbm_growth(
            scenario.expected_return * scenario.return_multiplier,
            scenario.volatility * scenario.volatility_multiplier,
            scenario.n_simulations,
            scenario.distribution_years,
            seeds[1],
        )
        diagnostics["assumptions"] = (
            "independent normal log-return shocks; constant mu/sigma; no regimes or stochastic volatility"
        )
    else:
        if history is None:
            raise ValueError("bootstrap requires supplied portfolio history")
        history = HistoricalReturns.model_validate(history.model_dump())
        if history.currency != scenario.base_currency:
            raise ValueError(
                "historical returns and scenario must use the same currency"
            )
        accumulation, accum_diag = bootstrap_growth(
            history,
            engine,
            scenario.n_simulations,
            scenario.accumulation_years,
            seeds[0],
            scenario.expected_return,
            scenario.volatility,
        )
        distribution, dist_diag = bootstrap_growth(
            history,
            engine,
            scenario.n_simulations,
            scenario.distribution_years,
            seeds[1],
            scenario.expected_return,
            scenario.volatility,
            scenario.return_multiplier,
            scenario.volatility_multiplier,
        )
        diagnostics |= {"accumulation": accum_diag, "distribution": dist_diag}
        metadata |= {
            "history": history.model_dump(mode="json"),
            "sample_id": history.sample_id,
            "block_boundary": "independent draws for accumulation and distribution; no cross-phase block",
            "scenario_mu_sigma_used": engine.bootstrap_mode == "matched_gbm_moments",
        }
    return _evaluate(
        scenario,
        accumulation,
        distribution,
        metadata,
        diagnostics,
        stress,
        stochastic=True,
    )
