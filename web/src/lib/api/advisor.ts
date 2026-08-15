import { getJson } from "./client";

// ---------------------------------------------------------------------------
// AI Advisor (Phase 4a — SSE streaming advisory reports)
// ---------------------------------------------------------------------------

export interface AdvisorStatusResponse {
  configured: boolean;
  model: string;
  /** 演示模式：LLM 端点回放录制样例而非真实生成。 */
  demo: boolean;
}

export interface ReportSummary {
  report_id: string;
  client_name: string;
  model: string;
  generated_at: string;
  total_tokens: number;
  has_notes: boolean;
}

export interface ReportListResponse {
  reports: ReportSummary[];
}

export interface ReportDetailResponse extends ReportSummary {
  content: string;
  prompt_tokens: number;
  completion_tokens: number;
  notes: string;
}

/** Terminal SSE event after the token stream completes. */
export interface AdvisorDoneEvent {
  type: "done";
  success: boolean;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  /** 思维链 tokens（reasoner 类模型；无推理能力时为 0/缺省）。 */
  reasoning_tokens?: number;
  error_message: string;
}

export const getAdvisorStatus = () =>
  getJson<AdvisorStatusResponse>("/api/advisor/status");

export const getAdvisorReports = (clientName?: string) =>
  getJson<ReportListResponse>(
    `/api/advisor/reports${clientName ? `?client_name=${encodeURIComponent(clientName)}` : ""}`
  );

export const getAdvisorReport = (reportId: string) =>
  getJson<ReportDetailResponse>(
    `/api/advisor/reports/${encodeURIComponent(reportId)}`
  );

