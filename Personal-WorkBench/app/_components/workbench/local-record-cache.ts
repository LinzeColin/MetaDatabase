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
const BROWSER_SCOPE_REQUEST_TIMEOUT_MS = 2_500;
const BROWSER_SCOPE_CACHE_TTL_MS = 5_000;
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

function localRecordFallbackKey(scope: string, resource: string): string {
  return `${LOCAL_RECORD_FALLBACK_PREFIX}\u0000${scope}\u0000${resource}`;
}

function deviceOutboxFallbackKey(scope: string): string {
  return `${DEVICE_OUTBOX_FALLBACK_PREFIX}\u0000${scope}`;
}

function browserLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
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

/**
 * A short authoritative session result may be reused by several resource
 * hooks in one rendered page. Explicit foreground checks clear it first, so
 * an account switch in another tab cannot retain a prior account partition.
 */
export function invalidateBrowserRecordScope(): void {
  cachedBrowserScope = null;
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
