"""
AI WealthPilot - China Treasury Yield Curve Tests

Covers src/data/yield_curve.py: rate_at interpolation and the
tushare → akshare → None provider cascade. All network calls are
monkeypatched — tushare's yc_cb is a separately-permissioned interface
and akshare is disabled in this suite's conftest by default.
"""

import sys
import types

import pandas as pd
import pytest

from src.data import yield_curve
from src.data.yield_curve import fetch_china_treasury_curve, rate_at


# ---------------------------------------------------------------- rate_at --

class TestRateAt:
    CURVE = {1.0: 0.012, 5.0: 0.014, 10.0: 0.017, 30.0: 0.022}

    def test_exact_tenor_hits_node(self):
        assert rate_at(self.CURVE, 5.0) == pytest.approx(0.014)

    def test_interpolates_linearly(self):
        # midpoint of 1–5y: 0.012 + 0.5 × 0.002 = 0.013
        assert rate_at(self.CURVE, 3.0) == pytest.approx(0.013)
        # quarter of the 10–30y segment: 0.017 + 0.25 × 0.005 = 0.01825
        assert rate_at(self.CURVE, 15.0) == pytest.approx(0.01825)

    def test_flattens_beyond_the_ends(self):
        assert rate_at(self.CURVE, 0.25) == pytest.approx(0.012)
        assert rate_at(self.CURVE, 40.0) == pytest.approx(0.022)

    def test_empty_curve_raises(self):
        with pytest.raises(ValueError):
            rate_at({}, 5.0)


# ------------------------------------------------------- tushare tier -----

def _fake_yc_cb_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": ["20260813", "20260814", "20260814"],
        "ts_code": ["1001.CB"] * 3,
        "curve_name": ["中债国债收益率曲线"] * 3,
        "curve_type": ["0"] * 3,
        "curve_term": [1.0, 1.0, 10.0],
        "yield": [1.10, 1.21, 1.70],
    })


class TestTushareTier:
    def test_parses_latest_trade_date(self, monkeypatch):
        monkeypatch.setattr(yield_curve, "TUSHARE_TOKEN", "fake-token")
        monkeypatch.setattr(
            "tushare.pro_api",
            lambda token: type("Pro", (), {"yc_cb": lambda self, **kw: _fake_yc_cb_frame()})(),
        )
        curve = yield_curve._from_tushare()
        assert curve == {1.0: pytest.approx(0.0121), 10.0: pytest.approx(0.017)}

    def test_no_token_returns_none(self, monkeypatch):
        monkeypatch.setattr(yield_curve, "TUSHARE_TOKEN", "")
        assert yield_curve._from_tushare() is None

    def test_permission_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(yield_curve, "TUSHARE_TOKEN", "fake-token")

        def boom(token):
            raise Exception("抱歉，您没有接口(yc_cb)访问权限")

        monkeypatch.setattr("tushare.pro_api", boom)
        assert yield_curve._from_tushare() is None


# ------------------------------------------------------- akshare tier -----

def _fake_akshare_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "曲线名称": ["中债国债收益率曲线", "中债国债收益率曲线", "其他曲线"],
        "日期": ["2026-08-13", "2026-08-14", "2026-08-14"],
        "3月": [1.10, 1.19, 9.99],
        "6月": [1.11, 1.20, 9.99],
        "1年": [1.12, 1.21, 9.99],
        "3年": [1.13, 1.26, 9.99],
        "5年": [1.14, 1.39, 9.99],
        "7年": [1.15, 1.52, 9.99],
        "10年": [1.16, 1.70, 9.99],
        "30年": [1.17, 2.16, 9.99],
    })


class TestAkshareTier:
    def test_parses_latest_treasury_row(self, monkeypatch):
        monkeypatch.setattr(
            "src.data.akshare_provider.is_available", lambda: True
        )
        # Inject a fake akshare module: akshare is an optional local-only
        # dependency and is not installed in CI.
        fake_ak = types.ModuleType("akshare")
        fake_ak.bond_china_yield = (
            lambda start_date, end_date: _fake_akshare_frame()
        )
        monkeypatch.setitem(sys.modules, "akshare", fake_ak)
        curve = yield_curve._from_akshare()
        assert curve is not None
        assert curve[0.25] == pytest.approx(0.0119)
        assert curve[10.0] == pytest.approx(0.017)
        assert curve[30.0] == pytest.approx(0.0216)

    def test_provider_unavailable_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "src.data.akshare_provider.is_available", lambda: False
        )
        assert yield_curve._from_akshare() is None


# --------------------------------------------------------- cascade --------

class TestCascade:
    def test_tushare_wins_when_available(self, monkeypatch):
        monkeypatch.setattr(
            yield_curve, "_from_tushare", lambda: {1.0: 0.01}
        )
        monkeypatch.setattr(
            yield_curve, "_from_akshare", lambda: {1.0: 0.99}
        )
        assert fetch_china_treasury_curve() == ({1.0: 0.01}, "tushare")

    def test_falls_through_to_akshare(self, monkeypatch):
        monkeypatch.setattr(yield_curve, "_from_tushare", lambda: None)
        monkeypatch.setattr(
            yield_curve, "_from_akshare", lambda: {1.0: 0.02}
        )
        assert fetch_china_treasury_curve() == ({1.0: 0.02}, "akshare")

    def test_none_when_every_tier_fails(self, monkeypatch):
        monkeypatch.setattr(yield_curve, "_from_tushare", lambda: None)
        monkeypatch.setattr(yield_curve, "_from_akshare", lambda: None)
        assert fetch_china_treasury_curve() is None
