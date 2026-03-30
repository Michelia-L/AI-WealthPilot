"""
AI WealthPilot - Risk Metrics Module
AI WealthPilot - 风险度量模块

Computes standard risk and performance metrics for portfolio analysis.
This module provides the quantitative foundation for evaluating portfolio
quality beyond simple returns — measuring how much risk was taken to
achieve those returns, and how bad losses could get in extreme scenarios.

计算投资组合分析中的标准风险和绩效指标。
本模块提供量化基础，用于评估组合质量——
不仅关注收益本身，还衡量为获取收益所承担的风险，
以及极端情景下可能遭受的损失。

Metrics implemented / 已实现的指标:
    - Sharpe Ratio (夏普比率): Risk-adjusted return using total volatility
      使用总波动率的风险调整收益
    - Sortino Ratio (索提诺比率): Risk-adjusted return using downside deviation only
      仅使用下行偏差的风险调整收益
    - Maximum Drawdown (最大回撤): Largest peak-to-trough decline
      最大峰值到谷底的跌幅
    - Value at Risk / VaR (在险价值): Maximum expected loss at a confidence level
      给定置信水平下的最大预期损失
    - Conditional VaR / CVaR (条件在险价值): Expected loss beyond VaR threshold
      超过 VaR 阈值时的预期损失（又称 Expected Shortfall / 预期亏损）

References / 参考文献:
    - CFA® Program Curriculum — Quantitative Methods & Portfolio Management
      CFA® 课程教材 —— 定量方法与投资组合管理
    - CFA® Level III — Risk Management for Private Wealth
      CFA® 三级 —— 私人财富风险管理
    - Basel III framework for VaR and CVaR in financial risk management
      巴塞尔协议 III 中 VaR 和 CVaR 在金融风险管理中的应用
"""

import numpy as np
import pandas as pd
from typing import Optional

# 从项目配置中导入无风险利率和年交易日数
# Import risk-free rate and annual trading days from project config
from src.config import RISK_FREE_RATE, TRADING_DAYS_PER_YEAR


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    """
    Annualized Sharpe Ratio.
    年化夏普比率。

    Formula / 公式:
        Sharpe = (R_p - R_f) / σ_p

        Where / 其中:
        - R_p = annualized portfolio return (年化组合收益率)
        - R_f = annual risk-free rate (年化无风险利率)
        - σ_p = annualized portfolio volatility (年化组合波动率)

    Interpretation / 解读:
        - Sharpe > 1.0: Generally considered good (良好)
        - Sharpe > 2.0: Very good (优秀)
        - Sharpe > 3.0: Exceptional (卓越)
        - Sharpe < 0: Portfolio underperforms the risk-free asset (组合表现不如无风险资产)

    Limitation / 局限性:
        Sharpe ratio penalizes BOTH upside and downside volatility equally.
        For asymmetric return distributions (e.g., options, crypto), the Sortino
        ratio may be more appropriate.
        夏普比率同等惩罚上行和下行波动率。
        对于非对称收益分布（如期权、加密货币），索提诺比率可能更合适。

    CFA Reference / CFA 参考:
        CFA L1/L3: The Sharpe ratio is the most widely used risk-adjusted
        performance measure. It represents the slope of the Capital Allocation
        Line (CAL) from the risk-free asset to the portfolio.
        CFA 一级/三级：夏普比率是使用最广泛的风险调整绩效指标。
        它代表从无风险资产到组合的资本配置线（CAL）的斜率。

    Args:
        returns: Series of daily portfolio returns.
                 组合日收益率序列。
        risk_free_rate: Annual risk-free rate.
                        年化无风险利率。

    Returns:
        Annualized Sharpe ratio as a float.
        年化夏普比率（浮点数）。
    """
    # 年化超额收益 = 日均收益率 × 252 - 年无风险利率
    # Annualized excess return = daily mean return × 252 - annual risk-free rate
    excess = returns.mean() * TRADING_DAYS_PER_YEAR - risk_free_rate

    # 年化波动率 = 日波动率 × √252
    # Annualized volatility = daily std × √252
    # 这基于波动率按时间平方根缩放的假设（i.i.d. 收益率）
    # This is based on the assumption that volatility scales with √time (i.i.d. returns)
    vol = returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    # 避免除以零 / Avoid division by zero
    return excess / vol if vol > 0 else 0.0


def sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    """
    Annualized Sortino Ratio — uses downside deviation instead of total volatility.
    年化索提诺比率 —— 使用下行偏差代替总波动率。

    Formula / 公式:
        Sortino = (R_p - R_f) / σ_downside

        Where / 其中:
        - σ_downside = standard deviation of NEGATIVE returns only
          下行偏差 = 仅计算负收益率的标准差

    Key Difference from Sharpe / 与夏普比率的关键区别:
        The Sharpe ratio treats all volatility as "risk", but investors
        generally don't mind upside volatility (large positive returns).
        The Sortino ratio only penalizes downside moves, making it a better
        measure when return distributions are asymmetric (skewed).

        夏普比率将所有波动率都视为"风险"，但投资者通常不介意上行波动
        （大幅正收益）。索提诺比率只惩罚下行波动，
        在收益分布不对称（偏斜）时是更好的衡量指标。

    CFA Reference / CFA 参考:
        CFA L3 Performance Evaluation: Sortino ratio is preferred when
        evaluating strategies with asymmetric payoffs (e.g., option-writing
        strategies, private equity, or crypto portfolios).
        CFA 三级绩效评估：在评估非对称收益的策略（如期权卖出策略、
        私募股权或加密货币组合）时，优先使用索提诺比率。

    Args:
        returns: Series of daily portfolio returns.
                 组合日收益率序列。
        risk_free_rate: Annual risk-free rate.
                        年化无风险利率。

    Returns:
        Annualized Sortino ratio as a float.
        年化索提诺比率（浮点数）。
    """
    # 年化超额收益 / Annualized excess return
    excess = returns.mean() * TRADING_DAYS_PER_YEAR - risk_free_rate

    # 仅筛选负收益率（亏损的交易日）来计算下行偏差
    # Filter only negative returns (losing days) to compute downside deviation
    downside = returns[returns < 0]

    # 年化下行偏差 = 负收益率的标准差 × √252
    # Annualized downside deviation = std of negative returns × √252
    downside_vol = downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    # 避免除以零 / Avoid division by zero
    return excess / downside_vol if downside_vol > 0 else 0.0


