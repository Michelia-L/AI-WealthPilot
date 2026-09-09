# CME vintages and forecast calibration

This package archives Capital Market Expectations independently of the operational
cache and evaluates saved forecasts against later outcomes. It accepts supplied
reports, dated source evidence and daily return snapshots. It never calls
`compute_cme`, implied-volatility providers, forward-return providers or the live
cache to fill historical gaps.

CME remains an assumption/forecast framework. These tools do not establish that
its forecasts are accurate, predict macro conditions or guarantee returns. Enough
actual archived vintages must accumulate before calibration can support empirical
claims. Parameter experiments do not tune production defaults automatically.

## Runnable offline example

Run from the repository root with the project's Python environment. The following
uses **synthetic reconstructions**, including invented forward assumptions. Its
historical dates are a fixture, not evidence of forecasts actually issued then.
All three horizons are mature within the supplied synthetic data coverage.

```python
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.portfolio.cme_blending import blend_assumption
from src.portfolio.cme_models import AssetClassCME, CMEReport
from validation.cme import (
    CMEVintage,
    NumericInput,
    RealizedPanel,
    SourceRecord,
    VintageStore,
    calibrate,
    evaluate_blending,
)

rng = np.random.default_rng(63)
dates = pd.bdate_range("2014-01-01", "2025-12-31")
keys = ("equity", "bonds", "gold")
proxies = dict(zip(keys, ("SPY", "AGG", "GLD"), strict=True))
returns = pd.DataFrame(
    rng.normal([0.0003, 0.0001, 0.0002], [0.012, 0.004, 0.008], (len(dates), 3)),
    index=dates,
    columns=keys,
)
output = Path("/tmp/wealthpilot-cme-validation")
store = VintageStore(output / "vintages")
# Explicit reconstruction time, distinct from the historical forecast date.
generated = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
vintages = []
for year in (2017, 2018, 2019):
    as_of = pd.Timestamp(f"{year}-12-31")
    history = returns.loc[
        (returns.index > as_of - pd.DateOffset(years=3)) & (returns.index <= as_of)
    ]
    assets = []
    for key, forward, implied in zip(
        keys, (0.07, 0.03, 0.025), (0.20, 0.08, 0.15), strict=True
    ):
        mu = float(history[key].mean() * 252)
        vol = float(history[key].std(ddof=1) * np.sqrt(252))
        assets.append(
            AssetClassCME(
                name=key,
                key=key,
                ticker=proxies[key],
                expected_return=blend_assumption(mu, forward, 0.5),
                historical_return=mu,
                forward_return=forward,
                volatility=vol,
                implied_volatility=implied,
                blended_volatility=blend_assumption(vol, implied, 0.5),
                # Unused descriptive fields are fixture placeholders, not estimates.
                sharpe_ratio=0,
                max_drawdown=0,
                var_95=0,
                cvar_95=0,
                data_points=len(history),
            )
        )
    report = CMEReport(
        as_of_date=history.index.max().date().isoformat(),
        data_lookback_years=3,
        risk_free_rate=0.02,
        risk_free_rate_source="synthetic fixed assumption",
        inflation_assumption=0.025,
        asset_classes=assets,
        correlation_matrix=history.corr().to_dict(),
    )
    available = as_of.tz_localize("UTC").to_pydatetime()
    sources = tuple(
        SourceRecord(
            component=component,
            provider="synthetic fixture",
            proxy="synthetic panel/assumptions",
            observed_at=available,
            available_at=available,
            retrieved_at=generated,
            quality="fresh",
            revision_policy="fixed_assumption",
            inputs=(NumericInput(name="fixture_only", value=1, units="indicator"),),
        )
        for component in (
            "history",
            "implied",
            "forward",
            "correlation",
            "risk_free",
            "inflation",
            "fx",
        )
    )
    vintage = CMEVintage.from_report(
        report,
        as_of=as_of.date(),
        generated_at=generated,
        vintage_type="reconstructed",
        model_version="synthetic-linear-v1",
        code_version="synthetic-example",
        base_currency="CNY",
        fx_treatment="synthetic CNY total-return panel",
        cache_status="fresh",
        sources=sources,
    )
    assert not vintage.strict_issues()
    vintages.append(store.load(store.save(vintage)))

panel = RealizedPanel(
    returns,
    proxies,
    "CNY",
    "synthetic CNY total-return panel",
    source="deterministic synthetic daily returns",
    revision_policy="synthetic",
    coverage_start="2014-01-01",
    coverage_end="2025-12-31",
)
calibration = calibrate(vintages, panel, evaluation_date="2025-12-31")
blending = evaluate_blending(vintages, panel, evaluation_date="2025-12-31")
for name, result in (("calibration", calibration), ("blending", blending)):
    (output / f"{name}.json").write_text(result.to_json(), encoding="utf-8")
    for table_name, table in result.tables().items():
        table.to_csv(output / f"{name}-{table_name}.csv", index=False)
```

