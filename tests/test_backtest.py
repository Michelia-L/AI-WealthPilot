"""
Engine-level tests for src/portfolio/backtest.py (P13).

All market data is synthetic and deterministic — the price fetch and the
risk-free-rate cascade are monkeypatched, so NAV and metric assertions are
exact hand-computed values, not smoke checks.
"""

import numpy as np
import pandas as pd
import pytest

from src.portfolio import backtest
from src.portfolio.backtest import InsufficientDataError, run_backtest

# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------


def _frame(series_map: dict, start: str) -> pd.DataFrame:
    """Equal-length synthetic price frame on a business-day index."""
    n = len(next(iter(series_map.values())))
    return pd.DataFrame(series_map, index=pd.bdate_range(start, periods=n))


def _stub(monkeypatch, df: pd.DataFrame, rf: float = 0.03) -> None:
    monkeypatch.setattr(backtest, "fetch_price_history", lambda **kw: df)
    monkeypatch.setattr(backtest, "fetch_risk_free_rate", lambda: rf)


# ---------------------------------------------------------------------------
# NAV simulation (monthly rebalancing)
# ---------------------------------------------------------------------------


def test_monthly_rebalancing_nav_exact(monkeypatch):
    """Hand-computed NAV across a month boundary with a rebalance reset."""
    # Jan 2024 has 23 bdays, Feb has 21 — 80 bdays spans Jan/Feb/Mar.
    aaa = [100.0, 110.0, 121.0] + [121.0] * 20        # Jan: +10%, +10%, flat
    aaa += [133.1, 146.41] + [146.41] * 19            # Feb: +10%, +10%, flat
    aaa += [146.41] * (80 - len(aaa))                 # Mar onward: flat
    df = _frame({"AAA": aaa, "BBB": [100.0] * 80}, "2024-01-01")
    _stub(monkeypatch, df)

    result = run_backtest(
        {"AAA": 0.5, "BBB": 0.5}, "1y", benchmark_weights={"BBB": 1.0}
    )
    nav = result["_equity"]["portfolio"]

    # First month: 50/50 from day one (base = 2024-01-01 close).
    assert nav.iloc[0] == pytest.approx(1.0)
    assert nav.iloc[1] == pytest.approx(0.5 * 1.10 + 0.5)   # 1.05
    assert nav.iloc[2] == pytest.approx(0.5 * 1.21 + 0.5)   # 1.105

    # Month-boundary return accrues to the drifted January weights:
    # AAA 121 -> 133.1 (+10%) before the Feb reset.
    feb1 = pd.Timestamp("2024-02-01")
    assert nav.loc[feb1] == pytest.approx(0.5 * 1.331 + 0.5)  # 1.1655

    # After the reset, Feb's +10% is earned by rebalanced 50/50 weights.
    feb2 = pd.Timestamp("2024-02-02")
    assert nav.loc[feb2] == pytest.approx(1.1655 * (0.5 * 1.10 + 0.5))  # 1.223775
    # ... which provably differs from buy-and-hold (never rebalanced):
    assert nav.loc[feb2] != pytest.approx(0.5 * 1.4641 + 0.5)           # 1.23205

    # Flat benchmark stays at 1.0.
    assert result["_equity"]["benchmark"].iloc[-1] == pytest.approx(1.0)
    assert result["weights"] == {"AAA": pytest.approx(0.5), "BBB": pytest.approx(0.5)}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_metrics_on_known_nav_path(monkeypatch):
    """Vol / Sharpe / max-drawdown / best-worst day against hand values."""
    prices = [100.0, 120.0, 90.0, 135.0, 105.0] + [105.0] * 65
    df = _frame({"AAA": prices}, "2024-01-01")
    _stub(monkeypatch, df)

    result = run_backtest(
        {"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0}, risk_free_rate=0.0
    )
    m = result["metrics"]

    # NAV: 1.0, 1.2, 0.9, 1.35, 1.05, flat... returns +20%, -25%, +50%, -2/9, 0...
    assert m["total_return"] == pytest.approx(0.05)
    assert m["best_day"] == pytest.approx(0.50)
    assert m["worst_day"] == pytest.approx(-0.25)

    # Max drawdown: 0.9 / 1.2 - 1 = -25% (unique trough; day 5 dips only -2/9).
    assert m["max_drawdown"] == pytest.approx(-0.25)
    assert m["max_drawdown_peak"] == df.index[1].date().isoformat()
    assert m["max_drawdown_trough"] == df.index[2].date().isoformat()

    rets = [0.20, -0.25, 0.50, -2.0 / 9.0] + [0.0] * 65
    expected_vol = float(np.std(rets, ddof=1) * np.sqrt(252))
    assert m["ann_volatility"] == pytest.approx(expected_vol)

    days = (df.index[-1] - df.index[0]).days
    expected_cagr = 1.05 ** (365.25 / days) - 1.0
    assert m["cagr"] == pytest.approx(expected_cagr)
    assert m["sharpe"] == pytest.approx(expected_cagr / expected_vol)  # rf = 0


def test_risk_free_rate_cascade_used_when_unset(monkeypatch):
    """risk_free_rate=None falls through to fetch_risk_free_rate()."""
    prices = (100.0 * (1.001 ** np.arange(70))).tolist()
    prices[10] *= 0.9  # one dip so volatility > 0
    df = _frame({"AAA": prices}, "2024-01-01")
    monkeypatch.setattr(backtest, "fetch_price_history", lambda **kw: df)
    monkeypatch.setattr(backtest, "fetch_risk_free_rate", lambda: 0.05)

    result = run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0})
    m = result["metrics"]
    assert m["sharpe"] == pytest.approx((m["cagr"] - 0.05) / m["ann_volatility"])


