"""Optimization method runners — the engine-dispatch service layer.

Sits behind POST /api/portfolio/optimize: each runner takes a prepared
returns frame plus already-resolved inputs (request scalars, and auxiliary
data such as AUM weights or discount curves injected by the router) and
returns the shared tuple::

    (optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra)

``extra`` is a plain dict of method-specific insight fields (the BLInsight /
SurplusInsight payloads) or ``{}`` — the API layer wraps it in the response
schema. No FastAPI, schema, or cache imports live here; request validation
and HTTP error mapping stay in api.routers.portfolio.
"""

from typing import Callable, Optional

import numpy as np
import pandas as pd

from src.config import (
    CME_INFLATION_ASSUMPTION,
    DEFAULT_ASSET_CLASSES,
    LDI_PROXY_DURATIONS,
)
from src.data.yield_curve import rate_at
from src.portfolio.inflation import resolve_personal_inflation, suggest_inflation_preset
from src.portfolio.liabilities import (
    estimate_liability_stats,
    estimate_liability_stats_from_curve,
    goals_to_liability,
    retirement_income_stream,
    stream_to_liability,
)
from src.portfolio.optimizer import BlackLittermanOptimizer, PortfolioOptimizer
from src.portfolio.views import ViewInput, ViewProcessor

FRONTIER_POINTS = 50
RESAMPLED_FRONTIER_POINTS = 20
RANDOM_PORTFOLIOS = 1000

# (optimizer, selected, max_sharpe, min_vol, frontier, random_portfolios, extra)
OptimizeRunResult = tuple[
    PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict
]


def run_mvo(
    returns: pd.DataFrame,
    *,
    method: str,
    mode: str,
    allow_short: bool,
    n_simulations: int,
    risk_free_rate: float,
    group_constraints: Optional[dict] = None,
    expected_returns: Optional[pd.Series] = None,
) -> OptimizeRunResult:
    """Traditional or Resampled (Michaud) MVO.

    When group_constraints is given (classic MVO only), the selected
    portfolio honors those per-group min/max limits while the max_sharpe /
    min_vol control portfolios stay unconstrained as a cost reference.
    """
    optimizer = PortfolioOptimizer(
        returns, risk_free_rate=risk_free_rate, expected_returns=expected_returns
    )
    max_sharpe = optimizer.maximize_sharpe(allow_short=allow_short)
    min_vol = optimizer.minimize_volatility(allow_short=allow_short)

    if method == "resampled":
        if mode == "max-sharpe":
            selected = optimizer.resampled_maximize_sharpe(
                n_simulations=n_simulations, allow_short=allow_short
            )
        else:
            selected = optimizer.resampled_minimize_volatility(
                n_simulations=n_simulations, allow_short=allow_short
            )
        frontier = optimizer.resampled_efficient_frontier(
            n_points=RESAMPLED_FRONTIER_POINTS,
            n_simulations=n_simulations,
            allow_short=allow_short,
        )
    else:
        if group_constraints:
            if mode == "max-sharpe":
                selected = optimizer.maximize_sharpe(
                    allow_short=allow_short, group_constraints=group_constraints
                )
            else:
                selected = optimizer.optimize_with_asset_class_constraints(
                    group_constraints, allow_short=allow_short
                )
        else:
            selected = max_sharpe if mode == "max-sharpe" else min_vol
        frontier = optimizer.efficient_frontier(
            n_points=FRONTIER_POINTS, allow_short=allow_short
        )

    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, {}


def run_cvar(
    returns: pd.DataFrame,
    *,
    mode: str,
    allow_short: bool,
    cvar_confidence: float,
    risk_free_rate: float,
    expected_returns: Optional[pd.Series] = None,
) -> OptimizeRunResult:
    """Mean-CVaR optimization (Rockafellar-Uryasev LP on daily scenarios).

    A single frontier solve feeds both the chart and the max-STARR
    reference point. Mode mapping: min-vol → the global min-CVaR
    portfolio; max-sharpe → the frontier point maximizing
    (return − rf) / CVaR (Stable Tail Adjusted Return Ratio).
    """
    optimizer = PortfolioOptimizer(
        returns, risk_free_rate=risk_free_rate, expected_returns=expected_returns
    )
    beta = cvar_confidence

    frontier = optimizer.cvar_efficient_frontier(
        n_points=FRONTIER_POINTS, beta=beta, allow_short=allow_short
    )
    min_cvar = optimizer.minimize_cvar(beta=beta, allow_short=allow_short)

    # Max-STARR reference: the frontier point with the best return per
    # unit of tail loss. cvar≈0 rows are masked before the ratio so a
    # degenerate zero-tail-loss point cannot win via inf; falls back to
    # the min-CVaR portfolio when no finite ratio remains (the downstream
    # empty-frontier check then surfaces a clean 422).
    max_ratio = min_cvar
    if not frontier.empty:
        weight_cols = [
            c
            for c in frontier.columns
            if c not in ("return", "volatility", "sharpe", "cvar")
        ]
        safe_cvar = frontier["cvar"].where(frontier["cvar"] > 1e-12)
        ratio = ((frontier["return"] - optimizer.risk_free_rate) / safe_cvar).dropna()
        if not ratio.empty:
            best = frontier.loc[ratio.idxmax()]
            max_ratio = {
                "weights": {name: float(best[name]) for name in weight_cols},
                "return": float(best["return"]),
                "volatility": float(best["volatility"]),
                "sharpe": float(best["sharpe"]),
                "cvar": float(best["cvar"]),
                "success": True,
            }

    max_sharpe = max_ratio
    min_vol = min_cvar
    selected = max_ratio if mode == "max-sharpe" else min_cvar
    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, {}


