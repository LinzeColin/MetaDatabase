"use client";

// EEI-PULSE client. One endpoint (/v1/meta/pulse) answers the question the
// workspace could never answer before: is anything actually arriving, and how
// much? Every screen that shows a number about the corpus reads it from here,
// so the totals, the growth curve and the collector heartbeat can never
// disagree with each other.

import { readProductionDataApiBaseUrl } from "./production-data-client";

export type PulseCounts = {
  entities: number;
  relationships: number;
  events: number;
};

export type PulseDay = PulseCounts & {
  day: string;
  entities_added: number;
  relationships_added: number;
  events_added: number;
};

export type PulseSource = {
  code: string;
  name: string;
  documents: number;
  last_seen_at: string | null;
};

export type PulseHeartbeatState = "live" | "delayed" | "stalled" | "unknown";

export type PulseRecord = {
  schema_version: string;
  generated_at: string;
  data_as_of: string | null;
  last_publish_at: string | null;
  totals: PulseCounts;
  added: { today: PulseCounts; d7: PulseCounts; d30: PulseCounts };
  series: PulseDay[];
  composition: {
    event_type: { bucket: string; count: number }[];
    relationship_family: { bucket: string; count: number }[];
  };
  sources: PulseSource[];
  heartbeat: {
    state: PulseHeartbeatState;
    last_seen_at: string | null;
    lag_seconds: number | null;
    collector: string | null;
  };
};

export type PulseResult =
  | { status: "skipped"; reason: string }
  | { status: "error"; endpoint: string; reason: string }
  | { status: "hydrated"; endpoint: string; record: PulseRecord };

function isCounts(value: unknown): value is PulseCounts {
  if (!value || typeof value !== "object") return false;
  const v = value as Partial<PulseCounts>;
  return (
    typeof v.entities === "number" &&
    typeof v.relationships === "number" &&
    typeof v.events === "number"
  );
}

function isPulseRecord(value: unknown): value is PulseRecord {
  if (!value || typeof value !== "object") return false;
  const v = value as Partial<PulseRecord>;
  return (
    v.schema_version === "eei-data-pulse-v1" &&
    isCounts(v.totals) &&
    Array.isArray(v.series) &&
    Boolean(v.heartbeat)
  );
}

export async function loadDataPulse(days = 60): Promise<PulseResult> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return { status: "skipped", reason: "api_base_missing" };
  }
  const endpoint = `${apiBaseUrl}/v1/meta/pulse?days=${days}`;
  try {
    const response = await window.fetch(endpoint, { cache: "no-store" });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok || !isPulseRecord(payload)) {
      return {
        status: "error",
        endpoint,
        reason: response.ok ? "pulse_contract_mismatch" : `http_${response.status}`
      };
    }
    return { status: "hydrated", endpoint, record: payload };
  } catch (error) {
    return {
      status: "error",
      endpoint,
      reason: error instanceof Error ? error.message : "network_error"
    };
  }
}

// —— formatting helpers (shared by the strip and the dashboard) ——————————

export function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(Math.max(0, Math.round(value)));
}

export function formatDelta(value: number): string {
  if (!value) return "持平";
  return `${value > 0 ? "+" : "−"}${formatCount(Math.abs(value))}`;
}

/** "3 分钟前" — the only honest way to render a heartbeat. */
export function formatLag(seconds: number | null): string {
  if (seconds === null) return "未知";
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} 秒前`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} 小时前`;
  return `${Math.round(seconds / 86400)} 天前`;
}

export const HEARTBEAT_LABEL: Record<PulseHeartbeatState, string> = {
  live: "采集中",
  delayed: "有延迟",
  stalled: "已停止",
  unknown: "未知"
};
