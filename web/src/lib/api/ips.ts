
// ---------------------------------------------------------------------------
// IPS workflow (Phase 4b — async generation tasks)
// ---------------------------------------------------------------------------

export interface IpsDocumentSummary {
  document_id: string;
  profile_id?: number | null;
  client_name: string;
  version: string;
  risk_level: string;
  status: string;
  revision_rounds: number;
  saved_at: string;
}

export interface IpsListResponse {
  documents: IpsDocumentSummary[];
}

export interface IpsDetailResponse {
  document_id: string;
  markdown: string;
  metadata: Record<string, unknown>;
  client_name: string;
  version: string;
  risk_level: string;
  status: string;
  revision_rounds: number;
  saved_at: string;
}

