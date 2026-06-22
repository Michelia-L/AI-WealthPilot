"""
AI Wealth Advisor page — Streamlit UI for generating AI advisory reports.

Users select a client profile, preview key metrics, then generate a
personalized investment advisory report powered by DeepSeek V4 Pro.
"""

import streamlit as st
from pathlib import Path

from src.views.compliance import render_suitability_disclaimer
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
    """Check and display API configuration status. Returns True if ready."""
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
    """Render profile selection dropdown and return the selected profile."""
    st.markdown("#### Select Client Profile")

    profiles = list_profiles()

    if not profiles:
        st.info(
            "📝 No client profiles found. Please create one first in the "
            "**🧠 Client Profiling** page. / \n\n"
            "未找到客户画像。请先在 **🧠 客户画像** 页面创建一个。"
        )
        return None

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
            # Store the filepath for downstream use (e.g., linking reports)
            st.session_state.advisor_selected_profile_path = selected_path
            return profile
        except Exception as e:
            st.error(
                f"❌ Failed to load profile / 加载画像失败: {str(e)}"
            )
            return None

    return None


def _render_profile_preview(profile: ClientProfile) -> None:
    """Render a compact dashboard preview of the selected client profile."""
    st.markdown("#### Profile Preview")

    # Row 1: Basic info
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

    # Row 2: Financial metrics
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

    if profile.goals:
        goals_summary = " | ".join(
            f"{g.name} (${g.target_amount:,.0f}, {g.years}y)"
            for g in profile.goals
        )
        st.caption(f"🎯 Goals / 目标: {goals_summary}")

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
    """Render report metadata footer and save/export options."""
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

    st.markdown("#### Save Report")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("💾 Save to Library / 保存到库", key="save_report_btn"):
            try:
                saved = save_report(
                    content=report.content,
                    client_name=report.client_name,
                    model=report.model,
                    profile_filepath=st.session_state.get("advisor_selected_profile_path") if profile else None,
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
        # Markdown download button
        markdown_content = f"""# Investment Advisory Report
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
        # JSON download button
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
    """Render the historical reports section with view/load options."""
    st.markdown("#### Historical Reports")

    if profile:
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
        reports_data = list_reports(limit=20)
        reports = reports_data

    if not reports:
        st.info(
            "📝 No saved reports found. Generate and save a report first. / "
            "未找到已保存的报告。请先生成并保存一份报告。"
        )
        return

    for i, report_info in enumerate(reports[:10]):  # 显示最近10份
        if isinstance(report_info, dict):
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
            # StoredReport object format
            with st.expander(
                f"📄 {report.client_name} - {report.generated_at[:10]}",
                expanded=False,
            ):
                st.caption(f"🤖 Model: {report.model}")
                st.caption(f"📊 Tokens: {report.total_tokens:,}")
                st.markdown(report.content[:500] + "...")

    if "viewing_report" in st.session_state and st.session_state.viewing_report:
        report = st.session_state.viewing_report
        st.divider()
        st.markdown(f"### 📄 Viewing Report")
        st.markdown(f"**Client / 客户**: {report.client_name}")
        st.markdown(f"**Generated / 生成时间**: {report.generated_at}")
        st.markdown(report.content)

        if st.button("❌ Close / 关闭", key="close_viewing_report"):
            st.session_state.viewing_report = None
            st.rerun()


def render() -> None:
    """Main render function for the AI Advisor page."""
    st.title("AI Wealth Advisor / AI 财富顾问")
    st.markdown(
        "Generate a personalized, CFA-compliant investment advisory report "
        "powered by **DeepSeek V4 Pro**. Select a client profile below to "
        "get started. / \n\n"
        "生成由 **DeepSeek V4 Pro** 驱动的个性化、符合 CFA 规范的投资咨询建议书。"
        "请在下方选择一个客户画像开始。"
    )
    st.divider()

    api_ready = _render_api_status()

    profile = _render_profile_selector()

    if profile is None:
        return

    st.divider()

    _render_profile_preview(profile)
    st.divider()

    st.markdown("#### Generate Advisory Report")

    acknowledged = render_suitability_disclaimer("advisor")

    if not api_ready:
        st.button(
            "🚀 Generate AI Advice / 生成 AI 建议",
            type="primary",
            disabled=True,
            help="Please configure your DeepSeek API key first / "
                 "请先配置 DeepSeek API Key",
        )
        return

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
            disabled=not acknowledged,
            help="Please acknowledge the disclaimer above first / "
                 "请先确认上方的免责声明" if not acknowledged else None,
        )
    with col2:
        if st.session_state.advisor_report is not None:
            if st.button(
                "🔄 Regenerate / 重新生成",
                key="regenerate_advice_btn",
                disabled=not acknowledged,
            ):
                generate_clicked = True
                st.session_state.advisor_report = None
                st.session_state.advisor_report_content = None

    if generate_clicked:
        st.divider()
        st.markdown("#### 📝 AI Investment Advisory Report / AI 投资建议书")

        with st.spinner("🧠 AI is analyzing your profile... / AI 正在分析你的画像..."):
            text_stream, report_container = stream_advice(profile)

            # Use st.write_stream for real-time streaming display
            try:
                full_response = st.write_stream(text_stream)
            except Exception as e:
                st.error(
                    f"❌ Error during generation / 生成过程中出错:\n\n{str(e)}"
                )
                return

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

    elif st.session_state.advisor_report_content is not None:
        st.divider()
        st.markdown("#### 📝 AI Investment Advisory Report / AI 投资建议书")
        st.markdown(st.session_state.advisor_report_content)
        if st.session_state.advisor_report:
            _render_report(st.session_state.advisor_report, profile)

    st.divider()
    _render_historical_reports(profile)
