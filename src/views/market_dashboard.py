"""
AI WealthPilot - Market Dashboard Page (Premium UI Edition)

This module implements the premium interactive Market Dashboard for the Streamlit app.
It displays real-time market quotes, historical price charts, correlation
heatmaps, and risk/return statistics for the user's asset universe.


"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List

# Import data fetching functions
from src.data.market_data import (
    fetch_price_history,
    compute_returns,
    compute_correlation_matrix,
    get_latest_quotes,
)

# Import visualization functions
from src.visualization.charts import (
    plot_price_history,
    plot_correlation_heatmap,
)

# Import risk metrics functions
from src.portfolio.risk_metrics import (
    sharpe_ratio,
    max_drawdown,
    value_at_risk,
    conditional_var,
)

# Import configuration
from src.config import ASSET_UNIVERSE, TRADING_DAYS_PER_YEAR
from src.views.compliance import render_compliance_banner

# Time period mapping table: UI label -> yfinance period parameter
PERIOD_OPTIONS = {
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "3 Years": "3y",
    "5 Years": "5y",
}

ALL_CATEGORIES: List[str] = sorted(set(info["category"] for info in ASSET_UNIVERSE.values()))

# Data Caching Functions (TTL = 300s to balance speed & rate limits)
@st.cache_data(ttl=300, show_spinner=False)
def _cached_fetch_prices_v2(tickers: Tuple[str, ...], period: str) -> Optional[pd.DataFrame]:
    """
    Cached wrapper for fetch_price_history.
    
    Args:
        tickers: Tuple of Yahoo Finance ticker symbols.
        period: Data period string (e.g., '1y', '5y').

    Returns:
        DataFrame of adjusted close prices, or None if the fetch fails.
    """
    try:
        return fetch_price_history(list(tickers), period=period)
    except Exception as e:
        st.error(f"⚠️ Error fetching historical price data: {str(e)}")
        with st.expander("Details / 详细错误信息"):
            st.exception(e)
        return None

@st.cache_data(ttl=300, show_spinner=False)
def _cached_get_quotes_v2(tickers: Tuple[str, ...]) -> Optional[pd.DataFrame]:
    """
    Cached wrapper for get_latest_quotes.
    
    Args:
        tickers: Tuple of ticker symbols.

    Returns:
        DataFrame of latest quotes, or None if the fetch fails.
    """
    try:
        return get_latest_quotes(list(tickers))
    except Exception as e:
        st.error(f"⚠️ Error fetching real-time market quotes: {str(e)}")
        with st.expander("Details / 详细错误信息"):
            st.exception(e)
        return None

# UI Components

def _render_top_controls() -> Tuple[List[str], str]:
    """
    Premium top control bar to replace the legacy sidebar layout.
    
    Returns:
        Tuple containing:
            - List of selected tickers.
            - Selected period string for yfinance.
    """
    # Inject custom CSS styles for the top control bar (with no inner indentation to prevent markdown parsing issues)
    st.markdown("""<style>
.premium-header {
    background: linear-gradient(135deg, #FDE047 0%, #D4AF37 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-family: 'Outfit', sans-serif;
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: -10px;
}
.premium-subtitle {
    color: #94A3B8;
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 0.95rem;
    letter-spacing: 0.05em;
    margin-bottom: 25px;
}
</style>
<div class="premium-header">Global Markets Pulse</div>
<div class="premium-subtitle">REAL-TIME TELEMETRY & QUANTITATIVE ANALYTICS</div>""", unsafe_allow_html=True)

    # Top-bar controls using columns
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        selected_categories = st.multiselect(
            "Filter by Asset Class / 资产类别过滤",
            options=ALL_CATEGORIES,
            default=ALL_CATEGORIES,
            help="Select the asset classes you want to monitor."
        )

    with col2:
        period_label = st.selectbox(
            "Analysis Horizon / 分析视窗",
            options=list(PERIOD_OPTIONS.keys()),
            index=3,  # Default to "1 Year"
        )
        period = PERIOD_OPTIONS[period_label]
        
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        # Select active tickers based on selected categories
        selected_tickers = [
            ticker for ticker, info in ASSET_UNIVERSE.items()
            if info["category"] in selected_categories
        ]
        st.caption(f"🎯 **{len(selected_tickers)}** assets actively monitored")

    return selected_tickers, period


def _render_market_overview(quotes_df: Optional[pd.DataFrame]) -> None:
    """
    CSS Grid responsive layout with glassmorphic cards, replacing legacy flow layouts.
    
    Args:
        quotes_df: DataFrame containing columns: ticker, name, category, price, change, change_pct.
    """
    if quotes_df is None or quotes_df.empty:
        st.warning("Market telemetry disconnected. Please verify connection. / 行情连接中断。")
        return

    # Premium grid and glassmorphic card styles (without inner indentation to prevent markdown compiling to code blocks)
    st.markdown(
        """<style>
.asset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 18px;
    padding: 10px 0 25px 0;
}
.premium-card {
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 20px;
    position: relative;
    overflow: hidden;
    transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}