def test_zero_volatility_sharpe_is_null(monkeypatch):
    """Perfectly flat prices -> returns exactly 0 -> sharpe null (not a crash)."""
    df = _frame({"AAA": [100.0] * 70}, "2024-01-01")
    _stub(monkeypatch, df)

    m = run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0})["metrics"]
    assert m["ann_volatility"] == 0.0
    assert m["sharpe"] is None
    assert m["total_return"] == 0.0


# ---------------------------------------------------------------------------
# Sparse-asset handling
# ---------------------------------------------------------------------------


def test_sparse_assets_dropped_and_weights_renormalized(monkeypatch):
    good = (100.0 * (1.001 ** np.arange(80))).tolist()
    df = _frame(
        {
            "AAA": good,
            "SHORT": good[:30] + [np.nan] * 50,   # 30 < 60 valid days
            "DEAD": [np.nan] * 80,                # no data at all
        },
        "2024-01-01",
    )
    _stub(monkeypatch, df)

    result = run_backtest(
        {"AAA": 0.5, "SHORT": 0.3, "DEAD": 0.2},
        "1y",
        benchmark_weights={"AAA": 1.0},
    )

    assert result["weights"] == {"AAA": pytest.approx(1.0)}
    assert any("SHORT" in n and "30" in n for n in result["notes"])
    assert any("DEAD" in n for n in result["notes"])
    # Single surviving asset: monthly rebalancing == buy-and-hold.
    nav = result["_equity"]["portfolio"]
    assert nav.iloc[-1] == pytest.approx(good[-1] / good[0])


def test_all_assets_sparse_raises_insufficient_data(monkeypatch):
    df = _frame({"AAA": [100.0] * 30}, "2024-01-01")  # 30 < 60
    _stub(monkeypatch, df)
    with pytest.raises(InsufficientDataError):
        run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0})


def test_empty_price_frame_raises_insufficient_data(monkeypatch):
    _stub(monkeypatch, pd.DataFrame())
    with pytest.raises(InsufficientDataError):
        run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0})


def test_invalid_period_raises_value_error(monkeypatch):
    _stub(monkeypatch, _frame({"AAA": [100.0] * 70}, "2024-01-01"))
    with pytest.raises(ValueError, match="回测区间"):
        run_backtest({"AAA": 1.0}, "7y", benchmark_weights={"AAA": 1.0})


# ---------------------------------------------------------------------------
# Stress scenarios
# ---------------------------------------------------------------------------


