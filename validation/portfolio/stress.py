"""Saved walk-forward historical replay and transparent deterministic shocks."""

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR
from src.portfolio.backtest import STRESS_SCENARIOS

from .comparison import require_same_protocol
from .forecasts import valid_forecast_boundary
from .metrics import compute_metrics


@dataclass(frozen=True)
class HistoricalScenario:
    name: str
    start: str
    end: str

    def __post_init__(self):
        start, end = pd.Timestamp(self.start), pd.Timestamp(self.end)
        if (
            not self.name
            or any(
                pd.isna(d) or d.tz is not None or d != d.normalize()
                for d in (start, end)
            )
            or start >= end
        ):
            raise ValueError(
                "Historical scenario requires a name and ordered calendar dates"
            )


def historical_stress(runs, scenarios=None, *, baseline=None, min_observations=20):
    require_same_protocol(runs)
    if type(min_observations) is not int or min_observations < 2:
        raise ValueError("Historical stress requires at least two observations")
    if baseline is not None and baseline not in runs:
        raise ValueError("Baseline must name a supplied run")
    scenarios = (
        tuple(HistoricalScenario(*s) for s in STRESS_SCENARIOS)
        if scenarios is None
        else tuple(scenarios)
    )
    if len({s.name for s in scenarios}) != len(scenarios):
        raise ValueError("Historical scenario names must be unique")
    rows = []
    for scenario in scenarios:
        scenario.__post_init__()
        start, end = pd.Timestamp(scenario.start), pd.Timestamp(scenario.end)
        for name, run in runs.items():
            sample = run.returns.loc[start:end]
            records = [
                r
                for r in run.rebalances
                if r["holding_start"] <= end and r["holding_end"] >= start
            ]
            row = {
                "name": name,
                "scenario": scenario.name,
                "start": start,
                "end": end,
                "first_observation": sample.index.min() if len(sample) else None,
                "last_observation": sample.index.max() if len(sample) else None,
                "observations": int(sample.notna().sum()),
                "missing_observations": int(sample.isna().sum()),
                "status": "out_of_range",
                "window_return": None,
                "max_drawdown": None,
                "peak_date": None,
                "trough_date": None,
                "recovery_date": None,
                "recovery_calendar_days": None,
                "recovery_status": "unavailable",
                "relative_return_vs_baseline": None,
                "pre_event_as_of": None,
                "pre_event_predicted_volatility": None,
                "realized_volatility": None,
                "volatility_error": None,
                "pre_event_covariance_role": None,
            }
            rows.append(row)
            if (
                run.returns.empty
                or run.returns.index.min() > start
                or run.returns.index.max() < end
                or pd.Timestamp(run.metadata["config"]["start_date"]) >= start
                or pd.Timestamp(run.metadata["config"]["end_date"]) < end
            ):
                continue
            if any(r["status"] != "ok" for r in records) or sample.isna().any():
                row["status"] = "incomplete_window"
                continue
            if len(sample) < min_observations:
                row["status"] = "insufficient_observations"
                continue
            metrics = compute_metrics(sample, 0)
            nav = (1 + sample).cumprod()
            drawdown = nav / nav.cummax().clip(lower=1) - 1
            trough = drawdown.idxmin()
            before = nav.loc[:trough]
            peak_value = max(1.0, float(before.max()))
            peak = before.idxmax() if before.max() > 1 else None
            row.update(
                status="ok",
                window_return=metrics["total_return"],
                max_drawdown=metrics["max_drawdown"],
                realized_volatility=metrics["annualized_volatility"],
                peak_date=peak,
                trough_date=trough,
            )
            # Forecast strictly before the named event; no re-fit with shock data.
            prior = [
                r
                for r in run.rebalances
                if r["as_of"] < start and r["holding_end"] >= start
            ]
            if prior:
                record = prior[-1]
                forecast = record.get("risk_forecast") or {}
                if (
                    record["allocation_status"] == "ok"
                    and forecast.get("status") == "ok"
                    and valid_forecast_boundary(forecast, record["as_of"])
                ):
                    predicted = forecast.get("predicted_volatility")
                    row.update(
                        pre_event_as_of=record["as_of"],
                        pre_event_predicted_volatility=predicted,
                        pre_event_covariance_role=forecast.get("covariance_role"),
                        volatility_error=metrics["annualized_volatility"] - predicted
                        if predicted is not None
                        else None,
                    )
            if metrics["max_drawdown"] == 0:
                row["recovery_status"] = "no_drawdown"
                continue
            # Recovery uses the saved strategy after the trough, with an explicit
            # first-gap cutoff, including a wholly absent holding month.
            failed = [
                r["holding_start"]
                for r in run.rebalances
                if r["holding_end"] > trough and r["status"] != "ok"
            ]
            tail = run.returns.loc[run.returns.index > trough]
            if failed:
                tail = tail.loc[tail.index < min(failed)]
            recovery_nav = nav.loc[trough] * (1 + tail).cumprod(skipna=False)
            recovered = recovery_nav[recovery_nav >= peak_value]
            row["recovery_status"] = (
                "recovered"
                if len(recovered)
                else "censored_at_gap"
                if failed
                else "not_recovered_in_available_history"
            )
            if len(recovered):
                date = recovered.index[0]
                row.update(
                    recovery_date=date, recovery_calendar_days=(date - trough).days
                )
        cohort = [r for r in rows if r["scenario"] == scenario.name]
        if baseline is not None:
            reference = next(r for r in cohort if r["name"] == baseline)
            for row in cohort:
                if row["status"] == reference["status"] == "ok":
                    row["relative_return_vs_baseline"] = (
                        row["window_return"] - reference["window_return"]
                    )
    return {
        "rows": rows,
        "metadata": {
            "stress_version": "1.0",
            "scenarios": [asdict(s) for s in scenarios],
            "baseline": baseline,
            "min_observations": min_observations,
            "date_policy": "inclusive daily-return dates; require full window coverage; no partial event statistics",
            "portfolio_policy": "saved gross walk-forward path including scheduled rebalances; no event-aware fitting",
            "recovery_policy": "from worst within-window trough to its preceding peak (initial NAV 1 included); observed future path until first gap",
            "forecast_comparison": "last active decision strictly before event vs event-window annualized daily volatility; different horizons, descriptive only",
        },
    }


