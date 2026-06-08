"""
AI WealthPilot - Compliance & Suitability Disclaimer Components
AI WealthPilot - 合规与适配性免责声明组件

Shared Streamlit UI components that render front-of-page regulatory
disclaimers before any quantitative output is displayed. In real
wealth management scenarios, compliance statements must be presented
and acknowledged before clients view any analytics.

共享的 Streamlit UI 组件，在任何量化输出展示之前渲染前置监管
免责声明。在真实财富管理场景中，合规声明必须在客户查看分析结果
之前呈现并获得确认。

CFA References:
    - CFA L3 PWM: Suitability and fiduciary duty standards
      (IPS must include risk disclosure and compliance language).
    - Global Investment Performance Standards (GIPS):
      Disclosure of model limitations and backtesting caveats.
"""

import streamlit as st


# ============================================================
# Bilingual Compliance Text / 双语合规声明文本
# ============================================================

_COMPLIANCE_ITEMS = [
    {
        "title_en": "1. No Investment Advice",
        "title_cn": "1. 不构成投资建议",
        "body_en": (
            "All outputs from this system (including asset allocations, optimization "
            "results, AI-generated reports, Monte Carlo simulations, and any other "
            "quantitative analytics) are provided for <strong>educational and informational "
            "demonstration purposes only</strong>. They do <strong>not</strong> constitute investment "
            "advice, a recommendation, or a solicitation to buy or sell any security."
        ),
        "body_cn": (
            "本系统输出的所有内容（包括资产配置、优化结果、AI 生成报告、蒙特卡洛模拟及其他"
            "量化分析）<strong>仅用于教育和信息演示目的</strong>，<strong>不构成</strong>任何形式的投资建议、推荐或"
            "证券买卖邀约。"
        ),
    },
    {
        "title_en": "2. Historical Backtesting Limitation",
        "title_cn": "2. 历史回溯的局限性",
        "body_en": (
            "All quantitative analyses and optimization results are based on "
            "<strong>historical data and statistical models</strong> through backtesting. "
            "<strong>Past performance does not guarantee future results.</strong> Market "
            "conditions, correlations, and return distributions may change "
            "materially over time."
        ),
        "body_cn": (
            "所有量化分析和优化结果均基于<strong>历史数据和统计模型</strong>进行回溯测试。"
            "<strong>过去的表现不能保证未来的结果。</strong> 市场条件、资产相关性和收益分布"
            "可能随时间发生重大变化。"
        ),
    },
    {
        "title_en": "3. Model Assumptions & Limitations",
        "title_cn": "3. 模型假设与局限性",
        "body_en": (
            "Mathematical models (MVO, Black-Litterman, Monte Carlo simulation, etc.) "
            "rely on <strong>simplifying assumptions</strong> and may not fully account for "
            "market liquidity, transaction costs, tax implications, regulatory "
            "constraints, or extreme tail events (black swans)."
        ),
        "body_cn": (
            "数学模型（MVO、Black-Litterman、蒙特卡洛模拟等）依赖于<strong>简化的假设条件</strong>，"
            "可能未能充分考虑市场流动性、交易成本、税收影响、监管限制或极端尾部事件"
            "（黑天鹅）。"
        ),
    },
    {
        "title_en": "4. Consult a Licensed Advisor",
        "title_cn": "4. 请咨询持牌顾问",
        "body_en": (
            "Before making any investment decision, you <strong>must</strong> consult a "
            "qualified and licensed financial advisor who can assess your "
            "individual financial situation, risk tolerance, and investment "
            "objectives. Do not rely solely on automated quantitative outputs."
        ),
        "body_cn": (
            "在做出任何投资决策之前，请<strong>务必</strong>咨询持有合法牌照的合格财务顾问，"
            "由其根据您的个人财务状况、风险承受能力和投资目标进行独立评估。"
            "切勿仅依赖自动化量化输出做出投资决策。"
        ),
    },
]

