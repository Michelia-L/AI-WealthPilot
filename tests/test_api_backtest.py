"""
API tests for GET /api/monitoring/{document_id}/backtest (P13).

The SAA document store uses the conftest tmp IPS_DIR; the market data layer
and risk-free rate are monkeypatched with deterministic synthetic series —
tests cover the HTTP contract (200 / 404 / 422 / 502), not live data.
"""

import json

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------


def _write_ips_doc(ips_dir, doc_id, saa, client_name="回测客户"):
    """Write a minimal IPS record (with SAA) into the tmp document store."""
    record = {
        "ips": {
            "client_name": client_name,
            "version": "1.0",
            "investment_guidelines": {"strategic_allocation": saa},
        },
        "audit_trail": {"final_status": "approved", "total_rounds": 0},
        "metadata": {"client_name": client_name, "saved_at": "2026-06-01T09:30:00"},
    }
    (ips_dir / f"{doc_id}.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )
    return doc_id


def _saa_entry(asset_class, target, min_w, max_w):
    return {
        "asset_class": asset_class,
        "target_weight": target,
        "min_weight": min_w,
        "max_weight": max_w,
        "rationale": "test",
    }


def _price_frame() -> pd.DataFrame:
    """
    700 bdays from 2019-06-03 (~2022-02): covers the 2020 COVID stress
    window, but not the 2022 rate-shock or 2008 GFC windows. A sine wiggle
    keeps daily returns non-constant so volatility and drawdowns are real.
    """
    dates = pd.bdate_range("2019-06-03", periods=700)
    d = np.arange(700, dtype=float)
    return pd.DataFrame(
        {
            "000300.SS": 100.0 * np.cumprod(1.0 + 0.0006 + 0.008 * np.sin(d / 7.0)),
            "AGG": 100.0 * np.cumprod(1.0 + 0.0002 + 0.001 * np.sin(d / 7.0)),
            "SPY": 100.0 * np.cumprod(1.0 + 0.0009 + 0.006 * np.sin(d / 7.0)),
        },
        index=dates,
    )


def _stub_market(monkeypatch, df=None, rf=0.03):
    df = df if df is not None else _price_frame()
    monkeypatch.setattr("src.portfolio.backtest.fetch_price_history", lambda **kw: df)
    monkeypatch.setattr("src.portfolio.backtest.fetch_risk_free_rate", lambda: rf)
    return df


@pytest.fixture
def ips_dir(tmp_path):
    """The tmp IPS_DIR installed by conftest.isolate_storage_dirs."""
    return tmp_path / "data" / "ips"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_backtest_full_contract(client, ips_dir, monkeypatch):
    df = _stub_market(monkeypatch)
    doc_id = _write_ips_doc(ips_dir, "ips_bt_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.6, 0.5, 0.7),
        _saa_entry("固定收益", 0.4, 0.3, 0.5),
    ])

    resp = client.get(f"/api/monitoring/{doc_id}/backtest?period=5y")
    assert resp.status_code == 200
    body = resp.json()

    assert body["document_id"] == doc_id
    assert body["client_name"] == "回测客户"
    assert body["period"] == "5y"
    assert body["as_of"] == df.index[-1].date().isoformat()

    # Display-name keyed, SAA-normalized weights (sums to 1 — no plug/rescale).
    assert set(body["weights"]) == {"国内权益（A股/沪深300）", "固定收益"}
    assert body["weights"]["国内权益（A股/沪深300）"] == pytest.approx(0.6)
    assert body["weights"]["固定收益"] == pytest.approx(0.4)

    # Metrics blocks: portfolio and benchmark share the same field set.
    metric_fields = {
        "total_return", "cagr", "ann_volatility", "sharpe", "max_drawdown",
        "max_drawdown_peak", "max_drawdown_trough", "best_day", "worst_day",
    }
    assert metric_fields <= set(body["metrics"])
    assert metric_fields <= set(body["benchmark"]["metrics"])
    for block in (body["metrics"], body["benchmark"]["metrics"]):
        for f in metric_fields - {"max_drawdown_peak", "max_drawdown_trough"}:
            assert isinstance(block[f], (int, float)), f
        assert block["max_drawdown"] <= 0
        assert block["max_drawdown_peak"]
        assert block["max_drawdown_trough"]
    assert body["benchmark"]["name"] == "60% SPY / 40% AGG"

    # Calendar-year table, ordered, one row per covered year.
    years = [y["year"] for y in body["yearly"]]
    assert years == sorted(years) and 2019 in years and 2022 in years
    assert {"year", "portfolio", "benchmark"} <= set(body["yearly"][0])

    # Charts are full Plotly JSON figures.
    assert body["equity_chart"]["data"] and body["equity_chart"]["layout"]
    assert len(body["equity_chart"]["data"]) == 2
    assert body["drawdown_chart"]["data"] and body["drawdown_chart"]["layout"]

    # Only the 2020 COVID window is covered by the synthetic range.
    assert len(body["stress"]) == 1
    covid = body["stress"][0]
    assert covid["scenario"] == "2020 新冠"
    assert covid["window"] == "2020-02-19~2020-03-23"
    assert isinstance(covid["portfolio_return"], float)
    assert isinstance(covid["benchmark_return"], float)

    assert isinstance(body["notes"], list)
    assert any("2022 加息冲击" in n for n in body["notes"])
    assert any("2008 金融危机" in n for n in body["notes"])


def test_backtest_document_not_found(client):
    assert client.get("/api/monitoring/ips_nobody_20260101_000000/backtest").status_code == 404
    assert client.get("/api/monitoring/..%2F..%2Fsecret/backtest").status_code == 404


def test_backtest_invalid_period_422(client, ips_dir, monkeypatch):
    _stub_market(monkeypatch)
    doc_id = _write_ips_doc(ips_dir, "ips_bt_period_20260601_093000", [
        _saa_entry("固定收益", 1.0, 0.9, 1.0),
    ])
    resp = client.get(f"/api/monitoring/{doc_id}/backtest?period=7y")
    assert resp.status_code == 422
    assert "回测区间" in resp.json()["detail"]


def test_backtest_missing_saa_422(client, ips_dir, monkeypatch):
    _stub_market(monkeypatch)
    doc_id = _write_ips_doc(ips_dir, "ips_bt_nosaa_20260601_093000", [])
    resp = client.get(f"/api/monitoring/{doc_id}/backtest")
    assert resp.status_code == 422
    assert "战略性资产配置" in resp.json()["detail"]


def test_backtest_insufficient_data_502(client, ips_dir, monkeypatch):
    """Every series below the 60-day minimum -> nothing left to backtest."""
    short = pd.DataFrame(
        {"000300.SS": [100.0] * 30, "AGG": [100.0] * 30, "SPY": [100.0] * 30},
        index=pd.bdate_range("2024-01-01", periods=30),
    )
    _stub_market(monkeypatch, df=short)
    doc_id = _write_ips_doc(ips_dir, "ips_bt_sparse_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.6, 0.5, 0.7),
        _saa_entry("固定收益", 0.4, 0.3, 0.5),
    ])
    resp = client.get(f"/api/monitoring/{doc_id}/backtest")
    assert resp.status_code == 502
    assert "无法执行回测" in resp.json()["detail"]
