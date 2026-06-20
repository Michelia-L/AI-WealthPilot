"""
Client profiling agent using the CFA IPS framework.

Collects client information through structured questionnaires and
computes risk tolerance scores following the CFA dual-track model:
Risk Tolerance = min(Ability, Willingness).

References:
    - CFA L3 PWM: Investment Policy Statement framework
    - CFA L3: Risk Tolerance = min(Ability, Willingness)
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.utils import sanitize_filename


# Breakpoints for mapping 1-5 risk score to risk tolerance levels.
RISK_SCORE_BREAKPOINTS: list[float] = [1.5, 2.5, 3.5, 4.5]


RISK_LEVEL_LABELS: list[str] = [
    "Conservative / 保守型",
    "Moderately Conservative / 稳健型",
    "Moderate / 平衡型",
    "Moderately Aggressive / 成长型",
    "Aggressive / 进取型",
]


def classify_risk_score(score: float) -> str:
    """Classify a 1-5 risk score into a bilingual risk tolerance label."""
    for i, breakpoint in enumerate(RISK_SCORE_BREAKPOINTS):
        if score <= breakpoint:
            return RISK_LEVEL_LABELS[i]
    return RISK_LEVEL_LABELS[-1]


@dataclass
class FinancialSituation:
    """Client's financial position."""
    annual_income: float = 0.0
    annual_expenses: float = 0.0
    investable_assets: float = 0.0
    total_liabilities: float = 0.0
    emergency_fund_months: float = 0.0

    @property
    def net_worth(self) -> float:
        """Net worth = investable assets - liabilities."""
        return self.investable_assets - self.total_liabilities

    @property
    def savings_rate(self) -> float:
        """Savings rate = (income - expenses) / income."""
        if self.annual_income <= 0:
            return 0.0
        return (self.annual_income - self.annual_expenses) / self.annual_income

    @property
    def debt_to_asset_ratio(self) -> float:
        """Debt-to-asset ratio."""
        if self.investable_assets <= 0:
            return 1.0
        return self.total_liabilities / self.investable_assets


@dataclass
class InvestmentGoal:
    """A single investment goal with target amount and time horizon."""
    name: str = ""
    target_amount: float = 0.0
    years: int = 0
    priority: str = "medium"


@dataclass
class RiskProfile:
    """Risk tolerance assessment: Risk Tolerance = min(Ability, Willingness)."""
    ability_score: float = 0.0
    willingness_score: float = 0.0
    tolerance_level: str = ""
    description: str = ""

    @property
    def final_score(self) -> float:
        """Final score = min(ability, willingness)."""
        if self.ability_score == 0 or self.willingness_score == 0:
            return 0.0
        return min(self.ability_score, self.willingness_score)

    def classify(self) -> str:
        """Classify risk tolerance level based on final score."""
        return classify_risk_score(self.final_score)


@dataclass
class ClientProfile:
    """Complete client profile following the CFA IPS framework."""

    name: str = ""
    age: int = 30
    marital_status: str = "single"  # single / married / divorced / widowed
    dependents: int = 0

    financial: FinancialSituation = field(default_factory=FinancialSituation)

    goals: list = field(default_factory=list)


    time_horizon_years: int = 10

    is_multi_stage: bool = False



    liquidity_needs: float = 0.0


    tax_status: str = "taxable"  # tax-exempt / taxable / tax-deferred


    esg_preference: bool = False
    sector_restrictions: list = field(default_factory=list)
    notes: str = ""


    risk_profile: RiskProfile = field(default_factory=RiskProfile)


    ability_answers: dict[str, str] = field(default_factory=dict)
    willingness_answers: dict[str, str] = field(default_factory=dict)


    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def summary(self) -> str:
        """Human-readable summary of the client profile."""
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


# Question options with corresponding scores
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
    """Compute the client's objective ability-to-bear-risk score (1-5)."""
    scores = []
    for q_key, q_data in RISK_ABILITY_QUESTIONS.items():
        if q_key in answers:
            option_key = answers[q_key]
            if option_key in q_data["options"]:
                scores.append(q_data["options"][option_key]["score"])
    return sum(scores) / len(scores) if scores else 0.0


def compute_willingness_score(answers: dict) -> float:
    """Compute the client's subjective willingness-to-take-risk score (1-5)."""
    scores = []
    for q_key, q_data in RISK_WILLINGNESS_QUESTIONS.items():
        if q_key in answers:
            option_key = answers[q_key]
            if option_key in q_data["options"]:
                scores.append(q_data["options"][option_key]["score"])
    return sum(scores) / len(scores) if scores else 0.0


