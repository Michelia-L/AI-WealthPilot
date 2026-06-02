"""
AI WealthPilot - AI Wealth Advisor Page
AI WealthPilot - AI 财富顾问页面

Interactive Streamlit page that integrates with the AI Advisor Agent
to generate personalized investment advisory reports. Users select
a saved client profile, preview its key metrics, then request an
AI-generated report powered by DeepSeek V4 Pro.

交互式 Streamlit 页面，与 AI 顾问 Agent 集成，
生成个性化的投资咨询建议书。用户选择已保存的客户画像，
预览其关键指标，然后请求由 DeepSeek V4 Pro 驱动的 AI 生成报告。

Page Flow / 页面流程:
    1. Check API configuration (检查 API 配置)
    2. Select saved client profile (选择已保存的客户画像)
    3. Preview profile key metrics (预览画像关键指标)
    4. Generate AI advisory report — streaming (生成 AI 建议书 — 流式)
    5. Display formatted report (展示格式化报告)

CFA Reference / CFA 参考:
    - CFA L3: Investment Policy Statement (IPS) — all 7 elements
      CFA 三级：投资政策声明 —— 7 大核心要素
    - CFA L3: Private Wealth Management Pathway
      CFA 三级：私人财富管理方向
"""

import streamlit as st
from pathlib import Path

from src.agents.profiler import (
    ClientProfile,
    load_profile,
    list_profiles,
    identify_behavioral_biases,
)
from src.agents.advisor import (
    is_api_configured,
    stream_advice,
    AdvisorReport,
)
from src.agents.report_storage import (
    save_report,
    load_report,
    list_reports,
    get_reports_for_profile,
    export_report_markdown,
)


def _render_api_status() -> bool:
    """
    Check and display the API configuration status.
    检查并展示 API 配置状态。

    If the DeepSeek API key is not configured, display a warning
    with setup instructions and return False to prevent generation.

    如果 DeepSeek API Key 未配置，显示警告信息和配置说明，
    并返回 False 以阻止生成。

    Returns:
        True if API is configured and ready, False otherwise.
        如果 API 已配置且就绪返回 True，否则返回 False。
    """
    if is_api_configured():
        return True

    st.warning(
        "⚠️ **DeepSeek API Key is not configured / DeepSeek API Key 未配置**\n\n"
        "To use the AI Advisor, please configure your API key:\n"
        "要使用 AI 顾问，请配置您的 API Key：\n\n"
        "1. Copy `.env.example` to `.env` / 复制 `.env.example` 为 `.env`\n"
        "2. Set `DEEPSEEK_API_KEY=your_key_here` / 设置您的 Key\n"
        "3. Get your key at [platform.deepseek.com]"
        "(https://platform.deepseek.com) / 在 DeepSeek 平台获取 Key\n"
        "4. Restart the application / 重启应用",
        icon="🔑",
    )
    return False


def _render_profile_selector() -> ClientProfile | None:
    """
    Render the profile selection dropdown and return the selected profile.
    渲染画像选择下拉菜单并返回所选画像。

    Lists all saved client profiles from the JSON document store,
    allowing the user to pick one for AI advisory generation.

    列出 JSON 文档存储中所有已保存的客户画像，
    允许用户选择一个进行 AI 建议书生成。

    Returns:
        Selected ClientProfile instance, or None if no profiles exist.
        所选的 ClientProfile 实例，如果没有画像则返回 None。
    """
    st.markdown("#### ⧉ Select Client Profile / 选择客户画像")

    profiles = list_profiles()

    if not profiles:
        st.info(
            "📝 No client profiles found. Please create one first in the "
            "**🧠 Client Profiling** page. / \n\n"
            "未找到客户画像。请先在 **🧠 客户画像** 页面创建一个。"
        )
        return None

    # 构建选择列表 / Build selection list
    # 每个选项显示: 姓名 | 年龄 | 风险等级 | 更新时间
    # Each option shows: name | age | risk level | updated time
    profile_options = {
        p["filepath"]: (
            f"{p['name']} | Age: {p['age']} | "
            f"Risk: {p['risk_level']} | "
            f"{p['updated_at'][:10]}"
        )
        for p in profiles
    }

    selected_path = st.selectbox(
        "Choose a profile / 选择画像",
        options=list(profile_options.keys()),
        format_func=lambda x: profile_options[x],
        key="advisor_profile_selector",
    )

    if selected_path:
        try:
            profile = load_profile(Path(selected_path))
            return profile
        except Exception as e:
            st.error(
                f"❌ Failed to load profile / 加载画像失败: {str(e)}"
            )
            return None

    return None


