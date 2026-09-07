"""Deterministic, offline proofs of walk-forward boundaries and accounting."""

import json
import socket
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from src.portfolio.optimizer import PortfolioOptimizer
from validation.portfolio import Allocation, StrategySpec, WalkForwardConfig, evaluate
from validation.portfolio.metrics import compute_metrics
from validation.portfolio.strategies import AllocationError


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Validation must not access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def daily():
    dates = pd.bdate_range("2019-01-01", "2020-12-31")
    rng = np.random.default_rng(60)
    return pd.DataFrame(
        rng.normal([0.001, 0.0003, 0.0007], [0.01, 0.003, 0.007], (len(dates), 3)),
        index=dates,
        columns=["SPY", "AGG", "GLD"],
    )


@pytest.fixture
def config():
    return WalkForwardConfig(
        start_date="2020-03-31",
        end_date="2020-06-30",
        universe=("SPY", "AGG", "GLD"),
        training_window=3,
        min_observations=30,
    )


@pytest.mark.parametrize(
    "name",
    [
        "equal_weight",
        "60_40",
        "static",
        "inverse_volatility",
        "min_variance",
        "mvo",
        "erc",
        "mean_cvar",
        "resampled_mvo",
    ],
)
def test_builtin_strategies_run_offline(daily, config, name):
    params = (
        {"weights": {"SPY": 0.3, "AGG": 0.5, "GLD": 0.2}} if name == "static" else {}
    )
    if name == "resampled_mvo":
        params = {"n_simulations": 8}
    run = evaluate(daily, replace(config, strategy=StrategySpec(name, params)))
    assert run.metrics["complete"]
    assert run.metrics["allocation_success_count"] == 3
    assert run.metrics["allocation_failure_count"] == 0
    for record in run.rebalances:
        assert sum(record["weights"].values()) == pytest.approx(1)
        assert min(record["weights"].values()) >= 0


@pytest.mark.parametrize(
    "name",
    [
        "equal_weight",
        "inverse_volatility",
        "min_variance",
        "mvo",
        "erc",
        "resampled_mvo",
    ],
)
def test_future_sentinel_and_availability_cannot_change_earlier_weights(
    daily, config, name
):
    params = {"n_simulations": 8} if name == "resampled_mvo" else {}
    config = replace(config, strategy=StrategySpec(name, params))
    original = evaluate(daily, config)
    sentinel = daily.copy()
    sentinel.loc[sentinel.index > "2020-03-31", "SPY"] = 10000
    sentinel.loc[sentinel.index > "2020-03-31", "GLD"] = np.nan
    altered = evaluate(sentinel, config)
    first = original.rebalances[0]
    other = altered.rebalances[0]
    assert other["weights"] == first["weights"]
    assert other["eligible_assets"] == first["eligible_assets"]
    assert other["diagnostics"] == first["diagnostics"]
    # Allocation remains unchanged even when the future holding data is absent.
    assert other["status"] == "failed"
    assert other["reason"] == "missing_or_invalid_holding_returns"


def test_exact_rolling_windows_and_custom_allocator_isolation(daily, config):
    seen = []

    class Spy:
        def allocate(self, history, as_of, settings):
            lower = as_of - pd.offsets.MonthEnd(settings.training_window)
            expected = daily.loc[(daily.index > lower) & (daily.index <= as_of)]
            pd.testing.assert_frame_equal(history, expected)
            seen.append((as_of, history.index.copy()))
            # The allocator cannot mutate the evaluator's input/config.
            history.iloc[:, :] = 999
            settings.universe = ("mutated",)
            return Allocation({"AGG": 1})

    original = daily.copy()
    run = evaluate(daily, replace(config, strategy=StrategySpec("custom")), Spy())
    pd.testing.assert_frame_equal(daily, original)
    assert len(seen) == 3
    for record, (as_of, dates) in zip(run.rebalances, seen, strict=True):
        assert record["training_end"] <= as_of < record["holding_start"]
        assert record["training_observations"] == len(dates)
    assert run.returns.index.is_unique
    pd.testing.assert_series_equal(
        run.returns,
        daily.loc["2020-04-01":"2020-06-30", "AGG"],
        check_names=False,
        atol=1e-14,
    )


