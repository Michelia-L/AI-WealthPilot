"""CME forecast calibration with explicit maturity and source-quality cohorts."""

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from validation.portfolio.walk_forward import _json_safe

from .realized import evaluation_day, horizon_window, realized_asset
from .vintages import CMEVintage


@dataclass(frozen=True)
class CalibrationConfig:
    horizons: tuple[int, ...] = (1, 3, 5)
    min_observations_per_year: int = 126
    min_vintages: int = 3
    min_rank_assets: int = 3
    material_underprediction_ratio: float = 1.5
    strict: bool = True

    def __post_init__(self):
        if (
            not self.horizons
            or len(set(self.horizons)) != len(self.horizons)
            or any(type(h) is not int or h < 1 for h in self.horizons)
        ):
            raise ValueError("Horizons must be unique positive integer years")
        for field, minimum in (
            ("min_observations_per_year", 2),
            ("min_vintages", 1),
            ("min_rank_assets", 2),
        ):
            if type(getattr(self, field)) is not int or getattr(self, field) < minimum:
                raise ValueError("Invalid calibration sample minimum")
        if (
            type(self.strict) is not bool
            or not np.isfinite(self.material_underprediction_ratio)
            or self.material_underprediction_ratio <= 1
        ):
            raise ValueError(
                "strict must be boolean and material risk ratio must exceed one"
            )


def source_quality(vintage, components=None, asset_key=None):
    relevant = [
        s.quality
        for s in vintage.sources
        if (components is None or s.component in components)
        and (asset_key is None or s.asset_key in (None, asset_key))
    ]
    priority = {"fresh": 0, "cached": 1, "stale": 2, "fallback": 3, "unknown": 4}
    return max(relevant, key=priority.get) if relevant else "unknown"


def identity(vintage):
    return {
        "vintage_id": vintage.vintage_id,
        "as_of": vintage.as_of.isoformat(),
        "model_version": vintage.model_version,
        "code_version": vintage.code_version,
        "vintage_type": vintage.vintage_type,
        "base_currency": vintage.base_currency,
        "fx_treatment": vintage.fx_treatment,
        "cache_status": vintage.cache_status,
        "source_quality": source_quality(vintage),
        "lookback_years": vintage.lookback_years,
        "inflation_assumption": vintage.inflation_assumption,
        "iv_blending_tau": vintage.iv_blending_tau,
        "forward_blending_omega": vintage.forward_blending_omega,
    }


def error_summary(rows, error_key, min_vintages):
    valid = [r for r in rows if r.get(error_key) is not None]
    errors = np.asarray([r[error_key] for r in valid], dtype=float)
    dates = sorted({str(r["as_of"]) for r in valid})
    enough = len(dates) >= min_vintages
    return {
        "rows": len(rows),
        "observations": len(valid),
        "missing": len(rows) - len(valid),
        "vintage_dates": len(dates),
        "first_vintage": dates[0] if dates else None,
        "last_vintage": dates[-1] if dates else None,
        "status": "ok" if enough else "insufficient_vintages",
        "bias": float(errors.mean()) if enough else None,
        "mae": float(np.abs(errors).mean()) if enough else None,
        "rmse": float(np.sqrt(np.mean(errors**2))) if enough else None,
        "median_error": float(np.median(errors)) if enough else None,
        "median_absolute_error": float(np.median(np.abs(errors))) if enough else None,
        "min_error": float(errors.min()) if enough else None,
        "max_error": float(errors.max()) if enough else None,
    }


COHORT = (
    "model_version",
    "vintage_type",
    "base_currency",
    "fx_treatment",
    "cache_status",
    "source_quality",
    "horizon_years",
    "lookback_years",
    "inflation_assumption",
    "iv_blending_tau",
    "forward_blending_omega",
)


def grouped(rows, keys):
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        groups.setdefault(key, []).append(row)
    return [
        ({k: v for k, v in zip(keys, key, strict=True)}, values)
        for key, values in groups.items()
    ]


@dataclass
class CalibrationReport:
    asset_rows: list[dict]
    correlation_rows: list[dict]
    matrix_rows: list[dict]
    ranking_rows: list[dict]
    summaries: list[dict]
    metadata: dict

    def to_dict(self):
        return _json_safe(asdict(self))

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, allow_nan=False)

    def tables(self):
        return {
            name: pd.json_normalize(value)
            for name, value in self.to_dict().items()
            if name != "metadata"
        }


