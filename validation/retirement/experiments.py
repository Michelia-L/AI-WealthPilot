"""Transparent comparisons; no parameter, engine or seed is auto-selected."""

import json
from itertools import product

import numpy as np
import pandas as pd

from src.portfolio.inflation import resolve_personal_inflation

from .bootstrap import HistoricalReturns
from .harness import evaluate_paths, run_retirement
from .report import RetirementReport
from .scenarios import EngineConfig, RetirementScenario, RetirementStress


def compare_models(
    scenario: RetirementScenario,
    history: HistoricalReturns,
    *,
    block_length: int = 6,
    bootstrap_mode: str = "empirical",
) -> RetirementReport:
    runs = {}
    for model, strategy in product(
        ("gbm", "iid_bootstrap", "block_bootstrap"), ("fixed", "guardrails")
    ):
        runs[f"{model}/{strategy}"] = run_retirement(
            scenario.changed(withdrawal_strategy=strategy),
            EngineConfig(
                engine=model, block_length=block_length, bootstrap_mode=bootstrap_mode
            ),
            history=history if model != "gbm" else None,
        )
    return RetirementReport(
        runs,
        {
            "experiment": "models_and_spending_rules",
            "pairing": "same phase draws for fixed/guardrails within each engine; engines have different draws",
            "bootstrap_mode": bootstrap_mode,
            "interpretation": "empirical models use historical moments; matched mode uses GBM marginal log moments but retains sample tails and block dependence",
        },
    )