def _render_profile_preview(profile: ClientProfile) -> None:
    """
    Render a compact preview of the selected client profile.
    渲染所选客户画像的紧凑预览。

    Displays the most important metrics in a dashboard-style layout
    so the user can confirm they've selected the right profile
    before generating the AI advisory report.

    以仪表板风格布局展示最重要的指标，
    让用户在生成 AI 建议书之前确认选择了正确的画像。

    Args:
        profile: ClientProfile instance to preview.
    """
    st.markdown("#### ⌬ Profile Preview / 画像预览")

    # Row 1: 基本信息 / Basic info
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Name / 姓名", profile.name or "N/A")
    with col2:
        st.metric("Age / 年龄", profile.age)
    with col3:
        st.metric("Time Horizon / 期限", f"{profile.time_horizon_years}y")
    with col4:
        st.metric(
            "Risk Level / 风险等级",
            profile.risk_profile.tolerance_level.split(" / ")[0]
            if profile.risk_profile.tolerance_level else "N/A",
        )

    # Row 2: 财务指标 / Financial metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Net Worth / 净资产",
            f"${profile.financial.net_worth:,.0f}",
        )
    with col2:
        st.metric(
            "Annual Income / 年收入",
            f"${profile.financial.annual_income:,.0f}",
        )
    with col3:
        st.metric(
            "Savings Rate / 储蓄率",
            f"{profile.financial.savings_rate:.1%}",
        )
    with col4:
        # 显示风险评分冲突状态 / Show risk score conflict status
        rp = profile.risk_profile
        if rp.ability_score > 0 and rp.willingness_score > 0:
            score_text = (
                f"{rp.ability_score:.1f} / {rp.willingness_score:.1f}"
            )
            st.metric(
                "Ability / Willingness",
                score_text,
                delta=(
                    "⚠ Conflict"
                    if abs(rp.ability_score - rp.willingness_score) >= 1.0
                    else "✓ Aligned"
                ),
                delta_color=(
                    "inverse"
                    if abs(rp.ability_score - rp.willingness_score) >= 1.0
                    else "normal"
                ),
            )
        else:
            st.metric("Risk Score / 风险评分", "N/A")

    # 投资目标快览 / Goals quick view
    if profile.goals:
        goals_summary = " | ".join(
            f"{g.name} (${g.target_amount:,.0f}, {g.years}y)"
            for g in profile.goals
        )
        st.caption(f"🎯 Goals / 目标: {goals_summary}")

    # === 行为偏差检测 / Behavioral Bias Detection ===
    biases = identify_behavioral_biases(profile)
    if biases:
        with st.expander(
            f"🧠 Behavioral Bias Analysis / 行为偏差分析 "
            f"({len(biases)} detected / 检测到 {len(biases)} 个)",
            expanded=False,
        ):
            for bias in biases:
                severity_icon = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢",
                }.get(bias.severity, "⚪")

                st.markdown(
                    f"{severity_icon} **{bias.name}** "
                    f"(Severity / 严重程度: {bias.severity})"
                )
                st.caption(bias.description)
                st.info(f"💡 **Recommendation / 建议**: {bias.recommendation}")
                st.divider()


