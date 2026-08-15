"""
API tests for portfolio monitoring & rebalancing (P10).

The CME engine and market data layer are stubbed via monkeypatch — tests
cover the monitoring math (weight normalization, drift, bands, rebalance
trades) and the HTTP contract (200 / 404 / 422), not live data sources.

The P17 section covers the fleet-wide band-status aggregation behind
GET /monitoring/status (one shared price fetch, per-document degrade,
daily TTL cache).
"""

import json
from datetime import date, datetime

import pandas as pd
import pytest

from api.routers import monitoring as monitoring_router
from src.portfolio.cme_models import AssetClassCME, CMEReport

SAVED_AT = "2026-06-01T09:30:00"

# Frozen clock for as_of assertions: the server reads datetime.now() inside
# src.portfolio.monitoring, so a local datetime.now() assertion races midnight.
FROZEN_DATE = "2026-06-15"


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 15, 23, 59)


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
    monkeypatch.setattr("src.portfolio.monitoring.datetime", _FrozenDatetime)
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
    assert body["as_of"] == FROZEN_DATE
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


# ---------------------------------------------------------------------------
# P17 — fleet-wide band status (GET /monitoring/status)
# ---------------------------------------------------------------------------

# 10 business days 2026-06-01 .. 2026-06-12; equity +80% over the full
# window, bonds -10%.
FLEET_PRICES = _prices({
    "000300.SS": [100.0, 110.0, 120.0, 130.0, 140.0,
                  150.0, 160.0, 170.0, 175.0, 180.0],
    "AGG": [100.0, 99.0, 98.0, 97.0, 96.0,
            95.0, 94.0, 93.0, 92.0, 90.0],
})

FLAT_PRICES = _prices({
    "000300.SS": [100.0] * 10,
    "AGG": [100.0] * 10,
})


def _counting_fetch(df, counter):
    """Price stub that records how often the shared fetch ran."""
    def fetch(tickers=None, period="5y", interval="1d",
              base_currency=None, adjust_currency=True):
        counter["calls"] += 1
        return df
    return fetch


@pytest.fixture(autouse=True)
def _reset_fleet_status_cache():
    """The module-level fleet TTLCache must not leak results across tests."""
    # P22: the cache key carries the request locale (zh via the client
    # fixture, en for headerless/explicit-en requests).
    keys = [
        f"fleet-status:{date.today().isoformat()}:{locale}" for locale in ("zh", "en")
    ]
    for key in keys:
        monitoring_router._fleet_status_cache.invalidate(key)
    yield
    for key in keys:
        monitoring_router._fleet_status_cache.invalidate(key)


def test_fleet_status_full_chain(client, ips_dir, monkeypatch):
    """One breach doc + one ok doc; single shared fetch; saved_at desc."""
    monkeypatch.setattr("src.portfolio.monitoring.datetime", _FrozenDatetime)
    counter = {"calls": 0}
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _counting_fetch(FLEET_PRICES, counter),
    )
    # Filename sorts after the ok doc, so a filename ordering would put the
    # breach doc first — asserting the ok doc leads proves the saved_at sort.
    _write_ips_doc(ips_dir, "ips_fleet_zbreach_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.5, 0.4, 0.6),
        _saa_entry("固定收益", 0.5, 0.4, 0.6),
    ], saved_at="2026-06-01T09:30:00", client_name="越带客户")
    _write_ips_doc(ips_dir, "ips_fleet_ok_20260610_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.5, 0.3, 0.8),
        _saa_entry("固定收益", 0.5, 0.2, 0.7),
    ], saved_at="2026-06-10T09:30:00", client_name="正常客户")

    resp = client.get("/api/monitoring/status")
    assert resp.status_code == 200
    body = resp.json()

    assert body["as_of"] == FROZEN_DATE
    assert body["price_as_of"] == "2026-06-12"
    assert body["summary"] == {"total": 2, "breach": 1, "ok": 1, "unknown": 0}
    # One shared fetch for the union of tickers, not one per document
    assert counter["calls"] == 1

    ok_item, breach_item = body["items"]  # saved_at descending

    assert ok_item["document_id"] == "ips_fleet_ok_20260610_093000"
    assert ok_item["client_name"] == "正常客户"
    assert ok_item["saved_at"] == "2026-06-10T09:30:00"
    assert ok_item["status"] == "ok"
    assert ok_item["out_of_band"] == 0
    # Window 06-10 -> 06-12: equity 170->180, AGG 93->90
    # drifted domestic = .5*(180/170) / (.5*(180/170) + .5*(90/93)) = 93/178
    assert ok_item["max_abs_drift_pp"] == pytest.approx(93 / 178 - 0.5)
    assert ok_item["note"] is None

    assert breach_item["document_id"] == "ips_fleet_zbreach_20260601_093000"
    assert breach_item["status"] == "breach"
    assert breach_item["out_of_band"] == 2  # equity above, bonds below
    assert breach_item["max_abs_drift_pp"] == pytest.approx(0.9 / 1.35 - 0.5)
    assert breach_item["note"] is None


