"""Offline retirement validation, including hand-calculated cash-flow fixtures."""

import json
import socket

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from src.portfolio.retirement_paths import distribution_from_growth, gbm_growth
from src.portfolio.simulator import MonteCarloSimulator
from validation.retirement import (
    AssumptionSource,
    EngineConfig,
    HistoricalReturns,
    RetirementScenario,
    RetirementStress,
    compare_models,
    convergence,
    evaluate_paths,
    monte_carlo_se,
    parameter_grid,
    run_retirement,
    sample_indices,
    sequence_experiment,
    stability_table,
    standard_sensitivities,
    stress_comparison,
)
from validation.retirement.bootstrap import bootstrap_growth


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("retirement validation must stay offline")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def scenario():
    return RetirementScenario(
        current_age=60,
        retirement_age=65,
        life_expectancy=85,
        current_savings=500_000,
        annual_savings=20_000,
        desired_annual_income=40_000,
        expected_return=0.06,
        volatility=0.18,
        n_simulations=100,
        seed=42,
        code_version="fixture-v1",
    )


@pytest.fixture
def history():
    return HistoricalReturns(
        dates=tuple(pd.date_range("2000-01-31", periods=60, freq="ME").date),
        returns=tuple(np.tile([-0.12, -0.06, 0.01, 0.02, 0.08, 0.1], 10)),
        frequency="monthly",
        source="static synthetic fixture",
        portfolio_mapping="one supplied whole-portfolio nominal total-return series",
        currency="CNY",
        fx_treatment="already translated to CNY",
        sample_kind="synthetic",
    )


@pytest.mark.parametrize("strategy", ["fixed", "guardrails"])
@pytest.mark.parametrize("seed", [7, 42])
def test_gbm_production_parity_and_reproducibility(scenario, strategy, seed):
    s = scenario.changed(withdrawal_strategy=strategy, seed=seed)
    production = MonteCarloSimulator(
        s.expected_return, s.volatility, s.n_simulations, seed=seed
    ).retirement_planning(
        s.current_age,
        s.retirement_age,
        s.life_expectancy,
        s.current_savings,
        s.annual_savings,
        s.desired_annual_income,
        s.inflation_rate,
        s.distribution_inflation_rate,
        s.withdrawal_strategy,
        s.guardrail_band,
        s.guardrail_adjust,
    )
    result = run_retirement(s)
    assert result.to_json(include_paths=True) == run_retirement(s).to_json(
        include_paths=True
    )
    np.testing.assert_array_equal(
        result.path_metrics.terminal_wealth, production["distribution_paths"][:, -1]
    )
    assert result.metrics["success_probability"] == production["survival_rate"]


def test_legacy_distribution_fixture():
    # Pre-refactor scalar equations, including the first guardrail inflation step.
    fixed = distribution_from_growth(np.array([100.0]), np.ones((1, 2)), 10, 0, 0, 0.1)
    guard = distribution_from_growth(
        np.array([100.0]), np.ones((1, 2)), 10, 0, 0, 0.1, "guardrails"
    )
    np.testing.assert_allclose(fixed.paths, [[100, 89, 76.9]])
    np.testing.assert_allclose(guard.requested, [[12.1, 11.979]])
    assert guard.cuts.tolist() == [[False, True]]
    assert guard.cut_amounts[0, 1] == pytest.approx(1.331)


def test_iid_resamples_only_supplied_values(history):
    index = sample_indices(60, 5, 24, 42)
    np.testing.assert_array_equal(index, sample_indices(60, 5, 24, 42))
    assert index.min() >= 0 and index.max() < 60
    growth, _ = bootstrap_growth(
        history, EngineConfig(engine="iid_bootstrap"), 5, 2, 42, 0.06, 0.2
    )
    expected = np.prod((1 + np.array(history.returns))[index].reshape(5, 2, 12), axis=2)
    np.testing.assert_allclose(growth, expected)


