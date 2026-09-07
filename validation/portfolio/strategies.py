"""Common allocation contract and adapters to the production optimizer."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import numpy as np
import pandas as pd

from src.portfolio.optimizer import PortfolioOptimizer

if TYPE_CHECKING:
    from .walk_forward import WalkForwardConfig


@dataclass
class Allocation:
    weights: dict[str, float]
    diagnostics: dict = field(default_factory=dict)
    success: bool = True


class PortfolioStrategy(Protocol):
    def allocate(
        self, history: pd.DataFrame, as_of: pd.Timestamp, config: "WalkForwardConfig"
    ) -> Allocation:
        """Use only supplied history; auxiliary data must also be vintage-safe."""
        ...


class AllocationError(ValueError):
    """A stable, non-sensitive reason for a strategy that cannot allocate."""


METHODS = {
    "min_variance": ("minimize_volatility", {"target_return"}),
    "mvo": ("maximize_sharpe", set()),
    "erc": ("risk_parity", set()),
    "mean_cvar": ("minimize_cvar", {"beta", "target_return"}),
    "resampled_mvo": ("resampled_maximize_sharpe", {"n_simulations"}),
}


@dataclass
class StrategySpec:
    name: str = "equal_weight"
    parameters: dict = field(default_factory=dict)

    def __post_init__(self):
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
            return Allocation(dict.fromkeys(assets, 1.0 / len(assets)))
        if self.name in {"static", "60_40"}:
            weights = (
                {"SPY": 0.6, "AGG": 0.4}
                if self.name == "60_40"
                else dict(self.parameters["weights"])
            )
            if any(asset not in assets and w != 0 for asset, w in weights.items()):
                raise AllocationError("benchmark_assets_unavailable")
            return Allocation({asset: w for asset, w in weights.items() if w != 0})
        if self.name == "inverse_volatility":
            if not np.isfinite(history).all().all():
                raise AllocationError("invalid_or_zero_volatility")
            vol = history.std(ddof=1)
            if not np.isfinite(vol).all() or (vol <= 1e-12).any():
                raise AllocationError("invalid_or_zero_volatility")
            # Scaling by the smallest vol avoids overflowing the reciprocal.
            inverse = vol.min() / vol
            return Allocation((inverse / inverse.sum()).to_dict())

        optimizer = PortfolioOptimizer(
            history,
            risk_free_rate=config.risk_free_rate,
            covariance_method=config.covariance_method,
            seed=config.random_seed,
        )
        method, _ = METHODS[self.name]
        result = getattr(optimizer, method)(**self.parameters)
        return Allocation(
            weights=result["weights"],
            success=bool(result["success"]),
            diagnostics={
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
