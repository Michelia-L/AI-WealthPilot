# 02 · 量化引擎

## 目的与边界

本章讲 `src/portfolio/` 的优化引擎：`optimizer.py` 的六种优化方法、`optimize_service.py` 的分发语义、`views.py` 的 BL 观点处理、`risk_constraints.py` 与 `risk_metrics.py` 两个配套库。

这一层只管一件事：**给定历史收益矩阵，算出权重**。它不做取数（第 3 章）、不做 HTTP（第 5 章）、不做持久化。引擎模块的 docstring 标注了五篇参考文献（Markowitz 1952、Black & Litterman 1992、Rockafellar & Uryasev 2000、Sharpe & Tint 1990、Spinu 2013）——本章按同样的谱系讲。

## 核心概念 · 共享地基

### 输入契约

`PortfolioOptimizer(returns, risk_free_rate, covariance_method, expected_returns, seed)` 的输入是一个**日度收益 DataFrame**：每列一个资产，列名是资产显示名（如 `US Equities (S&P 500)`，不是 ticker——改名发生在 API 取数层）。所有方法共享同一个实例状态：`mean_returns`（年化预期收益向量）与 `cov_matrix`（年化协方差矩阵）。

### 年化约定与它的边界

引擎的年化是全代码库统一的 252 交易日口径：

\[
\mu_{annual} = \bar{r}_{daily} \times 252, \qquad \Sigma_{annual} = \Sigma_{daily} \times 252, \qquad \sigma_{annual} = \sigma_{daily} \times \sqrt{252}
\]

`TRADING_DAYS_PER_YEAR = 252`（`src/config.py`）。**边界要心里有数**：加密货币 7×24 交易，√252 缩放会低估其年化波动； Mean-CVaR 的日度 CVaR 也按 ×√252 报年化（`minimize_cvar` 的 docstring 自称「标准 √T 尾部风险缩放」）。这是行业惯例口径，不是错误，但对 365 天交易的资产是系统性低估。

### 预期收益：样本均值与外部覆盖

`expected_returns` 参数（CME 引擎的接口）允许用外部向量**部分覆盖**预期收益：`reindex(returns.columns).fillna(样本均值)`——覆盖到的资产用外部值，没覆盖的保留样本均值（`__init__`）。**协方差永远来自历史收益**，不受覆盖影响。

### 协方差估计与数值稳定

`covariance_method` 三选一：`sample`（默认，样本协方差）、`ledoit-wolf`、`oas`（后两种是 sklearn 的收缩估计，**函数体内惰性 import**——不用就不加载 sklearn）。

估计完立刻做病态检查（`_check_condition_number`）：**条件数 > 1e10 时自动正则化** Σ + 10⁻⁶·I（`_regularize_covariance_matrix`，默认对角法，另实现了特征值裁剪但构造器只用对角法），并置 `is_regularized=True` 供披露。高度共线的资产组合（比如同时选了 AGG 和跟踪误差极小的同类产品）容易触发。

### 随机性的收口（P26）

`seed` 参数驱动 `self._rng = np.random.default_rng(seed)`，`random_portfolios`（Dirichlet 抽样）和 Resampled MVO（多元正态抽样）都走它——**库级 API 同 seed 可复现**（`tests/test_advanced_portfolio.py::TestSeededReproducibility` 钉住）。但注意：**API 路径不传 seed**（`optimize_service` 的 runner 全部省略该参数），所以网页端每次重跑的结果会有细微差异。这是有意的现状，不是遗漏。

### 两个求解器的分工

全引擎只有两种求解器，选择逻辑很干净：

- **scipy `minimize(method="SLSQP")`**：目标非线性的连续优化（MVO、Resampled、LDI、ERC、BL 后验组合）
- **scipy `linprog(method="highs")`**：Mean-CVaR 的 Rockafellar-Uryasev 线性规划——目标与约束全是线性的，走 LP 得到**确定性、无抽样噪声**的解

## 逐方法讲解

### 3.1 经典 MVO（Markowitz）

