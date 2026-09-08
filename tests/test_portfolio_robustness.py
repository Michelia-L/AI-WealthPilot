"""Offline fixtures for turnover, cost accounting and controlled experiments."""

import json
import socket
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from src.portfolio.optimizer import PortfolioOptimizer
from validation.portfolio import (
    Allocation,
    CostConfig,
    SensitivityConfig,
    StrategySpec,
    WalkForwardConfig,
    analyze_costs,
    analyze_weights,
    compare_allocations,
    compare_runs,
    compute_turnover,
    evaluate,
    run_sensitivity,
    weight_distance,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Research tests must stay offline")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def hand_run():
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
    return evaluate(data, config)


@pytest.fixture
def research_case():
    dates = pd.bdate_range("2015-01-01", "2021-06-30")
    rng = np.random.default_rng(61)
    data = pd.DataFrame(
        rng.normal([0.0003, 0.0001, 0.0002], [0.01, 0.003, 0.008], (len(dates), 3)),
        index=dates,
        columns=["SPY", "AGG", "GLD"],
    )
    config = WalkForwardConfig(
        start_date="2021-03-31",
        end_date="2021-06-30",
        universe=("SPY", "AGG", "GLD"),
        training_window=36,
        min_observations=100,
        strategy=StrategySpec("mvo"),
        random_seed=61,
    )
    return data, config


def test_drift_aware_turnover_matches_hand_calculation(hand_run):
    weights = hand_run.rebalances[0]["ending_weights"]
    assert weights == pytest.approx({"A": 0.605 / 1.105, "B": 0.5 / 1.105})
    report = compute_turnover(hand_run)
    turnover = 0.605 / 1.105 - 0.5
    assert report["per_rebalance"][0]["turnover"] == 0
    assert report["per_rebalance"][1]["turnover"] == pytest.approx(turnover)
    assert report["per_rebalance"][1]["pretrade_weights"] == weights
    summary = report["summary"]
    assert summary["annualized"] == pytest.approx(turnover * 252 / 4)
    assert summary["mean"] == summary["median"] == summary["p95"] == summary["max"]
    assert summary["observations"] == 1


def test_zero_cost_and_zero_target_turnover(hand_run, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Cost scenarios must not refit an optimizer")

    monkeypatch.setattr(PortfolioOptimizer, "__init__", forbidden)
    report = analyze_costs(hand_run)
    pd.testing.assert_series_equal(
        report.scenarios[0].returns, hand_run.returns, check_names=False
    )
    pd.testing.assert_series_equal(
        report.scenarios[0].nav, hand_run.nav, check_names=False
    )
    target = analyze_costs(hand_run, CostConfig(turnover_method="target"))
    for scenario in target.scenarios:
        assert (scenario.daily_costs == 0).all()
        assert scenario.metrics["cumulative_cost_drag"] == 0


def test_cost_debit_and_monotonic_net_performance(hand_run):
    report = analyze_costs(hand_run)
    turnover = 0.605 / 1.105 - 0.5
    previous = None
    for scenario in report.scenarios:
        cost = turnover * scenario.rate_bps / 10000
        expected_costs = pd.Series(
            [0, 0, cost, 0], index=hand_run.returns.index, dtype=float
        )
        pd.testing.assert_series_equal(
            scenario.daily_costs, expected_costs, check_names=False
        )
        np.testing.assert_allclose(scenario.returns, hand_run.returns - expected_costs)
        assert scenario.nav.iloc[-1] == pytest.approx(
            1.105 * (0.9 - cost) * (0.95 / 0.9)
        )
        assert scenario.metrics["cumulative_cost_paid"] == pytest.approx(1.105 * cost)
        assert scenario.metrics["cumulative_cost_drag"] == pytest.approx(
            hand_run.nav.iloc[-1] - scenario.nav.iloc[-1]
        )
        if previous is not None:
            assert (scenario.returns <= previous.returns).all()
            assert (scenario.nav <= previous.nav).all()
            assert scenario.metrics["net_cagr"] <= previous.metrics["net_cagr"]
        previous = scenario
    assert (
        json.loads(report.to_json())["metadata"]["config"]["turnover_method"] == "drift"
    )


def test_initial_allocation_convention(hand_run):
    report = analyze_costs(hand_run, CostConfig(rates_bps=(10,), charge_initial=True))
    assert report.turnover["per_rebalance"][0]["turnover"] == 1
    assert report.scenarios[0].daily_costs.iloc[0] == 0.001
    assert report.scenarios[0].returns.iloc[0] == pytest.approx(
        hand_run.returns.iloc[0] - 0.001
    )


def test_old_runs_require_explicit_target_mode_for_positive_costs(hand_run):
    for record in hand_run.rebalances:
        record.pop("ending_weights")
    report = analyze_costs(hand_run, CostConfig(rates_bps=(0, 10)))
    assert report.scenarios[0].metrics["complete"]
    assert not report.scenarios[1].metrics["complete"]
    assert report.scenarios[1].rebalances[1]["reason"] == "turnover_unavailable"
    assert report.scenarios[1].metrics["net_cagr"] is None
    assert (
        analyze_costs(hand_run, CostConfig(turnover_method="target"))
        .scenarios[-1]
        .metrics["complete"]
    )


def test_failed_period_does_not_bridge_turnover_or_nav(research_case):
    data, config = research_case
    data.loc["2021-04-05", :] = np.nan
    run = evaluate(data, replace(config, strategy=StrategySpec("equal_weight")))
    report = analyze_costs(run, CostConfig(rates_bps=(0, 10)))
    assert report.turnover["per_rebalance"][1]["turnover"] is None
    assert report.turnover["per_rebalance"][2]["turnover"] is not None
    assert report.turnover["summary"]["annualized"] is None
    for scenario in report.scenarios:
        assert scenario.nav.isna().all()
        assert scenario.returns.loc["2021-06"].notna().all()
        assert scenario.metrics["net_sharpe"] is None
        assert scenario.metrics["cumulative_cost_drag"] is None


def test_invalid_net_loss_is_explicit(hand_run):
    hand_run.returns.iloc[0] = -0.999
    report = analyze_costs(hand_run, CostConfig(rates_bps=(100,), charge_initial=True))
    assert report.scenarios[0].rebalances[0]["reason"] == "cost_exceeds_capital"
    assert report.scenarios[0].nav.isna().all()
    assert report.scenarios[0].metrics["net_cagr"] is None


def test_weight_concentration_and_bound_frequency(hand_run):
    hand_run.rebalances[1]["weights"] = {"A": 1}
    result = analyze_weights(hand_run)
    assert result["max_weight"]["max"] == 1
    assert result["effective_holdings"]["mean"] == 1.5
    assert result["per_rebalance"][1]["target_distance"] == 0.5
    assert result["weight_volatility"]["A"] == pytest.approx(np.std([0.5, 1], ddof=1))
    assert result["per_rebalance"][1]["lower_bound_fraction"] == 0.5
    assert result["per_rebalance"][1]["upper_bound_fraction"] == 0.5
    hand_run.rebalances[0]["allocation_status"] = "failed"
    assert analyze_weights(hand_run)["per_rebalance"][1]["target_distance"] is None


def test_weight_distance_is_symmetric_and_bounded():
    rng = np.random.default_rng(61)
    for _ in range(50):
        a = dict(zip(["A", "B", "C"], rng.dirichlet([1, 1, 1]), strict=True))
        b = dict(zip(["B", "C", "D"], rng.dirichlet([1, 1, 1]), strict=True))
        assert weight_distance(a, a) == 0
        assert 0 <= weight_distance(a, b) <= 1
        assert weight_distance(a, b) == pytest.approx(weight_distance(b, a))
    assert weight_distance({"A": 1}, {"B": 1}) == 1
    assert weight_distance({"A": 0.5, "B": 0.500000005}, {"C": 1}) == 1
    for invalid in ({}, {"A": -1, "B": 2}, {"A": np.nan}, {"A": 0.5}):
        with pytest.raises(ValueError):
            weight_distance(invalid, {"A": 1})


def test_mu_perturbation_changes_only_expected_return_input(research_case, monkeypatch):
    data, config = research_case
    input_snapshot = data.copy()
    captured = []
    original = PortfolioOptimizer.__init__

    def spy(self, history, **kwargs):
        captured.append((history.copy(), deepcopy(kwargs)))
        original(self, history, **kwargs)

    monkeypatch.setattr(PortfolioOptimizer, "__init__", spy)
    base = evaluate(data, config)
    variant = evaluate(
        data,
        replace(
            config,
            strategy=replace(config.strategy, expected_return_shifts={"SPY": 0.01}),
        ),
    )
    for (left, lk), (right, rk) in zip(captured[:3], captured[3:], strict=True):
        pd.testing.assert_frame_equal(left, right)
        expected = left.mean() * 252
        expected["SPY"] += 0.01
        pd.testing.assert_series_equal(rk.pop("expected_returns"), expected)
        assert lk.pop("expected_returns") is None
        assert lk == rk
    assert compare_allocations(base, variant)["weight_distance"]["max"] > 0
    pd.testing.assert_frame_equal(data, input_snapshot)


def test_covariance_and_window_experiments_share_oos_protocol(research_case):
    data, config = research_case
    report = run_sensitivity(
        data, config, SensitivityConfig(return_shocks=()), CostConfig(rates_bps=(0, 25))
    )
    assert {
        "base",
        "covariance_sample",
        "covariance_oas",
        "window_24m",
        "window_60m",
        "window_expanding",
    } == report.comparison.implementations.keys()
    base = report.comparison.implementations["base"].gross
    for name, implementation in report.comparison.implementations.items():
        run = implementation.gross
        assert run.returns.index.equals(base.returns.index)
        assert [r["as_of"] for r in run.rebalances] == [
            r["as_of"] for r in base.rebalances
        ]
        assert run.metadata["config"]["universe"] == base.metadata["config"]["universe"]
        if name.startswith("covariance"):
            assert [r["eligible_assets"] for r in run.rebalances] == [
                r["eligible_assets"] for r in base.rebalances
            ]
            assert report.changes[name]["eligible_universe_changed_count"] == 0
    assert base.metadata["config"]["training_window"] == 36
    assert (
        report.comparison.implementations["window_24m"].gross.metadata["config"][
            "training_window"
        ]
        == 24
    )
    assert (
        report.comparison.implementations["window_60m"].gross.metadata["config"][
            "training_window"
        ]
        == 60
    )
    assert (
        report.comparison.implementations["window_expanding"].gross.metadata["config"][
            "window_type"
        ]
        == "expanding"
    )
    assert json.loads(report.to_json())["metadata"]["config"]["training_windows"] == [
        24,
        36,
        60,
    ]


def test_seeded_random_perturbations_are_reproducible(research_case):
    data, config = research_case
    experiments = SensitivityConfig(
        return_shocks=(),
        random_draws=2,
        random_seed=61,
        covariance_methods=(),
        training_windows=(),
        include_expanding=False,
    )
    first = run_sensitivity(data, config, experiments, CostConfig(rates_bps=(0,)))
    second = run_sensitivity(data, config, experiments, CostConfig(rates_bps=(0,)))
    assert first.metadata == second.metadata
    assert first.changes == second.changes
    assert first.comparison.rows == second.comparison.rows
    for name in first.comparison.implementations:
        pd.testing.assert_series_equal(
            first.comparison.implementations[name].gross.returns,
            second.comparison.implementations[name].gross.returns,
        )


def test_mu_shocks_use_only_training_data(research_case):
    data, config = research_case
    experiments = SensitivityConfig(
        return_shocks=(-0.01, 0.01),
        shock_assets=("SPY",),
        covariance_methods=(),
        training_windows=(),
        include_expanding=False,
    )
    base = run_sensitivity(data, config, experiments, CostConfig(rates_bps=(0,)))
    data = data.copy()
    data.loc[data.index > config.start_date] = 0.5
    changed = run_sensitivity(data, config, experiments, CostConfig(rates_bps=(0,)))
    for name in base.comparison.implementations:
        left = base.comparison.implementations[name].gross.rebalances[0]
        right = changed.comparison.implementations[name].gross.rebalances[0]
        assert left["weights"] == right["weights"]
        assert left["diagnostics"] == right["diagnostics"]


@pytest.mark.parametrize(
    "name", ["equal_weight", "inverse_volatility", "erc", "min_variance", "mean_cvar"]
)
def test_inapplicable_mu_experiments_are_explicit(research_case, name):
    data, config = research_case
    config = replace(config, strategy=StrategySpec(name))
    report = run_sensitivity(
        data,
        config,
        SensitivityConfig(training_windows=(), include_expanding=False),
        CostConfig(rates_bps=(0,)),
    )
    assert {
        "kind": "expected_return",
        "reason": "strategy_not_return_dependent",
    } in report.metadata["skipped_experiments"]
    assert not any(name.startswith("mu") for name in report.comparison.implementations)


def test_weight_changes_report_concentration_and_failures(hand_run):
    variant = deepcopy(hand_run)
    variant.rebalances[0]["weights"] = {"A": 1}
    variant.rebalances[1]["allocation_status"] = "failed"
    variant.rebalances[1]["reason"] = "optimizer_unsuccessful"
    variant.metrics["allocation_failure_count"] = 1
    report = compare_allocations(hand_run, variant)
    assert report["weight_distance"]["mean"] == 0.5
    assert report["weight_distance"]["missing"] == 1
    assert not report["complete_pairs"]
    assert report["concentration_transition_count"] == 1
    assert report["variant_allocation_failure_count"] == 1
    assert report["asset_changes"][0]["max"] == 0.5


def test_rankings_are_per_cost_scenario_and_no_scores(research_case):
    data, config = research_case
    runs = {
        name: evaluate(data, replace(config, strategy=StrategySpec(name)))
        for name in ("equal_weight", "min_variance", "erc")
    }
    report = compare_runs(runs, CostConfig(rates_bps=(0, 25)))
    assert len(report.rows) == 6
    for rate in (0, 25):
        rows = [r for r in report.rows if r["cost_bps"] == rate]
        ordered = sorted(rows, key=lambda r: r["net_sharpe"], reverse=True)
        assert [r["net_sharpe_rank"] for r in ordered] == [1, 2, 3]
        assert all(r["rankings_complete"] for r in rows)
        assert all("score" not in r for r in rows)
    assert len(report.to_dataframe()) == 6
    assert json.loads(report.to_json())["rows"][0]["gross_cagr"] is not None


def test_incomplete_comparisons_do_not_rank_survivors(research_case):
    data, config = research_case
    good = evaluate(data, replace(config, strategy=StrategySpec("equal_weight")))
    failed = evaluate(data, replace(config, min_observations=10000))
    report = compare_runs({"good": good, "failed": failed})
    assert all(row["net_sharpe_rank"] is None for row in report.rows)
    assert all(not row["rankings_complete"] for row in report.rows)


def test_mismatched_protocol_rejected(research_case):
    data, config = research_case
    base = evaluate(data, config)
    for other in (
        replace(config, end_date="2021-06-15"),
        replace(config, risk_free_rate=0.02),
    ):
        with pytest.raises(ValueError, match="same input snapshot"):
            compare_runs({"base": base, "other": evaluate(data, other)})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rates_bps": (-1,)},
        {"rates_bps": (np.nan,)},
        {"rates_bps": (0, 0)},
        {"rates_bps": ()},
        {"turnover_method": "automatic"},
    ],
)
def test_cost_config_rejects_invalid_scenarios(kwargs):
    with pytest.raises(ValueError):
        CostConfig(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"random_seed": -1},
        {"return_shocks": (np.inf,)},
        {"covariance_methods": ("unknown",)},
        {"training_windows": (0,)},
        {"concentration_threshold": 2},
    ],
)
def test_sensitivity_config_rejects_invalid_experiments(kwargs):
    with pytest.raises(ValueError):
        SensitivityConfig(**kwargs)


