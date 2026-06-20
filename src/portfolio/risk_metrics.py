"""
Risk and performance metrics for portfolio analysis.

Computes standard risk-adjusted return measures and tail-risk
indicators used in portfolio evaluation and wealth management.

References:
    - CFA L1/L3: Quantitative Methods & Portfolio Management
    - Basel III framework for VaR / CVaR
"""

import numpy as np
import pandas as pd
from typing import Optional

from src.config import RISK_FREE_RATE, TRADING_DAYS_PER_YEAR


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    """Annualized Sharpe ratio: (R_p - R_f) / σ_p.

    Args:
        returns: Daily portfolio return series.
        risk_free_rate: Annual risk-free rate.

    Returns:
        Annualized Sharpe ratio.
    """
    excess = returns.mean() * TRADING_DAYS_PER_YEAR - risk_free_rate
    vol = returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    return excess / vol if vol > 0 else 0.0


def sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    """Annualized Sortino ratio using downside deviation (MAR=0).

    Args:
        returns: Daily portfolio return series.
        risk_free_rate: Annual risk-free rate.

    Returns:
        Annualized Sortino ratio.
    """
    excess = returns.mean() * TRADING_DAYS_PER_YEAR - risk_free_rate
    downside_diff = np.minimum(returns.values, 0.0)
    n = len(returns)
    if n > 1:
        # Downside deviation uses full sample denominator (N-1)
        downside_vol = np.sqrt(np.sum(downside_diff ** 2) / (n - 1)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        downside_vol = 0.0
    return excess / downside_vol if downside_vol > 0 else 0.0


def max_drawdown(prices: pd.Series) -> dict:
    """Largest peak-to-trough decline in portfolio value.

    Args:
        prices: Price or cumulative value series (not returns).

    Returns:
        Dict with 'max_drawdown' (negative pct), 'peak_date', 'trough_date'.
    """
    cummax = prices.cummax()
    drawdown = (prices - cummax) / cummax
    trough_idx = drawdown.idxmin()
    peak_idx = prices[:trough_idx].idxmax()
    return {
        "max_drawdown": float(drawdown.min()),
        "peak_date": peak_idx,
        "trough_date": trough_idx,
    }


def value_at_risk(
    returns: pd.Series,
    confidence: float = 0.95,
    method: str = "historical",
) -> float:
    """Value at Risk at a given confidence level.

    Args:
        returns: Daily portfolio return series.
        confidence: Confidence level (e.g. 0.95).
        method: 'historical' or 'parametric' (Gaussian).

    Returns:
        VaR as a positive number (loss magnitude).
    """
    if method == "historical":
        return -float(np.percentile(returns, (1 - confidence) * 100))
    elif method == "parametric":
        from scipy.stats import norm
        z = norm.ppf(1 - confidence)
        # VaR = -(μ + z_α × σ)
        return -(returns.mean() + z * returns.std())
    else:
        raise ValueError(f"Unknown method: {method}")


def conditional_var(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """CVaR / Expected Shortfall: average loss beyond VaR threshold.

    Args:
        returns: Daily portfolio return series.
        confidence: Confidence level (e.g. 0.95).

    Returns:
        CVaR as a positive number.
    """
    var = value_at_risk(returns, confidence, method="historical")
    tail_losses = returns[returns <= -var]
    return -float(tail_losses.mean()) if len(tail_losses) > 0 else var


def compute_all_metrics(
    returns: pd.Series,
    prices: Optional[pd.Series] = None,
) -> dict:
    """Compute all risk metrics at once for dashboard use.

    Args:
        returns: Daily return series.
        prices: Optional price series (needed for max drawdown).

    Returns:
        Dict of all computed metrics.
    """
    metrics = {
        "annualized_return": float(returns.mean() * TRADING_DAYS_PER_YEAR),
        "annualized_volatility": float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)),
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "var_95": value_at_risk(returns, 0.95),
        "cvar_95": conditional_var(returns, 0.95),
        "skewness": float(returns.skew()),
        "kurtosis": float(returns.kurtosis()),
    }
    if prices is not None:
        dd = max_drawdown(prices)
        metrics["max_drawdown"] = dd["max_drawdown"]
        metrics["peak_date"] = str(dd["peak_date"])
        metrics["trough_date"] = str(dd["trough_date"])
    return metrics
