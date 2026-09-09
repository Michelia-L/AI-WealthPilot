"""Supplied portfolio returns only; no providers, filling or inferred allocation."""

import hashlib
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from .scenarios import EngineConfig, Record


class HistoricalReturns(Record):
    dates: tuple[date, ...]
    returns: tuple[float, ...]
    frequency: Literal["monthly", "annual"]
    source: str = Field(min_length=1)
    portfolio_mapping: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    fx_treatment: str = Field(min_length=1)
    sample_kind: Literal["historical", "synthetic"]

    @model_validator(mode="after")
    def valid_sample(self):
        if len(self.dates) != len(self.returns) or len(self.dates) < 2:
            raise ValueError("need at least two dated returns")
        if any(r <= -1 for r in self.returns):
            raise ValueError("bootstrap returns must be > -1 for log-moment mapping")
        periods = pd.PeriodIndex(
            self.dates, freq="M" if self.frequency == "monthly" else "Y"
        )
        if not np.all(np.diff(periods.asi8) == 1):
            raise ValueError(
                "historical sample must have one observation per consecutive period"
            )
        return self

    @property
    def periods_per_year(self) -> int:
        return 12 if self.frequency == "monthly" else 1

    @property
    def sample_id(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def sample_indices(
    sample_size: int,
    n_paths: int,
    n_periods: int,
    seed: int,
    block_length: int = 1,
) -> np.ndarray:
    """Non-circular moving blocks; last block is truncated at horizon end.

    Each start is uniform over full blocks inside the sample. No block wraps
    from the last observation to the first; edge observations have less weight.
    """
    if (
        sample_size < 2
        or n_paths < 1
        or n_periods < 0
        or not 1 <= block_length <= sample_size
    ):
        raise ValueError("invalid bootstrap dimensions or block length")
    rng = np.random.default_rng(seed)
    n_blocks = (n_periods + block_length - 1) // block_length
    starts = rng.integers(0, sample_size - block_length + 1, size=(n_paths, n_blocks))
    return (starts[:, :, None] + np.arange(block_length)).reshape(n_paths, -1)[
        :, :n_periods
    ]


def bootstrap_growth(
    sample: HistoricalReturns,
    config: EngineConfig,
    n_paths: int,
    years: int,
    seed: int,
    expected_return: float,
    volatility: float,
    return_multiplier: float = 1.0,
    volatility_multiplier: float = 1.0,
) -> tuple[np.ndarray, dict]:
    frequency = sample.periods_per_year
    block = config.block_length if config.engine == "block_bootstrap" else 1
    indices = sample_indices(
        len(sample.returns), n_paths, years * frequency, seed, block
    )
    logs = np.log1p(sample.returns)
    mean, std = float(logs.mean()), float(logs.std(ddof=1))
    if np.ptp(logs) == 0:
        std = 0.0
    if config.bootstrap_mode == "matched_gbm_moments":
        target_vol = volatility * volatility_multiplier
        target_mean = (
            expected_return * return_multiplier - 0.5 * target_vol**2
        ) / frequency
        target_std = target_vol / np.sqrt(frequency)
    else:
        # Infer GBM log moments from the empirical sample, then apply the same
        # return/vol shift used by GBM. Identity multipliers keep raw returns.
        annual_vol = std * np.sqrt(frequency)
        implied_mu = mean * frequency + 0.5 * annual_vol**2
        target_vol = annual_vol * volatility_multiplier
        target_mean = (implied_mu * return_multiplier - 0.5 * target_vol**2) / frequency
        target_std = std * volatility_multiplier
    if std == 0 and target_std > 0:
        raise ValueError("constant bootstrap sample cannot match positive volatility")
    if (
        config.bootstrap_mode == "empirical"
        and return_multiplier == volatility_multiplier == 1
    ):
        mapped = logs
    else:
        mapped = target_mean + (logs - mean) * (target_std / std if std else 0)
    growth = np.exp(mapped[indices].reshape(n_paths, years, frequency).sum(axis=2))
    return growth, {
        "block_length_periods": block,
        "sample_log_mean_per_period": mean,
        "sample_log_std_per_period": std,
        "mapped_log_mean_per_period": float(mapped.mean()),
        "mapped_log_std_per_period": float(mapped.std(ddof=1)),
        "sampled_indices_sha256": hashlib.sha256(
            indices.astype("<i8").tobytes()
        ).hexdigest(),
        "mapping": config.bootstrap_mode,
    }