Archive JSON, input snapshots and the source evidence referenced by their hashes.
CSV tables are for analysis and need their JSON metadata companion. The archive
itself is the place to find the full immutable forecast inputs and outputs.

## Capturing actual reports

Pass an actual `CMEReport` and the `cache_status` returned with it to
`CMEVintage.from_report`. Supply the actual generation/capture timestamp, model
and code identifiers, currency/FX policy and available `SourceRecord` evidence.
Then explicitly call `VintageStore.save`. The live API/cache does not automatically
write into this archive.

`as_of` is the **forecast decision date**, in UTC. `report_as_of` separately
preserves `CMEReport.as_of_date`, which the current engine sets to the last price
date. A forecast computed on Monday using Friday prices is Monday's forecast.
Capturing a cached/stale report today does not create evidence that the same
forecast was captured on an earlier date. Original cache timestamps should only
be supplied when supported by an actual preserved historical record.

The adapter copies the report's actual parameters, assets and outputs, rather
than current request defaults. This matters when stale/fallback output was
produced under different assumptions. Asset keys must be present and unique;
proxy tickers and display names are both retained. Correlation matrix order is
the asset tuple order. Missing entries can be null; nonfinite numbers, malformed
matrices and negative volatility are rejected.

The vintage preserves historical/forward return components, historical/implied
volatility components, blended forecasts, correlation matrix, risk-free source,
inflation, lookback, tau/omega, currency policy and versions. Selected numeric
building blocks (e.g. dividend yield, growth assumption, MOVE quote, conversion
scale and duration) can be saved in `SourceRecord.inputs`. A source hash can
reference a separately archived history or provider snapshot. Do not pass raw
provider responses, API keys, user profiles or arbitrary cache metadata; the
schema rejects undeclared fields and has no raw-response metadata bag.

The current operational report does **not** expose all source observation,
publication and retrieval timestamps. The archive adapter cannot infer those
facts. A report with missing evidence can be preserved with `sources=()`, but
strict calibration excludes it. This is an explicit limitation of legacy reports,
not permission to assign present-day inputs a historical date. Live-provider
instrumentation and automatic archival scheduling are not introduced here.

## Immutability and model versions

`CMEVintage`, its asset snapshots and source records are frozen Pydantic models;
collections are tuples, including nested matrices and numeric inputs.
`VintageStore` writes a canonical JSON document to a SHA-256 filename using
atomic, no-overwrite publication. Re-saving identical content is idempotent and
concurrent saves do not expose partial records. Changed evidence has a new ID;
there is no update/delete API. Loading verifies the content hash. Invalid IDs
cannot traverse outside the archive directory.

Different model versions can coexist on one forecast date. Changing proxy maps,
MOVE conversion/duration, blend methodology, forward building blocks, inflation
or FX treatment should produce a new explicit `model_version`; `code_version`
preserves the producing commit/build identifier. Both are caller-required rather
than inferred from the code installed when an old report is imported.

Hashes detect accidental modification. They are not signatures, external
attestations or protection against someone rewriting the filesystem. Back up the
archive and source snapshots separately. Local archives under
`validation/data/cme_vintages/` are ignored by Git; fixture data should be kept
separately and identified as synthetic.

## Strict temporal provenance

Default `CalibrationConfig(strict=True)` excludes a whole vintage when required
evidence is missing or inconsistent. Excluded forecasts retain reason codes and
sample counts, with null calibration errors.

Every source has a component, optional asset key, provider/proxy, source quality,
revision policy, and timezone-aware observation, availability and retrieval times.
Shared sources may cover several assets. Required components are history for
each asset, implied/forward inputs when present, and shared correlation,
risk-free, inflation and FX evidence. Fixed assumptions also need the date they
were adopted; a zero FX-change assumption is not an undated exemption.

- Observed: the actual stored forecast was generated on `as_of`; each input was
  observed, available and retrieved no later than that generation time. A saved
  observed forecast can contain the revised history actually available then.
- Reconstructed: the historical decision cutoff is the end of `as_of` in UTC.
  Inputs must have been observed and available by that cutoff, although a
  point-in-time vintage may be retrieved later. Latest-revised or unknown
  revision policy is insufficient. Generation must follow the forecast date.
  Reconstructed linear-blend outputs must also match the archived components,
  allowing 1.1e-6 absolute tolerance for the engine's six-decimal rounding.
- All: source chronology must be ordered; unknown quality, unknown revision
  policy, future report dates and missing timestamps fail strict eligibility.

