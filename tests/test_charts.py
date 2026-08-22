"""Unit tests for src.visualization.charts (Plotly figure builders).

Figures are asserted structurally — trace count/type/names/data values —
without rendering. All inputs are locally constructed; no network access.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.visualization.charts import (
    get_asset_color,
    plot_allocation_pie,
    plot_backtest_equity,
    plot_correlation_heatmap,
    plot_drawdown,
    plot_efficient_frontier,
    plot_monte_carlo_paths,
    plot_price_history,
)


def _frontier() -> pd.DataFrame:
    return pd.DataFrame(
        {"return": [0.04, 0.08, 0.12], "volatility": [0.05, 0.12, 0.20]}
    )


def _random_ports(n: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    return pd.DataFrame(
        {
            "return": rng.normal(0.07, 0.03, n),
            "volatility": rng.normal(0.15, 0.05, n),
            "sharpe": rng.normal(0.5, 0.2, n),
        }
    )


class TestGetAssetColor:
    def test_ticker_match_from_asset_universe(self):
        assert get_asset_color("BTC-USD", 0) == "#F7931A"

    def test_name_match_from_asset_universe(self):
        assert get_asset_color("Gold Futures", 0) == "#FFD700"

    def test_gold_ticker_keeps_iconic_color(self):
        assert get_asset_color("GLD", 0) == "#FFD700"

    def test_equity_class_fallback_color(self):
        # "US Equities (S&P 500)" → DEFAULT_ASSET_CLASSES key US_EQUITY
        assert get_asset_color("US Equities (S&P 500)", 0) == "#06B6D4"

    def test_bond_class_fallback_color(self):
        # AGG → key US_BOND, matched on "BOND" before "TREASURY"
        assert get_asset_color("AGG", 0) == "#3B82F6"

    def test_unknown_uses_fallback_palette_by_index(self):
        assert get_asset_color("NO_SUCH_ASSET", 0) == "#D4AF37"
        # Palette has 7 entries: index wraps around
        assert get_asset_color("NO_SUCH_ASSET", 7) == get_asset_color(
            "NO_SUCH_ASSET", 0
        )
        assert get_asset_color("NO_SUCH_ASSET", 1) == "#10B981"


class TestPlotEfficientFrontier:
    def test_frontier_only_has_single_trace(self):
        fig = plot_efficient_frontier(_frontier())
        assert len(fig.data) == 1
        assert fig.data[0].name == "Efficient Frontier"

    def test_full_parameter_set_traces(self):
        fig = plot_efficient_frontier(
            _frontier(),
            random_portfolios=_random_ports(),
            max_sharpe={"return": 0.10, "volatility": 0.15, "sharpe": 0.8},
            min_vol={"return": 0.04, "volatility": 0.05, "sharpe": 0.3},
            risk_free_rate=0.02,
        )
        names = [t.name for t in fig.data]
        assert names[0] == "Random Portfolios"
        assert "Efficient Frontier" in names
        assert any(n.startswith("Max Sharpe") for n in names)
        assert any(n.startswith("Min Volatility") for n in names)
        assert any(n.startswith("Capital Allocation Line") for n in names)

    def test_cal_endpoints(self):
        # cal_max_vol = max(2.5 * 15, 1.2 * 20) = 37.5; E(R) = Rf + Sharpe * sigma
        fig = plot_efficient_frontier(
            _frontier(),
            max_sharpe={"return": 0.10, "volatility": 0.15, "sharpe": 0.8},
            risk_free_rate=0.02,
        )
        cal = [t for t in fig.data if t.name.startswith("Capital Allocation Line")][0]
        assert list(cal.x) == [0, 37.5]
        assert list(cal.y) == [2.0, 2.0 + 0.8 * 37.5]

    def test_no_cal_when_max_sharpe_failed(self):
        fig = plot_efficient_frontier(
            _frontier(),
            max_sharpe={
                "return": 0.10,
                "volatility": 0.15,
                "sharpe": 0.8,
                "success": False,
            },
            risk_free_rate=0.02,
        )
        assert not any(t.name.startswith("Capital Allocation Line") for t in fig.data)

    def test_no_cal_without_risk_free_rate(self):
        fig = plot_efficient_frontier(
            _frontier(),
            max_sharpe={"return": 0.10, "volatility": 0.15, "sharpe": 0.8},
        )
        assert not any(t.name.startswith("Capital Allocation Line") for t in fig.data)


class TestPlotAllocationPie:
    def test_near_zero_weights_filtered(self):
        fig = plot_allocation_pie({"A": 0.6, "B": 0.394, "tiny": 0.005, "dust": 0.001})
        pie = fig.data[0]
        assert list(pie.labels) == ["A", "B"]
        assert len(pie.labels) == len(pie.values)
        assert pie.hole == 0.45

    def test_boundary_weight_kept(self):
        # The filter keeps strictly abs(w) > 0.005
        fig = plot_allocation_pie({"A": 0.9, "B": 0.006})
        assert list(fig.data[0].labels) == ["A", "B"]


class TestPlotMonteCarloPaths:
    def _paths(self, n_sims=50, n_periods=10) -> np.ndarray:
        return (
            np.random.default_rng(0).normal(100, 5, (n_sims, n_periods)).cumsum(axis=1)
        )

    def test_trace_count_with_percentiles(self):
        fig = plot_monte_carlo_paths(self._paths(), n_display=20)
        # 20 sampled paths + p95/p5 band + median
        assert len(fig.data) == 23

    def test_display_capped_at_n_sims(self):
        fig = plot_monte_carlo_paths(self._paths(n_sims=30), n_display=200)
        assert len(fig.data) == 33

    def test_no_percentiles(self):
        fig = plot_monte_carlo_paths(self._paths(), n_display=15, percentiles=False)
        assert len(fig.data) == 15

    def test_goal_line_added(self):
        fig = plot_monte_carlo_paths(self._paths(), n_display=5, goal_amount=1000000)
        assert len(fig.layout.shapes) > 0


class TestPlotCorrelationHeatmap:
    def test_values_and_range(self):
        corr = pd.DataFrame(
            [[1.0, 0.5], [0.5, 1.0]], index=["A", "B"], columns=["A", "B"]
        )
        fig = plot_correlation_heatmap(corr)
        heatmap = fig.data[0]
        assert isinstance(heatmap, go.Heatmap)
        assert np.allclose(heatmap.z, corr.values)
        assert heatmap.zmid == 0
        assert heatmap.zmin == -1
        assert heatmap.zmax == 1


class TestPlotPriceHistory:
    def test_normalized_first_row_is_100(self):
        prices = pd.DataFrame(
            {"A": [100.0, 101.0, 102.0], "B": [np.nan, 200.0, 202.0]},
            index=pd.date_range("2026-01-01", periods=3),
        )
        fig = plot_price_history(prices, normalize=True)
        for trace in fig.data:
            assert trace.y[0] == 100.0

    def test_unnormalized_keeps_values(self):
        prices = pd.DataFrame(
            {"A": [100.0, 101.0, 102.0]}, index=pd.date_range("2026-01-01", periods=3)
        )
        fig = plot_price_history(prices, normalize=False)
        assert list(fig.data[0].y) == [100.0, 101.0, 102.0]

    def test_nan_filled_no_gaps(self):
        prices = pd.DataFrame(
            {"A": [100.0, np.nan, 102.0]}, index=pd.date_range("2026-01-01", periods=3)
        )
        fig = plot_price_history(prices, normalize=False)
        assert not np.isnan(fig.data[0].y.astype(float)).any()


class TestPlotBacktestEquity:
    def _equity(self, **cols) -> pd.DataFrame:
        idx = pd.date_range("2026-01-01", periods=3)
        return pd.DataFrame(cols, index=idx)

    def test_portfolio_only(self):
        fig = plot_backtest_equity(self._equity(portfolio=[1.0, 1.1, 1.2]), "60/40")
        assert len(fig.data) == 1
        assert fig.data[0].name == "Portfolio"

    def test_with_benchmark(self):
        fig = plot_backtest_equity(
            self._equity(portfolio=[1.0, 1.1, 1.2], benchmark=[1.0, 1.05, 1.1]), "60/40"
        )
        assert [t.name for t in fig.data] == ["Portfolio", "60/40"]

    def test_with_gross_overlay(self):
        fig = plot_backtest_equity(
            self._equity(portfolio=[1.0, 1.1, 1.2], portfolio_gross=[1.0, 1.11, 1.22]),
            "60/40",
        )
        assert [t.name for t in fig.data] == ["Portfolio (net)", "Portfolio (gross)"]

    def test_with_gross_and_benchmark(self):
        fig = plot_backtest_equity(
            self._equity(
                portfolio=[1.0, 1.1, 1.2],
                portfolio_gross=[1.0, 1.11, 1.22],
                benchmark=[1.0, 1.05, 1.1],
            ),
            "60/40",
        )
        assert [t.name for t in fig.data] == [
            "Portfolio (net)",
            "Portfolio (gross)",
            "60/40",
        ]


class TestPlotDrawdown:
    def _dd(self) -> pd.Series:
        return pd.Series(
            [0.0, -0.05, -0.02], index=pd.date_range("2026-01-01", periods=3)
        )

    def test_portfolio_only(self):
        fig = plot_drawdown(self._dd())
        assert len(fig.data) == 1
        assert fig.data[0].name == "Portfolio"

    def test_with_benchmark(self):
        fig = plot_drawdown(self._dd(), self._dd() * 0.5)
        assert [t.name for t in fig.data] == ["Portfolio", "Benchmark"]

    def test_percent_axis(self):
        fig = plot_drawdown(self._dd())
        assert fig.layout.yaxis.tickformat == ".0%"
