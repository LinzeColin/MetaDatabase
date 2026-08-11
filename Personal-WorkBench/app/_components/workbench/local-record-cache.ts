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
};

export type DeviceOutboxParentReference = {
  field: "habitId" | "goalId";
  localRecordId: string;
  resource: "habits" | "savings-goals";
};

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
const BROWSER_SCOPE_REQUEST_TIMEOUT_MS = 2_500;
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

function outboxKey(scope: string, idempotencyKey: string): string {
  return `${scope}\u0000${idempotencyKey}`;
}

function recordAliasKey(scope: string, resource: string, localRecordId: string): string {
  return `${scope}\u0000${resource}\u0000${localRecordId}`;
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
export async function resolveBrowserRecordScope(timeoutMs = BROWSER_SCOPE_REQUEST_TIMEOUT_MS): Promise<string> {
  if (typeof window === "undefined") return "guest";
  if (!pendingBrowserScope) {
    pendingBrowserScope = (async () => {
      const controller = new AbortController();
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
        if (!response) return "guest";
        if (!response.ok) return "guest";
        const session = (await response.json()) as unknown;
        const user = isRecord(session) && isRecord(session.user) ? session.user : null;
        const userId = user && typeof user.id === "string" && user.id.length > 0 ? user.id : null;
        return userId ? accountScope(userId) : "guest";
      } catch {
        return "guest";
      } finally {
        if (timeout !== undefined) clearTimeout(timeout);
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
  return parentReferences?.length ? { ...action, parentReferences, payload } : { ...action, payload };
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
  if (!canUseIndexedDb()) return null;
  const database = await openRecordDatabase();
  try {
    const transaction = database.transaction(RECORD_ALIAS_STORE, "readonly");
    const row = await requestValue(
      transaction.objectStore(RECORD_ALIAS_STORE).get(recordAliasKey(scope, resource, localRecordId)),
    ) as CachedRecordAliasRow | undefined;
    await transactionDone(transaction);
    return row && typeof row.remoteRecordId === "string" && row.remoteRecordId.length > 0
      ? row.remoteRecordId
      : null;
  } finally {
    database.close();
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
    || !canUseIndexedDb()
  ) return;
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
  } finally {
    database.close();
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event("mydairy:outbox-alias-resolved"));
}

/**
 * Outbox actions follow the same opaque account scope as local records. They
 * are deliberately separate from legacy localStorage so an action from an
 * unknown shared-browser account can never be replayed as the next account.
 */
export async function readDeviceOutbox(scope: string): Promise<DeviceOutboxAction[]> {
  if (!canUseIndexedDb()) return [];
  const database = await openRecordDatabase();
  try {
    const transaction = database.transaction(OUTBOX_STORE, "readonly");
    const index = transaction.objectStore(OUTBOX_STORE).index(OUTBOX_SCOPE_INDEX);
    const rows = await requestValue(index.getAll(IDBKeyRange.only(scope))) as CachedOutboxRow[];
    await transactionDone(transaction);
    return rows
      .map((row) => row.action)
      .filter(isDeviceOutboxAction)
      .sort((left, right) => left.queuedAt - right.queuedAt);
  } finally {
    database.close();
  }
}

export async function writeDeviceOutbox(scope: string, actions: DeviceOutboxAction[]): Promise<void> {
  if (!canUseIndexedDb()) throw new Error("IndexedDB is unavailable.");
  const database = await openRecordDatabase();
  try {
    const transaction = database.transaction(OUTBOX_STORE, "readwrite");
    const store = transaction.objectStore(OUTBOX_STORE);
    const index = store.index(OUTBOX_SCOPE_INDEX);
    const existingKeys = await requestValue(index.getAllKeys(IDBKeyRange.only(scope)));
    for (const key of existingKeys) store.delete(key);
    const seen = new Set<string>();
    for (const source of actions) {
      if (!isDeviceOutboxAction(source) || seen.has(source.idempotencyKey)) continue;
      seen.add(source.idempotencyKey);
      const action = sanitizeOutboxAction(source);
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
}

/**
 * Removes only acknowledged actions for one opaque account scope. This avoids
 * a resource-specific replay overwriting queued work owned by a different
 * workbench module in the same browser.
 */
export async function removeDeviceOutboxActions(scope: string, idempotencyKeys: string[]): Promise<void> {
  if (!canUseIndexedDb()) return;
  const keys = [...new Set(idempotencyKeys.filter((value) => typeof value === "string" && value.length > 0))];
  if (!keys.length) return;
  const database = await openRecordDatabase();
  try {
    const transaction = database.transaction(OUTBOX_STORE, "readwrite");
    const store = transaction.objectStore(OUTBOX_STORE);
    for (const idempotencyKey of keys) store.delete(outboxKey(scope, idempotencyKey));
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}

export async function appendDeviceOutbox(scope: string, action: DeviceOutboxAction): Promise<DeviceOutboxAction[]> {
  if (!canUseIndexedDb()) throw new Error("IndexedDB is unavailable.");
  if (!isDeviceOutboxAction(action)) throw new Error("Invalid device outbox action.");
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
  return readDeviceOutbox(scope);
}
