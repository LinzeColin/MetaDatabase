import {
  parseLegacyDeviceHistoryPayload,
  type GuestDeviceHistoryEnvelope,
  type GuestDeviceHistoryModule,
} from "./legacy-device-history-payload.ts";

export type {
  GuestDeviceHistoryEnvelope,
  GuestDeviceHistoryModule,
} from "./legacy-device-history-payload.ts";

/**
 * Device-local records are deliberately kept outside the cloud data plane.
 * They make an interrupted, logged-out, or consent-paused interaction useful
 * on this device without ever supplying a tenant identifier to an API.
 */
export type DeviceLocalRecord = Record<string, unknown> & {
  __mydairy_device_local_v1: true;
  created_at: number;
  id: string;
  updated_at: number;
};

export type DeviceOutboxAction = {
  createdAt: number;
  endpoint: string;
  idempotencyKey: string;
  localRecordId?: string;
  method: "POST";
  parentReferences?: DeviceOutboxParentReference[];
  payload: Record<string, unknown>;
  queuedAt: number;
  /** This queued payload is eligible only after a current account opt-in. */
  requiresSensitiveConsent?: true;
};

export type DeviceOutboxParentReference = {
  field: "habitId" | "goalId";
  localRecordId: string;
  resource: "habits" | "savings-goals";
};

/**
 * The only device-only history that may be offered for account import is the
 * anonymous partition. Account partitions deliberately stay private to the
 * account that created them, even when a shared browser later signs in as a
 * different person.
 */
type CachedRecordRow = {
  id: string;
  key: string;
  record: DeviceLocalRecord;
  resource: string;
  scope: string;
  updatedAt: number;
};

type CachedOutboxRow = {
  action: DeviceOutboxAction;
  key: string;
  queuedAt: number;
  scope: string;
};

type CachedRecordAliasRow = {
  key: string;
  localRecordId: string;
  remoteRecordId: string;
  resource: string;
  scope: string;
};

const DATABASE_NAME = "mydairy-device-records-v1";
const DATABASE_VERSION = 3;
const RECORD_STORE = "records";
const SCOPE_RESOURCE_INDEX = "by_scope_resource";
const OUTBOX_STORE = "outbox";
const OUTBOX_SCOPE_INDEX = "by_scope";
const RECORD_ALIAS_STORE = "record-aliases";
const LOCAL_MARKER = "__mydairy_device_local_v1";
const LOCAL_RECORD_FALLBACK_PREFIX = "mydairy.device-records.fallback.v1";
const DEVICE_OUTBOX_FALLBACK_PREFIX = "mydairy.device-outbox.fallback.v1";
const DEVICE_RECORD_ALIAS_FALLBACK_PREFIX = "mydairy.device-record-alias.fallback.v1";
// Keep this aligned with the account control's authoritative session check.
// A hosted D1-backed lookup can legitimately take longer than the old 2.5 s
// budget; treating that slow successful response as "guest" after an OAuth
// return partitions the just-authenticated person's history on this device.
const BROWSER_SCOPE_REQUEST_TIMEOUT_MS = 8_000;
const BROWSER_SCOPE_CACHE_TTL_MS = 5_000;
const BROWSER_SCOPE_UNAVAILABLE_BACKOFF_MS = 2_500;
const GUEST_DEVICE_HISTORY_SOURCE_KEY = "mydairy.guest-device-history-source.v1";
const GUEST_DEVICE_HISTORY_EXPORTED_AT_KEY = "mydairy.guest-device-history-exported-at.v1";
const tenantFieldNames = new Set(["userId", "user_id", "ownerId", "owner_id", "tenantId", "tenant_id"]);

const guestDeviceHistoryResources: ReadonlyArray<{
  module: GuestDeviceHistoryModule;
  resource: string;
}> = [
  { module: "habits", resource: "habits" },
  { module: "habitCheckins", resource: "habit-checkins" },
  { module: "todos", resource: "todos" },
  { module: "ledger", resource: "ledger" },
  { module: "food", resource: "food" },
  { module: "exercise", resource: "exercise" },
  { module: "weight", resource: "weights" },
  { module: "schedule", resource: "schedule" },
  { module: "anniversaries", resource: "anniversaries" },
  { module: "diary", resource: "diary" },
  { module: "savings", resource: "savings-goals" },
  { module: "savingsTransactions", resource: "savings-transactions" },
  { module: "period", resource: "periods" },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function canUseIndexedDb(): boolean {
  return typeof window !== "undefined" && typeof window.indexedDB !== "undefined";
}

function requestValue<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed."));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB transaction aborted."));
    transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB transaction failed."));
  });
}

function openRecordDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      const recordStore = database.objectStoreNames.contains(RECORD_STORE)
        ? request.transaction?.objectStore(RECORD_STORE)
        : database.createObjectStore(RECORD_STORE, { keyPath: "key" });
      if (recordStore && !recordStore.indexNames.contains(SCOPE_RESOURCE_INDEX)) {
        recordStore.createIndex(SCOPE_RESOURCE_INDEX, ["scope", "resource"], { unique: false });
      }
      const outboxStore = database.objectStoreNames.contains(OUTBOX_STORE)
        ? request.transaction?.objectStore(OUTBOX_STORE)
        : database.createObjectStore(OUTBOX_STORE, { keyPath: "key" });
      if (outboxStore && !outboxStore.indexNames.contains(OUTBOX_SCOPE_INDEX)) {
        outboxStore.createIndex(OUTBOX_SCOPE_INDEX, "scope", { unique: false });
      }
      if (!database.objectStoreNames.contains(RECORD_ALIAS_STORE)) {
        database.createObjectStore(RECORD_ALIAS_STORE, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Unable to open device record cache."));
  });
}

function cacheKey(scope: string, resource: string, id: string): string {
  return `${scope}\u0000${resource}\u0000${id}`;
}

function localRecordFallbackKey(scope: string, resource: string): string {
  return `${LOCAL_RECORD_FALLBACK_PREFIX}\u0000${scope}\u0000${resource}`;
}

function deviceOutboxFallbackKey(scope: string): string {
  return `${DEVICE_OUTBOX_FALLBACK_PREFIX}\u0000${scope}`;
}

function deviceRecordAliasFallbackKey(scope: string, resource: string, localRecordId: string): string {
  return `${DEVICE_RECORD_ALIAS_FALLBACK_PREFIX}\u0000${scope}\u0000${resource}\u0000${localRecordId}`;
}

function browserLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function newGuestDeviceHistorySourceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `guest-device-${crypto.randomUUID()}`;
  }
  return `guest-device-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * A stable, value-free source identifier makes an explicit retry idempotent.
 * It identifies this browser's anonymous cache, never an account or user.
 */
export function guestDeviceHistorySourceId(storage = browserLocalStorage()): string {
  try {
    const existing = storage?.getItem(GUEST_DEVICE_HISTORY_SOURCE_KEY) ?? "";
    if (/^guest-device-[a-z0-9-]{8,}$/i.test(existing)) return existing;
    const next = newGuestDeviceHistorySourceId();
    storage?.setItem(GUEST_DEVICE_HISTORY_SOURCE_KEY, next);
    return next;
  } catch {
    return newGuestDeviceHistorySourceId();
  }
}

/** Keep the explicit-import payload stable across a safe retry in this browser. */
export function guestDeviceHistoryExportedAt(
  storage = browserLocalStorage(),
  now = new Date(),
): string {
  try {
    const existing = storage?.getItem(GUEST_DEVICE_HISTORY_EXPORTED_AT_KEY) ?? "";
    if (existing && !Number.isNaN(new Date(existing).getTime())) return existing;
    const next = now.toISOString();
    storage?.setItem(GUEST_DEVICE_HISTORY_EXPORTED_AT_KEY, next);
    return next;
  } catch {
    return now.toISOString();
  }
}

function sortDeviceLocalRecords(records: DeviceLocalRecord[]): DeviceLocalRecord[] {
  return [...records].sort((left, right) => right.updated_at - left.updated_at);
}

/**
 * IndexedDB is the primary device cache. Some embedded browsers expose it but
 * reject opening a database; this small same-origin fallback keeps a record
 * visible on the current device instead of turning a temporary cache failure
 * into an apparently ignored click. The key contains only the opaque account
 * scope, never a tenant or user identifier.
 */
function readLocalRecordFallback(scope: string, resource: string): DeviceLocalRecord[] {
  const storage = browserLocalStorage();
  if (!storage) return [];
  try {
    const value = JSON.parse(storage.getItem(localRecordFallbackKey(scope, resource)) ?? "null") as unknown;
    return Array.isArray(value) ? sortDeviceLocalRecords(value.filter(isDeviceLocalRecord)) : [];
  } catch {
    return [];
  }
}

function writeLocalRecordFallback(scope: string, resource: string, record: DeviceLocalRecord): boolean {
  const storage = browserLocalStorage();
  if (!storage) return false;
  try {
    const next = sortDeviceLocalRecords([
      record,
      ...readLocalRecordFallback(scope, resource).filter((current) => current.id !== record.id),
    ]);
    storage.setItem(localRecordFallbackKey(scope, resource), JSON.stringify(next));
    return true;
  } catch {
    return false;
  }
}

function removeLocalRecordFallback(scope: string, resource: string, id: string): boolean {
  const storage = browserLocalStorage();
  if (!storage) return false;
  try {
    const key = localRecordFallbackKey(scope, resource);
    const next = readLocalRecordFallback(scope, resource).filter((record) => record.id !== id);
    if (next.length) storage.setItem(key, JSON.stringify(next));
    else storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

function mergeLocalRecordCaches(primary: DeviceLocalRecord[], fallback: DeviceLocalRecord[]): DeviceLocalRecord[] {
  const byId = new Map<string, DeviceLocalRecord>();
  for (const record of fallback) byId.set(record.id, record);
  for (const record of primary) byId.set(record.id, record);
  return sortDeviceLocalRecords([...byId.values()]);
}

function outboxKey(scope: string, idempotencyKey: string): string {
  return `${scope}\u0000${idempotencyKey}`;
}

function recordAliasKey(scope: string, resource: string, localRecordId: string): string {
  return `${scope}\u0000${resource}\u0000${localRecordId}`;
}

function toSnakeCase(value: string): string {
  return value.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
}

function toCamelCase(value: string): string {
  return value.replace(/_([a-z0-9])/g, (_, character: string) => character.toUpperCase());
}

function newLocalId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `local_${crypto.randomUUID().replaceAll("-", "")}`;
  }
  return `local_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function opaqueFallback(value: string): string {
  // Web Crypto is available in the supported browsers. Keep the rare fallback
  // one-way as well: a reversible encoding would expose the account id in IDB.
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

async function accountScope(userId: string): Promise<string> {
  if (typeof crypto !== "undefined" && crypto.subtle) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(userId));
    const suffix = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `account:${suffix}`;
  }
  return `account:${opaqueFallback(userId)}`;
}

