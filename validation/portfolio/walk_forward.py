"""Calendar-month walk-forward orchestration with no provider/data fetching."""

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib.metadata import version

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR

from .metrics import compute_metrics
from .strategies import (
    AllocationError,
    PortfolioStrategy,
    StrategySpec,
    allocation_error_reason,
)

VALIDATION_VERSION = "1.2"


@dataclass
class WalkForwardConfig:
    """Windows/frequency are positive calendar-month counts.

    start_date is the first month-end decision, end_date the inclusive last
    holding date. v1 requires holding_window == rebalance_frequency so one
    fully invested portfolio produces a continuous, non-overlapping series.
    """

    start_date: str
    end_date: str
    universe: tuple[str, ...]
    training_window: int = 36
    holding_window: int = 1
    rebalance_frequency: int = 1
    window_type: str = "rolling"
    min_observations: int = 252
    min_coverage: float = 0.9
    strategy: StrategySpec = field(default_factory=StrategySpec)
    expected_return_method: str = "historical"
    covariance_method: str = "ledoit-wolf"
    constraints: dict = field(default_factory=lambda: {"long_only": True})
    risk_free_rate: float = 0.0
    risk_free_rate_source: str = "constant annual assumption supplied by caller"
    random_seed: int = 0
    data_source: str = "caller-supplied daily simple returns"
    code_version: str | None = None

    def __post_init__(self):
        for key in (
            "training_window",
            "holding_window",
            "rebalance_frequency",
            "min_observations",
        ):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f"{key} must be a positive integer")
        if self.min_observations < 2:
            raise ValueError("min_observations must be at least 2")
        if self.holding_window != self.rebalance_frequency:
            raise ValueError("v1 requires holding_window == rebalance_frequency")
        start, end = pd.Timestamp(self.start_date), pd.Timestamp(self.end_date)
        if any(
            pd.isna(t) or t.tz is not None or t != t.normalize() for t in (start, end)
        ):
            raise ValueError("Dates must be timezone-naive calendar dates")
        if not start.is_month_end or end <= start:
            raise ValueError("start_date must be a month end strictly before end_date")
        if self.window_type not in {"rolling", "expanding"}:
            raise ValueError("window_type must be rolling or expanding")
        if not 0 < self.min_coverage <= 1:
            raise ValueError("min_coverage must be in (0, 1]")
        if not self.universe or len(set(self.universe)) != len(self.universe):
            raise ValueError("universe must be nonempty and unique")
        if any(not isinstance(asset, str) or not asset for asset in self.universe):
            raise ValueError("universe requires nonempty asset names")
        if self.expected_return_method != "historical":
            raise ValueError("v1 supports historical expected returns only")
        if self.covariance_method not in {"sample", "ledoit-wolf", "oas"}:
            raise ValueError("Unsupported covariance estimator")
        if self.constraints != {"long_only": True}:
            raise ValueError("v1 supports fully invested, long-only constraints only")
        if not np.isfinite(self.risk_free_rate) or self.risk_free_rate <= -1:
            raise ValueError("risk_free_rate must be finite and greater than -1")
        if type(self.random_seed) is not int or self.random_seed < 0:
            raise ValueError("random_seed must be a nonnegative integer")
        if self.strategy.expected_return_shifts.keys() - set(self.universe):
            raise ValueError(
                "Expected-return shift assets must belong to the configured universe"
            )


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


@dataclass
class ValidationRun:
    returns: pd.Series
    nav: pd.Series
    rebalances: list[dict]
    metrics: dict
    metadata: dict

    def to_dict(self) -> dict:
        return _json_safe(
            {
                "metadata": self.metadata,
                "metrics": self.metrics,
                "rebalances": self.rebalances,
                "series": [
                    {"date": date, "return": ret, "nav": self.nav.loc[date]}
                    for date, ret in self.returns.items()
                ],
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), allow_nan=False, indent=2)


def _validate_returns(returns: pd.DataFrame) -> None:
    index = returns.index
    if returns.empty or not isinstance(index, pd.DatetimeIndex):
        raise ValueError("returns must have a nonempty DatetimeIndex")
    if (
        index.hasnans
        or index.tz is not None
        or not index.is_unique
        or not index.is_monotonic_increasing
        or not (index == index.normalize()).all()
    ):
        raise ValueError("returns require sorted, unique, timezone-naive daily dates")
    if not returns.columns.is_unique:
        raise ValueError("Duplicate asset columns")
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in returns.dtypes):
        raise ValueError("returns must be numeric daily simple returns")


