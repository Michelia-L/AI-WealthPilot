"""Offline risk calibration, descriptive regime and stress hand calculations."""

import json
import socket
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from src.portfolio.backtest import STRESS_SCENARIOS
from src.portfolio.optimizer import PortfolioOptimizer
from validation.portfolio import (
    AnalysisSeries,
    AssetExposure,
    CalibrationConfig,
    HistoricalScenario,
    RegimeConfig,
    StrategySpec,
    SyntheticScenario,
    WalkForwardConfig,
    analyze_risk,
    calibrate_risk,
    classify_regimes,
    evaluate,
    historical_stress,
    regime_metrics,
    standard_scenarios,
    synthetic_stress,
)
from validation.portfolio.forecasts import risk_snapshot


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Risk research must not access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def case():
    dates = pd.bdate_range("2018-01-01", "2020-06-30")
    rng = np.random.default_rng(62)
    data = pd.DataFrame(
        rng.normal([0.0004, 0.0001], [0.012, 0.004], (len(dates), 2)),
        index=dates,
        columns=["SPY", "AGG"],
    )
    config = WalkForwardConfig(
        "2019-12-31",
        "2020-06-30",
        ("SPY", "AGG"),
        training_window=12,
        min_observations=40,
        covariance_method="sample",
    )
    return data, config


@pytest.fixture
def run(case):
    return evaluate(*case)


def series(values, units="daily_simple_return"):
    return AnalysisSeries(values, "deterministic fixture", "synthetic", units)


def test_snapshot_hand_covariance():
    history = pd.DataFrame(
        {"A": [0.01, -0.01, 0.02, -0.02], "B": [-0.02, -0.01, 0.01, 0.02]},
        index=pd.date_range("2020-01-01", periods=4),
    )
    optimizer = PortfolioOptimizer(history, covariance_method="sample")
    weights = {"A": 0.6, "B": 0.4}
    result = risk_snapshot(
        history, weights, optimizer, covariance_role="decision_model"
    )
    # Sample variances .001/3 each, cross-product -.0003/3.
    covariance = np.array([[0.001 / 3, -0.0003 / 3], [-0.0003 / 3, 0.001 / 3]]) * 252
    assert np.asarray(result["annual_covariance"]) == pytest.approx(covariance)
    assert result["predicted_volatility"] == pytest.approx(
        np.sqrt(np.array([0.6, 0.4]) @ covariance @ np.array([0.6, 0.4]))
    )
    assert result["downside_horizon"] == "one trading observation"


@pytest.mark.parametrize(
    "strategy", ["min_variance", "mvo", "erc", "resampled_mvo", "mean_cvar"]
)
def test_forecasts_use_actual_optimizer_covariance(case, strategy):
    data, config = case
    params = {"n_simulations": 2} if strategy == "resampled_mvo" else {}
    run = evaluate(
        data,
        replace(config, strategy=StrategySpec(strategy, params), end_date="2020-01-31"),
    )
    record = run.rebalances[0]
    forecast = record["risk_forecast"]
    assert record["allocation_status"] == forecast["status"] == "ok"
    assert forecast["predicted_volatility"] == pytest.approx(
        record["diagnostics"]["volatility"]
    )
    assert forecast["training_end"] <= record["as_of"]
    assert forecast["estimation_observations"] == record["estimation_observations"]
    assert forecast["covariance_role"] == (
        "reporting_only" if strategy == "mean_cvar" else "decision_model"
    )
    if strategy == "mean_cvar":
        history = data.loc[
            (data.index >= record["training_window_start"])
            & (data.index <= record["as_of"])
        ]
        result = PortfolioOptimizer(history, covariance_method="sample").minimize_cvar()
        assert forecast["var_daily"] == pytest.approx(result["var"] / np.sqrt(252))
        assert forecast["cvar_daily"] == pytest.approx(result["cvar"] / np.sqrt(252))
        assert forecast["downside_role"] == "decision_objective"