def test_stress_windows_out_of_range_are_skipped(monkeypatch):
    """2024-only data covers none of the three fixed windows."""
    prices = (100.0 * (1.001 ** np.arange(80))).tolist()
    df = _frame({"AAA": prices, "BBB": prices}, "2024-01-01")
    _stub(monkeypatch, df)

    result = run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"BBB": 1.0})
    assert result["stress"] == []
    skipped = [n for n in result["notes"] if "压力测试" in n and "已跳过" in n]
    assert len(skipped) == 3


def test_stress_window_buy_and_hold_values(monkeypatch):
    """2020 COVID window covered: exact window returns for both mixes."""
    dates = pd.bdate_range("2019-12-02", periods=130)  # through ~2020-06
    aaa = pd.Series(100.0, index=dates)
    aaa.loc[aaa.index >= "2020-03-23"] = 80.0   # -20% at the window end
    bbb = pd.Series(100.0, index=dates)
    bbb.loc[bbb.index >= "2020-03-23"] = 50.0   # -50% at the window end
    df = pd.DataFrame({"AAA": aaa, "BBB": bbb})
    _stub(monkeypatch, df)

    result = run_backtest(
        {"AAA": 0.5, "BBB": 0.5}, "5y", benchmark_weights={"BBB": 1.0}
    )

    assert len(result["stress"]) == 1
    covid = result["stress"][0]
    assert covid["scenario"] == "2020 新冠"
    assert covid["window"] == "2020-02-19~2020-03-23"
    # Buy-and-hold at target weights: 0.5*(-20%) + 0.5*(-50%)
    assert covid["portfolio_return"] == pytest.approx(-0.35)
    assert covid["benchmark_return"] == pytest.approx(-0.50)
    # The 2022 and 2008 windows are beyond the data range.
    assert any("2022" in n for n in result["notes"])
    assert any("2008" in n for n in result["notes"])


# ---------------------------------------------------------------------------
# Fee drag (P18)
# ---------------------------------------------------------------------------


def test_fee_drag_math_exact(monkeypatch):
    """net NAV = gross NAV * (1-fee)^(t/252); every portfolio output goes net."""
    n = 300
    prices = (100.0 * (1.0005 ** np.arange(n))).tolist()
    df = _frame({"AAA": prices}, "2024-01-01")
    _stub(monkeypatch, df)
    fee = 0.02

    gross = run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0})
    result = run_backtest(
        {"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0},
        annual_fee_rate=fee, fee_source="manual",
    )

    gross_tr = gross["metrics"]["total_return"]
    expected_net_tr = (1.0 + gross_tr) * (1.0 - fee) ** ((n - 1) / 252) - 1.0
    info = result["fee"]
    assert info["annual_rate"] == fee
    assert info["source"] == "manual"
    assert info["gross_total_return"] == pytest.approx(gross_tr)
    assert info["net_total_return"] == pytest.approx(expected_net_tr)
    assert info["cumulative_impact_pp"] == pytest.approx(gross_tr - expected_net_tr)

    # Positive drift: the fee drag makes net strictly worse than gross.
    assert gross_tr > 0
    assert info["net_total_return"] < info["gross_total_return"]

    # Metrics, yearly compounding and the drawdown curve are all net-of-fee.
    assert result["metrics"]["total_return"] == pytest.approx(expected_net_tr)
    yearly_compound = float(
        np.prod([1.0 + y["portfolio"] for y in result["yearly"]]) - 1.0
    )
    assert yearly_compound == pytest.approx(expected_net_tr)
    nav = result["_equity"]["portfolio"]
    dd = result["_drawdown"]["portfolio"]
    assert dd.min() == pytest.approx(float((nav / nav.cummax() - 1.0).min()))

    # The ghost column mirrors the no-fee NAV; the benchmark stays gross.
    assert result["_equity"]["portfolio_gross"].iloc[-1] == pytest.approx(
        gross["_equity"]["portfolio"].iloc[-1]
    )
    assert result["_equity"]["benchmark"].iloc[-1] == pytest.approx(
        gross["_equity"]["benchmark"].iloc[-1]
    )


def test_fee_default_zero_matches_legacy(monkeypatch):
    """fee=0 keeps the gross path: source 'none', no ghost column, caveat note."""
    prices = (100.0 * (1.001 ** np.arange(80))).tolist()
    df = _frame({"AAA": prices}, "2024-01-01")
    _stub(monkeypatch, df)

    result = run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0})
    info = result["fee"]
    assert info["annual_rate"] == 0.0
    assert info["source"] == "none"
    assert info["gross_total_return"] == info["net_total_return"]
    assert info["net_total_return"] == result["metrics"]["total_return"]
    assert info["cumulative_impact_pp"] == 0.0
    assert "portfolio_gross" not in result["_equity"].columns
    assert any("未计入费用拖累" in n for n in result["notes"])


