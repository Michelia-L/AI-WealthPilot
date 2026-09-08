# Walk-forward portfolio evaluation

This offline research engine refits a portfolio method at each historical
decision date and evaluates its allocation on subsequent daily returns. It is
separate from `src/portfolio/backtest.py`, which applies a supplied fixed target
allocation to history with monthly rebalancing. That historical backtest does
not establish whether the method that selected those targets works out of sample.

The evaluator accepts a supplied data snapshot and never fetches market data,
current CME estimates, LLM outputs, or a current risk-free rate. It does not
establish that any optimizer is superior, and synthetic results are correctness
examples rather than historical performance evidence.

## Runnable offline example

Run from the repository root with the project's Python dependencies installed:

```python
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from validation.portfolio import StrategySpec, WalkForwardConfig, evaluate

rng = np.random.default_rng(60)
dates = pd.bdate_range("2017-01-01", "2021-12-31")
returns = pd.DataFrame(
    rng.normal([0.0003, 0.0001, 0.0002], [0.01, 0.003, 0.008], (len(dates), 3)),
    index=dates,
    columns=["SPY", "AGG", "GLD"],
)
config = WalkForwardConfig(
    start_date="2019-12-31",  # first decision; first OOS return is in January
    end_date="2021-12-31",  # inclusive evaluation end
    universe=("SPY", "AGG", "GLD"),
    training_window=36,  # calendar months
    holding_window=1,
    rebalance_frequency=1,
    risk_free_rate=0.02,  # constant annual research assumption
    risk_free_rate_source="fixed 2% scenario assumption, not a historical series",
    random_seed=60,
    data_source="deterministic synthetic example",
    # Set code_version to the checked-out commit when archiving experiments.
)

strategies = [
    StrategySpec("equal_weight"),
    StrategySpec("60_40"),
    StrategySpec("static", {"weights": {"SPY": 0.4, "AGG": 0.4, "GLD": 0.2}}),
    StrategySpec("inverse_volatility"),
    StrategySpec("min_variance"),
    StrategySpec("mvo"),
    StrategySpec("erc"),
]
output = Path("/tmp/wealthpilot-validation")
output.mkdir(exist_ok=True)
for strategy in strategies:
    run = evaluate(returns, replace(config, strategy=strategy))
    (output / f"{strategy.name}.json").write_text(run.to_json(), encoding="utf-8")
    pd.concat([run.returns, run.nav], axis=1).to_csv(output / f"{strategy.name}.csv")
    print(strategy.name, run.metrics)
```

JSON is the complete archival format, including configuration, diagnostics,
weights, and provenance. The CSV above is only the return/NAV table; archive its
JSON companion. `to_dict()` produces the same JSON-compatible structure. Unknown
returns, undefined ratios and infinite condition numbers serialize as `null`,
with status/reason and regularization diagnostics explaining their context.

## Time and input contract

- Input is a numeric DataFrame of **daily simple returns**, not prices or log
  returns. Columns are assets and the index must be sorted, unique, normalized,
  timezone-naive dates. The caller supplies the full intended trading calendar.
  A date absent from all rows cannot be distinguished from a market holiday;
  insert explicit missing rows when observations are unavailable. The engine
  cannot verify daily frequency or the provenance of supplied returns.
- `start_date` is a calendar month end. The rolling training interval at decision
  `t` is `(t - training_window calendar month ends, t]`. For a 36-month window at
  2019-12-31, the first admissible observation is 2017-01-01. Expanding mode fixes
  that initial lower boundary and extends the upper boundary on each decision.
- Holding observations are strictly after `t` and through the next holding end,
  inclusive. `end_date` may truncate the final holding window. Decisions use the
  calendar, including month ends that fall on non-trading days; training then
  ends at the last available observation on or before that date.
- The input snapshot must reach the requested final holding end. If it stops
  earlier, that window fails with `incomplete_holding_window`, even when both
  dates fall in the same month. When the snapshot ends on the last trading day
  before a holiday/month end, set `end_date` to that observed date explicitly.
  The evaluator does not guess exchange holidays or silently shorten a run.