def test_reporting_covariance_does_not_gate_baseline(case):
    data, config = case
    config = replace(
        config, min_coverage=0.5, min_observations=150, end_date="2020-01-31"
    )
    dates = data.index[(data.index > "2018-12-31") & (data.index <= "2019-12-31")]
    data.loc[dates[:90], "SPY"] = np.nan
    data.loc[dates[-90:], "AGG"] = np.nan
    run = evaluate(data, config)
    record = run.rebalances[0]
    assert record["status"] == "ok"
    assert record["risk_forecast"]["reason"] == "insufficient_risk_history"
    assert record["weights"] == {"SPY": 0.5, "AGG": 0.5}
    static = evaluate(
        data, replace(config, strategy=StrategySpec("static", {"weights": {"SPY": 1}}))
    )
    assert static.rebalances[0]["risk_forecast"]["status"] == "ok"
    assert static.rebalances[0]["risk_forecast"]["assets"] == ["SPY"]


def test_risk_reporting_error_does_not_leak_or_change_allocation(case, monkeypatch):
    import validation.portfolio.walk_forward as engine

    def broken(*args, **kwargs):
        raise RuntimeError("api_key=private-sentinel")

    monkeypatch.setattr(engine, "reporting_snapshot", broken)
    run = evaluate(*case)
    assert all(r["status"] == "ok" for r in run.rebalances)
    assert all(
        r["risk_forecast"]["reason"] == "risk_estimation_exception"
        for r in run.rebalances
    )
    assert "private-sentinel" not in run.to_json()


def test_future_returns_do_not_change_first_forecast(case):
    data, config = case
    baseline = evaluate(data, config)
    altered = data.copy()
    altered.loc[altered.index > config.start_date] *= 3
    variant = evaluate(altered, config)
    assert baseline.rebalances[0]["weights"] == variant.rebalances[0]["weights"]
    assert (
        baseline.rebalances[0]["risk_forecast"]
        == variant.rebalances[0]["risk_forecast"]
    )
    original = calibrate_risk({"EW": baseline})["per_rebalance"][0]
    changed = calibrate_risk({"EW": variant})["per_rebalance"][0]
    assert original["realized_start"] > baseline.rebalances[0]["as_of"]
    assert original["realized_volatility"] != changed["realized_volatility"]


def test_calibration_error_metrics_known_fixture(run):
    errors = [0.01, -0.02, 0.03, -0.01, 0.02, -0.03]
    for record, error in zip(run.rebalances, errors, strict=True):
        values = run.returns.loc[record["holding_start"] : record["holding_end"]]
        realized = values.std(ddof=1) * np.sqrt(252)
        record["risk_forecast"]["predicted_volatility"] = realized - error
    report = calibrate_risk({"EW": run})
    summary = report["summary"][0]
    assert summary["mae"] == pytest.approx(0.02)
    assert summary["bias"] == pytest.approx(0)
    assert summary["rmse"] == pytest.approx(np.sqrt(np.mean(np.square(errors))))
    assert summary["median_absolute_error"] == pytest.approx(0.02)
    assert summary["paired_periods"] == 6


def test_daily_var_exceedances_and_conditional_loss(run):
    for record in run.rebalances:
        dates = run.returns.loc[record["holding_start"] : record["holding_end"]].index
        run.returns.loc[dates] = -0.01
        run.returns.loc[dates[:5]] = -0.03
        record["risk_forecast"].update(
            var_daily=0.02, cvar_daily=0.025, training_tail_observations=10
        )
    report = calibrate_risk({"EW": run})
    assert all(r["exceedances"] == 5 for r in report["per_rebalance"])
    assert all(
        r["realized_conditional_loss"] == pytest.approx(0.03)
        for r in report["per_rebalance"]
    )
    summary = report["summary"][0]
    assert summary["exceedance_frequency"] == pytest.approx(30 / len(run.returns))
    assert summary["expected_exceedance_frequency"] == pytest.approx(0.05)
    assert summary["conditional_loss_bias"] == pytest.approx(0.005)
    for record in run.rebalances:
        record["risk_forecast"]["var_daily"] = 0.03  # Ties are not strict breaches.
    report = calibrate_risk({"EW": run})
    assert report["summary"][0]["exceedances"] == 0
    assert report["summary"][0]["conditional_loss_bias"] is None