**金融直觉**：在「收益-风险」平面上找给定风险下收益最高（或给定收益下风险最小）的权重。最小方差点是所有分散化好处的极点；切点组合（max Sharpe）是资本配置线与前沿的切点。

**数学形式**——最小波动（`minimize_volatility`）：

\[
\min_w \; w^\top \Sigma w \quad \text{s.t.} \quad \sum_i w_i = 1, \; w^\top\mu = R_{target}\;(\text{可选})
\]

目标函数的解析梯度 \(\nabla = 2\Sigma w\) 直接喂给 SLSQP（带解析 Jacobian 的求解又快又稳）。目标收益约束是**等式**——所以前沿左下段（最小方差点以下的无效部分）也会被画出，这与教科书一致。

最大夏普（`maximize_sharpe`）最小化负 Sharpe：

\[
\min_w \; -\frac{w^\top\mu - r_f}{\sqrt{w^\top \Sigma w}}
\]

**代码落点**：

- `maximize_sharpe` **不带解析 Jacobian**（数值差分）——负 Sharpe 的解析梯度繁琐易错，SLSQP 差分足够
- 零波动是退化解：目标函数返回 `1e10` 罚值把求解器赶开（`_neg_sharpe_objective`，注释引 issue #5）；而 `portfolio_performance` 的**报告口径**遇零波动返回 Sharpe = 0——同一个零，求解时罚、报告时恕，两种处理是有意的
- `efficient_frontier`：目标网格为 `linspace(单资产最小均值, 单资产最大均值, n_points)`，逐点调 `minimize_volatility(target_return=...)`，**失败点静默跳过**（返回行数可少于 n_points）
- `random_portfolios`：`Dirichlet(α=1)` 抽样——天然多头、权重和为 1，即使全局开了 `allow_short` 也保持多头（它只服务散点图背景）
- `optimize_with_asset_class_constraints`：带组上下限的最小方差，每组生成两条不等式约束；lambda 用默认参数绑定循环变量（代码注释明示这是刻意的闭包陷阱规避）

### 3.2 Resampled MVO（Michaud 重采样）

**金融直觉**：样本均值 \(\hat{\mu}\) 是估计值，估计误差会被优化器放大成极端权重（「误差最大化器」）。Michaud 的办法：承认 \(\hat{\mu}\) 有不确定性，从它的抽样分布里反复重估、反复优化，把所得权重**平均**——平均后的权重天然更分散、更稳。

**数学形式**：每次抽样从估计量的渐近分布取一个备选预期收益向量：

\[
\mu^* \sim \mathcal{N}(\hat{\mu}_{daily}, \; \Sigma_{daily} / T)
\]

T 是样本天数——样本越大，抽样分布越紧，重采样退化为经典 MVO。对每个 \(\mu^*\) 跑一次目标求解（max-Sharpe 或 min-vol），收集成功解的权重取平均：

\[
\bar{w} = \frac{1}{K}\sum_{k=1}^{K} w^{(k)}, \quad \text{再归一化使 } \sum_i \bar{w}_i = 1
\]

**代码落点**（`_resampled_optimize`）：

- 抽样均值围绕 `mean_returns`（**尊重** `expected_returns` 覆盖），但抽样协方差直接从 `self.returns.cov()` 重算日度样本协方差——**无视 `covariance_method`**（Ledoit-Wolf/OAS 收缩不参与重采样）。这是要知道的口径差异
- 抽样向量经 `mean_override` 参数透传进目标函数，而不是改实例状态——旧实现用 try/finally 改 `self.mean_returns`，与并发读者有竞态（注释引 #1）
- 全部失败时退化为等权 + `success=False`，不抛异常
- `weight_std` 返回逐资产权重的离散度——重采样独有的「权重稳定性」诊断
- 前沿版（`resampled_efficient_frontier`）把每条抽样前沿 `np.interp` 插值到统一收益轴再逐点平均；Sharpe 由平均后的 ret/vol 重算

**边界**：Resampled 是分钟级计算（唯一走异步任务的方法，见第 1 章）；模拟次数 UI 可调 50–2000，默认 200（服务层）。

### 3.3 Mean-CVaR（Rockafellar-Uryasev LP）