@pytest.mark.parametrize("block", [3, 6, 12, 60])
def test_contiguous_blocks_do_not_wrap(block):
    indices = sample_indices(60, 20, 125, 7, block)
    assert indices.shape == (20, 125)
    for start in range(0, 125, block):
        assert (np.diff(indices[:, start : start + block], axis=1) == 1).all()
    assert indices.min() >= 0 and indices.max() < 60


def test_annual_bootstrap_and_no_accumulation(scenario):
    h = HistoricalReturns(
        dates=("2020-12-31", "2021-12-31", "2022-12-31"),
        returns=(-0.2, 0.1, 0.3),
        frequency="annual",
        source="fixture",
        portfolio_mapping="fixed portfolio",
        currency="USD",
        fx_treatment="USD",
        sample_kind="synthetic",
    )
    s = scenario.changed(
        current_age=65,
        return_multiplier=1,
        volatility_multiplier=1,
        base_currency="USD",
    )
    r = run_retirement(
        s, EngineConfig(engine="block_bootstrap", block_length=2), history=h
    )
    assert r.metadata["engine"]["history"]["dates"] == [
        "2020-12-31",
        "2021-12-31",
        "2022-12-31",
    ]
    assert r.diagnostics["median_retirement_wealth"] == s.current_savings
    assert json.loads(r.to_json())["metadata"]["engine"]["sample_id"] == h.sample_id


def test_matched_moments_and_distribution_shift(history):
    cfg = EngineConfig(engine="iid_bootstrap", bootstrap_mode="matched_gbm_moments")
    _, diag = bootstrap_growth(history, cfg, 10, 3, 42, 0.08, 0.2, 0.5, 0.7)
    assert diag["mapped_log_mean_per_period"] == pytest.approx(
        (0.08 * 0.5 - 0.5 * (0.2 * 0.7) ** 2) / 12
    )
    assert diag["mapped_log_std_per_period"] == pytest.approx(0.2 * 0.7 / np.sqrt(12))
    _, empirical = bootstrap_growth(
        history, EngineConfig(engine="iid_bootstrap"), 10, 3, 42, 999, 999
    )
    assert empirical["mapped_log_mean_per_period"] == pytest.approx(
        np.log1p(history.returns).mean()
    )


def test_bootstrap_comparison_reproducible_and_paired(scenario, history):
    report = compare_models(scenario, history)
    assert len(report.runs) == 6
    assert report.to_json() == compare_models(scenario, history).to_json()
    for engine in ("gbm", "iid_bootstrap", "block_bootstrap"):
        fixed, guard = [
            report.runs[f"{engine}/{strategy}"] for strategy in ("fixed", "guardrails")
        ]
        assert (
            fixed.metadata["distribution_growth_sha256"]
            == guard.metadata["distribution_growth_sha256"]
        )
        assert (
            fixed.metadata["accumulation_growth_sha256"]
            == guard.metadata["accumulation_growth_sha256"]
        )
    assert set(report.tables()) == {"comparison", "annual"}


def test_sequence_effect_and_no_withdrawal_invariance(scenario):
    s = scenario.changed(
        current_age=65,
        life_expectancy=69,
        current_savings=100,
        annual_savings=0,
        desired_annual_income=20,
        inflation_rate=0,
    )
    r = sequence_experiment(s, (-0.5, 0.5, 0.1, 0.1))
    early, late = r.runs["early_losses"], r.runs["late_losses"]
    assert early.metrics["median_terminal_wealth"] == 0
    assert early.metrics["median_depletion_year"] == 4
    assert late.metrics["median_terminal_wealth"] == pytest.approx(37.65)
    assert early.metrics["mean_lifetime_nominal_withdrawals"] == pytest.approx(68.25)
    assert late.metrics["mean_lifetime_nominal_withdrawals"] == 80
    assert early.metrics["survival_rate"] == 0 and late.metrics["survival_rate"] == 1
    assert early.metrics["success_probability_mc_se"] is None
    no_spend = sequence_experiment(
        s.changed(desired_annual_income=0), (-0.5, 0.5, 0.1, 0.1)
    )
    for run in no_spend.runs.values():
        assert run.metrics["median_terminal_wealth"] == pytest.approx(90.75)
    guard = sequence_experiment(
        s.changed(withdrawal_strategy="guardrails"), (-0.5, 0.5, 0.1, 0.1)
    )
    assert guard.runs["early_losses"].metrics["mean_spending_cuts"] > 0


