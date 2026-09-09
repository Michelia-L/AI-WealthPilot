"""Calendar-horizon outcomes from a caller-supplied daily return snapshot."""

import hashlib
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR


@dataclass
class RealizedPanel:
    returns: pd.DataFrame  # Stable asset-class keys, already on the stated FX basis.
    proxies: dict[str, str]
    base_currency: str
    fx_treatment: str
    source: str
    revision_policy: str
    coverage_start: str
    coverage_end: str

    def __post_init__(self):
        index = self.returns.index
        if (
            not isinstance(index, pd.DatetimeIndex)
            or index.hasnans
            or index.tz is not None
            or not index.is_unique
            or not index.is_monotonic_increasing
            or not (index == index.normalize()).all()
            or not self.returns.columns.is_unique
        ):
            raise ValueError(
                "Realized data require sorted unique timezone-naive daily dates and asset keys"
            )
        if any(not pd.api.types.is_numeric_dtype(t) for t in self.returns.dtypes):
            raise ValueError("Realized data must contain numeric daily simple returns")
        start, end = pd.Timestamp(self.coverage_start), pd.Timestamp(self.coverage_end)
        if (
            any(
                pd.isna(t) or t.tz is not None or t != t.normalize()
                for t in (start, end)
            )
            or start > end
        ):
            raise ValueError("Coverage dates must be ordered calendar dates")
        if len(index) and (index.min() < start or index.max() > end):
            raise ValueError(
                "Return observations must lie within declared calendar coverage"
            )
        if (
            not self.source
            or not self.fx_treatment
            or self.revision_policy
            not in {"point_in_time", "latest_revised", "not_revised", "synthetic"}
        ):
            raise ValueError(
                "Realized snapshot requires source, FX treatment and revision policy"
            )

    def provenance(self):
        return {
            "source": self.source,
            "revision_policy": self.revision_policy,
            "base_currency": self.base_currency,
            "fx_treatment": self.fx_treatment,
            "proxies": dict(self.proxies),
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "data_sha256": hashlib.sha256(
                pd.util.hash_pandas_object(self.returns, index=True).values.tobytes()
            ).hexdigest(),
        }


def horizon_window(vintage, panel, horizon, evaluation_date):
    start = pd.Timestamp(vintage.as_of)
    end = start + pd.DateOffset(years=horizon)
    if end.date() > evaluation_date:
        return end, None, "immature"
    if start < pd.Timestamp(panel.coverage_start) or end > pd.Timestamp(
        panel.coverage_end
    ):
        return end, None, "outside_coverage"
    return (
        end,
        panel.returns.loc[(panel.returns.index > start) & (panel.returns.index <= end)],
        "ok",
    )


def realized_asset(asset, sample, horizon, min_observations_per_year):
    result = {
        "status": "missing_asset",
        "observations": 0,
        "missing_observations": 0,
        "first_observation": None,
        "last_observation": None,
        "realized_return": None,
        "realized_arithmetic_return": None,
        "realized_volatility": None,
    }
    if asset.key not in sample:
        return result
    values = sample[asset.key]
    result.update(
        observations=int(values.notna().sum()),
        missing_observations=int(values.isna().sum()),
        first_observation=values.index.min() if len(values) else None,
        last_observation=values.index.max() if len(values) else None,
    )
    if values.isna().any():
        result["status"] = "missing_returns"
    elif not np.isfinite(values).all() or (values < -1).any():
        result["status"] = "invalid_returns"
    elif len(values) < min_observations_per_year * horizon:
        result["status"] = "insufficient_observations"
    else:
        # Calendar anniversaries define exactly H years, including leap years.
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            total_log = np.log1p(values).sum()
            cagr = float(np.expm1(total_log / horizon))
            arithmetic = float(values.mean() * TRADING_DAYS_PER_YEAR)
            vol = float(values.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if not np.isfinite([cagr, arithmetic, vol]).all():
            result["status"] = "nonfinite_outcome"
        else:
            result.update(
                status="ok",
                realized_return=cagr,
                realized_arithmetic_return=arithmetic,
                realized_volatility=vol,
            )
    return result


def evaluation_day(value):
    timestamp = pd.Timestamp(value)
    if (
        pd.isna(timestamp)
        or timestamp.tz is not None
        or timestamp != timestamp.normalize()
    ):
        raise ValueError("evaluation_date must be a timezone-naive calendar date")
    return date(timestamp.year, timestamp.month, timestamp.day)