def test_unsupported_expected_return_shift_rejected(research_case):
    _, config = research_case
    with pytest.raises(ValueError, match="return-dependent"):
        StrategySpec("erc", expected_return_shifts={"SPY": 0.01})
    with pytest.raises(ValueError, match="configured universe"):
        replace(
            config,
            strategy=StrategySpec("mvo", expected_return_shifts={"UNKNOWN": 0.01}),
        )


def test_custom_weights_support_cost_analysis(research_case):
    data, config = research_case

    class Static:
        def allocate(self, history, as_of, config):
            return Allocation({"AGG": 1})

    run = evaluate(data, replace(config, strategy=StrategySpec("custom")), Static())
    report = analyze_costs(run)
    assert report.turnover["summary"]["max"] == 0
    assert all(s.metrics["cumulative_cost_drag"] == 0 for s in report.scenarios)


def test_transaction_costs_can_reverse_rankings():
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
        {
            "A": [0.001, -0.001, 0.002, 0.003, 0.001, 0.001],
            "B": [-0.001, 0.001, 0.0007, 0.0015, 0.002, 0.003],
        },
        index=dates,
    )
    config = WalkForwardConfig(
        start_date="2020-01-31",
        end_date="2020-03-31",
        universe=("A", "B"),
        training_window=1,
        min_observations=2,
    )

    class Switch:
        def allocate(self, history, as_of, config):
            return Allocation({"A" if as_of.month == 1 else "B": 1})

    active = evaluate(data, replace(config, strategy=StrategySpec("custom")), Switch())
    static = evaluate(
        data, replace(config, strategy=StrategySpec("static", {"weights": {"B": 1}}))
    )
    report = compare_runs(
        {"active": active, "static": static}, CostConfig(rates_bps=(0, 50))
    )
    rows = {(r["name"], r["cost_bps"]): r for r in report.rows}
    assert rows["active", 0]["gross_sharpe_rank"] == 1
    assert rows["active", 0]["net_sharpe_rank"] == 1
    assert rows["active", 50]["net_sharpe_rank"] == 2
    assert rows["static", 50]["net_sharpe_rank"] == 1
    assert rows["active", 50]["net_cagr"] < rows["static", 50]["net_cagr"]


