"""Common archival output for calibration, regimes and stress comparisons."""

import json
from dataclasses import dataclass

import pandas as pd

from .costs import compute_turnover
from .regimes import classify_regimes, regime_metrics
from .risk_calibration import calibrate_risk
from .robustness import analyze_weights
from .stress import historical_stress, synthetic_stress
from .walk_forward import _json_safe


@dataclass
class RiskResearchReport:
    calibration: dict
    regimes: dict | None
    conditional_metrics: dict | None
    historical: dict
    synthetic: dict
    implementation: dict
    metadata: dict

    def to_dict(self):
        return _json_safe(self.__dict__)

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, allow_nan=False)

    def tables(self):
        """Flat core CSV tables; JSON retains nested definitions and diagnostics."""
        tables = {
            "calibration": self.calibration["per_rebalance"],
            "calibration_summary": self.calibration["summary"],
            "historical_stress": self.historical["rows"],
            "synthetic_stress": self.synthetic["rows"],
        }
        if self.conditional_metrics is not None:
            tables["regime_metrics"] = self.conditional_metrics["rows"]
        return {
            name: pd.json_normalize(_json_safe(rows)) for name, rows in tables.items()
        }


def analyze_risk(
    runs,
    *,
    benchmark=None,
    rates=None,
    inflation=None,
    calibration_config=None,
    regime_config=None,
    historical_scenarios=None,
    baseline=None,
    synthetic_scenarios=(),
    exposures=None,
):
    """Read saved runs only. External descriptive series never enter evaluate()."""
    if benchmark is None and (rates is not None or inflation is not None):
        raise ValueError("A benchmark is required for regime analysis")
    calibration = calibrate_risk(runs, calibration_config)
    regimes = conditional = None
    if benchmark is not None:
        regimes = classify_regimes(
            next(iter(runs.values())),
            benchmark,
            rates=rates,
            inflation=inflation,
            config=regime_config,
        )
        conditional = regime_metrics(
            runs,
            regimes,
            config=regime_config,
            calibration=calibration,
            calibration_config=calibration_config,
        )
    return RiskResearchReport(
        calibration,
        regimes,
        conditional,
        historical_stress(
            runs,
            historical_scenarios,
            baseline=baseline,
            min_observations=(
                calibration_config.min_observations if calibration_config else 20
            ),
        ),
        synthetic_stress(runs, synthetic_scenarios, exposures=exposures),
        {
            name: {"turnover": compute_turnover(run), "weights": analyze_weights(run)}
            for name, run in runs.items()
        },
        {
            "risk_report_version": "1.0",
            "runs": {name: run.metadata for name, run in runs.items()},
            "analysis_only": True,
            "performance_basis": "gross saved walk-forward paths",
            "limitations": "descriptive research; no regulatory VaR approval, macro prediction, causal inference or stress probability",
        },
    )
