import "server-only";
import { getJson, tickersParam } from "./client";
import type { AnalyticsResponse, CMEResponse, HealthResponse, QuotesResponse, RiskFreeRateResponse, UniverseResponse } from "./market";

export const getHealth = () => getJson<HealthResponse>("/api/health");

export const getUniverse = () => getJson<UniverseResponse>("/api/market/universe");

export const getQuotes = (tickers?: string[]) =>
  getJson<QuotesResponse>(
    `/api/market/quotes${tickers?.length ? `?tickers=${tickersParam(tickers)}` : ""}`
  );

export const getRiskFreeRate = () =>
  getJson<RiskFreeRateResponse>("/api/market/risk-free-rate");

export const getCme = () => getJson<CMEResponse>("/api/cme");

export const getAnalytics = (period: string, tickers: string[]) =>
  getJson<AnalyticsResponse>(
    `/api/market/analytics?period=${encodeURIComponent(period)}&tickers=${tickersParam(tickers)}`
  );