def _history_at(data, as_of, lower, config):
    # Slice first. In particular never drop columns based on the full dataset.
    window = data.loc[(data.index > lower) & (data.index <= as_of)].copy()
    valid = np.isfinite(window) & (window >= -1)
    counts = valid.sum()
    coverage = counts / max(len(window), 1)
    eligible = counts.index[
        (counts >= config.min_observations) & (coverage >= config.min_coverage)
    ].tolist()
    excluded = {
        asset: "insufficient_history"
        if counts[asset] < config.min_observations
        else "sparse_history"
        for asset in config.universe
        if asset not in eligible
    }
    # Keep the whole window and mask invalid values. Fitting sample selection
    # belongs to the strategy; baselines need not estimate joint covariance.
    return window[eligible].where(valid[eligible]), eligible, excluded


def _weights_valid(weights, eligible):
    if not weights or set(weights) - set(eligible):
        return False
    values = np.asarray(list(weights.values()), dtype=float)
    return bool(
        np.isfinite(values).all()
        and (values >= 0).all()
        and (values <= 1).all()
        and abs(values.sum() - 1) <= 1e-8
    )


def evaluate(
    returns: pd.DataFrame,
    config: WalkForwardConfig,
    strategy: PortfolioStrategy | None = None,
) -> ValidationRun:
    """Refit at each month end and buy-and-hold through the next window.

    Custom allocators receive a private copy of the historical window restricted
    to eligible assets. Missing/invalid observations are NaN, with dates retained.
    They must not fetch current auxiliary inputs or access future data through
    external state. Supply a data snapshot containing the full desired calendar;
    absent dates cannot be inferred from a returns-only input.
    """
    _validate_returns(returns)
    config = deepcopy(config)
    config.__post_init__()
    config.strategy.__post_init__()
    if (strategy is not None) != (config.strategy.name == "custom"):
        raise ValueError(
            "Custom allocators require StrategySpec('custom') and vice versa"
        )
    allocator = strategy if strategy is not None else config.strategy
    data = returns.reindex(columns=config.universe).astype(float).copy()
    start, end = pd.Timestamp(config.start_date), pd.Timestamp(config.end_date)
    oos = pd.Series(
        np.nan,
        index=data.index[(data.index > start) & (data.index <= end)],
        name="return",
    )
    records = []
    as_of = start
    initial_lower = start - pd.offsets.MonthEnd(config.training_window)
    while as_of < end:
        holding_end = min(as_of + pd.offsets.MonthEnd(config.holding_window), end)
        lower = (
            initial_lower
            if config.window_type == "expanding"
            else as_of - pd.offsets.MonthEnd(config.training_window)
        )
        history, eligible, excluded = _history_at(data, as_of, lower, config)
        dates = oos.index[(oos.index > as_of) & (oos.index <= holding_end)]
        record = {
            "as_of": as_of,
            "training_window_start": lower + pd.Timedelta(days=1),
            "training_start": history.index.min() if len(history) else None,
            "training_end": history.index.max() if len(history) else None,
            "training_window_observations": len(history),
            "estimation_observations": None,
            "holding_start": as_of + pd.Timedelta(days=1),
            "holding_end": holding_end,
            "holding_observations": len(dates),
            "strategy": config.strategy.name,
            "eligible_assets": eligible,
            "excluded_assets": excluded,
            "expected_return_method": config.expected_return_method,
            "covariance_method": config.covariance_method,
            "weights": {},
            "ending_weights": None,
            "diagnostics": {},
            "allocation_status": "not_attempted",
            "status": "skipped",
            "reason": None,
            "realized_return": None,
        }
        records.append(record)
        if not eligible:
            record["reason"] = "no_eligible_assets"
        else:
            try:
                allocation = allocator.allocate(
                    history.copy(deep=True), as_of, deepcopy(config)
                )
                record["diagnostics"] = deepcopy(allocation.diagnostics)
                record["estimation_observations"] = deepcopy(
                    allocation.estimation_observations
                )
                if not allocation.success:
                    raise AllocationError("optimizer_unsuccessful")
                if not _weights_valid(allocation.weights, eligible):
                    raise AllocationError("invalid_weights")
                record["weights"] = {k: float(v) for k, v in allocation.weights.items()}
                record["allocation_status"] = "ok"
            except Exception as exc:
                record["allocation_status"] = "failed"
                record["status"] = "failed"
                # Do not serialize arbitrary exception messages: a custom
                # strategy/provider could embed credentials or profile data.
                record["reason"] = (
                    allocation_error_reason(exc)
                    if isinstance(exc, AllocationError)
                    else "allocation_exception"
                )
                if isinstance(exc, AllocationError):
                    count = exc.estimation_observations
                    if type(count) is int and count >= 0:
                        record["estimation_observations"] = count
                    if record["reason"] == "insufficient_joint_history":
                        record["status"] = "skipped"
                        record["allocation_status"] = "not_attempted"
                record["diagnostics"]["exception_type"] = type(exc).__name__

            if record["allocation_status"] == "ok":
                active = {k: v for k, v in record["weights"].items() if v > 0}
                holding = data.loc[dates, list(active)]
                if not len(dates):
                    record["reason"] = "no_holding_observations"
                elif data.index.max() < holding_end:
                    record["status"] = "failed"
                    record["reason"] = "incomplete_holding_window"
                elif not (np.isfinite(holding) & (holding >= -1)).all().all():
                    # Never change the chosen universe/weights after seeing
                    # which assets are available in the holding window.
                    record["status"] = "failed"
                    record["reason"] = "missing_or_invalid_holding_returns"
                else:
                    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                        asset_growth = (1 + holding).cumprod()
                        wealth = asset_growth @ pd.Series(active)
                        prior = wealth.shift(1, fill_value=1.0)
                        # A completely wiped-out portfolio stays at zero wealth.
                        daily = wealth.div(prior).sub(1).where(prior != 0, 0.0)
                    if not np.isfinite(wealth).all() or not np.isfinite(daily).all():
                        record["status"] = "failed"
                        record["reason"] = "nonfinite_holding_wealth"
                    else:
                        oos.loc[dates] = daily
                        record["status"] = "ok"
                        record["realized_return"] = float(wealth.iloc[-1] - 1)
                        if wealth.iloc[-1] > 0:
                            record["ending_weights"] = (
                                asset_growth.iloc[-1]
                                * pd.Series(active)
                                / wealth.iloc[-1]
                            ).to_dict()
        as_of += pd.offsets.MonthEnd(config.rebalance_frequency)

    # An unknown period invalidates subsequent cumulative NAV; later local
    # holding returns and allocations remain available for diagnosis.
    nav = (1 + oos).cumprod(skipna=False).rename("nav")
    incomplete = [r for r in records if r["status"] != "ok"]
    if incomplete:
        # Also catches a wholly absent month, which has no NaN row in oos.
        nav.loc[nav.index >= incomplete[0]["holding_start"]] = np.nan
    metrics = compute_metrics(
        oos, config.risk_free_rate, periods_complete=not incomplete
    )
    metrics.update(
        rebalance_observations=len(records),
        allocation_success_count=sum(r["allocation_status"] == "ok" for r in records),
        allocation_failure_count=sum(
            r["allocation_status"] == "failed" for r in records
        ),
        successful_period_count=sum(r["status"] == "ok" for r in records),
        failed_period_count=sum(r["status"] == "failed" for r in records),
        skipped_period_count=sum(r["status"] == "skipped" for r in records),
    )
    digest = hashlib.sha256(
        pd.util.hash_pandas_object(data, index=True).values.tobytes()
    ).hexdigest()
    metadata = {
        "validation_version": VALIDATION_VERSION,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "allocator": f"{type(allocator).__module__}.{type(allocator).__qualname__}",
        "data_sha256": digest,
        "data_start": data.index.min(),
        "data_end": data.index.max(),
        "annualization_days": TRADING_DAYS_PER_YEAR,
        "holding_policy": "buy_and_hold; rebalance to target at each decision",
        "missing_data_policy": "point_in_time_eligibility; strategy_specific_estimation; unknown holding window on missing active returns",
        "failure_policy": "unknown returns; cumulative NAV remains unknown after a gap",
        "versions": {
            name: version(name) for name in ("numpy", "pandas", "scipy", "scikit-learn")
        },
    }
    return ValidationRun(oos, nav, records, metrics, metadata)