type BrowserScopeLookup = {
  cacheable: boolean;
  scope: string;
};

type PendingBrowserScope = {
  controller: AbortController;
  generation: number;
  request: Promise<BrowserScopeLookup>;
};

let cachedBrowserScope: { expiresAt: number; scope: string } | null = null;
let pendingBrowserScope: PendingBrowserScope | null = null;
let browserScopeGeneration = 0;
let browserScopeInvalidationQueued = false;
let browserScopeUnavailableUntil = 0;

/**
 * A short authoritative session result may be reused by several resource
 * hooks in one rendered page. Explicit foreground checks clear it first, so
 * an account switch in another tab cannot retain a prior account partition.
 */
export function invalidateBrowserRecordScope(): void {
  cachedBrowserScope = null;
  browserScopeUnavailableUntil = 0;
  if (browserScopeInvalidationQueued) return;
  browserScopeInvalidationQueued = true;
  queueMicrotask(() => {
    browserScopeInvalidationQueued = false;
  });
  browserScopeGeneration += 1;
  const pending = pendingBrowserScope;
  if (pending) {
    pending.controller.abort();
    if (pendingBrowserScope === pending) pendingBrowserScope = null;
  }
}

/**
 * A stable, opaque per-account partition prevents a shared browser from
 * showing one account's local-only records to another account. Guest records
 * intentionally remain a separate migration source and are never auto-synced.
 */
export async function resolveBrowserRecordScope(timeoutMs = BROWSER_SCOPE_REQUEST_TIMEOUT_MS): Promise<string> {
  if (typeof window === "undefined") return "guest";
  const now = Date.now();
  if (cachedBrowserScope && cachedBrowserScope.expiresAt > now) return cachedBrowserScope.scope;
  // A 429 or transport failure is never treated as an authenticated or
  // authoritative guest result. It does, however, need a tiny backoff so a
  // page with several resources cannot amplify one failed lookup into a
  // request storm that keeps the real login endpoint rate-limited.
  if (browserScopeUnavailableUntil > now) return "guest";
  const generation = browserScopeGeneration;
  if (!pendingBrowserScope || pendingBrowserScope.generation !== generation) {
    const controller = new AbortController();
    const request = (async (): Promise<BrowserScopeLookup> => {
      let timeout: ReturnType<typeof setTimeout> | undefined;
      try {
        const response = await Promise.race<Response | null>([
          // Local-only records are partitioned by account. A Google callback or
          // account switch must therefore read the current database-backed
          // session, never a short-lived browser cache from the prior account.
          fetch("/api/auth/get-session?disableCookieCache=true", { credentials: "same-origin", signal: controller.signal }),
          new Promise<null>((resolve) => {
            timeout = setTimeout(() => {
              controller.abort();
              resolve(null);
            }, timeoutMs);
          }),
        ]);
        if (!response) return { cacheable: false, scope: "guest" };
        // A normal unsigned response is authoritative, unlike a timeout,
        // rate-limit, or other transport failure. Reusing this short guest
        // result prevents each independent resource panel from amplifying the
        // same 401 into another session lookup. Login navigation and explicit
        // foreground checks both invalidate it before an account can change.
        if (response.status === 401) return { cacheable: true, scope: "guest" };
        if (!response.ok) return { cacheable: false, scope: "guest" };
        const session = (await response.json()) as unknown;
        const user = isRecord(session) && isRecord(session.user) ? session.user : null;
        const userId = user && typeof user.id === "string" && user.id.length > 0 ? user.id : null;
        return { cacheable: true, scope: userId ? await accountScope(userId) : "guest" };
      } catch {
        return { cacheable: false, scope: "guest" };
      } finally {
        if (timeout !== undefined) clearTimeout(timeout);
      }
    })();
    pendingBrowserScope = { controller, generation, request };
  }
  const pending = pendingBrowserScope;
  if (!pending) return "guest";
  try {
    const resolved = await pending.request;
    if (resolved.cacheable && pending.generation === browserScopeGeneration) {
      cachedBrowserScope = {
        expiresAt: Date.now() + BROWSER_SCOPE_CACHE_TTL_MS,
        scope: resolved.scope,
      };
      browserScopeUnavailableUntil = 0;
    } else if (pending.generation === browserScopeGeneration) {
      browserScopeUnavailableUntil = Date.now() + BROWSER_SCOPE_UNAVAILABLE_BACKOFF_MS;
    }
    return resolved.scope;
  } finally {
    // Collapse concurrent component initialization. An explicit invalidation
    // owns a newer generation and may already have replaced this request.
    if (pendingBrowserScope === pending) pendingBrowserScope = null;
  }
}

