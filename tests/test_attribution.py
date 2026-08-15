"""
AI WealthPilot - Brinson-Fachler Attribution Tests

Covers src/portfolio/attribution.py: ticker grouping, span-level series
on the backtest engine's rebalancing calendar, the per-span A+S+I
identity, and Carino geometric linking. All synthetic — no network.
"""

import numpy as np
import pandas as pd
import pytest

from src.portfolio.attribution import (
    brinson_attribution,
    group_of_ticker,
    monthly_group_series,
)


# ------------------------------------------------------------- grouping --

class TestGrouping:
    def test_known_tickers(self):
        assert group_of_ticker("SPY") == "equity"
        assert group_of_ticker("AGG") == "bond"
        assert group_of_ticker("GLD") == "alternative"
        assert group_of_ticker("BIL") == "cash"

    def test_ips_proxy_tickers_map_to_groups(self):
        """The CME/IPS universe maps onto groups (CSI 300 index is equity)."""
        assert group_of_ticker("000300.SS") == "equity"
        assert group_of_ticker("EWH") == "equity"
        assert group_of_ticker("511010.SS") == "bond"

    def test_unknown_ticker_lands_in_other(self):
        assert group_of_ticker("XYZ123") == "other"


# ------------------------------------------------------- hand-computed --

def _hand_frame() -> pd.DataFrame:
    """Two spans with exact boundary returns: SPY +10%/−5%, AGG 0%/+2%."""
    idx = pd.to_datetime(["2025-01-02", "2025-02-03", "2025-03-03"])
    return pd.DataFrame(
        {"SPY": [100.0, 110.0, 104.5], "AGG": [100.0, 100.0, 102.0]},
        index=idx,
    )


class TestHandComputed:
    """Portfolio 80/20 vs benchmark 60/40 over two spans."""

    def test_span_identity_and_bf_allocation(self):
        rows_p = monthly_group_series(_hand_frame(), {"SPY": 0.8, "AGG": 0.2})
        rows_b = monthly_group_series(_hand_frame(), {"SPY": 0.6, "AGG": 0.4})
        assert len(rows_p) == len(rows_b) == 2

        # Span 1: R_b = 0.06, R_p = 0.08
        w_p, R_g, R_tot = rows_p[0]
        assert R_tot == pytest.approx(0.08)
        assert R_g["equity"] == pytest.approx(0.10)
        assert R_g["bond"] == pytest.approx(0.0)

        # BF allocation span 1: equity (0.8−0.6)(0.10−0.06)=+0.008,
        # bond (0.2−0.4)(0−0.06)=+0.012 → total +0.02 == R_p − R_b
        w_b, R_b_g, R_b_tot = rows_b[0]
        a_eq = (0.8 - 0.6) * (0.10 - 0.06)
        a_bd = (0.2 - 0.4) * (0.0 - 0.06)
        assert a_eq + a_bd == pytest.approx(R_tot - R_b_tot)

    def test_carino_linked_totals(self):
        result = brinson_attribution(
            monthly_group_series(_hand_frame(), {"SPY": 0.8, "AGG": 0.2}),
            monthly_group_series(_hand_frame(), {"SPY": 0.6, "AGG": 0.4}),
        )
        assert result is not None
        assert result["months"] == 2

        # Selection and interaction vanish: same assets on both sides.
        assert result["selection"] == pytest.approx(0.0, abs=1e-12)
        assert result["interaction"] == pytest.approx(0.0, abs=1e-12)

        # Cumulative active return: 1.08·0.964 − 1.06·0.978
        active = 1.08 * 0.964 - 1.06 * 0.978
        assert result["active_return"] == pytest.approx(active)
        # Carino-linked effects sum exactly to the cumulative active return.
        assert result["allocation"] + result["selection"] + result[
            "interaction"
        ] == pytest.approx(active)

        # Hand-linked allocation: K·(k1·A1 + k2·A2)
        k1 = np.log(1.08 / 1.06) / 0.02
        k2 = np.log(0.964 / 0.978) / (-0.014)
        K = active / (np.log(1.04112) - np.log(1.03668))
        expected = K * (0.02 * k1 + (-0.014) * k2)
        assert result["allocation"] == pytest.approx(expected)

        # Per-group rows cover both groups and sum to the total.
        by_group = {g["group"]: g for g in result["groups"]}
        assert set(by_group) == {"equity", "bond"}
        assert sum(g["total"] for g in result["groups"]) == pytest.approx(active)