def test_calibration_retains_failed_small_and_missing_forecasts(run):
    run.rebalances[0]["risk_forecast"] = None
    run.rebalances[1]["status"] = "failed"
    run.rebalances[2]["risk_forecast"]["training_end"] = pd.Timestamp("2030-01-01")
    run.rebalances[3]["risk_forecast"]["training_tail_observations"] = 1
    rows = calibrate_risk({"EW": run})["per_rebalance"]
    assert rows[0]["status"] == "forecast_unavailable"
    assert rows[1]["status"] == "incomplete_holding_window"
    assert rows[2]["status"] == "invalid_forecast_boundary"
    assert rows[3]["downside_status"] == "insufficient_training_tail"
    report = calibrate_risk({"EW": run}, CalibrationConfig(min_observations=100))
    assert all(s["mae"] is None for s in report["summary"])


def test_zero_realized_vol_ratio_is_null(run):
    run.returns[:] = 0
    assert all(
        r["predicted_realized_ratio"] is None
        for r in calibrate_risk({"EW": run})["per_rebalance"]
    )


def test_regime_rules_provenance_and_determinism(run):
    benchmark = pd.Series(0.001, index=run.returns.index)
    benchmark.loc["2020-02"] = -0.002
    benchmark.loc["2020-03"] = np.resize([-0.03, 0.03], len(benchmark.loc["2020-03"]))
    levels = pd.Series(
        [0.01, 0.02, 0.01],
        index=pd.to_datetime(["2019-12-31", "2020-01-31", "2020-02-29"]),
    )
    kwargs = {
        "rates": series(levels, "annual_yield_decimal"),
        "inflation": series(levels, "yoy_inflation_decimal"),
    }
    regimes = classify_regimes(run, series(benchmark), **kwargs)
    assert regimes == classify_regimes(run, series(benchmark), **kwargs)
    labels = [r["analysis_regime_label"] for r in regimes["per_rebalance"]]
    assert labels[0] == {
        "equity": "bull",
        "volatility": "low_vol",
        "rates": "rising_rates",
        "inflation": "inflationary",
    }
    assert labels[1]["equity"] == "bear"
    assert labels[1]["rates"] == "falling_rates"
    assert labels[2]["volatility"] == "high_vol"
    assert labels[-1]["rates"] == "unknown"  # Stale macro observation.
    assert regimes["metadata"]["rates"]["revision_policy"] == "synthetic"
    assert len(regimes["metadata"]["benchmark"]["sha256"]) == 64


def test_missing_macro_and_benchmark_are_explicit(run):
    values = pd.Series(0.001, index=run.returns.index)
    values.iloc[0] = np.nan
    report = classify_regimes(run, series(values))
    assert report["per_rebalance"][0]["analysis_regime_label"] == dict.fromkeys(
        ["equity", "volatility", "rates", "inflation"], "unknown"
    )
    rows = regime_metrics({"EW": run}, report)["rows"]
    assert all(
        r["status"] != "ok" and r["cagr"] is None
        for r in rows
        if r["dimension"] == "rates"
    )


def test_posthoc_inputs_cannot_modify_runs(case, run):
    before = run.to_json()
    benchmark = series(pd.Series(0.001, index=run.returns.index))
    report = analyze_risk(
        {"EW": run},
        benchmark=benchmark,
        synthetic_scenarios=[SyntheticScenario("down", {"SPY": -0.3})],
    )
    changed = analyze_risk({"EW": run}, benchmark=series(-benchmark.values))
    assert report.regimes != changed.regimes
    assert before == run.to_json()
    assert "regime" not in WalkForwardConfig.__dataclass_fields__
    assert set(report.tables()) == {
        "calibration",
        "calibration_summary",
        "regime_metrics",
        "historical_stress",
        "synthetic_stress",
    }
    assert json.loads(report.to_json())["metadata"]["analysis_only"] is True


def test_regime_small_samples_and_failures(run):
    regimes = classify_regimes(run, series(pd.Series(0.001, index=run.returns.index)))
    config = RegimeConfig(min_periods=7)
    bull = next(
        r
        for r in regime_metrics({"EW": run}, regimes, config=config)["rows"]
        if r["label"] == "bull"
    )
    assert bull["status"] == "insufficient_sample" and bull["sharpe"] is None
    run.rebalances[0]["status"] = "failed"
    bull = next(
        r for r in regime_metrics({"EW": run}, regimes)["rows"] if r["label"] == "bull"
    )
    assert bull["status"] == "incomplete_periods" and bull["max_drawdown"] is None
    assert bull["failed_or_skipped_periods"] == 1