export function createDeviceLocalRecord(payload: Record<string, unknown>, now = Date.now(), id = newLocalId()): DeviceLocalRecord {
  const fields: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (!tenantFieldNames.has(key)) fields[toSnakeCase(key)] = value;
  }
  return {
    ...fields,
    [LOCAL_MARKER]: true,
    created_at: now,
    id,
    updated_at: now,
  } as DeviceLocalRecord;
}

/**
 * Device records store display fields in snake_case, while the tenant API
 * accepts the normal browser request shape. This recovers only the original
 * record fields; cache metadata and any tenant-shaped field stay on-device.
 */
export function deviceLocalRecordRequestPayload(record: DeviceLocalRecord): Record<string, unknown> {
  const metadata = new Set([LOCAL_MARKER, "created_at", "id", "updated_at"]);
  const payload: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(record)) {
    if (metadata.has(key) || tenantFieldNames.has(key)) continue;
    payload[toCamelCase(key)] = value;
  }
  return payload;
}

/**
 * Build an explicit import candidate from this browser's anonymous records.
 * It never reads account-scoped records, never reads files, and deliberately
 * omits photo references because local image bytes have no safe cloud mapping.
 * Applying the envelope remains a separate, verified-account confirmation.
 */
export async function buildGuestDeviceHistoryEnvelope(
  now = new Date(),
  sourceInstanceId = guestDeviceHistorySourceId(),
  exportedAt = guestDeviceHistoryExportedAt(browserLocalStorage(), now),
): Promise<GuestDeviceHistoryEnvelope> {
  const modules: GuestDeviceHistoryEnvelope["modules"] = {};

  for (const { module, resource } of guestDeviceHistoryResources) {
    const records = await readDeviceLocalRecords("guest", resource);
    const rows = records
      .filter((record) => record.id.startsWith("local_"))
      .map((record) => {
        const payload = deviceLocalRecordRequestPayload(record);
        if (module === "food" || module === "diary") delete payload.photoObjectId;
        return { id: record.id, ...payload };
      });
    if (rows.length) modules[module] = rows;
  }

  return {
    sourceInstanceId,
    sourceSchemaVersion: 1,
    exportedAt,
    modules,
    imageManifest: [],
  };
}

export type GuestDeviceHistoryRestoreResult = {
  accepted: boolean;
  restored: number;
  skipped: number;
};

/**
 * The retired host's IndexedDB is a different browser origin. Restore its
 * bounded anonymous envelope into this origin's guest partition only; account
 * partitions, outbox actions, image bytes, and source records are untouched.
 */
export async function restoreLegacyGuestDeviceHistory(
  value: unknown,
): Promise<GuestDeviceHistoryRestoreResult> {
  const envelope = parseLegacyDeviceHistoryPayload(value);
  if (!envelope) return { accepted: false, restored: 0, skipped: 0 };

  let restored = 0;
  let skipped = 0;
  const now = Date.now();
  for (const { module, resource } of guestDeviceHistoryResources) {
    const rows = envelope.modules[module] ?? [];
    const existingIds = new Set((await readDeviceLocalRecords("guest", resource)).map((record) => record.id));
    for (const row of rows) {
      const id = typeof row.id === "string" ? row.id : "";
      if (!id || existingIds.has(id)) {
        skipped += 1;
        continue;
      }
      const payload: Record<string, unknown> = {};
      for (const [key, item] of Object.entries(row)) {
        if (
          key !== "id"
          && key !== "photoObjectId"
          && key !== "photo_object_id"
          && !tenantFieldNames.has(key)
        ) payload[key] = item;
      }
      await writeDeviceLocalRecord("guest", resource, createDeviceLocalRecord(payload, now, id));
      existingIds.add(id);
      restored += 1;
    }
  }
  return { accepted: true, restored, skipped };
}

