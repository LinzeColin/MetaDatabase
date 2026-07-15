"use client";

import { readProductionDataApiBaseUrl } from "./production-data-client";

export type SupplyChainStage = {
  stage_id: string;
  stage_order: number;
  slug: string;
  name_zh: string;
  name_en: string;
  default_direction: string;
  examples: string | null;
};

export type SupplyChainRelationship = {
  id: string;
  relationship_type: string;
  status: string;
  confidence: number | null;
  observed_at: string | null;
  owner_signed_published: boolean;
  subject_name: string;
  object_name: string;
  fixture_flag: boolean;
  stage_id: string | null;
};

export type SupplyChainOverviewRecord = {
  stages: SupplyChainStage[];
  relationships: SupplyChainRelationship[];
  summary: {
    published_fact_count: number;
    demo_or_candidate_count: number;
    stages_total: number;
    stages_with_relationships: number;
  };
  abstentions: Record<string, string>;
};

export type SupplyChainSyncResult =
  | { mode: "unavailable"; status: "api_required"; reason: string }
  | { mode: "live"; status: "hydrated"; overview: SupplyChainOverviewRecord }
  | { mode: "live"; status: "error"; reason: string };

function isOverview(payload: unknown): payload is SupplyChainOverviewRecord {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const record = payload as Record<string, unknown>;
  return (
    Array.isArray(record.stages) &&
    Array.isArray(record.relationships) &&
    typeof record.summary === "object" &&
    record.summary !== null
  );
}

export async function loadSupplyChainOverview(): Promise<SupplyChainSyncResult> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return { mode: "unavailable", status: "api_required", reason: "api_base_missing" };
  }
  try {
    const response = await window.fetch(`${apiBaseUrl}/v1/supply-chain/overview`);
    const payload = (await response.json().catch(() => null)) as unknown;
    if (!response.ok || !isOverview(payload)) {
      return {
        mode: "live",
        status: "error",
        reason: `supply_chain_http_${response.status}`
      };
    }
    return { mode: "live", status: "hydrated", overview: payload };
  } catch {
    return { mode: "live", status: "error", reason: "supply_chain_fetch_failed" };
  }
}
