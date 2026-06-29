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

    def retirement_planning(
        self,
        current_age: int,
        retirement_age: int,
        life_expectancy: int,
        current_savings: float,
        annual_savings: float,
        desired_annual_income: float,
        inflation_rate: float = 0.025,
    ) -> dict:
        """Two-phase retirement simulation: accumulation then distribution.

        Phase 1 (accumulation): client saves until retirement_age.
        Phase 2 (distribution): client withdraws with 30% reduced
        return/vol (conservative shift) and inflation-adjusted withdrawals.

        Args:
            current_age: Client's current age.
            retirement_age: Target retirement age.
            life_expectancy: Planning horizon end age.
            current_savings: Current portfolio value.
            annual_savings: Yearly savings during accumulation.
            desired_annual_income: Annual income needed in retirement (today's $).
            inflation_rate: Annual inflation for withdrawal adjustment.

        Returns:
            Dict with 'accumulation', 'distribution_paths', 'survival_rate',
            'accumulation_years', 'distribution_years'.
        """
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

        # Phase 2: Distribution (30% reduced return/vol for conservative shift)
        dist_years = life_expectancy - retirement_age
        conservative_return = self.expected_return * 0.7
        conservative_vol = self.volatility * 0.7

        dist_paths = np.zeros((self.n_simulations, dist_years + 1))
        dist_paths[:, 0] = accum_result.terminal_values

        drift = conservative_return - 0.5 * conservative_vol ** 2
        rng = np.random.default_rng(self.rng.integers(0, 2**31))

        for t in range(1, dist_years + 1):
            z = rng.standard_normal(self.n_simulations)
            growth = np.exp(drift + conservative_vol * z)
            # Inflate withdrawal to nominal terms
            inflation_factor = (1.0 + inflation_rate) ** (accum_years + t)
            nominal_withdrawal = desired_annual_income * inflation_factor
            dist_paths[:, t] = dist_paths[:, t - 1] * growth - nominal_withdrawal
            dist_paths[:, t] = np.maximum(dist_paths[:, t], 0)

        # Survival rate: fraction of paths that never hit zero
        never_depleted = np.all(dist_paths > 0, axis=1)
        survival_rate = float(np.mean(never_depleted))

        return {
            "accumulation": accum_result,
            "distribution_paths": dist_paths,
            "survival_rate": survival_rate,
            "accumulation_years": accum_years,
            "distribution_years": dist_years,
        }


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
