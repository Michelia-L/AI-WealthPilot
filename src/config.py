"""
AI WealthPilot - Global Configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================
# Path Configuration
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DATA_DIR = DATA_DIR / "sample"

# ============================================================
# Application Settings
# ============================================================
APP_NAME = "AI WealthPilot"
APP_VERSION = "0.1.0"
APP_ENV = os.getenv("APP_ENV", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============================================================
# Asset Universe
# Assets we track and analyze — aligned with user's interests
# ============================================================
ASSET_UNIVERSE = {
    # Crypto
    "BTC-USD": {"name": "Bitcoin", "category": "Crypto", "color": "#F7931A"},
    # Commodities
    "GC=F": {"name": "Gold Futures", "category": "Commodity", "color": "#FFD700"},
    "SI=F": {"name": "Silver Futures", "category": "Commodity", "color": "#C0C0C0"},
    # Global Indices
    "^GSPC": {"name": "S&P 500", "category": "US Equity", "color": "#1F77B4"},
    "^IXIC": {"name": "NASDAQ", "category": "US Equity", "color": "#2CA02C"},
    "^DJI": {"name": "Dow Jones", "category": "US Equity", "color": "#9467BD"},
    "000300.SS": {"name": "CSI 300", "category": "CN Equity", "color": "#D62728"},
    "^HSI": {"name": "Hang Seng", "category": "HK Equity", "color": "#FF7F0E"},
    "^N225": {"name": "Nikkei 225", "category": "JP Equity", "color": "#E377C2"},
    "^FTSE": {"name": "FTSE 100", "category": "UK Equity", "color": "#17BECF"},
    "^GDAXI": {"name": "DAX", "category": "EU Equity", "color": "#BCBD22"},
    # Currencies
    "DX-Y.NYB": {"name": "US Dollar Index", "category": "Currency", "color": "#7F7F7F"},
    "CNY=X": {"name": "USD/CNY", "category": "Currency", "color": "#8C564B"},
}

# Default portfolio asset classes for optimization
DEFAULT_ASSET_CLASSES = {
    "US_EQUITY": {"ticker": "SPY", "name": "US Equities (S&P 500)"},
    "INTL_EQUITY": {"ticker": "EFA", "name": "International Developed Equities"},
    "EM_EQUITY": {"ticker": "EEM", "name": "Emerging Market Equities"},
    "US_BOND": {"ticker": "AGG", "name": "US Aggregate Bonds"},
    "TIPS": {"ticker": "TIP", "name": "Treasury Inflation-Protected"},
    "GOLD": {"ticker": "GLD", "name": "Gold"},
    "REIT": {"ticker": "VNQ", "name": "Real Estate (REITs)"},
    "CRYPTO": {"ticker": "BTC-USD", "name": "Bitcoin"},
}

# ============================================================
# Portfolio Optimization Defaults
# ============================================================
RISK_FREE_RATE = 0.045  # Current approximate risk-free rate
TRADING_DAYS_PER_YEAR = 252
MONTE_CARLO_SIMULATIONS = 10000
MONTE_CARLO_YEARS = 30

# ============================================================
# API Keys (loaded from .env)
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
