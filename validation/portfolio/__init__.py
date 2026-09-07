"""Strict walk-forward evaluation of supplied daily simple returns."""

from .strategies import Allocation, PortfolioStrategy, StrategySpec
from .walk_forward import ValidationRun, WalkForwardConfig, evaluate

__all__ = [
    "Allocation",
    "PortfolioStrategy",
    "StrategySpec",
    "ValidationRun",
    "WalkForwardConfig",
    "evaluate",
]
