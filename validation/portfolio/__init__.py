"""Strict walk-forward evaluation of supplied daily simple returns."""

from .comparison import ComparisonReport, compare_runs
from .costs import CostConfig, ImplementationReport, analyze_costs, compute_turnover
from .regimes import AnalysisSeries, RegimeConfig, classify_regimes, regime_metrics
from .risk_calibration import CalibrationConfig, calibrate_risk
from .risk_report import RiskResearchReport, analyze_risk
from .robustness import analyze_weights, weight_distance
from .sensitivity import (
    SensitivityConfig,
    SensitivityReport,
    compare_allocations,
    run_sensitivity,
)
from .strategies import Allocation, PortfolioStrategy, StrategySpec
from .stress import (
    AssetExposure,
    HistoricalScenario,
    SyntheticScenario,
    historical_stress,
    standard_scenarios,
    synthetic_stress,
)
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
    "AnalysisSeries",
    "RegimeConfig",
    "classify_regimes",
    "regime_metrics",
    "CalibrationConfig",
    "calibrate_risk",
    "RiskResearchReport",
    "analyze_risk",
    "AssetExposure",
    "HistoricalScenario",
    "SyntheticScenario",
    "historical_stress",
    "standard_scenarios",
    "synthetic_stress",
]
