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

type CachedRecordRow = {
  id: string;
  key: string;
  record: DeviceLocalRecord;
  resource: string;
  scope: string;
  updatedAt: number;
};

const DATABASE_NAME = "mydairy-device-records-v1";
const DATABASE_VERSION = 1;
const RECORD_STORE = "records";
const SCOPE_RESOURCE_INDEX = "by_scope_resource";
const LOCAL_MARKER = "__mydairy_device_local_v1";
const tenantFieldNames = new Set(["userId", "user_id", "ownerId", "owner_id", "tenantId", "tenant_id"]);

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
      const store = database.objectStoreNames.contains(RECORD_STORE)
        ? request.transaction?.objectStore(RECORD_STORE)
        : database.createObjectStore(RECORD_STORE, { keyPath: "key" });
      if (store && !store.indexNames.contains(SCOPE_RESOURCE_INDEX)) {
        store.createIndex(SCOPE_RESOURCE_INDEX, ["scope", "resource"], { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Unable to open device record cache."));
  });
}

function cacheKey(scope: string, resource: string, id: string): string {
  return `${scope}\u0000${resource}\u0000${id}`;
}

function toSnakeCase(value: string): string {
  return value.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
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

let pendingBrowserScope: Promise<string> | null = null;

/**
 * A stable, opaque per-account partition prevents a shared browser from
 * showing one account's local-only records to another account. Guest records
 * intentionally remain a separate migration source and are never auto-synced.
 */
export async function resolveBrowserRecordScope(): Promise<string> {
  if (typeof window === "undefined") return "guest";
  if (!pendingBrowserScope) {
    pendingBrowserScope = (async () => {
      try {
        const response = await fetch("/api/auth/get-session", { credentials: "same-origin" });
        if (!response.ok) return "guest";
        const session = (await response.json()) as unknown;
        const user = isRecord(session) && isRecord(session.user) ? session.user : null;
        const userId = user && typeof user.id === "string" && user.id.length > 0 ? user.id : null;
        return userId ? accountScope(userId) : "guest";
      } catch {
        return "guest";
      }
    })();
  }
  const request = pendingBrowserScope;
  try {
    return await request;
  } finally {
    // Collapse concurrent component initialization, but never retain a user
    // scope across a sign-in, sign-out, or account switch in the same tab.
    if (pendingBrowserScope === request) pendingBrowserScope = null;
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

export function isDeviceLocalRecord(value: unknown): value is DeviceLocalRecord {
  return isRecord(value) && value[LOCAL_MARKER] === true && typeof value.id === "string";
}

export function mergeWithDeviceLocalRecords<T extends { id: string }>(remote: T[], local: T[]): T[] {
  const remoteIds = new Set(remote.map((record) => record.id));
  return [...local.filter((record) => !remoteIds.has(record.id)), ...remote];
}

export async function readDeviceLocalRecords(scope: string, resource: string): Promise<DeviceLocalRecord[]> {
  if (!canUseIndexedDb()) return [];
  const database = await openRecordDatabase();
  try {
    const transaction = database.transaction(RECORD_STORE, "readonly");
    const index = transaction.objectStore(RECORD_STORE).index(SCOPE_RESOURCE_INDEX);
    const rows = await requestValue(index.getAll(IDBKeyRange.only([scope, resource]))) as CachedRecordRow[];
    await transactionDone(transaction);
    return rows
      .map((row) => row.record)
      .filter(isDeviceLocalRecord)
      .sort((left, right) => right.updated_at - left.updated_at);
  } finally {
    database.close();
  }
}

export async function writeDeviceLocalRecord(scope: string, resource: string, record: DeviceLocalRecord): Promise<void> {
  if (!canUseIndexedDb()) throw new Error("IndexedDB is unavailable.");
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
}

export async function removeDeviceLocalRecord(scope: string, resource: string, id: string): Promise<void> {
  if (!canUseIndexedDb()) return;
  const database = await openRecordDatabase();
  try {
    const transaction = database.transaction(RECORD_STORE, "readwrite");
    transaction.objectStore(RECORD_STORE).delete(cacheKey(scope, resource, id));
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}
