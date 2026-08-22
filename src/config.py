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
APP_VERSION = "0.10.1"
APP_ENV = os.getenv("APP_ENV", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Asset Universe
# Assets we track and analyze — aligned with user's interests
BASE_CURRENCY = "CNY"  # Base currency aligned with client-facing IPS (Chinese clients)
REPORTING_CURRENCY = "USD"  # For international asset pricing and portfolio optimization

ASSET_UNIVERSE = {
    # Crypto (USD-denominated)
    "BTC-USD": {
        "name": "Bitcoin",
        "category": "Crypto",
        "color": "#F7931A",
        "currency": "USD",
        "symbol": "$",
    },
    # Commodities (USD-denominated)
    "GC=F": {
        "name": "Gold Futures",
        "category": "Commodity",
        "color": "#FFD700",
        "currency": "USD",
        "symbol": "$",
    },
    "SI=F": {
        "name": "Silver Futures",
        "category": "Commodity",
        "color": "#C0C0C0",
        "currency": "USD",
        "symbol": "$",
    },
    # US Equity (USD-denominated)
    "^GSPC": {
        "name": "S&P 500",
        "category": "US Equity",
        "color": "#1F77B4",
        "currency": "USD",
        "symbol": "",
    },
    "^IXIC": {
        "name": "NASDAQ",
        "category": "US Equity",
        "color": "#2CA02C",
        "currency": "USD",
        "symbol": "",
    },
    "^DJI": {
        "name": "Dow Jones",
        "category": "US Equity",
        "color": "#9467BD",
        "currency": "USD",
        "symbol": "",
    },
    # Volatility (index points, not a tradable price)
    "^VIX": {
        "name": "CBOE VIX",
        "category": "Volatility",
        "color": "#C2185B",
        "currency": "Index",
        "symbol": "",
    },
    # CN Equity (CNY-denominated)
    "000300.SS": {
        "name": "CSI 300",
        "category": "CN Equity",
        "color": "#D62728",
        "currency": "CNY",
        "symbol": "",
    },
    # HK Equity (HKD-denominated)
    "^HSI": {
        "name": "Hang Seng",
        "category": "HK Equity",
        "color": "#FF7F0E",
        "currency": "HKD",
        "symbol": "",
    },
    # JP Equity (JPY-denominated)
    "^N225": {
        "name": "Nikkei 225",
        "category": "JP Equity",
        "color": "#E377C2",
        "currency": "JPY",
        "symbol": "",
    },
    # UK Equity (GBP-denominated)
    "^FTSE": {
        "name": "FTSE 100",
        "category": "UK Equity",
        "color": "#17BECF",
        "currency": "GBP",
        "symbol": "",
    },
    # EU Equity (EUR-denominated)
    "^GDAXI": {
        "name": "DAX",
        "category": "EU Equity",
        "color": "#BCBD22",
        "currency": "EUR",
        "symbol": "",
    },
    # KR Equity (KRW-denominated)
    "^KS11": {
        "name": "KOSPI",
        "category": "KR Equity",
        "color": "#4A90E2",
        "currency": "KRW",
        "symbol": "",
    },
    # TW Equity (TWD-denominated)
    "^TWII": {
        "name": "TAIEX",
        "category": "TW Equity",
        "color": "#50E3C2",
        "currency": "TWD",
        "symbol": "",
    },
    # IN Equity (INR-denominated)
    "^NSEI": {
        "name": "Nifty 50",
        "category": "IN Equity",
        "color": "#F5A623",
        "currency": "INR",
        "symbol": "",
    },
    # Currencies (Exchange rates)
    "DX-Y.NYB": {
        "name": "US Dollar Index",
        "category": "Currency",
        "color": "#7F7F7F",
        "currency": "Index",
        "symbol": "",
    },
    "CNY=X": {
        "name": "USD/CNY",
        "category": "Currency",
        "color": "#8C564B",
        "currency": "Rate",
        "symbol": "",
    },
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
    "CN_TREASURY": {"ticker": "511010.SS", "name": "China 5Y Treasury ETF"},
}

# Portfolio Optimization Defaults
DEFAULT_RISK_FREE_RATE = 0.045  # Static fallback risk-free rate (4.5%, USD leg)
DEFAULT_RISK_FREE_RATE_CNY = (
    0.02  # Static fallback for the CNY leg (~China 1Y government bond yield)
)
RISK_FREE_RATE = DEFAULT_RISK_FREE_RATE  # For backward compatibility
TRADING_DAYS_PER_YEAR = 252
MONTE_CARLO_SIMULATIONS = 10000
MONTE_CARLO_YEARS = 30

# Black-Litterman Model Defaults
BL_DEFAULT_TAU = 0.025  # Uncertainty scaling factor
BL_DEFAULT_DELTA = 2.5  # Risk aversion coefficient
BL_DEFAULT_CONFIDENCE = 70  # Default view confidence (%)

# AI Model Configuration — DeepSeek V4 Pro
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_MAX_TOKENS = 128000
DEEPSEEK_TEMPERATURE = 0.3
# OpenAI-client HTTP behavior (P24). The timeout bounds each request;
# streaming reads stay open across chunk gaps, so it must cover long
# generations. Retries cover transient network failures only — structured-
# output/schema retries stay with PydanticAI (``retries=3`` on the agents).
LLM_REQUEST_TIMEOUT = 600.0  # seconds
LLM_MAX_RETRIES = 2
# Per-task token budget for the multi-call IPS workflow (P24). Theoretical
# worst case is ~16 calls x 32K max_tokens ≈ 512K output tokens; typical
# runs use tens of thousands. 250K leaves headroom for revision rounds
# while bounding a runaway review-revise loop. Read dynamically via
# src.config so tests can monkeypatch it.
LLM_TASK_TOKEN_BUDGET = 250_000

# Demo Mode (P20): replay recorded fixtures for all LLM-powered features.
# Lets anyone clone the repo and experience the full AI advisor / IPS flow
# without a DeepSeek API key. Set DEMO_MODE=1 to force fixture replay even
# when a key is configured. Read dynamically via src.agents.demo_mode.
DEMO_MODE = os.getenv("DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")

# CME (Capital Market Expectations) Configuration
CME_LOOKBACK_YEARS = 5  # Historical data lookback
CME_INFLATION_ASSUMPTION = 0.025  # Long-term inflation assumption
CME_DATA_INTERVAL = "1d"  # Data frequency
CME_CACHE_TTL_DAYS = 90  # Cache validity period (days)
CME_CACHE_DIR = DATA_DIR / "cache" / "cme"  # Cache storage path

# Personal inflation presets (demographic & lifestyle-based inflation).
# Generic CPI misprices the inflation actually experienced by key private-
# banking segments, so presets apply a stylized additive delta over the base
# (generic-CPI) rate: "elderly" approximates the BLS CPI-E vs CPI-W gap
# (healthcare weight roughly doubles to ~11% for 62+ spending baskets);
# "luxury" approximates Forbes CLEWI's long-run premium over CPI (~+2.4pp/yr).
# Neither series has an official Chinese equivalent, so these are configurable
# assumptions — transparent and auditable, not a live data pipeline.
PERSONAL_INFLATION_DELTAS = {
    "standard": 0.0,
    "elderly": 0.0075,
    "luxury": 0.024,
}
# Client age at/above which the IPS pipeline defaults to the elderly preset.
PERSONAL_INFLATION_ELDERLY_MIN_AGE = 60

# LDI surplus optimization (Sharpe-Tint): bond proxies usable as liability
# hedges, with approximate effective durations in years. The liability
# return model duration-scales the proxy (r_L = g + λ·(r_p − μ_p),
# λ = D_L / D_proxy), so only these documented approximate durations are
# needed — no yield-curve feed.
LDI_PROXY_DURATIONS = {
    "US_BOND": 6.0,  # AGG ~ US aggregate bonds
    "LONG_TREASURY_BOND": 17.0,  # TLT ~ 20+yr Treasuries
    "TIPS": 7.0,  # TIP ~ inflation-protected Treasuries
    "CN_TREASURY": 4.3,  # 511010.SS ~ SSE 5Y treasury index ETF
}
LDI_DEFAULT_PROXY = "US_BOND"

# CME → optimizer expected-return bridge (expected_return_source="cme").
# Maps a CME proxy ticker to the optimizer-universe key with the same
# economic exposure. 000300.SS ↔ CHINA_EQUITY is an index-to-ETF
# equivalence (CSI 300 index vs the ASHR ETF proxy); EWH (HK equities)
# has no optimizer counterpart and is intentionally unmapped — uncovered
# assets fall back to their sample mean with disclosure.
CME_TICKER_TO_OPTIMIZER_ASSET = {
    "000300.SS": "CHINA_EQUITY",
    "EFA": "INTL_EQUITY",
    "AGG": "US_BOND",
    "GLD": "GOLD",
    "VNQ": "REIT",
    "BIL": "CASH",
}

# Tushare Pro data provider (paid CN backbone, P16)
# yfinance ticker → tushare ts_code. Routed tickers are served by Tushare
# Pro (daily bars); yfinance remains the fallback when Tushare is absent
# or errors out.
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
TUSHARE_TICKER_MAP = {
    "000300.SS": "000300.SH",  # CSI 300 index
}

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

# Asset-class alias table (P25): bilingual keyword lists per
# IPS_ASSET_CLASS_TICKERS category key, in priority order (first hit wins).
# Single source for monitoring's SAA->proxy mapping and the IPS workflow's
# SAA<->CME same-category match. zh aliases first (pre-existing behavior
# preserved verbatim); en aliases fix the en-locale coverage gap.
ASSET_CLASS_ALIASES: dict[str, list[str]] = {
    "domestic_equity": [
        "国内权益",
        "A股",
        "沪深300",
        "Domestic Equity",
        "A-shares",
        "A-share",
        "CSI 300",
    ],
    "international_equity_dm": [
        "国际权益",
        "发达市场",
        "International Equity",
        "Developed Markets",
        "EFA",
    ],
    "international_equity_hk": ["港股", "恒生", "Hong Kong", "Hang Seng", "EWH"],
    "fixed_income": ["固定收益", "固收", "债", "Fixed Income", "Bond"],
    "alternative_gold": ["黄金", "Gold", "GLD"],
    "alternative_reit": ["REITs", "REIT", "房地产", "Real Estate"],
    "cash": ["现金", "货币市场", "货币", "Cash", "Money Market", "BIL"],
}

# Implied Volatility Configuration
# Bayesian blending weight for implied vs historical volatility.
# τ (tau) controls the weight placed on forward-looking implied volatility:
#   blended_vol = τ × σ_implied + (1-τ) × σ_historical
#   τ = 0.0 → pure historical volatility (backward-looking only)
#   τ = 0.5 → equal weight (default; balanced approach)
#   τ = 1.0 → pure implied volatility (forward-looking only)

CME_IV_BLENDING_TAU = 0.5

# Forward-Looking Expected Returns (building blocks)
# Blending weight for forward-looking vs historical expected returns:
#   expected_return = ω × forward + (1-ω) × historical
#   ω = 0.0 → pure historical mean (backward-looking only)
#   ω = 0.5 → equal weight (default)
#   ω = 1.0 → pure building-blocks (forward-looking only)
# Per-asset degradation: assets whose forward inputs are unavailable
# keep their historical mean regardless of ω.
CME_FORWARD_BLENDING_OMEGA = 0.5

# Long-run nominal earnings/dividend growth assumptions by CME proxy
# ticker (building-blocks income + growth model). These are documented
# assumptions, not fetched data.
CME_FORWARD_GROWTH_ASSUMPTIONS = {
    "000300.SS": 0.06,  # CN equity: nominal GDP-linked
    "EFA": 0.04,  # DM equity
    "EWH": 0.045,  # HK equity
    "VNQ": 0.035,  # REITs: dividend growth
}

# Reference allocation for the retirement CME suggestion card: a balanced
# blend over the CME asset classes (documented assumption, not
# client-specific). Keys are IPS_ASSET_CLASS_TICKERS keys; weights sum to 1.
CME_REFERENCE_ALLOCATION = {
    "domestic_equity": 0.25,
    "international_equity_dm": 0.20,
    "international_equity_hk": 0.05,
    "fixed_income": 0.30,
    "alternative_gold": 0.10,
    "alternative_reit": 0.05,
    "cash": 0.05,
}

# Canonical risk-level → target annualized volatility band (P25 single
# source). Consumers: validate_saa enforcement, recommender interpolation,
# and the IPS agent prompts (composed at build time).
RISK_VOLATILITY_BANDS = {
    "conservative": (0.04, 0.08),
    "moderately_conservative": (0.08, 0.12),
    "moderate": (0.10, 0.15),
    "moderately_aggressive": (0.13, 0.18),
    "aggressive": (0.16, 0.25),
}

# SAA Validation thresholds
SAA_VOLATILITY_TOLERANCE_PP = 0.03  # Accept if vol within +3pp of efficient frontier

# Legacy API Keys (for future RAG modules — Phase 4)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
