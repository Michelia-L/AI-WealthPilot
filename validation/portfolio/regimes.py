"""Ex-post descriptive labels only; no signal or portfolio-construction API."""

import hashlib
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR
from src.portfolio.risk_metrics import conditional_var, value_at_risk

from .comparison import require_same_protocol
from .costs import compute_turnover
from .metrics import compute_metrics
from .risk_calibration import CalibrationConfig, calibration_summary


@dataclass
class AnalysisSeries:
    values: pd.Series
    source: str
    revision_policy: str
    units: str

    def __post_init__(self):
        index = self.values.index
        if (
            not isinstance(index, pd.DatetimeIndex)
            or index.hasnans
            or index.tz is not None
            or not index.is_unique
            or not index.is_monotonic_increasing
            or not (index == index.normalize()).all()
        ):
            raise ValueError(
                "Analysis series require sorted unique timezone-naive daily dates"
            )
        if (
            not pd.api.types.is_numeric_dtype(self.values.dtype)
            or np.isinf(self.values).any()
        ):
            raise ValueError(
                "Analysis series require numeric values; missing values may be NaN"
            )
        if (
            not self.source
            or not self.units
            or self.revision_policy
            not in {"latest_revised", "point_in_time", "not_revised", "synthetic"}
        ):
            raise ValueError(
                "Analysis series require source, units and explicit revision policy"
            )

    def provenance(self):
        return {
            "source": self.source,
            "revision_policy": self.revision_policy,
            "units": self.units,
            "data_start": self.values.index.min() if len(self.values) else None,
            "data_end": self.values.index.max() if len(self.values) else None,
            "sha256": hashlib.sha256(
                pd.util.hash_pandas_object(self.values).values.tobytes()
            ).hexdigest(),
        }