def test_mu_shocks_can_record_infeasibility():
    data = pd.DataFrame(
        {"A": [-0.0009, 0.0011, 0.001], "B": [-0.0018, 0.0022, 0.002]},
        index=pd.to_datetime(["2020-01-02", "2020-01-31", "2020-02-28"]),
    )
    config = WalkForwardConfig(
        start_date="2020-01-31",
        end_date="2020-02-28",
        universe=("A", "B"),
        training_window=1,
        min_observations=2,
        strategy=StrategySpec("min_variance", {"target_return": 0.0378}),
    )
    report = run_sensitivity(
        data,
        config,
        SensitivityConfig(
            return_shocks=(-0.1,),
            covariance_methods=(),
            training_windows=(),
            include_expanding=False,
        ),
        CostConfig(rates_bps=(0,)),
    )
    assert (
        report.comparison.implementations["base"].gross.rebalances[0][
            "allocation_status"
        ]
        == "ok"
    )
    assert report.changes["mu_0"]["variant_allocation_failure_count"] == 1
    assert report.changes["mu_0"]["weight_distance"]["mean"] is None
    assert not report.changes["mu_0"]["complete_pairs"]
    assert all(row["net_sharpe_rank"] is None for row in report.comparison.rows)


def test_cvar_mean_override_is_explicitly_unsupported(research_case):
    data, config = research_case
    config = replace(
        config, strategy=StrategySpec("mean_cvar", {"target_return": 0.02})
    )
    report = run_sensitivity(
        data,
        config,
        SensitivityConfig(
            covariance_methods=(), training_windows=(), include_expanding=False
        ),
        CostConfig(rates_bps=(0,)),
    )
    assert {
        "kind": "expected_return",
        "reason": "expected_return_override_not_supported",
    } in report.metadata["skipped_experiments"]
    assert list(report.comparison.implementations) == ["base"]
    with pytest.raises(ValueError, match="supported return-dependent"):
        replace(config.strategy, expected_return_shifts={"SPY": 0.01})