**金融直觉**：方差把上涨和下跌波动一视同仁；CVaR（Expected Shortfall）只看最坏 5% 日子的平均亏损——直接优化尾部。问题是如何求解：蒙特卡洛场景法有抽样噪声且不可复现，而 R-U 2000 的经典结果把 CVaR 最小化变成了一个**线性规划**。

**数学形式**：在历史日收益场景 \(r_s\)（S 个场景 × N 个资产）上，决策变量为权重 w、VaR 阈值 α、逐场景尾部超额 \(z_s \geq 0\)：

\[
\min_{w,\alpha,z} \; \alpha + \frac{1}{(1-\beta)\,S}\sum_{s=1}^{S} z_s
\]

\[
\text{s.t.} \quad z_s \geq -r_s^\top w - \alpha \;\; (\forall s), \qquad \sum_i w_i = 1, \qquad z_s \geq 0
\]

可选的目标收益约束以不等式 \(\mu_{daily}^\top w \geq R_{target}/252\) 加入。目标函数的最优值就是组合的日度 CVaR，\(\alpha\) 的最优值即 VaR。

**代码落点**（`_solve_cvar_lp`）：

- 场景矩阵 `R = self.returns.dropna()`——**完全案例**（complete-case）：含 NaN 的行整行丢弃，因为 HiGHS 拒绝非有限输入（KI-003 的根因与修复，见台账）。注意这与均值-方差路径（pandas skipna 容忍 NaN）的有效样本不同
- 约束矩阵 `A_ub = [-R, -1, -I]`，尾部约束逐场景一行
- 报告口径：日度 CVaR/VaR × √252 年化；而 `return/vol/sharpe` 仍是均值-方差口径——同一结果对象里两种口径并存，是有意的（让 CVaR 组合能直接放进均值-方差前沿图）
- LP 不可行抛 `ValueError`，路由层翻译成 422
- 「max-sharpe」模式实际是 **max-STARR**（服务层 `run_cvar`）：前沿上最大化 \((R - r_f)/CVaR\) 的点；CVaR≈0 的行先屏蔽再算比值，防止 inf 取胜

**为什么 LP 优于 MC 场景抽样**：确定性（同输入同输出，呼应可复现性要求）、无抽样误差、求解快。代价是场景集只能是历史样本本身。

### 3.4 LDI 盈余优化（Sharpe-Tint）

**金融直觉**：养老金/家族信托关心的不是资产本身的波动，而是**盈余**（资产 − 负债）的波动。把负债看成一个固定空头，组合优化目标变成对冲负债后的盈余风险。

**数学形式**：负债以比率 \(k = L/A\)（负债现值/可投资资产）进入，负债的收益率为外生估计（均值 \(\mu_L\)、波动 \(\sigma_L\)、与资产的协方差向量 c）：

\[
E(R_S) = w^\top\mu - k\,\mu_L
\]

\[
\mathrm{Var}(R_S) = w^\top\Sigma w - 2k\, w^\top c + k^2 \sigma_L^2
\]

**代码落点**：

- `surplus_performance` 计算上式，方差取 `max(var, 0)` 防数值负值。**盈余 Sharpe 不减无风险利率**——docstring 明说：盈余不是可按 rf 缩放的投资，减了没有经济学意义
- `minimize_surplus_volatility` 最小化 \(w^\top\Sigma w - 2k\,w^\top c\)（\(k^2\sigma_L^2\) 与 w 无关，省略），解析梯度 \(2\Sigma w - 2kc\)。`target_return` 是**不等式**（盈余收益 ≥ 目标，下限语义）——与经典 MVO 前沿的等式目标不同
- 负债的三条输入通道（显式参数 / 画像目标折现 / 退休收入流）与负债统计量的两级估计（中债曲线法优先，久期缩放代理兜底）在服务层 `run_surplus`，细节见第 3、5 章

### 3.5 风险平价 ERC（Spinu 凸规划）

**金融直觉**：等权重不等于等风险——60/40 组合 90% 的风险来自股票。ERC 要求每个资产对组合总风险的贡献相等。

