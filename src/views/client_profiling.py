"""
AI WealthPilot - Client Profiling Questionnaire Page
AI WealthPilot - 客户画像问卷页面

Interactive Streamlit page that collects client information through
a structured questionnaire based on the CFA IPS framework. Computes
risk tolerance scores and generates a complete client profile.

交互式 Streamlit 页面，通过基于 CFA IPS 框架的结构化问卷
收集客户信息。计算风险承受能力评分并生成完整的客户画像。

CFA Reference / CFA 参考:
    - CFA L3 Private Wealth: Investment Policy Statement (IPS) framework
      CFA 三级私人财富管理：投资政策声明（IPS）框架
    - CFA L3: Risk tolerance assessment = min(Ability, Willingness)
      CFA 三级：风险承受能力评估 = min(承受能力, 承担意愿)
"""

import streamlit as st
from pathlib import Path
from typing import Optional
import pandas as pd

from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
    assess_risk,
    save_profile,
    load_profile,
    list_profiles,
    compare_profiles,
    format_comparison_report,
    RISK_ABILITY_QUESTIONS,
    RISK_WILLINGNESS_QUESTIONS,
)


def _render_basic_info() -> dict:
    """
    Render the basic information section.
    渲染基本信息部分。

    Collects / 收集:
        - Name (姓名)
        - Age (年龄)
        - Marital status (婚姻状况)
        - Number of dependents (受抚养人数)

    Returns:
        Dict with basic info fields.
    """
    st.markdown("#### ⌬ Basic Information / 基本信息")

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name / 姓名", key="profile_name", placeholder="e.g., Zhang San")
        age = st.number_input("Age / 年龄", min_value=18, max_value=100, key="profile_age")
    with col2:
        marital_status = st.selectbox(
            "Marital Status / 婚姻状况",
            options=["single", "married", "divorced", "widowed"],
            format_func=lambda x: {
                "single": "Single / 单身",
                "married": "Married / 已婚",
                "divorced": "Divorced / 离异",
                "widowed": "Widowed / 丧偶",
            }[x],
            key="profile_marital_status",
        )
        dependents = st.number_input(
            "Number of dependents / 受抚养人数",
            min_value=0, max_value=20, key="profile_dependents",
        )

    return {
        "name": name,
        "age": age,
        "marital_status": marital_status,
        "dependents": dependents,
    }


def _render_financial_situation() -> dict:
    """
    Render the financial situation section.
    渲染财务状况部分。

    Collects / 收集:
        - Annual income (年收入)
        - Annual expenses (年支出)
        - Investable assets (可投资资产)
        - Total liabilities (负债总额)
        - Emergency fund months (应急基金月数)

    Returns:
        Dict with financial fields.
    """
    st.markdown("#### ⧉ Financial Situation / 财务状况")

    col1, col2 = st.columns(2)
    with col1:
        annual_income = st.number_input(
            "Annual income ($) / 年收入",
            min_value=0, step=10_000, format="%d",
            key="profile_annual_income",
        )
        investable_assets = st.number_input(
            "Investable assets ($) / 可投资资产",
            min_value=0, step=10_000, format="%d",
            key="profile_investable_assets",
        )
        emergency_fund_months = st.number_input(
            "Emergency fund (months of expenses) / 应急基金（月数）",
            min_value=0.0, step=1.0,
            key="profile_emergency_fund_months",
        )
    with col2:
        annual_expenses = st.number_input(
            "Annual expenses ($) / 年支出",
            min_value=0, step=5_000, format="%d",
            key="profile_annual_expenses",
        )
        total_liabilities = st.number_input(
            "Total liabilities ($) / 负债总额",
            min_value=0, step=10_000, format="%d",
            key="profile_total_liabilities",
        )

    return {
        "annual_income": annual_income,
        "annual_expenses": annual_expenses,
        "investable_assets": investable_assets,
        "total_liabilities": total_liabilities,
        "emergency_fund_months": emergency_fund_months,
    }


