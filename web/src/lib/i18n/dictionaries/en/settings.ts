export const settings = {
  /** Page title (h1 + metadata); also the other locale's eyebrow. */
  title: "Settings",
  description:
    "Custom AI model endpoint: any OpenAI-compatible service (DeepSeek, Qwen, OpenAI, local vLLM/Ollama, etc.) can be connected, and all AI features across the site take effect immediately after saving.",
  /** `resource` prop for the shared ApiOffline panel. */
  apiOfflineResource: "LLM settings",

  // Source badges
  sourceDb: "Custom Endpoint",
  sourceEnv: "Environment",
  sourceNone: "Not Configured",
  demoBadge: "Demo Mode",

  // Current effective configuration
  currentTitle: "Active Configuration",
  modelLabel: "Model",
  endpointLabel: "Endpoint",
  demoNotice:
    "Demo mode (DEMO_MODE=1) overrides all endpoint configuration — AI features replay recorded samples; turn it off to use the custom endpoint below.",

  // Custom endpoint form
  customTitle: "Custom Model Endpoint",
  customDescription:
    "Any service speaking the OpenAI API protocol can be connected. The key is stored in plaintext only in the local SQLite database (data/wealthpilot.db) and is never uploaded elsewhere; once saved, AI Advisor / IPS generation / rebalancing advice switch to the new endpoint immediately.",
  endpointField: "Endpoint (Base URL)",
  apiKeyHint:
    "Saving with an empty key clears the custom config and falls back to environment variables",
  modelPlaceholder: "Enter manually, or fetch the model list first",
  fetchModels: "Fetch Model List",
  fetching: "Fetching…",
  saveConfig: "Save Configuration",
  clearCustom: "Clear Custom",

  // Notices
  savedNotice: "Saved — all AI features now use the custom endpoint.",
  clearedNotice:
    "Custom configuration cleared — falling back to environment variables.",
  modelsFetched: (n: number) =>
    `Fetched ${n} available model${n === 1 ? "" : "s"}`,

  // Error fallbacks
  fetchFailed: (status: number) => `Fetch failed (HTTP ${status})`,
  saveFailedHttp: (status: number) => `Save failed (HTTP ${status})`,
  noModels: "The endpoint returned no available models",
};
