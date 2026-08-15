export const errors = {
  apiUnreachable: "API 服务不可达，请确认后端已启动。",
  upstreamError: (status: number) => `上游服务错误（HTTP ${status}）`,
  offline: {
    unreachable: (resource: string) => `无法获取${resource} — API 服务未响应。`,
    startBackend: "请先启动后端：",
    or: "或",
  },
  page: {
    errorTitle: "页面加载失败",
    errorHint: "渲染此页面时发生意外错误。",
    retry: "重试",
    notFoundTitle: "页面不存在",
    notFoundHint: "链接可能已失效，或页面已被移除。",
    backHome: "返回总览",
  },
};
