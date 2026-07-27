/** profileDetail namespace — /profiles/[id] client hub page and hub actions. */
export const profileDetail = {
  title: "客户枢纽",
  invalidId: "无效的客户编号",
  backToList: "返回客户列表",
  detailResource: "客户详情（客户可能不存在，或 API 离线）",
  headerDescription: (
    age: number,
    marital: string,
    dependents: number,
    updated: string
  ) => `${age} 岁 · ${marital} · 抚养/赡养 ${dependents} 人 · 更新于 ${updated}`,
  editProfile: "编辑画像",
  // Hub actions
  currentClient: "当前客户",
  setAsCurrentClient: "设为当前客户",
  generateReport: "生成建议书",
  generateIps: "生成 IPS",
  // Key metrics
  netWorth: "净资产",
  savingsRate: "年储蓄率",
  annualSavingsHint: (amount: string) => `年储蓄 ${amount}`,
  debtToAssetRatio: "负债资产比",
  finalRiskScore: "综合风险分",
  finalRiskScoreHint: "min（能力, 意愿） · 满分 5",
  // Financial situation panel
  financials: "财务状况",
  annualIncome: "年收入",
  annualExpenses: "年支出",
  investableAssets: "可投资资产",
  totalLiabilities: "总负债",
  emergencyFund: "应急基金",
  // Risk profile panel
  riskProfile: "风险画像",
  abilityScoreLabel: "风险承受能力（客观）",
  willingnessScoreLabel: "风险承受意愿（主观）",
  // Goals panel
  goals: "投资目标",
  noGoals: "尚未设定投资目标。",
  yearsLater: (n: number) => `${n} 年后`,
  priorityBadge: (v: string): string =>
    v === "high" ? "高优先" : v === "low" ? "低优先" : "中优先",
  // Constraints panel
  constraints: "约束与偏好",
  timeHorizon: "投资期限",
  horizonValue: (years: number, multiStage: boolean) =>
    `${years} 年${multiStage ? "（多阶段）" : ""}`,
  liquidityNeeds: "流动性需求",
  taxStatus: "税务状态",
  esgPreference: "ESG 偏好",
  esgYes: "是",
  esgNo: "否",
  sectorRestrictions: "行业限制",
  none: "无",
  // Recommendation section
  recommendation: "推荐配置",
  expectedReturn: "预期收益",
  expectedVolatility: "预期波动",
  sharpeRatio: "夏普比率",
  // Deliverables panel
  deliverables: "交付物",
  deliverableCount: (n: number) => `${n} 份`,
  advisorReport: "AI 建议书",
  deliverablesEmptyTitle: "还没有交付物",
  deliverablesEmptyHint:
    "使用上方「生成建议书」或「生成 IPS」为该客户产出第一份交付物。",
  // Shared domain labels
  unassessed: "未评估",
  monthsValue: (n: number) => `${n} 个月`,
  maritalLabel: (v: string) =>
    v === "single"
      ? "未婚"
      : v === "married"
        ? "已婚"
        : v === "divorced"
          ? "离异"
          : v === "widowed"
            ? "丧偶"
            : v,
  taxLabel: (v: string) =>
    v === "taxable"
      ? "应税账户"
      : v === "tax-exempt"
        ? "免税账户"
        : v === "tax-deferred"
          ? "延税账户"
          : v,
};