def test_expanding_windows_and_quarterly_holding(daily, config):
    run = evaluate(
        daily,
        replace(
            config,
            window_type="expanding",
            end_date="2020-12-31",
            holding_window=3,
            rebalance_frequency=3,
        ),
    )
    assert [r["as_of"] for r in run.rebalances] == list(
        pd.to_datetime(["2020-03-31", "2020-06-30", "2020-09-30"])
    )
    assert len({r["training_start"] for r in run.rebalances}) == 1
    counts = [r["training_observations"] for r in run.rebalances]
    assert counts[0] < counts[1] < counts[2]
    assert run.metrics["complete"]


def test_equal_weight_exact_and_inverse_volatility(config):
    history = pd.DataFrame(
        {"SPY": [-0.01, 0.01, -0.01, 0.01], "AGG": [-0.02, 0.02, -0.02, 0.02]},
        index=pd.bdate_range("2020-01-01", periods=4),
    )
    as_of = history.index[-1]
    assert StrategySpec().allocate(history, as_of, config).weights == {
        "SPY": 0.5,
        "AGG": 0.5,
    }
    inverse = StrategySpec("inverse_volatility").allocate(history, as_of, config)
    assert inverse.weights == pytest.approx({"SPY": 2 / 3, "AGG": 1 / 3})
    for invalid in (0, np.nan, np.inf):
        history["AGG"] = invalid
        with pytest.raises(AllocationError, match="invalid_or_zero_volatility"):
            StrategySpec("inverse_volatility").allocate(history, as_of, config)


def test_eligibility_uses_only_current_history(daily, config):
    daily.loc[daily.index < "2020-03-01", "GLD"] = np.nan
    run = evaluate(daily, replace(config, min_coverage=0.5))
    assert run.rebalances[0]["weights"] == {"SPY": 0.5, "AGG": 0.5}
    assert run.rebalances[0]["excluded_assets"] == {"GLD": "insufficient_history"}
    assert run.rebalances[1]["weights"] == dict.fromkeys(config.universe, 1 / 3)


def test_sparse_and_mixed_calendar_training(daily, config):
    daily.loc["2020-01-01":"2020-03-20", "GLD"] = np.nan
    # One missing training return gets removed from the common estimator sample.
    daily.loc["2020-03-25", "AGG"] = np.nan
    run = evaluate(daily, replace(config, min_observations=2))
    first = run.rebalances[0]
    assert first["excluded_assets"] == {"GLD": "sparse_history"}
    assert (
        first["training_observations"] == len(daily.loc["2020-01-01":"2020-03-31"]) - 1
    )


