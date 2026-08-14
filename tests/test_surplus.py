"""
AI WealthPilot - LDI Surplus Optimization Tests

Unit tests for src/portfolio/liabilities.py (goal discounting, proxy
duration-scaling) and the Sharpe-Tint surplus methods on
PortfolioOptimizer.
"""

import numpy as np
import pandas as pd
import pytest

from src.portfolio.liabilities import (
    estimate_liability_stats,
    goals_to_liability,
    retirement_income_stream,
    stream_to_liability,
)
from src.portfolio.optimizer import PortfolioOptimizer


@pytest.fixture
def returns_with_proxy():
    """Synthetic daily returns with a bond proxy correlated to BOND."""
    rng = np.random.default_rng(11)
    n_days = 800
    proxy = pd.Series(rng.normal(0.0002, 0.004, n_days), name="PROXY")
    assets = pd.DataFrame({
        "EQ": rng.normal(0.0005, 0.012, n_days) * 0.9 + proxy.values * 0.3,
        "BOND": proxy.values * 1.2 + rng.normal(0.0, 0.001, n_days),
        "GOLD": rng.normal(0.0003, 0.010, n_days),
    })
    return assets, proxy


# ============================================================
# goals_to_liability
# ============================================================

class TestGoalsToLiability:
    """Goal-stream discounting into PV + Macaulay duration."""

    def test_single_goal_hand_calc(self):
        pv, duration = goals_to_liability(
            [{"target_amount": 1_000_000, "years": 10}], 0.03
        )
        assert pv == pytest.approx(1_000_000 / 1.03**10)
        assert duration == pytest.approx(10.0)

    def test_duration_is_pv_weighted_average(self):
        goals = [
            {"target_amount": 1_000_000, "years": 10},
            {"target_amount": 500_000, "years": 20},
        ]
        pv, duration = goals_to_liability(goals, 0.025)
        pv1 = 1_000_000 / 1.025**10
        pv2 = 500_000 / 1.025**20
        assert pv == pytest.approx(pv1 + pv2)
        assert duration == pytest.approx((10 * pv1 + 20 * pv2) / (pv1 + pv2))

    def test_zero_amount_goals_are_skipped(self):
        pv, duration = goals_to_liability(
            [
                {"target_amount": 0, "years": 5},
                {"target_amount": 100_000, "years": 8},
            ],
            0.03,
        )
        assert pv == pytest.approx(100_000 / 1.03**8)
        assert duration == pytest.approx(8.0)

    def test_empty_or_all_zero_raises(self):
        with pytest.raises(ValueError):
            goals_to_liability([], 0.03)
        with pytest.raises(ValueError):
            goals_to_liability([{"target_amount": 0, "years": 5}], 0.03)


# ============================================================
# stream_to_liability / retirement_income_stream (LDI v2)
# ============================================================