def calibrate(vintages, panel, *, evaluation_date, config=None):
    """Read immutable forecasts and supplied outcomes; never call a provider."""
    config = config or CalibrationConfig()
    panel.__post_init__()
    evaluation_date = evaluation_day(evaluation_date)
    vintages = tuple(
        CMEVintage.model_validate_json(v.canonical_json()) for v in vintages
    )
    if not vintages or len({v.vintage_id for v in vintages}) != len(vintages):
        raise ValueError("Supply nonempty unique vintages")
    for v in vintages:
        if (
            v.base_currency != panel.base_currency
            or v.fx_treatment != panel.fx_treatment
        ):
            raise ValueError("Forecast and realized currency/FX treatments must match")
    assets, pairs, matrices, rankings = [], [], [], []
    for vintage in vintages:
        issues = vintage.strict_issues()
        for horizon in config.horizons:
            end, sample, window_status = horizon_window(
                vintage, panel, horizon, evaluation_date
            )
            status = "unsuitable_vintage" if config.strict and issues else window_status
            common = {
                **identity(vintage),
                "horizon_years": horizon,
                "horizon_end": end,
                "strict_issues": issues,
                "strict_eligible": not issues,
            }
            local = []
            for asset in vintage.asset_classes:
                row = {
                    **common,
                    "asset_key": asset.key,
                    "ticker": asset.ticker,
                    "status": status,
                    "forecast_return": asset.expected_return,
                    "forecast_volatility": asset.blended_volatility
                    if asset.blended_volatility is not None
                    else asset.volatility,
                    "historical_return": asset.historical_return,
                    "historical_volatility": asset.volatility,
                    "forward_return": asset.forward_return,
                    "implied_volatility": asset.implied_volatility,
                    "forward_available": asset.forward_return is not None,
                    "implied_available": asset.implied_volatility is not None,
                    "return_source_quality": source_quality(
                        vintage,
                        {"history", "forward", "fx", "inflation", "risk_free"},
                        asset.key,
                    ),
                    "volatility_source_quality": source_quality(
                        vintage, {"history", "implied", "fx"}, asset.key
                    ),
                    "observations": 0,
                    "missing_observations": 0,
                    "first_observation": None,
                    "last_observation": None,
                    "realized_return": None,
                    "realized_arithmetic_return": None,
                    "realized_volatility": None,
                    "return_error": None,
                    "volatility_error": None,
                    "predicted_realized_ratio": None,
                    "underprediction": None,
                    "material_underprediction": None,
                }
                if status == "ok":
                    if panel.proxies.get(asset.key) != asset.ticker:
                        row["status"] = "proxy_mismatch"
                    else:
                        row.update(
                            realized_asset(
                                asset, sample, horizon, config.min_observations_per_year
                            )
                        )
                    if row["status"] == "ok":
                        predicted, realized = (
                            row["forecast_volatility"],
                            row["realized_volatility"],
                        )
                        row.update(
                            return_error=row["realized_return"]
                            - row["forecast_return"],
                            volatility_error=realized - predicted,
                            predicted_realized_ratio=predicted / realized
                            if realized > 0
                            else None,
                            underprediction=realized > predicted,
                            material_underprediction=realized
                            > predicted * config.material_underprediction_ratio,
                        )
                assets.append(row)
                local.append(row)
            local_pairs = []
            for i, a in enumerate(vintage.asset_classes):
                for j in range(i + 1, len(vintage.asset_classes)):
                    b = vintage.asset_classes[j]
                    predicted = vintage.correlation_matrix[i][j]
                    row = {
                        **common,
                        "asset_a": a.key,
                        "asset_b": b.key,
                        "status": status,
                        "forecast_correlation": predicted,
                        "realized_correlation": None,
                        "correlation_error": None,
                        "observations": 0,
                    }
                    if status == "ok":
                        if local[i]["status"] != "ok" or local[j]["status"] != "ok":
                            row["status"] = "incomplete_pair"
                        elif predicted is None:
                            row["status"] = "forecast_unavailable"
                        elif (
                            local[i]["realized_volatility"] <= 1e-12
                            or local[j]["realized_volatility"] <= 1e-12
                        ):
                            row["status"] = "constant_series"
                        else:
                            realized = float(sample[a.key].corr(sample[b.key]))
                            row.update(
                                realized_correlation=realized,
                                correlation_error=realized - predicted,
                                observations=len(sample),
                            )
                    pairs.append(row)
                    local_pairs.append(row)
            complete = bool(local_pairs) and all(
                r["correlation_error"] is not None for r in local_pairs
            )
            errors = [
                r["correlation_error"]
                for r in local_pairs
                if r["correlation_error"] is not None
            ]
            matrices.append(
                {
                    **common,
                    "status": "ok" if complete else "incomplete_matrix",
                    "pairs": len(local_pairs),
                    "observed_pairs": len(errors),
                    "mean_absolute_correlation_error": float(np.abs(errors).mean())
                    if complete
                    else None,
                    "frobenius_error": float(np.sqrt(2 * np.square(errors).sum()))
                    if complete
                    else None,
                    "largest_underestimated_pair": max(
                        local_pairs, key=lambda r: r["correlation_error"]
                    )["asset_a"]
                    + "/"
                    + max(local_pairs, key=lambda r: r["correlation_error"])["asset_b"]
                    if complete and max(errors) > 0
                    else None,
                    "largest_overestimated_pair": min(
                        local_pairs, key=lambda r: r["correlation_error"]
                    )["asset_a"]
                    + "/"
                    + min(local_pairs, key=lambda r: r["correlation_error"])["asset_b"]
                    if complete and min(errors) < 0
                    else None,
                }
            )
            rank_row = {
                **common,
                "status": "insufficient_assets",
                "assets": len(local),
                "observed_assets": sum(r["status"] == "ok" for r in local),
                "rank_correlation": None,
                "positive_rank_correlation": None,
                "forecast_dispersion": None,
                "realized_dispersion": None,
            }
            if (
                all(r["status"] == "ok" for r in local)
                and len(local) >= config.min_rank_assets
            ):
                forecast = [r["forecast_return"] for r in local]
                realized = [r["realized_return"] for r in local]
                rank_row.update(
                    forecast_dispersion=float(np.std(forecast, ddof=1)),
                    realized_dispersion=float(np.std(realized, ddof=1)),
                )
                if len(set(forecast)) > 1 and len(set(realized)) > 1:
                    rho = float(spearmanr(forecast, realized).statistic)
                    rank_row.update(
                        status="ok",
                        rank_correlation=rho,
                        positive_rank_correlation=rho > 0,
                    )
                else:
                    rank_row["status"] = "constant_ranks"
            rankings.append(rank_row)
    summaries = []
    for cohort, rows in grouped(
        assets,
        (
            *COHORT,
            "asset_key",
            "ticker",
            "forward_available",
            "implied_available",
            "return_source_quality",
            "volatility_source_quality",
        ),
    ):
        if len({row["as_of"] for row in rows}) != len(rows):
            raise ValueError(
                "Select one vintage per forecast date within each model/configuration/source cohort"
            )
        summary = {
            **cohort,
            "kind": "asset",
            "return": error_summary(rows, "return_error", config.min_vintages),
            "volatility": error_summary(rows, "volatility_error", config.min_vintages),
        }
        valid = [r for r in rows if r["volatility_error"] is not None]
        enough = summary["volatility"]["status"] == "ok"
        ratios = [
            r["predicted_realized_ratio"]
            for r in valid
            if r["predicted_realized_ratio"] is not None
        ]
        summary.update(
            mean_predicted_realized_ratio=float(np.mean(ratios))
            if enough and ratios
            else None,
            underprediction_frequency=float(
                np.mean([r["underprediction"] for r in valid])
            )
            if enough
            else None,
            material_underprediction_frequency=float(
                np.mean([r["material_underprediction"] for r in valid])
            )
            if enough
            else None,
        )
        summaries.append(summary)
    for cohort, rows in grouped(pairs, (*COHORT, "asset_a", "asset_b")):
        summaries.append(
            {
                **cohort,
                "kind": "correlation_pair",
                **error_summary(rows, "correlation_error", config.min_vintages),
            }
        )
    for cohort, rows in grouped(rankings, COHORT):
        valid = [r for r in rows if r["rank_correlation"] is not None]
        dates = len({r["as_of"] for r in valid})
        summaries.append(
            {
                **cohort,
                "kind": "ranking",
                "rows": len(rows),
                "observations": len(valid),
                "vintage_dates": dates,
                "mean_rank_correlation": float(
                    np.mean([r["rank_correlation"] for r in valid])
                )
                if dates >= config.min_vintages
                else None,
                "positive_rank_frequency": float(
                    np.mean([r["positive_rank_correlation"] for r in valid])
                )
                if dates >= config.min_vintages
                else None,
            }
        )
    return CalibrationReport(
        assets,
        pairs,
        matrices,
        rankings,
        summaries,
        {
            "calibration_version": "1.0",
            "config": asdict(config),
            "evaluation_date": evaluation_date.isoformat(),
            "realized_snapshot": panel.provenance(),
            "vintage_ids": [v.vintage_id for v in vintages],
            "return_convention": "calendar anniversary CAGR: exp(sum(log1p(daily returns))/H)-1; arithmetic annualized outcome also reported",
            "forecast_return_convention": "stored annual CME expected return; historical component is arithmetic, not a CAGR forecast",
            "volatility_convention": "daily sample std ddof=1 times sqrt(252), over (as_of, anniversary]",
            "correlation_convention": "daily Pearson on complete common horizon; off-diagonal pairs; full symmetric matrix Frobenius error only if all pairs valid",
            "sample_policy": "no missing-return deletion or proxy replacement; immature/unusable rows retained; minima count distinct forecast dates",
            "overlap_policy": "overlapping horizons are dependent descriptive observations, not independent samples; no significance claims",
            "strict_policy": "exclude unproven timing/revision vintages; observed and reconstructed, cache/source quality and model version never pooled",
        },
    )
