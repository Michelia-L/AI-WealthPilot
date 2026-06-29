"""
Portfolio optimization engine: MVO, Efficient Frontier, Black-Litterman.

Implements Markowitz mean-variance optimization with SLSQP solver,
resampled efficient frontiers (Michaud), and the Black-Litterman
Bayesian model for combining equilibrium returns with investor views.

References:
    - Markowitz, H. (1952). Portfolio Selection. Journal of Finance.
    - Black & Litterman (1992). Global Portfolio Optimization. FAJ.
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import Optional

from src.config import RISK_FREE_RATE, TRADING_DAYS_PER_YEAR


class PortfolioOptimizer:
    """Mean-Variance Portfolio Optimizer using scipy SLSQP.

    Given historical returns, computes optimal portfolio weights
    along the efficient frontier.
    """

    def __init__(
        self,
        returns: pd.DataFrame,
        risk_free_rate: float = RISK_FREE_RATE,
        covariance_method: str = 'sample',
    ):
        """Initialize with historical return data.

        Args:
            returns: DataFrame of daily asset returns (columns = assets).
            risk_free_rate: Annual risk-free rate.
            covariance_method: 'sample', 'ledoit-wolf', or 'oas'.
        """
        if covariance_method not in ['sample', 'ledoit-wolf', 'oas']:
            raise ValueError(
                f"Unknown covariance method: {covariance_method}. "
                f"Supported methods are 'sample', 'ledoit-wolf', 'oas'."
            )

        self.returns = returns
        self.n_assets = returns.shape[1]
        self.asset_names = returns.columns.tolist()
        self.risk_free_rate = risk_free_rate
        self.covariance_method = covariance_method

        # Annualize: μ = daily_mean × 252
        self.mean_returns = returns.mean() * TRADING_DAYS_PER_YEAR

        # Estimate annualized covariance matrix
        if covariance_method == 'ledoit-wolf':
            from sklearn.covariance import ledoit_wolf
            shrunk_cov, _ = ledoit_wolf(returns.values)
            self.cov_matrix = pd.DataFrame(
                shrunk_cov, index=returns.columns, columns=returns.columns,
            ) * TRADING_DAYS_PER_YEAR
        elif covariance_method == 'oas':
            from sklearn.covariance import oas
            shrunk_cov, _ = oas(returns.values)
            self.cov_matrix = pd.DataFrame(
                shrunk_cov, index=returns.columns, columns=returns.columns,
            ) * TRADING_DAYS_PER_YEAR
        else:
            self.cov_matrix = returns.cov() * TRADING_DAYS_PER_YEAR

        # Regularize if ill-conditioned
        self.condition_number = self._check_condition_number()
        if self.condition_number > 1e10:
            self.cov_matrix = self._regularize_covariance_matrix()
            self.is_regularized = True
        else:
            self.is_regularized = False

        self.cov_values = self.cov_matrix.values

    def _check_condition_number(self) -> float:
        """Check 2-norm condition number of the covariance matrix."""
        try:
            return np.linalg.cond(self.cov_matrix.values)
        except np.linalg.LinAlgError:
            return float('inf')

    def _regularize_covariance_matrix(
        self,
        epsilon: float = 1e-6,
        method: str = 'diagonal',
    ) -> pd.DataFrame:
        """Regularize covariance matrix for numerical stability.

        Args:
            epsilon: Regularization strength.
            method: 'diagonal' (Σ + εI) or 'eigenvalue' clipping.

        Returns:
            Regularized covariance DataFrame.
        """
        cov_values = self.cov_matrix.values

        if method == 'diagonal':
            # Σ_reg = Σ + ε × I
            regularized = cov_values + epsilon * np.eye(self.n_assets)
        elif method == 'eigenvalue':
            eigenvalues, eigenvectors = np.linalg.eigh(cov_values)
            regularized_eigenvalues = np.maximum(eigenvalues, epsilon)
            regularized = eigenvectors @ np.diag(regularized_eigenvalues) @ eigenvectors.T
        else:
            raise ValueError(f"Unknown regularization method: {method}")

        regularized = (regularized + regularized.T) / 2
        return pd.DataFrame(
            regularized,
            index=self.cov_matrix.index,
            columns=self.cov_matrix.columns,
        )

    def portfolio_performance(
        self,
        weights: np.ndarray,
        mean_override: Optional[np.ndarray] = None,
    ) -> tuple[float, float, float]:
        """Compute annualized return, volatility, and Sharpe for given weights.

        Args:
            weights: Portfolio weight array (must sum to 1).
            mean_override: Optional per-asset expected-return vector used in
                place of ``self.mean_returns``. The resampled-MVO path threads
                its Monte-Carlo draws through this argument rather than mutating
                ``self.mean_returns`` (which would race with concurrent readers
                and was restored via try/finally — see #1). Defaults to None.

        Returns:
            Tuple of (return, volatility, sharpe_ratio).
        """
        # R_p = w' × μ
        mean = mean_override if mean_override is not None else self.mean_returns
        portfolio_return = np.dot(weights, mean)
        # σ_p = √(w' × Σ × w)
        portfolio_volatility = np.sqrt(
            np.dot(weights.T, np.dot(self.cov_values, weights))
        )
        # Reporting context: zero volatility is degenerate; return Sharpe 0.
        # Objective functions (neg_sharpe) apply their own infeasibility penalty
        # — see maximize_sharpe / bl_maximize_sharpe (#5).
        sharpe_ratio = (
            (portfolio_return - self.risk_free_rate) / portfolio_volatility
            if portfolio_volatility > 0
            else 0
        )
        return portfolio_return, portfolio_volatility, sharpe_ratio

    def minimize_volatility(
        self,
        target_return: Optional[float] = None,
        allow_short: bool = False,
        mean_override: Optional[np.ndarray] = None,
    ) -> dict:
        """Find minimum volatility portfolio, optionally at a target return.

        Args:
            target_return: If set, constrains portfolio to this return level.
            allow_short: Allow negative weights.
            mean_override: Optional expected-return vector overriding
                ``self.mean_returns`` (used by the resampled-MVO path to avoid
                mutating instance state, #1). Defaults to None.

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
        """
        n = self.n_assets
        init_weights = np.ones(n) / n
        bounds = ((-1, 1) if allow_short else (0, 1),) * n
        cov = self.cov_values
        if mean_override is not None:
            mean_vals = np.asarray(mean_override, dtype=float)
        else:
            mean_vals = self.mean_returns.values

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
        if target_return is not None:
            constraints.append({
                "type": "eq",
                "fun": lambda w: np.dot(w, mean_vals) - target_return,
            })

        # Minimize variance (equivalent to min vol); Jacobian = 2Σw
        result = minimize(
            fun=lambda w: np.dot(w.T, np.dot(cov, w)),
            jac=lambda w: 2.0 * np.dot(cov, w),
            x0=init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        weights = result.x
        ret, vol, sharpe = self.portfolio_performance(weights, mean_override)
        return {
            "weights": dict(zip(self.asset_names, weights)),
            "return": ret,
            "volatility": vol,
            "sharpe": sharpe,
            "success": result.success,
        }

    def maximize_sharpe(
        self,
        allow_short: bool = False,
        mean_override: Optional[np.ndarray] = None,
    ) -> dict:
        """Find maximum Sharpe ratio portfolio (tangency portfolio).

        Args:
            allow_short: Allow negative weights.
            mean_override: Optional expected-return vector overriding
                ``self.mean_returns`` (used by the resampled-MVO path to avoid
                mutating instance state, #1). Defaults to None.

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
        """
        n = self.n_assets
        init_weights = np.ones(n) / n
        bounds = ((-1, 1) if allow_short else (0, 1),) * n
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

        def neg_sharpe(w):
            ret, vol, _ = self.portfolio_performance(w, mean_override)
            # Zero volatility is degenerate/infeasible. Returning a large
            # positive value steers SLSQP away rather than treating it as the
            # global optimum (0). See #5.
            return -(ret - self.risk_free_rate) / vol if vol > 0 else 1e10

        result = minimize(
            fun=neg_sharpe,
            x0=init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        weights = result.x
        ret, vol, sharpe = self.portfolio_performance(weights, mean_override)
        return {
            "weights": dict(zip(self.asset_names, weights)),
            "return": ret,
            "volatility": vol,
            "sharpe": sharpe,
            "success": result.success,
        }

    def efficient_frontier(
        self,
        n_points: int = 100,
        allow_short: bool = False,
        mean_override: Optional[np.ndarray] = None,
    ) -> pd.DataFrame:
        """Compute efficient frontier across a range of target returns.

        Args:
            n_points: Number of frontier points.
            allow_short: Allow negative weights.
            mean_override: Optional expected-return vector overriding
                ``self.mean_returns`` (used by the resampled-MVO path, #1).
                Defaults to None.

        Returns:
            DataFrame with 'return', 'volatility', 'sharpe', and asset weight columns.
        """
        if mean_override is not None:
            mean_series = np.asarray(mean_override, dtype=float)
        else:
            mean_series = self.mean_returns
        min_ret = mean_series.min()
        max_ret = mean_series.max()
        target_returns = np.linspace(min_ret, max_ret, n_points)

        frontier = []
        for target in target_returns:
            try:
                result = self.minimize_volatility(
                    target_return=target,
                    allow_short=allow_short,
                    mean_override=mean_override,
                )
                if result["success"]:
                    row = {
                        "return": result["return"],
                        "volatility": result["volatility"],
                        "sharpe": result["sharpe"],
                    }
                    row.update(result["weights"])
                    frontier.append(row)
            except Exception:
                continue

        return pd.DataFrame(frontier)

    def random_portfolios(self, n_portfolios: int = 5000) -> pd.DataFrame:
        """Generate random portfolios via Dirichlet sampling for visualization.

        Args:
            n_portfolios: Number of random portfolios.

        Returns:
            DataFrame with 'return', 'volatility', 'sharpe'.
        """
        records = []
        for _ in range(n_portfolios):
            weights = np.random.dirichlet(np.ones(self.n_assets))
            ret, vol, sharpe = self.portfolio_performance(weights)
            records.append({"return": ret, "volatility": vol, "sharpe": sharpe})
        return pd.DataFrame(records)

    def summary(self) -> str:
        """Human-readable summary of the optimization universe."""
        lines = [
            f"Portfolio Optimizer — {self.n_assets} assets",
            f"Risk-free rate: {self.risk_free_rate:.2%}",
            "",
            "Annualized Expected Returns:",
        ]
        for name, ret in self.mean_returns.items():
            lines.append(f"  {name}: {ret:.2%}")
        lines.append("")
        lines.append("Annualized Volatilities:")
        for name in self.asset_names:
            vol = np.sqrt(self.cov_matrix.loc[name, name])
            lines.append(f"  {name}: {vol:.2%}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Resampled MVO (Michaud): shared implementation
    # ------------------------------------------------------------------

    def _resampled_optimize(
        self,
        objective_fn,
        n_simulations: int = 1000,
        allow_short: bool = False,
        **objective_kwargs,
    ) -> dict:
        """Run resampled optimization by averaging weights across MC draws.

        Draws expected returns from N(μ_hat, Σ/T), runs `objective_fn`
        on each draw, and averages the resulting optimal weights.

        Args:
            objective_fn: Bound method returning an optimization result dict
                          (e.g. self.maximize_sharpe or self.minimize_volatility).
            n_simulations: Number of Monte Carlo draws.
            allow_short: Allow negative weights.
            **objective_kwargs: Extra kwargs forwarded to objective_fn.

        Returns:
            Dict with averaged 'weights', performance metrics, and 'weight_std'.
        """
        all_weights = []

        daily_cov = self.returns.cov().values
        daily_mean = self.returns.mean().values
        cov_over_T = daily_cov / len(self.returns)

        # Thread the sampled expected returns through each objective as a
        # local argument (mean_override) instead of mutating self.mean_returns.
        # The previous try/finally save-restore raced with any concurrent
        # reader of self.mean_returns (e.g. portfolio_performance), #1.
        for _ in range(n_simulations):
            sampled = np.random.multivariate_normal(daily_mean, cov_over_T)
            mean_override = sampled * TRADING_DAYS_PER_YEAR
            result = objective_fn(
                allow_short=allow_short,
                mean_override=mean_override,
                **objective_kwargs,
            )
            if result['success']:
                all_weights.append(np.array(list(result['weights'].values())))

        if not all_weights:
            equal_weights = np.ones(self.n_assets) / self.n_assets
            ret, vol, sharpe = self.portfolio_performance(equal_weights)
            return {
                'weights': dict(zip(self.asset_names, equal_weights)),
                'return': ret, 'volatility': vol, 'sharpe': sharpe,
                'success': False,
            }

        avg_weights = np.mean(all_weights, axis=0)
        avg_weights /= np.sum(avg_weights)
        ret, vol, sharpe = self.portfolio_performance(avg_weights)
        return {
            'weights': dict(zip(self.asset_names, avg_weights)),
            'return': ret, 'volatility': vol, 'sharpe': sharpe,
            'success': True,
            'n_simulations': n_simulations,
            'weight_std': np.std(all_weights, axis=0).tolist(),
        }

    def resampled_maximize_sharpe(
        self,
        n_simulations: int = 1000,
        allow_short: bool = False,
    ) -> dict:
        """Maximum Sharpe portfolio via Michaud resampling.

        Args:
            n_simulations: Number of Monte Carlo draws.
            allow_short: Allow negative weights.

        Returns:
            Dict with averaged weights and performance metrics.
        """
        return self._resampled_optimize(
            self.maximize_sharpe, n_simulations, allow_short,
        )

    def resampled_minimize_volatility(
        self,
        target_return: Optional[float] = None,
        n_simulations: int = 1000,
        allow_short: bool = False,
    ) -> dict:
        """Minimum volatility portfolio via Michaud resampling.

        Args:
            target_return: Optional return constraint.
            n_simulations: Number of Monte Carlo draws.
            allow_short: Allow negative weights.

        Returns:
            Dict with averaged weights and performance metrics.
        """
        return self._resampled_optimize(
            self.minimize_volatility, n_simulations, allow_short,
            target_return=target_return,
        )

    def resampled_efficient_frontier(
        self,
        n_points: int = 100,
        n_simulations: int = 1000,
        allow_short: bool = False,
    ) -> pd.DataFrame:
        """Resampled efficient frontier (Michaud method).

        Averages frontier weights across MC simulations on a unified
        return axis to produce more stable, diversified allocations.

        Args:
            n_points: Points per frontier.
            n_simulations: MC draws.
            allow_short: Allow negative weights.

        Returns:
            DataFrame with resampled frontier data.
        """
        all_frontiers = []
        daily_cov = self.returns.cov().values
        daily_mean = self.returns.mean().values
        cov_over_T = daily_cov / len(self.returns)

        # Pass sampled means via mean_override instead of mutating
        # self.mean_returns (thread-safety, #1).
        for _ in range(n_simulations):
            sampled = np.random.multivariate_normal(daily_mean, cov_over_T)
            mean_override = sampled * TRADING_DAYS_PER_YEAR
            frontier = self.efficient_frontier(
                n_points=n_points,
                allow_short=allow_short,
                mean_override=mean_override,
            )
            if not frontier.empty:
                all_frontiers.append(frontier)

        if not all_frontiers:
            return pd.DataFrame()

        # Interpolate all frontiers onto a common return axis, then average
        all_ret_values = np.concatenate([f['return'].values for f in all_frontiers])
        unified_returns = np.linspace(all_ret_values.min(), all_ret_values.max(), n_points)

        weight_cols = [c for c in all_frontiers[0].columns
                       if c not in ('return', 'volatility', 'sharpe')]
        interp_cols = ['volatility'] + weight_cols

        interpolated = []
        for frontier in all_frontiers:
            frontier_sorted = frontier.sort_values('return')
            row_data = {'return': unified_returns}
            for col in interp_cols:
                row_data[col] = np.interp(
                    unified_returns,
                    frontier_sorted['return'].values,
                    frontier_sorted[col].values,
                )
            interpolated.append(pd.DataFrame(row_data))

        resampled_frontier = pd.concat(interpolated).groupby(level=0).mean()
        resampled_frontier['return'] = unified_returns
        if 'return' in resampled_frontier.columns and 'volatility' in resampled_frontier.columns:
            resampled_frontier['sharpe'] = (
                (resampled_frontier['return'] - self.risk_free_rate) /
                resampled_frontier['volatility']
            )
        return resampled_frontier

    def optimize_with_asset_class_constraints(
        self,
        asset_classes: dict,
        target_return: Optional[float] = None,
        allow_short: bool = False,
    ) -> dict:
        """Optimize with per-asset-class min/max weight constraints.

        Args:
            asset_classes: Dict of class constraints, e.g.
                {'equity': {'assets': ['US_EQ'], 'min': 0.3, 'max': 0.7}}.
            target_return: Optional return constraint.
            allow_short: Allow negative weights.

        Returns:
            Dict with weights, performance, and 'asset_class_weights'.
        """
        n = self.n_assets
        init_weights = np.ones(n) / n
        bounds = ((-1, 1) if allow_short else (0, 1),) * n
        constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]

        # Use ndarray (self.cov_values) and the .values of the mean Series on
        # the SLSQP hot path; passing the pandas objects here triggers
        # index-alignment dispatch on every Jacobian evaluation (#9).
        cov = self.cov_values
        mean_vals = self.mean_returns.values

        if target_return is not None:
            constraints.append({
                'type': 'eq',
                'fun': lambda w: np.dot(w, mean_vals) - target_return,
            })

        asset_class_indices = {}
        for class_name, class_config in asset_classes.items():
            assets = class_config['assets']
            if isinstance(assets[0], str):
                indices = [self.asset_names.index(a) for a in assets]
            else:
                indices = assets
            asset_class_indices[class_name] = indices
            min_weight = class_config.get('min', 0.0)
            max_weight = class_config.get('max', 1.0)
            constraints.append({
                'type': 'ineq',
                'fun': lambda w, idx=indices, m=min_weight: sum(w[i] for i in idx) - m,
            })
            constraints.append({
                'type': 'ineq',
                'fun': lambda w, idx=indices, m=max_weight: m - sum(w[i] for i in idx),
            })

        def portfolio_volatility(w):
            return np.sqrt(np.dot(w.T, np.dot(cov, w)))

        result = minimize(
            fun=portfolio_volatility,
            x0=init_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
        )

        weights = result.x
        ret, vol, sharpe = self.portfolio_performance(weights)
        asset_class_weights = {
            cn: sum(weights[i] for i in idx)
            for cn, idx in asset_class_indices.items()
        }
        return {
            'weights': dict(zip(self.asset_names, weights)),
            'return': ret, 'volatility': vol, 'sharpe': sharpe,
            'success': result.success,
            'asset_class_weights': asset_class_weights,
        }


class BlackLittermanOptimizer(PortfolioOptimizer):
    """Black-Litterman optimizer: Bayesian blend of equilibrium and views.

    Computes implied equilibrium returns from CAPM (Π = δΣw_mkt),
    then combines with investor views via the BL posterior formula.
    """

    def __init__(
        self,
        returns: pd.DataFrame,
        risk_free_rate: float = RISK_FREE_RATE,
        market_cap_weights: Optional[np.ndarray] = None,
        delta: Optional[float] = None,
        tau: float = 0.025,
        covariance_method: str = 'sample',
    ):
        """Initialize Black-Litterman optimizer.

        Args:
            returns: Daily asset returns DataFrame.
            risk_free_rate: Annual risk-free rate.
            market_cap_weights: Market-cap weights (sum to 1). Defaults to 1/N.
            delta: Risk aversion. If None, estimated as (R_mkt - R_f) / σ²_mkt.
            tau: Prior uncertainty scaling (typically 0.025-0.05).
            covariance_method: 'sample', 'ledoit-wolf', or 'oas'.
        """
        super().__init__(
            returns=returns,
            risk_free_rate=risk_free_rate,
            covariance_method=covariance_method,
        )
        self.tau = tau

        if market_cap_weights is not None:
            if len(market_cap_weights) != self.n_assets:
                raise ValueError(
                    f"market_cap_weights length ({len(market_cap_weights)}) "
                    f"must match number of assets ({self.n_assets})."
                )
            if abs(np.sum(market_cap_weights) - 1.0) > 1e-6:
                raise ValueError(
                    f"market_cap_weights must sum to 1.0, got {np.sum(market_cap_weights)}."
                )
            self.market_cap_weights = market_cap_weights
        else:
            self.market_cap_weights = np.ones(self.n_assets) / self.n_assets

        if delta is not None:
            self.delta = delta
        else:
            # δ = (R_mkt - R_f) / σ²_mkt
            market_return = np.dot(self.market_cap_weights, self.mean_returns)
            market_variance = float(
                self.market_cap_weights.T @ self.cov_matrix.values @ self.market_cap_weights
            )
            self.delta = (market_return - self.risk_free_rate) / market_variance if market_variance > 0 else 2.5

        self.Pi = self.implied_equilibrium_returns()
        self.mu_bl = None
        self.Sigma_bl = None
        self.views_applied = False

    def implied_equilibrium_returns(self) -> np.ndarray:
        """CAPM-implied equilibrium excess returns: Π = δΣw_mkt.

        Returns:
            Implied excess return vector (N,).
        """
        return self.delta * self.cov_matrix.values @ self.market_cap_weights

    def bl_posterior_returns(
        self,
        P: np.ndarray,
        Q: np.ndarray,
        Omega: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute BL posterior returns and covariance.

        μ_BL = [(τΣ)⁻¹ + P'Ω⁻¹P]⁻¹ × [(τΣ)⁻¹Π + P'Ω⁻¹Q]
        Σ_BL = Σ + [(τΣ)⁻¹ + P'Ω⁻¹P]⁻¹

        Args:
            P: Pick matrix (K × N).
            Q: View return vector (K,).
            Omega: View uncertainty matrix (K × K).

        Returns:
            Tuple of (mu_BL, Sigma_BL).
        """
        Sigma = self.cov_matrix.values
        Pi = self.Pi
        tau = self.tau

        epsilon = 1e-8
        tau_Sigma = tau * Sigma + epsilon * np.eye(self.n_assets)

        try:
            tau_Sigma_inv = np.linalg.inv(tau_Sigma)
            Omega_inv = np.linalg.inv(Omega)
        except np.linalg.LinAlgError:
            tau_Sigma_inv = np.linalg.pinv(tau_Sigma)
            Omega_inv = np.linalg.pinv(Omega)

        M = np.linalg.inv(tau_Sigma_inv + P.T @ Omega_inv @ P)
        mu_bl = M @ (tau_Sigma_inv @ Pi + P.T @ Omega_inv @ Q)
        Sigma_bl = Sigma + M
        return mu_bl, Sigma_bl

    def apply_views(self, views: list) -> None:
        """Apply investor views to compute BL posterior.

        Args:
            views: List of ViewInput objects from src.portfolio.views.
        """
        from src.portfolio.views import ViewProcessor
        view_processor = ViewProcessor(self.asset_names)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            views, self.cov_matrix, self.tau
        )
        self.mu_bl, self.Sigma_bl = self.bl_posterior_returns(P, Q, Omega)
        self.views_applied = True

    def bl_portfolio_performance(
        self,
        weights: np.ndarray,
    ) -> tuple[float, float, float]:
        """Portfolio performance using BL posterior returns.

        Args:
            weights: Portfolio weights (N,).

        Returns:
            Tuple of (return, volatility, sharpe).
        """
        if not self.views_applied:
            raise ValueError("Must call apply_views() before bl_portfolio_performance().")

        portfolio_return = float(np.dot(weights, self.mu_bl))
        portfolio_volatility = float(
            np.sqrt(np.dot(weights.T, np.dot(self.Sigma_bl, weights)))
        )
        sharpe_ratio = (
            (portfolio_return - self.risk_free_rate) / portfolio_volatility
            if portfolio_volatility > 0
            else 0
        )
        return portfolio_return, portfolio_volatility, sharpe_ratio

    def bl_maximize_sharpe(self, allow_short: bool = False) -> dict:
        """Max Sharpe portfolio using BL posterior returns.

        Args:
            allow_short: Allow negative weights.

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
        """
        if not self.views_applied:
            raise ValueError("Must call apply_views() before bl_maximize_sharpe().")

        n = self.n_assets
        init_weights = np.ones(n) / n
        bounds = ((-1, 1) if allow_short else (0, 1),) * n
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

        def neg_sharpe_bl(w):
            ret, vol, _ = self.bl_portfolio_performance(w)
            # Zero volatility is degenerate/infeasible; return a large penalty
            # so SLSQP does not mistake it for the optimum (#5).
            return -(ret - self.risk_free_rate) / vol if vol > 0 else 1e10

        result = minimize(
            fun=neg_sharpe_bl, x0=init_weights,
            method="SLSQP", bounds=bounds, constraints=constraints,
        )

        weights = result.x
        ret, vol, sharpe = self.bl_portfolio_performance(weights)
        return {
            "weights": dict(zip(self.asset_names, weights)),
            "return": ret, "volatility": vol, "sharpe": sharpe,
            "success": result.success,
        }

    def bl_minimize_volatility(
        self,
        target_return: Optional[float] = None,
        allow_short: bool = False,
    ) -> dict:
        """Min volatility portfolio using BL posterior covariance.

        Args:
            target_return: Optional return constraint.
            allow_short: Allow negative weights.

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
        """
        if not self.views_applied:
            raise ValueError("Must call apply_views() before bl_minimize_volatility().")

        n = self.n_assets
        init_weights = np.ones(n) / n
        bounds = ((-1, 1) if allow_short else (0, 1),) * n
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

        if target_return is not None:
            constraints.append({
                "type": "eq",
                "fun": lambda w: np.dot(w, self.mu_bl) - target_return,
            })

        def bl_volatility(w):
            return np.sqrt(np.dot(w.T, np.dot(self.Sigma_bl, w)))

        result = minimize(
            fun=bl_volatility, x0=init_weights,
            method="SLSQP", bounds=bounds, constraints=constraints,
        )

        weights = result.x
        ret, vol, sharpe = self.bl_portfolio_performance(weights)
        return {
            "weights": dict(zip(self.asset_names, weights)),
            "return": ret, "volatility": vol, "sharpe": sharpe,
            "success": result.success,
        }

    def bl_efficient_frontier(
        self,
        n_points: int = 100,
        allow_short: bool = False,
    ) -> pd.DataFrame:
        """Compute BL efficient frontier.

        Args:
            n_points: Number of frontier points.
            allow_short: Allow negative weights.

        Returns:
            DataFrame with 'return', 'volatility', 'sharpe', and weights.
        """
        if not self.views_applied:
            raise ValueError("Must call apply_views() before bl_efficient_frontier().")

        min_ret = float(self.mu_bl.min())
        max_ret = float(self.mu_bl.max())
        target_returns = np.linspace(min_ret, max_ret, n_points)

        frontier = []
        for target in target_returns:
            try:
                result = self.bl_minimize_volatility(
                    target_return=target, allow_short=allow_short
                )
                if result["success"]:
                    row = {
                        "return": result["return"],
                        "volatility": result["volatility"],
                        "sharpe": result["sharpe"],
                    }
                    row.update(result["weights"])
                    frontier.append(row)
            except Exception:
                continue
        return pd.DataFrame(frontier)

    def bl_summary(self) -> str:
        """Summary comparing equilibrium returns, views, and BL posterior."""
        if not self.views_applied:
            return "No views applied yet. Call apply_views() first."

        lines = [
            "Black-Litterman Model Summary",
            "=" * 60,
            "",
            f"Risk Aversion (δ): {self.delta:.4f}",
            f"Uncertainty Scale (τ): {self.tau}",
            f"Market Cap Weights: {dict(zip(self.asset_names, self.market_cap_weights))}",
            "",
            "Asset Returns Comparison:",
            "-" * 60,
            f"{'Asset':<15} {'Equilibrium':>18} {'BL Posterior':>20} {'Adjustment':>18}",
        ]
        for i, name in enumerate(self.asset_names):
            eq_ret = self.Pi[i]
            bl_ret = self.mu_bl[i]
            adj = bl_ret - eq_ret
            lines.append(f"{name:<15} {eq_ret:>17.2%} {bl_ret:>19.2%} {adj:>+17.2%}")
        return "\n".join(lines)


if __name__ == "__main__":
    np.random.seed(42)
    n_days = 252 * 5
    assets = ["US Equity", "Intl Equity", "Bonds", "Gold"]
    returns_data = pd.DataFrame(
        np.random.randn(n_days, len(assets)) * 0.01
        + np.array([0.0004, 0.0003, 0.0001, 0.0002]),
        columns=assets,
    )

    opt = PortfolioOptimizer(returns_data)
    print(opt.summary())

    print("\n--- Maximum Sharpe Portfolio ---")
    max_sharpe = opt.maximize_sharpe()
    print(f"Return: {max_sharpe['return']:.2%}")
    print(f"Volatility: {max_sharpe['volatility']:.2%}")
    print(f"Sharpe: {max_sharpe['sharpe']:.2f}")
    print("Weights:")
    for asset, w in max_sharpe["weights"].items():
        print(f"  {asset}: {w:.1%}")
