"""Strict walk-forward evaluation of supplied daily simple returns."""

from .comparison import ComparisonReport, compare_runs
from .costs import CostConfig, ImplementationReport, analyze_costs, compute_turnover
from .robustness import analyze_weights, weight_distance
from .sensitivity import (
    SensitivityConfig,
    SensitivityReport,
    compare_allocations,
    run_sensitivity,
)
from .strategies import Allocation, PortfolioStrategy, StrategySpec
from .walk_forward import ValidationRun, WalkForwardConfig, evaluate

__all__ = [
    "Allocation",
    "PortfolioStrategy",
    "StrategySpec",
    "ValidationRun",
    "WalkForwardConfig",
    "evaluate",
    "ComparisonReport",
    "compare_runs",
    "CostConfig",
    "ImplementationReport",
    "analyze_costs",
    "compute_turnover",
    "analyze_weights",
    "weight_distance",
    "SensitivityConfig",
    "SensitivityReport",
    "compare_allocations",
    "run_sensitivity",
]