def _render_investment_goals() -> list[dict]:
    """
    Render the investment goals section with dynamic add/remove.
    渲染投资目标部分，支持动态添加/删除。

    Each goal has / 每个目标包含:
        - Name (名称): e.g., Retirement, Education, House
        - Target amount (目标金额)
        - Time horizon (时间范围, years)
        - Priority (优先级)

    Returns:
        List of goal dicts.
    """
    st.markdown("#### ✦ Investment Goals / 投资目标")

    # 使用 session state 管理目标列表
    # Use session state to manage the goals list
    if "goals" not in st.session_state:
        st.session_state.goals = [
            {"name": "Retirement / 退休", "target_amount": 2_000_000, "years": 30, "priority": "high"},
        ]

    goals = st.session_state.goals

    # 展示现有目标 / Display existing goals
    for i, goal in enumerate(goals):
        col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 0.5])
        with col1:
            goals[i]["name"] = st.text_input(
                f"Goal {i+1}", value=goal["name"], key=f"goal_name_{i}",
            )
        with col2:
            goals[i]["target_amount"] = st.number_input(
                f"Target ($)", value=goal["target_amount"],
                min_value=0, step=10_000, format="%d", key=f"goal_amount_{i}",
            )
        with col3:
            goals[i]["years"] = st.number_input(
                f"Years", value=goal["years"],
                min_value=1, max_value=100, key=f"goal_years_{i}",
            )
        with col4:
            goals[i]["priority"] = st.selectbox(
                f"Priority",
                options=["high", "medium", "low"],
                index=["high", "medium", "low"].index(goal["priority"]),
                key=f"goal_priority_{i}",
            )
        with col5:
            st.markdown("")  # spacing
            if len(goals) > 1 and st.button("🗑️", key=f"goal_del_{i}"):
                goals.pop(i)
                st.rerun()

    # 添加新目标按钮 / Add new goal button
    if st.button("➕ Add Goal / 添加目标"):
        goals.append({
            "name": "",
            "target_amount": 100_000,
            "years": 10,
            "priority": "medium",
        })
        st.rerun()

    return goals


def _render_risk_ability_questions() -> dict:
    """
    Render the risk ability (objective) questionnaire.
    渲染风险承受能力（客观）问卷。

    These questions assess the client's OBJECTIVE capacity to bear risk,
    based on their financial situation and knowledge.

    这些问题评估客户承担风险的客观能力，基于其财务状况和知识。

    Returns:
        Dict mapping question keys to selected option keys.
    """
    st.markdown("#### ⌬ Risk Ability Assessment / 风险承受能力评估")
    st.caption(
        "These questions assess your **objective capacity** to bear risk. / "
        "这些问题评估你承担风险的**客观能力**。"
    )

    answers = {}
    for q_key, q_data in RISK_ABILITY_QUESTIONS.items():
        options = list(q_data["options"].keys())
        labels = [q_data["options"][opt]["label"] for opt in options]

        selected = st.radio(
            q_data["question"],
            options=options,
            format_func=lambda x, opts=q_data["options"]: opts[x]["label"],
            key=f"ability_{q_key}",
        )
        answers[q_key] = selected

    return answers


def _render_risk_willingness_questions() -> dict:
    """
    Render the risk willingness (subjective) questionnaire.
    渲染风险承担意愿（主观）问卷。

    These questions assess the client's PSYCHOLOGICAL comfort with risk,
    which may differ from their objective capacity.

    这些问题评估客户对风险的心理承受能力，
    可能与其客观能力不同。

    Returns:
        Dict mapping question keys to selected option keys.
    """
    st.markdown("#### ⌬ Risk Willingness Assessment / 风险承担意愿评估")
    st.caption(
        "These questions assess your **psychological comfort** with risk. "
        "Answer honestly — there are no right or wrong answers. / "
        "这些问题评估你对风险的**心理承受能力**。请如实作答——没有对错之分。"
    )

    answers = {}
    for q_key, q_data in RISK_WILLINGNESS_QUESTIONS.items():
        selected = st.radio(
            q_data["question"],
            options=list(q_data["options"].keys()),
            format_func=lambda x, opts=q_data["options"]: opts[x]["label"],
            key=f"willingness_{q_key}",
        )
        answers[q_key] = selected

    return answers