def test_fleet_status_no_saa_degrades(client, ips_dir, monkeypatch):
    """A doc without SAA turns unknown + note; the other doc is unaffected."""
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _stub_fetch(FLAT_PRICES),
    )
    _write_ips_doc(ips_dir, "ips_fleet_nosaa_20260601_093000", [],
                   saved_at="2026-06-01T09:30:00")
    _write_ips_doc(ips_dir, "ips_fleet_flat_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.5, 0.4, 0.6),
        _saa_entry("固定收益", 0.5, 0.4, 0.6),
    ], saved_at="2026-06-01T09:30:00")

    resp = client.get("/api/monitoring/status")
    assert resp.status_code == 200
    body = resp.json()

    assert body["summary"] == {"total": 2, "breach": 0, "ok": 1, "unknown": 1}
    items = {i["document_id"]: i for i in body["items"]}

    nosaa = items["ips_fleet_nosaa_20260601_093000"]
    assert nosaa["status"] == "unknown"
    assert nosaa["out_of_band"] == 0
    assert nosaa["max_abs_drift_pp"] is None
    assert "战略性资产配置" in nosaa["note"]

    flat = items["ips_fleet_flat_20260601_093000"]
    assert flat["status"] == "ok"
    assert flat["max_abs_drift_pp"] == pytest.approx(0.0)
    assert flat["note"] is None


def test_fleet_status_unparsable_doc_degrades(client, ips_dir, monkeypatch):
    """A doc whose SAA weights cannot parse degrades alone (no 5xx)."""
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _stub_fetch(FLAT_PRICES),
    )
    bad = _saa_entry("国内权益（A股/沪深300）", 0.5, 0.4, 0.6)
    bad["target_weight"] = "not-a-number"
    _write_ips_doc(ips_dir, "ips_fleet_broken_20260601_093000", [bad],
                   saved_at="2026-06-01T09:30:00")
    _write_ips_doc(ips_dir, "ips_fleet_flat_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.5, 0.4, 0.6),
        _saa_entry("固定收益", 0.5, 0.4, 0.6),
    ], saved_at="2026-06-01T09:30:00")

    resp = client.get("/api/monitoring/status")
    assert resp.status_code == 200
    body = resp.json()

    assert body["summary"] == {"total": 2, "breach": 0, "ok": 1, "unknown": 1}
    broken = next(
        i for i in body["items"]
        if i["document_id"] == "ips_fleet_broken_20260601_093000"
    )
    assert broken["status"] == "unknown"
    assert "解析失败" in broken["note"]


def test_fleet_status_fetch_failure_all_unknown(client, ips_dir, monkeypatch):
    """Price fetch raising degrades every doc to unknown; endpoint stays 200."""
    def _raising_fetch(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history", _raising_fetch
    )
    for i in range(2):
        _write_ips_doc(ips_dir, f"ips_fleet_doc{i}_20260601_093000", [
            _saa_entry("国内权益（A股/沪深300）", 0.5, 0.4, 0.6),
            _saa_entry("固定收益", 0.5, 0.4, 0.6),
        ], saved_at="2026-06-01T09:30:00")

    resp = client.get("/api/monitoring/status")
    assert resp.status_code == 200
    body = resp.json()

    assert body["price_as_of"] is None
    assert body["summary"] == {"total": 2, "breach": 0, "ok": 0, "unknown": 2}
    for item in body["items"]:
        assert item["status"] == "unknown"
        assert "行情数据获取失败" in item["note"]


def test_fleet_status_cached_until_refresh(client, ips_dir, monkeypatch):
    """Second call hits the daily cache; ?refresh=true recomputes."""
    counter = {"calls": 0}
    monkeypatch.setattr(
        "src.portfolio.monitoring.fetch_price_history",
        _counting_fetch(FLAT_PRICES, counter),
    )
    _write_ips_doc(ips_dir, "ips_fleet_flat_20260601_093000", [
        _saa_entry("国内权益（A股/沪深300）", 0.5, 0.4, 0.6),
        _saa_entry("固定收益", 0.5, 0.4, 0.6),
    ], saved_at="2026-06-01T09:30:00")

    assert client.get("/api/monitoring/status").status_code == 200
    assert counter["calls"] == 1
    assert client.get("/api/monitoring/status").status_code == 200
    assert counter["calls"] == 1  # cache hit
    assert client.get("/api/monitoring/status?refresh=true").status_code == 200
    assert counter["calls"] == 2  # invalidated, recomputed
    assert client.get("/api/monitoring/status").status_code == 200
    assert counter["calls"] == 2


def test_fleet_status_route_not_shadowed_by_document_id(client):
    """/monitoring/status must not be captured by /{document_id} (->404)."""
    resp = client.get("/api/monitoring/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["summary"] == {"total": 0, "breach": 0, "ok": 0, "unknown": 0}
