"""
AI WealthPilot - Implied Volatility Data Module

Fetches market-implied volatility indices (VIX, MOVE) via yfinance
as forward-looking volatility inputs for the CME engine's
weighted blending framework.

    - VIX: CBOE Volatility Index, reflects S&P 500 30-day implied volatility.
    - MOVE: ICE BofAML MOVE Index, reflects US Treasury implied volatility.

Quoting conventions differ and must not share one scale (issue #52):

    - VIX is quoted in percentage points of price volatility
      (20 = 20% annualized), so iv = raw × 0.01.
    - MOVE is quoted in basis points of annualized *yield* volatility
      (73 ≈ 73bp). Price volatility ≈ modified duration × yield
      volatility, so iv = raw × 1e-4 × duration. Durations below are
      approximate constants (they drift slowly with rate levels);
      for HYG/EMB the conversion only covers the rate component of
      volatility, credit-spread risk is a known underestimate.

Design:
    - Fetches VIX and MOVE as tradable indices (^VIX, ^MOVE).
    - Provides an asset-class → IV proxy mapping table.
    - Gracefully degrades: returns None for asset classes without
      a reliable IV proxy, or when yfinance fetch fails.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src import config

logger = logging.getLogger(__name__)


# Data Structures


@dataclass
class IVProxyConfig:
    """
    Configuration for an implied volatility proxy.

    Attributes:
        iv_ticker: yfinance ticker for the IV index (e.g. '^VIX').
        scale: Factor to convert raw quote to decimal annualized IV.
            VIX is quoted in percentage points (e.g. 20 = 20%),
            so scale=0.01 to get 0.20. Ignored when duration is set.
        duration: Approximate modified duration of the asset, used for
            yield-volatility indices (MOVE, quoted in bp): price vol ≈
            raw × 1e-4 × duration. None for price-vol indices (VIX).
        description: Human-readable description of the IV source.
    """

    iv_ticker: str
    scale: float = 0.01
    duration: Optional[float] = None
    description: str = ""


@dataclass
class ImpliedVolData:
    """
    Struct holding implied volatility data for a single asset class.

    Attributes:
        ticker: The asset proxy ticker (e.g. 'SPY').
        iv_index_ticker: The IV index ticker (e.g. '^VIX').
        iv_index_name: Human-readable name (e.g. 'CBOE VIX').
        implied_volatility: Annualized IV as a decimal (e.g. 0.20 for 20%).
        fetch_date: ISO date string of when the data was fetched.
    """

    ticker: str
    iv_index_ticker: str
    iv_index_name: str
    implied_volatility: float
    fetch_date: str


# Asset Class → IV Proxy Mapping

# Mapping from asset ticker to its IV proxy configuration.
# None means no reliable IV index is available for that asset class.
IV_PROXY_MAP: dict[str, Optional[IVProxyConfig]] = {
    "SPY": IVProxyConfig(
        iv_ticker="^VIX",
        scale=0.01,
        description="CBOE VIX (S&P 500 30-day implied volatility)",
    ),
    "EFA": IVProxyConfig(
        iv_ticker="^VIX",
        scale=0.01,
        description="Intl Developed Markets proxied by VIX",
    ),
    "EEM": IVProxyConfig(
        iv_ticker="^VIX", scale=0.01, description="Emerging Markets proxied by VIX"
    ),
    "ASHR": IVProxyConfig(
        iv_ticker="^VIX", scale=0.01, description="China A-Shares (ASHR) proxied by VIX"
    ),
    "EWH": IVProxyConfig(
        iv_ticker="^VIX", scale=0.01, description="Hong Kong equity proxied by VIX"
    ),
    "AGG": IVProxyConfig(
        iv_ticker="^MOVE",
        duration=6.0,  # agg bond index modified duration ≈ 6
        description="ICE BofAML MOVE (US Treasury implied volatility)",
    ),
    "TLT": IVProxyConfig(
        iv_ticker="^MOVE",
        duration=16.5,  # 20+ year Treasuries
        description="Long-Term US Treasuries proxied by MOVE",
    ),
    "HYG": IVProxyConfig(
        iv_ticker="^MOVE",
        duration=3.8,  # rate component only; credit spread risk not covered
        description="High Yield Bonds proxied by MOVE",
    ),
    "EMB": IVProxyConfig(
        iv_ticker="^MOVE",
        duration=7.0,  # rate component only; credit spread risk not covered
        description="Emerging Market Bonds proxied by MOVE",
    ),
    "TIP": IVProxyConfig(
        iv_ticker="^MOVE",
        duration=6.5,
        description="TIPS proxied by MOVE",
    ),
    # "000300.SS": None,   # CSI 300: no yfinance-accessible IV index
    # "GLD":      None,    # Gold: OVX exists but unreliable on yfinance
    # "VNQ":      None,    # REITs: no standard IV index
    # "DBC":      None,    # Commodities: no standard IV index
    # "BIL":      None,    # Cash: negligible volatility, IV not meaningful
    # "BTC-USD":  None,    # Crypto: no standard IV index
}

# Human-readable names for IV index tickers
IV_INDEX_NAMES: dict[str, str] = {
    "^VIX": "CBOE VIX",
    "^MOVE": "ICE BofAML MOVE",
}


# Core Fetching Logic


def _fetch_single_iv_index(iv_ticker: str) -> Optional[float]:
    """
    Fetch the latest closing price for a single IV index ticker.

    The raw quote is returned directly (not scaled). Conversion is
    applied later from IVProxyConfig (scale for price-vol indices,
    duration for yield-vol indices).

    Args:
        iv_ticker: yfinance ticker for the IV index (e.g. '^VIX').

    Returns:
        Latest closing price as float, or None if the fetch fails.
    """
    try:
        import yfinance as yf

        # DEMO_MODE: no network — degrade to historical-vol blending (KI-002).
        if config.DEMO_MODE:
            logger.info("DEMO_MODE: skipping IV index fetch for %s", iv_ticker)
            return None

        tkr = yf.Ticker(iv_ticker)
        # fast_info provides the latest price without downloading history
        price = tkr.fast_info.get("lastPrice")
        if price is not None and price > 0:
            return float(price)

        # Fallback: try getting the last close from history
        hist = tkr.history(period="5d")
        if not hist.empty:
            close = float(hist["Close"].iloc[-1])
            if close > 0:
                return close

        logger.warning("IV index %s returned no valid price", iv_ticker)
        return None

    except Exception as e:
        logger.warning("Failed to fetch IV index %s: %s", iv_ticker, e)
        return None


def fetch_implied_volatility(
    asset_tickers: list[str],
) -> dict[str, Optional[ImpliedVolData]]:
    """
    Fetch implied volatility data for a list of asset tickers.

    For each asset ticker, looks up its IV proxy in IV_PROXY_MAP.
    If a proxy exists and the IV index can be fetched successfully,
    returns an ImpliedVolData object. Otherwise returns None.

    The same IV index (e.g. ^VIX) is only fetched once even if
    multiple asset classes use it.

    Args:
        asset_tickers: List of asset proxy tickers (e.g. ['SPY', 'AGG']).

    Returns:
        Dict mapping each input ticker to its ImpliedVolData, or None
        if no IV data is available for that ticker.
    """
    from datetime import date

    result: dict[str, Optional[ImpliedVolData]] = {}
    fetch_date = date.today().isoformat()

    # Deduplicate: fetch each unique IV index only once
    unique_iv_tickers: dict[str, Optional[float]] = {}

    for asset_ticker in asset_tickers:
        proxy_cfg = IV_PROXY_MAP.get(asset_ticker)

        if proxy_cfg is None:
            # No IV proxy configured for this asset
            result[asset_ticker] = None
            continue

        iv_ticker = proxy_cfg.iv_ticker

        # Fetch the IV index if not already fetched
        if iv_ticker not in unique_iv_tickers:
            unique_iv_tickers[iv_ticker] = _fetch_single_iv_index(iv_ticker)

        raw_value = unique_iv_tickers[iv_ticker]

        if raw_value is None:
            logger.info(
                "IV index %s unavailable for asset %s, falling back to historical vol",
                iv_ticker,
                asset_ticker,
            )
            result[asset_ticker] = None
            continue

        # Convert the raw quote to decimal annualized IV (issue #52):
        # yield-vol indices (MOVE, bp) go through duration; price-vol
        # indices (VIX, percentage points) go through scale.
        if proxy_cfg.duration is not None:
            iv_decimal = raw_value * 1e-4 * proxy_cfg.duration
        else:
            iv_decimal = raw_value * proxy_cfg.scale
        iv_name = IV_INDEX_NAMES.get(iv_ticker, iv_ticker)

        result[asset_ticker] = ImpliedVolData(
            ticker=asset_ticker,
            iv_index_ticker=iv_ticker,
            iv_index_name=iv_name,
            implied_volatility=round(iv_decimal, 6),
            fetch_date=fetch_date,
        )

        logger.debug(
            "Fetched IV for %s via %s: %.4f (raw=%.2f)",
            asset_ticker,
            iv_ticker,
            iv_decimal,
            raw_value,
        )

    return result