def parameter_grid(
    scenario: RetirementScenario,
    axes: dict[str, tuple],
    engine: EngineConfig | None = None,
    *,
    history: HistoricalReturns | None = None,
) -> RetirementReport:
    """Cartesian, caller-bounded grid on common draws (same N/seed/horizon)."""
    allowed = {
        "expected_return",
        "volatility",
        "inflation_rate",
        "distribution_inflation_rate",
        "return_multiplier",
        "volatility_multiplier",
        "life_expectancy",
        "withdrawal_strategy",
        "guardrail_band",
        "guardrail_adjust",
    }
    if not axes or not set(axes) <= allowed:
        raise ValueError("unsupported or empty sensitivity axes")
    if any(not values or len(set(values)) != len(values) for values in axes.values()):
        raise ValueError("sensitivity axes must be nonempty and unique")
    engine = engine or EngineConfig()
    if (
        engine.engine != "gbm"
        and engine.bootstrap_mode == "empirical"
        and set(axes) & {"expected_return", "volatility"}
    ):
        raise ValueError(
            "empirical bootstrap ignores scenario mu/sigma; use matched_gbm_moments"
        )
    runs = {}
    for values in product(*axes.values()):
        updates = dict(zip(axes, values, strict=True))
        key = json.dumps(updates, sort_keys=True, separators=(",", ":"))
        runs[key] = run_retirement(scenario.changed(**updates), engine, history=history)
    derivatives = []
    if "expected_return" in axes:
        other_axes = {k: v for k, v in axes.items() if k != "expected_return"}
        for values in product(*other_axes.values()):
            group = dict(zip(other_axes, values, strict=True))
            rates = sorted(axes["expected_return"])
            for low, high in zip(rates[:-1], rates[1:], strict=True):
                keys = [
                    json.dumps(
                        group | {"expected_return": r},
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for r in (low, high)
                ]
                delta = (
                    runs[keys[1]].metrics["success_probability"]
                    - runs[keys[0]].metrics["success_probability"]
                )
                derivatives.append(
                    group
                    | {
                        "return_low": low,
                        "return_high": high,
                        "success_probability_change_per_unit_return": delta
                        / (high - low),
                    }
                )
    return RetirementReport(
        runs,
        {
            "experiment": "parameter_grid",
            "axes": axes,
            "return_sensitivity": derivatives,
            "pairing": "same phase seeds; GBM horizon extensions retain earlier draws; bootstrap pairing only guaranteed for identical shapes",
            "assumption_provenance": "CME reference retained if supplied; perturbed parameters are experiments, not original vintage forecasts",
        },
    )


def standard_sensitivities(scenario: RetirementScenario) -> dict[str, RetirementReport]:
    """GBM grids, with separate CPI-style and elderly-preset comparisons."""
    return {
        "return_volatility": parameter_grid(
            scenario,
            {
                "expected_return": tuple(
                    scenario.expected_return + d for d in (-0.02, -0.01, 0, 0.01, 0.02)
                ),
                "volatility": tuple(
                    dict.fromkeys(scenario.volatility * m for m in (0.75, 1, 1.25))
                ),
            },
        ),
        "allocation_shift": RetirementReport(
            {
                str(m): run_retirement(
                    scenario.changed(return_multiplier=m, volatility_multiplier=m)
                )
                for m in (0.5, 0.7, 0.85, 1.0)
            },
            {"experiment": "joint_retirement_return_volatility_multiplier"},
        ),
        "inflation": parameter_grid(
            scenario,
            {
                "inflation_rate": (0.02, 0.03, 0.04, 0.05),
                "distribution_inflation_rate": (0.02, 0.03, 0.04, 0.05),
            },
        ),
        "elderly_inflation": RetirementReport(
            {
                preset: run_retirement(
                    scenario.changed(
                        distribution_inflation_rate=resolve_personal_inflation(
                            scenario.inflation_rate, preset
                        )
                    )
                )
                for preset in ("standard", "elderly")
            },
            {
                "experiment": "production_inflation_presets",
                "interpretation": "stylized additive CPI-E-style assumption, not a live CPI-E series",
            },
        ),
        "longevity": parameter_grid(
            scenario,
            {
                "life_expectancy": tuple(
                    sorted(
                        {scenario.life_expectancy}
                        | {
                            age
                            for age in (85, 90, 95, 100)
                            if age > scenario.retirement_age
                        }
                    )
                )
            },
        ),
    }


def convergence(
    scenario: RetirementScenario,
    engine: EngineConfig | None = None,
    *,
    history: HistoricalReturns | None = None,
    counts: tuple[int, ...] = (1000, 5000, 10000, 25000),
    seeds: tuple[int, ...] = (7, 42, 123),
) -> RetirementReport:
    if (
        not counts
        or len(set(counts)) != len(counts)
        or len(seeds) < 2
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError("use unique counts and at least two unique seeds")
    runs = {
        f"n={n}/seed={seed}": run_retirement(
            scenario.changed(n_simulations=n, seed=seed), engine, history=history
        )
        for n, seed in product(counts, seeds)
    }
    rows = []
    for n in counts:
        for metric in (
            "success_probability",
            "median_terminal_wealth",
            "p5_terminal_wealth",
        ):
            values = np.array(
                [runs[f"n={n}/seed={seed}"].metrics[metric] for seed in seeds]
            )
            rows.append(
                {
                    "n_simulations": n,
                    "metric": metric,
                    "seed_count": len(seeds),
                    "mean": float(values.mean()),
                    "std_across_seeds": float(values.std(ddof=1)),
                    "min": float(values.min()),
                    "max": float(values.max()),
                }
            )
    return RetirementReport(
        runs,
        {
            "experiment": "convergence_and_seed_stability",
            "counts": counts,
            "seeds": seeds,
            "stability": rows,
            "interpretation": "repeated-seed variability is sampling uncertainty, not model uncertainty; counts do not use nested paths and no seed is selected",
        },
    )


def sequence_experiment(
    scenario: RetirementScenario,
    retirement_returns: tuple[float, ...],
    *,
    accumulation_returns: tuple[float, ...] = (),
) -> RetirementReport:
    """Cluster identical negative observations early/middle/late; keep their order."""
    if (
        len(retirement_returns) != scenario.distribution_years
        or len(accumulation_returns) != scenario.accumulation_years
    ):
        raise ValueError("sequence fixture must match both phase horizons")
    returns = np.asarray(retirement_returns, dtype=float)
    if not np.isfinite(returns).all() or (returns < -1).any():
        raise ValueError("invalid sequence returns")
    negative, positive = returns[returns < 0], returns[returns >= 0]
    middle = len(positive) // 2
    orders = {
        "early_losses": np.concatenate((negative, positive)),
        "middle_losses": np.concatenate(
            (positive[:middle], negative, positive[middle:])
        ),
        "late_losses": np.concatenate((positive, negative)),
    }
    runs = {
        name: evaluate_paths(
            scenario.changed(n_simulations=1),
            1 + np.array([accumulation_returns]),
            1 + values[None, :],
        )
        for name, values in orders.items()
    }
    return RetirementReport(
        runs,
        {
            "experiment": "controlled_sequence",
            "annual_simple_returns": {k: v.tolist() for k, v in orders.items()},
            "interpretation": "deterministic paths; survival is a fixture outcome, not an estimated probability; same return multiset",
        },
    )


def standard_stresses(scenario: RetirementScenario) -> tuple[RetirementStress, ...]:
    return (
        RetirementStress(name="early_retirement_crash", retirement_returns=(-0.30,)),
        RetirementStress(
            name="poor_return_decade",
            retirement_returns=(0.0,) * min(10, scenario.distribution_years),
        ),
        RetirementStress(
            name="early_high_inflation",
            retirement_inflation=(0.06,) * min(5, scenario.distribution_years),
        ),
        RetirementStress(
            name="combined_crash_inflation",
            retirement_returns=(-0.30,),
            retirement_inflation=(0.06,) * min(5, scenario.distribution_years),
        ),
    )


def stress_comparison(
    scenario: RetirementScenario,
    engine: EngineConfig | None = None,
    *,
    history: HistoricalReturns | None = None,
) -> RetirementReport:
    runs = {"baseline": run_retirement(scenario, engine, history=history)}
    runs.update(
        {
            stress.name: run_retirement(
                scenario, engine, history=history, stress=stress
            )
            for stress in standard_stresses(scenario)
        }
    )
    return RetirementReport(
        runs,
        {
            "experiment": "deterministic_retirement_overlays",
            "mechanism": "replace first retirement-year portfolio simple returns and/or inflation; later draws unchanged",
            "interpretation": "uncalibrated whole-portfolio shocks, not event probabilities; zero-return decade is poor only relative to positive base assumptions",
        },
    )


def stability_table(report: RetirementReport) -> pd.DataFrame:
    return pd.DataFrame(report.metadata.get("stability", []))
