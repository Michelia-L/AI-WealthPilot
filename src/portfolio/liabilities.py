"""
Liability modeling for LDI surplus optimization (Sharpe & Tint 1990).

Two liability-input channels feed the same downstream math:

- explicit: the caller provides the liability ratio k = L/A and the
  liability duration directly;
- profile goals: each investment goal (target_amount at t years) is one
  liability cash flow; the stream is discounted at the liability growth
  rate into a present value and a Macaulay duration.

The liability *return* process is modeled by duration-scaling a bond
proxy (no yield-curve feed):

    r_L = g + λ · (r_p − μ_p),   λ = D_L / D_proxy

so that μ_L = g (the liability growth/discount rate), σ_L = λ·σ_p and
Cov(assets, L) = λ·Cov(assets, proxy) — every quantity is estimated
from the fetched proxy series rather than hand-set correlations.

All annualization follows the optimizer's convention: mean × 252,
covariance × 252 on daily simple returns.
"""

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR


def goals_to_liability(
    goals: list[dict],
    discount_rate: float,
) -> tuple[float, float]:
    """Present value and Macaulay duration of a goal liability stream.

    Each goal is a single future cash flow: ``target_amount`` due in
    ``years`` years, discounted at the liability growth rate.

    Args:
        goals: List of dicts with 'target_amount' and 'years' keys
            (the shape stored in a client profile).
        discount_rate: Annual discount rate (the resolved liability
            growth rate).

    Returns:
        Tuple of (present_value, macaulay_duration_years).

    Raises:
        ValueError: When there are no goals or all amounts are zero.
    """
    flows = [
        (float(g.get("target_amount", 0.0)), int(g.get("years", 0)))
        for g in goals
        if float(g.get("target_amount", 0.0)) > 0
    ]
    if not flows:
        raise ValueError("Liability derivation requires at least one goal "
                         "with a positive target amount.")

    pv = 0.0
    weighted_years = 0.0
    for amount, years in flows:
        discounted = amount / (1.0 + discount_rate) ** years
        pv += discounted
        weighted_years += years * discounted

    duration = weighted_years / pv if pv > 0 else 0.0
    return pv, duration


def estimate_liability_stats(
    proxy_daily: pd.Series,
    assets_daily: pd.DataFrame,
    proxy_duration: float,
    liability_duration: float,
    growth_rate: float,
) -> tuple[float, float, np.ndarray]:
    """Liability return statistics via the duration-scaled proxy model.

    r_L = g + λ·(r_p − μ_p) with λ = D_L / D_proxy, hence:

        μ_L  = g
        σ_L  = λ · σ_p
        Cov_i = λ · Cov(asset_i, proxy)

    Args:
        proxy_daily: Daily simple returns of the bond proxy, date-aligned
            with ``assets_daily``.
        assets_daily: Daily simple returns of the investable assets.
        proxy_duration: Approximate effective duration of the proxy
            (LDI_PROXY_DURATIONS).
        liability_duration: Liability duration in years.
        growth_rate: Annualized liability growth rate g.

    Returns:
        Tuple of (mu_L, sigma_L, cov_vector) — annualized, cov_vector
        aligned to ``assets_daily.columns``.
    """
    lam = liability_duration / proxy_duration

    asset_vals = assets_daily.values  # (S, N)
    proxy_vals = np.asarray(proxy_daily, dtype=float)
    cov_matrix = np.cov(asset_vals.T, proxy_vals)  # (N+1, N+1)

    sigma_L = lam * float(np.sqrt(cov_matrix[-1, -1] * TRADING_DAYS_PER_YEAR))

    # Annualized asset-proxy covariance vector, then duration scaling.
    cov_vec = lam * cov_matrix[:-1, -1] * TRADING_DAYS_PER_YEAR

    return growth_rate, sigma_L, cov_vec