def test_hand_built_success_spending_and_depletion(scenario):
    s = scenario.changed(
        current_age=65,
        life_expectancy=67,
        n_simulations=3,
        current_savings=100,
        desired_annual_income=40,
        inflation_rate=0,
    )
    r = evaluate_paths(s, np.empty((3, 0)), np.array([[1, 1], [0.5, 1], [0, 1]]))
    assert r.metrics["success_probability"] == pytest.approx(1 / 3)
    assert r.metrics["probability_of_depletion"] == pytest.approx(2 / 3)
    assert r.metrics["median_depletion_year"] == 1.5
    assert r.metrics["median_depletion_age"] == 66.5
    np.testing.assert_allclose(r.path_metrics.nominal_withdrawals, [80, 50, 0])
    np.testing.assert_allclose(r.path_metrics.lifetime_real_shortfall, [0, 30, 80])
    assert r.metrics["fraction_paths_maintaining_spending_floor"] == pytest.approx(
        1 / 3
    )
    assert r.diagnostics["depletion_year_counts"] == {"1": 1, "2": 1}
    assert (
        json.loads(r.to_json(include_paths=True))["path_metrics"][0]["depletion_year"]
        is None
    )
    assert set(r.tables()) == {"summary", "paths", "annual"}


def test_zero_start_exact_exhaustion_and_contribution_timing(scenario):
    s = scenario.changed(
        current_age=65,
        life_expectancy=66,
        n_simulations=1,
        current_savings=0,
        desired_annual_income=0,
    )
    r = evaluate_paths(s, np.empty((1, 0)), np.ones((1, 1)))
    assert r.metrics["median_depletion_year"] == 0
    r = evaluate_paths(
        s.changed(current_savings=100, desired_annual_income=100, inflation_rate=0),
        np.empty((1, 0)),
        np.ones((1, 1)),
    )
    assert r.metrics["survival_rate"] == 0
    assert r.metrics["fraction_paths_maintaining_spending_floor"] == 1
    s = s.changed(
        current_age=63, current_savings=100, annual_savings=10, inflation_rate=0
    )
    a = evaluate_paths(s, np.array([[0.5, 2]]), np.ones((1, 1)))
    b = evaluate_paths(s, np.array([[2, 0.5]]), np.ones((1, 1)))
    assert a.metrics["median_terminal_wealth"] == 130
    assert b.metrics["median_terminal_wealth"] == 115


def test_inflation_nominal_and_real_spending(scenario):
    s = scenario.changed(
        current_age=64,
        life_expectancy=67,
        n_simulations=1,
        current_savings=10000,
        annual_savings=0,
        desired_annual_income=100,
        inflation_rate=0.1,
        distribution_inflation_rate=0.2,
    )
    r = evaluate_paths(s, np.ones((1, 1)), np.ones((1, 2)))
    np.testing.assert_allclose(r.annual_metrics.target_nominal_spending, [132, 158.4])
    assert r.metrics["mean_annual_real_spending"] == pytest.approx(100)
    low = evaluate_paths(
        s.changed(distribution_inflation_rate=0), np.ones((1, 1)), np.ones((1, 2))
    )
    assert (
        r.metrics["mean_requested_nominal_withdrawals"]
        > low.metrics["mean_requested_nominal_withdrawals"]
    )