/**
 * This read-only count lets the normal workbench make an existing anonymous
 * history recoverable after sign-in without manufacturing an import envelope
 * or touching an account-scoped cache. The actual transfer remains the
 * separate preview-and-confirm flow on the account page.
 */
export async function countGuestDeviceHistoryRecords(): Promise<number> {
  let count = 0;
  for (const { resource } of guestDeviceHistoryResources) {
    const records = await readDeviceLocalRecords("guest", resource);
    count += records.filter((record) => record.id.startsWith("local_")).length;
  }
  return count;
}

/**
 * Older sensitive records may have been safely retained in an account's
 * device cache before a consent-pending outbox existed. Once the account has
 * passed the server consent gate, this creates a stable, account-scoped retry
 * action so those records can join normal replay without moving guest data.
 */
export function createDeviceLocalRecoveryOutboxAction(
  resource: string,
  record: DeviceLocalRecord,
): DeviceOutboxAction | null {
  if (!/^[a-z-]+$/.test(resource) || !record.id.startsWith("local_")) return null;
  const payload = deviceLocalRecordRequestPayload(record);
  if (!Object.keys(payload).length) return null;
  return {
    createdAt: record.created_at,
    endpoint: `/api/mydairy/${resource}`,
    idempotencyKey: `local-recovery-${resource}-${record.id}`,
    localRecordId: record.id,
    method: "POST",
    payload,
    queuedAt: record.created_at,
    requiresSensitiveConsent: true,
  };
}

export function isDeviceLocalRecord(value: unknown): value is DeviceLocalRecord {
  return isRecord(value) && value[LOCAL_MARKER] === true && typeof value.id === "string";
}

function isDeviceOutboxAction(value: unknown): value is DeviceOutboxAction {
  return isRecord(value)
    && typeof value.endpoint === "string"
    && value.endpoint.startsWith("/api/mydairy/")
    && value.method === "POST"
    && isRecord(value.payload)
    && typeof value.idempotencyKey === "string"
    && Number.isFinite(value.createdAt)
    && Number.isFinite(value.queuedAt)
    && (value.localRecordId === undefined || typeof value.localRecordId === "string")
    && (value.requiresSensitiveConsent === undefined || value.requiresSensitiveConsent === true)
    && (value.parentReferences === undefined
      || (Array.isArray(value.parentReferences) && value.parentReferences.every(isDeviceOutboxParentReference)));
}

function isDeviceOutboxParentReference(value: unknown): value is DeviceOutboxParentReference {
  return isRecord(value)
    && (value.field === "habitId" || value.field === "goalId")
    && (value.resource === "habits" || value.resource === "savings-goals")
    && typeof value.localRecordId === "string"
    && value.localRecordId.length > 0;
}

function sanitizeOutboxAction(action: DeviceOutboxAction): DeviceOutboxAction {
  const payload: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(action.payload)) {
    if (!tenantFieldNames.has(key)) payload[key] = value;
  }
  const parentReferences = action.parentReferences
    ?.filter(isDeviceOutboxParentReference)
    .map((reference) => ({ ...reference }));
  const consent = action.requiresSensitiveConsent === true ? { requiresSensitiveConsent: true as const } : {};
  return parentReferences?.length
    ? { ...action, ...consent, parentReferences, payload }
    : { ...action, ...consent, payload };
}

function normalizeDeviceOutboxActions(actions: unknown[]): DeviceOutboxAction[] {
  const byIdempotencyKey = new Map<string, DeviceOutboxAction>();
  for (const candidate of actions) {
    if (!isDeviceOutboxAction(candidate)) continue;
    byIdempotencyKey.set(candidate.idempotencyKey, sanitizeOutboxAction(candidate));
  }
  return [...byIdempotencyKey.values()].sort((left, right) => left.queuedAt - right.queuedAt);
}

/**
 * Mirrors the record fallback for embedded browsers that expose IndexedDB but
 * reject opening it. The key is still account-scoped and opaque; a guest
 * action is never promoted to a later account by the resource client.
 */
function readDeviceOutboxFallback(scope: string): DeviceOutboxAction[] {
  const storage = browserLocalStorage();
  if (!storage) return [];
  try {
    const parsed = JSON.parse(storage.getItem(deviceOutboxFallbackKey(scope)) ?? "null") as unknown;
    return Array.isArray(parsed) ? normalizeDeviceOutboxActions(parsed) : [];
  } catch {
    return [];
  }
}

