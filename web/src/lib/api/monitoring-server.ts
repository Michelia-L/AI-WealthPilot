import "server-only";
import { getJson } from "./client";
import type { HoldingSnapshotHistory, MonitoringFleetResponse, MonitoringResponse } from "./monitoring";

export const getMonitoring = (documentId: string, locale?: string) =>
  getJson<MonitoringResponse>(
    `/api/monitoring/${encodeURIComponent(documentId)}`,
    locale
  );

export const getMonitoringFleetStatus = (locale?: string) =>
  getJson<MonitoringFleetResponse>("/api/monitoring/status", locale);

export const getHoldingSnapshots = (documentId: string, locale?: string) =>
  getJson<HoldingSnapshotHistory>(`/api/monitoring/${encodeURIComponent(documentId)}/holdings`, locale);
