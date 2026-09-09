"""Common survival AND spending outcomes; sampling error is not model risk."""

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.portfolio.retirement_paths import DistributionTrace

from .scenarios import RetirementScenario


def monte_carlo_se(probability: float, n_simulations: int) -> float:
    if not np.isfinite(probability) or not 0 <= probability <= 1 or n_simulations < 1:
        raise ValueError("invalid binomial sampling inputs")
    return float(np.sqrt(probability * (1 - probability) / n_simulations))


@dataclass
class RetirementRun:
    metrics: dict
    diagnostics: dict
    metadata: dict
    path_metrics: pd.DataFrame
    annual_metrics: pd.DataFrame

    def to_dict(self, *, include_paths: bool = False) -> dict:
        result = {
            "metrics": self.metrics,
            "diagnostics": self.diagnostics,
            "metadata": self.metadata,
            "annual_metrics": self.annual_metrics.to_dict(orient="records"),
        }
        if include_paths:
            # Pandas serializes missing depletion ages as null, never NaN.
            result["path_metrics"] = json.loads(
                self.path_metrics.to_json(orient="records")
            )
        return result

    def to_json(self, *, include_paths: bool = False) -> str:
        return json.dumps(
            self.to_dict(include_paths=include_paths),
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "summary": pd.json_normalize(
                {"metrics": self.metrics, "metadata": self.metadata}
            ),
            "paths": self.path_metrics.copy(),
            "annual": self.annual_metrics.copy(),
        }


def summarize(
    scenario: RetirementScenario,
    trace: DistributionTrace,
    metadata: dict,
    diagnostics: dict,
    *,
    stochastic: bool,
) -> RetirementRun:
    depleted = (trace.paths <= 0).any(axis=1)
    first_zero = (trace.paths <= 0).argmax(axis=1)
    depletion_year = np.where(depleted, first_zero, np.nan)
    real = trace.delivered / trace.inflation_factors
    requested_real = trace.requested / trace.inflation_factors
    target = scenario.desired_annual_income
    shortfall = np.maximum(target - real, 0)
    policy_reduction = np.maximum(target - requested_real, 0)
    # Floor must hold in EVERY distribution year, not just on average.
    floor_met = (real >= target * scenario.spending_floor_fraction).all(axis=1)
    cut_real = trace.cut_amounts / trace.inflation_factors
    terminal = trace.paths[:, -1]
    probability = float((~depleted).mean())
    cuts = trace.cuts.sum(axis=1)
    path_metrics = pd.DataFrame(
        {
            "path": np.arange(scenario.n_simulations),
            "survived": ~depleted,
            "terminal_wealth": terminal,
            "depletion_year": depletion_year,
            "depletion_age": scenario.retirement_age + depletion_year,
            "nominal_withdrawals": trace.delivered.sum(axis=1),
            "requested_nominal_withdrawals": trace.requested.sum(axis=1),
            "lifetime_real_spending": real.sum(axis=1),
            "mean_annual_real_spending": real.mean(axis=1),
            "lifetime_real_shortfall": shortfall.sum(axis=1),
            "policy_real_reduction_from_target": policy_reduction.sum(axis=1),
            "spending_cuts": cuts,
            "spending_increases": trace.increases.sum(axis=1),
            "cumulative_real_cut_amount": cut_real.sum(axis=1),
            "maintains_spending_floor": floor_met,
        }
    )
    metrics = {
        "success_probability": probability,
        "survival_rate": probability,
        "probability_of_depletion": float(depleted.mean()),
        "success_probability_mc_se": monte_carlo_se(probability, scenario.n_simulations)
        if stochastic
        else None,
        "median_terminal_wealth": float(np.median(terminal)),
        "p5_terminal_wealth": float(np.percentile(terminal, 5)),
        "p25_terminal_wealth": float(np.percentile(terminal, 25)),
        "median_depletion_year": float(np.median(first_zero[depleted]))
        if depleted.any()
        else None,
        "median_depletion_age": float(
            scenario.retirement_age + np.median(first_zero[depleted])
        )
        if depleted.any()
        else None,
        "mean_lifetime_nominal_withdrawals": float(trace.delivered.sum(axis=1).mean()),
        "mean_requested_nominal_withdrawals": float(trace.requested.sum(axis=1).mean()),
        "mean_lifetime_real_spending": float(real.sum(axis=1).mean()),
        "mean_annual_real_spending": float(real.mean()),
        "median_annual_real_spending_per_path": float(np.median(real.mean(axis=1))),
        "mean_lifetime_real_shortfall": float(shortfall.sum(axis=1).mean()),
        "mean_policy_real_reduction_from_target": float(
            policy_reduction.sum(axis=1).mean()
        ),
        "mean_spending_cuts": float(cuts.mean()),
        "mean_spending_increases": float(trace.increases.sum(axis=1).mean()),
        "mean_cumulative_real_cut_amount": float(cut_real.sum(axis=1).mean()),
        "mean_real_cut_amount_per_event": float(cut_real.sum() / cuts.sum())
        if cuts.sum()
        else None,
        "fraction_paths_maintaining_spending_floor": float(floor_met.mean()),
    }
    annual = pd.DataFrame(
        {
            "retirement_year": np.arange(1, scenario.distribution_years + 1),
            "age": np.arange(scenario.retirement_age + 1, scenario.life_expectancy + 1),
            "target_nominal_spending": trace.target,
            "mean_requested_nominal_spending": trace.requested.mean(axis=0),
            "mean_delivered_nominal_spending": trace.delivered.mean(axis=0),
            "mean_delivered_real_spending": real.mean(axis=0),
            "p5_delivered_real_spending": np.percentile(real, 5, axis=0),
            "cut_fraction": trace.cuts.mean(axis=0),
            "increase_fraction": trace.increases.mean(axis=0),
            "cumulative_depletion_fraction": (trace.paths[:, 1:] <= 0).mean(axis=0),
        }
    )
    diagnostics = diagnostics | {
        "depletion_year_counts": {
            str(int(y)): int((first_zero[depleted] == y).sum())
            for y in np.unique(first_zero[depleted])
        },
        "survivor_count": int((~depleted).sum()),
    }
    return RetirementRun(metrics, diagnostics, metadata, path_metrics, annual)


@dataclass
class RetirementReport:
    runs: dict[str, RetirementRun]
    metadata: dict

    def to_json(self) -> str:
        return json.dumps(
            {
                "metadata": self.metadata,
                "runs": {k: v.to_dict() for k, v in self.runs.items()},
            },
            sort_keys=True,
            allow_nan=False,
            indent=2,
        )

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "comparison": pd.json_normalize(
                [
                    {
                        "experiment": name,
                        **run.metrics,
                        "scenario": run.metadata["scenario"],
                        "engine": run.metadata["engine"],
                    }
                    for name, run in self.runs.items()
                ]
            ),
            "annual": pd.concat(
                [
                    r.annual_metrics.assign(experiment=name)
                    for name, r in self.runs.items()
                ],
                ignore_index=True,
            ),
        }
