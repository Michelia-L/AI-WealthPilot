# Risk calibration, regimes and stress research

These offline tools analyze saved walk-forward runs. They measure risk forecast
errors, group outcomes under transparent **ex-post** market labels, and apply
historical or deterministic stress scenarios. They do not select a winning
strategy or assume that shrinkage, minimum variance, ERC or CVaR will outperform.
No UI, macro forecasting, regulatory VaR approval, event probabilities or trade
execution is implemented.

## Runnable offline example

Run from the repository root using the project's Python environment. Every
input below is synthetic, including the yield and inflation series. The named
COVID dates demonstrate window selection, not actual COVID market performance.

```python
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from validation.portfolio import (
    AnalysisSeries,
    AssetExposure,
    StrategySpec,
    WalkForwardConfig,
    analyze_risk,
    evaluate,
    standard_scenarios,
)

rng = np.random.default_rng(62)
dates = pd.bdate_range("2017-01-01", "2020-06-30")
returns = pd.DataFrame(
    rng.normal([0.0003, 0.0001], [0.012, 0.004], (len(dates), 2)),
    index=dates,
    columns=["SPY", "AGG"],
)
config = WalkForwardConfig(
    start_date="2019-12-31",
    end_date="2020-06-30",
    universe=("SPY", "AGG"),
    training_window=24,
    min_observations=252,
    data_source="synthetic risk-validation example",
    random_seed=62,
    # Supply code_version when archiving a research experiment.
)
runs = {
    name: evaluate(returns, replace(config, strategy=StrategySpec(name)))
    for name in ("equal_weight", "mvo", "erc", "mean_cvar")
}
for method in ("sample", "ledoit-wolf", "oas"):
    runs[f"min_variance_{method}"] = evaluate(
        returns,
        replace(
            config, strategy=StrategySpec("min_variance"), covariance_method=method
        ),
    )
benchmark = AnalysisSeries(
    returns["SPY"],
    source="synthetic SPY benchmark",
    revision_policy="synthetic",
    units="daily_simple_return",
)
months = pd.date_range("2019-12-31", "2020-06-30", freq="ME")
rates = AnalysisSeries(
    pd.Series([0.02, 0.024, 0.018, 0.01, 0.012, 0.014, 0.015], index=months),
    source="synthetic yield levels",
    revision_policy="synthetic",
    units="annual_yield_decimal",
)
inflation = AnalysisSeries(
    pd.Series([0.02, 0.022, 0.021, 0.018, 0.017, 0.019, 0.02], index=months),
    source="synthetic year-over-year inflation",
    revision_policy="synthetic",
    units="yoy_inflation_decimal",
)
# Fixed hypothetical exposures, not estimates of these ETFs' historical duration.
exposures = {
    "SPY": AssetExposure(equity=True, duration=0, spread_duration=0),
    "AGG": AssetExposure(duration=5, spread_duration=3),
}
report = analyze_risk(
    runs,
    benchmark=benchmark,
    rates=rates,
    inflation=inflation,
    baseline="equal_weight",
    exposures=exposures,
    synthetic_scenarios=standard_scenarios(exposures),
)
output = Path("/tmp/wealthpilot-risk-validation")
output.mkdir(exist_ok=True)
(output / "risk-report.json").write_text(report.to_json(), encoding="utf-8")
for name, table in report.tables().items():
    table.to_csv(output / f"{name}.csv", index=False)
for name, run in runs.items():
    (output / f"run-{name}.json").write_text(run.to_json(), encoding="utf-8")
```

JSON retains definitions, input fingerprints, observations, missing counts,
status codes, timestamps and run configuration. CSV tables flatten core results;
archive their JSON companion and the input snapshots. The report includes #61's
turnover/concentration diagnostics without refitting or duplicating its cost
model. To study net performance separately, pass the same runs to `compare_runs`.
All risk and regime returns in this report are gross.

## Decision-time risk snapshots

Validation format **1.3** adds `risk_forecast` to every rebalance record. A failed
allocation has an unavailable forecast. A successful forecast includes the
ordered assets, annual covariance matrix, covariance estimator and regularization
flag, training dates/count, annualized volatility, daily VaR/CVaR and confidence.
The volatility calculation is `sqrt(w.T @ annual_covariance @ w)`.

- MVO, resampled MVO, minimum variance and ERC snapshot the actual production
  optimizer's covariance, including any regularization. `covariance_role` is
  `decision_model`. Resampled MVO reports its final weights against the original
  fitted covariance, consistent with production performance reporting; it does
  not claim that every resampled optimization used an identical matrix.