def test_window_eligibility_changes_are_reported_not_intersected(research_case):
    data, config = research_case
    data.loc[:"2019-12-31", "GLD"] = np.nan
    config = replace(config, strategy=StrategySpec("equal_weight"))
    report = run_sensitivity(
        data,
        config,
        SensitivityConfig(
            return_shocks=(),
            covariance_methods=(),
            training_windows=(12, 60),
            include_expanding=False,
        ),
        CostConfig(rates_bps=(0,)),
    )
    base = report.comparison.implementations["base"].gross
    short = report.comparison.implementations["window_12m"].gross
    assert "GLD" not in base.rebalances[0]["eligible_assets"]
    assert "GLD" in short.rebalances[0]["eligible_assets"]
    assert report.changes["window_12m"]["eligible_universe_changed_count"] == 3
    assert report.changes["window_12m"]["weight_distance"]["max"] > 0


def test_identical_experiments_reuse_base_run(research_case, monkeypatch):
    import validation.portfolio.sensitivity as module

    data, config = research_case
    original = module.evaluate
    calls = []

    def spy(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "evaluate", spy)
    report = run_sensitivity(
        data,
        config,
        SensitivityConfig(
            return_shocks=(0,),
            random_draws=1,
            random_scale=0,
            covariance_methods=(),
            training_windows=(),
            include_expanding=False,
        ),
    )
    assert len(calls) == 1
    assert len(report.comparison.rows) == 15  # three labels, five cost scenarios
    assert report.changes["mu_0"]["weight_distance"]["max"] == 0


def test_empty_month_remains_a_gap_in_cost_series(research_case):
    data, config = research_case
    data = data.loc[data.index.to_period("M") != pd.Period("2021-05")]
    run = evaluate(data, replace(config, strategy=StrategySpec("equal_weight")))
    report = analyze_costs(run)
    for scenario in report.scenarios:
        assert not scenario.metrics["complete"]
        assert scenario.nav.loc["2021-06"].isna().all()


def test_resampled_mu_sensitivity_keeps_optimizer_seed(research_case):
    data, config = research_case
    config = replace(
        config, strategy=StrategySpec("resampled_mvo", {"n_simulations": 4})
    )
    experiments = SensitivityConfig(
        return_shocks=(0.01,),
        covariance_methods=(),
        training_windows=(),
        include_expanding=False,
    )
    first = run_sensitivity(data, config, experiments, CostConfig(rates_bps=(0,)))
    second = run_sensitivity(data, config, experiments, CostConfig(rates_bps=(0,)))
    assert first.changes == second.changes
    assert first.metadata["optimizer_seed"] == 61
