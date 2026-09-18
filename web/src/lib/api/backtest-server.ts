import "server-only";
import { getJson } from "./client";
import type { BacktestResponse } from "./backtest";

export const getBacktest = (documentId: string, period: string, locale?: string) =>
  getJson<BacktestResponse>(
    `/api/monitoring/${encodeURIComponent(documentId)}/backtest?period=${encodeURIComponent(period)}`,
    locale
  );
