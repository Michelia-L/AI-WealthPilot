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
    safe_name = profile.name.replace(" ", "_").lower() if profile.name else "unnamed"
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
