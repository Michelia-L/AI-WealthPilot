"""
Liability modeling for LDI surplus optimization (Sharpe & Tint 1990).

Every liability is a cash-flow stream ``[(amount, years), ...]`` with two
distinct rates:

- the **discount rate** y — the liability discount rate (flat risk-free
  leg, or the ChinaBond treasury curve {tenor: y(t)} when available),
  used to present-value the stream;
- the **growth rate** g — the escalation rate of inflation-linked cash
  flows (e.g. retirement income stated in today's money).

Three input channels feed the same downstream math:

- explicit: the caller provides the liability ratio k = L/A and the
  liability duration directly (liability drift μ_L = resolved g);
- profile goals: nominal fixed targets (consistent with the IPS TVM
  treatment) — PV-discounted at y, drift μ_L = y;
- retirement income: annual income in today's money from year t0+1 to
  t0+n, inflation-linked at g — PV-discounted at y, drift μ_L = g.

The liability *return* process has two estimators, tried in order:

1. **Curve-based** (preferred, ``estimate_liability_stats_from_curve``):
   first-order duration exposure to the ChinaBond curve history —

       r_L,t ≈ −D_L · Δy_t(D_L)

   where y_t(D_L) is the curve rate interpolated at the liability
   duration each day. σ_L and the asset-liability covariances come
   straight from yield changes (same source as discounting);
2. **Duration-scaled bond proxy** (fallback, ``estimate_liability_stats``):

       r_L = μ_L + λ · (r_p − μ_p),   λ = D_L / D_proxy

   so that σ_L = λ·σ_p and Cov(assets, L) = λ·Cov(assets, proxy) —
   every quantity is estimated from the fetched proxy series rather
   than hand-set correlations.

All annualization follows the optimizer's convention: mean × 252,
covariance × 252 on daily simple returns.
"""

from typing import Optional

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR
from src.data.yield_curve import rate_at

# One liability cash flow: (amount, years_from_now). Amounts are nominal
# unless the caller grows them via stream_to_liability's growth_rate.
Flow = tuple[float, int]


def stream_to_liability(
    flows: list[Flow],
    discount_rate: "float | dict[float, float]",
    growth_rate: float = 0.0,
) -> tuple[float, float]:
    """Present value and Macaulay duration of a cash-flow stream.

    Each flow ``(amount, t)`` is first grown at ``growth_rate`` (use a
    non-zero rate only for amounts stated in today's money — inflation-
    linked liabilities such as retirement income) and then discounted:
    PV_t = amount·(1+g)^t / (1+y)^t, where y is either the flat
    ``discount_rate`` or the curve-interpolated y(t) when
    ``discount_rate`` is a {tenor: rate} dict.

    Args:
        flows: List of (amount, years_from_now) tuples.
        discount_rate: Flat annual liability discount rate, or a yield
            curve {tenor_years: rate_decimal} (e.g. the ChinaBond
            treasury curve from src.data.yield_curve).
        growth_rate: Annual escalation rate g of the cash flows (0 for
            nominal fixed amounts).

    Returns:
        Tuple of (present_value, macaulay_duration_years).

    Raises:
        ValueError: When the stream is empty or all amounts are zero.
    """
    positive = [(float(a), int(t)) for a, t in flows if float(a) > 0]
    if not positive:
        raise ValueError("Liability derivation requires at least one "
                         "cash flow with a positive amount.")

    pv = 0.0
    weighted_years = 0.0
    for amount, years in positive:
        nominal = amount * (1.0 + growth_rate) ** years
        y = (
            rate_at(discount_rate, years)
            if isinstance(discount_rate, dict)
            else discount_rate
        )
        discounted = nominal / (1.0 + y) ** years
        pv += discounted
        weighted_years += years * discounted

    duration = weighted_years / pv if pv > 0 else 0.0
    return pv, duration


def retirement_income_stream(
    years_to_retirement: int,
    distribution_years: int,
    annual_income: float,
) -> list[Flow]:
    """Retirement income as an inflation-linked liability stream.

    The desired income is stated in today's money; cash flows run from
    the first retirement year (t0 + 1) through the planning horizon
    (t0 + n). Callers pass the inflation growth rate to
    ``stream_to_liability`` so the stream escalates with the client's
    personal inflation segment.

    Args:
        years_to_retirement: Years from today until retirement (t0).
        distribution_years: Years of retirement withdrawals (n).
        annual_income: Desired annual income in today's money.

    Returns:
        List of (annual_income, t) flows for t in [t0+1, t0+n].
    """
    start = years_to_retirement + 1
    stop = years_to_retirement + distribution_years
    return [(float(annual_income), t) for t in range(start, stop + 1)]