def _render_profile_summary(profile: ClientProfile) -> None:
    """
    Render the completed profile summary and risk assessment.
    渲染完成的画像摘要和风险评估。

    Displays / 展示:
        - Client overview (客户概览)
        - Financial summary (财务摘要)
        - Risk tolerance result with CFA explanation (风险承受能力结果)
        - Investment goals (投资目标)

    Args:
        profile: Completed ClientProfile instance.
    """
    st.markdown("#### ⧉ Profile Summary / 画像摘要")

    # === 客户概览 / Client Overview ===
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Name / 姓名", profile.name or "N/A")
    with col2:
        st.metric("Age / 年龄", profile.age)
    with col3:
        st.metric("Dependents / 受抚养人", profile.dependents)
    with col4:
        st.metric("Time Horizon / 投资期限", f"{profile.time_horizon_years} years / 年")

    # === 财务摘要 / Financial Summary ===
    st.markdown("**Financial Overview / 财务概览**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Net Worth / 净资产", f"${profile.financial.net_worth:,.0f}")
    with col2:
        st.metric("Savings Rate / 储蓄率", f"{profile.financial.savings_rate:.1%}")
    with col3:
        st.metric("Annual Income / 年收入", f"${profile.financial.annual_income:,.0f}")
    with col4:
        st.metric("Emergency Fund / 应急基金", f"{profile.financial.emergency_fund_months:.0f} months / 月")

    st.divider()

    # === 风险评估结果 / Risk Assessment Result ===
    st.markdown("**Risk Tolerance Assessment / 风险承受能力评估**")
    st.markdown("")

    rp = profile.risk_profile

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Ability Score / 承受能力评分",
            f"{rp.ability_score:.1f} / 5",
            help="Objective capacity based on financial situation / 基于财务状况的客观能力",
        )
    with col2:
        st.metric(
            "Willingness Score / 承担意愿评分",
            f"{rp.willingness_score:.1f} / 5",
            help="Psychological comfort with risk / 对风险的心理承受能力",
        )
    with col3:
        st.metric(
            "Final Score / 最终评分",
            f"{rp.final_score:.1f} / 5",
            help="min(Ability, Willingness) — CFA principle",
        )

    # 风险等级展示 / Risk level display
    tolerance = rp.tolerance_level
    if rp.ability_score > 0 and rp.willingness_score > 0:
        if rp.ability_score < rp.willingness_score:
            note = (
                "⚠️ Your ability to bear risk is LOWER than your willingness. "
                "CFA guidelines recommend using the lower score. "
                "Consider building a larger emergency fund or increasing savings. / "
                "你的风险承受能力低于你的承担意愿。"
                "CFA 准则建议采用较低评分。"
                "建议增加应急基金或提高储蓄率。"
            )
        elif rp.willingness_score < rp.ability_score:
            note = (
                "💡 Your willingness to take risk is LOWER than your ability. "
                "CFA guidelines recommend using the lower score. "
                "You may benefit from education about long-term investing. / "
                "你的风险承担意愿低于你的承受能力。"
                "CFA 准则建议采用较低评分。"
                "你可以通过学习长期投资知识来提升信心。"
            )
        else:
            note = (
                "✅ Your ability and willingness to take risk are aligned. "
                "This is the ideal scenario for consistent investment planning. / "
                "你的承受能力和承担意愿一致，这是投资规划的理想状态。"
            )
        st.info(note)

    st.success(f"**Risk Tolerance Level / 风险承受能力等级: {tolerance}**")

    st.divider()

    # === 投资目标 / Investment Goals ===
    if profile.goals:
        st.markdown("**Investment Goals / 投资目标**")
        goals_data = [
            {
                "Goal / 目标": g.name,
                "Target ($) / 目标金额": f"${g.target_amount:,.0f}",
                "Years / 年数": g.years,
                "Priority / 优先级": g.priority,
            }
            for g in profile.goals
        ]
        st.dataframe(
            pd.DataFrame(goals_data),
            use_container_width=True,
            hide_index=True,
        )

    # === 特殊情况 / Unique Circumstances ===
    if profile.esg_preference or profile.sector_restrictions or profile.notes:
        st.markdown("**Special Considerations / 特殊考量**")
        if profile.esg_preference:
            st.write("- ESG investing preference / 偏好 ESG 投资")
        if profile.sector_restrictions:
            st.write(f"- Sector restrictions / 行业限制: {', '.join(profile.sector_restrictions)}")
        if profile.notes:
            st.write(f"- Notes / 备注: {profile.notes}")


def render() -> None:
    """
    Main render function for the Client Profiling page.
    客户画像页面的主渲染函数。

    Page flow / 页面流程:
        1. Basic information / 基本信息
        2. Financial situation / 财务状况
        3. Investment goals / 投资目标
        4. Risk ability questionnaire / 风险承受能力问卷
        5. Risk willingness questionnaire / 风险承担意愿问卷
        6. Additional settings / 附加设置
        7. Generate & save profile / 生成并保存画像
    """
    # === Initialize session state values for form fields ===
    if "profile_name" not in st.session_state:
        st.session_state.profile_name = ""
    if "profile_age" not in st.session_state:
        st.session_state.profile_age = 30
    if "profile_marital_status" not in st.session_state:
        st.session_state.profile_marital_status = "single"
    if "profile_dependents" not in st.session_state:
        st.session_state.profile_dependents = 0
    if "profile_annual_income" not in st.session_state:
        st.session_state.profile_annual_income = 100_000
    if "profile_investable_assets" not in st.session_state:
        st.session_state.profile_investable_assets = 200_000
    if "profile_emergency_fund_months" not in st.session_state:
        st.session_state.profile_emergency_fund_months = 6.0
    if "profile_annual_expenses" not in st.session_state:
        st.session_state.profile_annual_expenses = 60_000
    if "profile_total_liabilities" not in st.session_state:
        st.session_state.profile_total_liabilities = 0
    if "profile_esg_preference" not in st.session_state:
        st.session_state.profile_esg_preference = False
    if "profile_tax_status" not in st.session_state:
        st.session_state.profile_tax_status = "taxable"
    if "profile_sector_restrictions" not in st.session_state:
        st.session_state.profile_sector_restrictions = ""
    if "profile_notes" not in st.session_state:
        st.session_state.profile_notes = ""

    # Initialize questionnaire keys in session state
    for q_key, q_data in RISK_ABILITY_QUESTIONS.items():
        key = f"ability_{q_key}"
        if key not in st.session_state:
            st.session_state[key] = list(q_data["options"].keys())[0]

    for q_key, q_data in RISK_WILLINGNESS_QUESTIONS.items():
        key = f"willingness_{q_key}"
        if key not in st.session_state:
            st.session_state[key] = list(q_data["options"].keys())[0]

    st.title("⌬ Client Profiling / 客户画像")
    st.markdown(
        "Complete the questionnaire below to generate your investment profile "
        "based on the CFA Investment Policy Statement (IPS) framework. / "
        "填写以下问卷，基于 CFA 投资政策声明（IPS）框架生成你的投资画像。"
    )

    # Check if in edit mode and show warning/cancel option
    is_editing = "editing_profile_path" in st.session_state and st.session_state.editing_profile_path is not None
    if is_editing:
        st.warning(f"📝 **Currently Editing Profile / 正在编辑画像:** `{Path(st.session_state.editing_profile_path).name}`")
        if st.button("❌ Cancel Edit / 取消编辑", key="cancel_edit_top"):
            # Reset values
            st.session_state.editing_profile_path = None
            st.session_state.profile_name = ""
            st.session_state.profile_age = 30
            st.session_state.profile_marital_status = "single"
            st.session_state.profile_dependents = 0
            st.session_state.profile_annual_income = 100_000
            st.session_state.profile_investable_assets = 200_000
            st.session_state.profile_emergency_fund_months = 6.0
            st.session_state.profile_annual_expenses = 60_000
            st.session_state.profile_total_liabilities = 0
            st.session_state.profile_esg_preference = False
            st.session_state.profile_tax_status = "taxable"
            st.session_state.profile_sector_restrictions = ""
            st.session_state.profile_notes = ""
            st.session_state.goals = [
                {"name": "Retirement / 退休", "target_amount": 2_000_000, "years": 30, "priority": "high"},
            ]
            # Clear dynamic goal keys
            keys_to_delete = [k for k in st.session_state.keys() if k.startswith(("goal_name_", "goal_amount_", "goal_years_", "goal_priority_"))]
            for k in keys_to_delete:
                del st.session_state[k]
            st.rerun()

    st.divider()

    # ====================================
    # Step 1: Basic Info / 基本信息
    # ====================================
    basic = _render_basic_info()
    st.divider()

    # ====================================
    # Step 2: Financial Situation / 财务状况
    # ====================================
    financial = _render_financial_situation()
    st.divider()

    # ====================================
    # Step 3: Investment Goals / 投资目标
    # ====================================
    goals = _render_investment_goals()

    # 投资期限 = 最远目标的年数
    # Time horizon = years of the farthest goal
    time_horizon = max((g["years"] for g in goals), default=10)

    st.divider()

    # ====================================
    # Step 4: Risk Ability Questions / 承受能力问卷
    # ====================================
    ability_answers = _render_risk_ability_questions()
    st.divider()

    # ====================================
    # Step 5: Risk Willingness Questions / 承担意愿问卷
    # ====================================
    willingness_answers = _render_risk_willingness_questions()
    st.divider()

    # ====================================
    # Step 6: Additional Settings / 附加设置
    # ====================================
    st.markdown("#### ⌬ Additional Settings / 附加设置")

    col1, col2 = st.columns(2)
    with col1:
        esg_preference = st.checkbox(
            "ESG investing preference / 偏好 ESG 投资",
            key="profile_esg_preference",
        )
        tax_status = st.selectbox(
            "Tax status / 税务状况",
            options=["taxable", "tax-exempt", "tax-deferred"],
            format_func=lambda x: {
                "taxable": "Taxable / 应税",
                "tax-exempt": "Tax-exempt / 免税",
                "tax-deferred": "Tax-deferred / 延税",
            }[x],
            key="profile_tax_status",
        )
    with col2:
        sector_restrictions = st.text_input(
            "Sector restrictions (comma-separated) / 行业限制（逗号分隔）",
            placeholder="e.g., Tobacco, Gambling",
            key="profile_sector_restrictions",
        )
        notes = st.text_area(
            "Additional notes / 其他备注",
            placeholder="Any other information relevant to your investment plan...",
            key="profile_notes",
        )

    st.divider()

    # ====================================
    # Step 7: Generate Profile / 生成画像
    # ====================================
    st.markdown("#### ✦ Generate Profile / 生成画像")

    button_label = "💾 Update Profile / 更新我的画像" if is_editing else "🧮 Generate My Profile / 生成我的画像"
    
    if st.button(button_label, type="primary"):
        # 基本校验 / Basic validation
        if not basic["name"].strip():
            st.error("❌ Please enter your name. / 请输入你的姓名。")
            return

        # 计算风险评估 / Compute risk assessment
        risk_profile = assess_risk(ability_answers, willingness_answers)

        # 构建完整画像 / Build complete profile
        profile = ClientProfile(
            name=basic["name"],
            age=basic["age"],
            marital_status=basic["marital_status"],
            dependents=basic["dependents"],
            financial=FinancialSituation(**financial),
            goals=[InvestmentGoal(**g) for g in goals],
            time_horizon_years=time_horizon,
            tax_status=tax_status,
            esg_preference=esg_preference,
            sector_restrictions=[
                s.strip() for s in sector_restrictions.split(",") if s.strip()
            ],
            notes=notes,
            risk_profile=risk_profile,
            ability_answers=ability_answers,
            willingness_answers=willingness_answers,
        )

        if is_editing:
            # 更新已存在画像 / Update existing profile
            from src.agents.profiler import update_profile
            filepath = update_profile(Path(st.session_state.editing_profile_path), profile)
            st.success(f"✅ Profile updated in `{filepath.name}` / 画像已更新")
            # Clear edit state
            st.session_state.editing_profile_path = None
        else:
            # 保存全新画像 / Save new profile
            filepath = save_profile(profile)
            st.success(f"✅ Profile saved to `{filepath.name}` / 画像已保存")

        # 展示画像摘要 / Display profile summary
        _render_profile_summary(profile)

    # ====================================
    # 已保存画像列表 / Saved Profiles List
    # ====================================
    st.divider()
    st.markdown("#### ⧉ Saved Profiles / 已保存的画像")

    profiles = list_profiles()
    if profiles:
        for p in profiles:
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1.5, 1.5, 1.2])
            with col1:
                st.write(f"**{p['name']}**")
            with col2:
                st.write(f"Age: {p['age']}")
            with col3:
                st.write(f"Risk: {p['risk_level'].split(' / ')[-1]}")
            with col4:
                st.caption(p["updated_at"][:19].replace("T", " "))
            with col5:
                c_edit, c_del = st.columns(2)
                with c_edit:
                    if st.button("✏️", key=f"edit_prof_{p['filepath']}", help="Edit profile"):
                        profile_to_edit = load_profile(Path(p['filepath']))
                        st.session_state.editing_profile_path = p['filepath']
                        st.session_state.profile_name = profile_to_edit.name
                        st.session_state.profile_age = profile_to_edit.age
                        st.session_state.profile_marital_status = profile_to_edit.marital_status
                        st.session_state.profile_dependents = profile_to_edit.dependents
                        st.session_state.profile_annual_income = profile_to_edit.financial.annual_income
                        st.session_state.profile_investable_assets = profile_to_edit.financial.investable_assets
                        st.session_state.profile_emergency_fund_months = profile_to_edit.financial.emergency_fund_months
                        st.session_state.profile_annual_expenses = profile_to_edit.financial.annual_expenses
                        st.session_state.profile_total_liabilities = profile_to_edit.financial.total_liabilities
                        st.session_state.goals = [
                            {
                                "name": g.name,
                                "target_amount": g.target_amount,
                                "years": g.years,
                                "priority": g.priority
                            }
                            for g in profile_to_edit.goals
                        ]
                        st.session_state.profile_esg_preference = profile_to_edit.esg_preference
                        st.session_state.profile_tax_status = profile_to_edit.tax_status
                        st.session_state.profile_sector_restrictions = ", ".join(profile_to_edit.sector_restrictions)
                        st.session_state.profile_notes = profile_to_edit.notes
                        
                        # Load questionnaire answers if they exist
                        for q_key in RISK_ABILITY_QUESTIONS.keys():
                            if hasattr(profile_to_edit, "ability_answers") and q_key in profile_to_edit.ability_answers:
                                st.session_state[f"ability_{q_key}"] = profile_to_edit.ability_answers[q_key]
                        for q_key in RISK_WILLINGNESS_QUESTIONS.keys():
                            if hasattr(profile_to_edit, "willingness_answers") and q_key in profile_to_edit.willingness_answers:
                                st.session_state[f"willingness_{q_key}"] = profile_to_edit.willingness_answers[q_key]
                        
                        # Delete any stale dynamic goal keys
                        keys_to_delete = [k for k in st.session_state.keys() if k.startswith(("goal_name_", "goal_amount_", "goal_years_", "goal_priority_"))]
                        for k in keys_to_delete:
                            del st.session_state[k]
                        st.rerun()
                with c_del:
                    if st.button("🗑️", key=f"del_prof_{p['filepath']}", help="Delete profile"):
                        from src.agents.profiler import delete_profile
                        if delete_profile(Path(p['filepath'])):
                            if st.session_state.get("editing_profile_path") == p['filepath']:
                                st.session_state.editing_profile_path = None
                            st.rerun()
    else:
        st.info("No profiles saved yet. / 尚无已保存的画像。")

    # ====================================
    # Profile Comparison / 画像对比
    # ====================================
    st.divider()
    st.markdown("#### ⧉ Profile Comparison / 画像对比")

    if len(profiles) >= 2:
        # Build name-to-filepath mapping for loading profiles
        profile_options = {
            p["name"]: p["filepath"] for p in profiles
        }
        selected_names = st.multiselect(
            "Select profiles to compare (2 or more) / 选择要对比的画像（2个或更多）",
            options=list(profile_options.keys()),
            default=list(profile_options.keys())[:min(2, len(profile_options))],
        )

        if len(selected_names) >= 2:
            if st.button("🔍 Compare Selected Profiles / 对比所选画像", type="primary"):
                # Load all selected profiles
                loaded_profiles = []
                for name in selected_names:
                    filepath = Path(profile_options[name])
                    try:
                        profile_data = load_profile(filepath)
                        loaded_profiles.append(profile_data)
                    except Exception as e:
                        st.error(f"Failed to load {name}: {e}")

                if len(loaded_profiles) >= 2:
                    # Run comparison / 执行对比分析
                    comparison = compare_profiles(loaded_profiles)

                    # Display comparison report / 展示对比报告
                    report = format_comparison_report(comparison)
                    st.code(report, language=None)

                    # Interactive comparison table / 交互式对比表
                    st.markdown("**Detailed Comparison / 详细对比**")

                    comparison_data = []
                    for name in comparison.client_names:
                        summary = comparison.financial_summary.get(name, {})
                        comparison_data.append({
                            "Client / 客户": name,
                            "Risk Score / 风险评分": summary.get("risk_score", 0),
                            "Risk Level / 风险等级": summary.get("risk_level", "N/A"),
                            "Net Worth / 净资产": f"${summary.get('net_worth', 0):,.0f}",
                            "Income / 收入": f"${summary.get('annual_income', 0):,.0f}",
                            "Savings Rate / 储蓄率": f"{summary.get('savings_rate', 0):.1%}",
                            "Emergency Fund / 应急基金": f"{summary.get('emergency_fund_months', 0):.0f} months",
                            "Biases / 偏差数": comparison.bias_count_comparison.get(name, 0),
                        })
                    st.dataframe(
                        pd.DataFrame(comparison_data),
                        use_container_width=True,
                        hide_index=True,
                    )

                    # Key insights / 关键洞察
                    st.markdown("**Key Insights / 关键洞察**")
                    for insight in comparison.insights:
                        st.markdown(f"- {insight}")

        else:
            st.info(
                "Please select at least 2 profiles to compare. / "
                "请至少选择 2 个画像进行对比。"
            )
    else:
        st.info(
            "Need at least 2 saved profiles to enable comparison. / "
            "至少需要 2 个已保存的画像才能进行对比。"
        )