@dataclass(frozen=True)
class AssetExposure:
    equity: bool = False
    duration: float | None = None
    spread_duration: float | None = None

    def __post_init__(self):
        if type(self.equity) is not bool or any(
            v is not None and (not np.isfinite(v) or v < 0)
            for v in (self.duration, self.spread_duration)
        ):
            raise ValueError(
                "Exposures need an equity flag and nonnegative finite durations"
            )


@dataclass(frozen=True)
class SyntheticScenario:
    name: str
    return_shocks: dict[str, float] = field(default_factory=dict)
    rate_change: float = 0.0
    spread_change: float = 0.0
    volatility_multiplier: float = 1.0
    correlation_blend: float = 0.0

    def __post_init__(self):
        if not self.name or any(
            not np.isfinite(v)
            for v in (
                self.rate_change,
                self.spread_change,
                self.volatility_multiplier,
                self.correlation_blend,
            )
        ):
            raise ValueError("Synthetic shocks need names and finite parameters")
        if self.volatility_multiplier <= 0 or not 0 <= self.correlation_blend <= 1:
            raise ValueError(
                "Volatility multiplier must be positive; correlation blend must be in [0, 1]"
            )
        if any(
            not isinstance(a, str) or not a or not np.isfinite(v) or v < -1
            for a, v in self.return_shocks.items()
        ):
            raise ValueError(
                "Direct asset shocks require names and finite simple returns >= -1"
            )


def standard_scenarios(exposures):
    """Illustrative parameters, not empirical event estimates or forecasts."""
    equity = {a: -0.30 for a, exposure in exposures.items() if exposure.equity}
    return (
        SyntheticScenario("equity_down_30", equity),
        SyntheticScenario("rates_up_200bps", rate_change=0.02),
        SyntheticScenario("volatility_x1_5", volatility_multiplier=1.5),
        SyntheticScenario("correlation_convergence", correlation_blend=0.75),
        SyntheticScenario(
            "combined_risk_off",
            equity,
            rate_change=0.02,
            spread_change=0.01,
            volatility_multiplier=1.5,
            correlation_blend=0.75,
        ),
    )


