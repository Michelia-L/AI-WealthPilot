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
    7. Optionally drag the portfolio NAV by an all-in annual fee rate
       (P18): net_nav = gross_nav * (1 - fee) ** (t / 252). Portfolio
       metrics, yearly returns and the drawdown curve switch to the
       net-of-fee NAV; the benchmark always stays gross (index
       convention) and stress windows are fee-free buy-and-hold.

This module is pure computation. The FastAPI layer
(api/routers/monitoring.py) translates ValueError into 422 and
InsufficientDataError into 502, and converts the raw NAV/drawdown frames
(private ``_equity`` / ``_drawdown`` keys) into Plotly JSON charts.
All numbers are raw floats (0-1 decimals); dates are ISO strings;
human-readable caveats are collected in ``notes`` — bilingual via the
``locale`` parameter (Chinese by default, so direct callers keep the
pre-i18n behavior).

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

# Plausibility cap for the all-in annual fee drag (P18); rates outside
# [0, MAX_ANNUAL_FEE_RATE] are clipped with a note.
MAX_ANNUAL_FEE_RATE = 0.10

# Default benchmark: classic 60/40 stock/bond mix.
DEFAULT_BENCHMARK: dict[str, float] = {"SPY": 0.6, "AGG": 0.4}

# Fixed historical stress windows: (scenario key, window start, window end).
# Display names resolve per locale through _STRESS_NAMES below.
STRESS_SCENARIOS: list[tuple[str, str, str]] = [
    ("covid_2020", "2020-02-19", "2020-03-23"),
    ("rate_shock_2022", "2022-01-03", "2022-10-24"),
    ("gfc_2008", "2008-09-02", "2009-03-09"),
]

_STRESS_NAMES: dict[str, dict[str, str]] = {
    "covid_2020": {"zh": "2020 新冠", "en": "2020 COVID Crash"},
    "rate_shock_2022": {"zh": "2022 加息冲击", "en": "2022 Rate Shock"},
    "gfc_2008": {"zh": "2008 金融危机", "en": "2008 Global Financial Crisis"},
}

# Bilingual user-facing strings (exception messages and ``notes`` entries).
# zh keeps the pre-i18n wording verbatim; routers resolve the request locale
# and pass it down, direct callers default to zh. Kept here rather than in
# api/i18n.py because src/ must not import from the api/ transport shell.
_BT_STRINGS: dict[str, dict[str, str]] = {
    "label_portfolio": {"zh": "组合", "en": "Portfolio"},
    "label_benchmark": {"zh": "基准", "en": "Benchmark"},
    "invalid_period": {
        "zh": "不支持的回测区间：{period}（可选：{options}）。",
        "en": "Unsupported backtest period: {period} (available: {options}).",
    },
    "weights_empty": {
        "zh": "{label}权重为空或合计非正，无法执行回测。",
        "en": "{label} weights are empty or sum to a non-positive value; cannot run the backtest.",
    },
    "fetch_failed": {
        "zh": "行情数据获取失败：{error}",
        "en": "Failed to fetch price history: {error}",
    },
    "empty_prices": {
        "zh": "行情数据为空，无法执行回测。",
        "en": "Price history is empty; cannot run the backtest.",
    },
    "portfolio_sparse": {
        "zh": "组合资产的有效行情均不足 {min_obs} 个交易日，无法执行回测。",
        "en": "All portfolio assets have fewer than {min_obs} valid trading days; cannot run the backtest.",
    },
    "benchmark_missing": {
        "zh": "基准资产缺少有效行情数据，无法执行回测。",
        "en": "Benchmark assets lack valid price data; cannot run the backtest.",
    },
    "aligned_too_short": {
        "zh": "对齐后的行情窗口过短，无法执行回测。",
        "en": "The aligned price window is too short; cannot run the backtest.",
    },
    "fee_clipped": {
        "zh": "年化费用率 {fee:.2%} 超出 0–{max_rate:.0%} 的合理区间，已按 {clipped:.2%} 截断。",
        "en": "Annual fee rate {fee:.2%} is outside the plausible 0–{max_rate:.0%} range and was clipped to {clipped:.2%}.",
    },
    "fee_applied": {
        "zh": "已按年化费用率 {fee:.2%}（{source}）计入每日费用拖累（按 {days} 个交易日折算），组合指标为费后口径；基准为指数口径未计费。",
        "en": "A daily fee drag at an annual rate of {fee:.2%} ({source}) was applied (compounded over {days} trading days); portfolio metrics are net of fees while the benchmark stays gross (index convention).",
    },
    "fee_source_ips": {"zh": "IPS 披露 TER", "en": "IPS disclosed TER"},
    "fee_source_manual": {"zh": "手动费率", "en": "manual rate"},
    "stress_fee_free": {
        "zh": "压力测试为短窗口买入持有情景，未计费用拖累。",
        "en": "Stress tests are short-window buy-and-hold scenarios without fee drag.",
    },
    "no_fee": {
        "zh": "未计入费用拖累（费率为 0 或未披露），实际净值将低于回测值。",
        "en": "No fee drag was applied (rate is 0 or undisclosed); actual net values will be lower than the backtest.",
    },
    "drop_no_data": {
        "zh": "{label}资产 {ticker} 无行情数据，已剔除；剩余权重将重新归一化。",
        "en": "{label} asset {ticker} has no price data and was dropped; remaining weights were renormalized.",
    },
    "drop_sparse": {
        "zh": "{label}资产 {ticker} 有效行情仅 {n} 个交易日（不足 {min_obs}），已剔除；剩余权重将重新归一化。",
        "en": "{label} asset {ticker} has only {n} valid trading days (fewer than {min_obs}) and was dropped; remaining weights were renormalized.",
    },
    "stress_out_of_range": {
        "zh": "压力测试「{name}」（{window}）超出回测数据范围，已跳过。",
        "en": "Stress scenario \"{name}\" ({window}) falls outside the backtest data range and was skipped.",
    },
    "stress_too_short": {
        "zh": "压力测试「{name}」（{window}）窗口内有效交易日不足，已跳过。",
        "en": "Stress scenario \"{name}\" ({window}) has too few valid trading days and was skipped.",
    },
}


