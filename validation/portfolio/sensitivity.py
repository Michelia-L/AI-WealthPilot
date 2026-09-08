"""One-factor research experiments, all evaluated by the shared walk-forward loop."""

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from .comparison import ComparisonReport, compare_runs, require_same_protocol
from .costs import CostConfig
from .robustness import summarize, weight_distance
from .strategies import supports_expected_return_shifts
from .walk_forward import ValidationRun, WalkForwardConfig, _json_safe, evaluate

COVARIANCE_DEPENDENT = {"min_variance", "mvo", "resampled_mvo", "erc"}


@dataclass(frozen=True)
class SensitivityConfig:
    return_shocks: tuple[float, ...] = (-0.02, -0.01, -0.005, 0.005, 0.01, 0.02)
    shock_assets: tuple[str, ...] | None = None
    random_draws: int = 0
    random_scale: float = 0.01
    random_seed: int = 0
    covariance_methods: tuple[str, ...] = ("sample", "ledoit-wolf", "oas")
    training_windows: tuple[int, ...] = (24, 36, 60)
    include_expanding: bool = True
    concentration_threshold: float = 0.8

    def __post_init__(self):
        if any(not np.isfinite(v) for v in self.return_shocks) or len(
            set(self.return_shocks)
        ) != len(self.return_shocks):
            raise ValueError("Return shocks must be unique finite annual offsets")
        if (
            type(self.random_draws) is not int
            or self.random_draws < 0
            or type(self.random_seed) is not int
            or self.random_seed < 0
        ):
            raise ValueError("Random draw count and seed must be nonnegative integers")
        if not np.isfinite(self.random_scale) or self.random_scale < 0:
            raise ValueError("random_scale must be finite and nonnegative")
        if set(self.covariance_methods) - {"sample", "ledoit-wolf", "oas"} or len(
            set(self.covariance_methods)
        ) != len(self.covariance_methods):
            raise ValueError("Covariance methods must be unique supported estimators")
        if any(type(v) is not int or v < 1 for v in self.training_windows) or len(
            set(self.training_windows)
        ) != len(self.training_windows):
            raise ValueError("Training windows must be unique positive month counts")
        if (
            not np.isfinite(self.concentration_threshold)
            or not 0 < self.concentration_threshold <= 1
        ):
            raise ValueError("concentration_threshold must be in (0, 1]")
        if type(self.include_expanding) is not bool:
            raise ValueError("include_expanding must be boolean")


def compare_allocations(
    base: ValidationRun, variant: ValidationRun, *, concentration_threshold: float = 0.8
) -> dict:
    require_same_protocol({"base": base, "variant": variant})
    if not np.isfinite(concentration_threshold) or not 0 < concentration_threshold <= 1:
        raise ValueError("concentration_threshold must be in (0, 1]")
    rows = []
    for left, right in zip(base.rebalances, variant.rebalances, strict=True):
        row = {
            "as_of": left["as_of"],
            "base_allocation_status": left["allocation_status"],
            "variant_allocation_status": right["allocation_status"],
            "variant_reason": right["reason"],
            "same_eligible_universe": left["eligible_assets"]
            == right["eligible_assets"],
            "weight_distance": None,
            "asset_changes": None,
            "concentration_transition": None,
            "base_max_weight": None,
            "variant_max_weight": None,
        }
        if left["allocation_status"] == right["allocation_status"] == "ok":
            lw, rw = left["weights"], right["weights"]
            changes = {
                asset: rw.get(asset, 0) - lw.get(asset, 0)
                for asset in sorted(lw.keys() | rw.keys())
            }
            row.update(
                weight_distance=weight_distance(lw, rw),
                asset_changes=changes,
                base_max_weight=max(lw.values()),
                variant_max_weight=max(rw.values()),
                concentration_transition=max(lw.values())
                < concentration_threshold
                <= max(rw.values()),
            )
        rows.append(row)
    asset_summary = []
    for asset in base.metadata["config"]["universe"]:
        summary = summarize(
            abs(r["asset_changes"].get(asset, 0))
            if r["asset_changes"] is not None
            else None
            for r in rows
        )
        asset_summary.append({"asset": asset, **summary})
    asset_summary.sort(
        key=lambda item: (
            -(item["max"] if item["max"] is not None else -1),
            item["asset"],
        )
    )
    return {
        "per_rebalance": rows,
        "weight_distance": summarize(row["weight_distance"] for row in rows),
        "asset_changes": asset_summary,
        "concentration_transition_count": sum(
            r["concentration_transition"] is True for r in rows
        ),
        "concentration_threshold": concentration_threshold,
        "eligible_universe_changed_count": sum(
            not r["same_eligible_universe"] for r in rows
        ),
        "variant_allocation_failure_count": variant.metrics["allocation_failure_count"],
        "variant_skipped_period_count": variant.metrics["skipped_period_count"],
        "complete_pairs": all(row["weight_distance"] is not None for row in rows),
    }


