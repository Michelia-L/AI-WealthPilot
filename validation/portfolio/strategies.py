"""Common allocation contract and adapters to the production optimizer."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR
from src.portfolio.optimizer import PortfolioOptimizer

if TYPE_CHECKING:
    from .walk_forward import WalkForwardConfig


@dataclass
class Allocation:
    weights: dict[str, float]
    diagnostics: dict = field(default_factory=dict)
    success: bool = True
    estimation_observations: int | dict[str, int] | None = None


class PortfolioStrategy(Protocol):
    def allocate(
        self, history: pd.DataFrame, as_of: pd.Timestamp, config: "WalkForwardConfig"
    ) -> Allocation:
        """Choose a fitting sample from eligible history, which may contain NaNs.

        All supplied dates are <= as_of; auxiliary data must also be vintage-safe.
        """
        ...


class AllocationError(ValueError):
    """Allocation failure; only allowlisted reason codes may enter run output."""

    def __init__(self, reason: str, *, estimation_observations: int | None = None):
        super().__init__(reason)
        self.estimation_observations = estimation_observations


SAFE_ALLOCATION_REASONS = frozenset(
    {
        "custom_allocator_required",
        "invalid_training_boundary",
        "benchmark_assets_unavailable",
        "invalid_or_zero_volatility",
        "insufficient_joint_history",
        "optimizer_unsuccessful",
        "invalid_weights",
    }
)


def allocation_error_reason(exc: AllocationError) -> str:
    # Do not call str(exc): custom exceptions can contain arbitrary messages or
    # override __str__. Match an exact string argument against fixed codes only.
    reason = exc.args[0] if len(exc.args) == 1 else None
    return (
        reason
        if type(reason) is str and reason in SAFE_ALLOCATION_REASONS
        else "allocation_error"
    )


METHODS = {
    "min_variance": ("minimize_volatility", {"target_return"}),
    "mvo": ("maximize_sharpe", set()),
    "erc": ("risk_parity", set()),
    "mean_cvar": ("minimize_cvar", {"beta", "target_return"}),
    "resampled_mvo": ("resampled_maximize_sharpe", {"n_simulations"}),
}


def supports_expected_return_shifts(strategy: "StrategySpec") -> bool:
    return strategy.name in {"mvo", "resampled_mvo"} or (
        strategy.name == "min_variance"
        and strategy.parameters.get("target_return") is not None
    )


@dataclass
class StrategySpec:
    name: str = "equal_weight"
    parameters: dict = field(default_factory=dict)
    expected_return_shifts: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if self.expected_return_shifts:
            if not supports_expected_return_shifts(self):
                raise ValueError(
                    "Expected-return shifts require a supported return-dependent strategy"
                )
            if any(
                not isinstance(asset, str) or not asset or not np.isfinite(shift)
                for asset, shift in self.expected_return_shifts.items()
            ):
                raise ValueError(
                    "Expected-return shifts require asset names and finite annual offsets"
                )
        if self.name == "custom":
            return
        allowed = {
            "equal_weight": set(),
            "inverse_volatility": set(),
            "static": {"weights"},
            "60_40": set(),
            **{name: spec[1] for name, spec in METHODS.items()},
        }
        if self.name not in allowed:
            raise ValueError("Unsupported built-in strategy")
        if self.parameters.keys() - allowed[self.name]:
            raise ValueError("Unsupported strategy parameters")
        if self.name == "static" and "weights" not in self.parameters:
            raise ValueError("Static strategy requires weights")
        if "n_simulations" in self.parameters:
            n = self.parameters["n_simulations"]
            if type(n) is not int or n < 1:
                raise ValueError("n_simulations must be a positive integer")

    def allocate(
        self, history: pd.DataFrame, as_of: pd.Timestamp, config: "WalkForwardConfig"
    ) -> Allocation:
        if self.name == "custom":
            raise AllocationError("custom_allocator_required")
        if history.empty or history.index.max() > as_of:
            raise AllocationError("invalid_training_boundary")
        assets = history.columns
        if self.name == "equal_weight":
            return Allocation(
                dict.fromkeys(assets, 1.0 / len(assets)), estimation_observations=0
            )
        if self.name in {"static", "60_40"}:
            weights = (
                {"SPY": 0.6, "AGG": 0.4}
                if self.name == "60_40"
                else dict(self.parameters["weights"])
            )
            if any(asset not in assets and w != 0 for asset, w in weights.items()):
                raise AllocationError("benchmark_assets_unavailable")
            return Allocation(
                {asset: w for asset, w in weights.items() if w != 0},
                estimation_observations=0,
            )
        if self.name == "inverse_volatility":
            # Each asset uses its own valid history; unrelated missing dates
            # must not alter its volatility estimate.
            history = history.where(np.isfinite(history) & (history >= -1))
            vol = history.std(ddof=1)
            if not np.isfinite(vol).all() or (vol <= 1e-12).any():
                raise AllocationError("invalid_or_zero_volatility")
            # Scaling by the smallest vol avoids overflowing the reciprocal.
            inverse = vol.min() / vol
            return Allocation(
                (inverse / inverse.sum()).to_dict(),
                estimation_observations=history.count().to_dict(),
            )

        # Only production optimizer adapters need a joint complete-case sample.
        # Never substitute pairwise covariance or impute missing observations.
        history = history.where(np.isfinite(history) & (history >= -1)).dropna()
        if len(history) < config.min_observations:
            raise AllocationError(
                "insufficient_joint_history", estimation_observations=len(history)
            )

        expected_returns = None
        if self.expected_return_shifts:
            expected_returns = history.mean() * TRADING_DAYS_PER_YEAR + pd.Series(
                self.expected_return_shifts, dtype=float
            ).reindex(history.columns, fill_value=0.0)
        optimizer = PortfolioOptimizer(
            history,
            risk_free_rate=config.risk_free_rate,
            covariance_method=config.covariance_method,
            seed=config.random_seed,
            expected_returns=expected_returns,
        )
        method, _ = METHODS[self.name]
        result = getattr(optimizer, method)(**self.parameters)
        return Allocation(
            weights=result["weights"],
            success=bool(result["success"]),
            estimation_observations=len(history),
            diagnostics={
                "expected_returns": optimizer.mean_returns.to_dict(),
                "condition_number": float(optimizer.condition_number),
                "covariance_regularized": optimizer.is_regularized,
                **{
                    key: result[key]
                    for key in (
                        "return",
                        "volatility",
                        "sharpe",
                        "weight_std",
                        "n_simulations",
                        "risk_contributions",
                    )
                    if key in result
                },
            },
        )
