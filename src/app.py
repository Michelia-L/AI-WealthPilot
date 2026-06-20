"""
AI WealthPilot - Streamlit Application Entry Point

This is the main entry point for the Streamlit dashboard.
It provides the sidebar navigation and routes to individual page modules.

Run command: streamlit run src/app.py
"""

import sys
from pathlib import Path

# Path setup: ensure the project root is on Python's module search path
# This allows `from src.xxx import ...` to work correctly
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from src.views.styles import inject_premium_styles
from src.config import APP_VERSION

# Page Configuration
# Must be called before any other Streamlit command
st.set_page_config(
    page_title="AI WealthPilot",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_premium_styles()

# Sidebar Navigation
st.sidebar.markdown(
    '<div class="sidebar-brand">AI WealthPilot</div>'
    '<div class="sidebar-subtitle">Intelligent Wealth Management</div>',
    unsafe_allow_html=True,
)
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    options=[
        "✦ Market Dashboard",
        "⧉ Portfolio Optimizer",
        "⌖ Retirement Planner",
        "⌬ Client Profiling",
        "◈ AI Advisor",
    ],
    index=0,
)

st.sidebar.divider()
st.sidebar.caption(f"v{APP_VERSION} · AI Advisor Online")

# Page Router
# Renders the corresponding page based on the user's sidebar selection
if page == "✦ Market Dashboard":
    # Import and render the Market Dashboard page
    from src.views.market_dashboard import render as render_market_dashboard
    render_market_dashboard()

elif page == "⧉ Portfolio Optimizer":
    from src.views.portfolio_optimizer import render as render_portfolio_optimizer
    render_portfolio_optimizer()

elif page == "⌖ Retirement Planner":
    from src.views.retirement_planner import render as render_retirement_planner
    render_retirement_planner()

elif page == "⌬ Client Profiling":
    from src.views.client_profiling import render as render_client_profiling
    render_client_profiling()

elif page == "◈ AI Advisor":
    # Import and render the AI Advisor page
    from src.views.ai_advisor import render as render_ai_advisor
    render_ai_advisor()