def test_guardrail_spending_and_counts(scenario):
    s = scenario.changed(
        current_age=65,
        life_expectancy=68,
        n_simulations=1,
        current_savings=100,
        desired_annual_income=10,
        inflation_rate=0,
        withdrawal_strategy="guardrails",
    )
    r = evaluate_paths(s, np.empty((1, 0)), np.array([[0.5, 1, 1]]))
    np.testing.assert_allclose(
        r.annual_metrics.mean_requested_nominal_spending, [10, 9, 8.1]
    )
    assert r.metrics["mean_spending_cuts"] == 2
    assert r.metrics["mean_cumulative_real_cut_amount"] == pytest.approx(1.9)
    assert r.metrics["mean_lifetime_real_shortfall"] == pytest.approx(2.9)
    up = evaluate_paths(s, np.empty((1, 0)), np.array([[2, 2, 2]]))
    assert up.metrics["mean_spending_increases"] == 2
    depleted = evaluate_paths(
        s.changed(current_savings=1), np.empty((1, 0)), np.ones((1, 3))
    )
    assert depleted.metrics["mean_spending_cuts"] == 0
    assert depleted.metrics["mean_lifetime_nominal_withdrawals"] == 1


def test_se_and_repeated_seed_convergence(scenario):
    assert monte_carlo_se(0.868, 10000) == pytest.approx(np.sqrt(0.868 * 0.132 / 10000))
    assert monte_carlo_se(0, 10) == monte_carlo_se(1, 10) == 0
    report = convergence(scenario, counts=(20, 40), seeds=(7, 8, 9))
    assert len(report.runs) == 6
    table = stability_table(report)
    assert len(table) == 6
    values = [
        report.runs[f"n=20/seed={seed}"].metrics["success_probability"]
        for seed in (7, 8, 9)
    ]
    row = table[
        (table.n_simulations == 20) & (table.metric == "success_probability")
    ].iloc[0]
    assert row.std_across_seeds == pytest.approx(np.std(values, ddof=1))
    for run in report.runs.values():
        assert run.metrics["success_probability_mc_se"] == monte_carlo_se(
            run.metrics["success_probability"],
            run.metadata["scenario"]["n_simulations"],
        )


def test_sensitivity_grids_provenance_and_finite_differences(scenario):
    s = scenario.changed(
        assumption_source=AssumptionSource(
            source="archived synthetic assumptions", cme_vintage_id="a" * 64
        )
    )
    report = parameter_grid(
        s, {"expected_return": (0.04, 0.06, 0.08), "volatility": (0.1, 0.2)}
    )
    assert len(report.runs) == 6
    assert len(report.metadata["return_sensitivity"]) == 4
    rows = report.tables()["comparison"]
    group = rows[rows["scenario.volatility"] == 0.1].sort_values(
        "scenario.expected_return"
    )
    assert report.metadata["return_sensitivity"][0][
        "success_probability_change_per_unit_return"
    ] == pytest.approx(np.diff(group.success_probability)[0] / 0.02)
    for run in report.runs.values():
        assert (
            run.metadata["scenario"]["assumption_source"]["cme_vintage_id"] == "a" * 64
        )
    suites = standard_sensitivities(scenario.changed(n_simulations=10))
    assert set(suites) == {
        "return_volatility",
        "allocation_shift",
        "inflation",
        "elderly_inflation",
        "longevity",
    }
    assert len(suites["inflation"].runs) == 16
    assert len(suites["allocation_shift"].runs) == 4
    assert (
        suites["elderly_inflation"]
        .runs["elderly"]
        .metadata["effective_distribution_inflation_rate"]
        > scenario.inflation_rate
    )
    for suite in suites.values():
        json.loads(suite.to_json())


def test_shocks_replace_returns_and_inflate_spending(scenario):
    s = scenario.changed(
        current_age=65,
        life_expectancy=68,
        n_simulations=1,
        current_savings=1000,
        desired_annual_income=10,
        inflation_rate=0,
    )
    accumulation, distribution = np.empty((1, 0)), np.ones((1, 3))
    shock = RetirementStress(
        name="known", retirement_returns=(-0.3,), retirement_inflation=(0.1, 0.2)
    )
    r = evaluate_paths(s, accumulation, distribution, stress=shock)
    np.testing.assert_allclose(
        r.annual_metrics.target_nominal_spending, [11, 13.2, 13.2]
    )
    assert r.metrics["median_terminal_wealth"] == pytest.approx(662.6)
    np.testing.assert_array_equal(distribution, np.ones((1, 3)))
    suite = stress_comparison(scenario)
    assert len(suite.runs) == 5
    hashes = {r.metadata["accumulation_growth_sha256"] for r in suite.runs.values()}
    assert len(hashes) == 1