**数学形式**：风险贡献（本方差份额口径）定义为：

\[
RC_i = \frac{w_i\,(\Sigma w)_i}{w^\top \Sigma w}, \qquad \sum_i RC_i = 1
\]

Spinu (2013) 把「所有 \(RC_i = 1/N\)」转化为一个凸规划：

\[
\min_w \; \frac{1}{2} w^\top \Sigma w - \sum_i \ln w_i, \qquad w_i > 0
\]

**代码落点**（`risk_parity`）：

- 解析梯度 \(\Sigma w - 1/w\)，SLSQP 边界 `(1e-10, None)`
- **没有权重和为 1 的约束**——log 障碍项使目标对尺度自平衡，解出后直接归一化 \(w_i / \sum_j w_j\)
- log 障碍天然保证多头（\(w_i \leq 0\) 无定义）——所以**做空在该方法下被禁止**，路由层 422 前置拦截
- 预期收益完全不参与求解；返回的 return/Sharpe 只是展示上下文（用可能被覆盖的均值向量算）
- 求解失败抛 `ValueError`（不是 `success=False`）——与 MVO 路径的失败语义不同，写作/调试时注意

### 3.6 Black-Litterman

**金融直觉**：均值-方差对输入均值极其敏感，且「我认为 A 会涨 8%」这种观点与历史均值混排没有原则性办法。BL 用贝叶斯框架：以市场均衡收益为先验，把投资者观点按置信度混合成后验。

**数学形式与代码落点**（`BlackLittermanOptimizer`，继承 `PortfolioOptimizer`）：

1. **先验**（`implied_equilibrium_returns`）——CAPM 均衡：

   \[
   \Pi = R_f + \delta\,\Sigma w_{mkt}
   \]

   注意这是**总收益口径**（docstring 明示有意为之：与总收益形式的观点 Q 一致、与下游 Sharpe 只减一次 \(R_f\) 一致）；教科书的超额口径 \(\delta\Sigma w_{mkt} = \Pi - R_f\)。市值权重缺省等权，δ 缺省由 \((R_{mkt}-R_f)/\sigma^2_{mkt}\) 估计、退化时兜底 2.5，τ 默认 0.025。`use_prior()` 可把整个先验换成 CME 前视向量——`expected_return_source="cme"` 在 BL 方法下的真实语义就是**换先验**（schema 里「BL 与 cme 不兼容」的字段描述是过期文案，以代码为准）

2. **观点 → 矩阵**（`views.py` 的 `ViewProcessor.generate_P_Q_omega`）：绝对观点（「A 股年化 8%」）在 P 中占一行单点 1；相对观点（「美股跑赢欧股 2%」）多头 +1、空头 −1，Q 为利差。观点不确定度 Ω 用 **Idzorek 置信度闭式**：

   \[
   \omega_{kk} = \left(\frac{1}{c} - 1\right) \cdot P_k^\top \tau \Sigma P_k
   \]

   语义：单观点时被观点组合的后验均值恰好走到先验到观点的 c 比例处。端点钳制：c > 0.99 → 视图方差 ×0.01，c < 0.01 → ×100。docstring 明确记录：Idzorek 原始的组合空间 tilt 标定在此病态（tilt 方向与隐含权重方向不一致），故保留闭式

3. **后验**（`bl_posterior_returns`）——标准 BL：

   \[
   M = \left[(\tau\Sigma)^{-1} + P^\top \Omega^{-1} P\right]^{-1}, \qquad \mu_{BL} = M\left[(\tau\Sigma)^{-1}\Pi + P^\top \Omega^{-1} Q\right], \qquad \Sigma_{BL} = \Sigma + M
   \]

   数值细节：τΣ 先加 \(10^{-8} I\) 抖动再求逆；`inv` 失败退 `pinv`（两层：τΣ/Ω 一层、复合矩阵一层）——极端置信度可使复合矩阵数值秩亏

4. **后验组合**：`bl_maximize_sharpe` / `bl_minimize_volatility` / `bl_efficient_frontier` 用 \(\mu_{BL}\) 与 \(\Sigma_BL\) 重跑 MVO 三件套；波动率一律用后验协方差

