# 08 · Model Validation 与研究工作流

## 目的与边界

一个优化器可以通过全部单元测试，也可以为一段历史生成漂亮的净值曲线。这些结果分别回答实现和历史表现的问题；要判断模型是否值得继续研究，还需要约束当时能看到的信息，观察输入扰动、数据缺失和模型假设改变后，结论如何变化。

| 层次 | 回答的问题 | 本仓库入口 |
|---|---|---|
| Unit / integration tests | 公式、接口、失败路径是否按约定实现？ | `tests/` |
| Historical backtest | 给定固定目标组合，过去表现如何？ | `src/portfolio/backtest.py` |
| Model validation | 在明确的信息边界、样本和假设下，模型是否稳健、可复现、可解释？ | `validation/` |

`tests/` 检查研究工具是否执行了约定，`validation/` 产出可解释的研究证据。通过测试不能代替模型验证；一次验证也不能证明未来必然优越。退休模拟尤其是条件情景比较，不具备组合 walk-forward 的逐期历史预测含义。

本章串起 [#59](https://github.com/Michelia-L/AI-WealthPilot/issues/59) 的五条 workstream。精确参数、默认阈值、输出字段和完整可运行示例由各模块 README 维护；本章只解释跨模块的方法、数据边界与设计取舍。生产量化模型先读 [第 02 章](02-quant-engine.md)，CME 输入先读 [第 03 章](03-data-pipeline-cme.md)，测试与 CI 见 [第 07 章](07-quality-engineering.md)。

## 整体架构 · 共享模型，独立研究边界

![五条 validation workstream、保存结果的数据流与 production 复用边界](../diagrams/model-validation.svg)

| Workstream | 研究层增加什么 | 复用什么 |
|---|---|---|
| [#60 · Portfolio Walk-Forward](https://github.com/Michelia-L/AI-WealthPilot/issues/60) | 历史切片、资格判断、OOS 路径与失败记录 | `PortfolioOptimizer` 的生产优化方法 |
| [#61 · Costs / Turnover / Robustness](https://github.com/Michelia-L/AI-WealthPilot/issues/61) | 成本后处理、集中度、权重稳定性、单因素敏感性 | 已保存的 walk-forward 结果；敏感性重跑同一 `evaluate` |
| [#62 · Risk / Regimes / Stress](https://github.com/Michelia-L/AI-WealthPilot/issues/62) | 风险预测校准、事后分组、历史与合成压力 | 决策时风险快照、OOS 路径、生产风险函数 |
| [#63 · CME Vintage / Calibration](https://github.com/Michelia-L/AI-WealthPilot/issues/63) | 带来源证据的不可变预测归档、到期误差与混合参数实验 | `CMEReport` 和生产 `blend_assumption` |
| [#64 · Retirement Validation](https://github.com/Michelia-L/AI-WealthPilot/issues/64) | 替代收益过程、支出诊断、敏感性、收敛与压力实验 | 生产积累计算与 `distribution_from_growth` 现金流规则 |

Portfolio、CME、retirement 是独立的离线入口。CME 归档不自动写入 live cache，也不自动注入历史 optimizer；退休假设可以记录 CME provenance，但不会据此自动取数。研究编排因此可以变化，而生产公式和输入证据仍能分别追踪。

## Strict no-look-ahead · 先界定信息，再运行模型

### 决策时间、训练窗口与持有窗口

Portfolio 的 `as_of=t` 是决策边界。训练数据必须停在 `t`，持有期从 `t` 之后开始；rolling 与 expanding 的差异只改变训练左边界，不改变“未来数据不能进入当前决策”的原则。月末遇非交易日时只能使用当时已经存在的观测，不能借最终数据集反推当天可用资产。

`evaluate` 先切历史，再做 point-in-time eligibility。各策略随后选择自己的 fitting sample：Equal Weight 不需要协方差，Inverse Vol 可以按资产使用各自有效观测，生产 optimizer 则需要参与资产的联合样本。精确资格阈值和样本计数规则见 [portfolio README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/README.md)。

若先对完整资产面板做全局 `dropna()`，不相关资产的缺数可能错误地排除本来可用的 baseline。研究层因此把“当时可选资产”和“某策略实际用于估计的样本”分开记录。

### 用 future sentinel 验证信息边界

一种直接检查是改写某决策日之后的数据，再比较该日及更早的权重、资格判断和风险快照。它们应保持不变；后续 realized return、误差和完整输入 hash 可以变化。

现有 [test_walk_forward.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/tests/test_walk_forward.py) 与 [test_cme_validation.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/tests/test_cme_validation.py) 都包含这类 future-sentinel 检查。新增研究适配器应沿用相同思路，并覆盖自己的辅助输入。

`PortfolioStrategy.allocate(history, as_of, config)` 收到的是受限历史副本，但普通 Python 代码仍可能通过闭包或 provider 越过边界。框架不是安全沙箱；无风险利率、历史 views、宏观数据和其他外部假设仍需由调用方提供当时可用的证据。

### Ex-ante forecast 与 ex-post analysis label

配权使用的输入、协方差和风险预测属于 ex-ante 证据。持有期结束后生成的 bull/bear、利率或通胀标签属于 ex-post analysis，用来解释结果所处环境，不能反向进入 allocator。

同理，今天选取的一段历史样本可以用于退休情景比较，但它不能自动支持“过去某日已经能够做出同一预测”的主张。后者需要 point-in-time 的样本与假设证据。

### Failure-as-unknown · 缺口不能伪装成收益

逐期分配失败、资产不可用或持有期数据不足，都要保留状态与原因。成功配出的权重在后续估值失败时仍被保留，以区分模型问题和数据问题。

失败窗口的收益是未知，而不是 0%。若用 0% 填补，就隐含引入一个未经定义的现金策略；若删掉失败期，则按评估是否成功选择了样本。累计 NAV 因此不会在发生未知缺口后自动恢复。精确序列化形式与完整性规则由 portfolio README 和测试维护。

## Portfolio validation · 先建立可比较的参照

复杂 optimizer 必须和简单 baseline 使用同一 OOS 协议比较。只比较多个 optimizer，无法判断估计与求解复杂度是否真正增加了稳健性，还是只增加了换手、集中度和输入敏感性。

当前研究层包含 Equal Weight、显式 Static / 60-40、Inverse Vol，以及 MVO、MinVol、ERC、Mean-CVaR、resampled MVO 等生产适配器。不同策略依赖不同估计量，因此“训练区间有多少日期”和“这个策略实际用了多少观测”必须分开理解。

### Stitched OOS NAV 与漂移权重

每个持有窗口从决策目标权重开始，窗口内资产数量固定、权重随价格漂移；下个决策再按新目标重置。研究层把不重叠持有窗口的日收益拼成 stitched OOS 路径，并保存期末漂移权重。

期末漂移权重很重要：真实再平衡成本取决于“当前漂移组合到下一目标组合”的交易，而不是只看两个目标权重的差。具体字段、持有/再平衡约束和序列化契约见 [portfolio README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/README.md)。

### Costs / turnover / robustness

[costs.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/costs.py) 在已保存的 gross OOS 路径上施加比例成本，不重拟合策略，也不改变原目标。默认 turnover 使用相邻漂移权重与目标权重的距离；旧结果缺少必要证据时不会静默切换为更粗的近似。

[robustness.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/robustness.py) 关注集中度和权重稳定性，[sensitivity.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/sensitivity.py) 则沿相同 OOS 协议单独改变 expected return、covariance estimator 或 lookback 等因素。不可用的实验记录为 skipped，而不是“零敏感性”。完整参数矩阵见 [ROBUSTNESS.md](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/ROBUSTNESS.md)。

跨策略比较还会检查输入快照、universe、OOS 日期和研究协议是否相容；若某条候选路径不完整，不能只给幸存策略排榜。

## Risk calibration / regimes / stress

### 保存决策时的风险预测

[forecasts.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/forecasts.py) 保存决策时可见的风险快照，包括有序资产、协方差、估计器和训练证据。生产 optimizer 实际使用的协方差与仅用于报告的协方差会被区分，避免把事后补算的统计量伪装成当时的决策输入。

简单 baseline 可以拥有 reporting-only 风险估计；样本不足只让风险预测不可用，不会推翻已经有效的配权。旧归档若没有决策快照，报告保持 unavailable，而不是使用完整历史事后重建。

### Predicted vs realized

[risk_calibration.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/risk_calibration.py) 将决策时预测与下一持有期 realized return 配对，报告 volatility error、VaR exceedance 和 CVaR tail diagnostics。Bias、MAE、RMSE 分别回答有符号偏差、平均误差和大误差敏感度；样本门槛、尾部定义和输出字段见 [RISK_VALIDATION.md](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/RISK_VALIDATION.md)。

这些结果是描述性的模型诊断，不构成独立性检验、监管 VaR 认证或 regulatory model approval。

### Regimes 保留时间连续性

[regimes.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/regimes.py) 将 benchmark、利率和通胀等带来源信息的分析序列转换成事后标签。宏观观测缺失或不满足时间要求时标签为 unknown。

最大回撤按 contiguous regime episode 计算；被其他 regime 分隔的两个 bear 片段不能直接拼成一条连续净值曲线。Conditional CAGR 只描述被选择观测，不等价于一条现实可执行的连续策略路径。

### Historical stress 与 transparent synthetic shocks

[stress.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/stress.py) 的 historical stress 在已保存 OOS 路径上截取真实事件窗口；synthetic stress 则对已保存目标和显式暴露施加透明冲击，不重新优化，也不给场景赋予概率。

久期、spread duration 等必要暴露由调用方提供。缺少证据时结果保持未知，不通过默认值补成看似完整的压力结果。

## CME vintage validation · 保存当时的预测与来源

### Vintage 必须成为一等对象

CME 同时依赖历史、forward、implied volatility 与宏观假设。只保存最终 blended 数字不足以回答“预测何时可用、使用了什么输入、后来是否被修订”。

`CMEVintage` 因此分开记录 forecast `as_of`、原报告日期、实际生成/重建时间、模型版本、代码版本和 source evidence。`observed` 表示当时真实保存的预测；`reconstructed` 表示后来依据可证明的历史信息重建的决策。两者不能混为同一种证据。

`SourceRecord` 区分观测、可用和获取时间，并记录 provider/proxy、quality、revision policy 和可选 source hash。Strict 模式 fail closed：来源时间、修订状态或关键构件无法证明时，记录可以保留，但不能自动升级成 strict evidence。具体规则由 [vintages.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/cme/vintages.py) 的 `CMEVintage.strict_issues` 和 [CME README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/cme/README.md) 维护。

### Immutable content-addressed archive

`VintageStore` 以 canonical JSON 的 SHA-256 标识内容，相同内容重复保存幂等，证据变化产生新的 ID；加载时重新验证 hash。Content hash 能发现意外修改，但不是签名或外部认证，原始来源快照和备份仍需单独保存。

Live API / cache 当前没有自动捕获研究归档的流程，因此不能把今天的 stale/live cache 自动回填为过去的 observed vintage。

### 到期后才计算误差

[realized.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/cme/realized.py) 要求明确 realized-return 的资产映射、币种、FX 和覆盖区间。只有 horizon 到期后才能计算该预测误差；输入里即使误含未来数据，也不能让未到期预测提前成熟。

[calibration.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/cme/calibration.py) 比较归档 forecast 与 realized return、volatility 和 correlation。汇总会按模型、vintage 类型和配置等证据维度分组，避免把不可比预测混在一起。精确 horizon、最小样本和误差字段由 CME README 维护。

### Tau / omega counterfactual blending

[blending.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/cme/blending.py) 复用生产 [cme_blending.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/src/portfolio/cme_blending.py) 的 `blend_assumption`，只在归档构件上做 tau / omega 反事实实验，不修改原 vintage，也不自动调生产参数。

缺少替代构件时继续归入 historical fallback，而不是拿今天的 forward input 补进历史。这样实验回答的是“若当时用另一组混合参数会怎样”，而不是“用今天知道的东西改写过去会怎样”。

## Retirement model validation · 固定现金流规则，改变收益过程

### Production GBM baseline 与共同记账规则

[harness.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/retirement/harness.py) 生成年度 gross-return paths，再交给生产 `MonteCarloSimulator.simulate` 和 [retirement_paths.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/src/portfolio/retirement_paths.py) 的 `distribution_from_growth`。研究层不重写积累和退休现金流逻辑。

生产 GBM 使用 `exp(mu - sigma**2 / 2 + sigma * Z)`。退休阶段对 return / volatility 的保守缩放是当前生产 heuristic，而不是从新资产组合推导出的参数；验证层保留并披露这一约定。

Fixed 与 Guardrails 也沿用生产现有时序，包括收益、通胀和年末提取的先后关系。这里的重要原则不是让两个规则“看起来更一致”，而是保证比较使用同一套生产现金流记账。

### IID、moving-block bootstrap 与矩匹配

[bootstrap.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/retirement/bootstrap.py) 接受完整组合的历史 total-return series，不自动配权、不补缺、不换汇。IID 重采样单个观测；moving-block bootstrap 重采样连续块，以保留部分局部依赖。

`empirical` 直接比较历史经验分布与生产 GBM；`matched_gbm_moments` 先把历史 log returns 映射到目标边际矩，再保留样本形状和块顺序，用于更聚焦地观察分布形状和依赖差异。块长度、频率约束和输入 contract 见 [retirement README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/retirement/README.md)。

### Sequence-of-returns 与 spending trade-off

`sequence_experiment` 通过重排相同收益集合中的亏损位置，展示现金流存在时的 sequence-of-returns risk。没有现金流时相同复合收益可以得到相同终值；有持续提取时，亏损发生顺序会改变可持续性。

`compare_models` 在同一收益引擎内尽量使用相同 draws 比较 fixed / guardrails，同时观察 survival、实际支出、shortfall、cuts / increases。更高存续率可能以更低支出为代价，因此不能只看一个“成功率”。

### 参数、压力与两类不确定性

[experiments.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/retirement/experiments.py) 提供 return / volatility、通胀、退休参数和规划期限的 sensitivity，以及 deterministic stress、simulation-count convergence 与跨 seed stability。

增大模拟数可以减少给定模型下的 Monte Carlo sampling uncertainty，但不能消除参数估计、历史样本选择和 model uncertainty。GBM 与 bootstrap 即使使用相同 seed，也不代表两种机制的路径逐一配对。完整实验矩阵和默认值由 retirement README 维护。

## Reproducibility / provenance · 保存数字的生成条件

跨模块研究证据至少应能够回答以下问题；不同对象不要求拥有同名字段。

| 信息 | 研究证据需要回答什么 |
|---|---|
| Decision boundary / horizon | 何时决策，使用哪个训练、持有、到期或退休范围？ |
| Config / strategy / estimator | universe、约束、成本、分配方法和估计器是什么？ |
| Model / code version | 模型假设属于哪个版本，运行的是哪个 commit / build？ |
| Seed / numerical environment | 随机性和数值环境是否可追踪？ |
| Source / source dates | 数据何时观测、可用、获取，币种、FX、proxy 如何处理？ |
| Quality / revision policy | 使用原始 vintage、修订历史、cached / stale / fallback 还是 synthetic 数据？ |
| Historical sample | 完整输入或可重建输入是否保存？Hash 本身不能重建数据 |
| Stress / regime definition | 标签阈值、事件窗口、暴露和压力幅度是否归档？ |
| Diagnostics / failures | 缺失、失败、估计与求解诊断是否与结果一起保存？ |

Portfolio `ValidationRun.to_json()` 保存配置、逐次权重、诊断和路径，但调用方仍要保留输入快照。CME archive 保存预测构件与来源描述，source hash 指向的原始证据仍须另存。Retirement 保存历史输入、phase seeds 和运行摘要；若要完整 replay，也应保存足够的收益路径证据。

同样的输入、seed 与数值环境应产生可比较的研究结果，但运行时间戳会变化，跨平台求解器也可能有浮点差异。归档不能包含凭证、原始敏感 provider response 或真实客户秘密。

## 最小离线实验 · 从同一协议开始

完整、可复制的 synthetic examples 分别维护在 [portfolio README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/README.md)、[CME README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/cme/README.md) 和 [retirement README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/retirement/README.md)。Guide 只保留最短调用路径，避免复制字段级 contract。

例如 Portfolio 的最小离线比较可以从同一份 synthetic returns 开始：

```python
from dataclasses import replace

from validation.portfolio import StrategySpec, WalkForwardConfig, evaluate

config = WalkForwardConfig(
    start_date="2019-12-31",
    end_date="2020-06-30",
    universe=("SPY", "AGG"),
    data_source="synthetic fixture",
)
runs = {
    name: evaluate(returns, replace(config, strategy=StrategySpec(name)))
    for name in ("equal_weight", "mvo")
}
```

这里的 `returns` 必须由调用方显式构造或从离线 fixture 读取。随后沿 `compare_runs` → `analyze_risk` / `run_sensitivity` 保存 JSON 与输入快照。CME 的推荐路径是 `CMEVintage.from_report` → `VintageStore` → `calibrate` / `evaluate_blending`；Retirement 则是 `HistoricalReturns` + `RetirementScenario` → `compare_models` → sensitivity / stress / convergence。三个入口都可以只使用 synthetic/static fixtures，不依赖 live provider。

## 已知近似与边界

| 边界 | 当前研究结果不能替代什么 |
|---|---|
| 历史样本选择 | 不能修复调用方 universe 的 survivorship bias、事后筛选、退市缺失或错误 revision history |
| 实施成本 | 比例成本不覆盖真实 execution impact、spread、税费 / tax lots、流动性与已执行交易 |
| 风险校准 | VaR / CVaR、regime 和 stress 不构成正式监管认证、宏观预测或事件概率 |
| CME 历史证据 | 尚无自动历史重建 loader 或 live 归档调度；合成重建不能替代真实预测质量证据 |
| 退休模型 | 年度现金流与固定规划终龄不覆盖 stochastic mortality、税务、养老金、医疗及完整家庭负债模型 |
| 结论外推 | OOS、稳定性或较低误差仍依赖样本与协议，不能证明未来策略必然优越，也不构成投资建议审批 |

## 自检问题

1. 修改下一持有期收益后，哪些权重 / 预测必须不变，哪些 realized error 可以变化？
2. 为什么简单 baseline 的分配可以不需要估计样本，而风险报告仍可能需要联合历史？
3. 某一期失败后仍有局部收益，为什么不能把缺口补成 0% 或删除失败期后继续排榜？
4. 周一捕获一份基于周五价格的 CME，forecast `as_of`、report date 和 source availability 应如何区分？
5. 两段不连续 bear 期间的回撤为什么要在各自 episode 内计算？
6. Guardrails 的存续率提高时，应同时查看哪些支出指标？增加模拟数能消除模型差异吗？

## 代码入口与推荐阅读路径

| 阅读目的 | 路径与关键符号 |
|---|---|
| 理解配权和估值边界 | [portfolio README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/README.md) → [walk_forward.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/walk_forward.py) `evaluate` → [strategies.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/strategies.py) `StrategySpec.allocate` |
| 比较成本与输入稳定性 | [ROBUSTNESS.md](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/ROBUSTNESS.md) → `costs.py` / `sensitivity.py` |
| 查看风险报告组合方式 | [RISK_VALIDATION.md](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/RISK_VALIDATION.md) → [risk_report.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/portfolio/risk_report.py) `analyze_risk` |
| 从预测证据走向到期评估 | [CME README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/cme/README.md) → [vintages.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/cme/vintages.py) `CMEVintage` / `VintageStore` → `calibration.py` |
| 比较退休收益过程与支出规则 | [retirement README](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/retirement/README.md) → [harness.py](https://github.com/Michelia-L/AI-WealthPilot/blob/main/validation/retirement/harness.py) `run_retirement` → `experiments.py` |

新增研究功能的 PR 应检查是否改变本章的信息边界、模型假设或跨模块工作流。模块 README 维护精确 contract，本章维护系统解释；大型 workstream 的设计依据应能从 guide 找到，避免只留在 issue / PR 历史中。
