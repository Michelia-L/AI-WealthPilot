"""
AI WealthPilot - LDI Surplus Optimization Tests

Unit tests for src/portfolio/liabilities.py (goal discounting, proxy
duration-scaling) and the Sharpe-Tint surplus methods on
PortfolioOptimizer.
"""

import numpy as np
import pandas as pd
import pytest

from src.portfolio.liabilities import estimate_liability_stats, goals_to_liability
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