class TestStreamToLiability:
    """Cash-flow stream discounting with separate growth/discount rates."""

    def test_ungrown_single_flow_hand_calc(self):
        """growth_rate=0 ⇒ plain discounting at y."""
        pv, duration = stream_to_liability([(1_000_000, 10)], 0.03)
        assert pv == pytest.approx(1_000_000 / 1.03**10)
        assert duration == pytest.approx(10.0)

    def test_grown_flows_hand_calc(self):
        """Today's-money flows grow at g, then discount at y."""
        flows = [(100_000, 5), (100_000, 10)]
        pv, duration = stream_to_liability(flows, discount_rate=0.02, growth_rate=0.025)
        pv1 = 100_000 * 1.025**5 / 1.02**5
        pv2 = 100_000 * 1.025**10 / 1.02**10
        assert pv == pytest.approx(pv1 + pv2)
        assert duration == pytest.approx((5 * pv1 + 10 * pv2) / (pv1 + pv2))

    def test_equal_growth_and_discount_neutralizes(self):
        """g == y ⇒ growth and discounting cancel: PV = Σ base amounts."""
        flows = [(80_000, t) for t in range(6, 26)]
        pv, duration = stream_to_liability(flows, 0.025, 0.025)
        assert pv == pytest.approx(80_000 * 20)
        assert duration == pytest.approx(sum(range(6, 26)) / 20)

    def test_zero_discount_keeps_nominal_sum(self):
        """rf = 0 ⇒ PV = Σ grown amounts (retirement-channel test convention)."""
        flows = [(80_000, t) for t in range(6, 26)]
        pv, _ = stream_to_liability(flows, 0.0, 0.025)
        assert pv == pytest.approx(sum(80_000 * 1.025**t for t in range(6, 26)))

    def test_empty_stream_raises(self):
        with pytest.raises(ValueError):
            stream_to_liability([], 0.02)
        with pytest.raises(ValueError):
            stream_to_liability([(0.0, 5)], 0.02)

    def test_curve_discounting_per_tenor(self):
        """A curve dict discounts each flow at its interpolated y(t)."""
        curve = {1.0: 0.01, 10.0: 0.02, 30.0: 0.03}
        flows = [(100_000, 1), (100_000, 10)]
        pv, duration = stream_to_liability(flows, curve)
        pv1 = 100_000 / 1.01
        pv10 = 100_000 / 1.02**10
        assert pv == pytest.approx(pv1 + pv10)
        assert duration == pytest.approx((pv1 + 10 * pv10) / (pv1 + pv10))

    def test_curve_vs_flat_differs_when_sloped(self):
        """An upward-sloping curve prices long flows cheaper than a flat 1y rate."""
        curve = {1.0: 0.01, 30.0: 0.04}
        flows = [(100_000, 20)]
        pv_curve, _ = stream_to_liability(flows, curve)
        pv_flat, _ = stream_to_liability(flows, 0.01)
        assert pv_curve < pv_flat


class TestRetirementIncomeStream:
    """retirement_income_stream shape."""

    def test_year_range_and_amounts(self):
        flows = retirement_income_stream(
            years_to_retirement=20, distribution_years=25, annual_income=80_000
        )
        assert len(flows) == 25
        assert flows[0] == (80_000.0, 21)
        assert flows[-1] == (80_000.0, 45)
        assert all(amount == 80_000.0 for amount, _ in flows)

    def test_immediate_retirement_starts_next_year(self):
        flows = retirement_income_stream(0, 10, 50_000)
        assert flows[0][1] == 1
        assert flows[-1][1] == 10


# ============================================================
# estimate_liability_stats
# ============================================================

class TestEstimateLiabilityStats:
    """Duration-scaled proxy model: r_L = g + λ·(r_p − μ_p)."""

    def test_lambda_scaling(self, returns_with_proxy):
        assets, proxy = returns_with_proxy
        growth = 0.03
        mu_L, sigma_L, cov_vec = estimate_liability_stats(
            proxy, assets, proxy_duration=6.0, liability_duration=15.0,
            growth_rate=growth,
        )
        lam = 15.0 / 6.0
        assert mu_L == growth
        assert sigma_L == pytest.approx(
            lam * float(np.std(proxy.values, ddof=1) * np.sqrt(252))
        )
        for i, col in enumerate(assets.columns):
            expected = lam * np.cov(assets[col].values, proxy.values)[0, 1] * 252
            assert cov_vec[i] == pytest.approx(expected)

    def test_zero_duration_ratio_zeroes_risk(self, returns_with_proxy):
        """D_L = 0 ⇒ the liability is riskless: σ_L = 0, c = 0, μ_L = g."""
        assets, proxy = returns_with_proxy
        mu_L, sigma_L, cov_vec = estimate_liability_stats(
            proxy, assets, proxy_duration=6.0, liability_duration=0.0,
            growth_rate=0.02,
        )
        assert mu_L == 0.02
        assert sigma_L == 0.0
        np.testing.assert_allclose(cov_vec, 0.0)


# ============================================================
# Surplus optimization (Sharpe-Tint)
# ============================================================

