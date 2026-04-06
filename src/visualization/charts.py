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
# Color Palette — Premium dark theme
# ============================================================
COLORS = {
    "primary": "#6366f1",      # Indigo
    "secondary": "#8b5cf6",    # Purple
    "accent": "#0ea5e9",       # Sky blue
    "success": "#10b981",      # Emerald
    "warning": "#f59e0b",      # Amber
    "danger": "#ef4444",       # Red
    "bg_dark": "#0f172a",      # Slate 900
    "bg_card": "#1e293b",      # Slate 800
    "text": "#f1f5f9",         # Slate 100
    "text_muted": "#94a3b8",   # Slate 400
    "grid": "#334155",         # Slate 700
}

CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor=COLORS["bg_dark"],
    plot_bgcolor=COLORS["bg_card"],
    font=dict(family="Inter, sans-serif", color=COLORS["text"]),
    margin=dict(l=40, r=40, t=60, b=40),
    xaxis=dict(gridcolor=COLORS["grid"]),
    yaxis=dict(gridcolor=COLORS["grid"]),
)


def plot_efficient_frontier(
    frontier: pd.DataFrame,
    random_portfolios: Optional[pd.DataFrame] = None,
    max_sharpe: Optional[dict] = None,
    min_vol: Optional[dict] = None,
) -> go.Figure:
    """
    Plot the efficient frontier with optional random portfolio cloud
    and highlighted optimal portfolios.
    """
    fig = go.Figure()

    # Random portfolios cloud
    if random_portfolios is not None:
        fig.add_trace(go.Scatter(
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

    fig = go.Figure(go.Pie(
        labels=list(filtered.keys()),
        values=list(filtered.values()),
        hole=0.45,
        textinfo="label+percent",
        marker=dict(
            colors=px.colors.qualitative.Set2[:len(filtered)],
            line=dict(color=COLORS["bg_dark"], width=2),
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
    if normalize:
        data = (prices / prices.iloc[0]) * 100
        yaxis_title = "Normalized Price (base=100)"
    else:
        data = prices
        yaxis_title = "Price"

    fig = go.Figure()
    colors = px.colors.qualitative.Set2

    for i, col in enumerate(data.columns):
        fig.add_trace(go.Scatter(
            x=data.index,
            y=data[col],
            mode="lines",
            name=col,
            line=dict(width=2, color=colors[i % len(colors)]),
        ))

    fig.update_layout(
        **CHART_LAYOUT,
        title=title,
        yaxis_title=yaxis_title,
        hovermode="x unified",
    )

    return fig
