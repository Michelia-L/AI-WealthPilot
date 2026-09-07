"""Metrics for a complete, daily OOS series, with an explicit gap policy."""

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR


def compute_metrics(
    returns: pd.Series, risk_free_rate: float, *, periods_complete: bool = True
) -> dict:
    metrics = dict.fromkeys(
        (
            "total_return",
            "cagr",
            "annualized_volatility",
            "sharpe",
            "sortino",
            "max_drawdown",
            "best_day",
            "worst_day",
        )
    )
    metrics.update(
        observations=int(returns.notna().sum()),
        missing_observations=int(returns.isna().sum()),
        complete=bool(periods_complete and len(returns) and returns.notna().all()),
    )
    # Removing failed periods would bias the comparison. Do not publish a
    # whole-run performance statistic if any requested observations are unknown.
    if not metrics["complete"]:
        return metrics
    nav = (1 + returns).cumprod()
    years = len(returns) / TRADING_DAYS_PER_YEAR
    annual_vol = returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
    excess = returns - np.expm1(np.log1p(risk_free_rate) / TRADING_DAYS_PER_YEAR)
    downside = np.sqrt(np.minimum(excess, 0).pow(2).mean())
    # Include the initial capital so a loss on the first day is a drawdown.
    peaks = nav.cummax().clip(lower=1.0)
    metrics.update(
        total_return=float(nav.iloc[-1] - 1),
        cagr=float(nav.iloc[-1] ** (1 / years) - 1),
        annualized_volatility=float(annual_vol) if np.isfinite(annual_vol) else None,
        sharpe=float(excess.mean() * TRADING_DAYS_PER_YEAR / annual_vol)
        if annual_vol > 1e-12
        else None,
        sortino=float(excess.mean() / downside * np.sqrt(TRADING_DAYS_PER_YEAR))
        if downside > 1e-12
        else None,
        max_drawdown=float((nav / peaks - 1).min()),
        best_day=float(returns.max()),
        worst_day=float(returns.min()),
    )
    return metrics