**观点诊断**（不参与优化，纯披露）：`detect_relative_cycles` 把相对观点建成有向图跑**迭代版 Tarjan SCC**，成员数 >1 的强连通分量即矛盾循环（A>B 且 B>A），只警告不报错；`divergence_warnings` 在绝对观点离先验 >3σ 时提示后验将大幅倾斜；服务层 `bl_view_impacts` 逐观点披露「这条观点实际挪了多少权重」（先验组合 vs 只加该条观点的 BL 组合的 L1 权重距离——K 条观点 = K+1 次完整求解，不是免费操作）。

## 服务层语义（`optimize_service.py`）

五个 runner 把引擎装配成统一七元组 `(optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra)`。槽位语义因方法而异，是读响应时最容易误解的地方：

| 方法 | `selected` | `max_sharpe` 槽 | `min_vol` 槽 |
|---|---|---|---|
| mvo / resampled | 按 mode 选 | 真实 max-Sharpe | 真实 min-vol |
| mean-cvar | 按 mode 选 | **max-STARR**（(R−rf)/CVaR 最大点） | 全局 min-CVaR |
| risk-parity | 永远 ERC（mode 不适用） | 经典 MVO 组合（**对照基准**） | 同左 |
| surplus | 按 mode 选 | 盈余 Sharpe 最大 | 盈余方差最小 |
| black-litterman | 按 mode 选 | 后验 max-Sharpe | 后验 min-vol |

另外两个服务层设计：

- **组约束只压 `selected`**：客户风险等级上限只约束选中组合，`max_sharpe`/`min_vol` 对照组保持无约束——让读者直观看到约束的成本（`run_mvo` docstring）
- **服务层常量覆盖库默认**：前沿点数 50（库默认 100）、随机组合 1000（库默认 5000）、resampled 前沿 20 点——引用「默认值」时必须说明是哪一层

## 风险约束与指标库

**`risk_constraints.py`**：`ASSET_GROUPS` 四组（equity 4 / bond 6 / alternative 4 / cash 1，恰好覆盖 15 个资产类别 key）；`RISK_LEVEL_CAPS` 五级，**只压 equity（15%→90%）与 alternative（10%→30%）**——债券与现金不设限，保守端的保护由权益/另类的上限隐式实现（模块 docstring 明说是设计，不是缺漏；注意高收益债、EM 债都在 bond 组不受限）。`caps_for_tolerance` 按**中文词干**子串匹配（`"保守型"[:-1]` = 「保守」，双语全标签与裸中文名都能解析），失败抛双语 `ValueError`。

**`risk_metrics.py`**：六个纯函数，全部收日度序列：

- `sharpe_ratio` / `sortino_ratio`：波动或下行偏差为 0 返回 0.0。Sortino 的 MAR=0，下行偏差用**全样本分母 (n−1)** 而非下行样本数（非主流变体，代码注释标明——数值会系统性偏小，与外部工具对比时注意）
- `max_drawdown`：输入是**价格/净值序列**不是收益；返回负百分比 + peak/trough 日期
- `value_at_risk`：historical（分位数）或 parametric（高斯 \(-(\mu + z_\alpha\sigma)\)，含均值项）；返回正数损失幅度，**日度口径**
- `conditional_var`：历史法 VaR 之外的尾部均值；尾部为空回退 VaR 本身
- `compute_all_metrics`：汇总 dict；VaR/CVaR 键名刻意带 `_daily` 后缀（`var_95_daily`/`cvar_95_daily`，注释引 issue #7）——防止与年化指标直接比较。同一代码库内「日度」与「年化 ×√252」两种口径并存，引用任何 CVaR 数字时先确认口径

## 设计决策与取舍