def _render_report(report: AdvisorReport, profile: ClientProfile = None) -> None:
    """
    Render the metadata footer and save options for a generated advisory report.
    渲染已生成建议书的元数据页脚和保存选项。

    Shows model information, token usage, generation timestamp,
    and provides save/export functionality.

    展示模型信息、token 用量、生成时间戳，
    并提供保存/导出功能。

    Args:
        report: Completed AdvisorReport with metadata.
        profile: Associated ClientProfile (optional, for saving).
    """
    with st.expander("📊 Report Metadata / 报告元数据", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.caption(f"🤖 Model: `{report.model}`")
            st.caption(f"👤 Client: {report.client_name}")
        with col2:
            st.caption(f"📝 Prompt tokens: {report.prompt_tokens:,}")
            st.caption(f"💬 Completion tokens: {report.completion_tokens:,}")
        with col3:
            st.caption(f"📊 Total tokens: {report.total_tokens:,}")
            st.caption(f"🕐 Generated: {report.generated_at[:19]}")

    # === 保存和导出选项 / Save and Export Options ===
    st.markdown("#### ⧉ Save Report / 保存报告")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("💾 Save to Library / 保存到库", key="save_report_btn"):
            try:
                saved = save_report(
                    content=report.content,
                    client_name=report.client_name,
                    model=report.model,
                    profile_filepath=str(profile) if profile else None,
                    prompt_tokens=report.prompt_tokens,
                    completion_tokens=report.completion_tokens,
                )
                st.success(
                    f"✅ Report saved! / 报告已保存！\n\n"
                    f"File / 文件: `{saved.filepath}`"
                )
            except Exception as e:
                st.error(f"❌ Save failed / 保存失败: {str(e)}")

    with col2:
        # Markdown 下载按钮 / Markdown download button
        markdown_content = f"""# Investment Advisory Report / 投资咨询建议书

**Client / 客户**: {report.client_name}
**Generated / 生成时间**: {report.generated_at}
**Model / 模型**: {report.model}

---

{report.content}
"""
        st.download_button(
            label="📥 Download Markdown / 下载 Markdown",
            data=markdown_content,
            file_name=f"advisory_report_{report.client_name}_{report.generated_at[:10]}.md",
            mime="text/markdown",
            key="download_markdown_btn",
        )

    with col3:
        # JSON 下载按钮 / JSON download button
        import json
        report_json = json.dumps({
            "client_name": report.client_name,
            "model": report.model,
            "generated_at": report.generated_at,
            "content": report.content,
            "tokens": {
                "prompt": report.prompt_tokens,
                "completion": report.completion_tokens,
                "total": report.total_tokens,
            },
        }, indent=2, ensure_ascii=False)

        st.download_button(
            label="📥 Download JSON / 下载 JSON",
            data=report_json,
            file_name=f"advisory_report_{report.client_name}_{report.generated_at[:10]}.json",
            mime="application/json",
            key="download_json_btn",
        )


def _render_historical_reports(profile: ClientProfile = None) -> None:
    """
    Render the historical reports section.
    渲染历史报告部分。

    Displays previously saved reports with options to view and load.

    展示先前保存的报告，提供查看和加载选项。

    Args:
        profile: Optional ClientProfile to filter reports by.
                 可选的 ClientProfile，用于按客户筛选报告。
    """
    st.markdown("#### ⧉ Historical Reports / 历史报告")

    if profile:
        # 获取特定客户的历史报告 / Get reports for specific client
        profile_path = None
        profiles_list = list_profiles()
        for p in profiles_list:
            if p["name"] == profile.name:
                profile_path = p["filepath"]
                break

        if profile_path:
            reports = get_reports_for_profile(profile_path)
        else:
            reports = []
    else:
        # 获取所有报告 / Get all reports
        reports_data = list_reports(limit=20)
        reports = reports_data

    if not reports:
        st.info(
            "📝 No saved reports found. Generate and save a report first. / "
            "未找到已保存的报告。请先生成并保存一份报告。"
        )
        return

    # 显示报告列表 / Display report list
    for i, report_info in enumerate(reports[:10]):  # 显示最近10份
        if isinstance(report_info, dict):
            # 来自 list_reports 的字典格式 / Dict format from list_reports
            with st.expander(
                f"📄 {report_info.get('client_name', 'Unknown')} - "
                f"{report_info.get('generated_at', '')[:10]}",
                expanded=False,
            ):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"🤖 Model: {report_info.get('model', 'N/A')}")
                    st.caption(
                        f"📊 Tokens: {report_info.get('total_tokens', 0):,}"
                    )
                with col2:
                    if st.button(
                        "👁️ View / 查看",
                        key=f"view_report_{i}",
                    ):
                        try:
                            report = load_report(
                                Path(report_info["filepath"])
                            )
                            st.session_state.viewing_report = report
                        except Exception as e:
                            st.error(f"Failed to load / 加载失败: {str(e)}")
        else:
            # StoredReport 对象格式 / StoredReport object format
            with st.expander(
                f"📄 {report.client_name} - {report.generated_at[:10]}",
                expanded=False,
            ):
                st.caption(f"🤖 Model: {report.model}")
                st.caption(f"📊 Tokens: {report.total_tokens:,}")
                st.markdown(report.content[:500] + "...")

    # 显示正在查看的报告 / Display viewing report
    if "viewing_report" in st.session_state and st.session_state.viewing_report:
        report = st.session_state.viewing_report
        st.divider()
        st.markdown(f"### 📄 Viewing Report / 查看报告")
        st.markdown(f"**Client / 客户**: {report.client_name}")
        st.markdown(f"**Generated / 生成时间**: {report.generated_at}")
        st.markdown(report.content)

        if st.button("❌ Close / 关闭", key="close_viewing_report"):
            st.session_state.viewing_report = None
            st.rerun()


