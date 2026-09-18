import "server-only";
import { getJson } from "./client";
import type { AdvisorStatusResponse, ReportDetailResponse, ReportListResponse } from "./advisor";

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
