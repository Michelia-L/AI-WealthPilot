/** market namespace — populated by the localization pass (phase 22). */
export const market = {
  title: "市场仪表盘",
  description: "实时行情、跨资产相关性与资本市场预期（CME）。",
  footerDisclaimer:
    "数据来源：Yahoo Finance（yfinance），实时行情缓存 5 分钟。量化输出仅供参考，不构成投资建议。",
  /** resource props for the shared <ApiOffline> panel (rendered mid-sentence). */
  offlineUniverse: "资产宇宙元数据",
  offlineAnalytics: "分析数据",
  offlineQuotes: "行情数据",
  offlineCme: "资本市场预期（CME）",
  snapshotTitle: "市场速览",
  breadthUp: (n: number) => `上涨 ${n}`,
  breadthDown: (n: number) => `下跌 ${n}`,
  breadthFlat: (n: number) => `持平 ${n}`,
  breadthBest: "领涨",
  breadthWorst: "领跌",
  /** VIX 恐慌等级徽章（点位分级）。 */
  vixComplacent: "极度平静", // < 12
  vixCalm: "平静", // 12–17
  vixElevated: "警惕", // 17–25
  vixFear: "恐慌", // 25–35
  vixExtremeFear: "极度恐慌", // ≥ 35
  cmeTitle: "资本市场预期",
  cmeMeta: (
    asOf: string,
    riskFreeRate: string,
    source: string,
    lookbackYears: number
  ) =>
    `数据截至 ${asOf} · 无风险利率 ${riskFreeRate}（${source}）· 回溯 ${lookbackYears} 年`,
  tabPrice: "价格走势",
  tabCorrelation: "资产相关性",
  tabStats: "风险统计",
  normalizeToggle: "基准归一化（Base = 100）",
  correlationEmpty: "至少需要 2 个资产才能计算相关性矩阵。",
  corrGuideTitle: "解读",
  corrGuideSubtitle: "分散化分析",
  corrRedLabel: "红 (+1.0)",
  corrRedDesc: "：高度正相关，资产同涨同跌。",
  corrBlueLabel: "蓝 (−1.0)",
  corrBlueDesc: "：高度负相关，优秀的对冲组合。",
  corrWhiteLabel: "白 (0.0)",
  corrWhiteDesc: "：不相关，纯粹的分散化收益。",
  corrTip: "提示：用低相关性的资产构建组合，可以最大化夏普比率。",
  thAsset: "资产",
  thAssetClass: "资产类别",
  thAnnReturn: "年化收益",
  thAnnVol: "年化波动",
  thExpectedReturn: "预期收益",
  thForwardReturn: "前瞻收益",
  thBlendedVol: "混合波动 (IV)",
  thSharpe: "夏普",
  thMaxDrawdown: "最大回撤",
  thDailyVar: "日 VaR (95%)",
  thVolRegime: "波动状态",
  /** 风险统计表列头排序（点击循环：升序 → 降序 → 默认顺序）。 */
  sortAsc: "按此列升序",
  sortDesc: "按此列降序",
  sortReset: "恢复默认顺序",
};
