/** deliverables namespace — populated by the localization pass (phase 22). */
export const deliverables = {
  title: "交付物中心",
  description:
    "AI 建议书与 IPS 文档的统一浏览与导出 —— 每一次顾问交付，都留痕可查。",
  descriptionOffline: "AI 建议书与 IPS 文档的统一浏览与导出。",
  resourceList: "交付物列表",
  emptyTitle: "没有符合条件的交付物",
  emptyHint: "调整筛选条件，或先到 AI 顾问 / IPS 生成页为客户产出交付物。",
  kindAdvisor: "AI 建议书",
  kindIps: "IPS",
  ipsSub: (version: string, status: string, rounds: number) =>
    `v${version} · ${status} · 修订 ${rounds} 轮`,
  colType: "类型",
  colClient: "客户",
  colSummary: "摘要",
  colTime: "时间",
  colActions: "操作",
  filterClient: "客户",
  allClients: "全部客户",
  filterType: "类型",
  typeAll: "全部",
  typeIps: "IPS 文档",
  refreshing: "刷新中…",
  countLabel: (n: number) => `${n} 份`,
  backToCenter: "返回交付物中心",
  deleteTitle: "删除已存储文档？",
  deleteDescription: (name: string) =>
    `确定永久删除 ${name} 的这份已存储文档？此操作无法撤销。审核发布流程中的文档版本及客户确认记录会保留。`,
  deleteLabel: (name: string) => `删除 ${name} 的文档`,
  deleting: "删除中…",
  deleteFailed: "无法删除文档，请重试。",
};
