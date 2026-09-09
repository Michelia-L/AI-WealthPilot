"""Shared annual retirement cash flows for production and offline research."""

from dataclasses import dataclass

import numpy as np


@dataclass
class DistributionTrace:
    paths: np.ndarray
    requested: np.ndarray
    delivered: np.ndarray
    target: np.ndarray
    inflation_factors: np.ndarray
    cuts: np.ndarray
    increases: np.ndarray
    cut_amounts: np.ndarray


def gbm_growth(
    expected_return: float, volatility: float, n_paths: int, years: int, seed: int
) -> np.ndarray:
    """Year-major draws preserve the production simulator's seed convention."""
    rng = np.random.default_rng(seed)
    drift = expected_return - 0.5 * volatility**2
    return np.exp(drift + volatility * rng.standard_normal((years, n_paths)).T)


def distribution_from_growth(
    terminal_values: np.ndarray,
    growth: np.ndarray,
    desired_annual_income: float,
    accum_years: int,
    inflation_rate: float,
    distribution_inflation_rate: float,
    withdrawal_strategy: str = "fixed",
    guardrail_band: float = 0.2,
    guardrail_adjust: float = 0.1,
    *,
    inflation_schedule: np.ndarray | None = None,
) -> DistributionTrace:
    """Apply the existing end-of-year spending convention to supplied gross returns.

    Guardrails deliberately retain the production convention: W0 already has
    one distribution inflation step, and the first tentative withdrawal gets
    another. Triggers use pre-return wealth; depleted paths cannot fund spending.
    Requested spending is tracked separately from cash actually available.
    """
    growth = np.asarray(growth, dtype=float)
    terminal_values = np.asarray(terminal_values, dtype=float)
    if (
        growth.ndim != 2
        or terminal_values.shape != (growth.shape[0],)
        or not np.isfinite(growth).all()
        or (growth < 0).any()
        or not np.isfinite(terminal_values).all()
        or (terminal_values < 0).any()
    ):
        raise ValueError("invalid retirement growth or initial wealth")
    if withdrawal_strategy not in ("fixed", "guardrails"):
        raise ValueError("invalid withdrawal strategy")
    n_paths, years = growth.shape
    rates = np.full(years, distribution_inflation_rate)
    if inflation_schedule is not None:
        rates = np.asarray(inflation_schedule, dtype=float)
        if (
            rates.shape != (years,)
            or not np.isfinite(rates).all()
            or (rates <= -1).any()
        ):
            raise ValueError("invalid distribution inflation schedule")
    factors = (1.0 + inflation_rate) ** accum_years * (
        (1.0 + distribution_inflation_rate) ** np.arange(1, years + 1)
        if inflation_schedule is None
        else np.cumprod(1.0 + rates)
    )
    if not np.isfinite(factors).all() or (factors <= 0).any():
        raise ValueError("invalid cumulative inflation factors")
    target = desired_annual_income * factors
    paths = np.zeros((n_paths, years + 1))
    paths[:, 0] = terminal_values
    requested = np.zeros_like(growth)
    delivered = np.zeros_like(growth)
    cuts = np.zeros_like(growth, dtype=bool)
    increases = np.zeros_like(growth, dtype=bool)
    cut_amounts = np.zeros_like(growth)
    w0 = target[0] if years else 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        wr0 = np.where(terminal_values > 0, w0 / terminal_values, np.inf)
    withdrawals = np.full(n_paths, w0)
    for t in range(years):
        prev = paths[:, t]
        if withdrawal_strategy == "guardrails":
            tentative = withdrawals * (1.0 + rates[t])
            with np.errstate(divide="ignore", invalid="ignore"):
                current_wr = np.where(prev > 0, tentative / prev, np.inf)
            cut = current_wr > wr0 * (1.0 + guardrail_band)
            boost = current_wr < wr0 * (1.0 - guardrail_band)
            # Count only adjustments on paths that still hold wealth.
            cuts[:, t] = cut & (prev > 0)
            increases[:, t] = boost & (prev > 0)
            cut_amounts[:, t] = np.where(cuts[:, t], tentative * guardrail_adjust, 0)
            tentative = np.where(cut, tentative * (1.0 - guardrail_adjust), tentative)
            tentative = np.where(boost, tentative * (1.0 + guardrail_adjust), tentative)
            withdrawals = tentative
        else:
            tentative = target[t]
        available = prev * growth[:, t]
        requested[:, t] = tentative
        delivered[:, t] = np.minimum(tentative, available)
        paths[:, t + 1] = np.maximum(available - tentative, 0)
    if not all(np.isfinite(a).all() for a in (paths, requested, delivered, factors)):
        raise ValueError("nonfinite retirement cash flows")
    return DistributionTrace(
        paths, requested, delivered, target, factors, cuts, increases, cut_amounts
    )
