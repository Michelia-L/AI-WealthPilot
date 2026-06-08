"""
AI WealthPilot - Visualization Module

Plotly-based chart components for portfolio analysis dashboards.
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from typing import Optional


# ============================================================
# Color Palette — Premium dark theme (Vantablack-Gold-Emerald)
# ============================================================
COLORS = {
    "primary": "#D4AF37",      # Luxury Gold
    "secondary": "#10B981",    # Emerald
    "accent": "#06B6D4",       # Teal
    "success": "#10B981",      # Emerald
    "warning": "#FFD700",      # Iconic Gold
    "danger": "#ef4444",       # Red
    "bg_dark": "#050505",      # OLED Vantablack
    "bg_card": "#09090b",      # Deep Core Card
    "text": "#f8fafc",         # Slate 50
    "text_muted": "#94a3b8",   # Slate 400
    "grid": "rgba(255, 255, 255, 0.03)", # Ultra-thin transparent grid lines
}

CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",  # Transparent to blend with glassmorphic cards
    plot_bgcolor="rgba(9, 9, 11, 0.4)",  # Match the .inner-core background
    font=dict(family="Plus Jakarta Sans, sans-serif", color=COLORS["text"]),
    margin=dict(l=40, r=40, t=60, b=40),
    xaxis=dict(
        gridcolor=COLORS["grid"],
        linecolor="rgba(255, 255, 255, 0.05)",
        tickfont=dict(family="JetBrains Mono, monospace", size=10, color=COLORS["text_muted"]),
    ),
    yaxis=dict(
        gridcolor=COLORS["grid"],
        linecolor="rgba(255, 255, 255, 0.05)",
        tickfont=dict(family="JetBrains Mono, monospace", size=10, color=COLORS["text_muted"]),
    ),
    hoverlabel=dict(
        bgcolor="#09090b",
        bordercolor="rgba(255, 255, 255, 0.1)",
        font=dict(family="Plus Jakarta Sans, sans-serif", size=12, color="#f8fafc"),
    ),
)


def get_asset_color(name_or_ticker: str, index: int) -> str:
    """
    Resolves the configured color for an asset, ensuring brand consistency.
    Keeps Gold's iconic color (#FFD700 / #D4AF37) and Bitcoin's orange.
    """
    try:
        from src.config import ASSET_UNIVERSE, DEFAULT_ASSET_CLASSES

        # 1. Check direct matches in ASSET_UNIVERSE
        for ticker, info in ASSET_UNIVERSE.items():
            if name_or_ticker == ticker or name_or_ticker == info.get("name"):
                return info.get("color", "#D4AF37")

        # 2. Check matches in DEFAULT_ASSET_CLASSES
        for key, info in DEFAULT_ASSET_CLASSES.items():
            if name_or_ticker == info.get("ticker") or name_or_ticker == info.get("name"):
                if "gold" in name_or_ticker.lower() or info.get("ticker") == "GLD":
                    return "#FFD700"  # Iconic Gold
                if "btc" in name_or_ticker.lower() or "bitcoin" in name_or_ticker.lower() or info.get("ticker") == "BTC-USD":
                    return "#F7931A"  # Bitcoin Orange
                
                premium_colors = {
                    "EQUITY": "#06B6D4",      # Teal
                    "BOND": "#3B82F6",        # Blue
                    "TREASURY": "#60A5FA",    # Light blue
                    "COMMODITIES": "#A855F7", # Purple
                    "REIT": "#EC4899",        # Pink
                    "CASH": "#9CA3AF",        # Gray
                }
                for cls_key, color in premium_colors.items():
                    if cls_key in key:
                        return color
    except Exception:
        pass

    # 3. Fallback premium color palette
    fallback_palette = [
        "#D4AF37",  # Gold
        "#10B981",  # Emerald
        "#06B6D4",  # Teal
        "#3B82F6",  # Blue
        "#A855F7",  # Purple
        "#EC4899",  # Pink
        "#F59E0B",  # Amber
    ]
    return fallback_palette[index % len(fallback_palette)]



def plot_efficient_frontier(
    frontier: pd.DataFrame,
    random_portfolios: Optional[pd.DataFrame] = None,
    max_sharpe: Optional[dict] = None,
    min_vol: Optional[dict] = None,
    risk_free_rate: Optional[float] = None,
) -> go.Figure:
    """
    Plot the efficient frontier with optional random portfolio cloud,
    highlighted optimal portfolios, and Capital Allocation Line (CAL).

    CFA Reference: CFA Level I, Portfolio Management — CAL represents the
    risk-return tradeoff for portfolios combining the risk-free asset with
    the tangency portfolio. The CAL slope equals the maximum Sharpe ratio.

    Args:
        frontier: DataFrame with 'return', 'volatility' columns for the efficient frontier.
        random_portfolios: Optional DataFrame with random portfolio points.
        max_sharpe: Optional dict with tangency portfolio metrics (return, volatility, sharpe).
        min_vol: Optional dict with minimum volatility portfolio metrics.
        risk_free_rate: Optional risk-free rate for CAL computation (decimal, e.g., 0.045).
    """
    fig = go.Figure()

    # Random portfolios cloud
    if random_portfolios is not None:
        fig.add_trace(go.Scattergl(
            x=random_portfolios["volatility"] * 100,
            y=random_portfolios["return"] * 100,
            mode="markers",
            marker=dict(
                size=3,
                color=random_portfolios["sharpe"],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Sharpe"),
                opacity=0.4,
            ),
            name="Random Portfolios",
            hovertemplate="Return: %{y:.1f}%<br>Volatility: %{x:.1f}%<extra></extra>",
        ))

    # Efficient frontier line
    fig.add_trace(go.Scatter(
        x=frontier["volatility"] * 100,
        y=frontier["return"] * 100,
        mode="lines",
        line=dict(color=COLORS["accent"], width=3),
        name="Efficient Frontier",
    ))

    # Max Sharpe portfolio
    if max_sharpe is not None:
        fig.add_trace(go.Scatter(
            x=[max_sharpe["volatility"] * 100],
            y=[max_sharpe["return"] * 100],
            mode="markers",
            marker=dict(size=16, color=COLORS["warning"], symbol="star"),
            name=f"Max Sharpe ({max_sharpe['sharpe']:.2f})",
        ))

    # Min volatility portfolio
    if min_vol is not None:
        fig.add_trace(go.Scatter(
            x=[min_vol["volatility"] * 100],
            y=[min_vol["return"] * 100],
            mode="markers",
            marker=dict(size=14, color=COLORS["success"], symbol="diamond"),
            name=f"Min Volatility ({min_vol['volatility']:.1%})",
        ))

    # Capital Allocation Line (CAL): E(R) = Rf + Sharpe_max * σ
    # The CAL connects the risk-free asset (0, Rf) with the tangency portfolio
    # and extends beyond it (representing leveraged positions).
    if risk_free_rate is not None and max_sharpe is not None and max_sharpe.get("success", True):
        rf_pct = risk_free_rate * 100
        tangency_vol = max_sharpe["volatility"] * 100
        tangency_ret = max_sharpe["return"] * 100
        sharpe_ratio = max_sharpe["sharpe"]

        # Extend CAL to ~2.5x the tangency volatility (or frontier max, whichever is larger)
        frontier_max_vol = frontier["volatility"].max() * 100
        cal_max_vol = max(2.5 * tangency_vol, 1.2 * frontier_max_vol)

        # Two points: (0, Rf) and (cal_max_vol, Rf + Sharpe * cal_max_vol)
        cal_vols = [0, cal_max_vol]
        cal_rets = [rf_pct, rf_pct + sharpe_ratio * cal_max_vol]

        fig.add_trace(go.Scatter(
            x=cal_vols,
            y=cal_rets,
            mode="lines",
            line=dict(color=COLORS["primary"], width=2, dash="dash"),
            name=f"Capital Allocation Line (Sharpe={sharpe_ratio:.2f})",
            hovertemplate=(
                "CAL<br>"
                "Volatility: %{x:.1f}%<br>"
                "Expected Return: %{y:.1f}%<br>"
                "<i>E(R) = Rf + Sharpe × σ</i>"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        **CHART_LAYOUT,
        title="Efficient Frontier",
        xaxis_title="Annualized Volatility (%)",
        yaxis_title="Annualized Return (%)",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )

    return fig


def plot_allocation_pie(weights: dict, title: str = "Portfolio Allocation") -> go.Figure:
    """Pie chart of portfolio allocation weights."""
    # Filter out near-zero weights
    filtered = {k: v for k, v in weights.items() if abs(v) > 0.005}

    # Resolve colors dynamically using our premium color resolver
    asset_colors = [get_asset_color(label, i) for i, label in enumerate(filtered.keys())]

    fig = go.Figure(go.Pie(
        labels=list(filtered.keys()),
        values=list(filtered.values()),
        hole=0.45,
        textinfo="label+percent",
        marker=dict(
            colors=asset_colors,
            line=dict(color="#030712", width=2),
        ),
    ))

    fig.update_layout(
        **CHART_LAYOUT,
        title=title,
        showlegend=True,
    )

    return fig


def plot_monte_carlo_paths(
    paths: np.ndarray,
    n_display: int = 200,
    percentiles: bool = True,
    goal_amount: Optional[float] = None,
) -> go.Figure:
    """
    Plot Monte Carlo simulation paths with percentile bands.
    """
    fig = go.Figure()
    n_sims, n_periods = paths.shape
    x = list(range(n_periods))

    # Sample paths (semi-transparent)
    indices = np.random.choice(n_sims, min(n_display, n_sims), replace=False)
    for i in indices:
        fig.add_trace(go.Scatter(
            x=x, y=paths[i],
            mode="lines",
            line=dict(width=0.5, color=COLORS["primary"]),
            opacity=0.1,
            showlegend=False,
            hoverinfo="skip",
        ))

    if percentiles:
        # Percentile bands
        p5 = np.percentile(paths, 5, axis=0)
        p25 = np.percentile(paths, 25, axis=0)
        p50 = np.percentile(paths, 50, axis=0)
        p75 = np.percentile(paths, 75, axis=0)
        p95 = np.percentile(paths, 95, axis=0)

        fig.add_trace(go.Scatter(
            x=x, y=p95, mode="lines",
            line=dict(width=0, color=COLORS["success"]),
            showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=x, y=p5, mode="lines",
            fill="tonexty",
            fillcolor="rgba(16, 185, 129, 0.15)",
            line=dict(width=0),
            name="5th-95th percentile",
        ))
        fig.add_trace(go.Scatter(
            x=x, y=p50, mode="lines",
            line=dict(width=3, color=COLORS["warning"]),
            name="Median",
        ))

    # Goal line
    if goal_amount is not None:
        fig.add_hline(
            y=goal_amount,
            line_dash="dash",
            line_color=COLORS["danger"],
            annotation_text=f"Goal: ${goal_amount:,.0f}",
        )

    fig.update_layout(
        **CHART_LAYOUT,
        title="Monte Carlo Simulation — Portfolio Value Paths",
        xaxis_title="Year",
        yaxis_title="Portfolio Value ($)",
        yaxis_tickprefix="$",
    )

    return fig


def plot_correlation_heatmap(corr_matrix: pd.DataFrame) -> go.Figure:
    """Correlation heatmap of asset returns."""
    fig = go.Figure(go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns,
        y=corr_matrix.index,
        colorscale="RdBu_r",
        zmid=0,
        zmin=-1,
        zmax=1,
        text=corr_matrix.round(2).values,
        texttemplate="%{text}",
        textfont=dict(size=11),
    ))

    fig.update_layout(
        **CHART_LAYOUT,
        title="Asset Correlation Matrix",
        width=700,
        height=600,
    )

    return fig


def plot_price_history(
    prices: pd.DataFrame,
    normalize: bool = True,
    title: str = "Asset Price History",
) -> go.Figure:
    """
    Line chart of asset prices. If normalize=True, rebases all to 100.
    """
    # Clean the prices by forward-filling and backward-filling missing values.
    # This prevents NaN values (e.g. from different holiday schedules) from breaking the lines
    # and avoids division-by-NaN issues during normalization if the first row contains NaN.
    cleaned_prices = prices.ffill().bfill()

    if normalize:
        data = (cleaned_prices / cleaned_prices.iloc[0]) * 100
        yaxis_title = "Normalized Price (base=100)"
    else:
        data = cleaned_prices
        yaxis_title = "Price"

    fig = go.Figure()

    for i, col in enumerate(data.columns):
        fig.add_trace(go.Scatter(
            x=data.index,
            y=data[col],
            mode="lines",
            name=col,
            line=dict(width=2, color=get_asset_color(col, i)),
            connectgaps=True,
        ))

    fig.update_layout(
        **CHART_LAYOUT,
        title=title,
        yaxis_title=yaxis_title,
        hovermode="x unified",
    )

    return fig