@dataclass
class SensitivityReport:
    comparison: ComparisonReport
    changes: dict[str, dict]
    metadata: dict

    def to_dict(self) -> dict:
        return _json_safe(
            {
                "metadata": self.metadata,
                "changes": self.changes,
                "comparison": self.comparison.to_dict(),
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, allow_nan=False)


def run_sensitivity(
    returns: pd.DataFrame,
    config: WalkForwardConfig,
    experiments: SensitivityConfig | None = None,
    costs: CostConfig | None = None,
) -> SensitivityReport:
    """Run base plus one-factor mu/covariance/window scenarios (not a grid).

    Each mu shock is an annual offset vector fixed before the run and added to
    the historical mean at each as_of. Returns, covariance input, optimizer seed,
    constraints and holding data stay unchanged. Window experiments may alter
    eligibility, which is reported rather than intersected using hindsight.
    """
    experiments = experiments or SensitivityConfig()
    if config.strategy.name == "custom":
        raise ValueError(
            "Sensitivity adapters currently support built-in strategies only"
        )
    assets = (
        tuple(config.universe)
        if experiments.shock_assets is None
        else experiments.shock_assets
    )
    if (
        not assets
        or len(set(assets)) != len(assets)
        or set(assets) - set(config.universe)
    ):
        raise ValueError(
            "Shock assets must be unique members of the configured universe"
        )
    variants = {"base": deepcopy(config)}
    definitions = {"base": {"kind": "base"}}
    skipped = []

    def add_shift(name, shifts, kind):
        total = dict(config.strategy.expected_return_shifts)
        for asset, shift in shifts.items():
            total[asset] = total.get(asset, 0.0) + float(shift)
        total = {asset: shift for asset, shift in total.items() if shift != 0}
        variants[name] = replace(
            config, strategy=replace(config.strategy, expected_return_shifts=total)
        )
        definitions[name] = {"kind": kind, "annual_offsets": shifts}

    if supports_expected_return_shifts(config.strategy):
        for i, shock in enumerate(experiments.return_shocks):
            add_shift(f"mu_{i}", dict.fromkeys(assets, float(shock)), "expected_return")
        rng = np.random.default_rng(experiments.random_seed)
        for i in range(experiments.random_draws):
            shifts = dict(
                zip(
                    assets,
                    rng.normal(0, experiments.random_scale, len(assets)).tolist(),
                    strict=True,
                )
            )
            add_shift(f"mu_random_{i}", shifts, "random_expected_return")
    elif experiments.return_shocks or experiments.random_draws:
        skipped.append(
            {
                "kind": "expected_return",
                "reason": "expected_return_override_not_supported"
                if config.strategy.name == "mean_cvar"
                and config.strategy.parameters.get("target_return") is not None
                else "strategy_not_return_dependent",
            }
        )

    if config.strategy.name in COVARIANCE_DEPENDENT:
        for method in experiments.covariance_methods:
            if method != config.covariance_method:
                name = f"covariance_{method}"
                variants[name] = replace(config, covariance_method=method)
                definitions[name] = {"kind": "covariance", "method": method}
    elif experiments.covariance_methods:
        skipped.append(
            {"kind": "covariance", "reason": "allocation_not_covariance_dependent"}
        )

    for months in experiments.training_windows:
        if config.window_type != "rolling" or months != config.training_window:
            name = f"window_{months}m"
            variants[name] = replace(
                config, training_window=months, window_type="rolling"
            )
            definitions[name] = {
                "kind": "training_window",
                "months": months,
                "window_type": "rolling",
            }
    if experiments.include_expanding and config.window_type != "expanding":
        variants["window_expanding"] = replace(config, window_type="expanding")
        definitions["window_expanding"] = {
            "kind": "training_window",
            "months": config.training_window,
            "window_type": "expanding",
        }

    runs = {}
    cache = {}
    for name, variant in variants.items():
        key = json.dumps(_json_safe(asdict(variant)), sort_keys=True)
        if key not in cache:
            cache[key] = evaluate(returns, variant)
        runs[name] = cache[key]
    comparison = compare_runs(runs, costs)
    changes = {
        name: compare_allocations(
            runs["base"],
            run,
            concentration_threshold=experiments.concentration_threshold,
        )
        for name, run in runs.items()
        if name != "base"
    }
    for row in comparison.rows:
        change = changes.get(row["name"])
        row["experiment_kind"] = definitions[row["name"]]["kind"]
        row["annual_offset_change"] = definitions[row["name"]].get("annual_offsets")
        base_distance = (
            0.0
            if all(r["allocation_status"] == "ok" for r in runs["base"].rebalances)
            else None
        )
        row["mean_weight_distance_from_base"] = (
            change["weight_distance"]["mean"] if change else base_distance
        )
        row["max_weight_distance_from_base"] = (
            change["weight_distance"]["max"] if change else base_distance
        )
        row["eligible_universe_changed_count"] = (
            change["eligible_universe_changed_count"] if change else 0
        )
    return SensitivityReport(
        comparison,
        changes,
        {
            "sensitivity_version": "1.0",
            "config": asdict(experiments),
            "definitions": definitions,
            "skipped_experiments": skipped,
            "design": "one factor at a time; no optimizer tuning or selection using holding returns",
            "random_shock_policy": "independent Gaussian annual offsets per selected asset; same vector at every decision",
            "optimizer_seed": config.random_seed,
            "concentration_policy": "transition when max target weight crosses the configured threshold from below",
        },
    )