def test_complete_serialization_and_replay(scenario, history):
    s = RetirementScenario.model_validate_json(scenario.model_dump_json())
    result = run_retirement(s, EngineConfig(engine="block_bootstrap"), history=history)
    saved = json.loads(result.to_json())
    metadata = saved["metadata"]
    assert metadata["scenario"] == scenario.model_dump(mode="json")
    replay = run_retirement(
        RetirementScenario.model_validate(metadata["scenario"]),
        EngineConfig.model_validate(
            {k: metadata["engine"][k] for k in EngineConfig.model_fields}
        ),
        history=HistoricalReturns.model_validate(metadata["engine"]["history"]),
    )
    assert replay.to_json() == result.to_json()
    with pytest.raises(ValidationError):
        scenario.seed = 7


@pytest.mark.parametrize(
    "updates",
    [
        {"retirement_age": 59},
        {"life_expectancy": 65},
        {"volatility": -0.1},
        {"inflation_rate": -1},
        {"expected_return": float("nan")},
        {"n_simulations": 0},
        {"seed": -1},
        {"guardrail_adjust": 1},
        {"code_version": ""},
        {"unknown": "field"},
    ],
)
def test_invalid_scenarios_rejected(scenario, updates):
    with pytest.raises(ValidationError):
        scenario.changed(**updates)


@pytest.mark.parametrize(
    "updates",
    [
        {"dates": ("2020-01-01", "2020-03-01"), "returns": (0.1, 0.2)},
        {"dates": ("2020-01-01", "2020-01-31"), "returns": (0.1, 0.2)},
        {"returns": (-1,) * 60},
        {"returns": (float("nan"),) * 60},
        {"dates": ("2020-01-01",)},
    ],
)
def test_invalid_history_rejected(history, updates):
    with pytest.raises(ValidationError):
        HistoricalReturns.model_validate(history.model_dump() | updates)


def test_invalid_experiment_inputs(scenario, history):
    with pytest.raises(ValueError, match="requires supplied"):
        run_retirement(scenario, EngineConfig(engine="iid_bootstrap"))
    with pytest.raises(ValueError, match="does not use"):
        run_retirement(scenario, history=history)
    with pytest.raises(ValueError, match="dimensions"):
        run_retirement(
            scenario,
            EngineConfig(engine="block_bootstrap", block_length=61),
            history=history,
        )
    with pytest.raises(ValueError, match="ignores"):
        parameter_grid(
            scenario,
            {"expected_return": (0.05, 0.06)},
            EngineConfig(engine="iid_bootstrap"),
            history=history,
        )
    for axes in ({}, {"seed": (1, 2)}, {"volatility": ()}, {"volatility": (0.1, 0.1)}):
        with pytest.raises(ValueError):
            parameter_grid(scenario, axes)
    for counts, seeds in [
        ((10, 10), (1, 2)),
        ((10,), (1,)),
        ((), (1, 2)),
        ((10,), (1, 1)),
    ]:
        with pytest.raises(ValueError):
            convergence(scenario, counts=counts, seeds=seeds)
    with pytest.raises(ValueError, match="phase horizons"):
        sequence_experiment(scenario, (0.1,))
    with pytest.raises(ValueError, match="exceeds"):
        run_retirement(
            scenario, stress=RetirementStress(name="long", retirement_returns=(0,) * 21)
        )
    for p, n in [(float("nan"), 10), (-0.1, 10), (1.1, 10), (0.5, 0)]:
        with pytest.raises(ValueError):
            monte_carlo_se(p, n)