_DISCLAIMER_HEADER_EN = "Suitability Disclaimer / 适配性免责声明"
_ACKNOWLEDGMENT_EN = (
    "I have read, understood, and agree to the above disclaimer. "
    "I acknowledge that the outputs of this system do not constitute "
    "investment advice."
)
_ACKNOWLEDGMENT_CN = (
    "我已阅读、理解并同意上述免责声明。我知晓本系统的输出不构成投资建议。"
)

_BANNER_TEXT = (
    "**Disclaimer / 免责声明**: Quantitative outputs on this page are "
    "based on historical data and statistical models. They are for "
    "**informational and educational purposes only** and do **not** "
    "constitute investment advice. Past performance does not guarantee "
    "future results. Consult a licensed financial advisor before making "
    "any investment decision. / "
    "本页面的量化输出基于历史数据和统计模型，仅供**信息和教育目的**使用，"
    "**不构成**投资建议。过去的表现不能保证未来的结果。请在做出任何投资决策前"
    "咨询持牌财务顾问。"
)

_INFO_TEXT = (
    "ℹ️ **Notice / 提示**: Data entered on this page is stored locally "
    "for demonstration purposes only. No real personal financial data "
    "is collected or transmitted. / "
    "本页面输入的数据仅在本地存储，用于演示目的。不收集或传输真实的个人财务数据。"
)


# ============================================================
# Compliance UI Components / 合规 UI 组件
# ============================================================

def render_suitability_disclaimer(key_suffix: str = "default") -> bool:
    """
    Render a prominent suitability disclaimer with a mandatory acknowledgment
    checkbox. Must be confirmed before any quantitative output is displayed.

    渲染醒目的适配性免责声明，包含必须勾选的确认复选框。
    用户在确认之前不应看到任何量化输出。

    Args:
        key_suffix: Unique key suffix to avoid collision across pages
                    (e.g., "advisor", "optimizer", "retirement").

    Returns:
        True if the user has checked the acknowledgment box, False otherwise.
    """
    checkbox_key = f"compliance_acknowledged_{key_suffix}"

    st.markdown(
        '<div class="compliance-disclaimer">',
        unsafe_allow_html=True,
    )

    # Header
    st.warning(_DISCLAIMER_HEADER_EN, icon="⚠️")

    # Render each compliance item as collapsible detail or inline
    for item in _COMPLIANCE_ITEMS:
        st.markdown(f"**{item['title_en']}**")
        st.markdown(
            f'<div class="compliance-body">{item["body_en"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**{item['title_cn']}**")
        st.markdown(
            f'<div class="compliance-body">{item["body_cn"]}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Acknowledgment checkbox
    acknowledged = st.checkbox(
        f"{_ACKNOWLEDGMENT_EN}\n\n{_ACKNOWLEDGMENT_CN}",
        key=checkbox_key,
        value=False,
    )

    st.markdown('</div>', unsafe_allow_html=True)

    return acknowledged


def render_compliance_banner() -> None:
    """
    Render a compact compliance banner for auto-display pages
    (e.g., Market Dashboard) where data loads automatically
    without a user-triggered "generate" action.

    Distinct from the full disclaimer: no checkbox is required,
    but the banner appears prominently at the top of the page
    before any quantitative content.

    为自动展示数据的页面（如市场仪表板）渲染紧凑的合规横幅。
    与完整免责声明不同：无需 checkbox，但横幅会醒目地显示在
    页面顶部，先于任何量化内容。
    """
    st.info(_BANNER_TEXT, icon="⚠️")


def render_client_profiling_notice() -> None:
    """
    Render a lightweight informational notice for data-input pages
    (e.g., Client Profiling) that do not produce quantitative outputs.

    For data-collection pages it is appropriate to show a brief
    privacy and demo-purpose notice rather than the full investment
    disclaimer.

    为数据输入页面（如客户画像）渲染轻量级信息提示。
    对于数据收集页面，显示简短的隐私和演示目的通知而非完整
    投资声明更为合适。
    """
    st.info(_INFO_TEXT, icon="ℹ️")
