/** optimizer namespace — populated by the localization pass (phase 22). */
export const optimizer = {
  title: "组合优化器",
  description:
    "均值-方差优化（MVO）、Michaud 重采样前沿与 Black-Litterman 贝叶斯配置，求解有效前沿上的最优资产组合。",
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
  marketWeights: "市值权重",
  equalWeight: "等权（1/N）",
  customWeight: "自定义",
  marketWeightAria: (name: string) => `${name} 市值权重（%）`,
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
  colAsset: "资产",
  colAllocation: "配置权重",
  colWeightStd: "权重波动 σ",
  colEquilibrium: "均衡收益",
  colPosterior: "后验收益",
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

  // ---- backtest ----
  backtestTitle: "组合回测",
  backtestSubtitle: "用历史验证这组权重（月初再平衡）",
  backtestRun: "回测该组合",
  backtestRerun: "重新回测",
  backtestRunning: "回测计算中…",
  backtestFetching: "正在拉取历史行情并模拟净值…",
  backtestFailed: (status: number) => `回测失败（HTTP ${status}）`,
};
