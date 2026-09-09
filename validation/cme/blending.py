"""Counterfactual blend grids using only immutable saved CME components."""

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.portfolio.cme_blending import blend_assumption
from validation.portfolio.walk_forward import _json_safe

from .calibration import COHORT, CalibrationConfig, calibrate, error_summary, grouped


@dataclass(frozen=True)
class BlendGrid:
    tau: tuple[float, ...] = (0, 0.25, 0.5, 0.75, 1)
    omega: tuple[float, ...] = (0, 0.25, 0.5, 0.75, 1)

    def __post_init__(self):
        for values in (self.tau, self.omega):
            if (
                not values
                or len(set(values)) != len(values)
                or any(not np.isfinite(v) or not 0 <= v <= 1 for v in values)
            ):
                raise ValueError("Blend grids require unique finite weights in [0, 1]")


@dataclass
class BlendingReport:
    rows: list[dict]
    summaries: list[dict]
    rankings: list[dict]
    metadata: dict

    def to_dict(self):
        return _json_safe(asdict(self))

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, allow_nan=False)

    def tables(self):
        return {
            name: pd.json_normalize(value)
            for name, value in self.to_dict().items()
            if name != "metadata"
        }


def evaluate_blending(vintages, panel, *, evaluation_date, grid=None, config=None):
    """One-factor experiments, not a refit, current-data request or auto-tuner.

    Missing alternative components retain production's historical fallback and
    are kept in separate cohorts. Legacy missing historical returns are unknown.
    """
    grid = grid or BlendGrid()
    config = config or CalibrationConfig()
    calibration = calibrate(
        vintages, panel, evaluation_date=evaluation_date, config=config
    )
    rows = []
    for original in calibration.asset_rows:
        for parameter, weights, historical_key, forward_key, outcome_key in (
            (
                "tau",
                grid.tau,
                "historical_volatility",
                "implied_volatility",
                "realized_volatility",
            ),
            (
                "omega",
                grid.omega,
                "historical_return",
                "forward_return",
                "realized_return",
            ),
        ):
            history, forward = original[historical_key], original[forward_key]
            for weight in weights:
                row = {
                    **original,
                    "parameter": parameter,
                    "weight": weight,
                    "component_available": forward is not None,
                    "component_status": "available"
                    if forward is not None
                    else "historical_fallback",
                    "experiment_forecast": None,
                    "error": None,
                    "historical_error": None,
                    "experiment_underprediction": None,
                }
                if history is None:
                    row["component_status"] = "historical_component_unavailable"
                    if row["status"] == "ok":
                        row["status"] = "historical_component_unavailable"
                else:
                    predicted = blend_assumption(history, forward, weight)
                    row["experiment_forecast"] = predicted
                    if row["status"] == "ok":
                        outcome = row[outcome_key]
                        row.update(
                            error=outcome - predicted,
                            historical_error=outcome - history,
                            experiment_underprediction=outcome > predicted
                            if parameter == "tau"
                            else None,
                        )
                rows.append(row)
    summaries = []
    keys = (
        *COHORT,
        "asset_key",
        "ticker",
        "return_source_quality",
        "volatility_source_quality",
        "parameter",
        "weight",
        "component_status",
    )
    for cohort, values in grouped(rows, keys):
        summary = error_summary(values, "error", config.min_vintages)
        historical = error_summary(values, "historical_error", config.min_vintages)
        enough = summary["status"] == "ok"
        valid = [r for r in values if r["error"] is not None]
        summaries.append(
            {
                **cohort,
                **summary,
                "historical_mae": historical["mae"],
                "historical_rmse": historical["rmse"],
                "mae_change_vs_historical": summary["mae"] - historical["mae"]
                if enough
                else None,
                "rmse_change_vs_historical": summary["rmse"] - historical["rmse"]
                if enough
                else None,
                "underprediction_frequency": float(
                    np.mean([r["experiment_underprediction"] for r in valid])
                )
                if enough and cohort["parameter"] == "tau"
                else None,
                "forecast_std_across_vintages": float(
                    np.std([r["experiment_forecast"] for r in valid], ddof=1)
                )
                if enough and len(valid) > 1
                else None,
            }
        )
    rankings = []
    for cohort, values in grouped(
        [r for r in rows if r["parameter"] == "omega"],
        ("vintage_id", "horizon_years", "weight"),
    ):
        row = {
            **cohort,
            "as_of": values[0]["as_of"],
            "model_version": values[0]["model_version"],
            "vintage_type": values[0]["vintage_type"],
            "cache_status": values[0]["cache_status"],
            "source_quality": values[0]["source_quality"],
            "assets": len(values),
            "fallback_assets": sum(not r["component_available"] for r in values),
            "status": "insufficient_assets",
            "rank_correlation": None,
            "historical_rank_correlation": None,
            "rank_change_vs_historical": None,
        }
        if len(values) >= config.min_rank_assets and all(
            r["error"] is not None for r in values
        ):
            forecasts = [r["experiment_forecast"] for r in values]
            historical = [r["historical_return"] for r in values]
            realized = [r["realized_return"] for r in values]
            if len(set(realized)) > 1 and len(set(forecasts)) > 1:
                row.update(
                    status="ok",
                    rank_correlation=float(spearmanr(forecasts, realized).statistic),
                )
                if len(set(historical)) > 1:
                    row["historical_rank_correlation"] = float(
                        spearmanr(historical, realized).statistic
                    )
                    row["rank_change_vs_historical"] = (
                        row["rank_correlation"] - row["historical_rank_correlation"]
                    )
            else:
                row["status"] = "constant_ranks"
        rankings.append(row)
    return BlendingReport(
        rows,
        summaries,
        rankings,
        {
            "blending_version": "1.0",
            "grid": asdict(grid),
            "calibration": calibration.metadata,
            "design": "separate tau volatility and omega return grids on archived components; no joint grid or production parameter updates",
            "formula": "weight*forward + (1-weight)*historical; historical fallback if forward is absent",
            "rounding": "saved report components may be rounded; grids recompute their linear blend without additional rounding",
            "comparison": "paired same-vintage errors against historical-only; negative MAE/RMSE change means lower descriptive error",
            "missing_policy": "no present-day substitutes; unavailable forward components labeled and stratified; missing historical component prevents comparison",
        },
    )