@dataclass(frozen=True)
class RegimeConfig:
    low_volatility: float = 0.10
    high_volatility: float = 0.20
    rate_change_threshold: float = 0.0025
    inflation_change_threshold: float = 0.001
    max_level_age_days: int = 45
    min_label_observations: int = 20
    min_observations: int = 60
    min_periods: int = 3
    confidence: float = 0.95
    min_tail_observations: int = 5

    def __post_init__(self):
        if not (
            np.isfinite(self.low_volatility)
            and np.isfinite(self.high_volatility)
            and 0 <= self.low_volatility < self.high_volatility
        ):
            raise ValueError(
                "Volatility thresholds must be ordered nonnegative annual fractions"
            )
        for name in ("rate_change_threshold", "inflation_change_threshold"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(
                    "Level-change thresholds must be finite and nonnegative"
                )
        for name in (
            "max_level_age_days",
            "min_label_observations",
            "min_observations",
            "min_periods",
            "min_tail_observations",
        ):
            minimum = 2 if name in {"min_observations", "min_label_observations"} else 1
            if type(getattr(self, name)) is not int or getattr(self, name) < minimum:
                raise ValueError(
                    "Regime sample minima and level age must be positive integers"
                )
        if not np.isfinite(self.confidence) or not 0 < self.confidence < 1:
            raise ValueError("confidence must be in (0, 1)")


LABELS = {
    "equity": ("bull", "bear", "flat"),
    "volatility": ("low_vol", "normal_vol", "high_vol"),
    "rates": ("rising_rates", "falling_rates", "stable_rates"),
    "inflation": ("inflationary", "disinflationary", "stable_inflation"),
}


def _level_change(series, start, end, max_age):
    if series is None:
        return None, None, None
    points = []
    for date in (start, end):
        # A known missing last release is not silently replaced by an older one.
        past = series.values.loc[:date]
        if (
            past.empty
            or pd.isna(past.iloc[-1])
            or (date - past.index[-1]).days > max_age
        ):
            return None, None, None
        points.append((past.index[-1], float(past.iloc[-1])))
    return points[1][1] - points[0][1], points[0][0], points[1][0]


def classify_regimes(run, benchmark, *, rates=None, inflation=None, config=None):
    config = config or RegimeConfig()
    for series, units in (
        (benchmark, "daily_simple_return"),
        (rates, "annual_yield_decimal"),
        (inflation, "yoy_inflation_decimal"),
    ):
        if series is not None:
            series.__post_init__()
            if series.units != units:
                raise ValueError("Unexpected analysis series units")
    if (benchmark.values.dropna() < -1).any():
        raise ValueError("Benchmark simple returns cannot be below -1")
    rows = []
    for record in run.rebalances:
        start, end = pd.Timestamp(record["as_of"]), pd.Timestamp(record["holding_end"])
        dates = run.returns.index[
            (run.returns.index > start) & (run.returns.index <= end)
        ]
        sample = benchmark.values.reindex(dates)
        labels = dict.fromkeys(LABELS, "unknown")
        row = {
            "as_of": start,
            "holding_end": end,
            "analysis_regime_label": labels,
            "benchmark_observations": int(sample.notna().sum()),
            "benchmark_missing_observations": int(sample.isna().sum()),
            "benchmark_return": None,
            "benchmark_volatility": None,
        }
        if len(sample) >= config.min_label_observations and sample.notna().all():
            total = float((1 + sample).prod() - 1)
            vol = float(sample.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
            row.update(benchmark_return=total, benchmark_volatility=vol)
            labels["equity"] = "bull" if total > 0 else "bear" if total < 0 else "flat"
            labels["volatility"] = (
                "low_vol"
                if vol < config.low_volatility
                else "high_vol"
                if vol >= config.high_volatility
                else "normal_vol"
            )
        for dimension, series, threshold in (
            ("rates", rates, config.rate_change_threshold),
            ("inflation", inflation, config.inflation_change_threshold),
        ):
            change, before, after = _level_change(
                series, start, end, config.max_level_age_days
            )
            row.update(
                {
                    f"{dimension}_change": change,
                    f"{dimension}_start_observation": before,
                    f"{dimension}_end_observation": after,
                }
            )
            if change is not None:
                labels[dimension] = LABELS[dimension][
                    0 if change > threshold else 1 if change < -threshold else 2
                ]
        rows.append(row)
    return {
        "per_rebalance": rows,
        "metadata": {
            "regime_definition_version": "1.0",
            "label_type": "analysis_regime_label",
            "timing": "ex_post_only; never a decision input",
            "config": asdict(config),
            "equity_rule": "sign of compounded contemporaneous holding-period benchmark return",
            "volatility_rule": "annualized sample daily volatility in completed holding window; fixed thresholds",
            "level_rule": "latest observation at/before each boundary, bounded age; end minus start; strict threshold",
            "benchmark": benchmark.provenance(),
            "rates": rates.provenance() if rates else None,
            "inflation": inflation.provenance() if inflation else None,
        },
    }


def regime_metrics(
    runs, regimes, *, config=None, calibration=None, calibration_config=None
):
    """Pool conditional daily moments; drawdown never crosses unrelated regimes."""
    config = config or RegimeConfig()
    require_same_protocol(runs)
    first = next(iter(runs.values()))
    if [(r["as_of"], r["holding_end"]) for r in regimes["per_rebalance"]] != [
        (r["as_of"], r["holding_end"]) for r in first.rebalances
    ]:
        raise ValueError(
            "Regime labels must match the run's decision and holding dates"
        )
    rows = []
    for name, run in runs.items():
        turnovers = compute_turnover(run)["per_rebalance"]
        for dimension, labels in LABELS.items():
            for label in (*labels, "unknown"):
                selected = [
                    i
                    for i, r in enumerate(regimes["per_rebalance"])
                    if r["analysis_regime_label"][dimension] == label
                ]
                periods = [run.rebalances[i] for i in selected]
                samples = [
                    run.returns.loc[
                        (run.returns.index > p["as_of"])
                        & (run.returns.index <= p["holding_end"])
                    ]
                    for p in periods
                ]
                sample = pd.concat(samples) if samples else pd.Series(dtype=float)
                complete = (
                    all(p["status"] == "ok" for p in periods) and sample.notna().all()
                )
                status = (
                    "unknown_regime"
                    if label == "unknown"
                    else "incomplete_periods"
                    if not complete
                    else "insufficient_sample"
                    if len(periods) < config.min_periods
                    or len(sample) < config.min_observations
                    else "ok"
                )
                metrics = compute_metrics(
                    sample,
                    run.metadata["config"]["risk_free_rate"],
                    periods_complete=status == "ok",
                )
                # Drawdowns across disjoint episodes are not a tradable path.
                episodes = []
                for j, (i, values) in enumerate(zip(selected, samples, strict=True)):
                    if j and i == selected[j - 1] + 1:
                        episodes[-1] = pd.concat([episodes[-1], values])
                    else:
                        episodes.append(values)
                metrics["max_drawdown"] = (
                    min(compute_metrics(s, 0)["max_drawdown"] for s in episodes)
                    if status == "ok"
                    else None
                )
                turnover_values = [
                    turnovers[i]["turnover"]
                    for i in selected
                    if not turnovers[i]["initial_allocation"]
                ]
                tail_count = 0
                cvar = None
                if status == "ok":
                    threshold = value_at_risk(sample, config.confidence)
                    tail_count = int((sample <= -threshold).sum())
                    if tail_count >= config.min_tail_observations:
                        cvar = conditional_var(sample, config.confidence)
                row = {
                    "name": name,
                    "dimension": dimension,
                    "label": label,
                    "status": status,
                    "periods": len(periods),
                    "failed_or_skipped_periods": sum(
                        p["status"] != "ok" for p in periods
                    ),
                    **metrics,
                    "episodes": len(episodes),
                    "average_daily_return": float(sample.mean())
                    if status == "ok"
                    else None,
                    "annualized_arithmetic_return": float(
                        sample.mean() * TRADING_DAYS_PER_YEAR
                    )
                    if status == "ok"
                    else None,
                    "downside_deviation": float(
                        np.sqrt(
                            np.minimum(sample, 0).pow(2).mean() * TRADING_DAYS_PER_YEAR
                        )
                    )
                    if status == "ok"
                    else None,
                    "cvar_daily": cvar,
                    "tail_observations": tail_count,
                    "cvar_status": "ok" if cvar is not None else "insufficient_sample",
                    "positive_period_frequency": float(
                        np.mean([p["realized_return"] > 0 for p in periods])
                    )
                    if status == "ok"
                    else None,
                    "turnover_observations": sum(
                        v is not None for v in turnover_values
                    ),
                    "turnover_missing": sum(v is None for v in turnover_values),
                    "mean_turnover": float(np.mean(turnover_values))
                    if status == "ok"
                    and turnover_values
                    and all(v is not None for v in turnover_values)
                    else None,
                }
                if calibration is not None:
                    dates = {p["as_of"] for p in periods}
                    row["risk_calibration"] = calibration_summary(
                        [
                            r
                            for r in calibration["per_rebalance"]
                            if r["name"] == name and r["as_of"] in dates
                        ],
                        calibration_config or CalibrationConfig(),
                    )
                rows.append(row)
    return {
        "rows": rows,
        "metadata": {
            "config": asdict(config),
            "return_policy": "gross; conditional daily sample; CAGR annualizes selected days, not calendar exposure",
            "drawdown_policy": "worst contiguous regime episode, each starting at NAV 1; no joining separated episodes",
            "downside_deviation_target": 0,
            "sortino_target": "run risk-free daily equivalent",
            "turnover_policy": "drift-aware; initial allocation excluded; unknown prior weights retained",
            "sample_policy": "no performance statistics if any selected period fails or minima unmet; unknown labels are not performance cohorts",
        },
    }
