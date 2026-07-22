"""
AI WealthPilot - Portfolio Backtesting & Stress Testing (P13)

Historical simulation for a target-weight portfolio:

    1. Fetch adjusted daily prices for the portfolio and benchmark tickers
    2. Drop assets with missing or too-short history (< 60 valid daily
       observations), renormalizing the remaining target weights
    3. Simulate a monthly-rebalanced NAV (base 1.0): weights reset to target
       at the first trading day of each month and drift with returns between
       rebalances; the benchmark NAV follows the same rules
    4. Compute risk/return metrics (total return, CAGR, annualized
       volatility, Sharpe, max drawdown with peak/trough dates, best/worst
       day) for both NAV series
    5. Compound calendar-year returns
    6. Run fixed historical stress windows (2020 COVID crash, 2022 rate
       shock, 2008 GFC) as buy-and-hold over each window

This module is pure computation. The FastAPI layer
(api/routers/monitoring.py) translates ValueError into 422 and
InsufficientDataError into 502, and converts the raw NAV/drawdown frames
(private ``_equity`` / ``_drawdown`` keys) into Plotly JSON charts.
All numbers are raw floats (0-1 decimals); dates are ISO strings;
human-readable caveats are collected in ``notes`` (Chinese).

"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.data.market_data import fetch_price_history, fetch_risk_free_rate

logger = logging.getLogger(__name__)

VALID_PERIODS = ("1y", "3y", "5y", "10y")

# Minimum valid daily observations for an asset to stay in the backtest.
MIN_OBSERVATIONS = 60

TRADING_DAYS_PER_YEAR = 252

# Default benchmark: classic 60/40 stock/bond mix.
DEFAULT_BENCHMARK: dict[str, float] = {"SPY": 0.6, "AGG": 0.4}

# Fixed historical stress windows: (scenario name, window start, window end).
STRESS_SCENARIOS: list[tuple[str, str, str]] = [
    ("2020 新冠", "2020-02-19", "2020-03-23"),
    ("2022 加息冲击", "2022-01-03", "2022-10-24"),
    ("2008 金融危机", "2008-09-02", "2009-03-09"),
]


class InsufficientDataError(RuntimeError):
    """Raised when price history is too scarce to run a backtest at all."""


# Public Entry Point

def run_backtest(
    weights: dict[str, float],
    period: str,
    benchmark_weights: Optional[dict[str, float]] = None,
    risk_free_rate: Optional[float] = None,
) -> dict:
    """
    Backtest a target-weight portfolio against a benchmark.

    Args:
        weights: {ticker: target weight}, approximately normalized (rescaled
            defensively; renormalized again after dropping sparse assets).
        period: Lookback window — one of "1y" / "3y" / "5y" / "10y".
        benchmark_weights: {ticker: weight}; defaults to 60% SPY / 40% AGG.
        risk_free_rate: Annualized decimal; None cascades FRED -> yfinance
            -> static fallback via fetch_risk_free_rate().

    Returns:
        Dict matching the BacktestResponse contract, plus two private keys
        (``_equity`` / ``_drawdown``) holding the raw pandas frames the API
        layer turns into Plotly charts.

    Raises:
        ValueError: Invalid period or degenerate weight maps.
        InsufficientDataError: Price history missing/too short overall.
    """
    if period not in VALID_PERIODS:
        raise ValueError(
            f"不支持的回测区间：{period}（可选：{'、'.join(VALID_PERIODS)}）。"
        )

    notes: list[str] = []
    port = _normalized(weights, "组合")
    bench = _normalized(
        benchmark_weights if benchmark_weights is not None else DEFAULT_BENCHMARK,
        "基准",
    )

    rf = risk_free_rate if risk_free_rate is not None else fetch_risk_free_rate()

    tickers = sorted(set(port) | set(bench))
    try:
        raw = fetch_price_history(
            tickers=tickers, period=period, interval="1d", adjust_currency=False
        )
    except Exception as e:
        raise InsufficientDataError(f"行情数据获取失败：{e}") from e
    if raw is None or raw.empty:
        raise InsufficientDataError("行情数据为空，无法执行回测。")

    prices = raw.copy()
    if getattr(prices.index, "tz", None) is not None:
        prices.index = prices.index.tz_localize(None)
    prices = prices.sort_index()

    port = _drop_sparse_assets(port, prices, "组合", notes)
    bench = _drop_sparse_assets(bench, prices, "基准", notes)
    if not port:
        raise InsufficientDataError(
            f"组合资产的有效行情均不足 {MIN_OBSERVATIONS} 个交易日，无法执行回测。"
        )
    if not bench:
        raise InsufficientDataError("基准资产缺少有效行情数据，无法执行回测。")

    # Align calendars: forward-fill interior gaps (holiday mismatch), then
    # trim leading rows until every surviving series has started.
    keep = list(dict.fromkeys([*port, *bench]))
    aligned = prices[keep].ffill().dropna()
    if len(aligned) < 2:
        raise InsufficientDataError("对齐后的行情窗口过短，无法执行回测。")

    port_nav = _simulate_nav(aligned, port)
    bench_nav = _simulate_nav(aligned, bench)

    benchmark_name = " / ".join(f"{w:.0%} {t}" for t, w in bench.items())

    return {
        "period": period,
        "as_of": aligned.index[-1].date().isoformat(),
        "weights": {t: float(w) for t, w in port.items()},
        "metrics": _compute_metrics(port_nav, rf),
        "benchmark": {
            "name": benchmark_name,
            "metrics": _compute_metrics(bench_nav, rf),
        },
        "yearly": _yearly_returns(port_nav, bench_nav),
        "stress": _run_stress_scenarios(aligned, port, bench, notes),
        "notes": notes,
        # Raw frames for the API layer to chart (popped before responding).
        "_equity": pd.DataFrame({"portfolio": port_nav, "benchmark": bench_nav}),
        "_drawdown": pd.DataFrame(
            {"portfolio": _drawdown_series(port_nav),
             "benchmark": _drawdown_series(bench_nav)}
        ),
    }


# Weight Preparation

def _normalized(weights: dict[str, float], label: str) -> dict[str, float]:
    """Drop non-positive entries and rescale a weight map to sum 1."""
    clean = {t: float(w) for t, w in weights.items() if w and w > 0}
    total = sum(clean.values())
    if not clean or total <= 0:
        raise ValueError(f"{label}权重为空或合计非正，无法执行回测。")
    return {t: w / total for t, w in clean.items()}


def _drop_sparse_assets(
    weights: dict[str, float],
    prices: pd.DataFrame,
    label: str,
    notes: list[str],
) -> dict[str, float]:
    """
    Remove assets whose price series is missing or shorter than
    MIN_OBSERVATIONS valid days; renormalize the survivors to sum 1.
    """
    kept: dict[str, float] = {}
    for t, w in weights.items():
        series = prices[t] if t in prices.columns else None
        n = int(series.dropna().shape[0]) if series is not None else 0
        if n == 0:
            notes.append(
                f"{label}资产 {t} 无行情数据，已剔除；剩余权重将重新归一化。"
            )
            continue
        if n < MIN_OBSERVATIONS:
            notes.append(
                f"{label}资产 {t} 有效行情仅 {n} 个交易日"
                f"（不足 {MIN_OBSERVATIONS}），已剔除；剩余权重将重新归一化。"
            )
            continue
        kept[t] = w
    total = sum(kept.values())
    return {t: w / total for t, w in kept.items()} if total > 0 else {}


# NAV Simulation (monthly rebalancing)

def _simulate_nav(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """
    Monthly-rebalanced NAV starting at 1.0.

    Weights are reset to target at the close of each month's first trading
    day; between rebalances they drift with asset returns. Span (r_k, r_{k+1}]
    accrues returns to the weights set at r_k, so month-boundary returns are
    earned by the old (drifted) weights before the next reset.
    """
    cols = list(weights)
    w = np.array([weights[c] for c in cols], dtype=float)
    px = prices[cols]

    nav = pd.Series(index=px.index, dtype=float)
    nav.iloc[0] = 1.0

    periods = px.index.to_period("M")
    rebal_dates = px.index[~periods.duplicated()]
    current = 1.0
    for k, r_k in enumerate(rebal_dates):
        r_next = rebal_dates[k + 1] if k + 1 < len(rebal_dates) else px.index[-1]
        span = px.loc[(px.index > r_k) & (px.index <= r_next)]
        if span.empty:
            continue
        rel = span.to_numpy(dtype=float) / px.loc[r_k].to_numpy(dtype=float)
        values = current * (rel @ w)
        nav.loc[span.index] = values
        current = float(values[-1])
    return nav


# Metrics

def _drawdown_series(nav: pd.Series) -> pd.Series:
    """Underwater curve: NAV / running-max - 1 (<= 0)."""
    return nav / nav.cummax() - 1.0


def _compute_metrics(nav: pd.Series, risk_free_rate: float) -> dict:
    """Risk/return metrics for one NAV series (base 1.0, daily)."""
    rets = nav.pct_change().dropna()

    total_return = float(nav.iloc[-1] / nav.iloc[0] - 1.0)
    days = max((nav.index[-1] - nav.index[0]).days, 1)
    cagr = float((nav.iloc[-1] / nav.iloc[0]) ** (365.25 / days) - 1.0)

    ann_vol = (
        float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if len(rets) > 1
        else 0.0
    )
    sharpe = (cagr - risk_free_rate) / ann_vol if ann_vol > 0 else None

    dd = _drawdown_series(nav)
    trough = dd.idxmin()
    peak = nav.loc[:trough].idxmax()

    return {
        "total_return": total_return,
        "cagr": cagr,
        "ann_volatility": ann_vol,
        "sharpe": float(sharpe) if sharpe is not None else None,
        "max_drawdown": float(dd.loc[trough]),
        "max_drawdown_peak": peak.date().isoformat(),
        "max_drawdown_trough": trough.date().isoformat(),
        "best_day": float(rets.max()) if len(rets) else 0.0,
        "worst_day": float(rets.min()) if len(rets) else 0.0,
    }


def _yearly_returns(port_nav: pd.Series, bench_nav: pd.Series) -> list[dict]:
    """Compound daily NAV returns into calendar-year returns."""
    rets = pd.DataFrame(
        {"portfolio": port_nav.pct_change(), "benchmark": bench_nav.pct_change()}
    ).dropna()
    out = []
    for year, g in rets.groupby(rets.index.year):
        out.append({
            "year": int(year),
            "portfolio": float((1.0 + g["portfolio"]).prod() - 1.0),
            "benchmark": float((1.0 + g["benchmark"]).prod() - 1.0),
        })
    return out


# Stress Testing

def _buy_and_hold_return(window: pd.DataFrame, weights: dict[str, float]) -> float:
    """Window return of the target-weight mix, bought at window start."""
    rel = window.iloc[-1] / window.iloc[0] - 1.0
    return float(sum(w * float(rel[t]) for t, w in weights.items()))


def _run_stress_scenarios(
    prices: pd.DataFrame,
    port: dict[str, float],
    bench: dict[str, float],
    notes: list[str],
) -> list[dict]:
    """
    Evaluate the fixed STRESS_SCENARIOS windows against the aligned prices.
    Windows not fully covered by the data range are skipped with a note.
    """
    results = []
    data_start, data_end = prices.index[0], prices.index[-1]
    for name, start, end in STRESS_SCENARIOS:
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        if s < data_start or e > data_end:
            notes.append(
                f"压力测试「{name}」（{start}~{end}）超出回测数据范围，已跳过。"
            )
            continue
        window = prices.loc[s:e]
        if len(window) < 2:
            notes.append(
                f"压力测试「{name}」（{start}~{end}）窗口内有效交易日不足，已跳过。"
            )
            continue
        results.append({
            "scenario": name,
            "window": f"{start}~{end}",
            "portfolio_return": _buy_and_hold_return(window, port),
            "benchmark_return": _buy_and_hold_return(window, bench),
        })
    return results
