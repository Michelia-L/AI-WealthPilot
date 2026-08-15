import { getJson } from "./client";

// ---------------------------------------------------------------------------
// LLM Settings (Phase 21 — user-defined OpenAI-compatible endpoint)
// ---------------------------------------------------------------------------

export interface LlmSettingsResponse {
  configured: boolean;
  model: string;
  base_url: string;
  /** 生效来源：db = 用户自定义，env = 环境变量，none = 未配置。 */
  source: "db" | "env" | "none";
  /** 脱敏后的 API Key（sk-****1234），永远不会是原始值。 */
  api_key_masked: string;
  demo: boolean;
}

export const getLlmSettings = () =>
  getJson<LlmSettingsResponse>("/api/settings/llm");

