/** overview namespace — populated by the localization pass (phase 22). */
export const overview = {
  title: "财富驾驶舱",
  tagline:
    "机构级财富管理方法论 × AI 智能体——从客户画像到投资建议书的完整工作流。",
  workbenchTitle: "工作台",
  monitoringOffender: (name: string, driftPp: number) =>
    `${name} 偏离 ${driftPp.toFixed(1)}pp`,
  monitoringBreachTitle: (n: number) => `${n} 个组合偏离政策区间`,
  monitoringBreachHint: (asOf: string) => `建议评估复衡 · 行情截至 ${asOf}`,
  monitoringOk: (n: number) => `组合监控正常 · ${n} 个组合均在政策区间内`,
  monitoringUnknown: (n: number) => `（${n} 个暂无法检测）`,
  monitoringAsOf: (asOf: string) => `行情截至 ${asOf}`,
  monitoringUnavailable: "组合监控数据暂不可用",
  clientsTitle: "客户速览",
  clientsManage: "管理",
  clientsOffline: "API 离线，无法读取客户列表。",
  clientsEmptyTitle: "还没有客户画像",
  clientsEmptyHint: "建立第一份双轨风险评估画像，开启顾问工作流。",
  clientAge: (age: number) => `${age} 岁`,
  clientsTotal: (n: number) => `共 ${n} 位客户`,
  deliverablesTitle: "最近交付物",
  deliverablesOffline: "API 离线，无法读取交付物。",
  deliverablesEmptyTitle: "暂无交付物",
  deliverablesEmptyHint: "在 AI 顾问或 IPS 生成页为客户产出第一份建议书。",
  kindAdvisor: "AI 建议书",
  kindIps: "IPS 文档",
  /** resource prop for the shared <ApiOffline> panel (rendered mid-sentence). */
  offlineResource: "市场与客户数据",
  disclaimer:
    "AI WealthPilot 为研究与教育用途的财富管理原型。所有量化输出与 AI 生成内容基于历史数据与模型假设，不构成投资建议。",
  modules: {
    market: {
      title: "市场",
      desc: "全球行情、跨资产相关性与资本市场预期（CME）",
    },
    optimizer: {
      title: "组合优化",
      desc: "MVO · Resampled · Black-Litterman 有效前沿求解",
    },
    retirement: {
      title: "退休规划",
      desc: "GBM 蒙特卡洛两阶段生命周期模拟",
    },
    profiles: {
      title: "客户画像",
      desc: "双轨风险画像与行为金融偏差识别",
    },
    advisor: {
      title: "AI 顾问",
      desc: "DeepSeek 流式生成个性化投资建议书",
    },
    ips: {
      title: "IPS 生成",
      desc: "LangGraph 多智能体生成—评审—修订流水线",
    },
  },
};