- Mean-CVaR relies on historical loss scenarios rather than covariance in its LP.
  Its volatility snapshot has `covariance_role="reporting_only"`.
- Equal weight, static/60-40, inverse volatility and custom allocators without a
  supplied snapshot receive a separate `reporting_only` covariance estimate.
  This uses only positive-weight constituents and their joint complete rows
  within the already-sliced decision-time window. It uses the configured
  covariance estimator and minimum observations. An insufficient reporting sample
  does **not** skip or alter an otherwise valid baseline allocation.
  Inverse volatility still chooses weights from each asset's own observations.
- `estimation_observations` in the allocation record describes allocation fitting;
  the same field inside `risk_forecast` describes risk estimation. They can differ.
- A custom `Allocation` may supply `risk_forecast` using this schema and is
  responsible for its contents. Missing/invalid training dates, or dates after
  the decision, cannot establish a usable ex-ante forecast. Older saved runs
  without snapshots are reported as unavailable, not reconstructed using future
  data. Reporting exceptions produce fixed reason codes and do not fail allocation.

For most strategies daily downside estimates reuse production historical
`value_at_risk` and `conditional_var`: interpolated return percentile, then the
mean loss in the inclusive historical tail. For Mean-CVaR, snapshots instead
preserve the **LP threshold and objective**, undoing production's `sqrt(252)`
reporting scale. Its configured `beta` is preserved. These empirical conventions
can differ with finite samples and ties; `downside_method` makes that visible.
Loss is `-daily_return`, so a threshold can be negative in a gain-only history.

## Forecast calibration

`calibrate_risk(runs, CalibrationConfig(...))` compares each saved forecast with
actual daily portfolio returns in **(decision date, next holding end]**. Those
returns include buy-and-hold weight drift. They are not hypothetical constant
weight future returns. Forecasts use constant target historical scenarios, so
weight drift is one source of forecast/outcome difference.

Volatility is annualized with `sqrt(252)` and sample standard deviation (`ddof=1`).
The forecast is an annualized one-day covariance estimate, with no risk term
structure. Realized risk is estimated over the next holding period; its actual
dates, daily count and configured calendar-month horizon are recorded. A longer
forward frozen-portfolio horizon is not implemented. Short windows are noisy.

The error is `realized - predicted`. Summaries contain MAE, RMSE, signed bias,
median absolute error, error mean/median/p95/extrema, predicted/realized ratio
(null at zero realized volatility), and the frequency with which realized
volatility exceeds `material_exceedance_ratio * predicted`. The default ratio
is 1.5. Results stay separate by named candidate and covariance role, with the
estimator attached; sensitivity variants are not pooled into pseudo-independent
extra observations for an estimator.

`CalibrationConfig` defaults to 20 daily observations, three usable periods and
five tail observations. Missing or failed holding windows remain unpaired, with
counts; summaries describe available complete pairs only. They are not a ranking
or evidence of superiority when candidates have different usable periods.
Aggregate precision metrics are null when the period minimum is not met.

Daily VaR is compared with **daily losses**, never a compounded monthly return.
A breach is strictly `loss > VaR`; ties are not breaches. Counts and breach rates
remain observable, but insufficient historical tail observations exclude that
period from pooled downside calibration. Conditional mean loss and its difference
from forecast CVaR require at least five observed breaches by default. Pooled
conditional error weights each period's predicted CVaR by that period's breach
count. The nominal expected breach rate uses the saved confidence. CVaR's LP
objective is not an exact finite-sample strict-exceedance conditional mean; this
comparison is a descriptive diagnostic, not an assertion of finite-sample equality.
No independence tests, confidence intervals or formal VaR model approval are claimed.

## Descriptive market regimes

`classify_regimes` accepts `AnalysisSeries` inputs and produces only
`analysis_regime_label`. It does not expose a signal input to `evaluate` or call
an allocator. Updating these series after a run changes analysis labels, never
its weights. No data loaders or live provider calls are introduced.

Default `RegimeConfig` rules, evaluated separately for each completed holding period:

| Dimension | Rule |
| --- | --- |
| Equity | Compounded benchmark return: positive = bull, negative = bear, zero = flat |
| Volatility | Annualized daily sample volatility: below 10% = low, 10% to below 20% = normal, 20% or higher = high |
| Rates | Latest available level at each boundary; change above +25 bps = rising, below -25 bps = falling, otherwise stable |
| Inflation | Change in year-over-year inflation rate above +0.1 percentage point = inflationary, below -0.1 point = disinflationary, otherwise stable |

