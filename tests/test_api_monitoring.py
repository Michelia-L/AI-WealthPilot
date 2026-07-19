"""
API tests for portfolio monitoring & rebalancing (P10).

The CME engine and market data layer are stubbed via monkeypatch — tests
cover the monitoring math (weight normalization, drift, bands, rebalance
trades) and the HTTP contract (200 / 404 / 422), not live data sources.
"""

import json
from datetime import datetime

import pandas as pd
import pytest

from src.portfolio.cme_models import AssetClassCME, CMEReport

SAVED_AT = "2026-06-01T09:30:00"


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------


def _write_ips_doc(ips_dir, doc_id, saa, saved_at=SAVED_AT, client_name="测试客户"):
    """Write a minimal IPS record (with SAA) into the tmp document store."""
    record = {
        "ips": {
            "client_name": client_name,
            "version": "1.0",
            "investment_guidelines": {"strategic_allocation": saa},
        },
        "audit_trail": {"final_status": "approved", "total_rounds": 0},
        "metadata": {"client_name": client_name, "saved_at": saved_at, "notes": ""},
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


def _fake_cme_report() -> CMEReport:
    """Three-asset CME report aligned with IPS_ASSET_CLASS_TICKERS."""
    return CMEReport(
        as_of_date="2026-07-01",
        data_lookback_years=5,
        risk_free_rate=0.03,
        risk_free_rate_source="static_fallback",
        inflation_assumption=0.025,
        asset_classes=[
            AssetClassCME(
                name="Domestic Equity (A-Shares/CSI 300)",
                ticker="000300.SS",
                expected_return=0.08,
                volatility=0.20,
                sharpe_ratio=0.25,
                max_drawdown=-0.30,
                var_95=0.02,
                cvar_95=0.03,
                data_points=1200,
                blended_volatility=0.22,  # preferred over historical 0.20
            ),
            AssetClassCME(
                name="固定收益",
                ticker="AGG",
                expected_return=0.03,
                volatility=0.06,
                sharpe_ratio=0.0,
                max_drawdown=-0.10,
                var_95=0.005,
                cvar_95=0.008,
                data_points=1200,
            ),
            AssetClassCME(
                name="现金等价物",
                ticker="BIL",
                expected_return=0.02,
                volatility=0.01,
                sharpe_ratio=-1.0,
                max_drawdown=-0.001,
                var_95=0.0005,
                cvar_95=0.0008,
                data_points=1200,
            ),
        ],
        correlation_matrix={
            "Domestic Equity (A-Shares/CSI 300)": {
                "Domestic Equity (A-Shares/CSI 300)": 1.0,
                "固定收益": 0.1,
                "现金等价物": 0.0,
            },
            "固定收益": {
                "Domestic Equity (A-Shares/CSI 300)": 0.1,
                "固定收益": 1.0,
                "现金等价物": 0.0,
            },
            "现金等价物": {
                "Domestic Equity (A-Shares/CSI 300)": 0.0,
                "固定收益": 0.0,
                "现金等价物": 1.0,
            },
        },
    )


def _prices(series_map: dict) -> pd.DataFrame:
    """Small price frame indexed from 2026-06-01 (the SAVED_AT date)."""
    dates = pd.bdate_range("2026-06-01", periods=len(next(iter(series_map.values()))))
    return pd.DataFrame(series_map, index=dates)


def _stub_fetch(df):
    def fetch(tickers=None, period="5y", interval="1d",
              base_currency=None, adjust_currency=True):
        return df
    return fetch


@pytest.fixture
def ips_dir(tmp_path):
    """The tmp IPS_DIR installed by conftest.isolate_storage_dirs."""
    return tmp_path / "data" / "ips"


@pytest.fixture
def stub_cme(monkeypatch):
    report = _fake_cme_report()
    monkeypatch.setattr(
        "src.portfolio.monitoring.compute_cme", lambda *a, **kw: (report, "cached")
    )
    return report


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_monitoring_full_chain(client, ips_dir, stub_cme, monkeypatch):
    """End-to-end 200: cash plug, CME alignment, drift, portfolio metrics."""
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _stub_fetch(_prices({
            "000300.SS": [100.0, 110.0, 120.0],   # +20%
            "AGG": [100.0, 100.0, 100.0],          # 0%
            "BIL": [100.0, 100.5, 101.0],          # +1%
        })),
    )
    doc_id = _write_ips_doc(ips_dir, "ips_test_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.6, 0.5, 0.7),
        _saa_entry("固定收益", 0.3, 0.25, 0.4),
    ])  # sums to 0.9 -> 0.1 cash plug

    resp = client.get(f"/api/monitoring/{doc_id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["document_id"] == doc_id
    assert body["client_name"] == "测试客户"
    assert body["saved_at"] == SAVED_AT
    assert body["as_of"] == datetime.now().date().isoformat()
    assert body["cme_cache_status"] == "cached"

    # Cash plug appended as a third holding
    assert len(body["holdings"]) == 3
    cash = body["holdings"][2]
    assert cash["key"] == "cash"
    assert cash["ticker"] == "BIL"
    assert cash["target_weight"] == pytest.approx(0.1)
    assert cash["min_weight"] == 0.0
    assert cash["max_weight"] == pytest.approx(0.1)
    assert any("现金" in n for n in body["notes"])

    # Target-weight portfolio: mu = .6*.08 + .3*.03 + .1*.02
    port = body["portfolio"]
    assert port["expected_return"] == pytest.approx(0.059)
    assert port["volatility"] == pytest.approx(0.1350, abs=1e-3)
    assert port["sharpe"] == pytest.approx(0.2148, abs=1e-3)

    # Per-holding CME metrics use blended volatility when available
    domestic = body["holdings"][0]
    assert domestic["key"] == "domestic_equity"
    assert domestic["ticker"] == "000300.SS"
    assert domestic["metrics"]["volatility"] == pytest.approx(0.22)
    assert domestic["metrics"]["expected_return"] == pytest.approx(0.08)
    assert domestic["metrics"]["sharpe"] == pytest.approx(0.25)

    # Drift: gross = .6*1.2 + .3*1.0 + .1*1.01 = 1.121
    assert domestic["period_return"] == pytest.approx(0.20)
    assert domestic["drifted_weight"] == pytest.approx(0.72 / 1.121)
    assert domestic["drift_pp"] == pytest.approx(0.72 / 1.121 - 0.6)
    assert domestic["band_status"] == "within"
    assert body["holdings"][1]["band_status"] == "within"
    assert cash["band_status"] == "within"

    # Drifted portfolio computable (all holdings have price data)
    drifted = body["drifted_portfolio"]
    assert drifted["expected_return"] == pytest.approx(0.06121, abs=1e-4)
    assert drifted["volatility"] == pytest.approx(0.1438, abs=1e-3)
    assert drifted["sharpe"] is not None

    # Nothing out of band -> no trades
    assert body["rebalance"] == {"needed": False, "trades": []}


def test_monitoring_document_not_found(client):
    assert client.get("/api/monitoring/ips_nobody_20260101_000000").status_code == 404
    assert client.get("/api/monitoring/..%2F..%2Fsecret").status_code == 404


def test_monitoring_missing_saa_returns_422(client, ips_dir, stub_cme):
    doc_id = _write_ips_doc(ips_dir, "ips_nosaa_20260601_093000", [])
    resp = client.get(f"/api/monitoring/{doc_id}")
    assert resp.status_code == 422
    assert "战略性资产配置" in resp.json()["detail"]


def test_drift_bands_and_rebalance_trades(client, ips_dir, stub_cme, monkeypatch):
    """Strong equity rally + bond selloff: both classes out of band."""
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _stub_fetch(_prices({
            "000300.SS": [100.0, 140.0, 180.0],  # +80%
            "AGG": [100.0, 95.0, 90.0],          # -10%
            "BIL": [100.0, 100.0, 100.0],
        })),
    )
    doc_id = _write_ips_doc(ips_dir, "ips_drift_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.5, 0.4, 0.6),
        _saa_entry("固定收益", 0.5, 0.4, 0.6),
    ])  # sums to 1.0 -> no plug, no rescaling

    body = client.get(f"/api/monitoring/{doc_id}").json()

    # gross = .5*1.8 + .5*0.9 = 1.35
    domestic, fixed = body["holdings"]
    assert domestic["period_return"] == pytest.approx(0.80)
    assert domestic["drifted_weight"] == pytest.approx(0.9 / 1.35)
    assert domestic["drift_pp"] == pytest.approx(0.9 / 1.35 - 0.5)
    assert domestic["band_status"] == "above"      # .6667 > max .6

    assert fixed["period_return"] == pytest.approx(-0.10)
    assert fixed["drifted_weight"] == pytest.approx(0.45 / 1.35)
    assert fixed["band_status"] == "below"         # .3333 < min .4

    rebalance = body["rebalance"]
    assert rebalance["needed"] is True
    assert len(rebalance["trades"]) == 2
    trades = {t["key"]: t for t in rebalance["trades"]}
    # Overweight -> sell down to target; underweight -> buy up to target
    assert trades["domestic_equity"]["action"] == "sell"
    assert trades["domestic_equity"]["weight_pp"] == pytest.approx(0.5 - 0.9 / 1.35)
    assert trades["fixed_income"]["action"] == "buy"
    assert trades["fixed_income"]["weight_pp"] == pytest.approx(0.5 - 0.45 / 1.35)


