"use client";

import { readProductionDataApiBaseUrl } from "./production-data-client";

export type StructureEntityRef = {
  id: string;
  canonical_name: string;
  entity_type: string;
};

export type StructureItem = {
  entity: StructureEntityRef;
  relationship: {
    // P1-8：关系 UUID（若发布面在结构项上带出则用于证据下钻 /v1/evidence/
    // relationship/:id）。当前云 /empire 只返回焦点、结构层为空，故此字段常缺；
    // 缺失时结构行不渲染「查证」——杜绝裸下钻死链（§C.3）。
    id?: string;
    relationship_type: string;
    relationship_family: string;
    status: string;
  };
  relationship_scope: string;
  relationship_direction: string;
  control_semantics: string | null;
  fixture_notice: string | null;
};

export type StructureSection = {
  label: string;
  items: StructureItem[];
  data_status: string;
  data_gap: string | null;
  item_count: number;
};

export type EmpireFocus = StructureEntityRef & {
  fixture_notice: string | null;
  synthetic: boolean;
  primary_identifiers: Record<string, string>;
};

export type EmpireRecord = {
  as_of: string;
  focus: EmpireFocus;
  structure: Record<string, StructureSection>;
  coverage: Record<string, unknown>;
  data_mode: string;
  fixture_notice: string | null;
};

export type EmpireSyncResult =
  | { mode: "unavailable"; status: "api_required"; reason: string }
  | { mode: "live"; status: "hydrated"; empire: EmpireRecord }
  | { mode: "live"; status: "error"; reason: string };

function isEmpireRecord(payload: unknown): payload is EmpireRecord {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const record = payload as Record<string, unknown>;
  return (
    typeof record.focus === "object" &&
    record.focus !== null &&
    typeof record.structure === "object" &&
    record.structure !== null &&
    typeof record.data_mode === "string"
  );
}

export async function searchEntityIdByName(name: string): Promise<string | null> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return null;
  }
  try {
    const response = await window.fetch(
      `${apiBaseUrl}/v1/entities?q=${encodeURIComponent(name)}`
    );
    const payload = (await response.json().catch(() => null)) as unknown;
    // The local API returns a bare array; the cloud worker wraps it as
    // { query, entities: [...] }. Accept both so /structure resolves its focus
    // entity on either surface (module audit: focus_entity_not_resolved).
    const list = Array.isArray(payload)
      ? payload
      : ((payload as { entities?: unknown } | null)?.entities ?? null);
    if (!response.ok || !Array.isArray(list) || list.length === 0) {
      return null;
    }
    const top = list[0] as Record<string, unknown>;
    return typeof top.id === "string" ? top.id : null;
  } catch {
    return null;
  }
}

export async function loadEntityEmpire(entityId: string): Promise<EmpireSyncResult> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return { mode: "unavailable", status: "api_required", reason: "api_base_missing" };
  }
  try {
    const response = await window.fetch(
      `${apiBaseUrl}/v1/entities/${encodeURIComponent(entityId)}/empire`
    );
    const payload = (await response.json().catch(() => null)) as unknown;
    if (!response.ok || !isEmpireRecord(payload)) {
      return { mode: "live", status: "error", reason: `empire_http_${response.status}` };
    }
    return { mode: "live", status: "hydrated", empire: payload };
  } catch {
    return { mode: "live", status: "error", reason: "empire_fetch_failed" };
  }
}
