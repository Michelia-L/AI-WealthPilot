"""Unit tests for src.portfolio.optimize_service (method runners)."""

import numpy as np
import pandas as pd

from src.portfolio import optimize_service
from src.portfolio.optimize_service import run_cvar


def _returns() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=60, freq="B")
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "Asset A": rng.normal(0.0005, 0.01, 60),
            "Asset B": rng.normal(0.0003, 0.008, 60),
        },
        index=dates,
    )


def _min_cvar_result() -> dict:
    return {
        "weights": {"Asset A": 1.0, "Asset B": 0.0},
        "return": 0.0,
        "volatility": 0.0,
        "sharpe": 0.0,
        "cvar": 0.0,
        "success": True,
    }


def _patch_optimizer(monkeypatch, frontier: pd.DataFrame, min_cvar: dict) -> None:
    monkeypatch.setattr(
        optimize_service.PortfolioOptimizer,
        "cvar_efficient_frontier",
        lambda self, **_: frontier,
    )
    monkeypatch.setattr(
        optimize_service.PortfolioOptimizer,
        "minimize_cvar",
        lambda self, **_: min_cvar,
    )
    monkeypatch.setattr(
        optimize_service.PortfolioOptimizer,
        "random_portfolios",
        lambda self, **_: pd.DataFrame(),
    )


class TestRunCvarStarrGuard:
    """The max-STARR pick must ignore degenerate zero-CVaR frontier rows."""

    def test_zero_cvar_row_does_not_win_via_inf(self, monkeypatch):
        frontier = pd.DataFrame(
            {
                "return": [0.0, 0.10],
                "volatility": [0.0, 0.12],
                "sharpe": [0.0, 0.5],
                "cvar": [0.0, 0.05],
                "Asset A": [1.0, 0.6],
                "Asset B": [0.0, 0.4],
            }
        )
        _patch_optimizer(monkeypatch, frontier, _min_cvar_result())

        _, selected, max_sharpe, _, _, _, _ = run_cvar(
            _returns(),
            mode="max-sharpe",
            allow_short=False,
            cvar_confidence=0.95,
            risk_free_rate=0.02,
        )

        # The 0.10/0.05 row (ratio 1.6) wins; the cvar=0 row must not
        # produce an inf ratio and get picked.
        assert max_sharpe["return"] == 0.10
        assert np.isfinite(max_sharpe["return"])
        assert selected is max_sharpe

    def test_all_zero_cvar_falls_back_to_min_cvar(self, monkeypatch):
        frontier = pd.DataFrame(
            {
                "return": [0.0, 0.0],
                "volatility": [0.0, 0.0],
                "sharpe": [0.0, 0.0],
                "cvar": [0.0, 0.0],
                "Asset A": [1.0, 0.5],
                "Asset B": [0.0, 0.5],
            }
        )
        min_cvar = _min_cvar_result()
        _patch_optimizer(monkeypatch, frontier, min_cvar)

        _, selected, max_sharpe, _, _, _, _ = run_cvar(
            _returns(),
            mode="max-sharpe",
            allow_short=False,
            cvar_confidence=0.95,
            risk_free_rate=0.02,
        )

        assert max_sharpe is min_cvar
        assert selected is min_cvar