def test_missing_price_data_degrades(client, ips_dir, stub_cme, monkeypatch):
    """AGG absent from the price frame: unknown band, null drifted metrics."""
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _stub_fetch(_prices({"000300.SS": [100.0, 140.0, 180.0]})),
    )
    doc_id = _write_ips_doc(ips_dir, "ips_gap_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.5, 0.4, 0.6),
        _saa_entry("固定收益", 0.5, 0.4, 0.6),
    ])

    body = client.get(f"/api/monitoring/{doc_id}").json()
    domestic, fixed = body["holdings"]

    assert fixed["period_return"] is None
    assert fixed["drifted_weight"] is None
    assert fixed["drift_pp"] is None
    assert fixed["band_status"] == "unknown"
    assert any("AGG" in n for n in body["notes"])

    # Missing-data holding treated as unchanged (R=0) in normalization:
    # domestic drifted = .5*1.8 / (.5*1.8 + .5*1.0) = 0.6429
    assert domestic["drifted_weight"] == pytest.approx(0.9 / 1.4)
    assert domestic["band_status"] == "above"

    # Drifted-weight portfolio metrics degrade to nulls as a block
    assert body["drifted_portfolio"] == {
        "expected_return": None,
        "volatility": None,
        "sharpe": None,
    }

    # Target-weight portfolio and rebalance still work
    assert body["portfolio"]["expected_return"] is not None
    trades = body["rebalance"]["trades"]
    assert body["rebalance"]["needed"] is True
    assert len(trades) == 1 and trades[0]["key"] == "domestic_equity"
    assert trades[0]["action"] == "sell"


