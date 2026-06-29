"""
Market data acquisition layer using yfinance.

Fetches historical and real-time market data for the asset universe,
with optional cross-currency translation to a unified base currency.

"""

import os
import requests
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

# Import the asset universe definition, trading days constant, base currency, default risk-free rate, and FRED API Key from project config
from src.config import ASSET_UNIVERSE, TRADING_DAYS_PER_YEAR, BASE_CURRENCY, DEFAULT_RISK_FREE_RATE, FRED_API_KEY


def fetch_price_history(
    tickers: Optional[list[str]] = None,
    period: str = "5y",
    interval: str = "1d",
    base_currency: Optional[str] = None,
    adjust_currency: bool = True,
) -> pd.DataFrame:
    """Fetch adjusted close prices with optional currency translation to base currency."""
    # If no tickers specified, use the full asset universe from config
    if tickers is None:
        tickers = list(ASSET_UNIVERSE.keys())

    if base_currency is None:
        base_currency = BASE_CURRENCY

    # Determine the exchange rate tickers to download
    fx_tickers_to_download = []
    if adjust_currency:
        for t in tickers:
            asset_info = ASSET_UNIVERSE.get(t, {})
            curr = asset_info.get("currency", "USD")
            # If asset currency is different from base_currency, and not Index/Rate, fetch its rate to USD
            if curr not in ["Index", "Rate", base_currency]:
                if curr != "USD":
                    fx_tickers_to_download.append(f"{curr}=X")
        # If base_currency is not USD, we also need its rate to USD for secondary conversion
        if base_currency not in ["Index", "Rate", "USD"]:
            fx_tickers_to_download.append(f"{base_currency}=X")

        # Deduplicate
        fx_tickers_to_download = list(set(fx_tickers_to_download))

    # Combine download list (preserving original tickers order)
    all_download_tickers = []
    for t in (tickers + fx_tickers_to_download):
        if t not in all_download_tickers:
            all_download_tickers.append(t)

    # auto_adjust=True: prices already account for splits and dividends
    data = yf.download(all_download_tickers, period=period, interval=interval, auto_adjust=True)

    # Extract Close prices, unify to a DataFrame with tickers as columns
    if data.empty:
        prices = pd.DataFrame(columns=all_download_tickers)
    elif isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.levels[0]:
            prices = data["Close"].copy()
        else:
            prices = pd.DataFrame(np.nan, index=data.index, columns=all_download_tickers)
    else:
        if "Close" in data.columns:
            prices = data[["Close"]].copy()
            prices.columns = all_download_tickers
        else:
            prices = pd.DataFrame(np.nan, index=data.index, columns=all_download_tickers)

    # Ensure all download tickers exist in the DataFrame to prevent downstream KeyErrors
    for col in all_download_tickers:
        if col not in prices.columns:
            prices[col] = np.nan

    # Forward/backward fill only the exchange rate columns to handle trading days mismatch
    fx_cols = [c for c in prices.columns if c.endswith("=X")]
    if fx_cols:
        prices[fx_cols] = prices[fx_cols].ffill().bfill()

    # Perform currency translation
    if adjust_currency:
        for t in tickers:
            asset_info = ASSET_UNIVERSE.get(t, {})
            curr = asset_info.get("currency", "USD")

            # Step 1: convert non-USD prices to USD-denominated prices
            if curr not in ["Index", "Rate", "USD"]:
                fx_t = f"{curr}=X"
                if fx_t in prices.columns:
                    prices[t] = prices[t] / prices[fx_t]

            # Step 2: if base_currency is not USD, convert USD prices to base currency
            if base_currency != "USD" and curr not in ["Index", "Rate"]:
                base_fx_t = f"{base_currency}=X"
                if base_fx_t in prices.columns:
                    prices[t] = prices[t] * prices[base_fx_t]

    # Keep only the requested tickers, filtering out temporary exchange rates
    prices = prices[tickers]

    # Drop rows where ALL values are NaN
    prices = prices.dropna(how="all")

    return prices


