# Retirement model validation

`validation.retirement` is an offline research interface for asking how a
retirement plan changes under alternative return processes, spending rules and
assumptions. It has no provider, API or UI integration. Outputs are conditional
model results, not guaranteed probabilities of real-world success.

All engines use the production accumulation calculator and the shared
`src.portfolio.retirement_paths.distribution_from_growth` cash-flow rules.
The production GBM, default 0.7 retirement shift and public response structure
are retained. Validation adds supplied annual returns and spending diagnostics;
it does not introduce a second retirement accounting implementation.

## Offline example

Run from the repository root. This small synthetic example illustrates the
interface; it is not historical performance or a calibration of any portfolio.
No files are written until the explicit export calls.

```python
from pathlib import Path

import numpy as np
import pandas as pd

from validation.retirement import (
    EngineConfig,
    HistoricalReturns,
    RetirementScenario,
    compare_models,
    convergence,
    parameter_grid,
    run_retirement,
    sequence_experiment,
    stability_table,
    standard_sensitivities,
    stress_comparison,
)

scenario = RetirementScenario(
    current_age=55,
    retirement_age=65,
    life_expectancy=90,
    current_savings=800_000,
    annual_savings=40_000,
    desired_annual_income=80_000,
    base_currency="CNY",
    expected_return=0.06,
    volatility=0.15,
    inflation_rate=0.025,
    distribution_inflation_rate=0.03,
    n_simulations=1000,
    seed=42,
    code_version="replace-with-the-commit-used",
)
history = HistoricalReturns(
    dates=tuple(pd.date_range("2000-01-31", periods=240, freq="ME").date),
    returns=tuple(np.tile([-0.08, -0.02, 0.01, 0.02, 0.04, 0.07], 40)),
    frequency="monthly",
    source="deterministic synthetic fixture",
    portfolio_mapping="synthetic whole-portfolio nominal total returns",
    currency="CNY",
    fx_treatment="already expressed in CNY",
    sample_kind="synthetic",
)

# Six runs: GBM / IID / six-month block bootstrap, each fixed / guardrails.
comparison = compare_models(scenario, history, block_length=6)
print(comparison.tables()["comparison"])

# Explicitly control marginal log moments to isolate other model differences.
matched = compare_models(
    scenario, history, block_length=6, bootstrap_mode="matched_gbm_moments"
)

# One engine and one scenario, with all metadata retained.
run = run_retirement(
    scenario, EngineConfig(engine="block_bootstrap", block_length=12), history=history
)

# Small customizable Cartesian grid; same seed/draws for equal-sized runs.
grid = parameter_grid(
    scenario,
    {"expected_return": (0.04, 0.06, 0.08), "volatility": (0.12, 0.15, 0.18)},
)
print(grid.metadata["return_sensitivity"])

# Full default GBM suite: mu/vol, retirement shift, both inflation rates,
# standard/elderly inflation presets, and planning horizons.
sensitivities = standard_sensitivities(scenario)
stresses = stress_comparison(scenario)

# Defaults: 1k/5k/10k/25k paths and seeds 7/42/123. Small example here.
sampling = convergence(scenario, counts=(500, 1000), seeds=(7, 42, 123))
print(stability_table(sampling))

output = Path("/tmp/wealthpilot-retirement-validation")
output.mkdir(parents=True, exist_ok=True)
(output / "comparison.json").write_text(comparison.to_json(), encoding="utf-8")
(output / "matched.json").write_text(matched.to_json(), encoding="utf-8")
(output / "run.json").write_text(run.to_json(include_paths=True), encoding="utf-8")
(output / "scenario.json").write_text(
    scenario.model_dump_json(indent=2), encoding="utf-8"
)
for name, report in {
    "grid": grid,
    "stresses": stresses,
    "sampling": sampling,
    **sensitivities,
}.items():
    (output / f"{name}.json").write_text(report.to_json(), encoding="utf-8")
for name, table in comparison.tables().items():
    table.to_csv(output / f"{name}.csv", index=False)
for name, table in run.tables().items():
    table.to_csv(output / f"run-{name}.csv", index=False)
stability_table(sampling).to_csv(output / "convergence.csv", index=False)
```

