"""
AI advisory report generator using DeepSeek LLM.

Serializes ClientProfile into a structured prompt and calls
DeepSeek V4 Pro to produce a personalized advisory report.

References:
    - CFA L3 PWM: Investment Policy Statement framework
    - CFA L3: Asset Allocation & Behavioral Finance
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generator, Optional

from openai import OpenAI

from src.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_TEMPERATURE,
)
from src.agents.profiler import ClientProfile

logger = logging.getLogger(__name__)




@dataclass
class AdvisorReport:
    """Structured output of the AI Advisor Agent."""
    content: str = ""
    model: str = ""
    generated_at: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    client_name: str = ""
    success: bool = False
    error_message: str = ""



SYSTEM_PROMPT = """You are a Private Wealth Management advisor trained on the CFA® Level III curriculum, specializing in the Private Wealth Management (PWM) pathway. You operate within the CFA Institute's professional standards and ethical guidelines.

你是一位基于 CFA® 三级知识体系训练的私人财富管理顾问，专精于私人财富管理（PWM）方向。你遵循 CFA 协会的专业标准和道德准则。

## Your Core Competencies

1. **Investment Policy Statement (IPS) Framework / 投资政策声明框架**
   - Return objectives (收益目标)
   - Risk tolerance: Ability & Willingness assessment (风险承受能力：承受能力与承担意愿评估)
   - Time horizon analysis (投资期限分析)
   - Liquidity needs (流动性需求)
   - Tax considerations (税务考量)
   - Legal & regulatory constraints (法律与监管约束)
   - Unique circumstances (特殊情况)

2. **Asset Allocation / 资产配置**
   - Strategic Asset Allocation (SAA) (战略性资产配置)
   - Mean-Variance Optimization principles (均值-方差优化原理)
   - Risk budgeting and diversification (风险预算与分散化)
   - Human capital considerations (人力资本考量)

3. **Behavioral Finance / 行为金融学**
   - Identify common biases (loss aversion, overconfidence, anchoring)
   - 识别常见偏差（损失厌恶、过度自信、锚定效应）
   - Provide debiasing recommendations (提供纠偏建议)

## Output Requirements

Generate your advisory report in **bilingual format (English & Chinese / 中英双语)** with the following 6 sections. Use Markdown formatting:

1. **📋 Client Summary / 客户概况总结**
   - Summarize the client's profile, financial situation, and key characteristics
   - 总结客户画像、财务状况和关键特征

2. **🎯 Investment Objectives Analysis / 投资目标分析**
   - Analyze each goal's feasibility, required return, and priority
   - 分析每个目标的可行性、所需收益率和优先级

3. **⚖️ Risk Tolerance Interpretation / 风险承受能力解读**
   - Interpret the ability vs willingness scores
   - If they conflict, explain the CFA "use the lower" principle
   - 解读承受能力与承担意愿评分
   - 如果两者冲突，解释 CFA "就低不就高"原则

4. **📊 Recommended Asset Allocation / 建议资产配置方案**
   - Provide a specific allocation with percentages
   - Explain the rationale using MPT principles
   - Include asset classes: equities, bonds, alternatives, cash
   - 提供具体的配置百分比
   - 用 MPT 原理解释配置理由
   - 包含资产类别：股票、债券、另类投资、现金

5. **💡 Implementation Strategy / 实施策略与注意事项**
   - Specific ETF/fund suggestions aligned with allocation
   - Rebalancing frequency recommendation
   - Tax-efficient strategies if applicable
   - 与配置对应的具体 ETF/基金建议
   - 再平衡频率建议
   - 如适用，提供税务高效策略

6. **⚠️ Risk Disclosure / 风险披露与免责声明**
   - Past performance ≠ future results
   - Model limitations and assumptions
   - Recommendation to consult a licensed advisor
   - 历史表现不代表未来收益
   - 模型局限性和假设
   - 建议咨询持牌顾问

## Constraints