.premium-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(212, 175, 55, 0.5), transparent);
    opacity: 0;
    transition: opacity 0.4s ease;
}
.premium-card:hover {
    transform: translateY(-5px);
    border-color: rgba(212, 175, 55, 0.4);
    box-shadow: 0 12px 30px rgba(212, 175, 55, 0.15), 0 0 20px rgba(212, 175, 55, 0.1) inset;
}
.premium-card:hover::before {
    opacity: 1;
}
.card-header-v2 {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 15px;
}
.asset-name {
    font-family: 'Outfit', sans-serif;
    font-size: 1.05rem;
    font-weight: 600;
    color: #F8FAFC;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 160px;
}
.asset-ticker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: #D4AF37;
    background: rgba(212, 175, 55, 0.1);
    padding: 3px 8px;
    border-radius: 6px;
    border: 1px solid rgba(212, 175, 55, 0.2);
}
.asset-price {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.8rem;
    font-weight: 700;
    color: #FFFFFF;
    line-height: 1.1;
    margin-bottom: 8px;
}
.trend-pill {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    gap: 6px;
}
.trend-up {
    background: rgba(16, 185, 129, 0.15);
    color: #10B981;
    border: 1px solid rgba(16, 185, 129, 0.2);
}
.trend-down {
    background: rgba(239, 68, 68, 0.15);
    color: #EF4444;
    border: 1px solid rgba(239, 68, 68, 0.2);
}
.trend-flat {
    background: rgba(148, 163, 184, 0.15);
    color: #94A3B8;
    border: 1px solid rgba(148, 163, 184, 0.2);
}
.category-label {
    font-family: 'Outfit', sans-serif;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 10px;
    margin-top: 5px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    padding-bottom: 5px;
}
</style>""",
        unsafe_allow_html=True,
    )

    categories_in_data = sorted(quotes_df["category"].unique())

    for category in categories_in_data:
        cat_data = quotes_df[quotes_df["category"] == category]
        if cat_data.empty:
            continue

        st.markdown(f"<div class='category-label'>{category}</div>", unsafe_allow_html=True)
        
        cards_html = "<div class='asset-grid'>"
        
        for _, row in cat_data.iterrows():
            ticker = row.get("ticker", "")
            price = row.get("price")
            change = row.get("change")
            change_pct = row.get("change_pct")

            if pd.notna(price):
                asset_info = ASSET_UNIVERSE.get(ticker, {})
                currency_symbol = asset_info.get("symbol", "$")
                currency = asset_info.get("currency", "USD")

                # Format price decimals dynamically based on magnitude and currency
                if currency == "Rate":
                    # Exchange rates always require 4 decimals for precision
                    decimals = 4
                elif currency == "Index" or ticker.startswith("^"):
                    # Index tickers (like ^GSPC, ^IXIC) or USD Index always require 2 decimals
                    decimals = 2
                elif currency == "JPY":
                    # JPY assets are generally formatted as integers
                    decimals = 0
                else:
                    # General currencies (USD, CNY, etc.): 0 decimals for large assets (e.g. BTC, Gold),
                    # 2 decimals for medium assets (e.g. Silver), and 4 decimals for micro-assets (< 1)
                    decimals = 0 if price > 1000 else (2 if price > 1 else 4)

                
                price_str = f"{currency_symbol}{price:,.{decimals}f}" if currency_symbol else f"{price:,.{decimals}f}"

                # Format changes and color pill styles
                if pd.notna(change) and change > 0:
                    trend_class, icon = "trend-up", "▲"
                elif pd.notna(change) and change < 0:
                    trend_class, icon = "trend-down", "▼"
                else:
                    trend_class, icon = "trend-flat", "•"

                change_val = abs(change) if pd.notna(change) else 0.0
                change_str = f"{currency_symbol}{change_val:,.{decimals}f}" if currency_symbol else f"{change_val:,.{decimals}f}"
                pct_str = f"{abs(change_pct):.2f}%" if pd.notna(change_pct) else "0.00%"

                # Construct HTML without any leading indentation on individual lines to avoid markdown parser issues
                cards_html += (
                    f'<div class="premium-card">'
                    f'<div class="card-header-v2">'
                    f'<div class="asset-name" title="{row["name"]}">{row["name"]}</div>'
                    f'<div class="asset-ticker">{ticker}</div>'
                    f'</div>'
                    f'<div class="asset-price">{price_str}</div>'
                    f'<div class="trend-pill {trend_class}">'
                    f'<span>{icon}</span>'
                    f'<span>{change_str} ({pct_str})</span>'
                    f'</div>'
                    f'</div>'
                )
            else:
                cards_html += (
                    f'<div class="premium-card">'
                    f'<div class="card-header-v2">'
                    f'<div class="asset-name">{row["name"]}</div>'
                    f'<div class="asset-ticker">{ticker}</div>'
                    f'</div>'
                    f'<div class="asset-price">N/A</div>'
                    f'<div class="trend-pill trend-flat"><span>•</span><span>NO DATA</span></div>'
                    f'</div>'
                )
        cards_html += "</div>"
        st.markdown(cards_html, unsafe_allow_html=True)


def _render_price_chart(prices_df: Optional[pd.DataFrame], period_label: str) -> None:
    """
    Render historical price chart with options for performance normalization.
    
    Args:
        prices_df: DataFrame of historical adjusted close prices.
        period_label: Selected analysis horizon label.
    """
    if prices_df is None or prices_df.empty:
        st.warning("Unavailable historical data.")
        return

    # Elegant toggle for normalization
    normalize = st.toggle(
        "Normalize Performance (Base = 100) / 表现基准归一化", 
        value=True,
        help="Rebases all assets to 100 at start date for direct percentage comparison."
    )

    # Dynamically map the period label to standard name if needed
    period_str = next((k for k, v in PERIOD_OPTIONS.items() if v == period_label), period_label)
    
    fig = plot_price_history(
        prices_df,
        normalize=normalize,
        title=f"Asset Performance Trajectory — {period_str}",
    )
    
    # Fine-tune chart height and margins for a modern look
    fig.update_layout(height=550, margin=dict(t=50, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True, theme=None)


def _render_correlation_heatmap(prices_df: Optional[pd.DataFrame]) -> None:
    """
    Render asset return correlation heatmap and interpretation guide.
    
    Args:
        prices_df: DataFrame of historical adjusted close prices.
    """
    if prices_df is None or prices_df.empty or prices_df.shape[1] < 2:
        st.info("Requires at least 2 assets to compute correlation matrix.")
        return

    col_chart, col_desc = st.columns([3, 1])
    
    with col_chart:
        corr_matrix = compute_correlation_matrix(prices_df)
        fig = plot_correlation_heatmap(corr_matrix)
        fig.update_layout(height=550)
        st.plotly_chart(fig, use_container_width=True, theme=None)
        
    with col_desc:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("##### 🔍 Interpretation")
        st.markdown("""
        **Diversification Analysis**
        - <span style="color:#ef4444;font-weight:bold;">Red (+1.0)</span>: High positive correlation. Assets move in tandem.
        - <span style="color:#3b82f6;font-weight:bold;">Blue (-1.0)</span>: High negative correlation. Excellent for hedging.
        - <span style="color:#f8fafc;font-weight:bold;">White (0.0)</span>: Uncorrelated. Pure diversification benefit.
        
        *Tip: Construct portfolios with lower correlating assets to maximize your Sharpe Ratio.*
        """, unsafe_allow_html=True)


def _render_risk_statistics(prices_df: Optional[pd.DataFrame]) -> None:
    """
    Compute and display key risk/return statistics for the assets.
    
    Args:
        prices_df: DataFrame of historical adjusted close prices.
    """
    if prices_df is None or prices_df.empty:
        return

    returns_df = compute_returns(prices_df, method="simple")
    stats_records = []
    
    for col in returns_df.columns:
        ret_series = returns_df[col].dropna()
        price_series = prices_df[col].dropna()

        if len(ret_series) < 20:
            continue

        asset_info = ASSET_UNIVERSE.get(col, {})
        display_name = asset_info.get("name", col)

        # Financial logic formulas:
        # 1. Annualized Return: R_ann = E(R_p) = Mean(R_daily) * 252 (trading days)
        #    This scales the expected daily return to an annual basis.
        ann_return = float(ret_series.mean() * TRADING_DAYS_PER_YEAR)
        
        # 2. Annualized Volatility: Vol_ann = StdDev(R_daily) * sqrt(252)
        #    This scales the daily standard deviation using the square root of time rule.
        ann_vol = float(ret_series.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
        
        # 3. Sharpe Ratio: SR = (R_p - R_f) / Vol_p
        #    Risk-adjusted performance measure representing reward per unit of volatility.
        sr = sharpe_ratio(ret_series)
        
        # 4. Maximum Drawdown: MaxDD = (Peak - Trough) / Peak
        #    Represents the largest peak-to-trough drop in value before a new peak is achieved.
        dd = max_drawdown(price_series)
        
        # 5. Value at Risk (VaR 95%): Daily VaR at 95% confidence level.
        #    Estimates the maximum potential loss over a 1-day horizon with 95% probability.
        var_95 = value_at_risk(ret_series, confidence=0.95)

        stats_records.append({
            "Asset": display_name,
            "Ticker": col,
            "Ann. Return": ann_return * 100.0,
            "Ann. Volatility": ann_vol * 100.0,
            "Sharpe Ratio": sr,
            "Max Drawdown": dd['max_drawdown'] * 100.0,
            "Daily VaR (95%)": var_95 * 100.0,
        })

    if stats_records:
        df = pd.DataFrame(stats_records)
        
        # Display using Streamlit's new column_config features
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Asset": st.column_config.TextColumn("Asset (资产)", width="medium"),
                "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                "Ann. Return": st.column_config.NumberColumn("Return (年化收益)", format="%.2f%%", help="Annualized Expected Return"),
                "Ann. Volatility": st.column_config.NumberColumn("Volatility (年化波动)", format="%.2f%%", help="Annualized Standard Deviation"),
                "Sharpe Ratio": st.column_config.NumberColumn("Sharpe (夏普比率)", format="%.2f", help="Risk-adjusted return"),
                "Max Drawdown": st.column_config.NumberColumn("Max DD (最大回撤)", format="%.2f%%", help="Maximum observed peak-to-trough drop"),
                "Daily VaR (95%)": st.column_config.NumberColumn("VaR (在险价值)", format="%.2f%%", help="95% Confidence Daily Value at Risk"),
            }
        )
    else:
        st.info("Insufficient data points for statistical significance.")

# Main Render Function

def render() -> None:
    """
    Render function for the Market Dashboard.
    Orchestrates the top-bar control, CSS grids, and Tabbed layout.
    """
    # 1. Top control bar (replacing the sidebar)
    selected_tickers, period = _render_top_controls()

    render_compliance_banner()

    if not selected_tickers:
        st.warning("No assets selected. Please adjust your filters.")
        return

    # 2. Real-time market overview cards (CSS Grid layout)
    with st.spinner("Synchronizing with market telemetry... / 同步市场数据..."):
        quotes_df = _cached_get_quotes_v2(tuple(selected_tickers))
    _render_market_overview(quotes_df)

    # Prefetch historical data for downstream tabs
    with st.spinner("Downloading historical price vectors... / 获取历史序列..."):
        prices_df = _cached_fetch_prices_v2(tuple(selected_tickers), period)

    # 3. Tabbed layout (refactoring the long scrollable page to provide focused views)
    st.markdown("<br>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs([
        "📈 Price Trajectory (价格走势)", 
        "🕸️ Correlation Matrix (资产相关性)", 
        "📊 Risk & Metrics (风险统计)"
    ])
    
    with tab1:
        _render_price_chart(prices_df, period)
        
    with tab2:
        _render_correlation_heatmap(prices_df)
        
    with tab3:
        _render_risk_statistics(prices_df)

    # Footer disclaimer
    st.markdown("""
        <div style='text-align: center; margin-top: 50px; color: #64748B; font-size: 0.8rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 20px;'>
            Data sourced from Yahoo Finance via yfinance. Real-time metrics cached for 5 minutes. <br>
            Quantitative outputs are for informational purposes only.
        </div>
    """, unsafe_allow_html=True)