def test_regime_drawdown_does_not_join_disjoint_episodes(run):
    values = pd.Series(0.001, index=run.returns.index)
    values.loc["2020-02"] = -0.001
    labels = classify_regimes(run, series(values))
    run.returns[:] = 0
    for r in run.rebalances:
        r["realized_return"] = -0.1
    run.returns.loc["2020-01-02"] = -0.1
    run.returns.loc["2020-03-02"] = -0.1
    bull = next(
        r for r in regime_metrics({"EW": run}, labels)["rows"] if r["label"] == "bull"
    )
    assert bull["episodes"] == 2
    assert bull["max_drawdown"] == pytest.approx(-0.1)  # Joining would give -19%.
    assert bull["total_return"] == pytest.approx(-0.19)
    assert bull["positive_period_frequency"] == 0


def test_historical_windows_reuse_production_and_select_exact_dates(run):
    report = historical_stress({"EW": run}, min_observations=2)
    assert report["metadata"]["scenarios"] == [
        {"name": n, "start": s, "end": e} for n, s, e in STRESS_SCENARIOS
    ]
    covid = next(r for r in report["rows"] if r["scenario"] == "covid_2020")
    sample = run.returns.loc["2020-02-19":"2020-03-23"]
    assert covid["first_observation"] == pd.Timestamp("2020-02-19")
    assert covid["last_observation"] == pd.Timestamp("2020-03-23")
    assert covid["window_return"] == pytest.approx((1 + sample).prod() - 1)
    assert covid["pre_event_as_of"] == pd.Timestamp("2020-01-31")
    assert all(
        r["status"] == "out_of_range"
        for r in report["rows"]
        if r["scenario"] != "covid_2020"
    )


def test_historical_loss_recovery_and_baseline(run):
    run.returns[:] = 0
    run.returns.loc["2020-02-19"] = -0.2
    run.returns.loc["2020-03-24"] = 0.25
    scenario = HistoricalScenario("hand", "2020-02-19", "2020-03-23")
    report = historical_stress(
        {"EW": run, "baseline": deepcopy(run)}, [scenario], baseline="baseline"
    )
    row = report["rows"][0]
    assert row["max_drawdown"] == row["window_return"] == pytest.approx(-0.2)
    assert row["recovery_date"] == pd.Timestamp("2020-03-24")
    assert row["relative_return_vs_baseline"] == 0
    assert row["peak_date"] is None  # Opening capital included.
    run.rebalances[2]["status"] = "failed"
    assert (
        historical_stress({"EW": run}, [scenario])["rows"][0]["status"]
        == "incomplete_window"
    )


def test_synthetic_shocks_hand_calculation(run):
    exposures = {"SPY": AssetExposure(True, 0, 0), "AGG": AssetExposure(False, 5, 3)}
    scenarios = standard_scenarios(exposures)
    report = synthetic_stress({"EW": run}, scenarios, exposures=exposures)
    rows = report["rows"][:5]
    assert rows[0]["portfolio_return"] == pytest.approx(-0.15)
    assert rows[1]["portfolio_return"] == pytest.approx(-0.05)
    assert rows[2]["stressed_volatility"] == pytest.approx(
        rows[2]["base_volatility"] * 1.5
    )
    assert rows[3]["stressed_volatility"] >= rows[3]["base_volatility"]
    assert rows[4]["portfolio_return"] == pytest.approx(-0.215)
    forecast = run.rebalances[0]["risk_forecast"]
    cov = np.asarray(forecast["annual_covariance"])
    std = np.sqrt(cov.diagonal())
    stressed = 0.25 * cov + 0.75 * np.outer(std, std)
    assert rows[3]["stressed_volatility"] == pytest.approx(
        np.sqrt(np.array([0.5, 0.5]) @ stressed @ np.array([0.5, 0.5]))
    )


