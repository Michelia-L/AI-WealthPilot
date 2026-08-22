"""
AI WealthPilot - Forward-Looking Expected Returns Tests

Covers src/portfolio/forward_returns.py: the building-blocks models
(equity income+growth, bond YTM proxy, gold=inflation, cash=rf),
yfinance yield normalization (percent vs decimal), and the
graceful-degradation paths. All network calls are monkeypatched.
"""

import pytest

from src.portfolio import forward_returns
from src.portfolio.forward_returns import (
    ForwardReturnData,
    _normalize_yield,
    fetch_forward_returns,
)

# ------------------------------------------------------- yield parsing -----

class TestNormalizeYield:
    def test_decimal_passthrough(self):
        assert _normalize_yield(0.018) == pytest.approx(0.018)

    def test_percentage_points_divided_by_100(self):
        assert _normalize_yield(1.8) == pytest.approx(0.018)

    def test_missing_or_invalid_returns_none(self):
        assert _normalize_yield(None) is None
        assert _normalize_yield(0) is None
        assert _normalize_yield(-1.5) is None
        assert _normalize_yield("n/a") is None


# ------------------------------------------------------------- equity ------

class TestEquity:
    def test_income_plus_growth_decimal_yield(self, monkeypatch):
        monkeypatch.setattr(
            forward_returns, "_fetch_info_fields",
            lambda ticker: {"dividendYield": 0.018},
        )
        data = fetch_forward_returns(["EFA"], inflation=0.025, risk_free_rate=0.02)["EFA"]
        assert data is not None
        # 1.8% dividend + 4.0% configured growth
        assert data.forward_return == pytest.approx(0.058)
        assert data.source == "yfinance dividendYield"

    def test_percentage_yield_normalized(self, monkeypatch):
        monkeypatch.setattr(
            forward_returns, "_fetch_info_fields",
            lambda ticker: {"dividendYield": 1.8},
        )
        data = fetch_forward_returns(["EFA"], inflation=0.025, risk_free_rate=0.02)["EFA"]
        assert data.forward_return == pytest.approx(0.058)

    def test_missing_dividend_yield_degrades(self, monkeypatch):
        monkeypatch.setattr(
            forward_returns, "_fetch_info_fields",
            lambda ticker: {"quoteType": "INDEX"},
        )
        assert fetch_forward_returns(
            ["000300.SS"], inflation=0.025, risk_free_rate=0.02
        )["000300.SS"] is None

    def test_index_falls_back_to_yield_proxy(self, monkeypatch):
        """000300.SS (index) uses the ASHR ETF's dividend yield."""
        def fake_info(ticker):
            if ticker == "000300.SS":
                return {"quoteType": "INDEX"}  # no dividendYield
            if ticker == "ASHR":
                return {"dividendYield": 0.022}
            return None

        monkeypatch.setattr(forward_returns, "_fetch_info_fields", fake_info)
        data = fetch_forward_returns(
            ["000300.SS"], inflation=0.025, risk_free_rate=0.02
        )["000300.SS"]
        assert data is not None
        # 2.2% dividend (via ASHR) + 6.0% configured CN growth
        assert data.forward_return == pytest.approx(0.082)
        assert "ASHR" in data.source

    def test_yield_proxy_also_missing_degrades(self, monkeypatch):
        monkeypatch.setattr(
            forward_returns, "_fetch_info_fields", lambda ticker: None
        )
        assert fetch_forward_returns(
            ["000300.SS"], inflation=0.025, risk_free_rate=0.02
        )["000300.SS"] is None

    def test_info_fetch_failure_degrades(self, monkeypatch):
        monkeypatch.setattr(
            forward_returns, "_fetch_info_fields", lambda ticker: None
        )
        assert fetch_forward_returns(
            ["EWH"], inflation=0.025, risk_free_rate=0.02
        )["EWH"] is None


# ---------------------------------------------------------------- bond -----

class TestBond:
    def test_fund_yield_preferred(self, monkeypatch):
        monkeypatch.setattr(
            forward_returns, "_fetch_info_fields",
            lambda ticker: {"yield": 0.041},
        )
        monkeypatch.setattr(
            forward_returns, "_fetch_tnx_yield",
            lambda: pytest.fail("^TNX should not be fetched"),
        )
        data = fetch_forward_returns(["AGG"], inflation=0.025, risk_free_rate=0.02)["AGG"]
        assert data is not None
        assert data.forward_return == pytest.approx(0.041)
        assert data.source == "yfinance fund yield"

    def test_tnx_fallback(self, monkeypatch):
        monkeypatch.setattr(
            forward_returns, "_fetch_info_fields", lambda ticker: None
        )
        monkeypatch.setattr(forward_returns, "_fetch_tnx_yield", lambda: 0.043)
        data = fetch_forward_returns(["AGG"], inflation=0.025, risk_free_rate=0.02)["AGG"]
        assert data is not None
        assert data.forward_return == pytest.approx(0.043)
        assert "^TNX" in data.basis

    def test_all_sources_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            forward_returns, "_fetch_info_fields", lambda ticker: None
        )
        monkeypatch.setattr(forward_returns, "_fetch_tnx_yield", lambda: None)
        assert fetch_forward_returns(
            ["AGG"], inflation=0.025, risk_free_rate=0.02
        )["AGG"] is None


# ----------------------------------------------------- gold / cash / misc --

class TestSimpleKinds:
    def test_gold_equals_inflation(self):
        data = fetch_forward_returns(["GLD"], inflation=0.025, risk_free_rate=0.02)["GLD"]
        assert data is not None
        assert data.forward_return == pytest.approx(0.025)

    def test_cash_equals_risk_free_rate(self):
        data = fetch_forward_returns(["BIL"], inflation=0.025, risk_free_rate=0.02)["BIL"]
        assert data is not None
        assert data.forward_return == pytest.approx(0.02)

    def test_unmapped_ticker_returns_none(self):
        assert fetch_forward_returns(
            ["BTC-USD"], inflation=0.025, risk_free_rate=0.02
        )["BTC-USD"] is None

    def test_every_input_ticker_gets_an_entry(self):
        result = fetch_forward_returns(
            ["GLD", "BIL", "BTC-USD"], inflation=0.025, risk_free_rate=0.02
        )
        assert set(result) == {"GLD", "BIL", "BTC-USD"}
        assert isinstance(result["GLD"], ForwardReturnData)
        assert result["BTC-USD"] is None
