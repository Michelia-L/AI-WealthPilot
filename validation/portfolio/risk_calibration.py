"""Compare saved decision-time forecasts with subsequent gross holding returns."""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR

from .comparison import require_same_protocol
from .forecasts import valid_forecast_boundary
from .robustness import summarize


@dataclass(frozen=True)
class CalibrationConfig:
    min_observations: int = 20
    min_periods: int = 3
    min_tail_observations: int = 5
    material_exceedance_ratio: float = 1.5

    def __post_init__(self):
        for name in ("min_observations", "min_periods", "min_tail_observations"):
            value = getattr(self, name)
            if type(value) is not int or value < (
                2 if name == "min_observations" else 1
            ):
                raise ValueError(
                    "Calibration sample minima must be positive integers; volatility needs two observations"
                )
        if (
            not np.isfinite(self.material_exceedance_ratio)
            or self.material_exceedance_ratio <= 1
        ):
            raise ValueError("material_exceedance_ratio must exceed one")


def calibration_summary(rows, config):
    pairs = [r for r in rows if r["status"] == "ok"]
    errors = np.asarray([r["error"] for r in pairs])
    enough = len(pairs) >= config.min_periods
    tail = [r for r in rows if r["downside_status"] == "ok"]
    n = sum(r["observations"] for r in tail)
    breaches = sum(r["exceedances"] for r in tail)
    tail_enough = len(tail) >= config.min_periods and n >= config.min_observations
    return {
        "periods": len(rows),
        "paired_periods": len(pairs),
        "unpaired_periods": len(rows) - len(pairs),
        "status": "ok" if enough else "insufficient_periods",
        "mae": float(np.mean(np.abs(errors))) if enough else None,
        "rmse": float(np.sqrt(np.mean(errors**2))) if enough else None,
        "bias": float(np.mean(errors)) if enough else None,
        "median_absolute_error": float(np.median(np.abs(errors))) if enough else None,
        "error_distribution": summarize(errors) if enough else None,
        "predicted_realized_ratio": summarize(
            r["predicted_realized_ratio"] for r in pairs
        )
        if enough
        else None,
        "material_underprediction_frequency": float(
            np.mean([r["material_underprediction"] for r in pairs])
        )
        if enough
        else None,
        "downside_periods": len(tail),
        "downside_observations": n,
        "exceedances": breaches,
        "exceedance_frequency": breaches / n if tail_enough else None,
        "expected_exceedance_frequency": sum(
            r["observations"] * (1 - r["confidence"]) for r in tail
        )
        / n
        if tail_enough
        else None,
        "conditional_loss_status": "ok"
        if tail_enough and breaches >= config.min_tail_observations
        else "insufficient_exceedances",
        "conditional_loss_bias": sum(
            r["exceedance_loss_sum"] - r["exceedances"] * r["predicted_cvar_daily"]
            for r in tail
        )
        / breaches
        if tail_enough and breaches >= config.min_tail_observations
        else None,
    }


