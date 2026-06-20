"""
AI WealthPilot - Global Configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (override=True to prioritize .env file over system/terminal env vars)
load_dotenv(override=True)

# Path Configuration
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DATA_DIR = DATA_DIR / "sample"

# Application Settings
APP_NAME = "AI WealthPilot"
APP_VERSION = "0.3.0"
APP_ENV = os.getenv("APP_ENV", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Asset Universe
# Assets we track and analyze — aligned with user's interests
BASE_CURRENCY = "CNY"  # Base currency aligned with client-facing IPS (Chinese clients)
REPORTING_CURRENCY = "USD"  # For international asset pricing and portfolio optimization

ASSET_UNIVERSE = {
    # Crypto (USD-denominated)
    "BTC-USD": {"name": "Bitcoin", "category": "Crypto", "color": "#F7931A", "currency": "USD", "symbol": "$"},
    # Commodities (USD-denominated)
    "GC=F": {"name": "Gold Futures", "category": "Commodity", "color": "#FFD700", "currency": "USD", "symbol": "$"},
    "SI=F": {"name": "Silver Futures", "category": "Commodity", "color": "#C0C0C0", "currency": "USD", "symbol": "$"},
    # US Equity (USD-denominated)
    "^GSPC": {"name": "S&P 500", "category": "US Equity", "color": "#1F77B4", "currency": "USD", "symbol": ""},
    "^IXIC": {"name": "NASDAQ", "category": "US Equity", "color": "#2CA02C", "currency": "USD", "symbol": ""},
    "^DJI": {"name": "Dow Jones", "category": "US Equity", "color": "#9467BD", "currency": "USD", "symbol": ""},
    # CN Equity (CNY-denominated)
    "000300.SS": {"name": "CSI 300", "category": "CN Equity", "color": "#D62728", "currency": "CNY", "symbol": ""},
    # HK Equity (HKD-denominated)
    "^HSI": {"name": "Hang Seng", "category": "HK Equity", "color": "#FF7F0E", "currency": "HKD", "symbol": ""},
    # JP Equity (JPY-denominated)
    "^N225": {"name": "Nikkei 225", "category": "JP Equity", "color": "#E377C2", "currency": "JPY", "symbol": ""},
    # UK Equity (GBP-denominated)
    "^FTSE": {"name": "FTSE 100", "category": "UK Equity", "color": "#17BECF", "currency": "GBP", "symbol": ""},
    # EU Equity (EUR-denominated)
    "^GDAXI": {"name": "DAX", "category": "EU Equity", "color": "#BCBD22", "currency": "EUR", "symbol": ""},
    # KR Equity (KRW-denominated)
    "^KS11": {"name": "KOSPI", "category": "KR Equity", "color": "#4A90E2", "currency": "KRW", "symbol": ""},
    # TW Equity (TWD-denominated)
    "^TWII": {"name": "TAIEX", "category": "TW Equity", "color": "#50E3C2", "currency": "TWD", "symbol": ""},
    # IN Equity (INR-denominated)
    "^NSEI": {"name": "Nifty 50", "category": "IN Equity", "color": "#F5A623", "currency": "INR", "symbol": ""},
    # Currencies (Exchange rates)
    "DX-Y.NYB": {"name": "US Dollar Index", "category": "Currency", "color": "#7F7F7F", "currency": "Index", "symbol": ""},
    "CNY=X": {"name": "USD/CNY", "category": "Currency", "color": "#8C564B", "currency": "Rate", "symbol": ""},
}

# Default portfolio asset classes for optimization
DEFAULT_ASSET_CLASSES = {
    "US_EQUITY": {"ticker": "SPY", "name": "US Equities (S&P 500)"},
    "INTL_EQUITY": {"ticker": "EFA", "name": "International Developed Equities"},
    "EM_EQUITY": {"ticker": "EEM", "name": "Emerging Market Equities"},
    "CHINA_EQUITY": {"ticker": "ASHR", "name": "China A-Shares (ASHR)"},
    "US_BOND": {"ticker": "AGG", "name": "US Aggregate Bonds"},
    "LONG_TREASURY_BOND": {"ticker": "TLT", "name": "Long-Term US Treasuries (TLT)"},
    "HIGH_YIELD_BOND": {"ticker": "HYG", "name": "High Yield Bonds (HYG)"},
    "EM_BOND": {"ticker": "EMB", "name": "Emerging Market Bonds (EMB)"},
    "TIPS": {"ticker": "TIP", "name": "Treasury Inflation-Protected"},
    "GOLD": {"ticker": "GLD", "name": "Gold"},
    "COMMODITIES": {"ticker": "DBC", "name": "Broad Commodities (DBC)"},
    "REIT": {"ticker": "VNQ", "name": "Real Estate (REITs)"},
    "CRYPTO": {"ticker": "BTC-USD", "name": "Bitcoin"},
    "CASH": {"ticker": "BIL", "name": "Cash Equivalents (BIL)"},
}

# Portfolio Optimization Defaults
DEFAULT_RISK_FREE_RATE = 0.045  # Static fallback risk-free rate (4.5%)
RISK_FREE_RATE = DEFAULT_RISK_FREE_RATE  # For backward compatibility
TRADING_DAYS_PER_YEAR = 252
MONTE_CARLO_SIMULATIONS = 10000
MONTE_CARLO_YEARS = 30

# Black-Litterman Model Defaults
BL_DEFAULT_TAU = 0.025              # Uncertainty scaling factor
BL_DEFAULT_DELTA = 2.5              # Risk aversion coefficient
BL_DEFAULT_CONFIDENCE = 70          # Default view confidence (%)

# AI Model Configuration — DeepSeek V4 Pro
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_MAX_TOKENS = 128000
DEEPSEEK_TEMPERATURE = 0.3

# CME (Capital Market Expectations) Configuration
CME_LOOKBACK_YEARS = 5           # Historical data lookback
CME_INFLATION_ASSUMPTION = 0.025  # Long-term inflation assumption
CME_DATA_INTERVAL = "1d"          # Data frequency
CME_CACHE_TTL_DAYS = 90            # Cache validity period (days)
CME_CACHE_DIR = DATA_DIR / "cache" / "cme"  # Cache storage path

# IPS asset class → proxy ticker mapping
IPS_ASSET_CLASS_TICKERS = {
    "domestic_equity": {
        "ticker": "000300.SS",
        "name": "Domestic Equity (A-Shares/CSI 300)",
    },
    "international_equity_dm": {
        "ticker": "EFA",
        "name": "国际权益（发达市场）",
    },
    "international_equity_hk": {
        "ticker": "EWH",
        "name": "港股",
    },
    "fixed_income": {
        "ticker": "AGG",
        "name": "固定收益",
    },
    "alternative_gold": {
        "ticker": "GLD",
        "name": "另类-黄金",
    },
    "alternative_reit": {
        "ticker": "VNQ",
        "name": "另类-REITs",
    },
    "cash": {
        "ticker": "BIL",
        "name": "现金等价物",
    },
}

# Implied Volatility Configuration
# Bayesian blending weight for implied vs historical volatility.
# τ (tau) controls the weight placed on forward-looking implied volatility:
#   blended_vol = τ × σ_implied + (1-τ) × σ_historical
#   τ = 0.0 → pure historical volatility (backward-looking only)
#   τ = 0.5 → equal weight (default; CFA-recommended balanced approach)
#   τ = 1.0 → pure implied volatility (forward-looking only)
# CFA Reference: CFA L3 — multi-method CME blending.
CME_IV_BLENDING_TAU = 0.5

# SAA Validation thresholds
SAA_VOLATILITY_TOLERANCE_PP = 0.03  # Accept if vol within +3pp of efficient frontier

# Legacy API Keys (for future RAG modules — Phase 4)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