def test_overweight_saa_is_rescaled(client, ips_dir, stub_cme, monkeypatch):
    """SAA summing above 100% is proportionally normalized, with a note."""
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _stub_fetch(_prices({
            "000300.SS": [100.0, 100.0, 100.0],
            "AGG": [100.0, 100.0, 100.0],
            "BIL": [100.0, 100.0, 100.0],
        })),
    )
    doc_id = _write_ips_doc(ips_dir, "ips_over_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.7, 0.6, 0.8),
        _saa_entry("固定收益", 0.6, 0.5, 0.7),
    ])  # sums to 1.3 -> scale by 1/1.3

    body = client.get(f"/api/monitoring/{doc_id}").json()

    assert len(body["holdings"]) == 2  # no cash plug when rescaling
    domestic = body["holdings"][0]
    assert domestic["target_weight"] == pytest.approx(0.7 / 1.3)
    assert domestic["min_weight"] == pytest.approx(0.6 / 1.3)
    assert domestic["max_weight"] == pytest.approx(0.8 / 1.3)
    assert any("归一化" in n for n in body["notes"])

    # Flat prices -> drifted == target -> everything within bands
    assert all(h["band_status"] == "within" for h in body["holdings"])
    assert body["rebalance"]["needed"] is False


def test_unknown_asset_class(client, ips_dir, stub_cme, monkeypatch):
    """Unmappable SAA names get key/ticker null and never crash the run."""
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _stub_fetch(_prices({
            "000300.SS": [100.0, 100.0, 100.0],
            "AGG": [100.0, 100.0, 100.0],
        })),
    )
    doc_id = _write_ips_doc(ips_dir, "ips_unknown_20260601_093000", [
        _saa_entry("新兴市场股票", 0.5, 0.4, 0.6),
        _saa_entry("固定收益", 0.5, 0.4, 0.6),
    ])

    resp = client.get(f"/api/monitoring/{doc_id}")
    assert resp.status_code == 200
    body = resp.json()

    unknown, fixed = body["holdings"]
    assert unknown["key"] is None
    assert unknown["ticker"] is None
    assert unknown["metrics"] is None
    assert unknown["period_return"] is None
    assert unknown["band_status"] == "unknown"
    assert any("无法映射" in n for n in body["notes"])

    assert fixed["band_status"] == "within"
    # One holding lacks drift data -> drifted portfolio degrades
    assert body["drifted_portfolio"]["expected_return"] is None
    # Target portfolio still computed over the CME-mapped holding
    assert body["portfolio"]["expected_return"] is not None