def render() -> None:
    """
    Main render function for the AI Advisor page.
    AI 顾问页面的主渲染函数。

    Orchestrates the full page flow:
    编排完整的页面流程：
        1. Title and description (标题与描述)
        2. API status check (API 状态检查)
        3. Profile selection (画像选择)
        4. Profile preview (画像预览)
        5. Generate button → streaming report (生成按钮 → 流式报告)
        6. Report metadata footer (报告元数据页脚)
    """
    # === 页面标题 / Page Title ===
    st.title("✦ AI Wealth Advisor / AI 财富顾问")
    st.markdown(
        "Generate a personalized, CFA-compliant investment advisory report "
        "powered by **DeepSeek V4 Pro**. Select a client profile below to "
        "get started. / \n\n"
        "生成由 **DeepSeek V4 Pro** 驱动的个性化、符合 CFA 规范的投资咨询建议书。"
        "请在下方选择一个客户画像开始。"
    )
    st.divider()

    # === Step 1: API 状态检查 / API Status Check ===
    api_ready = _render_api_status()

    # === Step 2: 画像选择 / Profile Selection ===
    profile = _render_profile_selector()

    if profile is None:
        return

    st.divider()

    # === Step 3: 画像预览 / Profile Preview ===
    _render_profile_preview(profile)
    st.divider()

    # === Step 4: 生成建议书 / Generate Advisory Report ===
    st.markdown("#### ✦ Generate Advisory Report / 生成建议书")

    if not api_ready:
        st.button(
            "🚀 Generate AI Advice / 生成 AI 建议",
            type="primary",
            disabled=True,
            help="Please configure your DeepSeek API key first / "
                 "请先配置 DeepSeek API Key",
        )
        return

    # 使用 session state 管理报告状态
    # Use session state to manage report state
    if "advisor_report" not in st.session_state:
        st.session_state.advisor_report = None
    if "advisor_report_content" not in st.session_state:
        st.session_state.advisor_report_content = None

    col1, col2 = st.columns([1, 3])
    with col1:
        generate_clicked = st.button(
            "🚀 Generate AI Advice / 生成 AI 建议",
            type="primary",
            key="generate_advice_btn",
        )
    with col2:
        if st.session_state.advisor_report is not None:
            if st.button(
                "🔄 Regenerate / 重新生成",
                key="regenerate_advice_btn",
            ):
                generate_clicked = True
                st.session_state.advisor_report = None
                st.session_state.advisor_report_content = None

    if generate_clicked:
        st.divider()
        st.markdown("#### 📝 AI Investment Advisory Report / AI 投资建议书")

        # 流式生成建议书 / Stream the advisory report
        with st.spinner("🧠 AI is analyzing your profile... / AI 正在分析你的画像..."):
            text_stream, report_container = stream_advice(profile)

            # 使用 st.write_stream 实时渲染流式输出
            # Use st.write_stream for real-time streaming display
            try:
                full_response = st.write_stream(text_stream)
            except Exception as e:
                st.error(
                    f"❌ Error during generation / 生成过程中出错:\n\n{str(e)}"
                )
                return

        # 提取报告元数据 / Extract report metadata
        if report_container:
            report = report_container[0]
            if report.success:
                st.session_state.advisor_report = report
                st.session_state.advisor_report_content = full_response
                st.success(
                    "✅ Advisory report generated successfully! / "
                    "建议书生成成功！"
                )
                _render_report(report, profile)
            else:
                st.error(
                    f"❌ Generation failed / 生成失败:\n\n"
                    f"{report.error_message}"
                )

    # 如果之前已生成过报告，重新显示 / Redisplay if report was previously generated
    elif st.session_state.advisor_report_content is not None:
        st.divider()
        st.markdown("#### 📝 AI Investment Advisory Report / AI 投资建议书")
        st.markdown(st.session_state.advisor_report_content)
        if st.session_state.advisor_report:
            _render_report(st.session_state.advisor_report, profile)

    # === 历史报告 / Historical Reports ===
    st.divider()
    _render_historical_reports(profile)

    # === 合规声明 / Compliance Disclaimer ===
    st.divider()
    st.caption(
        "⚠️ **Disclaimer / 免责声明**: This AI-generated report is for "
        "educational and demonstration purposes only. It does not constitute "
        "professional financial advice. Always consult a licensed financial "
        "advisor before making investment decisions. / "
        "本 AI 生成的报告仅用于教育和演示目的，不构成专业的财务建议。"
        "在做出投资决策之前，请务必咨询持牌财务顾问。"
    )