def test_synthetic_missing_exposures_and_invalid_covariance(run):
    scenario = SyntheticScenario("rates", rate_change=0.02)
    report = synthetic_stress({"EW": run}, [scenario])
    assert all(r["loss_status"] == "missing_duration_exposure" for r in report["rows"])
    assert all(r["risk_status"] == "ok" for r in report["rows"])
    run.rebalances[0]["risk_forecast"]["annual_covariance"] = [[1, 2], [2, 1]]
    assert (
        synthetic_stress({"EW": run}, [scenario])["rows"][0]["risk_status"]
        == "invalid_covariance"
    )
    exposures = dict.fromkeys(["SPY", "AGG"], AssetExposure(duration=100))
    assert (
        synthetic_stress({"EW": run}, [scenario], exposures=exposures)["rows"][0][
            "loss_status"
        ]
        == "shock_below_minus_one"
    )


def test_covariance_candidates_remain_separate(case):
    data, config = case
    runs = {
        method: evaluate(
            data,
            replace(
                config, covariance_method=method, strategy=StrategySpec("min_variance")
            ),
        )
        for method in ["sample", "ledoit-wolf", "oas"]
    }
    report = analyze_risk(runs)
    assert len(report.calibration["summary"]) == 3
    assert {r["covariance_method"] for r in report.calibration["summary"]} == set(runs)
    assert all(r["periods"] == 6 for r in report.calibration["summary"])
    assert report.implementation["sample"]["turnover"]["summary"]["observations"] == 5


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CalibrationConfig(min_observations=1),
        lambda: CalibrationConfig(min_periods=0),
        lambda: CalibrationConfig(material_exceedance_ratio=1),
        lambda: RegimeConfig(low_volatility=0.3),
        lambda: RegimeConfig(rate_change_threshold=-1),
        lambda: RegimeConfig(min_periods=0),
        lambda: RegimeConfig(confidence=1),
        lambda: SyntheticScenario("x", volatility_multiplier=0),
        lambda: SyntheticScenario("x", correlation_blend=2),
        lambda: SyntheticScenario("x", {"SPY": -2}),
        lambda: HistoricalScenario("x", "2020-01-01", "2019-01-01"),
        lambda: AssetExposure(duration=-1),
    ],
)
def test_invalid_configuration(factory):
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize("training_end", [None, "not-a-date", "2030-01-01"])
def test_custom_forecast_requires_valid_past_boundary(run, training_end):
    run.rebalances[0]["risk_forecast"]["training_end"] = training_end
    assert (
        calibrate_risk({"EW": run})["per_rebalance"][0]["status"]
        == "invalid_forecast_boundary"
    )
    assert (
        synthetic_stress(
            {"EW": run}, [SyntheticScenario("vol", volatility_multiplier=1.5)]
        )["rows"][0]["risk_status"]
        == "invalid_forecast_boundary"
    )


def test_optimizer_snapshot_failure_preserves_allocation(case, monkeypatch):
    import validation.portfolio.strategies as strategies

    def broken(*args, **kwargs):
        raise RuntimeError("token=private-sentinel")

    monkeypatch.setattr(strategies, "risk_snapshot", broken)
    data, config = case
    run = evaluate(data, replace(config, strategy=StrategySpec("min_variance")))
    assert all(
        r["status"] == "ok"
        and r["risk_forecast"]["reason"] == "risk_estimation_exception"
        for r in run.rebalances
    )
    assert "private-sentinel" not in run.to_json()


def test_regime_exact_boundaries_and_future_macro_cutoff(run):
    benchmark = pd.Series(0.0, index=run.returns.index)
    levels = pd.Series(
        [0.0, 0.0025, -0.0025, 100.0],
        index=pd.to_datetime(["2019-12-31", "2020-01-31", "2020-02-29", "2030-01-01"]),
    )
    report = classify_regimes(
        run, series(benchmark), rates=series(levels, "annual_yield_decimal")
    )
    row = report["per_rebalance"][0]
    assert row["analysis_regime_label"]["rates"] == "stable_rates"
    assert row["analysis_regime_label"]["equity"] == "flat"
    assert row["rates_end_observation"] == pd.Timestamp("2020-01-31")
    assert report["per_rebalance"][-1]["analysis_regime_label"]["rates"] == "unknown"


