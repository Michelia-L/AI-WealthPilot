/** Client-safe contracts from /api/me; never reuse staff artifact DTOs here. */
export interface ClientIdentity {
  user_id: string;
  email: string;
  role: "client";
  is_demo: boolean;
}
export interface ClientProfile {
  name: string;
  age: number;
  marital_status: string;
  dependents: number;
  investable_assets: number;
  total_liabilities: number;
  net_worth: number;
  time_horizon_years: number;
  updated_at: string;
}
export interface ClientAllocation {
  asset_class: string;
  weight: number;
}
export interface ClientPortfolio {
  status: "published_plan" | "unavailable";
  report_id: string | null;
  allocation: ClientAllocation[];
  recommendation: string | null;
  performance: null;
  performance_explanation: string;
}
export interface ClientGoal {
  name: string;
  target_amount: number;
  years: number;
  priority: string;
  progress: null;
}
export interface ClientGoals {
  goals: ClientGoal[];
  progress_explanation: string;
}
export interface ClientRisk {
  assessed: boolean;
  level: string | null;
  explanation: string;
}
export interface ClientAdvisors {
  advisors: { email: string }[];
}
export type ClientDocumentType =
  "ips" | "portfolio_review" | "retirement_report";
export interface ClientReportSummary {
  id: string;
  document_id: string;
  type: ClientDocumentType;
  version: number;
  title: string;
  status: "published" | "acknowledged";
  published_at: string;
  acknowledged_at: string | null;
}
export interface ClientReport extends ClientReportSummary {
  content: {
    title: string;
    summary: string;
    recommendation: string;
    risk_explanation: string;
    risk_disclosure: string;
    allocation: ClientAllocation[];
    sections: { heading: string; text: string }[];
  };
}
export interface ClientAssistantAnswer {
  answer: string;
  demo: boolean;
}