def max_drawdown(prices: pd.Series) -> dict:
    """
    Maximum Drawdown — the largest peak-to-trough decline in portfolio value.
    最大回撤 —— 投资组合价值从峰值到谷底的最大跌幅。

    Formula / 公式:
        Drawdown_t = (P_t - P_peak) / P_peak
        Max Drawdown = min(Drawdown_t) for all t
        最大回撤 = 所有时间点中回撤值的最小值（最大负值）

    Interpretation / 解读:
        - A max drawdown of -30% means the portfolio lost 30% from its peak
          最大回撤 -30% 意味着组合从峰值下跌了 30%
        - This is a "worst case" historical measure — the largest cumulative
          loss an investor would have experienced if they bought at the peak
          这是一个"最坏情况"历史指标——如果投资者在峰值买入，
          可能经历的最大累计损失
        - Used extensively in hedge fund evaluation and wealth management
          在对冲基金评估和财富管理中被广泛使用

    CFA Reference / CFA 参考:
        CFA L3 Risk Management: Maximum drawdown is a key metric for
        assessing tail risk and investor pain. Clients with lower risk
        tolerance require portfolios with smaller max drawdowns.
        CFA 三级风险管理：最大回撤是评估尾部风险和投资者承受能力的关键指标。
        风险承受能力较低的客户需要最大回撤更小的组合。

    Args:
        prices: Series of portfolio prices or cumulative values (NOT returns).
                组合价格或累计净值序列（注意：不是收益率）。

    Returns:
        Dict with 'max_drawdown' (as negative percentage, e.g., -0.30 for -30%),
        'peak_date' (date of the peak), and 'trough_date' (date of the trough).
        返回字典，包含：max_drawdown（负百分比，如 -0.30 表示 -30%）、
        peak_date（峰值日期）、trough_date（谷底日期）。
    """
    # 计算截至每个时间点的历史最高价格（滚动最大值）
    # Compute the running historical peak price at each point in time
    cummax = prices.cummax()

    # 计算每个时间点相对于历史峰值的回撤幅度
    # Drawdown_t = (P_t - P_peak) / P_peak
    # 结果为负值或零（当处于新高时回撤为 0）
    # Calculate the drawdown at each point relative to its historical peak
    # Result is negative or zero (zero when at a new high)
    drawdown = (prices - cummax) / cummax

    # 找到最大回撤的谷底日期（回撤值最小的时间点）
    # Find the trough date (the point with the most negative drawdown)
    trough_idx = drawdown.idxmin()

    # 找到对应的峰值日期（谷底之前的最高价格点）
    # Find the corresponding peak date (the highest price point before the trough)
    peak_idx = prices[:trough_idx].idxmax()

    return {
        "max_drawdown": float(drawdown.min()),
        "peak_date": peak_idx,
        "trough_date": trough_idx,
    }


def value_at_risk(
    returns: pd.Series,
    confidence: float = 0.95,
    method: str = "historical",
) -> float:
    """
    Value at Risk (VaR) — the maximum expected loss at a given confidence level.
    在险价值（VaR）—— 在给定置信水平下的最大预期损失。

    Two methods are supported / 支持两种方法:

    1. Historical Simulation (历史模拟法):
       - Uses the actual historical return distribution
         使用实际的历史收益率分布
       - Non-parametric: makes no assumptions about the distribution shape
         非参数方法：不对分布形状做任何假设
       - VaR = negative of the (1-confidence) percentile of historical returns
         VaR = 历史收益率的 (1-confidence) 百分位数的负值
       - Example: 95% VaR uses the 5th percentile of returns
         例如：95% VaR 使用收益率的第 5 百分位数

    2. Parametric / Variance-Covariance (参数法 / 方差-协方差法):
       - Assumes returns follow a Normal (Gaussian) distribution
         假设收益率服从正态（高斯）分布
       - VaR = -(μ + z_α × σ)
       - Where z_α is the z-score for the given confidence level
         其中 z_α 是给定置信水平对应的 z 值
       - Example: 95% confidence → z = -1.645
         例如：95% 置信度 → z = -1.645

    CFA Reference / CFA 参考:
        CFA L2/L3 Risk Management: VaR answers the question "What is the
        maximum loss that will NOT be exceeded with X% confidence over a
        given time horizon?" VaR is required by Basel III for bank capital
        requirements.
        CFA 二级/三级风险管理：VaR 回答的问题是"在给定时间范围内，
        有 X% 的把握损失不会超过多少？" 巴塞尔协议 III 要求银行使用
        VaR 来确定资本金要求。

    Limitation / 局限性:
        VaR does NOT tell you how bad losses could be beyond the VaR threshold.
        For that, use CVaR / Expected Shortfall (see conditional_var).
        VaR 不能告诉你超过 VaR 阈值后的损失会有多大。
        要了解尾部损失，请使用 CVaR / 预期亏损（见 conditional_var 函数）。

    Args:
        returns: Series of portfolio returns (daily).
                 组合收益率序列（日频）。
        confidence: Confidence level (e.g., 0.95 for 95%, 0.99 for 99%).
                    置信水平（如 0.95 表示 95%，0.99 表示 99%）。
        method: 'historical' for historical simulation (历史模拟法),
                'parametric' for Gaussian assumption (参数法/正态假设).

    Returns:
        VaR as a positive number (representing the magnitude of the loss).
        VaR 作为正数返回（表示损失的绝对值大小）。
    """
    if method == "historical":
        # 历史模拟法：直接取历史收益率分布的左尾百分位数
        # Historical simulation: take the left-tail percentile of actual returns
        # 例如 95% 置信度 → 取第 5 百分位数 → 加负号变为正数
        # e.g., 95% confidence → take 5th percentile → negate to make positive
        return -float(np.percentile(returns, (1 - confidence) * 100))
    elif method == "parametric":
        from scipy.stats import norm
        # 参数法：假设收益率正态分布，利用 z 值计算
        # Parametric: assume Normal distribution, use z-score
        # z_α = 正态分布的分位数（95% 置信度对应 z ≈ -1.645）
        # z_α = quantile of the Normal distribution (95% confidence → z ≈ -1.645)
        z = norm.ppf(1 - confidence)
        # VaR = -(μ + z × σ)
        # 其中 μ 是日均收益率，σ 是日收益率标准差
        # where μ is daily mean return, σ is daily return std
        return -(returns.mean() + z * returns.std())
    else:
        raise ValueError(f"Unknown method: {method}")


