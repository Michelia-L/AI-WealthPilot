"""Complete, manually valued holdings snapshots and valuation comparisons.

All amounts (including unit prices and cost basis) use the IPS base currency.
No proxy price, FX rate, or return is inferred from quantities or cost basis.
"""

import math
from datetime import date


class HoldingValidationError(ValueError):
    """Stable validation code translated by the API's locale table."""


def value_snapshot(payload: dict, context: dict) -> dict:
    """Validate business invariants and value each line in a complete snapshot."""
    if payload["base_currency"] != context["base_currency"]:
        raise HoldingValidationError("currency")
    as_of = date.fromisoformat(payload["as_of"])
    if as_of > date.today():
        raise HoldingValidationError("future_date")
    allowed = {a["asset_class"] for a in context["assets"]}
    seen = set()
    valued = {}
    for row in payload["holdings"]:
        name = row["asset_class"]
        if name not in allowed:
            raise HoldingValidationError("asset")
        if name in seen:
            raise HoldingValidationError("duplicate")
        seen.add(name)
        amount, quantity, price = (
            row.get("market_value"),
            row.get("quantity"),
            row.get("unit_price"),
        )
        if amount is not None:
            if quantity is not None or price is not None:
                raise HoldingValidationError("valuation")
        elif quantity is None or price is None:
            raise HoldingValidationError("valuation")
        else:
            amount = quantity * price
        if not math.isfinite(amount) or amount < 0:
            raise HoldingValidationError("total")
        cost_date = row.get("cost_basis_date")
        if (row.get("cost_basis") is not None and not cost_date) or (
            cost_date and date.fromisoformat(cost_date) > as_of
        ):
            raise HoldingValidationError("cost_date")
        valued[name] = {**row, "market_value": amount}

    # Persist zero positions too: omitted assets mean no holding, never a
    # fallback to target weights. This also makes disposals visible in history.
    for name in allowed:
        valued.setdefault(name, {"asset_class": name, "market_value": 0.0})
    total = sum(row["market_value"] for row in valued.values())
    if not math.isfinite(total) or total <= 0:
        raise HoldingValidationError("total")
    holdings = [
        {
            **valued[a["asset_class"]],
            "weight": valued[a["asset_class"]]["market_value"] / total,
        }
        for a in context["assets"]
    ]
    return {**payload, "total_market_value": total, "holdings": holdings}


def compare_snapshots(current: dict, previous: dict | None) -> dict:
    """Changes between valuations include flows and must not be called returns."""
    result = {**current, "holdings": [dict(h) for h in current["holdings"]]}
    if previous is None or previous["base_currency"] != current["base_currency"]:
        return result
    prior = {h["asset_class"]: h for h in previous["holdings"]}
    result["previous_snapshot_id"] = previous["id"]
    result["total_market_value_change"] = (
        current["total_market_value"] - previous["total_market_value"]
    )
    for h in result["holdings"]:
        old = prior.get(h["asset_class"], {"market_value": 0.0, "weight": 0.0})
        h["market_value_change"] = h["market_value"] - old["market_value"]
        h["weight_change"] = h["weight"] - old["weight"]
    return result


def apply_actual_holdings(holdings: list[dict], snapshot: dict) -> None:
    """Attach snapshot weights; policy bands and CME remain shared with simulation."""
    by_name = {h["asset_class"]: h for h in snapshot["holdings"]}
    for h in holdings:
        row = by_name.get(h["name"])
        h["market_value"] = row["market_value"] if row else 0.0
        h["drifted_weight"] = h["market_value"] / snapshot["total_market_value"]
        h["period_return"] = None
