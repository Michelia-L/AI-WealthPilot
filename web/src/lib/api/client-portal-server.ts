import "server-only";
import { API_ORIGIN, getSessionHeaders } from "../session";
import type { Locale } from "../i18n/locale";
import type {
  ClientAdvisors,
  ClientGoals,
  ClientIdentity,
  ClientPortfolio,
  ClientProfile,
  ClientReport,
  ClientReportSummary,
  ClientRisk,
} from "./client-portal";

/** Preserve failure status so a service outage cannot become a missing document. */
async function readClient<T>(
  suffix: string,
  locale: Locale,
): Promise<{ data: T | null; status: number }> {
  try {
    const response = await fetch(`${API_ORIGIN}/api/me${suffix}`, {
      cache: "no-store",
      headers: { ...(await getSessionHeaders()), "X-Locale": locale },
    });
    if (!response.ok) return { data: null, status: response.status };
    return { data: (await response.json()) as T, status: response.status };
  } catch {
    return { data: null, status: 502 };
  }
}

export const getClientIdentity = (locale: Locale) =>
  readClient<ClientIdentity>("", locale);
export const getClientProfile = (locale: Locale) =>
  readClient<ClientProfile>("/profile", locale);
export const getClientPortfolio = (locale: Locale) =>
  readClient<ClientPortfolio>("/portfolio", locale);
export const getClientGoals = (locale: Locale) =>
  readClient<ClientGoals>("/goals", locale);
export const getClientRisk = (locale: Locale) =>
  readClient<ClientRisk>("/risk-profile", locale);
export const getClientAdvisors = (locale: Locale) =>
  readClient<ClientAdvisors>("/advisor", locale);
export const getClientReports = (locale: Locale, offset = 0, limit = 20) =>
  readClient<{ reports: ClientReportSummary[] }>(
    `/reports?limit=${limit}&offset=${offset}`,
    locale,
  );
export const getClientReport = (id: string, locale: Locale) =>
  readClient<ClientReport>(`/reports/${encodeURIComponent(id)}`, locale);
