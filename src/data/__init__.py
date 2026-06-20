"""AI WealthPilot - Data Module"""
from src.data.market_data import (
    fetch_price_history,
    compute_returns,
    compute_correlation_matrix,
    get_latest_quotes,
)

__all__ = [
    "fetch_price_history",
    "compute_returns",
    "compute_correlation_matrix",
    "get_latest_quotes",
]