The supported revision policies are `point_in_time`, `not_revised`,
`latest_revised`, `fixed_assumption` and `unknown`. Source quality retains
`fresh`, `cached`, `stale`, `fallback` or `unknown`. These are explicit caller
attestations; the code cannot prove that a provider's claimed vintage is genuine.

There is no automatic historical reconstruction loader. A caller may ingest a
reconstruction assembled from point-in-time components. If a historical forward
input is unavailable, omit that component and use the corresponding historical
branch, provide a documented dated proxy, or retain the record as unsuitable.
The code never consults today's forward inputs. `strict=False` permits exploratory
analysis of unsuitable records but retains their issues and `strict_eligible=False`;
such results cannot be presented as strict forecast validation.

## Outcomes and calibration

`RealizedPanel` contains numeric **daily simple total returns** keyed by stable
asset class, exact proxy mapping, base currency/FX treatment, source/revision
policy and declared calendar coverage. It does not translate FX or adjust prices.
The caller must supply the complete intended trading calendar and handle dividends,
FX and revisions consistently. Missing rows cannot be discovered from a returns-only
snapshot. Explicit NaNs, invalid returns and changed proxies are not filled or
silently substituted.

Default horizons are 1, 3 and 5 **calendar years**. `evaluation_date` is mandatory.
A horizon is immature before its anniversary even if future data were accidentally
supplied. The evaluation interval is **(as_of, as_of + H years]**; February 29
anniversaries clamp to February 28 in non-leap years. Declared calendar coverage
allows non-trading anniversary dates without inventing an extra trading day.

CAGR is `exp(sum(log1p(daily_return))/H) - 1`; a total loss gives -100%.
Volatility is sample daily standard deviation (`ddof=1`) times `sqrt(252)`.
At least 126 daily observations per horizon year are required by default, and
any missing/invalid observation in an asset's supplied horizon suppresses its
outcome. Missing assets/proxy mismatches are flagged per asset.

The primary return error is realized CAGR minus the **stored annual expected
return**. The production historical component is an arithmetic annualized mean,
not a geometric CAGR forecast. This difference, including volatility drag, affects
interpretation; the report also exposes realized arithmetic annualized returns.
No unimplemented arithmetic-to-geometric forecast conversion is silently applied.

Asset summaries contain bias, MAE, RMSE, median error/absolute error, extrema,
forecast dates and usable/missing counts. Volatility adds predicted/realized
ratio (null when realized volatility is zero), underprediction frequency and
material underprediction at a configurable default 1.5x ratio. Realized Pearson
correlations use complete common daily windows. Pairwise errors exclude diagonals;
full symmetric matrix Frobenius error is available only when all pairs are valid.
Constant series and missing forecast correlations remain unknown. Rank correlation
is Spearman across the complete declared asset universe, with at least three
assets by default; ties/constant ranks can make it undefined. Forecast and realized
cross-asset dispersion are also reported.

Summaries require three distinct usable forecast dates by default. They separate
model version, observed/reconstructed type, currency/FX policy, lookback,
inflation, blending parameters, cache state and source quality. Asset summaries
also retain proxy, component availability and return/volatility source quality.
Source quality is the worst relevant recorded state (unknown, fallback, stale,
cached, fresh); full per-source detail stays in the archive. Multiple captures
of one date within the same asset/model/configuration/source cohort are rejected;
select one explicitly instead of inflating the sample. Different model versions
remain separate. Overlapping multi-year outcomes are dependent observations,
so counts do not imply independent samples or statistical significance.

## Blend experiments

`evaluate_blending` uses the same maturity, outcome and strict-provenance checks.
Default tau and omega grids are 0, 0.25, 0.5, 0.75 and 1. They run independently:
tau changes only volatility; omega changes only expected return. The pure blend
function is shared with production CME generation, preserving its formula.

Endpoint zero selects historical inputs; endpoint one selects implied/forward
inputs **where available**. Missing alternative components use the production
historical fallback and receive a separate `historical_fallback` cohort. Legacy
reports without a stored historical return cannot support a return-blend
comparison; their history is not back-solved from rounded blended values.

Each weight reports same-vintage errors and MAE/RMSE differences against
historical-only, volatility underprediction, and forecast standard deviation
across vintages. Omega also reports per-vintage return ranks and their change
from the historical baseline, including how many assets used fallback inputs.
Negative MAE/RMSE differences indicate lower error on that descriptive sample;
there is no winner selection, significance claim or automatic parameter update.
Reblending archived six-decimal components may differ slightly from the original
forecast, which was blended before rounding. Original vintage outputs remain
unchanged and are what `calibrate` evaluates.

Run deterministic tests with `python -m pytest -q tests/test_cme_validation.py`.
