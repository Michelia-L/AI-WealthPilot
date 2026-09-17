import "server-only";
import { getJson } from "./client";
import type { AssetClassesResponse, RecommendationResponse } from "./portfolio";

export const getAssetClasses = () =>
  getJson<AssetClassesResponse>("/api/portfolio/asset-classes");

export const getRecommendation = (profileId: number, locale?: string) =>
  getJson<RecommendationResponse>(
    `/api/portfolio/recommendation?profile_id=${profileId}`,
    locale
  );
