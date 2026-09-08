# Portfolio robustness and implementation costs

Gross historical return, allocation stability and implementation cost are
separate dimensions of a research result. These tools measure each dimension
without selecting a winner through a combined score. They extend the
[walk-forward evaluator](README.md); they do not introduce another evaluation
loop, change the production optimizer, or model executed trades.

## Offline example

The following is a synthetic correctness example, not a performance claim or a
calibration of realistic trading costs. Run it from the repository root:

```python
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from validation.portfolio import (
    CostConfig,
    SensitivityConfig,
    StrategySpec,
    WalkForwardConfig,
    compare_runs,
    evaluate,
    run_sensitivity,
)

dates = pd.bdate_range("2015-01-01", "2021-06-30")
rng = np.random.default_rng(61)
returns = pd.DataFrame(
    rng.normal([0.0003, 0.0001, 0.0002], [0.01, 0.003, 0.008], (len(dates), 3)),
    index=dates,
    columns=["SPY", "AGG", "GLD"],
)
base = WalkForwardConfig(
    start_date="2021-03-31",
    end_date="2021-06-30",
    universe=("SPY", "AGG", "GLD"),
    training_window=36,
    random_seed=61,
    data_source="deterministic synthetic robustness example",
    risk_free_rate=0.0,
)
specs = [
    StrategySpec("equal_weight"),
    StrategySpec("60_40"),
    StrategySpec("inverse_volatility"),
    StrategySpec("min_variance"),
    StrategySpec("mvo"),
    StrategySpec("erc"),
    StrategySpec("mean_cvar"),
    StrategySpec("resampled_mvo", {"n_simulations": 16}),
]
runs = {spec.name: evaluate(returns, replace(base, strategy=spec)) for spec in specs}
costs = CostConfig(rates_bps=(0, 5, 10, 25, 50), turnover_method="drift")
comparison = compare_runs(runs, costs)
output = Path("/tmp/wealthpilot-robustness")
output.mkdir(exist_ok=True)
(output / "comparison.json").write_text(comparison.to_json(), encoding="utf-8")
comparison.to_dataframe().to_csv(output / "comparison.csv", index=False)

sensitivity = run_sensitivity(
    returns,
    replace(base, strategy=StrategySpec("mvo")),
    SensitivityConfig(
        return_shocks=(-0.02, -0.01, -0.005, 0.005, 0.01, 0.02),
        covariance_methods=("sample", "ledoit-wolf", "oas"),
        training_windows=(24, 36, 60),
        include_expanding=True,
        random_draws=2,
        random_seed=61,
    ),
    costs,
)
(output / "sensitivity.json").write_text(sensitivity.to_json(), encoding="utf-8")
sensitivity.comparison.to_dataframe().to_csv(output / "sensitivity.csv", index=False)
```

`analyze_costs(run, CostConfig(...))` applies new cost scenarios directly to an
existing `ValidationRun`. It never refits a portfolio. Cost and comparison JSON
include the original run, its configuration/provenance, per-decision weights,
turnover and concentration, and each scenario's daily cost/return/NAV series.
The CSV is a summary table and should be archived with the JSON. Sensitivity JSON
also contains the exact scenario definitions, offsets, random seed, skipped
experiments and allocation changes. Undefined values serialize as `null`.

## Turnover and cost convention

One-way turnover at a rebalance is `0.5 * sum(abs(target - pretrade))`, aligning
the union of assets and assigning zero weight to absent holdings. Assets entering
or leaving an eligible universe therefore contribute to turnover.

In the default **drift** mode, pretrade weights come from the preceding holding
window's ending weights. Validation format 1.2 records these as `ending_weights`
when valuation succeeds and terminal wealth is positive. Equal target weights
at consecutive decisions can still imply nonzero turnover because asset values
have drifted. For example, an initial 50/50 portfolio whose first asset gains
21% and whose second asset is flat ends at approximately 54.75/45.25; resetting
to 50/50 has approximately 4.75% one-way turnover.

