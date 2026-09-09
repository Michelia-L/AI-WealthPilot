"""Decision-time risk snapshots; no market-data access or allocation decisions."""

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR
from src.portfolio.optimizer import PortfolioOptimizer
from src.portfolio.risk_metrics import conditional_var, value_at_risk


def risk_snapshot(
    history,
    weights,
    optimizer,
    *,
    covariance_role,
    confidence=0.95,
    downside_result=None,
):
    """Save the actual annual covariance, plus daily historical loss estimates.

    Mean-CVaR uses its LP threshold/objective (undo production sqrt(252)
    reporting scale). Other methods use production historical VaR/CVaR helpers.
    These are constant-target historical scenarios, not a fitted NAV path.
    """
    assets = optimizer.asset_names
    vector = pd.Series(weights).reindex(assets, fill_value=0.0).to_numpy()
    covariance = optimizer.cov_matrix.to_numpy()
    variance = float(vector @ covariance @ vector)
    if (
        not np.isfinite(covariance).all()
        or not np.isfinite(variance)
        or variance < -1e-12
    ):
        raise ValueError("Invalid forecast covariance")
    scenarios = history[assets] @ vector
    if downside_result is None:
        var = value_at_risk(scenarios, confidence)
        cvar = conditional_var(scenarios, confidence)
        downside_method = "historical_percentile_and_inclusive_tail"
    else:
        var = downside_result["var"] / np.sqrt(TRADING_DAYS_PER_YEAR)
        cvar = downside_result["cvar"] / np.sqrt(TRADING_DAYS_PER_YEAR)
        downside_method = "mean_cvar_lp_threshold_and_objective"
    return {
        "status": "ok",
        "reason": None,
        "assets": assets,
        "annual_covariance": covariance.tolist(),
        "covariance_method": optimizer.covariance_method,
        "covariance_role": covariance_role,
        "covariance_regularized": bool(optimizer.is_regularized),
        "predicted_volatility": float(np.sqrt(max(variance, 0))),
        "training_start": history.index.min(),
        "training_end": history.index.max(),
        "estimation_observations": len(history),
        "confidence": confidence,
        "var_daily": float(var),
        "cvar_daily": float(cvar),
        "training_tail_observations": int((scenarios <= -var).sum()),
        "downside_method": downside_method,
        "downside_role": "decision_objective"
        if downside_result is not None
        else "reporting_only",
        "loss_convention": "signed loss = -daily simple return; threshold may be negative",
        "volatility_horizon": "annualized daily covariance; no term structure",
        "downside_horizon": "one trading observation",
    }


def reporting_snapshot(history, weights, config):
    """Fit only held constituents; failure never changes baseline eligibility."""
    active = [a for a, w in weights.items() if w > 0]
    clean = history[active].dropna()
    if len(clean) < config.min_observations:
        return {
            "status": "unavailable",
            "reason": "insufficient_risk_history",
            "estimation_observations": len(clean),
        }
    # Numerical overflow is an unavailable report, not a noisy or invalid matrix.
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        optimizer = PortfolioOptimizer(
            clean,
            covariance_method=config.covariance_method,
            risk_free_rate=config.risk_free_rate,
            seed=config.random_seed,
        )
        return risk_snapshot(
            clean, weights, optimizer, covariance_role="reporting_only"
        )


def valid_forecast_boundary(forecast, as_of):
    """Missing or invalid custom snapshot dates cannot establish ex-ante timing."""
    try:
        start = pd.Timestamp(forecast.get("training_start"))
        end = pd.Timestamp(forecast.get("training_end"))
        return bool(
            pd.notna(start)
            and pd.notna(end)
            and start.tz is None
            and end.tz is None
            and start == start.normalize()
            and end == end.normalize()
            and start <= end <= pd.Timestamp(as_of)
        )
    except (TypeError, ValueError):
        return False