- Window sizes and rebalance frequency are positive integer month counts. v1
  requires `holding_window == rebalance_frequency`; monthly and quarterly runs
  are supported. Overlapping cohorts, gaps between planned holdings, daily
  rebalancing and independent holding/rebalance frequencies are rejected.
- Targets are applied at the decision close, with no execution delay or costs.
  Between decisions, asset quantities are held fixed and weights drift. For
  initial weights `w`, window wealth at day `d` is
  `sum(w_i * product(1 + r_i, through d))`. Daily OOS returns are changes in that
  wealth; the next decision resets targets. NAV starts from implicit capital 1
  immediately before the first OOS return. This is a frictionless research
  execution assumption, not a trade simulator.

## Eligibility, missing data and failures

Eligibility is calculated **after slicing the training window**, independently
at each decision. It never depends on future asset availability.

| Condition | Behavior |
| --- | --- |
| Asset has fewer than `min_observations` valid returns | Exclude with `insufficient_history` |
| Asset has valid returns on less than `min_coverage` of supplied training dates | Exclude with `sparse_history` |
| Assets enter later | Admit only once their historical count and coverage pass |
| No eligible assets | Skip the decision with `no_eligible_assets` |
| Mixed calendars / missing training values | Retain training dates and mask invalid values as NaN; each strategy selects its fitting sample without filling |
| Optimizer has fewer than `min_observations` joint complete rows | Skip with `insufficient_joint_history` before constructing the production optimizer; never substitute pairwise covariance |
| Missing, infinite or below -100% return for an active holding | Mark the entire holding window unknown, preserving the chosen weights |
| Missing return for an asset with zero target weight | Does not affect holding valuation |
| No holding observations | Record `no_holding_observations` |
| Static/60-40 constituent unavailable at decision | Fail with `benchmark_assets_unavailable`; never redistribute its weight |
| Inverse-volatility has zero, nonfinite or negligible volatility | Fail with `invalid_or_zero_volatility`; never silently substitute equal weights |
| Invalid weights, optimizer exception or unsuccessful result | Record failure and continue fitting the next decision |
| Singular / ill-conditioned covariance | Reuse production regularization and report condition number and regularization flag |
| One eligible asset | Evaluate normally with a fully invested single-asset allocation when the strategy permits it |

Defaults are `min_observations=252` and `min_coverage=0.9`. A training window is a
maximum lookback, not a requirement that the asset existed throughout all 36
months. A shorter history is admitted when both thresholds pass. Tighten these
thresholds for experiments that require more history. Static allocations check
individual eligibility for their nonzero constituents; unrelated assets cannot
prevent allocation through a joint-sample requirement.

After point-in-time eligibility, fitting requirements depend on the strategy:

| Strategy | Fitting sample |
| --- | --- |
| Equal Weight | No estimation; allocate over individually eligible assets |
| Static / 60-40 | No estimation; require only the specified nonzero constituents to be individually eligible |
| Inverse Volatility | Estimate each asset's sample standard deviation from its own valid historical observations |
| Production optimizer adapters | Drop incomplete rows across participating eligible assets and require at least `min_observations` joint rows |
| Custom allocator | Receive eligible asset columns with NaNs retained; choose and validate its own fitting sample |

Per-decision `training_start`, `training_end` and `training_window_observations`
describe the supplied historical window, including dates with missing values.
`estimation_observations` is zero for successful allocation by a baseline that
needs no estimation, a per-asset count dictionary for inverse volatility, and
the joint row count for optimizer results (including insufficient-joint-history
skips). It is `null` when no count is reported, such as an unhandled allocation
exception or a custom allocator using the default. Custom allocators can set
`Allocation.estimation_observations` to report an integer or per-asset counts.
Validation format 1.1 replaces the ambiguous `training_observations` field with
these separate counts.

Failures produce unknown returns, **not cash returns, previous weights, or a
fallback optimizer**. Later local window returns remain available, but cumulative
NAV stays unknown after the first failed/skipped window. Whole-run return/risk
metrics are withheld whenever a window is incomplete, including a completely
absent month. Do not drop failed periods to rank strategies: this selects on
evaluation success. Counts distinguish allocation failure from holding-data
failure, and weights survive successful allocation even if valuation fails.

