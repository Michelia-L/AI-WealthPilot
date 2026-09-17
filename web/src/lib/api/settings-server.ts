import "server-only";
import { getJson } from "./client";
import type { LlmSettingsResponse } from "./settings";

export const getLlmSettings = () =>
  getJson<LlmSettingsResponse>("/api/settings/llm");
