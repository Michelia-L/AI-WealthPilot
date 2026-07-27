export const errors = {
  apiUnreachable: "API 服务不可达，请确认后端已启动。",
  upstreamError: (status: number) => `上游服务错误（HTTP ${status}）`,
  offline: {
    unreachable: (resource: string) => `无法获取${resource} — API 服务未响应。`,
    startBackend: "请先启动后端：",
    or: "或",
  },
};