def _bt(key: str, locale: str, **fmt) -> str:
    """Render a bilingual backtest string; unknown locales fall back to zh."""
    template = _BT_STRINGS[key].get(locale) or _BT_STRINGS[key]["zh"]
    return template.format(**fmt) if fmt else template


class InsufficientDataError(RuntimeError):
    """Raised when price history is too scarce to run a backtest at all."""


# Public Entry Point

def run_backtest(
    weights: dict[str, float],
    period: str,
    benchmark_weights: Optional[dict[str, float]] = None,
    risk_free_rate: Optional[float] = None,
    annual_fee_rate: float = 0.0,
    fee_source: str = "manual",
    locale: str = "zh",
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
        annual_fee_rate: All-in annual fee drag as a decimal (0.012 = 1.2%).
            Clipped to [0, MAX_ANNUAL_FEE_RATE]; applied to the portfolio
            NAV as a daily drag of (1 - fee) ** (1/252). The benchmark is
            always reported gross (index convention).
        fee_source: Provenance label echoed back in the "fee" block (e.g.
            "manual", "ips_fee_schedule"); reported as "none" when the
            cleaned rate is 0.
        locale: Language for exception messages, ``notes`` and stress
            scenario names ("zh" default / "en").

    Returns:
        Dict matching the BacktestResponse contract, plus two private keys
        (``_equity`` / ``_drawdown``) holding the raw pandas frames the API
        layer turns into Plotly charts. ``_equity`` gains a third column
        ``portfolio_gross`` when a fee drag is applied.

    Raises:
        ValueError: Invalid period or degenerate weight maps.
        InsufficientDataError: Price history missing/too short overall.
    """
    if period not in VALID_PERIODS:
        raise ValueError(
            _bt(
                "invalid_period",
                locale,
                period=period,
                options=("、" if locale == "zh" else ", ").join(VALID_PERIODS),
            )
        )

    notes: list[str] = []
    port_label = _bt("label_portfolio", locale)
    bench_label = _bt("label_benchmark", locale)
    port = _normalized(weights, port_label, locale)
    bench = _normalized(
        benchmark_weights if benchmark_weights is not None else DEFAULT_BENCHMARK,
        bench_label,
        locale,
    )

    fee = float(annual_fee_rate)
    if fee < 0.0 or fee > MAX_ANNUAL_FEE_RATE:
        clipped = min(max(fee, 0.0), MAX_ANNUAL_FEE_RATE)
        notes.append(
            _bt(
                "fee_clipped",
                locale,
                fee=fee,
                max_rate=MAX_ANNUAL_FEE_RATE,
                clipped=clipped,
            )
        )
        fee = clipped

    rf = risk_free_rate if risk_free_rate is not None else fetch_risk_free_rate()

    tickers = sorted(set(port) | set(bench))
    try:
        raw = fetch_price_history(
            tickers=tickers, period=period, interval="1d", adjust_currency=False
        )
    except Exception as e:
        raise InsufficientDataError(_bt("fetch_failed", locale, error=e)) from e
    if raw is None or raw.empty:
        raise InsufficientDataError(_bt("empty_prices", locale))

    prices = raw.copy()
    if getattr(prices.index, "tz", None) is not None:
        prices.index = prices.index.tz_localize(None)
    prices = prices.sort_index()

    port = _drop_sparse_assets(port, prices, port_label, notes, locale)
    bench = _drop_sparse_assets(bench, prices, bench_label, notes, locale)
    if not port:
        raise InsufficientDataError(
            _bt("portfolio_sparse", locale, min_obs=MIN_OBSERVATIONS)
        )
    if not bench:
        raise InsufficientDataError(_bt("benchmark_missing", locale))

    # Align calendars: forward-fill interior gaps (holiday mismatch), then
    # trim leading rows until every surviving series has started.
    keep = list(dict.fromkeys([*port, *bench]))
    aligned = prices[keep].ffill().dropna()
    if len(aligned) < 2:
        raise InsufficientDataError(_bt("aligned_too_short", locale))

    port_nav_gross = _simulate_nav(aligned, port)
    bench_nav = _simulate_nav(aligned, bench)

    # P18 fee drag: rebalancing logic is untouched — the gross NAV is simply
    # scaled by a daily-compounded fee factor indexed by trading day.
    if fee > 0.0:
        drag = (1.0 - fee) ** (np.arange(len(aligned)) / TRADING_DAYS_PER_YEAR)
        port_nav = pd.Series(
            port_nav_gross.to_numpy(dtype=float) * drag,
            index=port_nav_gross.index,
        )
    else:
        port_nav = port_nav_gross

    stress = _run_stress_scenarios(aligned, port, bench, notes, locale)

    if fee > 0.0:
        source_label = {
            "ips_fee_schedule": _bt("fee_source_ips", locale),
            "manual": _bt("fee_source_manual", locale),
        }.get(fee_source, fee_source)
        notes.append(
            _bt(
                "fee_applied",
                locale,
                fee=fee,
                source=source_label,
                days=TRADING_DAYS_PER_YEAR,
            )
        )
        notes.append(_bt("stress_fee_free", locale))
    else:
        notes.append(_bt("no_fee", locale))

    gross_total_return = float(port_nav_gross.iloc[-1] / port_nav_gross.iloc[0] - 1.0)
    net_total_return = float(port_nav.iloc[-1] / port_nav.iloc[0] - 1.0)

    equity = pd.DataFrame({"portfolio": port_nav, "benchmark": bench_nav})
    if fee > 0.0:
        equity["portfolio_gross"] = port_nav_gross

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
        "stress": stress,
        "fee": {
            "annual_rate": fee,
            "source": fee_source if fee > 0.0 else "none",
            "gross_total_return": gross_total_return,
            "net_total_return": net_total_return,
            "cumulative_impact_pp": gross_total_return - net_total_return,
        },
        "notes": notes,
        # Raw frames for the API layer to chart (popped before responding).
        "_equity": equity,
        "_drawdown": pd.DataFrame(
            {"portfolio": _drawdown_series(port_nav),
             "benchmark": _drawdown_series(bench_nav)}
        ),
    }


# Weight Preparation

def _normalized(
    weights: dict[str, float], label: str, locale: str = "zh"
) -> dict[str, float]:
    """Drop non-positive entries and rescale a weight map to sum 1."""
    clean = {t: float(w) for t, w in weights.items() if w and w > 0}
    total = sum(clean.values())
    if not clean or total <= 0:
        raise ValueError(_bt("weights_empty", locale, label=label))
    return {t: w / total for t, w in clean.items()}


def _drop_sparse_assets(
    weights: dict[str, float],
    prices: pd.DataFrame,
    label: str,
    notes: list[str],
    locale: str = "zh",
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
            notes.append(_bt("drop_no_data", locale, label=label, ticker=t))
            continue
        if n < MIN_OBSERVATIONS:
            notes.append(
                _bt(
                    "drop_sparse",
                    locale,
                    label=label,
                    ticker=t,
                    n=n,
                    min_obs=MIN_OBSERVATIONS,
                )
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
    locale: str = "zh",
) -> list[dict]:
    """
    Evaluate the fixed STRESS_SCENARIOS windows against the aligned prices.
    Windows not fully covered by the data range are skipped with a note.
    Scenario display names resolve per ``locale``.
    """
    results = []
    data_start, data_end = prices.index[0], prices.index[-1]
    for key, start, end in STRESS_SCENARIOS:
        name = _STRESS_NAMES[key].get(locale) or _STRESS_NAMES[key]["zh"]
        window_label = f"{start}~{end}"
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        if s < data_start or e > data_end:
            notes.append(
                _bt("stress_out_of_range", locale, name=name, window=window_label)
            )
            continue
        window = prices.loc[s:e]
        if len(window) < 2:
            notes.append(
                _bt("stress_too_short", locale, name=name, window=window_label)
            )
            continue
        results.append({
            "scenario": name,
            "window": window_label,
            "portfolio_return": _buy_and_hold_return(window, port),
            "benchmark_return": _buy_and_hold_return(window, bench),
        })
    return results
