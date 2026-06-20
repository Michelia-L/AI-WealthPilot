"""
AI WealthPilot - IPS PydanticAI Agent Definitions

Defines the PydanticAI agents used in the IPS generation workflow.
Each agent is configured with a specific system prompt, output schema,
and is responsible for one step in the Generate-Review-Revise pipeline.

Architecture:
    ips_generator_agent   → IPSDocument     (generate initial IPS draft)
    suitability_reviewer  → ReviewResult    (check client-IPS fit)
    compliance_reviewer   → ReviewResult    (check regulatory compliance)
    consistency_reviewer  → ReviewResult    (check internal consistency)
    ips_reviser_agent     → IPSDocument     (revise IPS based on review)

CFA Reference:
    - CFA L3 PWM: IPS framework and compliance standards
    - CFA L3: Behavioral Finance — bias identification
    - CFA L3: Risk Tolerance = min(Ability, Willingness)

Model:
    DeepSeek V4 Pro via OpenAI-compatible API (PydanticAI)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from src.agents.ips_models import IPSDocument, ReviewResult, ReviewDimension

logger = logging.getLogger(__name__)


# Model Configuration

def _get_model() -> OpenAIModel:
    """
    Create PydanticAI model pointing to DeepSeek V4 Pro.

    Uses OpenAIProvider with the OpenAI-compatible interface
    since DeepSeek's API follows the OpenAI chat completions protocol.

    Returns:
        Configured OpenAIModel instance.

    Raises:
        ValueError: If DEEPSEEK_API_KEY is not set.
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError(
            "DEEPSEEK_API_KEY is not configured. "
            "Please set it in your .env file."
        )
    provider = OpenAIProvider(
        base_url=DEEPSEEK_BASE_URL,
        api_key=DEEPSEEK_API_KEY,
    )
    # DeepSeek V4 Pro thinking mode is incompatible with
    # PydanticAI's tool_choice="required" for structured output.
    # Must be disabled via extra_body.
    return OpenAIModel(
        DEEPSEEK_MODEL,
        provider=provider,
    )


# Reference Document Loading

_IPS_REFERENCE_DIR = Path(__file__).parent.parent.parent / "docs" / "ips_reference"


def load_ips_template() -> str:
    """
    Load the IPS structural template for context injection.

    Returns:
        Full text of the IPS template document.
    """
    template_path = _IPS_REFERENCE_DIR / "ips_template_structure.md"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    logger.warning("IPS template not found at %s", template_path)
    return ""


def load_compliance_checklist() -> dict:
    """
    Load the machine-readable compliance checklist.

    Returns:
        Parsed checklist dictionary.
    """
    checklist_path = _IPS_REFERENCE_DIR / "compliance_checklist.json"
    if checklist_path.exists():
        with open(checklist_path, "r", encoding="utf-8") as f:
            return json.load(f)
    logger.warning("Compliance checklist not found at %s", checklist_path)
    return {}


# System Prompts