class TestSurplusOptimization:
    """Surplus QP on PortfolioOptimizer."""

    def _liability(self, returns_with_proxy, duration=15.0, growth=0.025):
        assets, proxy = returns_with_proxy
        return estimate_liability_stats(
            proxy, assets, proxy_duration=6.0,
            liability_duration=duration, growth_rate=growth,
        )

    def test_zero_ratio_degenerates_to_classic_mvo(self, returns_with_proxy):
        """k = 0 ⇒ no liability: surplus min-vol == classic min-vol."""
        assets, _ = returns_with_proxy
        opt = PortfolioOptimizer(assets)
        classic = opt.minimize_volatility()
        surplus = opt.minimize_surplus_volatility(
            0.0, 0.02, 0.05, np.zeros(len(assets.columns))
        )
        for name in assets.columns:
            assert surplus["weights"][name] == pytest.approx(
                classic["weights"][name], abs=1e-6
            )

    def test_liability_hedging_demand(self, returns_with_proxy):
        """A proxy-correlated liability tilts min-vol toward the bond leg."""
        assets, _ = returns_with_proxy
        opt = PortfolioOptimizer(assets)
        mu_L, sigma_L, cov_vec = self._liability(returns_with_proxy)
        classic = opt.minimize_volatility()
        surplus = opt.minimize_surplus_volatility(1.0, mu_L, sigma_L, cov_vec)
        assert surplus["weights"]["BOND"] > classic["weights"]["BOND"]

    def test_weights_sum_to_one(self, returns_with_proxy):
        assets, _ = returns_with_proxy
        opt = PortfolioOptimizer(assets)
        mu_L, sigma_L, cov_vec = self._liability(returns_with_proxy)
        for result in (
            opt.minimize_surplus_volatility(1.0, mu_L, sigma_L, cov_vec),
            opt.maximize_surplus_sharpe(1.0, mu_L, sigma_L, cov_vec),
        ):
            assert result["success"]
            assert abs(sum(result["weights"].values()) - 1.0) < 1e-6

    def test_surplus_sharpe_uses_no_risk_free(self, returns_with_proxy):
        """Surplus Sharpe convention: E(R_S)/σ_S, rf not subtracted."""
        assets, _ = returns_with_proxy
        opt = PortfolioOptimizer(assets, risk_free_rate=0.10)  # absurd rf
        mu_L, sigma_L, cov_vec = self._liability(returns_with_proxy)
        w = np.ones(len(assets.columns)) / len(assets.columns)
        ret, vol, sharpe = opt.surplus_performance(w, 1.0, mu_L, sigma_L, cov_vec)
        assert sharpe == pytest.approx(ret / vol)

    def test_frontier_shape_and_weights(self, returns_with_proxy):
        assets, _ = returns_with_proxy
        opt = PortfolioOptimizer(assets)
        mu_L, sigma_L, cov_vec = self._liability(returns_with_proxy)
        frontier = opt.surplus_efficient_frontier(
            1.0, mu_L, sigma_L, cov_vec, n_points=10
        )
        assert not frontier.empty
        assert len(frontier) <= 10
        assert {"return", "volatility", "sharpe"} <= set(frontier.columns)
        weight_sums = frontier[list(assets.columns)].sum(axis=1)
        np.testing.assert_allclose(weight_sums, 1.0, atol=1e-6)

    def test_frontier_volatility_u_shape(self, returns_with_proxy):
        """Surplus vol along the frontier bottoms near the min-vol point."""
        assets, _ = returns_with_proxy
        opt = PortfolioOptimizer(assets)
        mu_L, sigma_L, cov_vec = self._liability(returns_with_proxy)
        frontier = opt.surplus_efficient_frontier(
            1.0, mu_L, sigma_L, cov_vec, n_points=12
        )
        assert frontier["volatility"].iloc[-1] > frontier["volatility"].min()

    def test_allow_short(self, returns_with_proxy):
        assets, _ = returns_with_proxy
        opt = PortfolioOptimizer(assets)
        mu_L, sigma_L, cov_vec = self._liability(returns_with_proxy)
        result = opt.minimize_surplus_volatility(
            1.0, mu_L, sigma_L, cov_vec, allow_short=True
        )
        assert result["success"]
        assert abs(sum(result["weights"].values()) - 1.0) < 1e-6
