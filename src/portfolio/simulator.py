"""
Monte Carlo simulator for goal-based portfolio planning.

Simulates portfolio value paths using Geometric Brownian Motion (GBM)
with optional contributions/withdrawals. Supports two-phase retirement
planning (accumulation → distribution) with survival rate estimation.

    - Glasserman (2003). Monte Carlo Methods in Financial Engineering.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional

from src.config import MONTE_CARLO_SIMULATIONS, MONTE_CARLO_YEARS, TRADING_DAYS_PER_YEAR


@dataclass
class SimulationResult:
    """Container for Monte Carlo simulation results."""

    paths: np.ndarray
    terminal_values: np.ndarray
    mean_terminal: float
    median_terminal: float
    percentile_5: float
    percentile_25: float
    percentile_75: float
    percentile_95: float
    goal_amount: Optional[float] = None
    probability_of_success: Optional[float] = None

    def summary(self) -> str:
        """Human-readable summary of simulation results."""
        lines = [
            "Monte Carlo Simulation Results",
            f"  Simulations: {len(self.terminal_values):,}",
            f"  Mean terminal value: ${self.mean_terminal:,.0f}",
            f"  Median terminal value: ${self.median_terminal:,.0f}",
            f"  5th percentile: ${self.percentile_5:,.0f}",
            f"  95th percentile: ${self.percentile_95:,.0f}",
        ]
        if self.goal_amount is not None:
            lines.append(f"  Goal: ${self.goal_amount:,.0f}")
            lines.append(
                f"  Probability of success: {self.probability_of_success:.1%}"
            )
        return "\n".join(lines)


class MonteCarloSimulator:
    """Monte Carlo simulator using GBM for portfolio planning."""

    def __init__(
        self,
        expected_return: float,
        volatility: float,
        n_simulations: int = MONTE_CARLO_SIMULATIONS,
        n_years: int = MONTE_CARLO_YEARS,
        seed: Optional[int] = None,
    ):
        """Initialize simulator.

        Args:
            expected_return: Annualized expected return (e.g. 0.08).
            volatility: Annualized volatility (e.g. 0.15).
            n_simulations: Number of simulation paths.
            n_years: Projection horizon in years.
            seed: Random seed for reproducibility.
        """
        self.expected_return = expected_return
        self.volatility = volatility
        self.n_simulations = n_simulations
        self.n_years = n_years
        self.rng = np.random.default_rng(seed)

    def simulate(
        self,
        initial_value: float,
        annual_contribution: float = 0,
        annual_withdrawal: float = 0,
        goal_amount: Optional[float] = None,
    ) -> SimulationResult:
        """Run Monte Carlo simulation with annual GBM steps.

        Each step: V_{t+1} = V_t × exp(drift + σZ) + C - W
        where drift = μ - 0.5σ² (Jensen's inequality correction).

        Args:
            initial_value: Starting portfolio value.
            annual_contribution: Yearly addition.
            annual_withdrawal: Yearly withdrawal.
            goal_amount: Target value for success probability.

        Returns:
            SimulationResult with all paths and statistics.
        """
        n_periods = self.n_years
        paths = np.zeros((self.n_simulations, n_periods + 1))
        paths[:, 0] = initial_value

        # drift = μ - 0.5σ² corrects for volatility drag
        drift = self.expected_return - 0.5 * self.volatility**2

        for t in range(1, n_periods + 1):
            z = self.rng.standard_normal(self.n_simulations)
            growth = np.exp(drift + self.volatility * z)
            paths[:, t] = paths[:, t - 1] * growth + annual_contribution - annual_withdrawal
            paths[:, t] = np.maximum(paths[:, t], 0)

        terminal = paths[:, -1]
        return SimulationResult(
            paths=paths,
            terminal_values=terminal,
            mean_terminal=float(np.mean(terminal)),
            median_terminal=float(np.median(terminal)),
            percentile_5=float(np.percentile(terminal, 5)),
            percentile_25=float(np.percentile(terminal, 25)),
            percentile_75=float(np.percentile(terminal, 75)),
            percentile_95=float(np.percentile(terminal, 95)),
            goal_amount=goal_amount,
            probability_of_success=(
                float(np.mean(terminal >= goal_amount))
                if goal_amount is not None
                else None
            ),
        )

    def _distribution_phase(
        self,
        terminal_values: np.ndarray,
        dist_years: int,
        desired_annual_income: float,
        accum_years: int,
        inflation_rate: float,
        distribution_inflation_rate: float,
        withdrawal_strategy: str,
        guardrail_band: float,
        guardrail_adjust: float,
        seed: int,
    ) -> np.ndarray:
        """Distribution-phase paths under one withdrawal strategy.

        fixed: withdrawals are purely inflation-adjusted (rigid spending).
        guardrails: simplified Guyton-Klinger (2006) rules — each path
        anchors its initial withdrawal rate WR0 = W0 / V0 at retirement;
        every year the tentative withdrawal steps up with the distribution
        inflation rate, then

            current WR > WR0 × (1 + band)  →  cut by `guardrail_adjust`
                                               (capital-preservation rule)
            current WR < WR0 × (1 − band)  →  raise by `guardrail_adjust`
                                               (prosperity rule)

        All operations are vectorized across paths; depleted paths keep a
        zero balance (their WR reads as +inf, so no rule fires).

        References:
            - Guyton & Klinger (2006). Decision Rules for Portfolio
              Withdrawal. Journal of Financial Planning.
        """
        # 30% reduced return/vol for the conservative retirement shift.
        conservative_return = self.expected_return * 0.7
        conservative_vol = self.volatility * 0.7
        drift = conservative_return - 0.5 * conservative_vol ** 2

        dist_paths = np.zeros((self.n_simulations, dist_years + 1))
        dist_paths[:, 0] = terminal_values
        rng = np.random.default_rng(seed)

        if withdrawal_strategy == "guardrails":
            # First-year withdrawal matches the fixed schedule at t=1.
            w0 = (
                desired_annual_income
                * (1.0 + inflation_rate) ** accum_years
                * (1.0 + distribution_inflation_rate)
            )
            with np.errstate(divide="ignore", invalid="ignore"):
                wr0 = np.where(terminal_values > 0, w0 / terminal_values, np.inf)
            withdrawals = np.full(self.n_simulations, w0)

        for t in range(1, dist_years + 1):
            z = rng.standard_normal(self.n_simulations)
            growth = np.exp(drift + conservative_vol * z)

            if withdrawal_strategy == "guardrails":
                prev = dist_paths[:, t - 1]
                tentative = withdrawals * (1.0 + distribution_inflation_rate)
                with np.errstate(divide="ignore", invalid="ignore"):
                    current_wr = np.where(prev > 0, tentative / prev, np.inf)
                cut = current_wr > wr0 * (1.0 + guardrail_band)
                boost = current_wr < wr0 * (1.0 - guardrail_band)
                tentative = np.where(
                    cut, tentative * (1.0 - guardrail_adjust), tentative
                )
                tentative = np.where(
                    boost, tentative * (1.0 + guardrail_adjust), tentative
                )
                withdrawals = tentative
                dist_paths[:, t] = np.maximum(prev * growth - tentative, 0)
            else:
                # Inflate withdrawal to nominal terms: the target income (in
                # today's money) is eroded by the accumulation-phase rate
                # until retirement, then by the distribution-phase rate.
                inflation_factor = (
                    (1.0 + inflation_rate) ** accum_years
                    * (1.0 + distribution_inflation_rate) ** t
                )
                nominal_withdrawal = desired_annual_income * inflation_factor
                dist_paths[:, t] = dist_paths[:, t - 1] * growth - nominal_withdrawal
                dist_paths[:, t] = np.maximum(dist_paths[:, t], 0)

        return dist_paths

    def retirement_planning(
        self,
        current_age: int,
        retirement_age: int,
        life_expectancy: int,
        current_savings: float,
        annual_savings: float,
        desired_annual_income: float,
        inflation_rate: float = 0.025,
        distribution_inflation_rate: Optional[float] = None,
        withdrawal_strategy: str = "fixed",
        guardrail_band: float = 0.2,
        guardrail_adjust: float = 0.1,
    ) -> dict:
        """Two-phase retirement simulation: accumulation then distribution.

        Phase 1 (accumulation): client saves until retirement_age.
        Phase 2 (distribution): client withdraws with 30% reduced
        return/vol (conservative shift) and inflation-adjusted withdrawals,
        optionally moderated by Guyton-Klinger guardrails.

        Args:
            current_age: Client's current age.
            retirement_age: Target retirement age.
            life_expectancy: Planning horizon end age.
            current_savings: Current portfolio value.
            annual_savings: Yearly savings during accumulation.
            desired_annual_income: Annual income needed in retirement (today's $).
            inflation_rate: Annual inflation during the accumulation phase.
            distribution_inflation_rate: Annual inflation during the
                distribution phase. Defaults to inflation_rate (single-rate
                legacy behavior). Retirees spend out of an elderly
                (healthcare-tilted) basket, so a CPI-E-style rate higher
                than the accumulation-phase generic CPI is often the
                better assumption — see src.portfolio.inflation.
            withdrawal_strategy: 'fixed' (rigid inflation-adjusted) or
                'guardrails' (Guyton-Klinger capital-preservation and
                prosperity rules around the initial withdrawal rate).
            guardrail_band: Relative band around the initial withdrawal
                rate that triggers an adjustment (0.2 = ±20%).
            guardrail_adjust: Withdrawal cut/raise applied when a rule
                fires (0.1 = ∓10%).

        Returns:
            Dict with 'accumulation', 'distribution_paths', 'survival_rate',
            'accumulation_years', 'distribution_years', 'withdrawal_strategy';
            under 'guardrails', also 'baseline_survival_rate' — the fixed-
            strategy survival computed on the SAME random draws (common
            random numbers keep the comparison honest).
        """
        if withdrawal_strategy not in ("fixed", "guardrails"):
            raise ValueError(
                f"Unknown withdrawal strategy: {withdrawal_strategy}. "
                "Supported: 'fixed', 'guardrails'."
            )
        if distribution_inflation_rate is None:
            distribution_inflation_rate = inflation_rate
        # Phase 1: Accumulation
        accum_years = retirement_age - current_age
        accum_sim = MonteCarloSimulator(
            expected_return=self.expected_return,
            volatility=self.volatility,
            n_simulations=self.n_simulations,
            n_years=accum_years,
            seed=self.rng.integers(0, 2**31),
        )
        accum_result = accum_sim.simulate(
            initial_value=current_savings,
            annual_contribution=annual_savings,
        )

        # Phase 2: Distribution
        dist_years = life_expectancy - retirement_age
        dist_seed = int(self.rng.integers(0, 2**31))

        dist_paths = self._distribution_phase(
            accum_result.terminal_values, dist_years, desired_annual_income,
            accum_years, inflation_rate, distribution_inflation_rate,
            withdrawal_strategy, guardrail_band, guardrail_adjust, dist_seed,
        )

        # Survival rate: fraction of paths that never hit zero
        never_depleted = np.all(dist_paths > 0, axis=1)
        survival_rate = float(np.mean(never_depleted))

        result = {
            "accumulation": accum_result,
            "distribution_paths": dist_paths,
            "survival_rate": survival_rate,
            "accumulation_years": accum_years,
            "distribution_years": dist_years,
            "withdrawal_strategy": withdrawal_strategy,
        }

        if withdrawal_strategy == "guardrails":
            # Fixed-strategy baseline on identical draws.
            baseline_paths = self._distribution_phase(
                accum_result.terminal_values, dist_years, desired_annual_income,
                accum_years, inflation_rate, distribution_inflation_rate,
                "fixed", guardrail_band, guardrail_adjust, dist_seed,
            )
            result["baseline_survival_rate"] = float(
                np.mean(np.all(baseline_paths > 0, axis=1))
            )

        return result


if __name__ == "__main__":
    sim = MonteCarloSimulator(
        expected_return=0.08,
        volatility=0.15,
        n_simulations=10000,
        seed=42,
    )
    result = sim.retirement_planning(
        current_age=30,
        retirement_age=60,
        life_expectancy=85,
        current_savings=100000,
        annual_savings=50000,
        desired_annual_income=200000,
    )
    print("=== Retirement Planning Simulation ===")
    print(f"Accumulation phase: {result['accumulation_years']} years")
    print(result["accumulation"].summary())
    print(f"\nDistribution phase: {result['distribution_years']} years")
    print(f"Portfolio survival rate: {result['survival_rate']:.1%}")