def test_constant_sample_and_invalid_paths(scenario, history):
    constant = HistoricalReturns.model_validate(
        history.model_dump() | {"returns": (0,) * 60}
    )
    with pytest.raises(ValueError, match="constant"):
        run_retirement(
            scenario,
            EngineConfig(engine="iid_bootstrap", bootstrap_mode="matched_gbm_moments"),
            history=constant,
        )
    run_retirement(scenario, EngineConfig(engine="iid_bootstrap"), history=constant)
    s = scenario.changed(current_age=65, life_expectancy=66, n_simulations=1)
    for values in ([[float("nan")]], [[-1]], [[1, 1]]):
        with pytest.raises(ValueError):
            evaluate_paths(s, np.empty((1, 0)), values)
    with pytest.raises(ValueError, match="growth"):
        evaluate_paths(s, np.ones((1, 1)), np.ones((1, 1)))
    for values in ((-1.1,), (float("nan"),)):
        with pytest.raises(ValueError):
            sequence_experiment(s, values)
    for updates in ({"retirement_returns": (-1.1,)}, {"retirement_inflation": (-1,)}):
        with pytest.raises(ValidationError):
            RetirementStress(name="bad", **updates)


def test_gbm_horizon_prefix_preserved():
    np.testing.assert_array_equal(
        gbm_growth(0.05, 0.15, 10, 5, 42), gbm_growth(0.05, 0.15, 10, 10, 42)[:, :5]
    )


def test_invalid_currency_and_constant_nonzero_sample(scenario, history):
    with pytest.raises(ValueError, match="same currency"):
        run_retirement(
            scenario.changed(base_currency="USD"),
            EngineConfig(engine="iid_bootstrap"),
            history=history,
        )
    constant = HistoricalReturns.model_validate(
        history.model_dump() | {"returns": (0.1,) * 60}
    )
    with pytest.raises(ValueError, match="constant"):
        run_retirement(
            scenario,
            EngineConfig(engine="iid_bootstrap", bootstrap_mode="matched_gbm_moments"),
            history=constant,
        )


def test_shared_trace_rejects_invalid_growth_and_deflators():
    kwargs = dict(
        desired_annual_income=10,
        accum_years=0,
        inflation_rate=0,
        distribution_inflation_rate=0,
    )
    for terminal, growth in [
        ([100], [[-1]]),
        ([100], [[float("inf")]]),
        ([-1], [[1]]),
        ([100, 200], [[1]]),
    ]:
        with pytest.raises(ValueError, match="growth"):
            distribution_from_growth(np.array(terminal), np.array(growth), **kwargs)
    with pytest.raises(ValueError, match="strategy"):
        distribution_from_growth(
            np.array([100]), np.ones((1, 1)), **kwargs, withdrawal_strategy="other"
        )
    for schedule in (np.array([-1]), np.array([float("nan")]), np.ones(2)):
        with pytest.raises(ValueError, match="schedule"):
            distribution_from_growth(
                np.array([100]), np.ones((1, 1)), **kwargs, inflation_schedule=schedule
            )
    with pytest.raises(ValueError, match="inflation factors"):
        distribution_from_growth(
            np.array([100]),
            np.ones((1, 1)),
            **(kwargs | {"distribution_inflation_rate": -1}),
        )


def test_path_serialization_replays_original_and_stress(scenario):
    s = scenario.changed(current_age=65, life_expectancy=67, n_simulations=1)
    r = evaluate_paths(
        s,
        np.empty((1, 0)),
        np.array([[1.1, 0.9]]),
        stress=RetirementStress(name="crash", retirement_returns=(-0.3,)),
    )
    metadata = json.loads(r.to_json())["metadata"]
    replay = evaluate_paths(
        RetirementScenario.model_validate(metadata["scenario"]),
        metadata["engine"]["accumulation_growth"],
        metadata["engine"]["distribution_growth"],
        stress=RetirementStress.model_validate(metadata["stress"]),
    )
    assert replay.to_json() == r.to_json()
