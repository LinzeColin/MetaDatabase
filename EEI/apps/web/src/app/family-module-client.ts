"use client";

import { readProductionDataApiBaseUrl } from "./production-data-client";

export type FamilyRelationship = {
  id: string;
  relationship_type: string;
  relationship_family: string;
  status: string;
  confidence: number | null;
  observed_at: string | null;
  owner_signed_published: boolean;
  subject_name: string;
  object_name: string;
  fixture_flag: boolean;
};

export type MaEvent = {
  id: string;
  event_type: string;
  title: string;
  status: string;
  announced_at: string | null;
  effective_at: string | null;
};

export type SignalModelRecord = {
  model_key: string;
  version: string;
  has_scored_run: boolean;
};

export type FamilyOverviewRecord = {
  relationships: FamilyRelationship[];
  events?: MaEvent[];
  signal_models?: SignalModelRecord[];
  summary: Record<string, unknown>;
  abstentions: Record<string, string>;
};

export type FamilyOverviewSyncResult =
  | { mode: "unavailable"; status: "api_required"; reason: string }
  | { mode: "live"; status: "hydrated"; overview: FamilyOverviewRecord }
  | { mode: "live"; status: "error"; reason: string };

function isFamilyOverview(payload: unknown): payload is FamilyOverviewRecord {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const record = payload as Record<string, unknown>;
  return Array.isArray(record.relationships) && typeof record.summary === "object";
}

export async function loadFamilyOverview(
  endpoint: "/v1/ma/overview" | "/v1/control/overview" | "/v1/signals/overview"
): Promise<FamilyOverviewSyncResult> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return { mode: "unavailable", status: "api_required", reason: "api_base_missing" };
  }
  try {
    const response = await window.fetch(`${apiBaseUrl}${endpoint}`);
    const payload = (await response.json().catch(() => null)) as unknown;
    if (!response.ok || !isFamilyOverview(payload)) {
      return { mode: "live", status: "error", reason: `family_http_${response.status}` };
    }
    return { mode: "live", status: "hydrated", overview: payload };
  } catch {
    return { mode: "live", status: "error", reason: "family_fetch_failed" };
  }
}