def assess_risk(ability_answers: dict, willingness_answers: dict) -> RiskProfile:
    """Compute full risk profile from questionnaire answers."""
    profile = RiskProfile(
        ability_score=compute_ability_score(ability_answers),
        willingness_score=compute_willingness_score(willingness_answers),
    )
    profile.tolerance_level = profile.classify()
    return profile



PROFILES_DIR = DATA_DIR / "profiles"


def save_profile(profile: ClientProfile) -> Path:
    """Save a client profile to a JSON file."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(profile.name)
    filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = PROFILES_DIR / filename

    profile.updated_at = datetime.now().isoformat()

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(profile), f, indent=2, ensure_ascii=False)

    return filepath


def load_profile(filepath: Path) -> ClientProfile:
    """Load a client profile from a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

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
    """List all saved client profiles with summary info."""
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
    """Update an existing client profile file in-place."""
    if not filepath.exists():
        raise FileNotFoundError(
            f"Profile file not found: {filepath} / 画像文件未找到: {filepath}"
        )

    profile.updated_at = datetime.now().isoformat()

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(profile), f, indent=2, ensure_ascii=False)

    return filepath


def delete_profile(filepath: Path) -> bool:
    """Delete a client profile file."""
    try:
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    except Exception:
        return False



@dataclass
class BehavioralBias:
    """A detected behavioral finance bias."""
    bias_type: str
    name: str
    description: str
    severity: str
    recommendation: str


def identify_behavioral_biases(profile: ClientProfile) -> list[BehavioralBias]:
    """Identify potential behavioral biases from client profile data."""
    biases: list[BehavioralBias] = []
    rp = profile.risk_profile


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

    # When ability and willingness conflict, use the lower score
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



@dataclass
class ProfileComparison:
    """Comparison results across multiple client profiles."""
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
    """Compare multiple client profiles across key metrics."""
    if len(profiles) < 2:
        raise ValueError(
            "At least 2 profiles required for comparison. / "
            "至少需要 2 个画像才能进行对比。"
        )

    comparison = ProfileComparison()

    for profile in profiles:
        name = profile.name
        comparison.client_names.append(name)


        rp = profile.risk_profile
        comparison.risk_score_comparison[name] = rp.final_score
        comparison.risk_level_comparison[name] = rp.tolerance_level

        fin = profile.financial
        comparison.net_worth_comparison[name] = fin.net_worth

        savings_rate = fin.savings_rate
        comparison.savings_rate_comparison[name] = savings_rate

        biases = identify_behavioral_biases(profile)
        comparison.bias_count_comparison[name] = len(biases)

        comparison.financial_summary[name] = {
            "annual_income": fin.annual_income,
            "net_worth": fin.net_worth,
            "annual_savings": fin.annual_income - fin.annual_expenses,
            "savings_rate": savings_rate,
            "emergency_fund_months": fin.emergency_fund_months,
            "risk_score": rp.final_score,
            "risk_level": rp.tolerance_level,
        }

    comparison.insights = _generate_comparison_insights(comparison, profiles)

    return comparison


def _generate_comparison_insights(
    comparison: ProfileComparison,
    profiles: list[ClientProfile],
) -> list[str]:
    """Generate analytical insights from profile comparison."""
    insights: list[str] = []


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
    """Format profile comparison as a readable report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("CLIENT PROFILE COMPARISON REPORT / 客户画像对比报告")
    lines.append("=" * 60)
    lines.append(f"Report Date / 报告日期: {comparison.comparison_date}")
    lines.append("")

    # Risk comparison table
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

    # Financial comparison
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

    # Behavioral bias comparison
    lines.append("-" * 60)
    lines.append("BEHAVIORAL BIASES / 行为偏差")
    lines.append("-" * 60)
    for name in comparison.client_names:
        count = comparison.bias_count_comparison.get(name, 0)
        lines.append(f"{name:<20} {count} biases detected")
    lines.append("")

    # Insights
    lines.append("-" * 60)
    lines.append("KEY INSIGHTS / 关键洞察")
    lines.append("-" * 60)
    for i, insight in enumerate(comparison.insights, 1):
        lines.append(f"{i}. {insight}")
    lines.append("")

    return "\n".join(lines)