Thresholds are fixed/configurable, not quantiles fitted on future history.
Benchmark returns must cover every supplied trading date in the window and have
at least 20 observations by default. Missing benchmark observations produce unknown
labels. Level observations are dated at/before each boundary and cannot be older
than 45 calendar days by default; a missing latest observation is not replaced by
an older valid one. No series or stale values produce an unknown label.

`AnalysisSeries` requires source, units and one of `latest_revised`,
`point_in_time`, `not_revised` or `synthetic`. Units are daily simple returns,
decimal annual yields, or decimal year-over-year inflation, respectively.
Publication-date/vintage alignment is the caller's responsibility. Latest-revised
historical CPI is acceptable **only for these ex-post labels**; its label is not
claimed knowable at decision time, even if its index precedes that date. Snapshot
fingerprints, date ranges, selected macro observation dates, rules and thresholds
are serialized. An inflationary label describes acceleration under this rule,
not a forecast or an absolute definition of high inflation.

`regime_metrics` requires three periods and 60 daily observations by default.
It reports daily mean, arithmetic annualized return, geometric annualization,
volatility, Sharpe/Sortino, downside deviation, daily CVaR, turnover and positive
holding-period frequency. Every row retains daily/period/tail counts, including
empty predefined labels. Failed selected periods suppress that cohort's
performance statistics. Unknown labels are not performance cohorts.

Conditional CAGR compounds the selected daily observations and annualizes their
count; it is **not** a strategy's return over elapsed calendar time. Maximum
drawdown is the worst drawdown within a **contiguous episode** of that label,
starting each episode at capital 1. It never joins separated episodes. Downside
deviation uses a zero target and population denominator; Sortino uses the run's
daily risk-free equivalent, consistent with existing walk-forward metrics.
Turnover reuses #61's drift-aware calculation, excludes initialization and retains
unknown prior weights. CVaR needs the configured minimum tail count. When supplied,
risk calibration is also grouped under the same descriptive labels.

## Historical and synthetic stress

`historical_stress` reuses `src.portfolio.backtest.STRESS_SCENARIOS`:

- COVID: 2020-02-19 through 2020-03-23.
- Rate shock: 2022-01-03 through 2022-10-24.
- GFC: 2008-09-02 through 2009-03-09.

Date bounds include both daily-return dates. A run must cover the whole window;
partial windows, failed holdings and too few observations are flagged. Unlike
the production fixed-allocation replay, these are saved walk-forward strategy
paths, including their scheduled rebalances. Custom `HistoricalScenario` windows
are supported. Choosing event windows is retrospective evaluation, not construction.

Outputs include window return, peak-to-trough drawdown (opening capital included),
peak/trough dates, return difference from an explicitly named baseline, and recovery
after the worst trough if observed. Recovery stops at the first failed/missing
holding window and distinguishes unrecovered/censored results. Event volatility
is compared with the last active forecast strictly before the event. Their different
horizons make this descriptive; annualized volatility is not directly a crash-loss
forecast.

`synthetic_stress` applies scenarios to each saved target without refitting.
`standard_scenarios(exposures)` supplies illustrative, configurable assumptions:

- Equity assets down 30%, other direct returns zero.
- Parallel yield increase of 200 bps, using `-duration * yield_change`.
- Asset volatility multiplied by 1.5.
- Correlations blended 75% of the way toward perfect positive correlation.
- Combined equity -30%, yield +200 bps, credit spread +100 bps, volatility x1.5
  and correlation blend 75%.

Portfolio shock return is the weighted sum of direct returns minus duration and
spread-duration terms. Durations are caller-supplied fixed hypothetical years;
explicit zero is allowed, missing required exposures produce unknown loss.
These are not historical duration estimates. No convexity, carry, FX or factor
model is assumed. An implied asset return below -100% is flagged, not clipped.

Covariance stress uses `(1-a)*Sigma + a*outer(asset_vol, asset_vol)`, followed by
multiplication by the volatility multiplier squared. For `a` in [0,1], this
preserves positive semidefiniteness and converges correlations toward +1 without
changing marginal variances before scaling. Annualized stressed volatility is
reported separately from the instantaneous return shock; no probability or loss
horizon is invented. Scenario definitions and exposures are in the JSON output.
