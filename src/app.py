"""
AI WealthPilot - Streamlit Application Entry Point
AI WealthPilot - Streamlit 应用入口

This is the main entry point for the Streamlit dashboard.
It provides the sidebar navigation and routes to individual page modules.

这是 Streamlit 仪表板的主入口。
提供侧栏导航并路由到各个页面模块。

Run with / 运行方式: streamlit run src/app.py
"""

import sys
from pathlib import Path

# ============================================================
# 路径配置：确保项目根目录在 Python 的搜索路径中
# Path setup: ensure the project root is on Python's module search path
# 这样 `from src.xxx import ...` 才能正常工作
# This allows `from src.xxx import ...` to work correctly
# ============================================================
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

# ============================================================
# Page Configuration / 页面配置
# 必须在所有其他 Streamlit 命令之前调用
# Must be called before any other Streamlit command
# ============================================================
st.set_page_config(
    page_title="AI WealthPilot",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Sidebar Navigation / 侧栏导航
# ============================================================
st.sidebar.title("🏦 AI WealthPilot")
st.sidebar.markdown("*Intelligent Wealth Management*")
st.sidebar.divider()

# 页面导航选择器 / Page navigation selector
page = st.sidebar.radio(
    "Navigation",
    options=[
        "📈 Market Dashboard",
        "📊 Portfolio Optimizer",
        "🎯 Retirement Planner",
        "🧠 Client Profiling",
        "🤖 AI Advisor",
    ],
    index=0,
)

st.sidebar.divider()
st.sidebar.caption("v0.3.0 · AI Advisor Online")

# ============================================================
# Page Router / 页面路由
# 根据用户在侧栏中选择的页面，渲染对应的内容
# Renders the corresponding page based on the user's sidebar selection
# ============================================================
if page == "📈 Market Dashboard":
    # 导入并渲染市场仪表板页面
    # Import and render the Market Dashboard page
    from src.pages.market_dashboard import render as render_market_dashboard
    render_market_dashboard()

elif page == "📊 Portfolio Optimizer":
    from src.pages.portfolio_optimizer import render as render_portfolio_optimizer
    render_portfolio_optimizer()

elif page == "🎯 Retirement Planner":
    from src.pages.retirement_planner import render as render_retirement_planner
    render_retirement_planner()

elif page == "🧠 Client Profiling":
    from src.pages.client_profiling import render as render_client_profiling
    render_client_profiling()

elif page == "🤖 AI Advisor":
    # 导入并渲染 AI 顾问页面
    # Import and render the AI Advisor page
    from src.pages.ai_advisor import render as render_ai_advisor
    render_ai_advisor()