def test_analysis_series_validation_and_protocol_mismatch(run):
    values = pd.Series([0.0, 0.0], index=pd.to_datetime(["2020-01-01", "2020-01-01"]))
    with pytest.raises(ValueError):
        series(values)
    with pytest.raises(ValueError):
        series(pd.Series([np.inf], index=pd.to_datetime(["2020-01-01"])))
    with pytest.raises(ValueError):
        AnalysisSeries(run.returns, "source", "unspecified", "daily_simple_return")
    with pytest.raises(ValueError):
        classify_regimes(run, series(run.returns, "annual_yield_decimal"))
    with pytest.raises(ValueError):
        classify_regimes(run, series(run.returns * 0 - 2))
    with pytest.raises(ValueError):
        analyze_risk({"EW": run}, rates=series(run.returns, "annual_yield_decimal"))
    labels = classify_regimes(run, series(run.returns))
    labels["per_rebalance"].pop()
    with pytest.raises(ValueError):
        regime_metrics({"EW": run}, labels)
    other = deepcopy(run)
    other.metadata["data_sha256"] = "different"
    with pytest.raises(ValueError):
        calibrate_risk({"EW": run, "other": other})


def test_historical_recovery_is_censored_at_wholly_missing_month(run):
    run.returns[:] = 0
    run.returns.loc["2020-02-19"] = -0.2
    run.returns.loc["2020-05-01"] = 0.3
    run.rebalances[3]["status"] = "skipped"
    run.returns = run.returns.loc[run.returns.index.month != 4]
    row = historical_stress({"EW": run})["rows"][0]
    assert row["status"] == "ok"
    assert row["recovery_status"] == "censored_at_gap"
    assert row["recovery_date"] is None
    run.rebalances[3]["status"] = "ok"
    run.returns.loc["2020-05-01"] = 0
    assert (
        historical_stress({"EW": run})["rows"][0]["recovery_status"]
        == "not_recovered_in_available_history"
    )
    run.returns[:] = 0.001
    assert historical_stress({"EW": run})["rows"][0]["recovery_status"] == "no_drawdown"


def test_stress_invalid_definitions_and_small_sample(run):
    scenario = HistoricalScenario("small", "2020-02-19", "2020-02-20")
    assert (
        historical_stress({"EW": run}, [scenario])["rows"][0]["status"]
        == "insufficient_observations"
    )
    with pytest.raises(ValueError):
        historical_stress({"EW": run}, [scenario, scenario])
    with pytest.raises(ValueError):
        historical_stress({"EW": run}, baseline="missing")
    with pytest.raises(ValueError):
        historical_stress({"EW": run}, min_observations=1)
    shock = SyntheticScenario("x")
    with pytest.raises(ValueError):
        synthetic_stress({"EW": run}, [shock, shock])
    with pytest.raises(ValueError):
        synthetic_stress({"EW": run}, [SyntheticScenario("x", {"typo": -0.1})])
    with pytest.raises(ValueError):
        synthetic_stress({"EW": run}, [shock], exposures={"typo": AssetExposure()})


def test_failed_allocations_and_legacy_runs_stay_unknown_in_stress(run):
    run.rebalances[0]["allocation_status"] = "failed"
    del run.rebalances[1]["risk_forecast"]
    run.rebalances[2]["risk_forecast"]["assets"] = ["SPY"]
    rows = synthetic_stress({"EW": run}, [SyntheticScenario("x", {"SPY": -0.3})])[
        "rows"
    ]
    assert rows[0]["portfolio_return"] is None
    assert rows[1]["portfolio_return"] == pytest.approx(-0.15)
    assert rows[1]["stressed_volatility"] is None
    assert rows[2]["risk_status"] == "incomplete_covariance"


def test_absent_holding_month_remains_a_missing_calibration_period(case):
    data, config = case
    data = data.loc[(data.index.year != 2020) | (data.index.month != 2)]
    run = evaluate(data, config)
    row = calibrate_risk({"EW": run})["per_rebalance"][1]
    assert row["status"] == "incomplete_holding_window"
    assert row["observations"] == 0
    assert row["realized_volatility"] is None
    labels = classify_regimes(run, series(data["SPY"]))
    assert labels["per_rebalance"][1]["analysis_regime_label"]["equity"] == "unknown"