def test_fee_rate_out_of_range_clipped(monkeypatch):
    """Rates outside [0, 10%] are clipped with a Chinese note."""
    prices = (100.0 * (1.001 ** np.arange(80))).tolist()
    df = _frame({"AAA": prices}, "2024-01-01")
    _stub(monkeypatch, df)

    high = run_backtest(
        {"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0}, annual_fee_rate=0.5
    )
    assert high["fee"]["annual_rate"] == 0.10
    assert high["fee"]["source"] == "manual"
    assert any("截断" in n for n in high["notes"])

    low = run_backtest(
        {"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0}, annual_fee_rate=-0.01
    )
    assert low["fee"]["annual_rate"] == 0.0
    assert low["fee"]["source"] == "none"
    assert any("截断" in n for n in low["notes"])


def test_fee_notes_disclose_net_basis(monkeypatch):
    """fee>0 notes: net-of-fee metrics basis + stress windows are fee-free."""
    prices = (100.0 * (1.001 ** np.arange(80))).tolist()
    df = _frame({"AAA": prices}, "2024-01-01")
    _stub(monkeypatch, df)

    result = run_backtest(
        {"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0},
        annual_fee_rate=0.012, fee_source="ips_fee_schedule",
    )
    assert any(
        "1.20%" in n and "IPS 披露 TER" in n and "费后" in n
        for n in result["notes"]
    )
    assert any("压力测试" in n and "未计费用" in n for n in result["notes"])


# ---------------------------------------------------------------------------
# Locale (P22-i18n-2): zh default verbatim, en fully English
# ---------------------------------------------------------------------------


def test_invalid_period_error_locale(monkeypatch):
    """The invalid-period ValueError follows the locale argument."""
    with pytest.raises(ValueError, match="不支持的回测区间"):
        run_backtest({"AAA": 1.0}, "7y")
    with pytest.raises(ValueError, match="Unsupported backtest period"):
        run_backtest({"AAA": 1.0}, "7y", locale="en")


def test_empty_prices_error_locale(monkeypatch):
    """InsufficientDataError messages are English-only under locale='en'."""
    monkeypatch.setattr(backtest, "fetch_price_history", lambda **kw: pd.DataFrame())
    with pytest.raises(InsufficientDataError, match="行情数据为空"):
        run_backtest({"AAA": 1.0}, "1y")
    with pytest.raises(InsufficientDataError, match="Price history is empty"):
        run_backtest({"AAA": 1.0}, "1y", locale="en")


def test_stress_scenario_names_and_notes_locale(monkeypatch):
    """Stress names and skip notes render in the requested locale."""
    dates = pd.bdate_range("2019-06-03", periods=700)  # covers COVID window only
    d = np.arange(700, dtype=float)
    df = pd.DataFrame(
        {"AAA": 100.0 * np.cumprod(1.0 + 0.0006 + 0.008 * np.sin(d / 7.0))},
        index=dates,
    )
    _stub(monkeypatch, df)

    zh = run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0})
    assert zh["stress"][0]["scenario"] == "2020 新冠"
    assert any("2022 加息冲击" in n for n in zh["notes"])
    assert any("未计入费用拖累" in n for n in zh["notes"])

    en = run_backtest({"AAA": 1.0}, "1y", benchmark_weights={"AAA": 1.0}, locale="en")
    assert en["stress"][0]["scenario"] == "2020 COVID Crash"
    assert any("2022 Rate Shock" in n for n in en["notes"])
    assert any("No fee drag" in n for n in en["notes"])
    # No Chinese residue anywhere in the English notes.
    assert all(not any("一" <= ch <= "鿿" for ch in n) for n in en["notes"])