def calibrate_risk(runs, config=None):
    """Next holding window only: (as_of, holding_end], actual drifting OOS path.

    Daily VaR is tested against daily observations, not monthly compounded loss.
    Strict loss > VaR breaches exclude ties; ES needs enough observed breaches.
    No gap dropping, inference tests, independence assumptions or model ranking.
    """
    config = config or CalibrationConfig()
    require_same_protocol(runs)
    rows = []
    for name, run in runs.items():
        for record in run.rebalances:
            forecast = record.get("risk_forecast") or {}
            as_of, end = (
                pd.Timestamp(record["as_of"]),
                pd.Timestamp(record["holding_end"]),
            )
            future = run.returns.loc[
                (run.returns.index > as_of) & (run.returns.index <= end)
            ]
            row = {
                "name": name,
                "strategy": record["strategy"],
                "as_of": as_of,
                "realized_start": future.index.min() if len(future) else None,
                "realized_end": end,
                "horizon_calendar_months": run.metadata["config"]["holding_window"],
                "covariance_method": forecast.get(
                    "covariance_method", record["covariance_method"]
                ),
                "covariance_role": forecast.get("covariance_role", "unavailable"),
                "observations": int(future.notna().sum()),
                "missing_observations": int(future.isna().sum()),
                "status": "forecast_unavailable",
                "downside_status": "forecast_unavailable",
                "predicted_volatility": forecast.get("predicted_volatility"),
                "realized_volatility": None,
                "error": None,
                "predicted_realized_ratio": None,
                "material_underprediction": None,
                "confidence": forecast.get("confidence"),
                "predicted_var_daily": forecast.get("var_daily"),
                "predicted_cvar_daily": forecast.get("cvar_daily"),
                "exceedances": None,
                "exceedance_frequency": None,
                "exceedance_loss_sum": None,
                "realized_conditional_loss": None,
                "conditional_loss_error": None,
                "conditional_loss_status": "unavailable",
            }
            rows.append(row)
            if record["allocation_status"] != "ok" or forecast.get("status") != "ok":
                continue
            # Explicitly reject a custom snapshot dated after the decision.
            if not valid_forecast_boundary(forecast, as_of):
                row["status"] = row["downside_status"] = "invalid_forecast_boundary"
                continue
            if record["status"] != "ok" or future.isna().any() or not len(future):
                row["status"] = row["downside_status"] = "incomplete_holding_window"
                continue
            if len(future) < config.min_observations:
                row["status"] = row["downside_status"] = "insufficient_observations"
                continue
            predicted = row["predicted_volatility"]
            if predicted is not None and np.isfinite(predicted) and predicted >= 0:
                realized = float(future.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
                row.update(
                    status="ok",
                    realized_volatility=realized,
                    error=realized - predicted,
                    predicted_realized_ratio=predicted / realized
                    if realized > 0
                    else None,
                    material_underprediction=bool(
                        realized > predicted * config.material_exceedance_ratio
                    ),
                )
            var, cvar, confidence = (
                row["predicted_var_daily"],
                row["predicted_cvar_daily"],
                row["confidence"],
            )
            if (
                any(v is None or not np.isfinite(v) for v in (var, cvar, confidence))
                or not 0 < confidence < 1
            ):
                continue
            losses = -future
            exceed = losses[losses > var]
            row.update(
                exceedances=len(exceed),
                exceedance_frequency=len(exceed) / len(future),
                exceedance_loss_sum=float(exceed.sum()),
            )
            if (
                forecast.get("training_tail_observations", 0)
                < config.min_tail_observations
            ):
                row["downside_status"] = "insufficient_training_tail"
                continue
            row["downside_status"] = "ok"
            row["conditional_loss_status"] = "insufficient_exceedances"
            if len(exceed) >= config.min_tail_observations:
                row.update(
                    realized_conditional_loss=float(exceed.mean()),
                    conditional_loss_error=float(exceed.mean() - cvar),
                    conditional_loss_status="ok",
                )
    groups = []
    # Keep candidate/estimator/role separate. Pooling duplicated sensitivity
    # paths would falsely inflate the sample count for an estimator.
    for name in runs:
        selected = [r for r in rows if r["name"] == name]
        for role in sorted({r["covariance_role"] for r in selected}):
            group = [r for r in selected if r["covariance_role"] == role]
            groups.append(
                {
                    "name": name,
                    "strategy": group[0]["strategy"],
                    "covariance_method": group[0]["covariance_method"],
                    "covariance_role": role,
                    **calibration_summary(group, config),
                }
            )
    return {
        "per_rebalance": rows,
        "summary": groups,
        "metadata": {
            "calibration_version": "1.0",
            "config": asdict(config),
            "forecast_horizon": "annualized one-day risk",
            "realized_horizon": "next holding window, strictly after decision; gross drifting portfolio",
            "annualization_days": TRADING_DAYS_PER_YEAR,
            "downside_horizon": "daily; strict loss > forecast VaR; ES conditional mean requires minimum breaches",
            "summary_policy": "observed complete pairs only; missing counts retained; candidate and covariance role kept separate",
            "regulatory_validation": False,
        },
    }
