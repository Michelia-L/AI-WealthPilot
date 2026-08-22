"""
Performance attribution — Brinson-Fachler decomposition with Carino linking.

Decomposes a portfolio's active return vs its benchmark into
allocation / selection / interaction effects per asset group, using the
backtest engine's own rebalancing calendar (monthly spans between
rebalance dates), so the per-span identity holds exactly against the
simulated NAVs:

    A_g = (w_p,g − w_b,g)·(R_b,g − R_b)   allocation (Brinson-Fachler:
                                             credit only for overweighting
                                             groups that beat the total
                                             benchmark — verified against
                                             the authoritative BF/BHB
                                             comparison; BHB's raw R_b,g
                                             baseline overcredits in bull
                                             markets)
    S_g = w_b,g·(R_p,g − R_b,g)           selection
    I_g = (w_p,g − w_b,g)·(R_p,g − R_b,g) interaction

    Σ_g (A+S+I) = R_p,m − R_b,m           (exact per span)

Groups absent from the benchmark use the portfolio's own group return
as the benchmark sleeve (forcing S = I = 0) — the standard BF
convention for non-benchmark holdings.

Cumulative effects are geometrically linked with Carino factors:

    k_m = [ln(1+R_p,m) − ln(1+R_b,m)] / (R_p,m − R_b,m)
    K   = (R_p − R_b) / [ln(1+R_p) − ln(1+R_b)]   (whole window)
    E_total = K · Σ_m (k_m · E_m)

(Per span the log-active difference is k_m × the arithmetic one; the
log differences telescope across spans, and K converts the total back
to arithmetic — so linked effects sum exactly to the cumulative
active return.)

All arithmetic is decimal returns; group labels are machine keys
(equity/bond/alternative/cash/other) — presentation localization lives
in the web dictionary layer.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.config import DEFAULT_ASSET_CLASSES, IPS_ASSET_CLASS_TICKERS
from src.portfolio.risk_constraints import ASSET_GROUPS

logger = logging.getLogger(__name__)

# ticker → asset-class key → group, built once from config.
_TICKER_TO_GROUP: dict[str, str] = {}
for _key, _info in DEFAULT_ASSET_CLASSES.items():
    _group = next(
        (g for g, members in ASSET_GROUPS.items() if _key in members), None
    )
    if _group is not None:
        _TICKER_TO_GROUP[_info["ticker"]] = _group

# IPS asset-class proxies (CME universe) carry different class keys than
# DEFAULT_ASSET_CLASSES — map them onto the same groups so e.g. the CSI 300
# index proxy is equity, not "other".
_IPS_KEY_TO_GROUP = {
    "domestic_equity": "equity",
    "international_equity_dm": "equity",
    "international_equity_hk": "equity",
    "fixed_income": "bond",
    "alternative_gold": "alternative",
    "alternative_reit": "alternative",
    "cash": "cash",
}

for _key, _info in IPS_ASSET_CLASS_TICKERS.items():
    _group = _IPS_KEY_TO_GROUP.get(_key)
    if _group is not None and _info["ticker"] not in _TICKER_TO_GROUP:
        _TICKER_TO_GROUP[_info["ticker"]] = _group


def group_of_ticker(ticker: str) -> str:
    """Map a ticker to its asset group; unmapped tickers land in 'other'."""
    return _TICKER_TO_GROUP.get(ticker, "other")


def monthly_group_series(
    prices: pd.DataFrame, weights: dict[str, float]
) -> list[tuple[dict[str, float], dict[str, float], float]]:
    """Per-span group weights/returns on the NAV engine's calendar.

    The engine resets weights to target at each month's first trading
    day (close), so beginning-of-span weights are the constant target
    weights; span returns are computed from span-boundary price ratios,
    matching _simulate_nav's arithmetic exactly.

    Args:
        prices: Aligned daily price panel (columns = tickers).
        weights: {ticker: target weight}, normalized.

    Returns:
        List of (w_g, R_g, R_total) per span: group → beginning weight,
        group → span return, and the portfolio's span return. Spans with
        zero length (single-day panels) are skipped by construction.
    """
    tickers = list(weights)
    groups = {t: group_of_ticker(t) for t in tickers}
    group_list = sorted({groups[t] for t in tickers})
    w_g = {
        g: sum(weights[t] for t in tickers if groups[t] == g)
        for g in group_list
    }

    periods = prices.index.to_period("M")
    rebal = prices.index[~periods.duplicated()]
    bounds = list(rebal) + [prices.index[-1]]

    rows: list[tuple[dict[str, float], dict[str, float], float]] = []
    for k in range(len(bounds) - 1):
        r0, r1 = bounds[k], bounds[k + 1]
        if not r0 < r1:
            continue
        ratio = (prices.loc[r1, tickers] / prices.loc[r0, tickers]) - 1.0
        R_g = {}
        for g in group_list:
            members = [t for t in tickers if groups[t] == g]
            sleeve = sum(weights[t] * float(ratio[t]) for t in members)
            R_g[g] = sleeve / w_g[g] if w_g[g] > 0 else float("nan")
        R_total = sum(weights[t] * float(ratio[t]) for t in tickers)
        rows.append((w_g, R_g, float(R_total)))
    return rows


def _carino_factor(r_p: float, r_b: float) -> float:
    """Carino per-span factor k = [ln(1+R_p) − ln(1+R_b)] / (R_p − R_b),
    with the exact limit 1/(1+R) when the two returns coincide."""
    if abs(r_p - r_b) < 1e-12:
        return 1.0 / (1.0 + r_p)
    return (np.log(1.0 + r_p) - np.log(1.0 + r_b)) / (r_p - r_b)


def brinson_attribution(
    port_rows: list[tuple[dict[str, float], dict[str, float], float]],
    bench_rows: list[tuple[dict[str, float], dict[str, float], float]],
) -> Optional[dict]:
    """Brinson-Fachler attribution over the aligned span rows.

    Args:
        port_rows: monthly_group_series rows for the portfolio.
        bench_rows: same for the benchmark (same calendar).

    Returns:
        Dict with months, cumulative active_return, linked total effects
        (allocation/selection/interaction) and per-group rows, or None
        when fewer than two spans are available.
    """
    n = min(len(port_rows), len(bench_rows))
    if n < 2:
        return None

    all_groups = sorted(
        set(port_rows[0][0]) | set(bench_rows[0][0])
    )

    # Per-span effects, kept per group for the Carino link.
    per_span: list[dict[str, dict[str, float]]] = []
    port_total_ret = 1.0
    bench_total_ret = 1.0
    for m in range(n):
        w_p, R_p_g, R_p_m = port_rows[m]
        w_b, R_b_g, R_b_m = bench_rows[m]
        port_total_ret *= 1.0 + R_p_m
        bench_total_ret *= 1.0 + R_b_m

        span: dict[str, dict[str, float]] = {}
        for g in all_groups:
            wp = w_p.get(g, 0.0)
            wb = w_b.get(g, 0.0)
            rp = R_p_g.get(g, float("nan"))
            rb = R_b_g.get(g, float("nan"))
            if wb == 0.0 and not np.isnan(rp):
                # Group absent from the benchmark: portfolio sleeve return
                # stands in as the benchmark sleeve (S = I = 0 by fiat).
                rb = rp
            if np.isnan(rp) or np.isnan(rb):
                a = s = i = 0.0
            else:
                a = (wp - wb) * (rb - R_b_m)
                s = wb * (rp - rb)
                i = (wp - wb) * (rp - rb)
            span[g] = {"allocation": a, "selection": s, "interaction": i}
        per_span.append(span)

    k_m = [
        _carino_factor(port_rows[m][2], bench_rows[m][2]) for m in range(n)
    ]
    active_total = port_total_ret - bench_total_ret  # R_p − R_b, cumulative
    # K maps the telescoped log-active difference back to arithmetic:
    # (R_p − R_b) = K · [ln(1+R_p) − ln(1+R_b)].
    log_diff = float(np.log(port_total_ret) - np.log(bench_total_ret))
    if abs(log_diff) > 1e-12:
        K = active_total / log_diff
    else:
        K = 1.0 / ((port_total_ret + bench_total_ret) / 2.0)

    def linked(effect: str, group: Optional[str] = None) -> float:
        raw = sum(
            (span[group][effect] if group else sum(v[effect] for v in span.values()))
            * k
            for span, k in zip(per_span, k_m, strict=False)
        )
        return float(K * raw)

    groups_out = []
    for g in all_groups:
        a = linked("allocation", g)
        s = linked("selection", g)
        i = linked("interaction", g)
        groups_out.append({
            "group": g,
            "avg_weight_portfolio": float(
                np.mean([port_rows[m][0].get(g, 0.0) for m in range(n)])
            ),
            "avg_weight_benchmark": float(
                np.mean([bench_rows[m][0].get(g, 0.0) for m in range(n)])
            ),
            "allocation": a,
            "selection": s,
            "interaction": i,
            "total": a + s + i,
        })

    return {
        "months": n,
        "active_return": float(active_total),
        "allocation": linked("allocation"),
        "selection": linked("selection"),
        "interaction": linked("interaction"),
        "groups": groups_out,
    }
