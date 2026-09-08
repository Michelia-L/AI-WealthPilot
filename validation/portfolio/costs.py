"""Post-process saved OOS paths under explicit one-way turnover cost scenarios."""

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR

from .metrics import compute_metrics
from .robustness import analyze_weights, summarize, weight_distance
from .walk_forward import ValidationRun, _json_safe


@dataclass(frozen=True)
class CostConfig:
    rates_bps: tuple[float, ...] = (0, 5, 10, 25, 50)
    turnover_method: str = "drift"
    charge_initial: bool = False

    def __post_init__(self):
        if (
            not self.rates_bps
            or len(set(self.rates_bps)) != len(self.rates_bps)
            or any(
                not np.isfinite(rate) or not 0 <= rate <= 10000
                for rate in self.rates_bps
            )
        ):
            raise ValueError(
                "Cost scenarios must be unique finite bps rates in [0, 10000]"
            )
        if self.turnover_method not in {"drift", "target"}:
            raise ValueError("turnover_method must be drift or target")
        if type(self.charge_initial) is not bool:
            raise ValueError("charge_initial must be boolean")


def compute_turnover(run: ValidationRun, config: CostConfig | None = None) -> dict:
    config = config or CostConfig()
    records = []
    previous = None
    for i, record in enumerate(run.rebalances):
        turnover = None
        pretrade = None
        reason = None
        weights = record["weights"]
        if record["allocation_status"] != "ok":
            reason = "allocation_unavailable"
        elif i == 0:
            # Exclude initialization by assuming capital starts in the first
            # target, or charge a full allocation from cash (one-way turnover 1).
            turnover = 1.0 if config.charge_initial else 0.0
        else:
            if config.turnover_method == "target":
                pretrade = (
                    previous["weights"]
                    if previous["allocation_status"] == "ok"
                    else None
                )
            elif previous["status"] == "ok":
                pretrade = previous.get("ending_weights")
            if pretrade:
                turnover = weight_distance(weights, pretrade)
            else:
                reason = "previous_weights_unavailable"
        records.append(
            {
                "as_of": record["as_of"],
                "turnover": turnover,
                "pretrade_weights": pretrade,
                "initial_allocation": i == 0,
                "reason": reason,
            }
        )
        previous = record
    values = [r["turnover"] for r in records]
    summary = summarize(values if config.charge_initial else values[1:])
    complete = all(v is not None for v in values) and bool(run.metrics["complete"])
    years = len(run.returns) / TRADING_DAYS_PER_YEAR
    summary.update(
        annualized=float(sum(values) / years) if complete and years else None,
        complete=complete,
        full_reallocation_count=sum(
            v is not None and v >= 1 - 1e-8
            for v in (values if config.charge_initial else values[1:])
        ),
    )
    return {"per_rebalance": records, "summary": summary}


@dataclass
class CostScenario:
    rate_bps: float
    returns: pd.Series
    nav: pd.Series
    daily_costs: pd.Series
    rebalances: list[dict]
    metrics: dict

    def to_dict(self) -> dict:
        return _json_safe(
            {
                "rate_bps": self.rate_bps,
                "metrics": self.metrics,
                "rebalances": self.rebalances,
                "series": [
                    {
                        "date": date,
                        "return": ret,
                        "nav": self.nav.loc[date],
                        "cost_fraction": self.daily_costs.loc[date],
                    }
                    for date, ret in self.returns.items()
                ],
            }
        )


@dataclass
class ImplementationReport:
    gross: ValidationRun
    scenarios: list[CostScenario]
    turnover: dict
    weights: dict
    metadata: dict

    def to_dict(self) -> dict:
        return _json_safe(
            {
                "metadata": self.metadata,
                "gross": self.gross.to_dict(),
                "turnover": self.turnover,
                "weights": self.weights,
                "scenarios": [s.to_dict() for s in self.scenarios],
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, allow_nan=False)


def analyze_costs(
    run: ValidationRun, config: CostConfig | None = None
) -> ImplementationReport:
    """No fitting or market-data access. Debit turnover * bps/10000 once/window.

    The cost is subtracted from the first observed daily return in the holding
    window (as a fraction of opening NAV). Other daily returns stay unchanged.
    Costs do not alter the original target or drift path; this is a first-order
    proportional-cost overlay, not a self-financing trade or execution simulator.
    """
    config = config or CostConfig()
    turnover = compute_turnover(run, config)
    scenarios = []
    for rate in config.rates_bps:
        net = run.returns.copy().rename("net_return")
        daily_costs = pd.Series(0.0, index=net.index, name="cost_fraction")
        records = []
        for record, trade in zip(
            run.rebalances, turnover["per_rebalance"], strict=True
        ):
            dates = net.index[
                (net.index > record["as_of"]) & (net.index <= record["holding_end"])
            ]
            cost = (
                0.0
                if rate == 0
                else trade["turnover"] * rate / 10000
                if trade["turnover"] is not None
                else None
            )
            reason = None
            if cost is None:
                reason = "turnover_unavailable"
                net.loc[dates] = np.nan
                daily_costs.loc[dates] = np.nan
            elif len(dates):
                daily_costs.loc[dates[0]] = cost
                net.loc[dates[0]] -= cost
                if net.loc[dates[0]] < -1:
                    reason = "cost_exceeds_capital"
                    net.loc[dates] = np.nan
            if record["status"] != "ok":
                reason = reason or "gross_period_unavailable"
            records.append(
                {
                    "as_of": record["as_of"],
                    "holding_start": record["holding_start"],
                    "turnover": trade["turnover"],
                    "cost_fraction": cost,
                    "status": "failed" if reason else "ok",
                    "reason": reason,
                }
            )
        failures = [r for r in records if r["status"] != "ok"]
        nav = (1 + net).cumprod(skipna=False).rename("net_nav")
        if failures:
            nav.loc[nav.index >= failures[0]["holding_start"]] = np.nan
        metrics = compute_metrics(
            net, run.metadata["config"]["risk_free_rate"], periods_complete=not failures
        )
        complete = run.metrics["complete"] and metrics["complete"]
        metrics.update(
            gross_cagr=run.metrics["cagr"],
            net_cagr=metrics["cagr"],
            gross_sharpe=run.metrics["sharpe"],
            net_sharpe=metrics["sharpe"],
            cumulative_cost_drag=float(run.nav.iloc[-1] - nav.iloc[-1])
            if complete
            else None,
            cumulative_cost_paid=float(
                (nav.shift(1, fill_value=1.0) * daily_costs).sum()
            )
            if complete
            else None,
            cost_fraction_sum=float(daily_costs.sum()) if complete else None,
            annualized_turnover=turnover["summary"]["annualized"],
        )
        scenarios.append(
            CostScenario(float(rate), net, nav, daily_costs, records, metrics)
        )
    return ImplementationReport(
        run,
        scenarios,
        turnover,
        analyze_weights(run),
        {
            "implementation_version": "1.0",
            "config": asdict(config),
            "cost_convention": "net first holding-day return = gross return - one-way turnover * rate_bps / 10000",
            "cost_basis": "rate per unit of one-way turnover, not per sum of buys and sells",
            "initial_allocation": "full allocation from cash"
            if config.charge_initial
            else "capital starts at first target; no initial cost",
            "annualization_days": TRADING_DAYS_PER_YEAR,
            "cost_drag_units": "difference in final NAV per unit of initial capital; includes foregone compounding",
            "missing_policy": "unknown turnover with positive costs invalidates net period; never bridge NAV gaps",
        },
    )
