export const ips = {
  /** Page title (h1 + metadata); also the other locale's eyebrow. */
  title: "IPS 生成",
  description:
    "LangGraph 多智能体工作流：注入资本市场预期后生成初稿，经适当性、合规、一致性三维评审与 SAA 量化验证，自动修订直至定稿入库。",

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
  selectProfile: "选择画像",
  profileOption: (name: string, age: number, risk: string | null) =>
    `${name}（${age} 岁${risk ? ` · ${risk}` : ""}）`,
  maxRevisions: "最大修订轮数",
  generate: "生成 IPS",
  running: "工作流运行中…",
  pipelineHint: "CME → 初稿 → 三维评审 → SAA 量化验证 → 修订/定稿（通常需要数分钟）",

  // Progress timeline
  progressTitle: "工作流进度",
  processing: "正在处理…",
  donePre: "IPS 已生成并入库 · 文档",
  statusLabel: "状态",
  doneRevisions: (n: number) => ` · 修订 ${n} 轮`,
  viewNow: "立即查看",

  // Document viewer
  version: "版本",
  revisionRounds: "修订轮次",
  downloadPdf: "下载 PDF",

  // Document library
  libraryTitle: "IPS 文档库",
  libraryHint: "本地 JSON 存储",
  libraryEmptyTitle: "暂无 IPS 文档",
  libraryEmptyHint: "选择客户画像并运行上方工作流后，生成的 IPS 文档将保存在这里。",
  thClient: "客户",
  thRisk: "风险等级",
  thRevisions: "修订轮数",
  thSaved: "保存时间",
  thActions: "操作",

  // Error fallbacks
  createTaskFailed: (status: number) => `创建任务失败（HTTP ${status}）`,
  progressUnavailable: "无法接收任务进度",
  generateFailed: "生成失败",
  loadFailed: "加载失败",
};
