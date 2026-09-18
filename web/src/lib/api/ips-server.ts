import "server-only";
import { getJson } from "./client";
import type { IpsDetailResponse, IpsListResponse } from "./ips";

export const getIpsDocuments = () => getJson<IpsListResponse>("/api/ips");

export const getIpsDocument = (documentId: string) =>
  getJson<IpsDetailResponse>(`/api/ips/${encodeURIComponent(documentId)}`);
