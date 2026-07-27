export const settings = {
  /** Page title (h1 + metadata); also the other locale's eyebrow. */
  title: "设置",
  description:
    "自定义 AI 模型端点：任何 OpenAI 兼容服务（DeepSeek、通义、OpenAI、本地 vLLM/Ollama 等）均可接入，保存后全站 AI 功能即时生效。",
  /** `resource` prop for the shared ApiOffline panel. */
  apiOfflineResource: "LLM 设置",

  // Source badges
  sourceDb: "自定义端点",
  sourceEnv: "环境变量",
  sourceNone: "未配置",
  demoBadge: "演示模式",

  // Current effective configuration
  currentTitle: "当前生效配置",
  modelLabel: "模型",
  endpointLabel: "端点",
  demoNotice:
    "演示模式（DEMO_MODE=1）优先于一切端点配置 —— AI 功能回放录制样例；关闭后方可用下方自定义端点。",

  // Custom endpoint form
  customTitle: "自定义模型端点",
  customDescription:
    "兼容 OpenAI API 协议的服务均可接入。Key 仅明文保存在本机 SQLite（data/wealthpilot.db），不会上传他处；保存后 AI 顾问 / IPS 生成 / 调仓建议立即切换到新端点。",
  endpointField: "端点地址（Base URL）",
  apiKeyHint: "留空保存 = 清除自定义配置，回退到环境变量",
  modelPlaceholder: "手动填写，或先拉取模型列表",
  fetchModels: "拉取模型列表",
  fetching: "拉取中…",
  saveConfig: "保存配置",
  clearCustom: "清除自定义",

  // Notices
  savedNotice: "已保存 —— 全站 AI 功能已切换到自定义端点。",
  clearedNotice: "已清除自定义配置 —— 回退到环境变量。",
  modelsFetched: (n: number) => `已获取 ${n} 个可用模型`,

  // Error fallbacks
  fetchFailed: (status: number) => `拉取失败（HTTP ${status}）`,
  saveFailedHttp: (status: number) => `保存失败（HTTP ${status}）`,
  noModels: "端点未返回任何可用模型",
};
