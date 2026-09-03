/** profiles namespace — /profiles list, manager, form, compare, questionnaire. */
export const profiles = {
  title: "客户画像",
  description:
    "IPS 框架客户信息管理：双轨风险评估取 min(能力, 意愿) 得出最终风险等级。",
  createProfile: "新建画像",
  deleteDialogTitle: "删除客户画像",
  deleteDialogDescription: (name: string) =>
    `确定删除画像「${name}」？此操作不可撤销。`,
  // Async action fallbacks (server detail messages pass through untouched)
  errorCompareFailed: "对比失败",
  errorLoadFailed: "加载失败",
  errorValidationFailed: "校验失败",
  errorListSeparator: "；",
  errorSaveFailed: (status: number) => `保存失败（HTTP ${status}）`,
  errorDeleteFailed: "删除失败",
  errorImportFailed: "导入失败",
  importSummary: (found: number, imported: number, skipped: number) =>
    `导入完成：发现 ${found} 个 JSON 文件，新增 ${imported} 条，跳过 ${skipped} 条。`,
  uploadJson: "上传 JSON",
  uploadInvalid: (files: string) => `以下文件未通过校验：${files}`,
  // Form
  editFormTitle: (name: string) => `编辑画像 · ${name || "…"}`,
  sectionBasicInfo: "基本信息",
  fieldName: "姓名",
  namePlaceholder: "例如：张三",
  fieldAge: "年龄",
  fieldMaritalStatus: "婚姻状况",
  fieldDependents: "受抚养人数",
  sectionFinancials: "财务状况",
  fieldAnnualIncome: "年收入",
  fieldAnnualExpenses: "年支出",
  fieldInvestableAssets: "可投资资产",
  fieldTotalLiabilities: "总负债",
  fieldEmergencyFundMonths: "应急基金（月数）",
  sectionGoals: "投资目标",
  addGoal: "添加目标",
  noGoalsYet: "暂无目标，点击右上角添加。",
  fieldGoalName: "目标名称",
  goalNamePlaceholder: "例如：退休",
  fieldTargetAmount: "目标金额",
  fieldYears: "年限",
  fieldPriority: "优先级",
  deleteGoalAria: "删除目标",
  sectionConstraints: "投资约束与偏好",
  fieldTimeHorizon: "投资期限（年）",
  fieldLiquidityNeeds: "流动性需求（金额）",
  fieldTaxStatus: "税务状态",
  fieldSectorRestrictions: "行业限制（逗号分隔）",
  sectorRestrictionsPlaceholder: "例如：烟草, 军工",
  esgPreferenceLabel: "ESG 偏好（环境/社会/治理）",
  fieldNotes: "备注",
  sectionQuestionnaire: "风险问卷",
  saveChanges: "保存修改",
  // List
  importFromJson: "从 JSON 导入",
  comparing: "对比中…",
  compareSelected: (n: number) => `对比所选（${n}）`,
  selectOneMoreHint: (max: number) => `再选 1 个即可对比（最多 ${max} 个）`,
  listResource: "画像列表",
  emptyTitle: "还没有客户画像",
  emptyHint: "建立第一份双轨风险评估画像，或从 Streamlit 时代的 JSON 文件导入。",
  selectSrOnly: "选择",
  colRiskLevel: "风险等级",
  colUpdated: "更新时间",
  colActions: "操作",
  selectForCompareAria: (name: string) => `选择 ${name} 参与对比`,
  editAria: (name: string) => `编辑 ${name}`,
  deleteAria: (name: string) => `删除 ${name}`,
  // Compare
  compareTitle: "画像对比",
  colClient: "客户",
  colRiskScore: "风险评分",
  colNetWorth: "净资产",
  colSavingsRate: "储蓄率",
  colEmergencyFund: "应急基金",
  colBiasCount: "偏差数",
  keyInsights: "关键洞察",
  biasAnalysis: "行为偏差分析",
  noBiasesDetected: "未检测到行为偏差",
  // Questionnaire
  riskAbility: "风险承受能力",
  riskWillingness: "风险承受意愿",
  combinedScore: "综合 = min(能力, 意愿)",
  livePreview: "实时预览",
  abilityTrackTitle: "风险承受能力（客观 · 5 题）",
  willingnessTrackTitle: "风险承受意愿（主观 · 4 题）",
  questionnaireHelp:
    "已答题目自动算分（未答题不参与平均），保存时覆盖手动评分；再次点击选项可取消作答。全部留空则保留手动评分，0 表示未评估。",
  questionnaireUnavailable:
    "风险问卷加载失败（API 未就绪），暂以手动评分代替；评分为 0 表示未评估。",
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
  priorityShort: (v: string): string =>
    v === "high" ? "高" : v === "low" ? "低" : "中",
};