_GENERATOR_SYSTEM_PROMPT = """你是一名持有 CFA® 三级证书的资深私人财富管理顾问，专精于为高净值个人客户编写投资政策声明书（IPS）。

## 你的任务
根据提供的客户画像数据和 IPS 结构模板，生成一份完整的、专业级的投资政策声明书。

## 核心原则
1. **严格遵循 CFA IPS 框架**：必须包含所有标准章节（收益目标、风险承受能力、投资期限、流动性、税务、法律、特殊情况、投资指引、监控评估）
2. **数据驱动**：所有分析和建议必须基于客户的实际数据，不得臆造数据
3. **风险承受能力双轨制**：严格执行"取较低值"原则
   - 必须填写 `risk_tolerance` 中的量化风险锚点字段：
     - `max_acceptable_annual_loss`: 基于风险等级的最大可接受年度亏损（保守:-5%, 稳健:-10%, 平衡:-15%, 成长:-20%, 进取:-30%）
     - `target_volatility_min` / `target_volatility_max`: 目标波动率区间（保守:4-8%, 稳健:8-12%, 平衡:10-15%, 成长:13-18%, 进取:16-25%）
     - `var_tolerance_95`: 95% 置信水平下的年化 VaR 容忍度
     - `max_drawdown_tolerance`: 最大回撤容忍度
4. **量化精确**：收益目标必须有明确的数学推导过程
5. **资产配置合理性**：战略性资产配置必须与客户的风险等级、投资期限、流动性需求一致
6. **合规意识**：必须包含充分的风险披露和合规声明
7. **资本市场预期（CME）驱动的资产配置**：
   - 如果提供了 CME 数据，战略性资产配置（SAA）必须参考 CME 中的预期收益率和波动率
   - 无风险利率和通胀率必须使用 CME 中提供的数值，不得自行假设
   - 组合预期收益率必须基于 CME 各资产预期收益率加权计算，并与 IPS 所需收益率对比
   - 风险披露中必须说明 CME 基于历史数据，不代表未来表现
   - 各资产类别的配置理由应引用 CME 数据支撑（如夏普比率、波动率、相关性）
8. **多目标收益分解**（当客户有多个投资目标时）：
   - 必须在 `goal_level_requirements` 中为每个投资目标单独计算所需收益率
   - 每个目标使用 TVM 公式推导：r = (FV/PV)^(1/n) - 1，其中 FV=目标金额，PV=分配资本，n=年限
   - `required_nominal_return` 应为各目标按分配资本加权的综合所需收益率
   - 高优先级目标应优先分配资本
   - `return_methodology` 字段必须明确标注使用的计算方法（TVM / Annuity PMT / Gordon Growth Model 等）
   - 如果某个目标的所需收益率超出 SAA 预期收益率范围，必须在 return_objective_narrative 中标注不可行风险
9. **多币种与汇率管理**（当存在跨境资产或外币敞口时）：
   - 必须在 `currency_policy` 字段中定义货币政策
   - 基准计价货币（`base_currency`）默认统一为 "CNY"（以匹配人民币计价客户的需求）
   - 必须评估外币资产的敞口比例 `foreign_exposure_pct`（例如战略配置中 S&P 500、NASDAQ、BTC、黄金期货等外币资产的加权比例之和）
   - 必须在 `hedging_strategy` 中指定对冲策略（例如 "Unhedged" 或 "Partial hedge via forward contracts"）并明确对冲比例 `hedging_ratio`
   - 在 `currency_narrative` 中详细说明汇率波动风险及其管理策略
10. **费用与成本披露**（CFA L3 PWM 必须项）：
   - 必须在 `fee_schedule` 字段中填写完整的费用披露信息
   - `management_fee_rate`: 年化投资管理费率（通常 0.005-0.02，即 0.5%-2%）
   - `custody_fee_rate`: 年化托管费率（通常 0.001-0.003，即 0.1%-0.3%）
   - `transaction_cost_estimate`: 预估年化交易成本占 AUM 比例（通常 0.001-0.005）
   - `total_expense_ratio`: TER = 管理费 + 托管费 + 交易成本，必须精确计算
   - `net_return_impact`: 明确说明费用对净收益率的影响，格式为"总收益率 X% - TER Y% = 净收益率 Z%"
   - `fee_narrative`: 完整的费用披露叙述，必须覆盖所有费用组成部分及其合理性说明

## 输出要求
- 使用中文撰写所有叙述性内容
- 所有数字必须精确，不使用模糊表述
- 资产配置以百分比表示，权重之和必须等于 100%
- 收益率使用小数表示（如 0.08 表示 8%）

## 约束
- 绝不保证具体收益或结果
- 如果所需收益率超出客户风险承受范围，必须明确指出
- 必须考虑客户的完整财务状况
- `compliance_statement` 中必须包含以下合规要素：
  - 24 小时投资冷静期提示（依据《证券期货投资者适当性管理办法》，适用于私募基金等产品）
  - KYC（了解你的客户）完成确认声明，确认已完成客户身份验证和投资适当性评估"""


