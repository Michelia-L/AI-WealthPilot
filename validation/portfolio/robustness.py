"""Weight concentration and stability measurements on saved allocation paths."""

import numpy as np

from .walk_forward import ValidationRun


def weight_distance(left: dict[str, float], right: dict[str, float]) -> float:
    """One-way L1 distance on fully invested long-only portfolios (range 0..1)."""
    for weights in (left, right):
        values = np.asarray(list(weights.values()), dtype=float)
        if (
            not len(values)
            or not np.isfinite(values).all()
            or (values < 0).any()
            or not np.isclose(values.sum(), 1, atol=1e-8, rtol=0)
        ):
            raise ValueError("Weight distance requires normalized long-only portfolios")
    # The normalization tolerance must not turn a full reallocation into >100%.
    return min(
        1.0,
        float(
            0.5
            * sum(
                abs(left.get(a, 0) - right.get(a, 0))
                for a in sorted(left.keys() | right.keys())
            )
        ),
    )


def summarize(values) -> dict:
    """Keep missing counts explicit; summaries describe observed values only."""
    values = list(values)
    observed = np.asarray(
        [v for v in values if v is not None and np.isfinite(v)], dtype=float
    )
    result = {"observations": len(observed), "missing": len(values) - len(observed)}
    for key, fn in (
        ("mean", np.mean),
        ("median", np.median),
        ("p95", lambda x: np.quantile(x, 0.95)),
        ("max", np.max),
        ("min", np.min),
    ):
        result[key] = float(fn(observed)) if len(observed) else None
    return result


def analyze_weights(run: ValidationRun, *, bound_tolerance: float = 1e-8) -> dict:
    """Measure valid targets; never bridge an unsuccessful allocation."""
    if not np.isfinite(bound_tolerance) or not 0 <= bound_tolerance < 0.5:
        raise ValueError("bound_tolerance must be in [0, 0.5)")
    records = []
    history = []
    previous = None
    universe = run.metadata["config"]["universe"]
    for record in run.rebalances:
        weights = record["weights"] if record["allocation_status"] == "ok" else None
        row = {
            "as_of": record["as_of"],
            "max_weight": None,
            "effective_holdings": None,
            "target_distance": None,
            "lower_bound_fraction": None,
            "upper_bound_fraction": None,
        }
        if weights:
            # Validate saved weights and align inactive assets to zero.
            weight_distance(weights, weights)
            history.append([weights.get(a, 0) for a in universe])
            eligible_values = [weights.get(a, 0) for a in record["eligible_assets"]]
            row.update(
                max_weight=max(weights.values()),
                effective_holdings=1 / sum(w * w for w in weights.values()),
                target_distance=weight_distance(weights, previous)
                if previous is not None
                else None,
                lower_bound_fraction=float(
                    np.mean(np.asarray(eligible_values) <= bound_tolerance)
                ),
                upper_bound_fraction=float(
                    np.mean(np.asarray(eligible_values) >= 1 - bound_tolerance)
                ),
            )
        records.append(row)
        previous = weights
    asset_volatility = {
        asset: float(np.std(np.asarray(history)[:, i], ddof=1))
        if len(history) > 1
        else None
        for i, asset in enumerate(universe)
    }
    return {
        "per_rebalance": records,
        "max_weight": summarize(r["max_weight"] for r in records),
        "effective_holdings": summarize(r["effective_holdings"] for r in records),
        "target_distance": summarize(r["target_distance"] for r in records[1:]),
        "weight_volatility": asset_volatility,
        "lower_bound_fraction": summarize(r["lower_bound_fraction"] for r in records),
        "upper_bound_fraction": summarize(r["upper_bound_fraction"] for r in records),
        "predicted_volatility": summarize(
            r["diagnostics"].get("volatility") for r in run.rebalances
        ),
        "condition_number": summarize(
            r["diagnostics"].get("condition_number") for r in run.rebalances
        ),
        "nonfinite_condition_count": sum(
            r["diagnostics"].get("condition_number") is not None
            and not np.isfinite(r["diagnostics"]["condition_number"])
            for r in run.rebalances
        ),
        "regularized_count": sum(
            bool(r["diagnostics"].get("covariance_regularized")) for r in run.rebalances
        ),
        "bound_tolerance": bound_tolerance,
        "bound_policy": "0/1 bounds among eligible assets; ineligible assets excluded from bound frequency",
    }
