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
  page: {
    errorTitle: "Page failed to load",
    errorHint: "An unexpected error occurred while rendering this page.",
    retry: "Retry",
    notFoundTitle: "Page not found",
    notFoundHint: "The link may be broken or the page may have been removed.",
    backHome: "Back to overview",
  },
};