def goals_to_liability(
    goals: list[dict],
    discount_rate: "float | dict[float, float]",
) -> tuple[float, float]:
    """Present value and Macaulay duration of a goal liability stream.

    Each goal is a single nominal cash flow: ``target_amount`` due in
    ``years`` years (consistent with the IPS TVM treatment — nominal
    targets, no growth), discounted at the flat rate or curve supplied.

    Args:
        goals: List of dicts with 'target_amount' and 'years' keys
            (the shape stored in a client profile).
        discount_rate: Flat annual liability discount rate, or a yield
            curve {tenor_years: rate_decimal}.

    Returns:
        Tuple of (present_value, macaulay_duration_years).

    Raises:
        ValueError: When there are no goals or all amounts are zero.
    """
    flows = [
        (float(g.get("target_amount", 0.0)), int(g.get("years", 0)))
        for g in goals
    ]
    return stream_to_liability(flows, discount_rate, growth_rate=0.0)


def estimate_liability_stats(
    proxy_daily: pd.Series,
    assets_daily: pd.DataFrame,
    proxy_duration: float,
    liability_duration: float,
    growth_rate: float,
) -> tuple[float, float, np.ndarray]:
    """Liability return statistics via the duration-scaled proxy model.

    r_L = μ_L + λ·(r_p − μ_p) with λ = D_L / D_proxy, hence:

        σ_L  = λ · σ_p
        Cov_i = λ · Cov(asset_i, proxy)

    Args:
        proxy_daily: Daily simple returns of the bond proxy, date-aligned
            with ``assets_daily``.
        assets_daily: Daily simple returns of the investable assets.
        proxy_duration: Approximate effective duration of the proxy
            (LDI_PROXY_DURATIONS).
        liability_duration: Liability duration in years.
        growth_rate: The liability drift μ_L (growth g for inflation-
            linked streams, the discount rate y for nominal ones).

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


def _date_index(idx) -> pd.DatetimeIndex:
    """Normalize a date-like index to tz-naive midnight timestamps."""
    idx = pd.to_datetime(idx)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def estimate_liability_stats_from_curve(
    curve_history: pd.DataFrame,
    assets_daily: pd.DataFrame,
    liability_duration: float,
    growth_rate: float,
    min_points: int = 60,
) -> Optional[tuple[float, float, np.ndarray]]:
    """Liability return statistics from yield-curve history.

    First-order duration exposure: the liability PV moves opposite to
    yield changes at its duration point,

        r_L,t = −D_L · Δy_t(D_L)

    where y_t(D_L) is the curve rate interpolated at
    ``liability_duration`` on each curve date (``rate_at`` semantics:
    linear between nodes, flat beyond the ends). Convexity is ignored
    — disclosed as a first-order approximation.

    Args:
        curve_history: Daily yield history, date index × float tenor
            columns, decimal rates (fetch_china_treasury_curve_history).
        assets_daily: Daily simple returns of the investable assets.
        liability_duration: Liability duration D_L in years.
        growth_rate: The liability drift μ_L (unchanged semantics:
            growth g for inflation-linked streams, y for nominal ones).
        min_points: Minimum aligned trading days required; below this
            the estimate is considered unreliable.

    Returns:
        Tuple of (mu_L, sigma_L, cov_vector) — annualized, cov_vector
        aligned to ``assets_daily.columns`` — or None when the aligned
        overlap is shorter than ``min_points`` (caller then falls back
        to the duration-scaled proxy model).
    """
    if curve_history is None or curve_history.empty:
        return None

    y_t = curve_history.apply(
        lambda row: rate_at(row.dropna().to_dict(), liability_duration),
        axis=1,
    ).dropna()
    r_l = (-liability_duration * y_t.diff()).dropna()
    r_l.index = _date_index(r_l.index)
    r_l = r_l[~r_l.index.duplicated(keep="last")]
    if len(r_l) < min_points:
        return None

    assets = assets_daily.copy()
    assets.index = _date_index(assets.index)
    joined = assets.join(r_l.rename("__liab__"), how="inner").dropna()
    if len(joined) < min_points:
        return None

    asset_vals = joined[assets_daily.columns].values  # (S, N)
    liab_vals = joined["__liab__"].values
    cov_matrix = np.cov(asset_vals.T, liab_vals)  # (N+1, N+1)

    sigma_L = float(np.sqrt(cov_matrix[-1, -1] * TRADING_DAYS_PER_YEAR))
    cov_vec = cov_matrix[:-1, -1] * TRADING_DAYS_PER_YEAR

    return growth_rate, sigma_L, cov_vec