`turnover_method="target"` explicitly compares consecutive target allocations.
It ignores drift and is available for older saved runs without ending weights.
Drift mode never silently falls back to target mode. Unknown preceding holdings
make turnover unknown; a later successfully valued holding window can restore
the following *local* turnover calculation without restoring cumulative NAV.

Initialization is explicit:

- Default `charge_initial=False`: capital begins in the first target portfolio,
  with initial turnover/cost set to zero. Initialization is excluded from the
  average, median, p95, maximum and full-reallocation event statistics.
- `charge_initial=True`: assume a full initial allocation from cash, with
  one-way turnover 1 and a corresponding initial cost. Include it in statistics.
- This convention applies only to the first scheduled decision. A skipped first
  decision does not create a free initialization at a later successful decision.

Annualized turnover is total observed turnover divided by OOS observation count
/ 252 years, matching the evaluator's annualization. It is withheld when the
gross path or required turnover is incomplete. Other turnover summaries report
their observed and missing counts so partial summaries are not mistaken for
complete experiments. A full-reallocation event means turnover >= `1 - 1e-8`.

For each cost rate, in basis points per unit of **one-way turnover**:

```text
cost fraction = turnover * rate_bps / 10000
net return on first observed holding day = gross daily return - cost fraction
```

The remaining daily returns in that window are unchanged, and net NAV compounds
the resulting net daily series. Cost is debited once, as a fraction of that
day's opening NAV. The rate is not charged separately to both buys and sells;
convert rate assumptions to this one-way convention before comparing results.

This is a first-order proportional-cost overlay using the saved gross target
and drift path. It does not reoptimize after costs, alter relative holdings to
fund fees, or provide a self-financing execution ledger. The subtraction on the
first holding day is the timing convention; it differs from deducting a fee
before that day's return. Nonnegative costs cannot mechanically improve net
return under this convention; they can still change volatility or Sharpe in
either direction, so no monotonic-Sharpe claim is made.

The cost metrics distinguish:

- `cost_fraction_sum`: sum of the modeled debits expressed as fractions of each
  debit day's opening NAV; it is not a compounded portfolio return.
- `cumulative_cost_paid`: sum of those fractions multiplied by each debit day's
  opening net NAV, in units of initial capital.
- `cumulative_cost_drag`: final gross NAV minus final net NAV, also in units of
  initial capital; this includes foregone compounding.

These cumulative measures and net performance metrics are withheld on incomplete
paths. A missing turnover invalidates a positive-cost holding window. At 0 bps,
the cost is zero even if turnover is unknown, preserving the gross return/NAV
path. A cost that would drive a daily return below -100% produces an explicit
`cost_exceeds_capital` failure. Failed or empty gross periods remain gaps; they
are never converted to cash returns or removed before ranking.

## Concentration, stability and ranking

`analyze_weights(run)` reports per-decision maximum weight, effective holdings
`1 / sum(w**2)`, target-to-target distance, and lower/upper-bound fractions. It
also summarizes these measures, per-asset sample standard deviation of target
weights, predicted volatility, covariance conditioning and regularization.

Weight volatility uses successful allocations, aligning the configured universe
with zero for inactive assets. It needs at least two observations. Target
distance never bridges a failed allocation; it measures target instability
separately from drift-aware implementation turnover. A valuation failure does
not invalidate an otherwise successful allocation's concentration measurement.

Bound fractions describe only the current supported 0/1 long-only bounds, with
a configurable tolerance defaulting to `1e-8`. Their denominator is eligible
assets, so an ineligible asset is not counted as a solver hitting its lower
bound. No concentration caps or other unimplemented constraints are inferred.

Comparison rows include gross/net CAGR and Sharpe, cost drag, turnover, realized
volatility/drawdown, concentration/effective holdings, target instability,
predicted volatility, condition/regularization diagnostics and failure counts.
Each metric has its own ranking direction and ties share the minimum rank.
Rankings are within a cost scenario, across the supplied named candidates. There
is **no weighted overall score**. Sensitivity rows additionally report mean and
maximum weight distance from the base run.