Each run serializes the complete scenario, effective inflation, engine, actual
historical dates **and values**, source, portfolio/FX mapping, sample hash, block
length, seed and phase seeds, model/code version, Python/NumPy versions, stress
overlays and hashes of the annual gross returns used. Supplied deterministic
paths also retain their original gross-return arrays. This makes replay possible
without a live provider. Archives contain monetary assumptions: keep real-client
exports private; do not commit them as fixtures. Arbitrary provider/configuration
metadata bags are not accepted by the typed inputs.

`code_version` must be supplied by the caller; it is not inferred from Git.
`AssumptionSource(source=..., cme_vintage_id=...)` optionally links assumptions to
an archived [CME vintage](../cme/README.md). No CME data is fetched. A sensitivity
run retains this reference and its actual changed parameters; it does not claim
that the modified parameters were forecasts in that vintage.

## Cash flows and the existing GBM baseline

- Annual steps; portfolio returns occur first, followed by a nominal end-of-year
  contribution during accumulation or withdrawal during retirement.
- Annual savings stay constant in nominal money. They are not inflation-indexed.
- GBM gross returns are `exp(mu - sigma**2 / 2 + sigma * Z)`, with independent
  normal shocks. `mu` is the production drift parameter: expected annual simple
  return is `exp(mu) - 1`, not exactly `mu`. There are no regimes, stochastic
  volatility or separately calibrated fat tails.
- Distribution uses `mu * return_multiplier` and
  `sigma * volatility_multiplier`, each defaulting to 0.7. These are heuristics,
  not an inferred asset allocation or a return series for a different portfolio.
- A target income in today's money becomes
  `income * (1 + accumulation_inflation)**accumulation_years
  * (1 + distribution_inflation)**retirement_year` under fixed spending.
  The first retirement year includes one distribution inflation step.
- Guardrails retain the existing production convention: the initial withdrawal
  anchor includes the first distribution inflation step; the first tentative
  withdrawal is inflated **again**. Consequently fixed and guardrails do not
  start with identical real spending when inflation is nonzero. This behavior
  is explicitly regression-tested; the validation does not silently correct it.
- Guardrail triggers compare tentative withdrawal / **pre-return** wealth with
  the initial withdrawal rate times `1 +/- guardrail_band`. Each triggered rule
  cuts or raises the tentative amount by `guardrail_adjust` (default 10%). Future
  tentative spending inherits that adjustment and inflation. It is a simplified
  rule, not a full implementation of every Guyton–Klinger decision rule.
- Wealth is floored at zero. Actual delivered withdrawals are capped by available
  post-return wealth; requested spending can continue after depletion but does
  not count as delivered spending or an active guardrail adjustment.

At default multipliers the harness reproduces production GBM terminal paths and
survival on identical inputs/seeds. The shared distribution refactor also retains
the old production paths. First-year guardrail timing is a known model convention
to assess separately if the production spending rules change.

## Bootstrap frequency, dependence and matching

Supply a **single whole-portfolio nominal total-return series** with explicit
allocation/rebalancing/FX mapping. There is no automatic asset weighting or FX
conversion; the sample currency must match scenario cash flows. Monthly inputs
must have exactly one observation per consecutive month; annual inputs one per
consecutive calendar year. Dates represent supplied observation periods, not
decision-time availability. No missing periods are filled or dropped. Monthly
returns are compounded in groups of twelve before the annual cash-flow step;
withdrawals therefore still happen annually, not monthly.

