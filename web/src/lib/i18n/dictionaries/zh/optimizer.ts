/** optimizer namespace — populated by the localization pass (phase 22). */
export const optimizer = {
  title: "组合优化器",
  description:
    "均值-方差优化（MVO）、Michaud 重采样前沿、Black-Litterman 贝叶斯配置、Mean-CVaR 尾部风险优化、LDI 盈余优化与风险平价（ERC），求解有效前沿上的最优资产组合。",
  /** ApiOffline `resource` prop shown when the asset universe cannot load. */
  assetUniverse: "优化资产宇宙",

  // ---- workspace form ----
  assetClassesLabel: (n: number) => `资产类别 · 已选 ${n}（至少 2 个）`,
  historyWindow: "历史窗口",
  methodLabel: "优化方法",
  objectiveLabel: "目标",
  riskFreeRate: "无风险利率",
  rfAuto: "自动获取",
  rfManualAria: "手动无风险利率（%）",
  methodMvo: "传统 MVO",
  methodResampled: "重采样 MVO",
  modeMaxSharpe: "最大夏普",
  modeMinVol: "最小波动",
  allowShort: "允许做空",
  simulations: "模拟次数",
  cvarConfidence: "CVaR 置信水平",
  cvarModeHint: "最大夏普 → 最大化 (收益−无风险利率)/CVaR；最小波动 → 最小化 CVaR",
  expectedReturnSource: "预期收益来源",
  sourceSample: "历史样本",
  sourceCme: "CME 预期",
  cmeBlHint: "BL 将以 CME 为先验",
  cmeFallbackHint: (names: string) =>
    `以下资产未被 CME 覆盖，已回退为历史样本均值：${names}`,
  cmeFallbackHintBl: (names: string) =>
    `以下资产未被 CME 覆盖，先验回退为均衡收益：${names}`,
  clientRiskConstraint: (name: string) => `客户风险约束（${name}）`,
  mvoOnlyHint: "仅传统 MVO 生效",
  selectClientHint: "在侧边栏选择客户后，可将其风险等级注入为权重约束",
  run: "运行优化",
  running: "优化计算中…",
  progressResampled: "重采样任务已创建，等待进度…",
  progressSync: "正在获取行情并求解…",
  emptyTitle: "配置参数并开始优化",
  emptyHint: "至少选择 2 个资产类别；提交后将展示有效前沿、配置权重与关键指标。",

  // ---- workspace errors ----
  progressUnavailable: "无法接收任务进度",
  optimizeFailed: "优化失败",
  streamEnded: "任务流意外结束（服务可能已重启，请重试）",
  createTaskFailed: (status: number) => `创建任务失败（HTTP ${status}）`,
  requestFailed: (status: number) => `请求失败（HTTP ${status}）`,

  // ---- Black-Litterman config ----
  blConfig: "Black-Litterman 配置",
  blTau: "τ（不确定性缩放）",
  blDelta: "δ（风险厌恶系数）",
  marketWeights: "基准权重",
  equalWeight: "等权（1/N）",
  customWeight: "自定义",
  marketWeightAria: (name: string) => `${name} 基准权重（%）`,
  investorViews: (n: number) => `投资者观点（${n}）`,
  addView: "添加观点",
  viewsEmptyHint:
    "Black-Litterman 需要至少一条观点。绝对观点：看多某资产至目标收益；相对观点：A 相对 B 的超额收益。",
  viewTypeAria: "观点类型",
  viewAbsolute: "绝对",
  viewRelative: "相对",
  longAssetAria: "多头资产",
  shortAssetAria: "空头资产",
  outperforms: "跑赢",
  expectedReturn: "预期收益",
  excessReturn: "超额",
  viewReturnAria: "观点收益（%）",
  confidence: "置信度",
  deleteViewAria: "删除观点",

  // ---- Surplus (LDI) config ----
  methodSurplus: "盈余优化 (LDI)",
  surplusConfig: "盈余优化（LDI）配置",
  surplusSource: "负债来源",
  surplusSourceManual: "手动输入",
  surplusSourceProfile: "客户画像推导",
  surplusProfileHint: (name: string) =>
    `负债由客户「${name}」的投资目标折现推导（资产基数 = 可投资资产）`,
  surplusNoClientHint: "在侧边栏选择客户后，可由其投资目标自动推导负债",
  surplusRatio: "负债比率（L/A）",
  surplusDuration: "负债久期",
  durationYears: (v: number) => `${v} 年`,
  surplusProxy: "对冲代理",
  surplusGrowth: "负债增长率",
  growthInflation: "通胀联动",
  growthRiskFree: "无风险利率",
  growthCustom: "自定义",
  surplusCustomGrowthAria: "自定义负债增长率（%）",
  surplusInflationSegment: "通胀人群",
  surplusPresetStandard: "标准",
  surplusPresetElderly: "老年",
  surplusPresetLuxury: "奢华",
  surplusAutoPresetHint: "画像通道按客户年龄自动选择通胀人群（≥60 岁为老年）",
  surplusSourceRetirement: "退休收入流",
  yearsToRetirement: "距退休年数",
  distributionYears: "支取年数",
  annualIncome: "退休年收入（今日购买力）",
  assetValueLabel: "资产基数",
  surplusProfileBaseHint: "资产基数与通胀人群取自选中客户画像",
  surplusAssumptionHint:
    "负债现值按无风险利率折现，经久期缩放债券代理建模（近似有效久期：AGG 6 年、TLT 17 年、TIP 7 年）；退休收入流按通胀增长率逐年放大。以上为简化假设，非真实收益率曲线定价。",

  // ---- Risk parity (ERC) ----
  methodRiskParity: "风险平价 (ERC)",
  rpModeHint: "风险平价与预期收益无关，目标不适用",
  rpShortHint: "仅多头",
  colRiskContribution: "风险贡献",
  rpBenchmarkHint: "最大夏普 / 最小波动组合为经典 MVO 基准，供与 ERC 组合对照。",

  // ---- results ----
  groupEquity: "权益",
  groupBond: "固收",
  groupAlternative: "另类",
  groupCash: "现金",
  constraintsPrefix: "已按 ",
  constraintsSuffix: (level: string) => ` 的风险等级（${level}）注入权重约束`,
  benchmarksUnconstrained: "对照组（最大夏普 / 最小波动）未施加约束",
  annReturn: "年化收益",
  annVolatility: "年化波动",
  sharpeRatio: "夏普比率",
  cvarLabel: (conf: number) =>
    `${Math.round(conf * 100)}% CVaR（年化预期尾部损失）`,
  fundingRatio: "资金充足率（A/L）",
  colAsset: "资产",
  colAllocation: "配置权重",
  colWeightStd: "权重波动 σ",
  colEquilibrium: "均衡收益",
  colPriorCme: "先验 (CME)",
  colPosterior: "后验收益",
  blImpacts: (items: string) => `观点影响力（对后验组合的权重偏移）：${items}`,
  blWeightsEqual: "均衡权重：等权",
  blWeightsAum: "均衡权重：ETF 规模近似",
  blWeightsCustom: "均衡权重：自定义",
  currentSelected: "当前选中",
  returnLabel: "收益",
  volLabel: "波动",
  sharpeLabel: "夏普",
  paramsSummary: (p: {
    period: string;
    tradingDays: number;
    riskFreeRate: string;
    allowShort: boolean;
    nSimulations: number | null;
  }) =>
    `参数：${p.period} 窗口 · ${p.tradingDays} 个交易日 · 无风险利率 ${p.riskFreeRate} · ${
      p.allowShort ? "允许做空" : "仅多头"
    }${p.nSimulations ? ` · ${p.nSimulations} 次重采样` : ""}`,
  surplusAssumptions: (p: {
    source: string;
    ratio: string;
    duration: string;
    growth: string;
    discount: string;
    discountSource: string;
    sigmaSource: string;
    horizon: string | null;
    proxy: string;
  }) =>
    `LDI 假设：${p.source} · 负债比率 L/A=${p.ratio} · 久期 ${p.duration} · 折现率 ${p.discount}（${p.discountSource}） · 漂移 ${p.growth}${p.horizon ? ` · 负债期限 ${p.horizon}` : ""} · σ 来源 ${p.sigmaSource} · 对冲代理 ${p.proxy}`,
  discountSourceCurve: "中债国债收益率曲线",
  discountSourceFlat: "统一无风险利率",
  sigmaSourceCurve: "中债曲线",
  sigmaSourceProxy: "债券代理",

  // ---- backtest ----
  backtestTitle: "组合回测",
  backtestSubtitle: "用历史验证这组权重（月初再平衡）",
  backtestRun: "回测该组合",
  backtestRerun: "重新回测",
  backtestRunning: "回测计算中…",
  backtestFetching: "正在拉取历史行情并模拟净值…",
  backtestFailed: (status: number) => `回测失败（HTTP ${status}）`,
};
