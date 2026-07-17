"""
Response schemas for the AI WealthPilot API.

CME models are imported directly from the core (src.portfolio.cme_models)
so the API contract and the engine can never drift apart.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.portfolio.cme_models import CMEReport


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str


class AssetInfo(BaseModel):
    """Static display metadata for one asset in the universe."""

    name: str
    category: str
    color: str
    currency: str
    symbol: str


class UniverseResponse(BaseModel):
    assets: dict[str, AssetInfo]


class Quote(BaseModel):
    ticker: str
    name: str
    category: str
    price: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    # Display metadata copied from ASSET_UNIVERSE so the frontend can format
    # prices (currency symbol, decimal rules) without a second request.
    currency: str = "USD"
    symbol: str = ""
    color: str = "#D4AF37"


class QuotesResponse(BaseModel):
    as_of: datetime
    quotes: list[Quote]


class RiskFreeRateResponse(BaseModel):
    rate: float = Field(
        description="Annualized risk-free rate as a decimal, e.g. 0.045 for 4.5%"
    )
    as_of: datetime


class CMEResponse(BaseModel):
    cache_status: str = Field(
        description="Provenance of the report: 'fresh' | 'cached' | 'stale' | 'fallback'"
    )
    report: CMEReport


class RiskStat(BaseModel):
    """Per-asset risk/return statistics over the analysis window."""

    ticker: str
    name: str
    ann_return: float = Field(description="Annualized mean return (decimal)")
    ann_volatility: float = Field(description="Annualized volatility (decimal)")
    sharpe: float
    max_drawdown: float = Field(description="Largest peak-to-trough loss (negative decimal)")
    var_95: float = Field(description="Daily 95% Value at Risk (positive decimal)")


class AnalyticsResponse(BaseModel):
    """
    Aggregated dashboard analytics for a ticker set and time window.

    price_chart / correlation_chart are full Plotly figures serialized via
    plotly's fig.to_json() (numpy arrays encoded as base64 typed arrays,
    decoded natively by plotly.js on the client).
    """

    period: str
    tickers: list[str]
    as_of: datetime
    price_chart: dict[str, Any]
    correlation_chart: Optional[dict[str, Any]] = None
    stats: list[RiskStat] = Field(default_factory=list)