def run_risk_parity(
    returns: pd.DataFrame,
    *,
    allow_short: bool,
    risk_free_rate: float,
    expected_returns: Optional[pd.Series] = None,
) -> OptimizeRunResult:
    """Risk parity (Equal Risk Contribution).

    The ERC portfolio is return-agnostic, so mode does not apply: the
    selected slot carries the ERC portfolio while the max_sharpe/min_vol
    slots hold classic MVO portfolios as benchmarks on the same efficient
    frontier. Long-only by construction (Spinu log-barrier).
    """
    if allow_short:
        raise ValueError(
            "Risk parity is long-only by construction (Spinu log-barrier)."
        )
    optimizer = PortfolioOptimizer(
        returns,
        risk_free_rate=risk_free_rate,
        expected_returns=expected_returns,
    )
    selected = optimizer.risk_parity()
    max_sharpe = optimizer.maximize_sharpe(allow_short=False)
    min_vol = optimizer.minimize_volatility(allow_short=False)
    frontier = optimizer.efficient_frontier(n_points=FRONTIER_POINTS, allow_short=False)
    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, {}


def bl_view_impacts(
    returns: pd.DataFrame,
    optimizer: BlackLittermanOptimizer,
    view_inputs: list[ViewInput],
    names: list[str],
    *,
    allow_short: bool,
    risk_free_rate: float,
    locale: str = "zh",
) -> list[dict]:
    """Per-view impact: L1 weight distance between the prior portfolio
    (max-Sharpe under the bare prior) and the max-Sharpe portfolio with
    only that single view applied.

    Disclosure only — the combined posterior above is what gets
    optimized; this answers "how much did each view actually move".
    """
    prior_series = pd.Series(optimizer.Pi, index=names)
    base = PortfolioOptimizer(
        returns,
        risk_free_rate=risk_free_rate,
        expected_returns=prior_series,
    )
    w0 = base.maximize_sharpe(allow_short=allow_short)["weights"]

    impacts: list[dict] = []
    for v in view_inputs:
        single = BlackLittermanOptimizer(
            returns,
            risk_free_rate=risk_free_rate,
            market_cap_weights=optimizer.market_cap_weights,
            delta=optimizer.delta,
            tau=optimizer.tau,
        )
        if optimizer.prior_source != "equilibrium":
            single.use_prior(optimizer.Pi, optimizer.prior_source)
        single.apply_views([v], locale=locale)
        w1 = single.bl_maximize_sharpe(allow_short=allow_short)["weights"]
        impact = float(sum(abs(w1[n] - w0[n]) for n in names))
        if v.view_type == "relative":
            label = f"{v.asset_long} > {v.asset_short} ({v.expected_return:+.1%})"
        else:
            label = f"{v.asset_long} → {v.expected_return:.1%}"
        impacts.append({"label": label, "impact": impact})
    return impacts