_SUITABILITY_REVIEW_PROMPT = """你是一名专业的 IPS 适配性审查员，负责验证投资政策声明书（IPS）是否准确反映了客户的实际情况。

## 审查维度：适配性 (Suitability)

你需要逐项检查以下内容：

1. **风险等级匹配**：IPS 中的风险等级是否与客户风险评估结果一致
2. **能力-意愿冲突处理**：如存在冲突，是否正确采用了较低值
3. **收益目标可实现性**：所需收益率是否在客户风险等级可承受的合理范围内
4. **投资期限匹配**：资产配置的风险水平是否与投资期限匹配
5. **流动性需求充足性**：流动性安排是否满足客户需求
6. **应急基金覆盖**：是否建议了足够的应急储备
7. **投资目标优先级反映**：高优先级目标是否在配置中得到充分反映

## 输出要求
- 对每个发现的问题，必须说明所在章节、严重程度、具体描述和修改建议
- 如果引用了 CFA 原则或法规，必须在 regulation_reference 中注明
- 只有在所有检查项均通过时，才将 passed 设为 true
- 使用中文描述所有问题"""


_COMPLIANCE_REVIEW_PROMPT = """你是一名专业的 IPS 合规性审查员，负责验证投资政策声明书（IPS）是否符合监管要求和行业规范。

## 审查维度：合规性 (Compliance)

你需要逐项检查以下内容：

1. **风险披露完整性**：是否包含完整的风险披露声明（市场风险、模型局限性、历史业绩不代表未来）
2. **合规声明存在性**：是否包含合规声明
3. **权重约束合法性**：所有资产类别权重之和是否为 100%
4. **禁止投资工具声明**：客户的行业限制或 ESG 偏好是否在禁投清单中反映
5. **适当性原则**：推荐的投资工具是否符合客户的风险等级
6. **法律约束完整性**：是否识别了适用的法律法规
7. **费用披露完整性**：IPS 是否包含 fee_schedule 字段，且完整披露了管理费率、托管费率、交易成本预估和 TER（总费用率），并说明了费用对净收益率的影响
8. **投资者冷静期提示**：compliance_statement 中是否包含关于签署后 24 小时冷静期的提示（适用于私募基金等产品，依据《证券期货投资者适当性管理办法》）
9. **KYC 完整性确认**：compliance_statement 是否包含已完成客户身份验证和投资适当性评估的 KYC 确认声明

## 输出要求
- 合规问题默认为 critical 严重程度
- 必须引用具体的法规或行业规范
- 使用中文描述所有问题"""


_CONSISTENCY_REVIEW_PROMPT = """你是一名专业的 IPS 一致性审查员，负责验证投资政策声明书（IPS）各章节之间的内部逻辑一致性。

## 审查维度：一致性 (Consistency)

你需要逐项检查以下内容：

1. **风险等级与配置一致性**：声明的风险等级是否与实际资产配置的风险水平一致
   - 保守型：权益类 ≤ 30%
   - 稳健型：权益类 ≤ 45%
   - 平衡型：权益类 ≤ 60%
   - 成长型：权益类 ≤ 75%
   - 进取型：权益类 ≤ 90%
2. **收益目标与配置一致性**：配置方案的预期收益率能否覆盖所需收益率
3. **期限与配置一致性**：投资期限分析是否与配置逻辑一致
4. **执行摘要一致性**：摘要内容是否与各章节一致
5. **特殊情况与投资指引一致性**：特殊情况中的限制是否在投资指引中反映
6. **再平衡策略一致性**：投资指引和监控章节的再平衡政策是否一致

## 输出要求
- 逻辑矛盾为 critical，表述不一致为 warning，措辞优化为 info
- 使用中文描述所有问题"""