IID samples individual observations with replacement. The moving-block bootstrap
samples uniform starts over full contiguous blocks **without circular wrapping**,
concatenates blocks and truncates the final block at the horizon. Edge observations
have lower inclusion weights than interior observations. Default block length is
6 **source periods**: use 3/6/12 for monthly data, or explicitly choose (for example)
2/3 years for annual data. Blocks cannot exceed the supplied sample length.
Accumulation and distribution use independent phase draws; blocks do not span
the retirement transition. This preserves local sample dependence within blocks,
not all long-run serial structure.

Both modes use annualized empirical log-return sample standard deviation (`ddof=1`).
Returns must exceed -100% because log-moment mapping is required. A deterministic
supplied path or stress can contain an exact -100% loss.

| Mode | Accumulation | Distribution |
| --- | --- | --- |
| `empirical` (default) | Resamples the supplied returns directly | Applies the explicit return/volatility multipliers to empirical log moments |
| `matched_gbm_moments` | Centers/scales sample log returns to the scenario's GBM log moments | Centers/scales to the scenario's shifted GBM log moments |

For `f` observations per year and empirical log mean `m`, std `s`, the empirical
annual equivalent is `sigma_h = s * sqrt(f)` and
`mu_h = m * f + sigma_h**2 / 2`. Distribution log returns become
`(mu_h * return_multiplier - (sigma_h * volatility_multiplier)**2 / 2) / f
+ (log_return - m) * volatility_multiplier`. Identity multipliers preserve the
original sample. The empirical mode ignores scenario mu/sigma, which is recorded
in metadata; a mu/sigma grid rejects this mode rather than reporting meaningless
flat sensitivity.

Matched mode uses scenario mu/sigma instead of these empirical moments. It retains
the empirical standardized log-return shape and sampled block order. Matching
marginal moments does **not** force block-compounded annual moments to equal GBM
moments when observations are dependent. A constant sample cannot be rescaled to
positive volatility and is rejected. Model-specific diagnostics include original
and mapped moments and hashes of sampled indices.

Use the empirical comparison to assess both distribution and estimation changes;
use matched mode to control marginal assumptions more closely. Neither establishes
that the future will resemble the supplied history. The sample is caller-chosen,
so historical selection, survivorship and revision bias remain research concerns.

## Sequence-of-returns fixture

The same observations `[-0.5, 0.5, 0.1, 0.1]` have the same compounded return.
Starting with 100, withdrawing 20 at each year end and using zero inflation gives:

| Loss placement | Annual returns | Terminal wealth | Depletion year | Delivered withdrawals |
| --- | --- | ---: | ---: | ---: |
| Early | -50%, +50%, +10%, +10% | 0 | 4 | 68.25 |
| Middle | +50%, -50%, +10%, +10% | 12.45 | none | 80 |
| Late | +50%, +10%, +10%, -50% | 37.65 | none | 80 |

Without withdrawals, all three terminate at 90.75 (up to floating-point rounding).
Contributions during accumulation can also create order effects; they are not
present in this fixture.

```python
fixture = scenario.changed(
    current_age=65,
    retirement_age=65,
    life_expectancy=69,
    current_savings=100,
    annual_savings=0,
    desired_annual_income=20,
    inflation_rate=0,
    distribution_inflation_rate=0,
)
sequence = sequence_experiment(fixture, (-0.5, 0.5, 0.1, 0.1))
print(sequence.tables()["comparison"])
```

The function clusters negatives early, in the middle or late, retaining their
relative order and the order of nonnegative observations. It forces one path per
case and reports a deterministic survival indicator, with no MC sampling error.
For nonzero accumulation horizons, supply `accumulation_returns` explicitly.
`evaluate_paths` accepts arbitrary annual **gross-return matrices** to construct
other hand-built experiments; those matrices are used as supplied, without
applying another retirement multiplier.

## Sensitivity, spending tradeoffs and shocks

`standard_sensitivities` includes:

- Mu at base ±0/1/2 percentage points crossed with volatility ×0.75/1/1.25.
- Joint retirement return/volatility multipliers 0.50/0.70/0.85/1.00. Separate
  multipliers can be explored with `parameter_grid`.
- Accumulation inflation crossed with distribution inflation at 2/3/4/5%.
- Generic versus the production `elderly` CPI-E-style additive inflation preset.
  This is a stylized assumption, not a retrieved CPI-E series.
- Planning end ages 85/90/95/100 where greater than retirement age, plus the base
  horizon. This is longevity-horizon sensitivity, not actuarial mortality modeling.

Grid reports include finite differences in success probability per **unit** change
in expected return, holding other axes fixed. Multiply this derivative by 0.01 to
express a one-percentage-point return change. Grid exports expose probability,
median/P5/P25 wealth, depletion and spending; no parameter is auto-selected.

Fixed/guardrail comparisons use identical returns within each engine. Examine
survival **together with** delivered real spending, shortfalls, cuts and increases.
Guardrails can improve survival by spending less and can also spend more after
good returns. There is no general guarantee of better survival on every path.

Standard stresses replace whole-portfolio simple returns with -30% in the first
retirement year, 0% for up to the first ten retirement years, 6% inflation for up
to five years, or the crash and inflation together. Later draws stay unchanged.
The zero-return decade is poor relative to positive expected returns; none of
these shocks is a calibrated equity exposure or event probability. Custom
`RetirementStress` prefixes allow other return/inflation values. After an inflation
shock, subsequent annual rates revert to base but the price-level increase
persists. Stress-adjusted inflation also deflates spending to today's money.

## Metrics and Monte Carlo uncertainty

Success/survival means wealth is **strictly positive at retirement and every
retirement year end**. Exactly funding the final withdrawal and ending at zero
counts as depleted even if the spending target was met. Depletion year zero means
no wealth at retirement. Median depletion age/year is conditional on depleted
paths and is null if none deplete; diagnostics retain the complete year histogram.

Nominal withdrawals mean actual cash delivered, capped by available wealth. Real
spending divides each year's cash by cumulative accumulation/distribution
inflation. Shortfall is the positive difference from the original real target;
increases do not cancel shortfalls in other years. Requested-policy reductions
from target are also reported separately from shortages caused by exhaustion.
Cut amounts measure the reduction at each trigger relative to that year's
pre-adjustment tentative amount; cumulative cut amounts do not double-count the
entire future effect as a new trigger. Cuts/increases are counted only while the
path has positive pre-return wealth.

The spending-floor fraction defaults to 80% of target and must be delivered in
**every** retirement year for a path to qualify. Average real spending per path
includes depleted years with zero delivered spending. Annual tables show the
target, requested/delivered means, real-spending P5 and adjustment frequencies.
Per-path tables retain terminal wealth, spending, shortfalls and depletion.

Stochastic runs report `sqrt(p * (1 - p) / N)`, an approximate one-standard-error
binomial sampling error conditional on the model and, for bootstrap, the fixed
historical sample. It excludes uncertainty in that sample, parameter estimation
and model choice. The plug-in error is zero at p=0 or p=1; this does not establish
certainty. Deterministic path fixtures report null instead.

`convergence` repeats complete runs at each count/seed, reporting mean, sample
standard deviation and min/max across seeds for probability, median terminal and
P5 terminal wealth. It does not pick a seed or declare automatic convergence.
GBM uses production year-major random draws: equal seeds and equal path counts
preserve earlier years when horizons extend. Counts are **not** nested samples;
bootstrap common draws are guaranteed only for identical phase shapes. Engine
comparisons use different sampling mechanisms, so identical seed values do not
make GBM and bootstrap draws paired.

Tax, pension, healthcare, mortality and other household liability models are
outside this package. Increasing the path count can reduce Monte Carlo noise;
it cannot resolve the spread caused by model assumptions.
