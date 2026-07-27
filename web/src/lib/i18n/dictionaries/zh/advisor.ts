export const advisor = {
  /** Page title (h1 + metadata); also the other locale's eyebrow. */
  title: "AI 顾问",
  description:
    "基于客户画像，由 DeepSeek 流式逐字生成个性化投资建议书（IPS 框架 · 行为金融 · 资产配置）。",

  // Config / demo banners
  notConfigured:
    "DEEPSEEK_API_KEY 未配置 —— 请在项目根目录 .env 中设置并重启 API 服务后使用。",
  demoMode:
    "演示模式 —— AI 生成内容为录制样例，用于功能预览；配置 DEEPSEEK_API_KEY 并关闭 DEMO_MODE 后体验真实生成。",

  // Generation panel
  profilesUnreachable: "无法获取画像列表 —— 请确认 API 服务已启动。",
  noProfilesPre: "还没有客户画像。请先在",
  noProfilesLink: "客户画像",
  noProfilesPost: "页面创建。",
  selectClient: "选择客户",
  profileOption: (name: string, age: number, risk: string | null) =>
    `${name}（${age} 岁${risk ? ` · ${risk}` : ""}）`,
  generateReport: "生成建议书",
  generating: "AI 生成中…",
  stop: "停止",
  model: "模型",

  // Report body
  reportTitle: "AI 投资建议书",
  tokenSummary: (
    total: number,
    input: number,
    output: number,
    reasoning?: number
  ) =>
    `${total.toLocaleString()} tokens（输入 ${input.toLocaleString()} / 输出 ${output.toLocaleString()}${
      reasoning ? ` · 思考 ${reasoning.toLocaleString()}` : ""
    }）`,
  savedToLibrary: "已保存到报告库",
  clientName: "客户名称",
  deliveryNotes: "交付备注（可选）",
  notesPlaceholder: "随报告一起存档的一句话备注…",
  saveToLibrary: "保存到报告库",

  // Empty states
  thinking: "DeepSeek 正在思考…",
  streaming: "DeepSeek 正在生成…",
  idleTitle: "建议书将在此流式呈现",
  thinkingHint: "推理过程见上方「思考过程」，正文随后抵达。",
  streamingHint: "首段文字即将抵达。",
  idleHint: "选择客户后点击「生成建议书」，报告逐字输出，可一键存入报告库。",

  // Reasoning section (shared component)
  reasoningTitle: "思考过程",
  reasoningTokens: (n: number) => `思考 ${n.toLocaleString()} tokens`,

  // Report library
  libraryTitle: "报告库",
  libraryEmptyTitle: "暂无已保存的报告",
  libraryEmptyHint: "生成建议书后点击「保存到报告库」，即可在此随时回看。",
  thClient: "客户",
  thGenerated: "生成时间",
  thActions: "操作",
  viewReportLabel: "查看报告",
  deleteReportLabel: "删除报告",
  deleteTitle: "删除这份报告？",
  deleteDescription: "报告将从报告库中永久移除，此操作无法撤销。",

  // Error fallbacks
  requestFailed: (status: number) => `请求失败（HTTP ${status}）`,
  validationFailed: "报告校验未通过",
  generationInterrupted: "生成中断",
  saveFailed: "保存失败",
  loadFailed: "加载失败",
  deleteFailed: "删除失败",
};
