"""
AI WealthPilot - Portfolio Recommender Module
AI WealthPilot - 投资组合推荐模块

Integrates the quantitative portfolio optimization engine with
client profiling to generate personalized asset allocation recommendations.

将量化投资组合优化引擎与客户画像集成，
生成个性化的资产配置推荐。

Key Features / 核心功能:
    1. Map client risk scores to target risk levels
       将客户风险评分映射到目标风险水平
    2. Generate optimal portfolio based on risk profile
       基于风险画像生成最优组合
    3. Provide personalized allocation recommendations
       提供个性化配置推荐

CFA Reference / CFA 参考:
    - CFA L3 Asset Allocation: Risk tolerance drives asset allocation
      CFA 三级资产配置：风险承受能力驱动资产配置
    - CFA L3: Strategic Asset Allocation (SAA) based on client profile
      CFA 三级：基于客户画像的战略性资产配置
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from src.agents.profiler import ClientProfile, RiskProfile
from src.portfolio.optimizer import PortfolioOptimizer
from src.config import RISK_FREE_RATE


# ============================================================
# Data Model — Portfolio Recommendation
# 数据模型 —— 投资组合推荐
# ============================================================

@dataclass
class PortfolioRecommendation:
    """
    Represents a personalized portfolio recommendation.
    表示个性化的投资组合推荐。

    Contains the recommended asset allocation along with
    expected performance metrics and rationale.

    包含推荐的资产配置以及预期绩效指标和理由。
    """
    # 风险等级 / Risk level
    risk_level: str = ""
    # 建议配置：资产类别 → 权重 / Suggested allocation: asset class → weight
    suggested_allocation: dict = field(default_factory=dict)
    # 预期年化收益率 / Expected annualized return
    expected_return: float = 0.0
    # 预期年化波动率 / Expected annualized volatility
    expected_volatility: float = 0.0
    # 夏普比率 / Sharpe ratio
    sharpe_ratio: float = 0.0
    # 配置理由 / Allocation rationale
    rationale: str = ""
    # 资产类别列表 / Asset class names
    asset_classes: list = field(default_factory=list)
    # 权重数组 / Weights array
    weights: np.ndarray = field(default_factory=lambda: np.array([]))


# ============================================================
# Risk Score to Target Volatility Mapping
# 风险评分到目标波动率的映射
# ============================================================

# 风险评分 → 目标波动率范围
# Risk score → target volatility range
RISK_VOLATILITY_MAP = {
    # Conservative / 保守型: 1.0-1.5 → 5-8% volatility
    "conservative": {"min_score": 1.0, "max_score": 1.5, "target_vol": 0.06},
    # Moderately Conservative / 稳健型: 1.5-2.5 → 8-12% volatility
    "moderately_conservative": {"min_score": 1.5, "max_score": 2.5, "target_vol": 0.10},
    # Moderate / 平衡型: 2.5-3.5 → 12-15% volatility
    "moderate": {"min_score": 2.5, "max_score": 3.5, "target_vol": 0.13},
    # Moderately Aggressive / 成长型: 3.5-4.5 → 15-18% volatility
    "moderately_aggressive": {"min_score": 3.5, "max_score": 4.5, "target_vol": 0.16},
    # Aggressive / 进取型: 4.5-5.0 → 18-22% volatility
    "aggressive": {"min_score": 4.5, "max_score": 5.0, "target_vol": 0.20},
}


def _get_target_volatility(risk_score: float) -> float:
    """
    Map client risk score to target portfolio volatility.
    将客户风险评分映射到目标组合波动率。

    This function implements the CFA principle that risk tolerance
    should drive asset allocation decisions.

    该函数实现了 CFA 原则：风险承受能力应驱动资产配置决策。

    Args:
        risk_score: Client's final risk score (1-5).
                    客户的最终风险评分 (1-5)。

    Returns:
        Target annualized volatility (e.g., 0.12 for 12%).
        目标年化波动率（如 0.12 表示 12%）。
    """
    # Clamp risk_score to valid range [1.0, 5.0]
    # Risk scores outside this range indicate uninitialized or invalid profiles
    # 将风险评分限制在 [1.0, 5.0] 的有效范围内
    risk_score = max(1.0, min(5.0, risk_score))

    # Linear interpolation between risk levels
    # 风险等级之间的线性插值
    if risk_score <= 1.5:
        # Conservative: 5-8% volatility
        return 0.05 + (risk_score - 1.0) * 0.06
    elif risk_score <= 2.5:
        # Moderately Conservative: 8-12% volatility
        return 0.08 + (risk_score - 1.5) * 0.04
    elif risk_score <= 3.5:
        # Moderate: 12-15% volatility
        return 0.12 + (risk_score - 2.5) * 0.03
    elif risk_score <= 4.5:
        # Moderately Aggressive: 15-18% volatility
        return 0.15 + (risk_score - 3.5) * 0.03
    else:
        # Aggressive: 18-22% volatility
        return 0.18 + (risk_score - 4.5) * 0.04


def _classify_risk_level(risk_score: float) -> str:
    """
    Classify risk score into risk level category.
    将风险评分分类为风险等级类别。

    Args:
        risk_score: Client's final risk score (1-5).

    Returns:
        Risk level string in English.
    """
    if risk_score <= 1.5:
        return "Conservative"
    elif risk_score <= 2.5:
        return "Moderately Conservative"
    elif risk_score <= 3.5:
        return "Moderate"
    elif risk_score <= 4.5:
        return "Moderately Aggressive"
    else:
        return "Aggressive"


# ============================================================
# Core Recommendation Function
# 核心推荐函数
# ============================================================

def recommend_portfolio(
    profile: ClientProfile,
    returns_data: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
) -> PortfolioRecommendation:
    """
    Generate personalized portfolio recommendation based on client profile.
    基于客户画像生成个性化投资组合推荐。

    This function implements the CFA asset allocation framework:
    1. Assess client risk tolerance (from profiler)
       评估客户风险承受能力（来自 profiler）
    2. Map risk score to target volatility
       将风险评分映射到目标波动率
    3. Use MVO optimizer to find optimal portfolio
       使用 MVO 优化器找到最优组合
    4. Generate recommendation with rationale
       生成推荐及理由

    CFA Reference / CFA 参考:
        CFA L3 Asset Allocation:
        - Risk tolerance = min(Ability, Willingness)
        - Asset allocation should reflect risk tolerance
        - Diversification reduces portfolio risk

    Args:
        profile: Complete ClientProfile with risk assessment.
                 包含风险评估的完整 ClientProfile。
        returns_data: DataFrame of historical asset returns.
                      历史资产收益率 DataFrame。
        risk_free_rate: Annual risk-free rate.
                        年化无风险利率。

    Returns:
        PortfolioRecommendation with allocation and metrics.
        包含配置和指标的 PortfolioRecommendation。
    """
    # Step 1: Get risk score from profile
    # 步骤 1: 从画像获取风险评分
    risk_score = profile.risk_profile.final_score
    risk_level = _classify_risk_level(risk_score)

    # Step 2: Map to target volatility
    # 步骤 2: 映射到目标波动率
    target_volatility = _get_target_volatility(risk_score)

    # Step 3: Initialize optimizer
    # 步骤 3: 初始化优化器
    optimizer = PortfolioOptimizer(returns_data, risk_free_rate)

    # Step 4: Find optimal portfolio at target volatility
    # 步骤 4: 在目标波动率下寻找最优组合
    result = optimizer.minimize_volatility()

    # Step 5: If target return is specified in goals, try to achieve it
    # 步骤 5: 如果目标中指定了目标收益率，尝试达到
    if profile.goals:
        # Calculate required return based on most important goal
        primary_goal = max(profile.goals, key=lambda g: g.priority == "high")
        if primary_goal.years > 0:
            required_return = (
                (primary_goal.target_amount / max(profile.financial.investable_assets, 1))
                ** (1 / primary_goal.years)
                - 1
            )
            # Try to find portfolio with target return
            result_with_return = optimizer.minimize_volatility(
                target_return=required_return
            )
            if result_with_return.get("success", False):
                result = result_with_return

    # Step 6: Build recommendation
    # 步骤 6: 构建推荐
    weights = np.array(list(result["weights"].values()))
    asset_classes = list(result["weights"].keys())

    # Generate rationale
    rationale = _generate_rationale(
        profile, risk_level, target_volatility, result
    )

    return PortfolioRecommendation(
        risk_level=risk_level,
        suggested_allocation=result["weights"],
        expected_return=result["return"],
        expected_volatility=result["volatility"],
        sharpe_ratio=result["sharpe"],
        rationale=rationale,
        asset_classes=asset_classes,
        weights=weights,
    )


def _generate_rationale(
    profile: ClientProfile,
    risk_level: str,
    target_volatility: float,
    optimization_result: dict,
) -> str:
    """
    Generate human-readable rationale for the portfolio recommendation.
    生成投资组合推荐的人类可读理由。

    Args:
        profile: Client profile.
        risk_level: Classified risk level.
        target_volatility: Target volatility.
        optimization_result: MVO optimization result.

    Returns:
        Formatted rationale string.
    """
    rp = profile.risk_profile

    rationale_parts = [
        f"Based on your risk profile assessment (Ability: {rp.ability_score:.1f}/5, "
        f"Willingness: {rp.willingness_score:.1f}/5), "
        f"you are classified as **{risk_level}** investor.",
        "",
        f"Your target portfolio volatility is approximately "
        f"**{target_volatility:.1%}** annualized.",
        "",
    ]

    # Add conflict note if applicable
    if abs(rp.ability_score - rp.willingness_score) >= 1.0:
        rationale_parts.extend([
            "⚠️ **Note**: There is a significant difference between your "
            "objective risk ability and subjective willingness. "
            "Per CFA guidelines, we use the lower score to protect you.",
            "",
        ])

    # Add allocation explanation
    rationale_parts.extend([
        "The recommended allocation is optimized using **Mean-Variance "
        "Optimization (MVO)** based on Modern Portfolio Theory (MPT):",
        "",
    ])

    # List top allocations
    sorted_alloc = sorted(
        optimization_result["weights"].items(),
        key=lambda x: x[1],
        reverse=True,
    )
    for asset, weight in sorted_alloc[:5]:  # Top 5 assets
        if weight > 0.01:  # Only show > 1%
            rationale_parts.append(f"- **{asset}**: {weight:.1%}")

    return "\n".join(rationale_parts)


# ============================================================
# Utility Functions
# 工具函数
# ============================================================

def get_recommended_allocation_text(recommendation: PortfolioRecommendation) -> str:
    """
    Format portfolio recommendation as readable text.
    将投资组合推荐格式化为可读文本。

    Args:
        recommendation: PortfolioRecommendation instance.

    Returns:
        Formatted text string.
    """
    lines = [
        f"## Recommended Portfolio / 推荐投资组合",
        f"",
        f"**Risk Level / 风险等级**: {recommendation.risk_level}",
        f"**Expected Return / 预期收益**: {recommendation.expected_return:.2%}",
        f"**Expected Volatility / 预期波动率**: {recommendation.expected_volatility:.2%}",
        f"**Sharpe Ratio / 夏普比率**: {recommendation.sharpe_ratio:.2f}",
        f"",
        f"### Asset Allocation / 资产配置",
        f"",
    ]

    for asset, weight in sorted(
        recommendation.suggested_allocation.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        if weight > 0.001:  # Only show > 0.1%
            lines.append(f"- {asset}: {weight:.1%}")

    lines.extend([
        f"",
        f"### Rationale / 配置理由",
        f"",
        recommendation.rationale,
    ])

    return "\n".join(lines)