# ------------------------------------------------------------- property --

class TestIdentityProperty:
    def test_per_span_identity_random_multi_group(self):
        """Σ_g(A+S+I) == R_p,m − R_b,m per span, random 4-asset data."""
        rng = np.random.default_rng(3)
        idx = pd.bdate_range("2025-01-06", periods=90)
        prices = pd.DataFrame(
            100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, (90, 4)), axis=0)),
            index=idx,
            columns=["SPY", "AGG", "GLD", "BIL"],
        )
        port = {"SPY": 0.5, "AGG": 0.2, "GLD": 0.2, "BIL": 0.1}
        # benchmark holds no gold/cash → exercises the BF absent-group rule
        bench = {"SPY": 0.6, "AGG": 0.4}
        rows_p = monthly_group_series(prices, port)
        rows_b = monthly_group_series(prices, bench)
        assert len(rows_p) == len(rows_b) >= 2

        for (w_p, R_p_g, R_p_m), (w_b, R_b_g, R_b_m) in zip(rows_p, rows_b):
            total = 0.0
            for g in set(w_p) | set(w_b):
                wp, wb = w_p.get(g, 0.0), w_b.get(g, 0.0)
                rp, rb = R_p_g.get(g, np.nan), R_b_g.get(g, np.nan)
                if wb == 0.0 and not np.isnan(rp):
                    rb = rp
                if np.isnan(rp) or np.isnan(rb):
                    continue
                total += (
                    (wp - wb) * (rb - R_b_m)
                    + wb * (rp - rb)
                    + (wp - wb) * (rp - rb)
                )
            assert total == pytest.approx(R_p_m - R_b_m, abs=1e-12)

    def test_linked_effects_sum_to_active_return(self):
        rng = np.random.default_rng(5)
        idx = pd.bdate_range("2025-01-06", periods=120)
        prices = pd.DataFrame(
            100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, (120, 3)), axis=0)),
            index=idx,
            columns=["SPY", "AGG", "GLD"],
        )
        result = brinson_attribution(
            monthly_group_series(prices, {"SPY": 0.5, "AGG": 0.3, "GLD": 0.2}),
            monthly_group_series(prices, {"SPY": 0.6, "AGG": 0.4}),
        )
        assert result is not None
        assert (
            result["allocation"] + result["selection"] + result["interaction"]
            == pytest.approx(result["active_return"])
        )


# ----------------------------------------------------------------- edges --

class TestEdges:
    def test_unknown_ticker_grouped_as_other(self):
        idx = pd.bdate_range("2025-01-06", periods=70)
        rng = np.random.default_rng(9)
        prices = pd.DataFrame(
            100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, (70, 2)), axis=0)),
            index=idx,
            columns=["ZZZ", "AGG"],
        )
        rows = monthly_group_series(prices, {"ZZZ": 0.6, "AGG": 0.4})
        assert "other" in rows[0][0]
        assert rows[0][0]["other"] == pytest.approx(0.6)

    def test_fewer_than_two_spans_returns_none(self):
        idx = pd.bdate_range("2025-01-06", periods=20)  # single month
        prices = pd.DataFrame(
            {"SPY": np.linspace(100, 105, 20), "AGG": np.linspace(50, 50.5, 20)},
            index=idx,
        )
        assert brinson_attribution(
            monthly_group_series(prices, {"SPY": 0.6, "AGG": 0.4}),
            monthly_group_series(prices, {"SPY": 0.6, "AGG": 0.4}),
        ) is None
