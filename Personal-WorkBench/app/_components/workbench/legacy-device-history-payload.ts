/**
 * A retired hostname cannot read or write the canonical hostname's IndexedDB.
 * This compact, browser-only payload is the sole bridge for anonymous device
 * history. It deliberately contains no account identity, credentials, files,
 * or cloud object references.
 */
export type GuestDeviceHistoryModule =
  | "habits"
  | "habitCheckins"
  | "todos"
  | "ledger"
  | "food"
  | "exercise"
  | "weight"
  | "schedule"
  | "anniversaries"
  | "diary"
  | "savings"
  | "savingsTransactions"
  | "period";

export type GuestDeviceHistoryEnvelope = {
  sourceInstanceId: string;
  sourceSchemaVersion: 1;
  exportedAt: string;
  modules: Partial<Record<GuestDeviceHistoryModule, Array<Record<string, unknown>>>>;
  imageManifest: [];
};

export const LEGACY_DEVICE_HISTORY_SESSION_KEY = "mydairy.legacy-device-history.v1";
export const LEGACY_DEVICE_HISTORY_TRANSFER_EVENT = "mydairy:legacy-device-history-transferred";

const MODULES = new Set<GuestDeviceHistoryModule>([
  "habits",
  "habitCheckins",
  "todos",
  "ledger",
  "food",
  "exercise",
  "weight",
  "schedule",
  "anniversaries",
  "diary",
  "savings",
  "savingsTransactions",
  "period",
]);
const TENANT_FIELDS = new Set(["userId", "user_id", "ownerId", "owner_id", "tenantId", "tenant_id"]);
const UNSAFE_FIELDS = new Set(["__proto__", "constructor", "prototype"]);
const MAX_PAYLOAD_CHARACTERS = 2_000_000;
const MAX_ROWS_PER_MODULE = 1_000;
const MAX_TOTAL_ROWS = 5_000;
const MAX_VALUE_DEPTH = 12;
const LOCAL_RECORD_ID = /^local_[a-z0-9_-]{8,128}$/i;
const SOURCE_INSTANCE_ID = /^guest-device-[a-z0-9-]{8,128}$/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function safeValue(value: unknown, depth = 0): boolean {
  if (value === null || typeof value === "boolean") return true;
  if (typeof value === "string") return value.length <= MAX_PAYLOAD_CHARACTERS;
  if (typeof value === "number") return Number.isFinite(value);
  if (depth >= MAX_VALUE_DEPTH) return false;
  if (Array.isArray(value)) {
    return value.length <= MAX_ROWS_PER_MODULE && value.every((item) => safeValue(item, depth + 1));
  }
  if (!isRecord(value)) return false;
  const entries = Object.entries(value);
  return entries.length <= 100 && entries.every(([key, item]) => (
    !UNSAFE_FIELDS.has(key) && !TENANT_FIELDS.has(key) && safeValue(item, depth + 1)
  ));
}

function asJsonValue(value: unknown): unknown {
  if (typeof value === "string") {
    if (value.length > MAX_PAYLOAD_CHARACTERS) return null;
    try {
      return JSON.parse(value);
    } catch {
      return null;
    }
  }
  try {
    const serialized = JSON.stringify(value);
    return serialized && serialized.length <= MAX_PAYLOAD_CHARACTERS ? JSON.parse(serialized) : null;
  } catch {
    return null;
  }
}

/**
 * Parse only a bounded, anonymous history envelope. Callers keep the result
 * in browser storage; this parser never sends it to a database or an API.
 */
export function parseLegacyDeviceHistoryPayload(value: unknown): GuestDeviceHistoryEnvelope | null {
  const parsed = asJsonValue(value);
  if (!isRecord(parsed)) return null;
  if (
    typeof parsed.sourceInstanceId !== "string"
    || !SOURCE_INSTANCE_ID.test(parsed.sourceInstanceId)
    || parsed.sourceSchemaVersion !== 1
    || typeof parsed.exportedAt !== "string"
    || parsed.exportedAt.length > 64
    || !Number.isFinite(Date.parse(parsed.exportedAt))
    || !isRecord(parsed.modules)
    || !Array.isArray(parsed.imageManifest)
    || parsed.imageManifest.length !== 0
  ) return null;

  let totalRows = 0;
  for (const [moduleName, rows] of Object.entries(parsed.modules)) {
    if (!MODULES.has(moduleName as GuestDeviceHistoryModule) || !Array.isArray(rows) || rows.length > MAX_ROWS_PER_MODULE) {
      return null;
    }
    totalRows += rows.length;
    if (
      totalRows > MAX_TOTAL_ROWS
      || !rows.every((row) => isRecord(row) && typeof row.id === "string" && LOCAL_RECORD_ID.test(row.id) && safeValue(row))
    ) return null;
  }

  return parsed as GuestDeviceHistoryEnvelope;
}

/** Normalise a browser-produced envelope before it crosses the hostname boundary. */
export function serializeLegacyDeviceHistoryPayload(value: unknown): string | null {
  const parsed = parseLegacyDeviceHistoryPayload(value);
  if (!parsed) return null;
  const serialized = JSON.stringify(parsed);
  return serialized.length <= MAX_PAYLOAD_CHARACTERS ? serialized : null;
}
