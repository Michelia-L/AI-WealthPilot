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



Model:
    DeepSeek V4 Pro via OpenAI-compatible API (PydanticAI)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from src import config
from src.agents.ips_models import IPSDocument, ReviewDimension, ReviewResult
from src.agents.llm_config import get_llm_config
from src.portfolio.risk_constraints import RISK_LEVEL_CAPS

logger = logging.getLogger(__name__)


# Model Configuration


def _get_model() -> OpenAIChatModel:
    """
    Create PydanticAI model from the resolved LLM config (FR-002).

    Uses OpenAIProvider with the OpenAI-compatible interface
    since DeepSeek's API follows the OpenAI chat completions protocol.
    User-saved endpoint settings (app_settings table) override the
    DeepSeek env defaults.

    Returns:
        Configured OpenAIChatModel instance.

    Raises:
        ValueError: If no API key is configured (DB or env).
    """
    cfg = get_llm_config()
    if not cfg.configured:
        raise ValueError(
            "DEEPSEEK_API_KEY is not configured. Please set it in your .env file."
        )
    provider = OpenAIProvider(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
    )
    return OpenAIChatModel(
        cfg.model,
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

_GENERATOR_SYSTEM_PROMPT = """你是一名资深私人财富管理顾问，专精于为高净值个人客户编写投资政策声明书（IPS）。

## 你的任务
根据提供的客户画像数据和 IPS 结构模板，生成一份完整的、专业级的投资政策声明书。

## 核心原则
1. **严格遵循标准 IPS 框架**：必须包含所有标准章节（收益目标、风险承受能力、投资期限、流动性、税务、法律、特殊情况、投资指引、监控评估）
2. **数据驱动**：所有分析和建议必须基于客户的实际数据，不得臆造数据
3. **风险承受能力双轨制**：严格执行"取较低值"原则
   - 必须填写 `risk_tolerance` 中的量化风险锚点字段：
     - `max_acceptable_annual_loss`: 基于风险等级的最大可接受年度亏损（保守:-5%, 稳健:-10%, 平衡:-15%, 成长:-20%, 进取:-30%）
     - `target_volatility_min` / `target_volatility_max`: 目标波动率区间（__VOL_BANDS__）
     - `var_tolerance_95`: 95% 置信水平下的年化 VaR 容忍度
     - `max_drawdown_tolerance`: 最大回撤容忍度
4. **量化精确**：收益目标必须有明确的数学推导过程
5. **资产配置合理性**：战略性资产配置必须与客户的风险等级、投资期限、流动性需求一致
6. **合规意识**：必须包含充分的风险披露和合规声明
7. **资本市场预期（CME）驱动的资产配置**：
   - 如果提供了 CME 数据，战略性资产配置（SAA）必须参考 CME 中的预期收益率和波动率
   - 无风险利率和通胀率必须使用 CME 中提供的数值，不得自行假设
   - `required_real_return` 必须等于 `required_nominal_return` 减去 CME 中的通胀率假设；若该通胀率已按客户所在人群调整（如老年客户采用 CPI-E 风格的更高通胀假设），必须在 `return_calculation_basis` 中说明所采用的人群专属通胀假设
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
10. **费用与成本披露**（行业合规必须项）：
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


# English-only counterpart of _GENERATOR_SYSTEM_PROMPT (Phase 22): identical
# analytical and structural requirements, but the IPS is written entirely in
# English.
_GENERATOR_SYSTEM_PROMPT_EN = """You are a senior private wealth management advisor specializing in writing Investment Policy Statements (IPS) for high-net-worth individual clients.

## Your Task
Based on the provided client profile data and the IPS structural template, generate a complete, professional-grade Investment Policy Statement, written entirely in English.

## Core Principles
1. **Strictly follow the standard IPS framework**: every standard section must be present (return objectives, risk tolerance, time horizon, liquidity, taxes, legal, unique circumstances, investment guidelines, monitoring & review)
2. **Data-driven**: all analysis and recommendations must be grounded in the client's actual data — never fabricate figures
3. **Dual-track risk tolerance**: strictly apply the "use the lower score" principle
   - You MUST fill in the quantitative risk-anchor fields of `risk_tolerance`:
     - `max_acceptable_annual_loss`: maximum acceptable annual loss by risk level (conservative: -5%, moderately_conservative: -10%, moderate: -15%, moderately_aggressive: -20%, aggressive: -30%)
     - `target_volatility_min` / `target_volatility_max`: target volatility band (__VOL_BANDS__)
     - `var_tolerance_95`: annualized VaR tolerance at the 95% confidence level
     - `max_drawdown_tolerance`: maximum drawdown tolerance
4. **Quantitative precision**: return objectives must show an explicit mathematical derivation
5. **Sound asset allocation**: the strategic asset allocation must be consistent with the client's risk level, time horizon, and liquidity needs
6. **Compliance awareness**: include adequate risk disclosure and compliance statements
7. **CME-driven asset allocation**:
   - If CME data is provided, the strategic asset allocation (SAA) MUST reference the expected returns and volatilities from the CME
   - The risk-free rate and inflation rate MUST use the values provided in the CME — do not assume your own
   - `required_real_return` MUST equal `required_nominal_return` minus the CME inflation assumption; if that assumption has been adjusted for the client's demographic segment (e.g. a CPI-E-style higher rate for elderly clients), the segment-specific inflation basis MUST be stated in `return_calculation_basis`
   - The portfolio's expected return MUST be computed as the CME-weighted average of the asset-class expected returns, and compared against the IPS required return
   - The risk disclosure MUST state that the CME is based on historical data and does not represent future performance
   - The rationale for each asset-class allocation should cite CME data (e.g. Sharpe ratio, volatility, correlations)
8. **Multi-goal return decomposition** (when the client has multiple investment goals):
   - You MUST compute a separate required return for each goal in `goal_level_requirements`
   - Derive each goal's required return with the TVM formula: r = (FV/PV)^(1/n) - 1, where FV = target amount, PV = allocated capital, n = years
   - `required_nominal_return` should be the capital-weighted composite required return across all goals
   - Higher-priority goals should receive capital first
   - The `return_methodology` field MUST state the calculation method used (TVM / Annuity PMT / Gordon Growth Model, etc.)
   - If any goal's required return exceeds the SAA's expected return range, the infeasibility risk MUST be flagged in return_objective_narrative
9. **Multi-currency and FX management** (when cross-border assets or foreign-currency exposure exist):
   - You MUST define the currency policy in the `currency_policy` field
   - The base currency (`base_currency`) defaults to "CNY" (to match clients whose needs are CNY-denominated)
   - You MUST assess the foreign-currency exposure ratio `foreign_exposure_pct` (e.g. the weighted sum of foreign-currency assets such as S&P 500, NASDAQ, BTC, and gold futures in the strategic allocation)
   - You MUST specify a hedging strategy in `hedging_strategy` (e.g. "Unhedged" or "Partial hedge via forward contracts") with an explicit `hedging_ratio`
   - Explain the FX fluctuation risk and its management strategy in detail in `currency_narrative`
10. **Fee and cost disclosure** (an industry compliance must):
   - You MUST complete the full fee disclosure in the `fee_schedule` field
   - `management_fee_rate`: annualized investment management fee (typically 0.005-0.02, i.e. 0.5%-2%)
   - `custody_fee_rate`: annualized custody fee (typically 0.001-0.003, i.e. 0.1%-0.3%)
   - `transaction_cost_estimate`: estimated annualized transaction costs as a share of AUM (typically 0.001-0.005)
   - `total_expense_ratio`: TER = management fee + custody fee + transaction costs; must be computed precisely
   - `net_return_impact`: state the fee impact on net returns explicitly, in the form "gross return X% - TER Y% = net return Z%"
   - `fee_narrative`: a complete fee disclosure narrative covering every fee component and its justification

## Output Requirements
- Write ALL narrative content in English
- All figures must be precise; avoid vague wording
- Asset allocations are expressed as percentages and the weights must sum to exactly 100%
- Returns are expressed as decimals (e.g. 0.08 means 8%)

## Constraints
- Never guarantee specific returns or outcomes
- If the required return exceeds what the client's risk tolerance can bear, state so explicitly
- Consider the client's complete financial picture holistically
- `compliance_statement` MUST contain the following compliance elements:
  - A 24-hour cooling-off period notice (per the Measures for the Suitability Management of Securities and Futures Investors, applicable to products such as private funds)
  - A KYC (Know Your Customer) completion confirmation, stating that client identity verification and investment suitability assessment have been completed"""


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
- 如果引用了行业准则或法规，必须在 regulation_reference 中注明
- 只有在所有检查项均通过时，才将 passed 设为 true
- 使用中文描述所有问题"""


# English-only counterpart of _SUITABILITY_REVIEW_PROMPT (Phase 22).
_SUITABILITY_REVIEW_PROMPT_EN = """You are a professional IPS suitability reviewer, responsible for verifying that an Investment Policy Statement (IPS) accurately reflects the client's actual situation.

## Review Dimension: Suitability

Check each of the following items:

1. **Risk level match**: whether the risk level in the IPS matches the client's risk assessment results
2. **Ability-willingness conflict handling**: if a conflict exists, whether the lower score was correctly used
3. **Return objective feasibility**: whether the required return is within a reasonable range bearable by the client's risk level
4. **Time horizon match**: whether the risk level of the asset allocation matches the time horizon
5. **Liquidity adequacy**: whether the liquidity arrangements meet the client's needs
6. **Emergency fund coverage**: whether sufficient emergency reserves are recommended
7. **Goal priority reflection**: whether high-priority goals are adequately reflected in the allocation

## Output Requirements
- For every issue found, state the section it is in, the severity, a specific description, and a suggested fix
- If you cite industry guidelines or regulations, note them in regulation_reference
- Set passed to true only when every check item passes
- Describe all issues in English"""


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


# English-only counterpart of _COMPLIANCE_REVIEW_PROMPT (Phase 22).
_COMPLIANCE_REVIEW_PROMPT_EN = """You are a professional IPS compliance reviewer, responsible for verifying that an Investment Policy Statement (IPS) meets regulatory requirements and industry standards.

## Review Dimension: Compliance

Check each of the following items:

1. **Risk disclosure completeness**: whether a complete risk disclosure statement is included (market risk, model limitations, past performance does not represent future results)
2. **Compliance statement presence**: whether a compliance statement is included
3. **Weight constraint legality**: whether all asset-class weights sum to 100%
4. **Prohibited instruments declaration**: whether the client's sector restrictions or ESG preferences are reflected in the prohibited-instruments list
5. **Suitability principle**: whether the recommended investment instruments match the client's risk level
6. **Legal constraint completeness**: whether the applicable laws and regulations are identified
7. **Fee disclosure completeness**: whether the IPS contains a fee_schedule field that fully discloses the management fee rate, custody fee rate, estimated transaction costs, and TER (total expense ratio), and explains the fee impact on net returns
8. **Cooling-off period notice**: whether compliance_statement includes a notice about the 24-hour cooling-off period after signing (applicable to products such as private funds, per the Measures for the Suitability Management of Securities and Futures Investors)
9. **KYC completion confirmation**: whether compliance_statement includes a KYC confirmation that client identity verification and investment suitability assessment have been completed

## Output Requirements
- Compliance issues default to critical severity
- You must cite the specific regulation or industry standard
- Describe all issues in English"""


_CONSISTENCY_REVIEW_PROMPT = """你是一名专业的 IPS 一致性审查员，负责验证投资政策声明书（IPS）各章节之间的内部逻辑一致性。

## 审查维度：一致性 (Consistency)

你需要逐项检查以下内容：

1. **风险等级与配置一致性**：声明的风险等级是否与实际资产配置的风险水平一致
__EQUITY_CAPS__
2. **收益目标与配置一致性**：配置方案的预期收益率能否覆盖所需收益率
3. **期限与配置一致性**：投资期限分析是否与配置逻辑一致
4. **执行摘要一致性**：摘要内容是否与各章节一致
5. **特殊情况与投资指引一致性**：特殊情况中的限制是否在投资指引中反映
6. **再平衡策略一致性**：投资指引和监控章节的再平衡政策是否一致

## 输出要求
- 逻辑矛盾为 critical，表述不一致为 warning，措辞优化为 info
- 使用中文描述所有问题"""


# English-only counterpart of _CONSISTENCY_REVIEW_PROMPT (Phase 22).
_CONSISTENCY_REVIEW_PROMPT_EN = """You are a professional IPS consistency reviewer, responsible for verifying the internal logical consistency across the sections of an Investment Policy Statement (IPS).

## Review Dimension: Consistency

Check each of the following items:

1. **Risk level vs allocation consistency**: whether the stated risk level matches the actual risk level of the asset allocation
__EQUITY_CAPS__
2. **Return objective vs allocation consistency**: whether the allocation's expected return can cover the required return
3. **Horizon vs allocation consistency**: whether the time horizon analysis is consistent with the allocation logic
4. **Executive summary consistency**: whether the summary content matches each section
5. **Unique circumstances vs guidelines consistency**: whether restrictions in the unique circumstances are reflected in the investment guidelines
6. **Rebalancing strategy consistency**: whether the rebalancing policies in the investment guidelines and the monitoring section agree

## Output Requirements
- Logical contradictions are critical, inconsistent statements are warning, wording improvements are info
- Describe all issues in English"""


_REVISER_SYSTEM_PROMPT = """你是一名资深 IPS 修订专家。

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


# English-only counterpart of _REVISER_SYSTEM_PROMPT (Phase 22).
_REVISER_SYSTEM_PROMPT_EN = """You are a senior IPS revision specialist.

## Your Task
Precisely revise an Investment Policy Statement (IPS) based on the issues and suggestions raised by the review team. Write all content in English.

## Revision Principles
1. **Precise revision**: only fix the issues identified in the review; do not alter parts that have no issues
2. **Maintain consistency**: when revising one section, keep its logic consistent with the other sections
3. **Data accuracy**: recompute every revised figure to ensure mathematical correctness
4. **Traceability**: every change should be traceable, and the revised content should be more accurate and professional

## Numeric Change Propagation Rules (Critical)
5. **Numeric consistency**: whenever you change any return, volatility, or weight figure, you MUST scan the whole document and update every place that references it:
   - Changed SAA weights → update the weight descriptions in guideline_narrative and executive_summary
   - Changed expected returns → update the return references in return_objective, executive_summary, and risk_disclosure
   - Changed risk level → update the risk descriptions in risk_tolerance, executive_summary, and investment_guidelines
   - Every figure in executive_summary must match the latest values in the corresponding sections
6. **Cross-validation**: after revising, verify yourself that the key figures in executive_summary (returns, weights, risk level) exactly match the corresponding sections

## Output Requirements
- Output the complete revised IPS (not only the changed parts)
- Ensure all weights still sum to 100%
- Ensure consistency of figures such as returns
- Write all content in English"""


# Locale resolution for the five workflow system prompts (Phase 22). zh keeps
# the pre-i18n prompts verbatim; en switches to the English-only variants.
_SYSTEM_PROMPTS_ZH = {
    "generator": _GENERATOR_SYSTEM_PROMPT,
    "suitability": _SUITABILITY_REVIEW_PROMPT,
    "compliance": _COMPLIANCE_REVIEW_PROMPT,
    "consistency": _CONSISTENCY_REVIEW_PROMPT,
    "reviser": _REVISER_SYSTEM_PROMPT,
}

_SYSTEM_PROMPTS_EN = {
    "generator": _GENERATOR_SYSTEM_PROMPT_EN,
    "suitability": _SUITABILITY_REVIEW_PROMPT_EN,
    "compliance": _COMPLIANCE_REVIEW_PROMPT_EN,
    "consistency": _CONSISTENCY_REVIEW_PROMPT_EN,
    "reviser": _REVISER_SYSTEM_PROMPT_EN,
}


# Prompt numeric-guidance composition (P25). The generator and
# consistency prompt constants carry __VOL_BANDS__ / __EQUITY_CAPS__
# placeholders (plain-text markers, so the constants stay free of
# f-string escaping); get_system_prompt — the single access point —
# fills them from the canonical config tables, keeping the LLM-facing
# numbers in lockstep with the enforced ones. Level display names below
# are pure presentation text; every number comes from config.

# zh display names keyed by RISK_VOLATILITY_BANDS key (the en generator
# prompt historically displays the snake_case keys themselves).
_VOL_LEVEL_LABELS_ZH = {
    "conservative": "保守",
    "moderately_conservative": "稳健",
    "moderate": "平衡",
    "moderately_aggressive": "成长",
    "aggressive": "进取",
}

# en display names keyed by RISK_LEVEL_CAPS key (Chinese level names).
_EQUITY_LEVEL_LABELS_EN = {
    "保守型": "Conservative",
    "稳健型": "Moderately conservative",
    "平衡型": "Moderate",
    "成长型": "Moderately aggressive",
    "进取型": "Aggressive",
}


def _vol_band_text(locale: str) -> str:
    """Render the per-level volatility-band listing for generator prompts.

    Keeps the pre-P25 formatting verbatim: zh labels take a bare colon
    (``保守:4-8%``), en labels a colon plus space (``moderate: 10-15%``).
    """
    parts = []
    for key, (lo, hi) in config.RISK_VOLATILITY_BANDS.items():
        if locale == "en":
            parts.append(f"{key}: {lo * 100:.0f}-{hi * 100:.0f}%")
        else:
            parts.append(f"{_VOL_LEVEL_LABELS_ZH[key]}:{lo * 100:.0f}-{hi * 100:.0f}%")
    return ", ".join(parts)


def _equity_caps_text(locale: str) -> str:
    """Render the per-level equity-cap bullet lines for consistency prompts."""
    lines = []
    for key, caps in RISK_LEVEL_CAPS.items():
        cap = f"{caps['equity']:.0%}"
        if locale == "en":
            lines.append(f"   - {_EQUITY_LEVEL_LABELS_EN[key]}: equities ≤ {cap}")
        else:
            lines.append(f"   - {key}：权益类 ≤ {cap}")
    return "\n".join(lines)


def get_system_prompt(role: str, locale: str = "zh") -> str:
    """System prompt for an IPS workflow role in the report language.

    Fills the __VOL_BANDS__ / __EQUITY_CAPS__ placeholders (P25) from the
    canonical config tables; roles without placeholders pass through
    unchanged.
    """
    table = _SYSTEM_PROMPTS_EN if locale == "en" else _SYSTEM_PROMPTS_ZH
    return (
        table[role]
        .replace("__VOL_BANDS__", _vol_band_text(locale))
        .replace("__EQUITY_CAPS__", _equity_caps_text(locale))
    )


# Shared Model Settings


def _get_model_settings() -> ModelSettings:
    """Build model settings for the resolved endpoint.

    DeepSeek V4 Pro defaults to "thinking mode" which rejects
    tool_choice="required" (used by PydanticAI for structured output),
    so thinking is explicitly disabled via extra_body — but ONLY for
    DeepSeek endpoints: custom OpenAI-compatible endpoints (FR-002) may
    reject the unknown field, so it is sent only when the effective
    base_url points at DeepSeek. max_tokens is 32768 to accommodate a
    full IPS with CME references.
    """
    settings: ModelSettings = {
        "temperature": 0.3,
        "max_tokens": 32768,
    }
    if "deepseek" in get_llm_config().base_url.lower():
        settings["extra_body"] = {"thinking": {"type": "disabled"}}
    return settings


# Agent Factory Functions


def create_ips_generator_agent(locale: str = "zh") -> Agent[None, IPSDocument]:
    """
    Create the IPS generation agent.

    This agent takes a ClientProfile (serialized as context in the
    user prompt) and the IPS template reference, then generates
    a complete, structured IPSDocument.

    Args:
        locale: Language of the generated IPS ("zh" or "en").

    Returns:
        PydanticAI Agent configured for IPS generation.
    """
    return Agent(
        model=_get_model(),
        output_type=IPSDocument,
        system_prompt=get_system_prompt("generator", locale),
        model_settings=_get_model_settings(),
        retries=3,
    )


def create_suitability_reviewer(locale: str = "zh") -> Agent[None, ReviewResult]:
    """
    Create the suitability review agent.

    Checks whether the IPS properly reflects the client's risk
    profile, return requirements, time horizon, and liquidity needs.

    Args:
        locale: Language the review findings are written in ("zh" or "en").

    Returns:
        PydanticAI Agent configured for suitability review.
    """
    return Agent(
        model=_get_model(),
        output_type=ReviewResult,
        system_prompt=get_system_prompt("suitability", locale),
        model_settings=_get_model_settings(),
        retries=3,
    )


def create_compliance_reviewer(locale: str = "zh") -> Agent[None, ReviewResult]:
    """
    Create the compliance review agent.

    Checks whether the IPS meets regulatory requirements including
    risk disclosure, compliance statements, and weight constraints.

    Args:
        locale: Language the review findings are written in ("zh" or "en").

    Returns:
        PydanticAI Agent configured for compliance review.
    """
    return Agent(
        model=_get_model(),
        output_type=ReviewResult,
        system_prompt=get_system_prompt("compliance", locale),
        model_settings=_get_model_settings(),
        retries=3,
    )


def create_consistency_reviewer(locale: str = "zh") -> Agent[None, ReviewResult]:
    """
    Create the consistency review agent.

    Checks whether all IPS sections are internally consistent
    (e.g., risk level matches allocation, return matches allocation).

    Args:
        locale: Language the review findings are written in ("zh" or "en").

    Returns:
        PydanticAI Agent configured for consistency review.
    """
    return Agent(
        model=_get_model(),
        output_type=ReviewResult,
        system_prompt=get_system_prompt("consistency", locale),
        model_settings=_get_model_settings(),
        retries=3,
    )


def create_ips_reviser_agent(locale: str = "zh") -> Agent[None, IPSDocument]:
    """
    Create the IPS revision agent.

    Takes the current IPS draft and review issues as context,
    then produces a revised IPSDocument addressing all issues.

    Args:
        locale: Language of the revised IPS ("zh" or "en").

    Returns:
        PydanticAI Agent configured for IPS revision.
    """
    return Agent(
        model=_get_model(),
        output_type=IPSDocument,
        system_prompt=get_system_prompt("reviser", locale),
        model_settings=_get_model_settings(),
        retries=3,
    )


# Prompt Construction Helpers


def build_generation_prompt(
    client_profile_json: str,
    ips_template: str,
    cme_text: str = "",
    locale: str = "zh",
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
        locale: Scaffolding language of the prompt ("zh" verbatim original,
            "en" English-only).

    Returns:
        Formatted user prompt string.
    """
    if locale == "en":
        cme_section = ""
        if cme_text:
            cme_section = f"""

═══════════════════════════════════════════
CAPITAL MARKET EXPECTATIONS (CME) — Quantitative Engine Data
═══════════════════════════════════════════

{cme_text}

"""

        return f"""Based on the client profile data below, and referring to the IPS structural template and the Capital Market Expectations (CME) data, generate a complete Investment Policy Statement.

═══════════════════════════════════════════
CLIENT PROFILE DATA
═══════════════════════════════════════════

{client_profile_json}

═══════════════════════════════════════════
IPS STRUCTURAL TEMPLATE (REFERENCE)
═══════════════════════════════════════════

{ips_template}
{cme_section}
═══════════════════════════════════════════

Generate the complete IPS strictly following the template structure, with substantive content in every section.
Write all narrative content in English. Express returns as decimals (e.g. 0.08 means 8%).
Asset allocation weights must sum to 1.0 (i.e. 100%).
If CME data is provided, the SAA's expected returns and volatilities must be consistent with the CME."""

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
    locale: str = "zh",
) -> str:
    """
    Build the user prompt for IPS review.

    Args:
        ips_json: Serialized IPSDocument as JSON string.
        client_profile_json: Serialized ClientProfile as JSON string.
        dimension: Which review dimension to focus on.
        checklist_items: Optional checklist items for this dimension.
        locale: Scaffolding language of the prompt ("zh" verbatim original,
            "en" English-only).

    Returns:
        Formatted review prompt string.
    """
    if locale == "en":
        checklist_text = ""
        if checklist_items:
            checklist_text = "\n\n═══════════════════════════════════════════\n"
            checklist_text += "COMPLIANCE CHECKLIST\n"
            checklist_text += "═══════════════════════════════════════════\n\n"
            for item in checklist_items:
                checklist_text += (
                    f"- [{item['id']}] {item['name']} ({item['severity']})\n"
                    f"  Rule: {item['rule']}\n\n"
                )

        return f"""Review the following Investment Policy Statement (IPS) on the {dimension.value} dimension.

═══════════════════════════════════════════
IPS DOCUMENT UNDER REVIEW
═══════════════════════════════════════════

{ips_json}

═══════════════════════════════════════════
ORIGINAL CLIENT PROFILE DATA (for cross-checking)
═══════════════════════════════════════════

{client_profile_json}
{checklist_text}
Check each item and output a structured review result. The dimension field must be set to "{dimension.value}"."""

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
    locale: str = "zh",
) -> str:
    """
    Build the user prompt for IPS revision.

    Args:
        ips_json: Serialized current IPSDocument as JSON string.
        review_issues_json: Serialized list of ReviewIssue as JSON string.
        locale: Scaffolding language of the prompt ("zh" verbatim original,
            "en" English-only).

    Returns:
        Formatted revision prompt string.
    """
    if locale == "en":
        return f"""Revise the following Investment Policy Statement (IPS) according to the review findings below.

═══════════════════════════════════════════
CURRENT IPS DOCUMENT
═══════════════════════════════════════════

{ips_json}

═══════════════════════════════════════════
ISSUES IDENTIFIED IN REVIEW
═══════════════════════════════════════════

{review_issues_json}

═══════════════════════════════════════════

Address every issue with precise revisions and output the complete revised IPS.
Do not skip any issue; do not alter parts that have no issues.
Ensure logical consistency across all sections after the revision."""

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