def compute_returns(prices: pd.DataFrame, method: str = "log") -> pd.DataFrame:
    """Compute log or simple returns from a price DataFrame."""
    if method == "log":
        # Log return formula: r_t = ln(P_t / P_{t-1})
        returns = np.log(prices / prices.shift(1))
    else:
        # Simple return: r_t = (P_t - P_{t-1}) / P_{t-1}
        returns = prices.pct_change()

    # Only drop rows where ALL returns are NaN (e.g., the first row, or non-trading days where all assets are inactive)
    return returns.dropna(how="all")


def compute_correlation_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute Pearson correlation matrix from simple returns."""
    # First compute simple returns, then calculate Pearson correlation matrix
    # Note: using simple returns (not log) as they are more intuitive cross-sectionally
    returns = compute_returns(prices, method="simple")
    return returns.corr()


def get_latest_quotes(tickers: Optional[list[str]] = None) -> pd.DataFrame:
    """Get latest quote data (price, change, change_pct) for a list of tickers."""
    # If no tickers specified, use the default asset universe
    if tickers is None:
        tickers = list(ASSET_UNIVERSE.keys())

    records = []
    for ticker in tickers:
        try:
            # fast_info provides lightweight real-time quote data, faster than the info property
            info = yf.Ticker(ticker).fast_info
            # Get the asset's display name and category from the ASSET_UNIVERSE config
            asset_info = ASSET_UNIVERSE.get(ticker, {})
            records.append({
                "ticker": ticker,
                "name": asset_info.get("name", ticker),
                "category": asset_info.get("category", "Unknown"),
                "price": info.get("lastPrice", None),
                "previous_close": info.get("previousClose", None),
            })
        except Exception:
            # If a ticker fails to fetch (e.g., network issue, invalid symbol), skip it
            continue

    df = pd.DataFrame(records)

    # Calculate price change and percentage change (only when data is available)
    # change = last price - previous close
    # change_pct = (change / previous_close) * 100
    if not df.empty and "price" in df.columns and "previous_close" in df.columns:
        df["change"] = df["price"] - df["previous_close"]
        df["change_pct"] = (df["change"] / df["previous_close"]) * 100

    return df


def fetch_risk_free_rate(
    fred_api_key: Optional[str] = None,
    default_rate: Optional[float] = None,
) -> float:
    """Fetch current annualized risk-free rate (FRED -> yfinance -> static fallback)."""
    fallback_rate = default_rate if default_rate is not None else DEFAULT_RISK_FREE_RATE
    api_key = fred_api_key or FRED_API_KEY or os.getenv("FRED_API_KEY")

    # 1. Try FRED API if key is available
    if api_key:
        try:
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": "DGS3MO",
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                observations = data.get("observations", [])
                if observations:
                    val_str = observations[0].get("value")
                    if val_str and val_str != ".":
                        return float(val_str) / 100.0
        except Exception:
            # Silent fallback to yfinance
            pass

    # 2. Try yfinance ^IRX (13-Week Treasury Bill)
    try:
        ticker = yf.Ticker("^IRX")
        # Try fast_info first
        rate_pct = ticker.fast_info.get("lastPrice")
        if rate_pct is not None and rate_pct > 0:
            return float(rate_pct) / 100.0
            
        # Fallback to history if fast_info fails
        hist = ticker.history(period="1d")
        if not hist.empty:
            rate_val = hist["Close"].iloc[-1]
            if rate_val is not None and rate_val > 0:
                return float(rate_val) / 100.0
    except Exception:
        # Silent fallback to static default
        pass

    # 3. Fallback to static default rate
    return fallback_rate


# Main entry point - for quick testing and validation
if __name__ == "__main__":
    # Quick test: download 1y of SPY, GLD, BTC-USD
    print("Fetching sample data...")
    prices = fetch_price_history(["SPY", "GLD", "BTC-USD"], period="1y")
    print(f"Fetched {len(prices)} trading days of data")
    print(prices.tail())

    # Print correlation matrix to observe inter-asset correlation (basis for diversification analysis)
    print("\nCorrelation matrix:")
    print(compute_correlation_matrix(prices))
