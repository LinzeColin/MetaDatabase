"use client";

import { readProductionDataApiBaseUrl } from "./production-data-client";

export type PolicyRelationshipRecord = {
  id: string;
  relationship_type: string;
  status: string;
  confidence: number | null;
  observed_at: string | null;
  subject_id: string;
  subject_name: string;
  object_id: string;
  object_name: string;
  fixture_flag: boolean;
};

export type PolicyFilingYear = {
  year: number;
  filings: number;
};

export type PolicyFilingRecord = {
  id: string;
  title: string;
  url: string;
  document_date: string | null;
  publisher: string | null;
};

export type PolicyModelRecord = {
  model_key: string;
  version: string;
  has_scored_run: boolean;
};

export type PolicyOverviewRecord = {
  policy_relationships: PolicyRelationshipRecord[];
  regulatory_filings: {
    source: string;
    by_year: PolicyFilingYear[];
    latest: PolicyFilingRecord[];
    scoped_to_entity: boolean;
  };
  policy_models: PolicyModelRecord[];
  abstentions: Record<string, string>;
};

export type PolicyOverviewSyncResult =
  | { mode: "unavailable"; status: "api_required"; reason: string }
  | { mode: "live"; status: "hydrated"; overview: PolicyOverviewRecord }
  | { mode: "live"; status: "error"; reason: string };

function isPolicyOverviewRecord(payload: unknown): payload is PolicyOverviewRecord {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const record = payload as Record<string, unknown>;
  return (
    Array.isArray(record.policy_relationships) &&
    typeof record.regulatory_filings === "object" &&
    record.regulatory_filings !== null &&
    Array.isArray((record.regulatory_filings as Record<string, unknown>).by_year) &&
    Array.isArray(record.policy_models)
  );
}

export async function loadPolicyOverview(
  entityId?: string
): Promise<PolicyOverviewSyncResult> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return { mode: "unavailable", status: "api_required", reason: "api_base_missing" };
  }
  const query = entityId ? `?entity=${encodeURIComponent(entityId)}` : "";
  const endpoint = `${apiBaseUrl}/v1/policy/overview${query}`;
  try {
    const response = await window.fetch(endpoint);
    const payload = (await response.json().catch(() => null)) as unknown;
    if (!response.ok || !isPolicyOverviewRecord(payload)) {
      return {
        mode: "live",
        status: "error",
        reason: `policy_overview_http_${response.status}`
      };
    }
    return { mode: "live", status: "hydrated", overview: payload };
  } catch {
    return { mode: "live", status: "error", reason: "policy_overview_fetch_failed" };
  }
}
