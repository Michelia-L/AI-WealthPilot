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
        assert record["training_window_observations"] == len(dates)
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
    counts = [r["training_window_observations"] for r in run.rebalances]
    assert counts[0] < counts[1] < counts[2]
    assert run.metrics["complete"]


def test_custom_diagnostics_are_snapshots(daily, config):
    class Stateful:
        def __init__(self):
            self.diagnostics = {"decisions": []}

        def allocate(self, history, as_of, config):
            self.diagnostics["decisions"].append(as_of)
            return Allocation({"AGG": 1}, self.diagnostics)

    run = evaluate(daily, replace(config, strategy=StrategySpec("custom")), Stateful())
    assert [len(r["diagnostics"]["decisions"]) for r in run.rebalances] == [1, 2, 3]


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
    run = evaluate(
        daily,
        replace(config, min_observations=2, strategy=StrategySpec("min_variance")),
    )
    first = run.rebalances[0]
    assert first["excluded_assets"] == {"GLD": "sparse_history"}
    assert first["training_window_observations"] == len(
        daily.loc["2020-01-01":"2020-03-31"]
    )
    assert first["estimation_observations"] == first["training_window_observations"] - 1


def test_no_eligible_assets_skips_without_optimizer(daily, config, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Optimizer called with insufficient history")

    monkeypatch.setattr(PortfolioOptimizer, "__init__", forbidden)
    run = evaluate(
        daily, replace(config, min_observations=1000, strategy=StrategySpec("mvo"))
    )
    assert run.metrics["skipped_period_count"] == 3
    assert run.metrics["allocation_success_count"] == 0
    assert all(r["reason"] == "no_eligible_assets" for r in run.rebalances)
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
    daily.loc["2020-03-25", "AGG"] = np.nan
    config = replace(config, strategy=StrategySpec(name))
    run = evaluate(daily, config)
    history = daily.loc["2020-01-01":"2020-03-31"].dropna()
    production = PortfolioOptimizer(
        history,
        risk_free_rate=config.risk_free_rate,
        covariance_method=config.covariance_method,
        seed=config.random_seed,
    )
    expected = getattr(production, method)()
    assert run.rebalances[0]["weights"] == expected["weights"]
    assert run.rebalances[0]["estimation_observations"] == len(history)


@pytest.fixture
def staggered_history():
    training_dates = pd.bdate_range("2020-01-01", periods=260)
    dates = training_dates.append(pd.DatetimeIndex(["2021-01-04"]))
    rng = np.random.default_rng(60)
    data = pd.DataFrame(
        rng.normal(0.001, 0.01, (len(dates), 3)),
        index=dates,
        columns=["SPY", "AGG", "GLD"],
    )
    data.iloc[:10, 0] = np.nan
    data.iloc[10:20, 1] = np.nan
    data.iloc[20:40, 2] = np.nan
    config = WalkForwardConfig(
        start_date="2020-12-31",
        end_date="2021-01-04",
        universe=("SPY", "AGG", "GLD"),
        training_window=12,
        min_observations=240,
        min_coverage=0.9,
    )
    return data, config


@pytest.mark.parametrize("name", ["equal_weight", "static", "60_40"])
def test_baselines_do_not_require_joint_estimation_sample(staggered_history, name):
    data, config = staggered_history
    params = {"weights": {"SPY": 0.6, "AGG": 0.4}} if name == "static" else {}
    config = replace(config, strategy=StrategySpec(name, params))
    run = evaluate(data, config)
    first = run.rebalances[0]
    assert first["eligible_assets"] == list(config.universe)
    assert first["status"] == "ok"
    assert first["training_window_observations"] == 260
    assert first["estimation_observations"] == 0
    assert run.metrics["complete"]
    if name == "equal_weight":
        assert first["weights"] == dict.fromkeys(config.universe, 1 / 3)
    else:
        assert first["weights"] == {"SPY": 0.6, "AGG": 0.4}
        without_gld = evaluate(data, replace(config, universe=("SPY", "AGG")))
        assert without_gld.rebalances[0]["weights"] == first["weights"]
        pd.testing.assert_series_equal(without_gld.returns, run.returns)


def test_inverse_volatility_uses_each_assets_valid_history(staggered_history):
    data, config = staggered_history
    history = data.loc[: config.start_date]
    counts = history.count().to_dict()
    assert counts == {"SPY": 250, "AGG": 250, "GLD": 240}
    assert len(history.dropna()) == 220
    expected = 1 / history.std(ddof=1)
    expected /= expected.sum()
    run = evaluate(data, replace(config, strategy=StrategySpec("inverse_volatility")))
    first = run.rebalances[0]
    assert first["weights"] == pytest.approx(expected.to_dict())
    assert first["estimation_observations"] == counts
    assert (
        json.loads(run.to_json())["rebalances"][0]["estimation_observations"] == counts
    )
    assert run.metrics["complete"]


@pytest.mark.parametrize(
    "name", ["min_variance", "mvo", "erc", "mean_cvar", "resampled_mvo"]
)
def test_optimizers_still_require_joint_sample(staggered_history, name, monkeypatch):
    data, config = staggered_history

    def forbidden(*args, **kwargs):
        pytest.fail("Optimizer must not be constructed with insufficient joint history")

    monkeypatch.setattr(PortfolioOptimizer, "__init__", forbidden)
    run = evaluate(data, replace(config, strategy=StrategySpec(name)))
    first = run.rebalances[0]
    assert first["eligible_assets"] == list(config.universe)
    assert first["reason"] == "insufficient_joint_history"
    assert first["status"] == "skipped"
    assert first["allocation_status"] == "not_attempted"
    assert first["training_window_observations"] == 260
    assert first["estimation_observations"] == 220
    assert run.metrics["allocation_failure_count"] == 0
    assert run.metrics["skipped_period_count"] == 1
    assert run.returns.isna().all()


def test_custom_history_keeps_missing_values_and_as_of_boundary(staggered_history):
    data, config = staggered_history
    data.iloc[0, 0] = np.inf
    data.iloc[10, 1] = -2
    expected = data.loc[: config.start_date].where(
        lambda frame: np.isfinite(frame) & (frame >= -1)
    )

    class Spy:
        def allocate(self, history, as_of, config):
            pd.testing.assert_frame_equal(history, expected)
            assert history.index.max() <= as_of
            assert len(history) == 260
            assert history.isna().any().all()
            history.iloc[:, :] = 123
            return Allocation({"AGG": 1})

    original = data.copy()
    config = replace(config, strategy=StrategySpec("custom"))
    first = evaluate(data, config, Spy())
    pd.testing.assert_frame_equal(data, original)
    data.loc[data.index > config.start_date] = np.nan
    altered = evaluate(data, config, Spy())
    assert first.rebalances[0]["weights"] == altered.rebalances[0]["weights"]
    assert first.rebalances[0]["estimation_observations"] is None


@pytest.mark.parametrize(
    "message",
    [
        "private-error-marker",
        "invalid_weights: private-error-marker",
        "",
        "invalid_weights",
    ],
)
def test_allocation_errors_only_serialize_safe_reason_codes(daily, config, message):
    class Custom:
        def allocate(self, history, as_of, config):
            raise AllocationError(message)

    run = evaluate(daily, replace(config, strategy=StrategySpec("custom")), Custom())
    expected = "invalid_weights" if message == "invalid_weights" else "allocation_error"
    assert all(r["reason"] == expected for r in run.rebalances)
    assert run.metrics["allocation_failure_count"] == 3
    assert "private-error-marker" not in run.to_json()


def test_allocation_error_str_override_is_not_serialized(daily, config):
    class CustomError(AllocationError):
        def __str__(self):
            return "private-error-marker"

    class Custom:
        def allocate(self, history, as_of, config):
            raise CustomError("invalid_weights")

    run = evaluate(daily, replace(config, strategy=StrategySpec("custom")), Custom())
    assert all(r["reason"] == "invalid_weights" for r in run.rebalances)
    assert "private-error-marker" not in run.to_json()


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