def test_insufficient_joint_history_skips_without_optimizer(daily, config, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Optimizer called with insufficient history")

    monkeypatch.setattr(PortfolioOptimizer, "__init__", forbidden)
    run = evaluate(
        daily, replace(config, min_observations=1000, strategy=StrategySpec("mvo"))
    )
    assert run.metrics["skipped_period_count"] == 3
    assert run.metrics["allocation_success_count"] == 0
    assert all(r["reason"] == "insufficient_joint_history" for r in run.rebalances)
    assert run.returns.isna().all()
    assert run.metrics["total_return"] is None


@pytest.mark.parametrize("exception", [False, True])
def test_optimization_failure_does_not_corrupt_next_period(
    daily, config, monkeypatch, exception
):
    original = PortfolioOptimizer.minimize_volatility
    attempts = 0

    def fail_once(self, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            if exception:
                raise RuntimeError("private-provider-message")
            return {"success": False, "weights": {"SPY": 1}}
        return original(self, **kwargs)

    monkeypatch.setattr(PortfolioOptimizer, "minimize_volatility", fail_once)
    run = evaluate(daily, replace(config, strategy=StrategySpec("min_variance")))
    assert run.metrics["allocation_failure_count"] == 1
    assert run.metrics["allocation_success_count"] == 2
    assert run.rebalances[1]["status"] == "ok"
    assert run.returns.loc["2020-05"].notna().all()
    assert run.nav.isna().all()
    assert run.metrics["sharpe"] is None
    assert "private-provider-message" not in run.to_json()


def test_hand_calculated_buy_and_hold_nav_and_rebalance():
    # First period: half in A, half in B. A gains 10% twice, so wealth =
    # 0.5 * 1.1**2 + 0.5 = 1.105 (not 1.05**2). Reset targets in March.
    dates = pd.to_datetime(
        [
            "2020-01-02",
            "2020-01-31",
            "2020-02-03",
            "2020-02-28",
            "2020-03-02",
            "2020-03-31",
        ]
    )
    data = pd.DataFrame(
        {"A": [0.01, -0.01, 0.1, 0.1, -0.2, 0], "B": [-0.01, 0.01, 0, 0, 0, 0.1]},
        index=dates,
    )
    config = WalkForwardConfig(
        start_date="2020-01-31",
        end_date="2020-03-31",
        universe=("A", "B"),
        training_window=1,
        min_observations=2,
    )
    run = evaluate(data, config)
    np.testing.assert_allclose(run.nav, [1.05, 1.105, 1.105 * 0.9, 1.105 * 0.95])
    assert run.rebalances[0]["realized_return"] == pytest.approx(0.105)
    assert run.rebalances[1]["realized_return"] == pytest.approx(-0.05)
    assert run.metrics["total_return"] == pytest.approx(1.105 * 0.95 - 1)
    assert run.metrics["max_drawdown"] == pytest.approx(-0.1)


def test_missing_holding_data_never_imputed_or_renormalized(daily, config):
    daily.loc["2020-04-15", "SPY"] = np.nan
    run = evaluate(daily, config)
    assert run.rebalances[0]["weights"] == dict.fromkeys(config.universe, 1 / 3)
    assert run.rebalances[0]["reason"] == "missing_or_invalid_holding_returns"
    assert run.returns.loc["2020-04"].isna().all()
    assert run.nav.isna().all()
    # Missing data for a zero-weight asset doesn't invalidate a static policy.
    static = replace(
        config, strategy=StrategySpec("static", {"weights": {"AGG": 1, "SPY": 0}})
    )
    assert evaluate(daily, static).metrics["complete"]


def test_empty_holding_month_and_partial_final_window(daily, config):
    no_april = daily.loc[daily.index.to_period("M") != pd.Period("2020-04")]
    run = evaluate(no_april, config)
    assert run.rebalances[0]["reason"] == "no_holding_observations"
    assert not run.metrics["complete"]
    assert run.nav.isna().all()
    partial = evaluate(daily, replace(config, end_date="2020-06-15"))
    assert partial.returns.index[-1] == pd.Timestamp("2020-06-15")
    assert partial.rebalances[-1]["holding_end"] == pd.Timestamp("2020-06-15")


def test_unavailable_benchmark_is_explicit(daily, config):
    run = evaluate(
        daily.drop(columns="AGG"), replace(config, strategy=StrategySpec("60_40"))
    )
    assert all(r["reason"] == "benchmark_assets_unavailable" for r in run.rebalances)
    assert run.metrics["allocation_failure_count"] == 3


def test_truncated_snapshot_is_not_a_complete_holding_window(daily, config):
    run = evaluate(daily.loc[:"2020-06-15"], config)
    assert run.rebalances[-1]["reason"] == "incomplete_holding_window"
    assert run.returns.loc["2020-06"].isna().all()
    assert not run.metrics["complete"]
    assert run.metrics["total_return"] is None


def test_nonfinite_compounded_wealth_is_an_explicit_failure(daily, config):
    daily.loc["2020-04", :] = 1e200
    run = evaluate(daily, config)
    assert run.rebalances[0]["reason"] == "nonfinite_holding_wealth"
    assert run.rebalances[0]["allocation_status"] == "ok"
    assert run.returns.loc["2020-04"].isna().all()
    assert run.metrics["total_return"] is None


@pytest.mark.parametrize(
    "name,method",
    [
        ("min_variance", "minimize_volatility"),
        ("mvo", "maximize_sharpe"),
        ("erc", "risk_parity"),
    ],
)
def test_adapter_matches_production_optimizer(daily, config, name, method):
    config = replace(config, strategy=StrategySpec(name))
    run = evaluate(daily, config)
    history = daily.loc["2020-01-01":"2020-03-31"]
    production = PortfolioOptimizer(
        history,
        risk_free_rate=config.risk_free_rate,
        covariance_method=config.covariance_method,
        seed=config.random_seed,
    )
    expected = getattr(production, method)()
    assert run.rebalances[0]["weights"] == expected["weights"]


@pytest.mark.parametrize(
    "name", ["equal_weight", "inverse_volatility", "min_variance", "mvo", "erc"]
)
def test_single_asset(daily, config, name):
    run = evaluate(
        daily, replace(config, universe=("AGG",), strategy=StrategySpec(name))
    )
    assert run.metrics["complete"]
    assert all(r["weights"] == pytest.approx({"AGG": 1}) for r in run.rebalances)


def test_singular_covariance_and_serialization(daily, config):
    daily["GLD"] = daily["SPY"]
    run = evaluate(
        daily,
        replace(
            config, covariance_method="sample", strategy=StrategySpec("min_variance")
        ),
    )
    assert run.metrics["complete"]
    assert all(r["diagnostics"]["covariance_regularized"] for r in run.rebalances)
    document = json.loads(run.to_json())
    assert document["metadata"]["config"]["random_seed"] == 0
    assert document["metadata"]["config"]["constraints"] == {"long_only": True}
    assert len(document["metadata"]["data_sha256"]) == 64
    assert document["series"][0]["date"].startswith("2020-04-01")


def test_seeded_resampling_is_reproducible(daily, config):
    config = replace(
        config,
        strategy=StrategySpec("resampled_mvo", {"n_simulations": 12}),
        random_seed=123,
    )
    first, second = evaluate(daily, config), evaluate(daily, config)
    assert first.rebalances == second.rebalances
    pd.testing.assert_series_equal(first.returns, second.returns)
    assert first.metadata["data_sha256"] == second.metadata["data_sha256"]


@pytest.mark.parametrize(
    "weights",
    [{"SPY": 0.5}, {"SPY": 1.1, "AGG": -0.1}, {"SPY": np.nan}, {"SPY": np.inf}],
)
def test_invalid_weights_are_failures(daily, config, weights):
    run = evaluate(
        daily, replace(config, strategy=StrategySpec("static", {"weights": weights}))
    )
    assert all(r["reason"] == "invalid_weights" for r in run.rebalances)
    json.loads(run.to_json())  # NaN and Infinity must serialize as null.


@pytest.mark.parametrize(
    "change",
    [
        {"holding_window": 2},
        {"training_window": 0},
        {"start_date": "2020-03-30"},
        {"min_observations": 1},
        {"expected_return_method": "cme"},
        {"constraints": {"long_only": False}},
        {"random_seed": -1},
        {"risk_free_rate": float("nan")},
    ],
)
def test_unsupported_config_rejected(config, change):
    with pytest.raises(ValueError):
        replace(config, **change)


def test_invalid_input_dates_rejected(daily, config):
    for data in (
        daily.iloc[::-1],
        pd.concat([daily, daily.iloc[-1:]]),
        daily.tz_localize("UTC"),
    ):
        with pytest.raises(ValueError):
            evaluate(data, config)


def test_metrics_include_initial_loss_and_undefined_ratios():
    result = compute_metrics(pd.Series([-0.1, 0.0]), 0)
    assert result["max_drawdown"] == pytest.approx(-0.1)
    assert result["total_return"] == pytest.approx(-0.1)
    assert result["annualized_volatility"] == pytest.approx(
        np.std([-0.1, 0], ddof=1) * np.sqrt(252)
    )
    assert result["cagr"] == pytest.approx(0.9**126 - 1)
    flat = compute_metrics(pd.Series([0.0, 0.0]), 0)
    assert flat["sharpe"] is None
    assert flat["sortino"] is None


def test_total_loss_keeps_nav_at_zero(daily, config):
    daily.loc["2020-04-01", :] = -1
    run = evaluate(daily, config)
    assert run.returns.iloc[0] == -1
    assert (run.returns.loc["2020-04"].iloc[1:] == 0).all()
    assert (run.nav == 0).all()
    assert run.metrics["total_return"] == -1