def synthetic_stress(runs, scenarios, *, exposures=None):
    require_same_protocol(runs)
    exposures = exposures or {}
    scenarios = tuple(scenarios)
    universe = set(next(iter(runs.values())).metadata["config"]["universe"])
    if exposures.keys() - universe or len({s.name for s in scenarios}) != len(
        scenarios
    ):
        raise ValueError(
            "Exposures must belong to the universe and scenario names must be unique"
        )
    for exposure in exposures.values():
        exposure.__post_init__()
    for scenario in scenarios:
        scenario.__post_init__()
        if scenario.return_shocks.keys() - universe:
            raise ValueError("Shock assets must belong to the configured universe")
    rows = []
    for name, run in runs.items():
        for record in run.rebalances:
            for scenario in scenarios:
                row = {
                    "name": name,
                    "as_of": record["as_of"],
                    "scenario": scenario.name,
                    "loss_status": "allocation_unavailable",
                    "risk_status": "forecast_unavailable",
                    "asset_shocks": None,
                    "portfolio_return": None,
                    "base_volatility": None,
                    "stressed_volatility": None,
                    "volatility_change": None,
                }
                rows.append(row)
                if record["allocation_status"] != "ok":
                    continue
                shocks = {}
                for asset, weight in record["weights"].items():
                    if weight <= 0:
                        continue
                    exposure = exposures.get(asset, AssetExposure())
                    if (scenario.rate_change and exposure.duration is None) or (
                        scenario.spread_change and exposure.spread_duration is None
                    ):
                        row["loss_status"] = "missing_duration_exposure"
                        break
                    shocks[asset] = (
                        scenario.return_shocks.get(asset, 0)
                        - (exposure.duration or 0) * scenario.rate_change
                        - (exposure.spread_duration or 0) * scenario.spread_change
                    )
                else:
                    row["asset_shocks"] = shocks
                    row["loss_status"] = (
                        "shock_below_minus_one"
                        if any(s < -1 for s in shocks.values())
                        else "ok"
                    )
                    if row["loss_status"] == "ok":
                        row["portfolio_return"] = float(
                            sum(record["weights"][a] * s for a, s in shocks.items())
                        )
                forecast = record.get("risk_forecast") or {}
                if forecast.get("status") != "ok":
                    continue
                if not valid_forecast_boundary(forecast, record["as_of"]):
                    row["risk_status"] = "invalid_forecast_boundary"
                    continue
                assets = forecast["assets"]
                if set(a for a, w in record["weights"].items() if w > 0) - set(assets):
                    row["risk_status"] = "incomplete_covariance"
                    continue
                cov = np.asarray(forecast["annual_covariance"], dtype=float)
                if (
                    not assets
                    or cov.shape != (len(assets), len(assets))
                    or not np.isfinite(cov).all()
                    or not np.allclose(cov, cov.T)
                    or np.linalg.eigvalsh(cov).min() < -1e-10
                ):
                    row["risk_status"] = "invalid_covariance"
                    continue
                std = np.sqrt(np.maximum(np.diag(cov), 0))
                # Convex blend with a rank-one perfectly correlated covariance
                # preserves variances and PSD; no invalid pairwise replacement.
                stressed = (
                    (1 - scenario.correlation_blend) * cov
                    + scenario.correlation_blend * np.outer(std, std)
                ) * scenario.volatility_multiplier**2
                w = np.array([record["weights"].get(a, 0) for a in assets])
                base = float(np.sqrt(max(float(w @ cov @ w), 0)))
                vol = float(np.sqrt(max(float(w @ stressed @ w), 0)))
                row.update(
                    risk_status="ok",
                    base_volatility=base,
                    stressed_volatility=vol,
                    volatility_change=vol - base,
                )
    return {
        "rows": rows,
        "metadata": {
            "synthetic_version": "1.0",
            "scenarios": [asdict(s) for s in scenarios],
            "exposures": {a: asdict(e) for a, e in exposures.items()},
            "return_policy": "instantaneous target-weight shock; direct return - duration*yield change - spread duration*spread change; unspecified direct shocks zero",
            "duration_policy": "years; decimal yield/spread moves; missing exposure is unknown, explicit zero allowed; no convexity, carry or FX",
            "covariance_policy": "annual covariance convex blend with outer(asset volatilities), then multiplier squared; PSD-preserving correlation convergence",
            "horizon": "instantaneous return shock; annualized volatility scenario reported separately, not converted into a loss",
            "exposure_timing": "caller-supplied fixed hypothetical assumptions applied at each saved decision; not historical exposure estimates",
            "annualization_days": TRADING_DAYS_PER_YEAR,
        },
    }