- Be professional, thorough, and data-driven
- Always cite CFA principles when making recommendations
- Never guarantee specific returns or outcomes
- Consider the client's complete financial picture holistically
- Adapt tone to the client's investment knowledge level
- 专业、全面、以数据为驱动
- 提出建议时始终引用 CFA 原则
- 绝不保证具体收益或结果
- 全面考虑客户的整体财务状况
- 根据客户的投资知识水平调整措辞"""




def _build_user_prompt(profile: ClientProfile) -> str:
    """Serialize a ClientProfile into a structured LLM prompt."""
    goals_text = ""
    if profile.goals:
        for i, goal in enumerate(profile.goals, 1):
            goals_text += (
                f"  {i}. {goal.name}\n"
                f"     - Target Amount / 目标金额: ${goal.target_amount:,.0f}\n"
                f"     - Time Horizon / 时间范围: {goal.years} years / 年\n"
                f"     - Priority / 优先级: {goal.priority}\n"
            )
    else:
        goals_text = "  No specific goals defined / 未定义具体目标\n"

    unique_text_parts = []
    if profile.esg_preference:
        unique_text_parts.append("- ESG investing preference / 偏好 ESG 投资")
    if profile.sector_restrictions:
        restrictions = ", ".join(profile.sector_restrictions)
        unique_text_parts.append(
            f"- Sector restrictions / 行业限制: {restrictions}"
        )
    if profile.notes:
        unique_text_parts.append(f"- Additional notes / 备注: {profile.notes}")
    unique_text = "\n".join(unique_text_parts) if unique_text_parts else "  None / 无"

    rp = profile.risk_profile
    conflict_note = ""
    if rp.ability_score > 0 and rp.willingness_score > 0:
        if abs(rp.ability_score - rp.willingness_score) >= 1.0:
            conflict_note = (
                f"\n  ⚠️ CONFLICT DETECTED / 冲突检测: "
                f"Ability ({rp.ability_score:.1f}) vs "
                f"Willingness ({rp.willingness_score:.1f}) differ by "
                f"{abs(rp.ability_score - rp.willingness_score):.1f} points. "
                f"CFA principle: use the LOWER score."
            )


    prompt = f"""Please generate a comprehensive investment advisory report for the following client:
请为以下客户生成全面的投资咨询建议书：

═══════════════════════════════════════════
CLIENT PROFILE / 客户画像
═══════════════════════════════════════════

【Basic Information / 基本信息】
  Name / 姓名: {profile.name}
  Age / 年龄: {profile.age}
  Marital Status / 婚姻状况: {profile.marital_status}
  Dependents / 受抚养人数: {profile.dependents}

【Financial Situation / 财务状况】
  Annual Income / 年收入: ${profile.financial.annual_income:,.0f}
  Annual Expenses / 年支出: ${profile.financial.annual_expenses:,.0f}
  Investable Assets / 可投资资产: ${profile.financial.investable_assets:,.0f}
  Total Liabilities / 负债总额: ${profile.financial.total_liabilities:,.0f}
  Net Worth / 净资产: ${profile.financial.net_worth:,.0f}
  Savings Rate / 储蓄率: {profile.financial.savings_rate:.1%}
  Debt-to-Asset Ratio / 资产负债率: {profile.financial.debt_to_asset_ratio:.1%}
  Emergency Fund / 应急基金: {profile.financial.emergency_fund_months:.0f} months / 月

【Investment Goals / 投资目标】
{goals_text}
【Time Horizon / 投资期限】
  Primary Horizon / 主要期限: {profile.time_horizon_years} years / 年
  Multi-stage / 多阶段: {"Yes / 是" if profile.is_multi_stage else "No / 否"}

【Risk Tolerance Assessment / 风险承受能力评估】
  Ability Score / 承受能力评分: {rp.ability_score:.1f} / 5.0
  Willingness Score / 承担意愿评分: {rp.willingness_score:.1f} / 5.0
  Final Score / 最终评分: {rp.final_score:.1f} / 5.0 (= min(Ability, Willingness))
  Risk Level / 风险等级: {rp.tolerance_level}{conflict_note}

【Tax Status / 税务状况】
  {profile.tax_status}

【Liquidity Needs / 流动性需求】
  ${profile.liquidity_needs:,.0f}

【Unique Circumstances / 特殊情况】
{unique_text}

═══════════════════════════════════════════