def run_bl(
    returns: pd.DataFrame,
    *,
    keys: list[str],
    views: list[dict],
    mode: str,
    allow_short: bool,
    risk_free_rate: float,
    delta: float,
    tau: float,
    custom_market_weights: Optional[dict[str, float]],
    resolve_aum_weights: Callable[[], Optional[np.ndarray]],
    expected_returns: Optional[pd.Series] = None,
    cme_fallback: Optional[list[str]] = None,
    locale: str = "zh",
) -> OptimizeRunResult:
    """Black-Litterman optimization. Requires at least one view.

    Prior: CAPM equilibrium by default; when expected_return_source="cme"
    the CME vector replaces it (uncovered assets re-anchor to their
    equilibrium returns, disclosed via cme_fallback_assets).

    Market-cap weights resolve custom > aum > equal; ``resolve_aum_weights``
    is called lazily (only when custom weights are absent or all-zero) so
    the caller's TTL-cached AUM fetch doesn't run when it isn't needed.
    ``views`` are plain dicts (BLViewInput dumps) keyed by asset class key.
    """
    if not views:
        raise ValueError("Black-Litterman optimization requires at least one view.")

    names = [DEFAULT_ASSET_CLASSES[k]["name"] for k in keys]
    name_of = dict(zip(keys, names, strict=False))

    market_weights = None
    weights_source = "equal"
    if custom_market_weights:
        w = np.array([custom_market_weights.get(k, 0.0) for k in keys], dtype=float)
        if w.sum() > 0:
            market_weights = w / w.sum()
            weights_source = "custom"
    if market_weights is None:
        # ETF AUM as a rough market-cap proxy, resolved lazily by the
        # caller (TTL-cached there) so the fetch only happens when needed.
        aum_weights = resolve_aum_weights()
        if aum_weights is not None:
            market_weights = aum_weights
            weights_source = "aum"

    optimizer = BlackLittermanOptimizer(
        returns,
        risk_free_rate=risk_free_rate,
        market_cap_weights=market_weights,
        delta=delta,
        tau=tau,
    )

    if expected_returns is not None:
        # CME prior: covered assets take the CME value; uncovered ones
        # re-anchor to their equilibrium return (BL-consistent fallback).
        equilibrium = optimizer.implied_equilibrium_returns()
        fallback = set(cme_fallback or [])
        prior = np.array(
            [
                equilibrium[i] if name in fallback else float(expected_returns[name])
                for i, name in enumerate(names)
            ]
        )
        optimizer.use_prior(prior, source="cme")

    view_inputs = [
        ViewInput(
            view_type=v["view_type"],
            asset_long=name_of.get(v["asset_long"], v["asset_long"]),
            asset_short=(
                name_of.get(v["asset_short"], v["asset_short"])
                if v.get("asset_short")
                else None
            ),
            expected_return=v["expected_return"],
            confidence=v["confidence"],
        )
        for v in views
    ]
    optimizer.apply_views(view_inputs, locale=locale)
    max_sharpe = optimizer.bl_maximize_sharpe(allow_short=allow_short)
    min_vol = optimizer.bl_minimize_volatility(allow_short=allow_short)
    frontier = optimizer.bl_efficient_frontier(
        n_points=FRONTIER_POINTS, allow_short=allow_short
    )

    selected = max_sharpe if mode == "max-sharpe" else min_vol
    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)

    equilibrium = optimizer.implied_equilibrium_returns()
    posterior = optimizer.mu_bl

    # Diagnostics: contradictory relative-view cycles + far-from-prior views
    view_processor = ViewProcessor(names, locale)
    sigma_vec = np.sqrt(np.diag(optimizer.cov_matrix.values))
    bl_warnings = view_processor.detect_relative_cycles(
        view_inputs
    ) + view_processor.divergence_warnings(view_inputs, optimizer.Pi, sigma_vec)
    impacts = bl_view_impacts(
        returns,
        optimizer,
        view_inputs,
        names,
        allow_short=allow_short,
        risk_free_rate=risk_free_rate,
        locale=locale,
    )

    extra = {
        "equilibrium_returns": {
            n: float(r) for n, r in zip(names, equilibrium, strict=False)
        },
        "posterior_returns": {
            n: float(r) for n, r in zip(names, posterior, strict=False)
        },
        "prior_source": optimizer.prior_source,
        "prior_returns": (
            {n: float(r) for n, r in zip(names, optimizer.Pi, strict=False)}
            if optimizer.prior_source == "cme"
            else None
        ),
        "warnings": bl_warnings,
        "view_impacts": impacts,
        "market_weights_source": weights_source,
    }
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra


def run_surplus(
    returns: pd.DataFrame,
    *,
    mode: str,
    allow_short: bool,
    risk_free_rate: float,
    surplus_raw: dict,
    proxy_returns: Optional[pd.Series],
    discount_curve: Optional[dict[float, float]],
    discount_source: str,
    curve_history: Optional[pd.DataFrame],
    expected_returns: Optional[pd.Series] = None,
) -> OptimizeRunResult:
    """LDI surplus optimization (Sharpe-Tint): assets minus liabilities.

    Three liability channels — explicit ratio/duration, profile goals
    (nominal, discounted at rf, drift μ_L = rf), and the retirement
    income stream (inflation-linked at the resolved growth g, discounted
    at rf, drift μ_L = g). Liability risk stats prefer the curve-based
    estimator (ChinaBond yield-change history at the liability duration),
    falling back to the duration-scaled bond proxy; returns the standard
    tuple with a SurplusInsight payload dict in the extra slot.

    ``discount_curve`` / ``curve_history`` are resolved and injected by the
    caller (TTL-cached there); ``discount_source`` is the caller's label
    ("china_treasury_curve" or "flat_risk_free").
    """
    rf = risk_free_rate

    # Liability growth rate g — the escalation rate of inflation-linked
    # cash flows (the retirement stream; the manual channel also uses it
    # as drift). The liability discount rate y is always the risk-free
    # leg rf, and nominal goal streams drift at y — see liabilities.py.
    growth_source = surplus_raw["growth_source"]
    if growth_source == "risk_free":
        growth = rf
    elif growth_source == "custom":
        growth = float(surplus_raw["custom_growth"])
    else:  # inflation — personal preset (age-suggested on profile channels)
        preset = surplus_raw.get("inflation_preset")
        if preset is None:
            preset = suggest_inflation_preset(surplus_raw.get("age"))
        growth = resolve_personal_inflation(CME_INFLATION_ASSUMPTION, preset)

    # Liability spec per channel: ratio k = L/A, duration, drift μ_L.
    # Discounting: ChinaBond treasury curve when the provider cascade has
    # one, otherwise the flat risk-free leg.
    discount = discount_curve if discount_curve is not None else rf

    source = surplus_raw["source"]
    cash_flows: Optional[int] = None
    horizon: Optional[float] = None
    if source == "manual":
        k = surplus_raw["liability_ratio"]
        duration = surplus_raw["liability_duration"]
        mu_L = growth
    elif source == "profile":
        pv, duration = goals_to_liability(surplus_raw["goals"], discount)
        k = pv / surplus_raw["investable_assets"]
        mu_L = rf
        positive = [
            g for g in surplus_raw["goals"] if float(g.get("target_amount", 0.0)) > 0
        ]
        cash_flows = len(positive)
        horizon = float(max(int(g.get("years", 0)) for g in positive))
    else:  # retirement — inflation-linked income stream
        flows = retirement_income_stream(
            surplus_raw["years_to_retirement"],
            surplus_raw["distribution_years"],
            surplus_raw["annual_income"],
        )
        pv, duration = stream_to_liability(flows, discount, growth)
        k = pv / surplus_raw["asset_value"]
        mu_L = growth
        cash_flows = len(flows)
        horizon = float(flows[-1][1])

    # Representative discount rate: curve rate at the liability duration.
    discount_rate_value = (
        float(rate_at(discount_curve, duration))
        if discount_curve is not None
        else float(rf)
    )

    # Liability risk stats: prefer the curve-based estimator (first-order
    # duration exposure to ChinaBond yield changes — same source as
    # discounting); fall back to the duration-scaled bond proxy when the
    # curve history is unavailable or too short to align.
    sigma_l_source = "bond_proxy"
    proxy_key = surplus_raw["proxy"]
    stats = None
    if curve_history is not None:
        stats = estimate_liability_stats_from_curve(
            curve_history,
            returns,
            liability_duration=duration,
            growth_rate=mu_L,
        )
    if stats is not None:
        mu_L, sigma_L, cov_vec = stats
        sigma_l_source = "china_treasury_curve"
    else:
        if proxy_returns is None:
            # Proxy already sits inside the requested universe.
            proxy_returns = returns[DEFAULT_ASSET_CLASSES[proxy_key]["name"]]
        mu_L, sigma_L, cov_vec = estimate_liability_stats(
            proxy_returns,
            returns,
            proxy_duration=LDI_PROXY_DURATIONS[proxy_key],
            liability_duration=duration,
            growth_rate=mu_L,
        )

    optimizer = PortfolioOptimizer(
        returns, risk_free_rate=risk_free_rate, expected_returns=expected_returns
    )
    max_sharpe = optimizer.maximize_surplus_sharpe(
        k, mu_L, sigma_L, cov_vec, allow_short=allow_short
    )
    min_vol = optimizer.minimize_surplus_volatility(
        k, mu_L, sigma_L, cov_vec, allow_short=allow_short
    )
    frontier = optimizer.surplus_efficient_frontier(
        k,
        mu_L,
        sigma_L,
        cov_vec,
        n_points=FRONTIER_POINTS,
        allow_short=allow_short,
    )
    selected = max_sharpe if mode == "max-sharpe" else min_vol
    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)

    extra = {
        "liability_ratio": float(k),
        "funding_ratio": float(1.0 / k),
        "liability_duration": float(duration),
        "liability_growth": float(mu_L),
        "discount_rate": discount_rate_value,
        "discount_source": discount_source,
        "sigma_l_source": sigma_l_source,
        "proxy": proxy_key,
        "source": source,
        "cash_flows": cash_flows,
        "horizon_years": horizon,
    }
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra
