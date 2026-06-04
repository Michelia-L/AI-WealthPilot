"""
AI WealthPilot - Client Profiling Agent
AI WealthPilot - 客户画像模块

Implements the CFA Investment Policy Statement (IPS) framework for
client profiling. Collects client information through structured
questionnaires and computes risk tolerance scores.

实现基于 CFA 投资政策声明（IPS）框架的客户画像。
通过结构化问卷收集客户信息，并计算风险承受能力评分。

CFA Reference / CFA 参考:
    - CFA L3 Private Wealth Management: Investment Policy Statement
      CFA 三级私人财富管理：投资政策声明
    - CFA L3: Risk Tolerance = f(Ability, Willingness)
      CFA 三级：风险承受能力 = f(承受能力, 承担意愿)
    - CFA L3: When ability and willingness conflict, use the LOWER score
      CFA 三级：当承受能力和承担意愿冲突时，取较低值

Key IPS Elements Covered / 涵盖的 IPS 关键要素:
    1. Client Identification (客户识别)
    2. Financial Situation (财务状况)
    3. Investment Objectives (投资目标)
    4. Risk Tolerance — Ability & Willingness (风险承受能力)
    5. Time Horizon (投资期限)
    6. Liquidity Needs (流动性需求)
    7. Tax Considerations (税务考量)
    8. Unique Circumstances (特殊情况)
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.utils import sanitize_filename


# ============================================================
# Data Model — Client Profile
# 数据模型 —— 客户画像
# ============================================================

@dataclass
class FinancialSituation:
    """
    Client's financial position.
    客户的财务状况。

    CFA IPS Element: Financial Situation
    CFA IPS 要素：财务状况
    """
    # 年收入 / Annual income
    annual_income: float = 0.0
    # 年支出 / Annual expenses
    annual_expenses: float = 0.0
    # 当前投资资产 / Current investment assets
    investable_assets: float = 0.0
    # 负债总额 / Total liabilities
    total_liabilities: float = 0.0
    # 应急基金（月数）/ Emergency fund (months of expenses)
    emergency_fund_months: float = 0.0

    @property
    def net_worth(self) -> float:
        """净资产 = 可投资资产 - 负债 / Net worth = investable assets - liabilities"""
        return self.investable_assets - self.total_liabilities

    @property
    def savings_rate(self) -> float:
        """储蓄率 = (收入 - 支出) / 收入 / Savings rate = (income - expenses) / income"""
        if self.annual_income <= 0:
            return 0.0
        return (self.annual_income - self.annual_expenses) / self.annual_income

    @property
    def debt_to_asset_ratio(self) -> float:
        """资产负债率 = 负债 / 可投资资产 / Debt-to-asset ratio"""
        if self.investable_assets <= 0:
            return 1.0
        return self.total_liabilities / self.investable_assets


@dataclass
class InvestmentGoal:
    """
    A single investment goal with target amount and time horizon.
    单个投资目标，包含目标金额和时间范围。

    CFA IPS Element: Return Objectives
    CFA IPS 要素：收益目标
    """
    # 目标名称（如"退休"、"子女教育"、"购房"）/ Goal name
    name: str = ""
    # 目标金额 / Target amount
    target_amount: float = 0.0
    # 距今年数 / Years from now
    years: int = 0
    # 优先级：high / medium / low / Priority level
    priority: str = "medium"


@dataclass
class RiskProfile:
    """
    Risk tolerance assessment results.
    风险承受能力评估结果。

    CFA Framework / CFA 框架:
        Risk Tolerance = min(Ability, Willingness)
        风险承受能力 = min(承受能力, 承担意愿)

        - Ability (承受能力): objective, based on financial situation
          客观指标，基于财务状况
        - Willingness (承担意愿): subjective, based on psychological comfort
          主观指标，基于心理承受能力

    When ability and willingness conflict, the advisor should use
    the LOWER score and counsel the client to align the two.
    当两者冲突时，顾问应采用较低评分，并引导客户统一两者。
    """
    # 承受能力评分 (1-5, 5=最高) / Ability score (1-5, 5=highest)
    ability_score: float = 0.0
    # 承担意愿评分 (1-5, 5=最高) / Willingness score (1-5, 5=highest)
    willingness_score: float = 0.0
    # 最终风险承受能力等级 / Final risk tolerance level
    tolerance_level: str = ""
    # 风险承受能力描述 / Risk tolerance description
    description: str = ""

    @property
    def final_score(self) -> float:
        """
        最终评分 = min(承受能力, 承担意愿)
        CFA 原则：取较低值，确保客户不会承担超出其能力或意愿的风险
        Final score = min(ability, willingness)
        CFA principle: use the lower score to ensure client doesn't
        take risk beyond their capacity or comfort level.
        """
        if self.ability_score == 0 or self.willingness_score == 0:
            return 0.0
        return min(self.ability_score, self.willingness_score)

    def classify(self) -> str:
        """
        根据最终评分分类风险承受能力等级。
        Classify risk tolerance level based on final score.

        Returns:
            Risk tolerance level string.
        """
        score = self.final_score
        if score <= 1.5:
            return "Conservative / 保守型"
        elif score <= 2.5:
            return "Moderately Conservative / 稳健型"
        elif score <= 3.5:
            return "Moderate / 平衡型"
        elif score <= 4.5:
            return "Moderately Aggressive / 成长型"
        else:
            return "Aggressive / 进取型"


@dataclass
class ClientProfile:
    """
    Complete client profile following the CFA IPS framework.
    遵循 CFA IPS 框架的完整客户画像。

    This is the central data structure for the AI Advisor system.
    All downstream modules (AI Advisor, IPS Generator, Portfolio Optimizer)
    consume this profile to generate personalized recommendations.

    这是 AI 顾问系统的核心数据结构。
    所有下游模块（AI 顾问、IPS 生成器、组合优化器）
    都消费此画像以生成个性化建议。
    """
    # === 客户识别 / Client Identification ===
    name: str = ""
    age: int = 30
    marital_status: str = "single"  # single / married / divorced / widowed
    dependents: int = 0

    # === 财务状况 / Financial Situation ===
    financial: FinancialSituation = field(default_factory=FinancialSituation)

    # === 投资目标 / Investment Goals ===
    goals: list = field(default_factory=list)

    # === 投资期限 / Time Horizon ===
    # 以年为单位 / In years
    time_horizon_years: int = 10
    # 是否多阶段 / Multi-stage (e.g., accumulation → distribution)
    is_multi_stage: bool = False

    # === 流动性需求 / Liquidity Needs ===
    # 近期需要的现金金额 / Near-term cash needed
    liquidity_needs: float = 0.0

    # === 税务状况 / Tax Considerations ===
    tax_status: str = "taxable"  # tax-exempt / taxable / tax-deferred

    # === 特殊情况 / Unique Circumstances ===
    esg_preference: bool = False
    sector_restrictions: list = field(default_factory=list)
    notes: str = ""

    # === 风险评估 / Risk Assessment ===
    risk_profile: RiskProfile = field(default_factory=RiskProfile)

    # === 元数据 / Metadata ===
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        """初始化时间戳 / Initialize timestamps."""
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def summary(self) -> str:
        """
        Generate a human-readable summary of the client profile.
        生成客户画像的可读摘要。
        """
        lines = [
            f"Client Profile: {self.name}",
            f"  Age: {self.age}, Marital Status: {self.marital_status}",
            f"  Dependents: {self.dependents}",
            f"  Net Worth: ${self.financial.net_worth:,.0f}",
            f"  Savings Rate: {self.financial.savings_rate:.1%}",
            f"  Time Horizon: {self.time_horizon_years} years",
            f"  Risk Tolerance: {self.risk_profile.tolerance_level} "
            f"(score: {self.risk_profile.final_score:.1f}/5)",
            f"  Goals: {', '.join(g.name for g in self.goals) if self.goals else 'None'}",
        ]
        return "\n".join(lines)


# ============================================================
# Risk Scoring Logic
# 风险评分逻辑
# ============================================================

# 问题选项及对应评分 / Question options with corresponding scores
RISK_ABILITY_QUESTIONS = {
    "income_stability": {
        "question": "How stable is your current income? / 你目前的收入有多稳定？",
        "question_en": "How stable is your current income?",
        "options": {
            "very_unstable": {"label": "Very unstable (freelance, variable) / 很不稳定", "score": 1},
            "somewhat_unstable": {"label": "Somewhat unstable / 不太稳定", "score": 2},
            "moderate": {"label": "Moderately stable / 一般稳定", "score": 3},
            "stable": {"label": "Stable (fixed salary) / 稳定", "score": 4},
            "very_stable": {"label": "Very stable (tenured, government) / 非常稳定", "score": 5},
        },
    },
    "investment_knowledge": {
        "question": "How would you rate your investment knowledge? / 你的投资知识水平如何？",
        "options": {
            "none": {"label": "No knowledge / 无知识", "score": 1},
            "limited": {"label": "Limited / 有限", "score": 2},
            "moderate": {"label": "Moderate / 中等", "score": 3},
            "good": {"label": "Good / 良好", "score": 4},
            "expert": {"label": "Expert / 专家", "score": 5},
        },
    },
    "investment_experience": {
        "question": "How many years of investment experience do you have? / 你有多少年投资经验？",
        "options": {
            "none": {"label": "None / 无", "score": 1},
            "1_3": {"label": "1-3 years / 1-3年", "score": 2},
            "3_5": {"label": "3-5 years / 3-5年", "score": 3},
            "5_10": {"label": "5-10 years / 5-10年", "score": 4},
            "10_plus": {"label": "10+ years / 10年以上", "score": 5},
        },
    },
    "emergency_fund": {
        "question": "How many months of expenses does your emergency fund cover? / 你的应急基金能覆盖几个月的支出？",
        "options": {
            "none": {"label": "None / 没有", "score": 1},
            "1_3": {"label": "1-3 months / 1-3个月", "score": 2},
            "3_6": {"label": "3-6 months / 3-6个月", "score": 3},
            "6_12": {"label": "6-12 months / 6-12个月", "score": 4},
            "12_plus": {"label": "12+ months / 12个月以上", "score": 5},
        },
    },
    "income_vs_expenses": {
        "question": "What is your income relative to expenses? / 你的收入相对于支出如何？",
        "options": {
            "deficit": {"label": "Expenses > Income / 支出大于收入", "score": 1},
            "breakeven": {"label": "About equal / 基本持平", "score": 2},
            "moderate_surplus": {"label": "20-50% surplus / 20-50%盈余", "score": 3},
            "good_surplus": {"label": "50-100% surplus / 50-100%盈余", "score": 4},
            "high_surplus": {"label": "100%+ surplus / 100%以上盈余", "score": 5},
        },
    },
}

RISK_WILLINGNESS_QUESTIONS = {
    "loss_reaction": {
        "question": "If your portfolio dropped 20% in a month, you would: / 如果你的组合一个月内下跌20%，你会：",
        "options": {
            "sell_all": {"label": "Sell everything / 全部卖出", "score": 1},
            "sell_some": {"label": "Sell some / 卖出一部分", "score": 2},
            "do_nothing": {"label": "Do nothing / 不动", "score": 3},
            "buy_more": {"label": "Buy more / 加仓", "score": 4},
            "aggressively_buy": {"label": "Aggressively buy more / 大幅加仓", "score": 5},
        },
    },
    "volatility_comfort": {
        "question": "Which investment outcome would you be most comfortable with? / 你最能接受哪种投资结果？",
        "options": {
            "low_low": {"label": "Low return (3%), low risk / 低收益(3%)低风险", "score": 1},
            "moderate_low": {"label": "Moderate return (6%), low risk / 中收益(6%)低风险", "score": 2},
            "moderate": {"label": "Moderate return (8%), moderate risk / 中收益(8%)中风险", "score": 3},
            "high_moderate": {"label": "High return (12%), moderate risk / 高收益(12%)中风险", "score": 4},
            "very_high": {"label": "Very high return (15%+), high risk / 很高收益(15%+)高风险", "score": 5},
        },
    },
    "gambling_scenario": {
        "question": "You are given $10,000. Would you take a coin flip: double or nothing? / 给你1万元，你愿意掷硬币：翻倍或全输？",
        "options": {
            "definitely_no": {"label": "Definitely not / 绝对不会", "score": 1},
            "probably_no": {"label": "Probably not / 可能不会", "score": 2},
            "maybe": {"label": "Maybe / 可能", "score": 3},
            "probably_yes": {"label": "Probably yes / 可能会", "score": 4},
            "definitely_yes": {"label": "Definitely yes / 一定会", "score": 5},
        },
    },
    "tracking_error_tolerance": {
        "question": "How much short-term underperformance vs benchmark can you tolerate? / 你能容忍多少短期跑输基准？",
        "options": {
            "minimal": {"label": "< 2% / 不超过2%", "score": 1},
            "low": {"label": "2-5%", "score": 2},
            "moderate": {"label": "5-10%", "score": 3},
            "high": {"label": "10-15%", "score": 4},
            "very_high": {"label": "15%+ / 超过15%", "score": 5},
        },
    },
}


def compute_ability_score(answers: dict) -> float:
    """
    Compute the client's ability-to-bear-risk score.
    计算客户的风险承受能力评分。

    Ability is OBJECTIVE — based on financial facts:
    承受能力是客观的 —— 基于财务事实：
    - Income stability (收入稳定性)
    - Investment knowledge (投资知识)
    - Investment experience (投资经验)
    - Emergency fund adequacy (应急基金充足性)
    - Income vs expenses ratio (收支比)

    Args:
        answers: Dict mapping question keys to selected option keys.
                 映射问题键到所选选项键的字典。

    Returns:
        Average ability score (1-5).
        平均承受能力评分 (1-5)。
    """
    scores = []
    for q_key, q_data in RISK_ABILITY_QUESTIONS.items():
        if q_key in answers:
            option_key = answers[q_key]
            if option_key in q_data["options"]:
                scores.append(q_data["options"][option_key]["score"])
    return sum(scores) / len(scores) if scores else 0.0


def compute_willingness_score(answers: dict) -> float:
    """
    Compute the client's willingness-to-take-risk score.
    计算客户的风险承担意愿评分。

    Willingness is SUBJECTIVE — based on psychological comfort:
    承担意愿是主观的 —— 基于心理承受能力：
    - Reaction to losses (对亏损的反应)
    - Volatility comfort (波动率承受度)
    - Gambling propensity (赌博倾向)
    - Tracking error tolerance (跟踪误差容忍度)

    Args:
        answers: Dict mapping question keys to selected option keys.

    Returns:
        Average willingness score (1-5).
    """
    scores = []
    for q_key, q_data in RISK_WILLINGNESS_QUESTIONS.items():
        if q_key in answers:
            option_key = answers[q_key]
            if option_key in q_data["options"]:
                scores.append(q_data["options"][option_key]["score"])
    return sum(scores) / len(scores) if scores else 0.0


def assess_risk(ability_answers: dict, willingness_answers: dict) -> RiskProfile:
    """
    Compute full risk profile from questionnaire answers.
    从问卷答案计算完整的风险画像。

    CFA Principle / CFA 原则:
        Risk Tolerance = min(Ability, Willingness)
        When the two conflict, the LOWER score prevails.
        The advisor should counsel the client to align the two.

    Args:
        ability_answers: Answers to ability questions.
        willingness_answers: Answers to willingness questions.

    Returns:
        RiskProfile with scores and classification.
    """
    profile = RiskProfile(
        ability_score=compute_ability_score(ability_answers),
        willingness_score=compute_willingness_score(willingness_answers),
    )
    profile.tolerance_level = profile.classify()
    return profile


# ============================================================
# Profile Persistence — JSON Storage
# 画像持久化 —— JSON 存储
# ============================================================

PROFILES_DIR = DATA_DIR / "profiles"


def save_profile(profile: ClientProfile) -> Path:
    """
    Save a client profile to a JSON file.
    将客户画像保存为 JSON 文件。

    Args:
        profile: ClientProfile instance to save.

    Returns:
        Path to the saved file.
    """
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    # 使用客户名和时间戳作为文件名
    # Use client name and timestamp as filename
    safe_name = sanitize_filename(profile.name)
    filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = PROFILES_DIR / filename

    # 更新时间戳 / Update timestamp
    profile.updated_at = datetime.now().isoformat()

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(profile), f, indent=2, ensure_ascii=False)

    return filepath


def load_profile(filepath: Path) -> ClientProfile:
    """
    Load a client profile from a JSON file.
    从 JSON 文件加载客户画像。

    Args:
        filepath: Path to the JSON file.

    Returns:
        ClientProfile instance.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 重建嵌套数据对象 / Rebuild nested data objects
    financial = FinancialSituation(**data.pop("financial", {}))
    risk = RiskProfile(**data.pop("risk_profile", {}))
    goals = [InvestmentGoal(**g) for g in data.pop("goals", [])]

    return ClientProfile(
        financial=financial,
        risk_profile=risk,
        goals=goals,
        **data,
    )


def list_profiles() -> list[dict]:
    """
    List all saved client profiles with summary info.
    列出所有已保存的客户画像及摘要信息。

    Returns:
        List of dicts with filepath, name, age, risk level.
    """
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profiles = []
    for filepath in sorted(PROFILES_DIR.glob("*.json"), reverse=True):
        try:
            profile = load_profile(filepath)
            profiles.append({
                "filepath": str(filepath),
                "name": profile.name,
                "age": profile.age,
                "risk_level": profile.risk_profile.tolerance_level,
                "updated_at": profile.updated_at,
            })
        except Exception:
            continue
    return profiles


def update_profile(filepath: Path, profile: ClientProfile) -> Path:
    """
    Update an existing client profile file.
    更新已存在的客户画像文件。

    This function overwrites the existing file with updated profile data.
    It preserves the original filepath and updates the 'updated_at' timestamp.

    该函数用更新后的画像数据覆盖现有文件。
    保留原始文件路径并更新 'updated_at' 时间戳。

    Args:
        filepath: Path to the existing profile JSON file.
                  现有画像 JSON 文件的路径。
        profile: Updated ClientProfile instance.
                 更新后的 ClientProfile 实例。

    Returns:
        Path to the updated file (same as input filepath).
        更新后的文件路径（与输入的 filepath 相同）。

    Raises:
        FileNotFoundError: If the specified file does not exist.
                           如果指定的文件不存在。
    """
    if not filepath.exists():
        raise FileNotFoundError(
            f"Profile file not found: {filepath} / 画像文件未找到: {filepath}"
        )

    # 更新时间戳 / Update timestamp
    profile.updated_at = datetime.now().isoformat()

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(profile), f, indent=2, ensure_ascii=False)

    return filepath


def delete_profile(filepath: Path) -> bool:
    """
    Delete a client profile file.
    删除客户画像文件。

    Args:
        filepath: Path to the profile JSON file to delete.
                  要删除的画像 JSON 文件路径。

    Returns:
        True if deletion was successful, False otherwise.
        删除成功返回 True，否则返回 False。

    CFA Reference / CFA 参考:
        Data retention policies may require keeping client records
        for a certain period. In production systems, consider
        soft-delete (archiving) instead of hard-delete.
        数据保留政策可能要求保留客户记录一定期限。
        在生产系统中，考虑使用软删除（归档）而非硬删除。
    """
    try:
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    except Exception:
        return False


# ============================================================
# Behavioral Finance — Bias Identification
# 行为金融学 —— 偏差识别
# ============================================================

@dataclass
class BehavioralBias:
    """
    Represents a detected behavioral finance bias.
    表示检测到的行为金融偏差。

    CFA Reference / CFA 参考:
        CFA L3 Behavioral Finance: Common investor biases include
        loss aversion, overconfidence, anchoring, recency bias,
        mental accounting, and herding behavior.
        CFA 三级行为金融学：常见的投资者偏差包括损失厌恶、
        过度自信、锚定效应、近因偏差、心理账户和羊群效应。
    """
    # 偏差类型 / Bias type
    bias_type: str
    # 偏差名称（中英文）/ Bias name (bilingual)
    name: str
    # 偏差描述 / Bias description
    description: str
    # 严重程度：high / medium / low / Severity level
    severity: str
    # 纠偏建议 / Debiasing recommendation
    recommendation: str


def identify_behavioral_biases(profile: ClientProfile) -> list[BehavioralBias]:
    """
    Identify potential behavioral finance biases based on client profile.
    基于客户画像识别潜在的行为金融偏差。

    This function analyzes the client's risk questionnaire answers,
    financial situation, and investment behavior patterns to detect
    common behavioral biases documented in CFA curriculum.

    该函数分析客户的风险问卷答案、财务状况和投资行为模式，
    以检测 CFA 课程中记录的常见行为偏差。

    CFA Reference / CFA 参考:
        CFA L3 Behavioral Finance:
        - Loss Aversion: Tendency to feel losses more intensely than gains
          损失厌恶：对损失的感受比收益更强烈
        - Overconfidence: Overestimating one's investment ability
          过度自信：高估自己的投资能力
        - Risk Perception Mismatch: Willingness vs ability conflict
          风险感知错配：意愿与能力的冲突

    Args:
        profile: Complete ClientProfile with risk assessment.
                 包含风险评估的完整 ClientProfile。

    Returns:
        List of detected BehavioralBias instances.
        检测到的 BehavioralBias 实例列表。
    """
    biases: list[BehavioralBias] = []
    rp = profile.risk_profile

    # ============================================================
    # 1. Loss Aversion Detection / 损失厌恶检测
    # ============================================================
    # 如果客户对损失反应过于强烈（willingness 低但 ability 高），
    # 可能存在损失厌恶偏差
    # If client overreacts to losses (low willingness but high ability),
    # may indicate loss aversion bias
    if rp.ability_score > 0 and rp.willingness_score > 0:
        if rp.willingness_score <= 2.0 and rp.ability_score >= 3.5:
            biases.append(BehavioralBias(
                bias_type="loss_aversion",
                name="Loss Aversion / 损失厌恶",
                description=(
                    "Your willingness to take risk is significantly lower than "
                    "your financial ability. This suggests you may be overly "
                    "focused on potential losses rather than long-term gains. / "
                    "您的风险承担意愿明显低于您的财务能力。这表明您可能过度关注"
                    "潜在损失而非长期收益。"
                ),
                severity="high",
                recommendation=(
                    "Consider that short-term volatility is the 'price of admission' "
                    "for long-term equity returns. Focus on your long-term goals "
                    "rather than daily fluctuations. / "
                    "请考虑短期波动是获得长期股票收益的'入场费'。"
                    "请关注您的长期目标而非每日波动。"
                ),
            ))

    # ============================================================
    # 2. Overconfidence Detection / 过度自信检测
    # ============================================================
    # 如果客户声称高投资知识但经验有限，可能存在过度自信
    # If client claims high knowledge but has limited experience,
    # may indicate overconfidence
    if rp.ability_score >= 4.0 and rp.willingness_score >= 4.5:
        biases.append(BehavioralBias(
            bias_type="overconfidence",
            name="Overconfidence / 过度自信",
            description=(
                "Your extremely high risk tolerance may indicate overconfidence "
                "in your ability to predict market movements. Research shows "
                "most active traders underperform passive strategies. / "
                "您极高的风险承受能力可能表明您对预测市场走势过度自信。"
                "研究表明大多数主动交易者的表现不如被动策略。"
            ),
            severity="medium",
            recommendation=(
                "Remember that markets are largely efficient. Consider a "
                "core-satellite approach: passive index funds for core holdings, "
                "with limited active bets. / "
                "请记住市场在很大程度上是有效的。考虑核心-卫星策略："
                "核心持仓使用被动指数基金，有限的主动投资。"
            ),
        ))

    # ============================================================
    # 3. Ability-Willingness Conflict / 能力-意愿冲突检测
    # ============================================================
    # CFA 原则：当能力和意愿冲突时，取较低值并进行投资者教育
    # CFA principle: when ability and willingness conflict, use lower
    # score and provide investor education
    if rp.ability_score > 0 and rp.willingness_score > 0:
        score_diff = abs(rp.ability_score - rp.willingness_score)
        if score_diff >= 1.5:
            higher = "ability" if rp.ability_score > rp.willingness_score else "willingness"
            biases.append(BehavioralBias(
                bias_type="risk_mismatch",
                name="Risk Tolerance Mismatch / 风险承受能力错配",
                description=(
                    f"There is a significant gap ({score_diff:.1f} points) between "
                    f"your objective risk ability and subjective willingness. "
                    f"Your {higher} score is notably higher. / "
                    f"您的客观风险能力与主观意愿之间存在显著差距（{score_diff:.1f}分）。"
                    f"您的{higher}评分明显更高。"
                ),
                severity="high",
                recommendation=(
                    "Per CFA guidelines, we use the lower score to protect you. "
                    "Consider discussing with an advisor to align your comfort "
                    "level with your financial capacity. / "
                    "根据 CFA 指引，我们采用较低评分以保护您。"
                    "建议与顾问讨论，使您的心理舒适度与财务能力相匹配。"
                ),
            ))

    # ============================================================
    # 4. Financial Behavior Risk / 财务行为风险检测
    # ============================================================
    # 如果负债率高但风险偏好也高，存在行为风险
    # If high debt ratio but also high risk appetite, behavioral risk exists
    if profile.financial.debt_to_asset_ratio > 0.5 and rp.willingness_score >= 4.0:
        biases.append(BehavioralBias(
            bias_type="leverage_risk",
            name="Leverage Risk Behavior / 杠杆风险行为",
            description=(
                f"Your debt-to-asset ratio is "
                f"{profile.financial.debt_to_asset_ratio:.1%}, "
                f"yet you show high risk tolerance. This combination "
                f"increases financial vulnerability. / "
                f"您的资产负债率为 {profile.financial.debt_to_asset_ratio:.1%}，"
                f"但您显示出高风险容忍度。这种组合增加了财务脆弱性。"
            ),
            severity="high",
            recommendation=(
                "Prioritize debt reduction before increasing investment risk. "
                "High leverage combined with aggressive investing can lead to "
                "forced liquidation during market downturns. / "
                "请在增加投资风险之前优先减少债务。"
                "高杠杆与激进投资相结合可能导致市场下跌时被迫清算。"
            ),
        ))

    # ============================================================
    # 5. Emergency Fund Adequacy / 应急基金充足性检测
    # ============================================================
    if profile.financial.emergency_fund_months < 3 and rp.willingness_score >= 3.0:
        biases.append(BehavioralBias(
            bias_type="inadequate_safety_net",
            name="Inadequate Safety Net / 安全网不足",
            description=(
                f"Your emergency fund covers only "
                f"{profile.financial.emergency_fund_months:.0f} months of expenses, "
                f"below the recommended 3-6 months. Yet you show moderate-to-high "
                f"risk tolerance. / "
                f"您的应急基金仅覆盖 {profile.financial.emergency_fund_months:.0f} 个月的支出，"
                f"低于推荐的 3-6 个月。但您显示出中等至高的风险容忍度。"
            ),
            severity="medium",
            recommendation=(
                "Build your emergency fund to at least 3-6 months of expenses "
                "before taking on significant investment risk. This prevents "
                "the need to sell investments at unfavorable times. / "
                "请在承担重大投资风险之前，将应急基金建立到至少 3-6 个月的支出。"
                "这可以避免在不利时机被迫出售投资。"
            ),
        ))

    return biases


# =============================================================
# Profile Comparison / 画像对比分析
# =============================================================
@dataclass
class ProfileComparison:
    """
    Represents a comparison between multiple client profiles.
    多个客户画像的对比结果。
    """
    client_names: list[str] = field(default_factory=list)
    risk_score_comparison: dict[str, float] = field(default_factory=dict)
    risk_level_comparison: dict[str, str] = field(default_factory=dict)
    net_worth_comparison: dict[str, float] = field(default_factory=dict)
    savings_rate_comparison: dict[str, float] = field(default_factory=dict)
    bias_count_comparison: dict[str, int] = field(default_factory=dict)
    financial_summary: dict[str, dict] = field(default_factory=dict)
    insights: list[str] = field(default_factory=list)
    comparison_date: str = field(default_factory=lambda: datetime.now().isoformat())


def compare_profiles(profiles: list[ClientProfile]) -> ProfileComparison:
    """
    Compare multiple client profiles across key financial and risk metrics.
    对比多个客户画像的关键财务和风险指标。

    This function enables wealth managers to perform side-by-side analysis
    of different clients, useful for resource allocation and service tiering.

    Args:
        profiles: List of ClientProfile instances to compare (minimum 2)

    Returns:
        ProfileComparison with structured comparison data and insights

    Raises:
        ValueError: If fewer than 2 profiles provided

    CFA Reference:
        - IPS comparison across client segments
        - Risk tolerance = min(ability, willingness) for each client
        - Behavioral bias severity analysis across client base
    """
    if len(profiles) < 2:
        raise ValueError(
            "At least 2 profiles required for comparison. / "
            "至少需要 2 个画像才能进行对比。"
        )

    comparison = ProfileComparison()

    for profile in profiles:
        name = profile.name
        comparison.client_names.append(name)

        # Risk score and level / 风险评分与等级
        rp = profile.risk_profile
        comparison.risk_score_comparison[name] = rp.final_score
        comparison.risk_level_comparison[name] = rp.tolerance_level

        # Net worth comparison / 净资产对比
        fin = profile.financial
        comparison.net_worth_comparison[name] = fin.net_worth

        # Savings rate comparison / 储蓄率对比
        savings_rate = fin.savings_rate
        comparison.savings_rate_comparison[name] = savings_rate

        # Behavioral bias count / 行为偏差数量
        biases = identify_behavioral_biases(profile)
        comparison.bias_count_comparison[name] = len(biases)

        # Financial summary / 财务概要
        comparison.financial_summary[name] = {
            "annual_income": fin.annual_income,
            "net_worth": fin.net_worth,
            "annual_savings": fin.annual_income - fin.annual_expenses,
            "savings_rate": savings_rate,
            "emergency_fund_months": fin.emergency_fund_months,
            "risk_score": rp.final_score,
            "risk_level": rp.tolerance_level,
        }

    # Generate insights / 生成对比洞察
    comparison.insights = _generate_comparison_insights(comparison, profiles)

    return comparison


def _generate_comparison_insights(
    comparison: ProfileComparison,
    profiles: list[ClientProfile],
) -> list[str]:
    """
    Generate analytical insights from profile comparison.
    从画像对比中生成分析洞察。
    """
    insights: list[str] = []

    # Find highest and lowest risk clients / 找出最高和最低风险客户
    risk_scores = comparison.risk_score_comparison
    if risk_scores:
        max_risk_name = max(risk_scores, key=risk_scores.get)
        min_risk_name = min(risk_scores, key=risk_scores.get)

        if max_risk_name != min_risk_name:
            insights.append(
                f"Risk tolerance varies significantly: {max_risk_name} "
                f"({risk_scores[max_risk_name]:.1f}) vs {min_risk_name} "
                f"({risk_scores[min_risk_name]:.1f}). / "
                f"风险容忍度差异显著：{max_risk_name} "
                f"({risk_scores[max_risk_name]:.1f}) vs {min_risk_name} "
                f"({risk_scores[min_risk_name]:.1f})。"
            )

    # Find highest net worth client / 找出最高净资产客户
    net_worths = comparison.net_worth_comparison
    if net_worths:
        max_nw_name = max(net_worths, key=net_worths.get)
        min_nw_name = min(net_worths, key=net_worths.get)
        if max_nw_name != min_nw_name:
            nw_ratio = (
                net_worths[max_nw_name] / net_worths[min_nw_name]
                if net_worths[min_nw_name] > 0 else float('inf')
            )
            insights.append(
                f"Net worth range: {max_nw_name} has {nw_ratio:.1f}x "
                f"the net worth of {min_nw_name}. / "
                f"净资产范围：{max_nw_name} 是 {min_nw_name} 的 {nw_ratio:.1f} 倍。"
            )

    # Savings rate comparison / 储蓄率对比
    savings_rates = comparison.savings_rate_comparison
    if savings_rates:
        avg_rate = sum(savings_rates.values()) / len(savings_rates)
        high_savers = [
            name for name, rate in savings_rates.items()
            if rate > avg_rate * 1.5
        ]
        if high_savers:
            insights.append(
                f"High savers ({', '.join(high_savers)}) may benefit from "
                f"more aggressive investment strategies. / "
                f"高储蓄率客户 ({', '.join(high_savers)}) 可能适合更激进的投资策略。"
            )

    # Behavioral bias analysis / 行为偏差分析
    bias_counts = comparison.bias_count_comparison
    if bias_counts:
        max_biases = max(bias_counts.values())
        if max_biases > 0:
            high_bias_clients = [
                name for name, count in bias_counts.items()
                if count == max_biases
            ]
            insights.append(
                f"Client(s) with most behavioral biases "
                f"({', '.join(high_bias_clients)}: {max_biases} biases) "
                f"may benefit from enhanced behavioral coaching. / "
                f"行为偏差最多的客户 "
                f"({', '.join(high_bias_clients)}: {max_biases} 个偏差) "
                f"可能需要更多的行为金融指导。"
            )

    # Risk ability vs willingness mismatch / 风险能力与意愿不匹配
    for profile in profiles:
        rp = profile.risk_profile
        if rp.ability_score >= 4.0 and rp.willingness_score <= 2.0:
            insights.append(
                f"{profile.name} has high risk ability "
                f"({rp.ability_score:.1f}) but low willingness "
                f"({rp.willingness_score:.1f}), indicating potential "
                f"for education on risk/return trade-offs. / "
                f"{profile.name} 的风险能力高 "
                f"({rp.ability_score:.1f}) 但意愿低 "
                f"({rp.willingness_score:.1f})，"
                f"可通过教育改善风险收益认知。"
            )

    if not insights:
        insights.append(
            "Profiles are relatively similar across key metrics. / "
            "各画像在关键指标上较为相似。"
        )

    return insights


def format_comparison_report(comparison: ProfileComparison) -> str:
    """
    Format profile comparison as a readable report.
    将画像对比格式化为可读报告。
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("CLIENT PROFILE COMPARISON REPORT / 客户画像对比报告")
    lines.append("=" * 60)
    lines.append(f"Report Date / 报告日期: {comparison.comparison_date}")
    lines.append("")

    # Risk comparison table / 风险对比表
    lines.append("-" * 60)
    lines.append("RISK PROFILE COMPARISON / 风险画像对比")
    lines.append("-" * 60)
    header = f"{'Client':<20} {'Score':<10} {'Level':<20}"
    lines.append(header)
    lines.append("-" * 50)
    for name in comparison.client_names:
        score = comparison.risk_score_comparison.get(name, 0)
        level = comparison.risk_level_comparison.get(name, "N/A")
        lines.append(f"{name:<20} {score:<10.1f} {level:<20}")
    lines.append("")

    # Financial comparison / 财务对比
    lines.append("-" * 60)
    lines.append("FINANCIAL COMPARISON / 财务对比")
    lines.append("-" * 60)
    header = f"{'Client':<20} {'Net Worth':<15} {'Savings Rate':<15}"
    lines.append(header)
    lines.append("-" * 50)
    for name in comparison.client_names:
        nw = comparison.net_worth_comparison.get(name, 0)
        sr = comparison.savings_rate_comparison.get(name, 0)
        lines.append(f"{name:<20} ${nw:>12,.0f} {sr:>12.1%}")
    lines.append("")

    # Behavioral bias comparison / 行为偏差对比
    lines.append("-" * 60)
    lines.append("BEHAVIORAL BIASES / 行为偏差")
    lines.append("-" * 60)
    for name in comparison.client_names:
        count = comparison.bias_count_comparison.get(name, 0)
        lines.append(f"{name:<20} {count} biases detected")
    lines.append("")

    # Insights / 洞察
    lines.append("-" * 60)
    lines.append("KEY INSIGHTS / 关键洞察")
    lines.append("-" * 60)
    for i, insight in enumerate(comparison.insights, 1):
        lines.append(f"{i}. {insight}")
    lines.append("")

    return "\n".join(lines)