Please generate the advisory report following the 6-section format specified in your instructions.
请按照你指令中规定的 6 个章节格式生成建议书。"""

    return prompt




def validate_report_content(content: str) -> tuple[bool, str]:
    """Validate that the generated report meets minimal length and structure requirements.

    Args:
        content: The generated report text.

    Returns:
        tuple[bool, str]: (is_valid, error_message).
    """
    if not content or len(content.strip()) < 100:
        return False, f"Report content is too short ({len(content.strip()) if content else 0} chars, minimum is 100)."

    # Check for presence of keywords corresponding to the 6 required sections
    required_sections = [
        ("Client Summary", "客户概况"),
        ("Investment Objectives", "投资目标"),
        ("Risk Tolerance", "风险承受能力"),
        ("Asset Allocation", "资产配置"),
        ("Implementation Strategy", "实施策略"),
        ("Risk Disclosure", "风险披露")
    ]

    missing_sections = []
    content_lower = content.lower()
    for english_kw, chinese_kw in required_sections:
        if english_kw.lower() not in content_lower and chinese_kw not in content:
            missing_sections.append(f"{english_kw} / {chinese_kw}")

    if missing_sections:
        return False, f"Missing required sections in report: {', '.join(missing_sections)}."

    return True, ""


def _get_client() -> OpenAI:
    """Initialize an OpenAI-compatible client for DeepSeek."""
    if not DEEPSEEK_API_KEY:
        raise ValueError(
            "DEEPSEEK_API_KEY is not configured. "
            "Please set it in your .env file."
        )
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def is_api_configured() -> bool:
    """Check if the DeepSeek API key is configured."""
    return bool(DEEPSEEK_API_KEY)




def _create_initial_report(profile: ClientProfile) -> AdvisorReport:
    """Create an initial AdvisorReport with metadata pre-filled."""
    return AdvisorReport(
        client_name=profile.name,
        model=DEEPSEEK_MODEL,
        generated_at=datetime.now().isoformat(),
    )


def _build_messages(profile: ClientProfile) -> list[dict]:
    """Build the message list for the DeepSeek API call."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(profile)},
    ]



def generate_advice(profile: ClientProfile) -> AdvisorReport:
    """Generate a complete advisory report (non-streaming)."""
    report = _create_initial_report(profile)

    try:
        client = _get_client()

        messages = _build_messages(profile)

        logger.info(
            f"Generating advisory report for client: {profile.name} "
            f"using model: {DEEPSEEK_MODEL}"
        )


        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            max_tokens=DEEPSEEK_MAX_TOKENS,
            temperature=DEEPSEEK_TEMPERATURE,
            stream=False,
        )

        report.content = response.choices[0].message.content or ""
        is_valid, err_msg = validate_report_content(report.content)
        if is_valid:
            report.success = True
        else:
            report.success = False
            report.error_message = err_msg
            logger.error(f"Report validation failed: {err_msg}")


        if response.usage:
            report.prompt_tokens = response.usage.prompt_tokens
            report.completion_tokens = response.usage.completion_tokens
            report.total_tokens = response.usage.total_tokens

        logger.info(
            f"Report generated successfully. "
            f"Tokens: {report.total_tokens} "
            f"(prompt: {report.prompt_tokens}, "
            f"completion: {report.completion_tokens})"
        )

    except ValueError as e:
        report.error_message = str(e)
        logger.error(f"Configuration error: {e}")

    except Exception as e:
        report.error_message = f"Failed to generate report: {str(e)}"
        logger.error(f"API call failed: {e}", exc_info=True)

    return report


def generate_advice_stream(
    profile: ClientProfile,
) -> Generator[str, None, AdvisorReport]:
    """Generate an advisory report with streaming output."""
    report = _create_initial_report(profile)

    try:
        client = _get_client()

        messages = _build_messages(profile)

        logger.info(
            f"Starting streaming advisory report for: {profile.name}"
        )


        stream = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            max_tokens=DEEPSEEK_MAX_TOKENS,
            temperature=DEEPSEEK_TEMPERATURE,
            stream=True,
        )

        full_content = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                full_content.append(text)
                yield text

        report.content = "".join(full_content)
        is_valid, err_msg = validate_report_content(report.content)
        if is_valid:
            report.success = True
        else:
            report.success = False
            report.error_message = err_msg
            logger.error(f"Streaming report validation failed: {err_msg}")

        logger.info(
            f"Streaming report completed for: {profile.name}"
        )

    except ValueError as e:
        report.error_message = str(e)
        logger.error(f"Configuration error: {e}")

    except Exception as e:
        report.error_message = f"Failed to generate report: {str(e)}"
        logger.error(f"Streaming API call failed: {e}", exc_info=True)

    return report


def stream_advice(profile: ClientProfile) -> tuple[Generator[str, None, None], list]:
    """Streamlit streaming wrapper returning (generator, report_container)."""
    report_container = []

    def _stream():
        report = yield from generate_advice_stream(profile)
        report_container.append(report)

    return _stream(), report_container