function writeDeviceOutboxFallback(scope: string, actions: DeviceOutboxAction[]): boolean {
  const storage = browserLocalStorage();
  if (!storage) return false;
  try {
    const next = normalizeDeviceOutboxActions(actions);
    const key = deviceOutboxFallbackKey(scope);
    if (next.length) storage.setItem(key, JSON.stringify(next));
    else storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

function removeDeviceOutboxFallback(scope: string, idempotencyKeys: string[]): boolean {
  const storage = browserLocalStorage();
  if (!storage) return false;
  try {
    const removed = new Set(idempotencyKeys);
    return writeDeviceOutboxFallback(
      scope,
      readDeviceOutboxFallback(scope).filter((action) => !removed.has(action.idempotencyKey)),
    );
  } catch {
    return false;
  }
}

function appendDeviceOutboxFallback(scope: string, action: DeviceOutboxAction): DeviceOutboxAction[] | null {
  const current = readDeviceOutboxFallback(scope);
  if (current.some((entry) => entry.idempotencyKey === action.idempotencyKey)) return current;
  const next = normalizeDeviceOutboxActions([...current, action]);
  return writeDeviceOutboxFallback(scope, next) ? next : null;
}

/**
 * Parent aliases share the same opaque account scope as their local outbox.
 * They keep a queued child safe when an embedded browser exposes IndexedDB
 * but refuses to open it after the parent reaches the cloud.
 */
function readDeviceRecordAliasFallback(scope: string, resource: string, localRecordId: string): string | null {
  const storage = browserLocalStorage();
  if (!storage) return null;
  try {
    const remoteRecordId = storage.getItem(deviceRecordAliasFallbackKey(scope, resource, localRecordId));
    return typeof remoteRecordId === "string" && remoteRecordId.length > 0 ? remoteRecordId : null;
  } catch {
    return null;
  }
}

function writeDeviceRecordAliasFallback(
  scope: string,
  resource: string,
  localRecordId: string,
  remoteRecordId: string,
): boolean {
  const storage = browserLocalStorage();
  if (!storage) return false;
  try {
    storage.setItem(deviceRecordAliasFallbackKey(scope, resource, localRecordId), remoteRecordId);
    return true;
  } catch {
    return false;
  }
}

const childResourceDependencies = {
  "habit-checkins": { field: "habitId", resource: "habits" },
  "savings-transactions": { field: "goalId", resource: "savings-goals" },
} as const satisfies Record<string, Pick<DeviceOutboxParentReference, "field" | "resource">>;

function isChildResourceWithDependency(resource: string): resource is keyof typeof childResourceDependencies {
  return Object.hasOwn(childResourceDependencies, resource);
}

function resourceFromOutboxAction(action: DeviceOutboxAction): string | null {
  const match = /^\/api\/mydairy\/([a-z-]+)$/.exec(action.endpoint);
  return match?.[1] ?? null;
}

export function mergeWithDeviceLocalRecords<T extends { id: string }>(remote: T[], local: T[]): T[] {
  const remoteIds = new Set(remote.map((record) => record.id));
  return [...local.filter((record) => !remoteIds.has(record.id)), ...remote];
}

export async function readDeviceLocalRecords(scope: string, resource: string): Promise<DeviceLocalRecord[]> {
  const fallback = readLocalRecordFallback(scope, resource);
  if (!canUseIndexedDb()) return fallback;
  try {
    const database = await openRecordDatabase();
    try {
      const transaction = database.transaction(RECORD_STORE, "readonly");
      const index = transaction.objectStore(RECORD_STORE).index(SCOPE_RESOURCE_INDEX);
      const rows = await requestValue(index.getAll(IDBKeyRange.only([scope, resource]))) as CachedRecordRow[];
      await transactionDone(transaction);
      return mergeLocalRecordCaches(rows.map((row) => row.record).filter(isDeviceLocalRecord), fallback);
    } finally {
      database.close();
    }
  } catch {
    return fallback;
  }
}

export async function writeDeviceLocalRecord(scope: string, resource: string, record: DeviceLocalRecord): Promise<void> {
  if (!canUseIndexedDb()) {
    if (writeLocalRecordFallback(scope, resource, record)) return;
    throw new Error("Device storage is unavailable.");
  }
  try {
    const database = await openRecordDatabase();
    try {
      const transaction = database.transaction(RECORD_STORE, "readwrite");
      transaction.objectStore(RECORD_STORE).put({
        id: record.id,
        key: cacheKey(scope, resource, record.id),
        record,
        resource,
        scope,
        updatedAt: record.updated_at,
      } satisfies CachedRecordRow);
      await transactionDone(transaction);
    } finally {
      database.close();
    }
    // Remove a stale fallback copy only after the primary cache committed.
    removeLocalRecordFallback(scope, resource, record.id);
  } catch (error) {
    if (writeLocalRecordFallback(scope, resource, record)) return;
    throw error;
  }
}

export async function removeDeviceLocalRecord(scope: string, resource: string, id: string): Promise<void> {
  if (!canUseIndexedDb()) {
    removeLocalRecordFallback(scope, resource, id);
    return;
  }
  let indexedDbError: unknown = null;
  try {
    const database = await openRecordDatabase();
    try {
      const transaction = database.transaction(RECORD_STORE, "readwrite");
      transaction.objectStore(RECORD_STORE).delete(cacheKey(scope, resource, id));
      await transactionDone(transaction);
    } finally {
      database.close();
    }
  } catch (error) {
    indexedDbError = error;
  }
  const removedFallback = removeLocalRecordFallback(scope, resource, id);
  if (indexedDbError && !removedFallback) throw indexedDbError;
}

/**
 * A local_ value is created only by this device cache; server record IDs use a
 * different namespace. Mark it as a dependency before any storage operation
 * so a failed child-cache write can never make the immediate request send that
 * device-only parent value to the cloud database.
 */
export function deriveDeviceOutboxParentReferences(
  resource: string,
  payload: Record<string, unknown>,
): DeviceOutboxParentReference[] {
  if (!isChildResourceWithDependency(resource)) return [];
  const dependency = childResourceDependencies[resource];
  const localRecordId = payload[dependency.field];
  if (typeof localRecordId !== "string" || !localRecordId.startsWith("local_")) return [];
  const reference = { field: dependency.field, localRecordId, resource: dependency.resource } as DeviceOutboxParentReference;
  return [reference];
}

async function readDeviceRecordAlias(
  scope: string,
  resource: string,
  localRecordId: string,
): Promise<string | null> {
  const fallback = readDeviceRecordAliasFallback(scope, resource, localRecordId);
  if (!canUseIndexedDb()) return fallback;
  try {
    const database = await openRecordDatabase();
    try {
      const transaction = database.transaction(RECORD_ALIAS_STORE, "readonly");
      const row = await requestValue(
        transaction.objectStore(RECORD_ALIAS_STORE).get(recordAliasKey(scope, resource, localRecordId)),
      ) as CachedRecordAliasRow | undefined;
      await transactionDone(transaction);
      return row && typeof row.remoteRecordId === "string" && row.remoteRecordId.length > 0
        ? row.remoteRecordId
        : fallback;
    } finally {
      database.close();
    }
  } catch {
    return fallback;
  }
}

/**
 * Replays use cloud parent identifiers only after the originating parent was
 * accepted for this same opaque account. A missing alias is a harmless wait,
 * never a malformed child mutation.
 */
export async function resolveDeviceOutboxActionWithAliases(
  action: DeviceOutboxAction,
  resolveAlias: (reference: DeviceOutboxParentReference) => Promise<string | null>,
): Promise<DeviceOutboxAction | null> {
  if (!action.parentReferences?.length) return action;
  const payload = { ...action.payload };
  for (const reference of action.parentReferences) {
    const remoteRecordId = await resolveAlias(reference);
    if (!remoteRecordId) return null;
    payload[reference.field] = remoteRecordId;
  }
  return { ...action, payload };
}

export async function resolveDeviceOutboxAction(
  scope: string,
  action: DeviceOutboxAction,
): Promise<DeviceOutboxAction | null> {
  return resolveDeviceOutboxActionWithAliases(
    action,
    (reference) => readDeviceRecordAlias(scope, reference.resource, reference.localRecordId),
  );
}

/**
 * Once a local parent is accepted by the server, retain the opaque local-to-
 * cloud correspondence in the same account partition and wake its queued
 * children for a fresh replay attempt.
 */
export async function rememberDeviceOutboxRecordAlias(
  scope: string,
  action: DeviceOutboxAction,
  remoteRecordId: string,
): Promise<void> {
  const resource = resourceFromOutboxAction(action);
  if (
    (resource !== "habits" && resource !== "savings-goals")
    || !action.localRecordId
    || !remoteRecordId
  ) return;
  let saved = false;
  if (!canUseIndexedDb()) {
    saved = writeDeviceRecordAliasFallback(scope, resource, action.localRecordId, remoteRecordId);
  } else {
    try {
      const database = await openRecordDatabase();
      try {
        const transaction = database.transaction(RECORD_ALIAS_STORE, "readwrite");
        transaction.objectStore(RECORD_ALIAS_STORE).put({
          key: recordAliasKey(scope, resource, action.localRecordId),
          localRecordId: action.localRecordId,
          remoteRecordId,
          resource,
          scope,
        } satisfies CachedRecordAliasRow);
        await transactionDone(transaction);
        saved = true;
      } finally {
        database.close();
      }
    } catch {
      saved = writeDeviceRecordAliasFallback(scope, resource, action.localRecordId, remoteRecordId);
    }
  }
  if (saved && typeof window !== "undefined") window.dispatchEvent(new Event("mydairy:outbox-alias-resolved"));
}

/**
 * Outbox actions follow the same opaque account scope as local records. They
 * are deliberately separate from legacy localStorage so an action from an
 * unknown shared-browser account can never be replayed as the next account.
 */
export async function readDeviceOutbox(scope: string): Promise<DeviceOutboxAction[]> {
  const fallback = readDeviceOutboxFallback(scope);
  if (!canUseIndexedDb()) return fallback;
  try {
    const database = await openRecordDatabase();
    try {
      const transaction = database.transaction(OUTBOX_STORE, "readonly");
      const index = transaction.objectStore(OUTBOX_STORE).index(OUTBOX_SCOPE_INDEX);
      const rows = await requestValue(index.getAll(IDBKeyRange.only(scope))) as CachedOutboxRow[];
      await transactionDone(transaction);
      return normalizeDeviceOutboxActions([...fallback, ...rows.map((row) => row.action)]);
    } finally {
      database.close();
    }
  } catch {
    return fallback;
  }
}

export async function writeDeviceOutbox(scope: string, actions: DeviceOutboxAction[]): Promise<void> {
  if (!canUseIndexedDb()) {
    if (writeDeviceOutboxFallback(scope, actions)) return;
    throw new Error("Device outbox storage is unavailable.");
  }
  try {
    const database = await openRecordDatabase();
    try {
      const transaction = database.transaction(OUTBOX_STORE, "readwrite");
      const store = transaction.objectStore(OUTBOX_STORE);
      const index = store.index(OUTBOX_SCOPE_INDEX);
      const existingKeys = await requestValue(index.getAllKeys(IDBKeyRange.only(scope)));
      for (const key of existingKeys) store.delete(key);
      for (const action of normalizeDeviceOutboxActions(actions)) {
        store.put({
          action,
          key: outboxKey(scope, action.idempotencyKey),
          queuedAt: action.queuedAt,
          scope,
        } satisfies CachedOutboxRow);
      }
      await transactionDone(transaction);
    } finally {
      database.close();
    }
    // A successful replacement write makes any degraded-mode snapshot stale.
    writeDeviceOutboxFallback(scope, []);
  } catch (error) {
    if (writeDeviceOutboxFallback(scope, actions)) return;
    throw error;
  }
}

/**
 * Removes only acknowledged actions for one opaque account scope. This avoids
 * a resource-specific replay overwriting queued work owned by a different
 * workbench module in the same browser.
 */
export async function removeDeviceOutboxActions(scope: string, idempotencyKeys: string[]): Promise<void> {
  const keys = [...new Set(idempotencyKeys.filter((value) => typeof value === "string" && value.length > 0))];
  if (!keys.length) return;
  if (!canUseIndexedDb()) {
    removeDeviceOutboxFallback(scope, keys);
    return;
  }
  let indexedDbError: unknown = null;
  try {
    const database = await openRecordDatabase();
    try {
      const transaction = database.transaction(OUTBOX_STORE, "readwrite");
      const store = transaction.objectStore(OUTBOX_STORE);
      for (const idempotencyKey of keys) store.delete(outboxKey(scope, idempotencyKey));
      await transactionDone(transaction);
    } finally {
      database.close();
    }
  } catch (error) {
    indexedDbError = error;
  }
  const removedFallback = removeDeviceOutboxFallback(scope, keys);
  if (indexedDbError && !removedFallback) throw indexedDbError;
}

export async function appendDeviceOutbox(scope: string, action: DeviceOutboxAction): Promise<DeviceOutboxAction[]> {
  if (!isDeviceOutboxAction(action)) throw new Error("Invalid device outbox action.");
  if (!canUseIndexedDb()) {
    const fallback = appendDeviceOutboxFallback(scope, action);
    if (fallback) return fallback;
    throw new Error("Device outbox storage is unavailable.");
  }
  try {
    const database = await openRecordDatabase();
    try {
      const transaction = database.transaction(OUTBOX_STORE, "readwrite");
      const store = transaction.objectStore(OUTBOX_STORE);
      const key = outboxKey(scope, action.idempotencyKey);
      const existing = await requestValue(store.get(key));
      if (!existing) {
        const sanitized = sanitizeOutboxAction(action);
        store.put({
          action: sanitized,
          key,
          queuedAt: sanitized.queuedAt,
          scope,
        } satisfies CachedOutboxRow);
      }
      await transactionDone(transaction);
    } finally {
      database.close();
    }
    removeDeviceOutboxFallback(scope, [action.idempotencyKey]);
    return readDeviceOutbox(scope);
  } catch (error) {
    const fallback = appendDeviceOutboxFallback(scope, action);
    if (fallback) return fallback;
    throw error;
  }
}