def conditional_var(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """
    Conditional VaR (CVaR) / Expected Shortfall (ES).
    条件在险价值（CVaR）/ 预期亏损（ES）。

    CVaR measures the expected (average) loss in the worst-case scenarios
    that exceed the VaR threshold. It captures "tail risk" — the risk of
    extreme, rare events.

    CVaR 衡量在超过 VaR 阈值的最坏情景中的预期（平均）损失。
    它捕捉的是"尾部风险"——极端罕见事件的风险。

    Formula / 公式:
        CVaR = E[Loss | Loss > VaR]
        CVaR = 在损失超过 VaR 条件下的损失期望值

    Why CVaR is preferred over VaR / 为什么 CVaR 优于 VaR:
        - VaR only tells you the threshold; CVaR tells you the average
          loss when things go really bad
          VaR 只告诉你阈值；CVaR 告诉你情况真的很糟时的平均损失
        - CVaR is a "coherent" risk measure (satisfies subadditivity),
          while VaR is not
          CVaR 是"一致性"风险度量（满足次可加性），而 VaR 不是
        - Basel III has moved toward requiring Expected Shortfall
          巴塞尔协议 III 已转向要求使用预期亏损

    CFA Reference / CFA 参考:
        CFA L2/L3: CVaR (Expected Shortfall) provides a more complete
        picture of tail risk than VaR. It is especially important for
        portfolios with non-normal return distributions (fat tails).
        CFA 二级/三级：CVaR（预期亏损）比 VaR 提供了更完整的尾部风险图景。
        对于非正态收益分布（肥尾）的组合尤为重要。

    Args:
        returns: Series of portfolio returns (daily).
                 组合收益率序列（日频）。
        confidence: Confidence level (e.g., 0.95 for 95%).
                    置信水平（如 0.95 表示 95%）。

    Returns:
        CVaR as a positive number (average loss in worst-case tail).
        CVaR 作为正数返回（尾部最坏情况下的平均损失）。
    """
    # 先计算历史 VaR 作为阈值
    # First compute historical VaR as the threshold
    var = value_at_risk(returns, confidence, method="historical")

    # 筛选出所有损失超过 VaR 的交易日（即尾部最坏的那些天）
    # Filter all trading days where the loss exceeded VaR (the worst tail days)
    # returns <= -var 表示收益率小于等于 VaR 的负值（即亏损 >= VaR）
    # returns <= -var means return is at or below the negative VaR (i.e., loss >= VaR)
    tail_losses = returns[returns <= -var]

    # 取尾部损失的均值并取负号（返回正数表示损失大小）
    # Take the mean of tail losses and negate (return positive number for loss magnitude)
    # 如果没有尾部数据（极少见），回退到 VaR 值
    # If no tail data exists (very rare), fall back to VaR value
    return -float(tail_losses.mean()) if len(tail_losses) > 0 else var


def compute_all_metrics(
    returns: pd.Series,
    prices: Optional[pd.Series] = None,
) -> dict:
    """
    Compute all risk metrics at once — a convenience function for dashboards.
    一次性计算所有风险指标 —— 为仪表板提供的便捷函数。

    This function aggregates all individual risk metrics into a single dictionary,
    making it easy to populate a dashboard or generate a risk report.

    本函数将所有单独的风险指标汇总到一个字典中，
    方便用于填充仪表板或生成风险报告。

    Metrics included / 包含的指标:
        - Annualized return (年化收益率)
        - Annualized volatility (年化波动率)
        - Sharpe ratio (夏普比率)
        - Sortino ratio (索提诺比率)
        - 95% VaR (95% 在险价值)
        - 95% CVaR (95% 条件在险价值)
        - Skewness (偏度): measures return distribution asymmetry
          衡量收益分布的不对称性（负偏 = 左尾更长 = 极端亏损更频繁）
        - Kurtosis (峰度): measures tail thickness ("fat tails")
          衡量尾部厚度（"肥尾"）（高峰度 = 极端事件更频繁）
        - Max drawdown (最大回撤, optional): if price series is provided
          如果提供了价格序列，则额外计算最大回撤

    CFA Reference / CFA 参考:
        CFA L1 Quantitative Methods: Skewness and kurtosis are the 3rd and
        4th moments of the return distribution. Negative skewness and excess
        kurtosis (> 3) indicate that Normal distribution assumptions may
        underestimate tail risk.
        CFA 一级定量方法：偏度和峰度是收益分布的第 3 和第 4 阶矩。
        负偏度和超额峰度（> 3）表明正态分布假设可能低估了尾部风险。

    Args:
        returns: Daily return series for the portfolio or asset.
                 组合或资产的日收益率序列。
        prices: Optional price series (needed for max drawdown calculation).
                If not provided, max drawdown will be skipped.
                可选的价格序列（计算最大回撤时需要）。
                如果未提供，将跳过最大回撤计算。

    Returns:
        Dict of all computed metrics with descriptive string keys.
        包含所有计算指标的字典，键为描述性字符串。
    """
    metrics = {
        # 年化收益率 = 日均收益率 × 252
        # Annualized return = daily mean × 252
        "annualized_return": float(returns.mean() * TRADING_DAYS_PER_YEAR),

        # 年化波动率 = 日标准差 × √252
        # Annualized volatility = daily std × √252
        "annualized_volatility": float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)),

        # 风险调整绩效指标 / Risk-adjusted performance metrics
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),

        # 尾部风险指标 / Tail risk metrics
        "var_95": value_at_risk(returns, 0.95),
        "cvar_95": conditional_var(returns, 0.95),

        # 分布形态指标 / Distribution shape metrics
        # 偏度 (skewness): 0 = 对称, 负值 = 左偏（不利）, 正值 = 右偏（有利）
        # Skewness: 0 = symmetric, negative = left-skewed (unfavorable), positive = right-skewed
        "skewness": float(returns.skew()),

        # 峰度 (kurtosis): pandas 使用超额峰度（正态分布 = 0）
        # 正值 = 肥尾（极端事件更多）, 负值 = 瘦尾
        # Kurtosis: pandas uses excess kurtosis (Normal = 0)
        # Positive = fat tails (more extreme events), negative = thin tails
        "kurtosis": float(returns.kurtosis()),
    }

    # 如果提供了价格序列，额外计算最大回撤
    # If price series is provided, additionally compute maximum drawdown
    if prices is not None:
        dd = max_drawdown(prices)
        metrics["max_drawdown"] = dd["max_drawdown"]
        metrics["peak_date"] = str(dd["peak_date"])
        metrics["trough_date"] = str(dd["trough_date"])

    return metrics