- **为什么 CVaR 走 LP 而其他走 SLSQP？** R-U 形式化后目标与约束全线性，LP 求解器（HiGHS）给出确定性全局最优；MVO/BL/ERC 的目标非线性，SLSQP 是合适工具。LP 还顺带满足了可复现性（P26 后 CVaR 是全引擎最确定性的方法）。
- **为什么 Resampled 平均权重而不是平均前沿？** 权重平均直接给出可执行组合；前沿版另走插值逐点平均（`np.interp`），两条路径分工明确。
- **为什么 BL 先验用总收益口径？** 观点 Q 以总收益输入、下游 Sharpe 只减一次 rf——口径错位会产生一整个 rf 的系统性偏差。
- **为什么组约束只压 selected？** 披露价值：用户能同时看到「约束下最优」和「无约束参照」，约束成本一目了然。
- **为什么 `risk_parity` 失败抛异常而 MVO 返回 success=False？** ERC 无解几乎一定是数据病态（协方差矩阵坏了），静默退化会掩盖数据问题；MVO 的单点失败在前沿扫描里是常态，静默跳过合理。

## 已知近似与边界

- **√252 年化对 7×24 资产系统性低估波动**（BTC）；对股票是行业标准口径。
- **Resampled 的抽样协方差无视 `covariance_method`**——选了 Ledoit-Wolf 收缩，重采样的抽样分布仍用样本协方差（但 MVO 求解本身用的是收缩后的矩阵）。
- **CVaR LP 的场景集是完全案例**——混合交易日历时（含 crypto/A 股）有效场景只剩共同连续交易日，BTC 周末波动与周一缺口收益不进场景（KI-003 取舍）。
- **BL 的 τ=0.025、δ=2.5 兜底都是经验值**；Idzorek 置信度是闭式视图空间版，与原始文献的组合空间标定不同（docstring 记录了取舍理由）。
- **Sortino 下行偏差的全样本分母**是非主流变体，数值系统性偏小。
- **API 路径不可复现**：服务层不传 seed，random_portfolios 与 resampled 每次请求有细微差异。
- **`ViewProcessor.validate_views` 生产无人调用**（仅测试用）——置信度范围实际由 API schema 的 Field 校验拦截，未知资产由 `generate_P_Q_omega` 拦。

## 自检问题

1. 引擎的年化约定是什么？对 BTC-USD 意味着什么系统性偏差？
2. `maximize_sharpe` 与 `minimize_volatility` 在解析梯度上有无差异？零波动时两处分别怎么处理？
3. Resampled 重采样的抽样分布是什么？为什么协方差项要除以 T？它尊重/无视 `__init__` 的哪些输入？
4. Mean-CVaR 的 LP 决策变量有哪些？`A_ub` 怎么构造？为什么场景矩阵要先 `dropna()`？
5. 盈余优化里 k、μ_L、c 各是什么？盈余 Sharpe 为什么不减 rf？它的目标约束与 MVO 前沿的等式约束有何不同？
6. ERC 的目标函数为什么不需要权重和为 1 的约束？为什么不能做空？
7. BL 先验的总收益口径与教科书超额口径差什么？`use_prior` 在 CME 模式下替换了什么？
8. `run_cvar` 的 max_sharpe 槽位实际是什么？`run_risk_parity` 的两个对照槽位填的是什么？
9. `risk_metrics` 里 VaR/CVaR 是什么口径？和 `minimize_cvar` 报告的年化 CVaR 差一个什么因子？

## 代码入口清单（推荐阅读顺序）

1. `src/portfolio/optimizer.py` 的 `__init__` 与 `portfolio_performance`——共享地基
2. 同文件 `minimize_volatility` / `maximize_sharpe` / `efficient_frontier`——MVO 主线
3. 同文件 `_resampled_optimize`——重采样
4. 同文件 `_solve_cvar_lp` / `minimize_cvar`——CVaR LP
5. 同文件 `surplus_performance` / `minimize_surplus_volatility`——LDI
6. 同文件 `risk_contributions` / `risk_parity`——ERC
7. 同文件 `BlackLittermanOptimizer`（`implied_equilibrium_returns` → `bl_posterior_returns`）+ `src/portfolio/views.py`——BL 全链
8. `src/portfolio/optimize_service.py`——服务层槽位语义
9. `src/portfolio/risk_constraints.py`、`src/portfolio/risk_metrics.py`——两个配套小库
