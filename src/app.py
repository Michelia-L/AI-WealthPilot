"""
AI WealthPilot - Streamlit Application Entry Point

Main entry point for the Streamlit dashboard. Provides the sidebar
navigation and routes to individual page modules.

Navigation icons are inline SVG (Lucide-style hairlines) rather than Unicode
glyphs, so they render consistently across Windows/macOS/Linux and carry
aria-labels for screen readers.

Run command: streamlit run src/app.py
"""

import sys
from pathlib import Path
from importlib import import_module

# Path setup: ensure the project root is on Python's module search path
# This allows `from src.xxx import ...` to work correctly
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from src.views.styles import inject_premium_styles, render_sidebar_nav, NAV_ITEMS
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

# Selection round-trips through query params (?nav=<key>) so the custom HTML
# nav buttons can drive routing. The active key persists in session_state.
qp = st.query_params
if "nav" in qp and any(item["key"] == qp["nav"] for item in NAV_ITEMS):
    st.session_state["nav_active"] = qp["nav"]

active_key = st.session_state.get("nav_active", NAV_ITEMS[0]["key"])
st.sidebar.markdown(render_sidebar_nav(NAV_ITEMS, active_key), unsafe_allow_html=True)

st.sidebar.divider()
st.sidebar.caption(f"v{APP_VERSION} · AI Advisor Online")

# Map key -> (module path, render function name)
_ROUTES = {
    "market": ("src.views.market_dashboard", "render"),
    "portfolio": ("src.views.portfolio_optimizer", "render"),
    "retirement": ("src.views.retirement_planner", "render"),
    "profiling": ("src.views.client_profiling", "render"),
    "advisor": ("src.views.ai_advisor", "render"),
}

module_name, fn_name = _ROUTES[active_key]
mod = import_module(module_name)
getattr(mod, fn_name)()