Comparisons require the same input fingerprint, configured universe, OOS daily
dates, decision dates, holding/rebalance frequency and risk-free assumption.
Strategies and training assumptions can differ. If any candidate has an
incomplete gross/net path in a cost scenario, rankings for that entire cohort
are withheld. Undefined metrics, such as Sharpe for a flat portfolio, retain
null ranks; other defined metrics remain available.

## Controlled sensitivity experiments

Experiments vary **one factor at a time** and reuse `evaluate()` for every
distinct configuration. They do not perform a Cartesian search for the best
backtest. The base run is reused for identical configurations; cost scenarios
are post-processing, so five rates do not mean five optimizer runs.

Expected-return shocks are annual additive offsets. `0.01` means one percentage
point, not a 1% relative multiplication. Each decision estimates historical means
using its own eligible, complete-case training sample, then supplies the shifted
mean vector through the production optimizer's existing `expected_returns`
argument. The historical observations, covariance inputs, risk-free assumption,
constraints, optimizer seed and OOS return observations stay unchanged.

The default six shocks shift every configured asset by +/-0.5, +/-1 and +/-2
percentage points. Use `shock_assets=("SPY",)` for per-asset deterministic shocks.
Random experiments draw independent Gaussian annual offsets with configurable
standard deviation and seed. One offset vector is fixed before each experiment
and reused at every decision, making this a sensitivity to persistent input
error, not a simulation of daily forecast noise. The perturbation seed is
separate from the unchanged optimizer seed. Exact offset vectors are serialized.

You can also directly evaluate a chosen vector:

```python
shifted = replace(
    base,
    strategy=StrategySpec("mvo", expected_return_shifts={"SPY": 0.01, "AGG": -0.005}),
)
shifted_run = evaluate(returns, shifted)
```

Offsets are applied only when an asset becomes eligible, with no use of future
availability. Existing offsets in a base strategy are retained and scenario
offsets are added to them.

Applicability is explicit:

| Experiment | Supported allocations |
| --- | --- |
| Expected returns | MVO, resampled MVO, and Minimum Variance when a target-return constraint is supplied |
| Covariance estimator | Minimum Variance, MVO, resampled MVO and ERC |
| Training window | All built-in strategies, including baseline eligibility/history effects |

Unconstrained Minimum Variance and Mean-CVaR do not depend on expected means for
allocation. ERC and the simple baselines do not either. With a target-return
constraint, the current production Mean-CVaR LP uses the mean of historical
scenarios directly, ignoring the constructor's expected-return override in that
constraint. Its independent mean-shock experiment is therefore explicitly
unsupported; changing the historical scenarios would also change the loss
distribution and would not isolate mean sensitivity. Mean-CVaR also uses those
scenarios rather than the chosen covariance matrix for optimization; covariance
only affects its reporting, so an allocation covariance experiment is marked
inapplicable. Unsupported experiments are recorded as skipped, not presented
as zero sensitivity. Custom allocators can use costs/weight comparisons, but
automatic perturbation adapters currently support built-in strategies only.

Covariance alternatives use exactly the same training windows and point-in-time
eligible universe at each decision. Window alternatives retain the same OOS
protocol but may change asset eligibility; those differences are counted in the
output rather than forcing an intersection using future availability. As in the
base evaluator, lookback length is a maximum horizon: `min_observations` and
`min_coverage` control admission and can admit a shorter actual history. Inspect
the recorded training dates/counts when interpreting a 24/36/60-month comparison.

`compare_allocations(base, variant)` records allocation distance, signed changes
by asset, per-asset mean/maximum absolute changes, eligibility differences, and
variant failures. A concentration transition means maximum weight crosses the
explicit threshold (default 80%) from below; it is a descriptive threshold, not
an inferred suitability rule. Failed allocation pairs have unknown distance and
are counted, not assigned zero. Condition numbers, regularization, statuses and
failure reasons support inspection of infeasible or unstable scenarios.

These results cannot correct survivorship bias, revised data or missing delisting
returns in the supplied snapshot. Tax lots, taxes, per-security spreads, market
impact, calibrated liquidity limits, regimes, CME vintages, retirement validation
and UI integration remain outside this research layer.

```bash
python -m pytest -q tests/test_walk_forward.py tests/test_portfolio_robustness.py
```
