"""Transparent comparison tables and separate metric rankings, without a score."""

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .costs import CostConfig, ImplementationReport, analyze_costs
from .walk_forward import ValidationRun, _json_safe


def require_same_protocol(runs: dict[str, ValidationRun]) -> None:
    if not runs:
        raise ValueError("At least one validation run is required")
    first = next(iter(runs.values()))
    keys = (
        "start_date",
        "end_date",
        "universe",
        "holding_window",
        "rebalance_frequency",
        "risk_free_rate",
    )
    for run in runs.values():
        if (
            any(
                _json_safe(run.metadata["config"][k])
                != _json_safe(first.metadata["config"][k])
                for k in keys
            )
            or run.metadata["data_sha256"] != first.metadata["data_sha256"]
            or not run.returns.index.equals(first.returns.index)
            or [r["as_of"] for r in run.rebalances]
            != [r["as_of"] for r in first.rebalances]
        ):
            raise ValueError(
                "Comparisons require the same input snapshot, universe, OOS dates, rebalance protocol and risk-free assumption"
            )


@dataclass
class ComparisonReport:
    rows: list[dict]
    implementations: dict[str, ImplementationReport]
    metadata: dict

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(_json_safe(self.rows))

    def to_dict(self) -> dict:
        return _json_safe(
            {
                "metadata": self.metadata,
                "rows": self.rows,
                "implementations": {
                    k: v.to_dict() for k, v in self.implementations.items()
                },
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, allow_nan=False)


def compare_runs(
    runs: dict[str, ValidationRun], costs: CostConfig | None = None
) -> ComparisonReport:
    """Compare strategies or sensitivity variants on a shared OOS protocol.

    Rankings are per cost scenario and per metric. A failed net/gross path in
    any candidate suppresses the cohort's rankings; no survivor-only leaderboard.
    Undefined metrics (e.g. zero-volatility Sharpe) retain null ranks.
    """
    costs = costs or CostConfig()
    require_same_protocol(runs)
    reports = {name: analyze_costs(run, costs) for name, run in runs.items()}
    rows = []
    for name, report in reports.items():
        run = report.gross
        weights = report.weights
        for scenario in report.scenarios:
            rows.append(
                {
                    "name": name,
                    "strategy": run.metadata["config"]["strategy"]["name"],
                    "covariance_method": run.metadata["config"]["covariance_method"],
                    "training_window": run.metadata["config"]["training_window"],
                    "window_type": run.metadata["config"]["window_type"],
                    "cost_bps": scenario.rate_bps,
                    **{
                        k: scenario.metrics[k]
                        for k in (
                            "gross_cagr",
                            "net_cagr",
                            "gross_sharpe",
                            "net_sharpe",
                            "cumulative_cost_drag",
                            "annualized_turnover",
                        )
                    },
                    "gross_volatility": run.metrics["annualized_volatility"],
                    "net_volatility": scenario.metrics["annualized_volatility"],
                    "gross_max_drawdown": run.metrics["max_drawdown"],
                    "net_max_drawdown": scenario.metrics["max_drawdown"],
                    "max_weight": weights["max_weight"]["max"],
                    "mean_max_weight": weights["max_weight"]["mean"],
                    "mean_effective_holdings": weights["effective_holdings"]["mean"],
                    "mean_target_distance": weights["target_distance"]["mean"],
                    "mean_predicted_volatility": weights["predicted_volatility"][
                        "mean"
                    ],
                    "max_condition_number": weights["condition_number"]["max"],
                    "nonfinite_condition_count": weights["nonfinite_condition_count"],
                    "regularized_count": weights["regularized_count"],
                    "allocation_failure_count": run.metrics["allocation_failure_count"],
                    "allocation_failure_frequency": run.metrics[
                        "allocation_failure_count"
                    ]
                    / len(run.rebalances)
                    if run.rebalances
                    else None,
                    "skipped_period_count": run.metrics["skipped_period_count"],
                    "complete": bool(
                        run.metrics["complete"] and scenario.metrics["complete"]
                    ),
                }
            )
    directions = {
        "gross_sharpe": False,
        "net_sharpe": False,
        "gross_cagr": False,
        "net_cagr": False,
        "annualized_turnover": True,
        "net_max_drawdown": False,
        "mean_target_distance": True,
    }
    for rate in costs.rates_bps:
        cohort = [row for row in rows if row["cost_bps"] == rate]
        complete = all(row["complete"] for row in cohort)
        for metric, ascending in directions.items():
            values = pd.Series(
                {row["name"]: row[metric] for row in cohort}, dtype=float
            )
            ranks = values.where(np.isfinite(values)).rank(
                method="min", ascending=ascending
            )
            for row in cohort:
                rank = ranks[row["name"]]
                row[f"{metric}_rank"] = (
                    int(rank) if complete and pd.notna(rank) else None
                )
                row["rankings_complete"] = complete
    return ComparisonReport(
        rows,
        reports,
        {
            "comparison_version": "1.0",
            "rank_policy": "separate ranks per cost scenario and metric; minimum rank for ties; no aggregate score",
            "failure_policy": "suppress cohort rankings when any gross/net path is incomplete",
            "rank_directions": {
                k: "lower_is_better" if v else "higher_is_better"
                for k, v in directions.items()
            },
        },
    )