## Strategies and extension boundary

| Name | Implementation / parameters |
| --- | --- |
| `equal_weight` | Exact `1/N` over eligible assets |
| `60_40` | Static 60% SPY / 40% AGG; both must be eligible |
| `static` | Required `weights` dictionary, finite nonnegative weights summing to 1; no automatic normalization |
| `inverse_volatility` | Normalized inverse sample standard deviation |
| `min_variance` | `PortfolioOptimizer.minimize_volatility`; optional annual `target_return` |
| `mvo` | `PortfolioOptimizer.maximize_sharpe` |
| `erc` | `PortfolioOptimizer.risk_parity` |
| `mean_cvar` | `PortfolioOptimizer.minimize_cvar`; optional `beta`, annual `target_return` |
| `resampled_mvo` | `PortfolioOptimizer.resampled_maximize_sharpe`; optional positive `n_simulations` |

All built-in production adapters use the selected covariance estimator (`sample`,
`ledoit-wolf`, or `oas`), historical mean returns, and the configured constant
annual risk-free rate. Baselines do not use a covariance estimator. v1 supports
fully invested long-only portfolios; unsupported constraints and estimators are
rejected. It does not load today's CME, views or market capitalizations into
historical optimizations. Black-Litterman needs an adapter with historical view
and prior vintages and is not a built-in strategy yet.

A custom object implements the shared contract:

```python
from validation.portfolio import Allocation


class MyStrategy:
    def allocate(self, history, as_of, config):
        # history is a private copy with dates <= as_of and eligible columns.
        # Missing/invalid returns are NaN. Choose and validate a fitting sample.
        # Reuse a production model here; auxiliary inputs must be vintage-safe.
        return Allocation(weights={history.columns[0]: 1.0}, diagnostics={})


custom_config = replace(config, strategy=StrategySpec("custom", {"name": "example"}))
run = evaluate(returns, custom_config, strategy=MyStrategy())
```

The engine limits supplied history; it cannot sandbox arbitrary Python code.
Custom allocators must not close over future data, fetch current information, or
use hindsight-selected inputs. Serialize their parameters in `StrategySpec` and
record their code version. Diagnostics/configuration must contain research
parameters only, never credentials or private client data. Only fixed codes
from `SAFE_ALLOCATION_REASONS` may be serialized from an `AllocationError`.
Unrecognized messages become `allocation_error`, and other exceptions become
`allocation_exception`; exception string representations are never serialized.
Custom diagnostics and reported sample counts remain the adapter's responsibility.

## Metrics and reproducibility

For complete runs, metrics include total return, CAGR, annualized sample
volatility, Sharpe, Sortino, maximum drawdown and best/worst daily return.
CAGR uses observation count / 252 years, consistent with the production
optimizer's daily annualization. Sharpe uses mean daily excess return divided by
daily sample volatility, scaled by sqrt(252). The constant annual risk-free rate
is compounded to a daily rate. Sortino uses the root mean squared negative
excess return over **all** observations. Zero denominators return `null`.
Drawdown includes initial capital, so an initial loss is counted.

Provenance includes validation version, UTC run timestamp, optional caller-supplied
code version, complete configuration, allocator class, input-data fingerprint
and date bounds, numerical library versions and policy assumptions. Each
production optimizer is reconstructed per decision using the same explicit
seed. Repeated runs on the same input and numerical environment reproduce
weights/returns; run timestamps differ and floating-point solvers may differ
across platforms. The fingerprint describes the full supplied snapshot, so
changing future rows changes provenance even though earlier allocations stay
unchanged.

The engine prevents estimator access to future rows; it cannot repair a
survivorship-biased universe, revised historical data, missing delisting returns,
or other errors in the supplied snapshot. Weight history is retained for later
turnover and cost analysis. Transaction costs, robustness grids, regimes, CME
vintages, retirement validation and UI integration are outside this module.

Run the deterministic tests with:

```bash
python -m pytest -q tests/test_walk_forward.py
```