_REVISER_SYSTEM_PROMPT = """你是一名持有 CFA® 三级证书的资深 IPS 修订专家。

## 你的任务
根据审查团队提出的问题和修改建议，对投资政策声明书（IPS）进行精准修订。

## 修订原则
1. **精准修订**：只修改审查中指出的问题，不改动没有问题的部分
2. **保持一致性**：修改某个章节时，确保与其他章节的逻辑保持一致
3. **数据准确**：修改后的数字必须重新验算，确保数学正确
4. **留痕意识**：所有修改都应该是可追溯的，修改后的内容应更加准确和专业

## 数值变更传播规则（Critical）
5. **数值一致性**：当修改任何收益率、波动率或权重数值时，必须全文检查并更新所有引用该数值的位置：
   - 修改 SAA 权重 → 更新 guideline_narrative、executive_summary 中的权重描述
   - 修改预期收益率 → 更新 return_objective、executive_summary、risk_disclosure 中的收益率引用
   - 修改风险等级 → 更新 risk_tolerance、executive_summary、investment_guidelines 中的风险描述
   - executive_summary 中的所有数字必须与各章节的最新数值一致
6. **交叉验证**：修订完成后，自行验证 executive_summary 中的关键数字（收益率、权重、风险等级）是否与对应章节完全一致

## 输出要求
- 输出修订后的完整 IPS（不是只输出修改的部分）
- 确保所有权重之和仍为 100%
- 确保收益率等数值的一致性
- 使用中文撰写"""


# Shared Model Settings

# DeepSeek V4 Pro defaults to "thinking mode" which rejects
# tool_choice="required" (used by PydanticAI for structured output).
# We explicitly disable thinking mode so function calling works.
# max_tokens set to 32768 to accommodate full IPS with CME references.
_MODEL_SETTINGS: ModelSettings = {
    "temperature": 0.3,
    "max_tokens": 32768,
    "extra_body": {"thinking": {"type": "disabled"}},
}


# Agent Factory Functions

def create_ips_generator_agent() -> Agent[None, IPSDocument]:
    """
    Create the IPS generation agent.

    This agent takes a ClientProfile (serialized as context in the
    user prompt) and the IPS template reference, then generates
    a complete, structured IPSDocument.

    Returns:
        PydanticAI Agent configured for IPS generation.
    """
    return Agent(
        model=_get_model(),
        output_type=IPSDocument,
        system_prompt=_GENERATOR_SYSTEM_PROMPT,
        model_settings=_MODEL_SETTINGS,
        retries=3,
    )


def create_suitability_reviewer() -> Agent[None, ReviewResult]:
    """
    Create the suitability review agent.

    Checks whether the IPS properly reflects the client's risk
    profile, return requirements, time horizon, and liquidity needs.

    Returns:
        PydanticAI Agent configured for suitability review.
    """
    return Agent(
        model=_get_model(),
        output_type=ReviewResult,
        system_prompt=_SUITABILITY_REVIEW_PROMPT,
        model_settings=_MODEL_SETTINGS,
        retries=3,
    )


def create_compliance_reviewer() -> Agent[None, ReviewResult]:
    """
    Create the compliance review agent.

    Checks whether the IPS meets regulatory requirements including
    risk disclosure, compliance statements, and weight constraints.

    Returns:
        PydanticAI Agent configured for compliance review.
    """
    return Agent(
        model=_get_model(),
        output_type=ReviewResult,
        system_prompt=_COMPLIANCE_REVIEW_PROMPT,
        model_settings=_MODEL_SETTINGS,
        retries=3,
    )


def create_consistency_reviewer() -> Agent[None, ReviewResult]:
    """
    Create the consistency review agent.

    Checks whether all IPS sections are internally consistent
    (e.g., risk level matches allocation, return matches allocation).

    Returns:
        PydanticAI Agent configured for consistency review.
    """
    return Agent(
        model=_get_model(),
        output_type=ReviewResult,
        system_prompt=_CONSISTENCY_REVIEW_PROMPT,
        model_settings=_MODEL_SETTINGS,
        retries=3,
    )


def create_ips_reviser_agent() -> Agent[None, IPSDocument]:
    """
    Create the IPS revision agent.

    Takes the current IPS draft and review issues as context,
    then produces a revised IPSDocument addressing all issues.

    Returns:
        PydanticAI Agent configured for IPS revision.
    """
    return Agent(
        model=_get_model(),
        output_type=IPSDocument,
        system_prompt=_REVISER_SYSTEM_PROMPT,
        model_settings=_MODEL_SETTINGS,
        retries=3,
    )


# Prompt Construction Helpers

def build_generation_prompt(
    client_profile_json: str,
    ips_template: str,
    cme_text: str = "",
) -> str:
    """
    Build the user prompt for IPS generation.

    Combines the client profile data, IPS template reference,
    and Capital Market Expectations (CME) data into a single
    prompt for the generation agent.

    Args:
        client_profile_json: Serialized ClientProfile as JSON string.
        ips_template: Full text of the IPS structural template.
        cme_text: CME data formatted as LLM-readable text.

    Returns:
        Formatted user prompt string.
    """
    cme_section = ""
    if cme_text:
        cme_section = f"""

═══════════════════════════════════════════
资本市场预期 (CME) — 量化引擎数据
═══════════════════════════════════════════

{cme_text}

"""

    return f"""请根据以下客户画像数据，参照 IPS 结构模板和资本市场预期（CME）数据，生成一份完整的投资政策声明书。

═══════════════════════════════════════════
客户画像数据
═══════════════════════════════════════════

{client_profile_json}

═══════════════════════════════════════════
IPS 结构参考模板
═══════════════════════════════════════════

{ips_template}
{cme_section}
═══════════════════════════════════════════

请严格按照模板结构生成完整的 IPS，确保每个章节都有实质性内容。
所有叙述性内容使用中文。收益率使用小数表示（如 0.08 表示 8%）。
资产配置权重之和必须等于 1.0（即 100%）。
如果提供了 CME 数据，SAA 的预期收益率和波动率必须与 CME 一致。"""


def build_review_prompt(
    ips_json: str,
    client_profile_json: str,
    dimension: ReviewDimension,
    checklist_items: Optional[list[dict]] = None,
) -> str:
    """
    Build the user prompt for IPS review.

    Args:
        ips_json: Serialized IPSDocument as JSON string.
        client_profile_json: Serialized ClientProfile as JSON string.
        dimension: Which review dimension to focus on.
        checklist_items: Optional checklist items for this dimension.

    Returns:
        Formatted review prompt string.
    """
    checklist_text = ""
    if checklist_items:
        checklist_text = "\n\n═══════════════════════════════════════════\n"
        checklist_text += "合规检查清单\n"
        checklist_text += "═══════════════════════════════════════════\n\n"
        for item in checklist_items:
            checklist_text += (
                f"- [{item['id']}] {item['name']}（{item['severity']}）\n"
                f"  规则：{item['rule']}\n\n"
            )

    return f"""请对以下投资政策声明书（IPS）进行{dimension.value}维度的审查。

═══════════════════════════════════════════
待审查的 IPS 文档
═══════════════════════════════════════════

{ips_json}

═══════════════════════════════════════════
客户原始画像数据（用于对照验证）
═══════════════════════════════════════════

{client_profile_json}
{checklist_text}
请逐项检查并输出结构化的审查结果。dimension 字段必须设为 "{dimension.value}"。"""


def build_revision_prompt(
    ips_json: str,
    review_issues_json: str,
) -> str:
    """
    Build the user prompt for IPS revision.

    Args:
        ips_json: Serialized current IPSDocument as JSON string.
        review_issues_json: Serialized list of ReviewIssue as JSON string.

    Returns:
        Formatted revision prompt string.
    """
    return f"""请根据以下审查意见修订投资政策声明书（IPS）。

═══════════════════════════════════════════
当前 IPS 文档
═══════════════════════════════════════════

{ips_json}

═══════════════════════════════════════════
审查发现的问题
═══════════════════════════════════════════

{review_issues_json}

═══════════════════════════════════════════

请针对每个问题进行精准修订，输出修订后的完整 IPS。
不要遗漏任何问题，不要改动没有问题的部分。
确保修订后各章节之间的逻辑一致性。"""
