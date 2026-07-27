export const errors = {
  apiUnreachable:
    "API service unreachable — please make sure the backend is running.",
  upstreamError: (status: number) => `Upstream service error (HTTP ${status})`,
  offline: {
    unreachable: (resource: string) =>
      `Unable to load ${resource} — the API service is not responding.`,
    startBackend: "Start the backend first: ",
    or: " or ",
  },
};
