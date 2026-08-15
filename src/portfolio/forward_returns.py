"""
AI WealthPilot - Forward-Looking Expected Returns (Building Blocks)

Computes forward-looking expected returns for CME asset classes using a
simplified building-blocks model, mirroring the graceful-degradation
design of implied_volatility.py:

    - Equity / REITs:  E(R) = dividend yield + long-run nominal growth
      Dividend yield from yfinance ``Ticker.info`` (both percent and
      decimal encodings handled); growth is a documented config
      assumption per ticker (CME_FORWARD_GROWTH_ASSUMPTIONS).
    - Bonds:  E(R) = yield-to-maturity proxy — yfinance fund ``yield``,
      falling back to the ^TNX 10-year treasury yield.
    - Gold:  E(R) = inflation assumption (long-run real return ≈ 0).
    - Cash:  E(R) = current risk-free rate.

Every failure path returns None — the CME engine then keeps the
historical mean for that asset class. Forward returns are computed in
each asset's local currency; expected FX change is assumed to be zero
(disclosed in the CME methodology notes).
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.config import CME_FORWARD_GROWTH_ASSUMPTIONS

logger = logging.getLogger(__name__)


# Data Structures

@dataclass
class ForwardReturnConfig:
    """
    Building-blocks configuration for one asset-class proxy.

    Attributes:
        kind: Block model — 'equity' (income + growth), 'bond' (YTM
            proxy), 'gold' (inflation), or 'cash' (risk-free rate).
        growth: Long-run nominal earnings/dividend growth assumption
            (decimal). Only used by the 'equity' kind.
        yield_ticker: Optional ETF proxy for the income input when the
            proxy itself carries no dividend data (e.g. the CSI 300
            index 000300.SS → ASHR ETF).
    """
    kind: str
    growth: float = 0.0
    yield_ticker: Optional[str] = None


@dataclass
class ForwardReturnData:
    """
    Forward-looking expected return for a single asset class.

    Attributes:
        ticker: The asset proxy ticker (e.g. 'AGG').
        forward_return: Annualized forward expected return as decimal.
        basis: Short human-readable composition label, e.g.
            '股息率1.8%+增长6.0%'.
        source: Data source label for the market-derived input.
    """
    ticker: str
    forward_return: float
    basis: str
    source: str


# Asset Class → Building-Blocks Mapping

# Mapping from asset ticker to its forward-return configuration.
# Tickers absent from this map (or mapped to None) have no forward
# model and degrade to their historical mean.
FORWARD_RETURN_MAP: dict[str, Optional[ForwardReturnConfig]] = {
    "000300.SS": ForwardReturnConfig(
        kind="equity",
        growth=CME_FORWARD_GROWTH_ASSUMPTIONS.get("000300.SS", 0.06),
        # The CSI 300 index carries no dividend data on yfinance;
        # use the ASHR ETF (same economic exposure) as income proxy.
        yield_ticker="ASHR",
    ),
    "EFA": ForwardReturnConfig(
        kind="equity",
        growth=CME_FORWARD_GROWTH_ASSUMPTIONS.get("EFA", 0.04),
    ),
    "EWH": ForwardReturnConfig(
        kind="equity",
        growth=CME_FORWARD_GROWTH_ASSUMPTIONS.get("EWH", 0.045),
    ),
    "VNQ": ForwardReturnConfig(
        kind="equity",  # REITs: dividend yield + dividend growth
        growth=CME_FORWARD_GROWTH_ASSUMPTIONS.get("VNQ", 0.035),
    ),
    "AGG": ForwardReturnConfig(kind="bond"),
    "GLD": ForwardReturnConfig(kind="gold"),
    "BIL": ForwardReturnConfig(kind="cash"),
}


# Market-Data Helpers (all degrade to None)

def _normalize_yield(raw: object) -> Optional[float]:
    """
    Normalize a yfinance yield figure to a decimal.

    yfinance returns dividendYield / fund yield inconsistently across
    tickers and versions — sometimes a decimal (0.018), sometimes
    percentage points (1.8). Values above 0.2 (20%) are treated as
    percentage points; 20% is a sane upper bound for these broad ETFs.

    Args:
        raw: The raw value from yfinance info.

    Returns:
        Decimal yield, or None if the value is missing/invalid.
    """
    try:
        val = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    if val > 0.2:
        val = val / 100.0
    return val


def _fetch_info_fields(ticker: str) -> Optional[dict]:
    """
    Fetch yfinance Ticker.info for the given ticker.

    Returns:
        The info dict, or None on any failure.
    """
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) and info else None
    except Exception as e:
        logger.warning("Failed to fetch info for %s: %s", ticker, e)
        return None


def _fetch_tnx_yield() -> Optional[float]:
    """
    Fetch the ^TNX 10-year treasury yield (percent) as a decimal.

    Fallback for bond YTM when the fund's own yield is unavailable.

    Returns:
        Decimal yield (e.g. 0.043), or None on failure.
    """
    try:
        import yfinance as yf

        hist = yf.Ticker("^TNX").history(period="5d")
        if hist.empty:
            return None
        close = float(hist["Close"].iloc[-1])
        return close / 100.0 if close > 0 else None
    except Exception as e:
        logger.warning("Failed to fetch ^TNX yield: %s", e)
        return None


# Per-Kind Builders

def _forward_equity(ticker: str, cfg: ForwardReturnConfig) -> Optional[ForwardReturnData]:
    """Equity/REIT: E(R) = dividend yield + long-run growth."""
    info = _fetch_info_fields(ticker)
    div_yield = _normalize_yield(info.get("dividendYield")) if info else None
    source = "yfinance dividendYield"
    if div_yield is None and cfg.yield_ticker:
        proxy_info = _fetch_info_fields(cfg.yield_ticker)
        div_yield = (
            _normalize_yield(proxy_info.get("dividendYield"))
            if proxy_info else None
        )
        source = f"yfinance dividendYield ({cfg.yield_ticker} proxy)"
    if div_yield is None:
        return None
    forward = div_yield + cfg.growth
    return ForwardReturnData(
        ticker=ticker,
        forward_return=round(forward, 6),
        basis=f"股息率{div_yield:.1%}+增长{cfg.growth:.1%}",
        source=source,
    )


def _forward_bond(ticker: str) -> Optional[ForwardReturnData]:
    """Bond: E(R) = YTM proxy (fund yield → ^TNX 10Y fallback)."""
    info = _fetch_info_fields(ticker)
    ytm = _normalize_yield(info.get("yield")) if info else None
    if ytm is not None:
        return ForwardReturnData(
            ticker=ticker,
            forward_return=round(ytm, 6),
            basis=f"到期收益率代理{ytm:.1%}",
            source="yfinance fund yield",
        )
    tnx = _fetch_tnx_yield()
    if tnx is not None:
        return ForwardReturnData(
            ticker=ticker,
            forward_return=round(tnx, 6),
            basis=f"到期收益率代理{tnx:.1%}（^TNX）",
            source="^TNX 10Y yield",
        )
    return None


# Public Entry Point

def fetch_forward_returns(
    asset_tickers: list[str],
    inflation: float,
    risk_free_rate: float,
) -> dict[str, Optional[ForwardReturnData]]:
    """
    Compute forward-looking expected returns for a list of tickers.

    Args:
        asset_tickers: Asset proxy tickers (e.g. ['000300.SS', 'AGG']).
        inflation: Long-term inflation assumption (used for gold).
        risk_free_rate: Current risk-free rate (used for cash).

    Returns:
        Dict mapping each input ticker to its ForwardReturnData, or
        None when no forward model/input is available for it.
    """
    result: dict[str, Optional[ForwardReturnData]] = {}

    for ticker in asset_tickers:
        cfg = FORWARD_RETURN_MAP.get(ticker)
        if cfg is None:
            result[ticker] = None
            continue

        try:
            if cfg.kind == "equity":
                data = _forward_equity(ticker, cfg)
            elif cfg.kind == "bond":
                data = _forward_bond(ticker)
            elif cfg.kind == "gold":
                data = ForwardReturnData(
                    ticker=ticker,
                    forward_return=round(inflation, 6),
                    basis=f"通胀假设{inflation:.1%}（长期实际收益≈0）",
                    source="config inflation assumption",
                )
            elif cfg.kind == "cash":
                data = ForwardReturnData(
                    ticker=ticker,
                    forward_return=round(risk_free_rate, 6),
                    basis=f"无风险利率{risk_free_rate:.1%}",
                    source="risk-free rate cascade",
                )
            else:
                logger.warning("Unknown forward kind %s for %s", cfg.kind, ticker)
                data = None
        except Exception as e:
            logger.warning("Forward return failed for %s: %s", ticker, e)
            data = None

        if data is None:
            logger.info(
                "Forward return unavailable for %s, degrading to historical",
                ticker,
            )
        result[ticker] = data

    return result
