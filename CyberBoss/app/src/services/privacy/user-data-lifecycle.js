"use strict";

// CB-800 / AC-029: scoped export, scoped deletion, crypto-shred, tombstone.
//
// Both halves fail closed on scope. Export builds only from rows the caller
// owns and then re-checks the assembled result before it is handed back, so a
// query written without its WHERE clause in some later change is caught by the
// second gate rather than shipped to a user. Deletion runs the frozen plan
// step by step, writes an immutable receipt for each step, and can resume an
// interrupted request without repeating a step that already succeeded.
//
// The crypto-shred is the point of no return. Once the wrapped user DEK is
// destroyed every residual ciphertext is unreadable; that step is never undone
// and never re-run against a user who has already passed it.

const { createHash, randomUUID } = require("node:crypto");

const {
  DeletionPlanError,
  buildDeletionPlan,
  resumePoint,
  validateDeletionReceipts,
} = require("./deletion-plan");
const { assertKeyBelongsToUser } = require("../canonical/object-key");

const EXPORT_SCHEMA = "cyberboss.user-export-manifest.v1";
const USER_ID_PATTERN = /^usr_[A-Za-z0-9_-]{20,}$/;

// Tables a user may export from, and the column that scopes each of them.
// Anything not named here is not exportable, so adding a table does not
// silently widen an export.
const EXPORTABLE = Object.freeze([
  Object.freeze({ table: "user_settings", scope: "user_id" }),
  Object.freeze({ table: "imports", scope: "user_id" }),
  Object.freeze({ table: "profile_facts", scope: "user_id" }),
  Object.freeze({ table: "profile_decisions", scope: "user_id" }),
  Object.freeze({ table: "activity_daily", scope: "user_id" }),
  Object.freeze({ table: "consent_events", scope: "user_id" }),
]);

// Never exported, with the reason recorded in the manifest. Handing a user
// their own wrapped key or credential ciphertext turns an export into a
// credential-exfiltration path the moment the export object leaks.
const EXCLUDED_FROM_EXPORT = Object.freeze({
  user_data_keys: "wrapped_key_material_is_never_exported",
  provider_credentials: "credential_ciphertext_is_never_exported",
  setup_tokens: "single_use_authentication_material",
  web_sessions: "live_session_material",
  model_budget_reservations: "rebuildable_operational_state",
});

class LifecycleError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "LifecycleError";
    this.code = code;
    this.detail = detail;
  }
}

function sha256Json(value) {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function requireUserId(userId) {
  if (typeof userId !== "string" || !USER_ID_PATTERN.test(userId)) {
    throw new LifecycleError("LIFECYCLE_USER_ID_INVALID", "userId");
  }
  return userId;
}

function buildUserExportManifest({
  userId,
  generatedAt,
  factRefs = [],
  objectRefs = [],
  recordCounts = {},
}) {
  requireUserId(userId);
  const timestamp = new Date(generatedAt);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new LifecycleError("LIFECYCLE_GENERATED_AT_INVALID", "generatedAt");
  }
  const facts = [...new Set(factRefs.map(String))].sort();
  const objects = [...new Set(objectRefs.map(String))].sort();
  // Every object named in an export must sit under this user's prefix.
  for (const ref of objects) {
    assertKeyBelongsToUser(ref, userId);
  }
  const payload = {
    schema: EXPORT_SCHEMA,
    userId,
    generatedAt: timestamp.toISOString(),
    factRefs: facts,
    objectRefs: objects,
    recordCounts: Object.fromEntries(
      Object.entries(recordCounts)
        .map(([table, count]) => [String(table), Number(count) || 0])
        .sort(([a], [b]) => a.localeCompare(b)),
    ),
    excluded: EXCLUDED_FROM_EXPORT,
  };
  return Object.freeze({ ...payload, manifestSha256: sha256Json(payload) });
}

// Reads only rows the caller owns. The scope is applied in the query and
// re-checked on the assembled result.
class SqliteUserExporter {
  constructor({ database, now = () => new Date().toISOString() }) {
    if (!database || typeof database.prepare !== "function") {
      throw new LifecycleError("LIFECYCLE_DATABASE_REQUIRED", "database");
    }
    this.database = database;
    this.now = now;
  }

  #tableExists(table) {
    return Boolean(
      this.database
        .prepare("SELECT 1 AS present FROM sqlite_schema WHERE type='table' AND name=?")
        .get(table),
    );
  }

  export({ userId, objectRefs = [] }) {
    requireUserId(userId);
    const data = {};
    const recordCounts = {};
    for (const { table, scope } of EXPORTABLE) {
      if (!this.#tableExists(table)) {
        continue;
      }
      const rows = this.database
        .prepare(`SELECT * FROM ${table} WHERE ${scope}=? ORDER BY rowid`)
        .all(userId);
      // Second gate: prove on the assembled rows, not only in the query text,
      // that nothing belonging to another user came back.
      for (const row of rows) {
        if (row[scope] !== userId) {
          throw new LifecycleError("EXPORT_SCOPE_VIOLATION", table);
        }
      }
      data[table] = rows;
      recordCounts[table] = rows.length;
    }
    for (const excluded of Object.keys(EXCLUDED_FROM_EXPORT)) {
      if (Object.hasOwn(data, excluded)) {
        throw new LifecycleError("EXPORT_EXCLUDED_TABLE_PRESENT", excluded);
      }
    }
    const manifest = buildUserExportManifest({
      userId,
      generatedAt: this.now(),
      objectRefs,
      recordCounts,
    });
    return Object.freeze({ manifest, data: Object.freeze(data) });
  }

  recordReceipt({ userId, manifest, objectRef = null }) {
    requireUserId(userId);
    if (!manifest || manifest.userId !== userId) {
      throw new LifecycleError("EXPORT_MANIFEST_SCOPE_VIOLATION", "manifest");
    }
    const exportId = `exp_${randomUUID().replaceAll("-", "")}`;
    const total = Object.values(manifest.recordCounts).reduce((sum, count) => sum + count, 0);
    this.database
      .prepare(
        `INSERT INTO export_receipts(
           export_id, user_id, manifest_sha256, object_ref, record_count, generated_at
         ) VALUES (?,?,?,?,?,?)`,
      )
      .run(exportId, userId, manifest.manifestSha256, objectRef, total, manifest.generatedAt);
    return Object.freeze({ exportId, manifestSha256: manifest.manifestSha256, recordCount: total });
  }
}

// Immutable, per-step, per-user receipts. A receipt for one user's request can
// never be read as satisfying another user's step.
class SqliteDeletionReceiptStore {
  constructor({ database, now = () => new Date().toISOString() }) {
    if (!database || typeof database.prepare !== "function") {
      throw new LifecycleError("LIFECYCLE_DATABASE_REQUIRED", "database");
    }
    this.database = database;
    this.now = now;
  }

  get({ userId, idempotencyKey }) {
    const row = this.database
      .prepare(
        `SELECT idempotency_key, request_id, step_id, user_id, action, status,
                result_sha256, irreversible, occurred_at
         FROM deletion_receipts WHERE idempotency_key=? AND user_id=?`,
      )
      .get(idempotencyKey, userId);
    if (!row) {
      return null;
    }
    return Object.freeze({
      id: row.step_id,
      requestId: row.request_id,
      userId: row.user_id,
      action: row.action,
      status: row.status,
      resultSha256: row.result_sha256,
      irreversible: Number(row.irreversible) === 1,
      occurredAt: row.occurred_at,
    });
  }

  put({ userId, requestId, step, status, resultSha256 }) {
    this.database
      .prepare(
        `INSERT INTO deletion_receipts(
           idempotency_key, request_id, step_id, user_id, action, status,
           result_sha256, irreversible, occurred_at
         ) VALUES (?,?,?,?,?,?,?,?,?)`,
      )
      .run(
        step.idempotencyKey,
        requestId,
        step.id,
        userId,
        step.action,
        status,
        resultSha256,
        step.irreversible ? 1 : 0,
        this.now(),
      );
    return this.get({ userId, idempotencyKey: step.idempotencyKey });
  }

  listForRequest({ userId, requestId }) {
    return this.database
      .prepare(
        `SELECT step_id, request_id, user_id, action, status, result_sha256,
                irreversible, occurred_at
         FROM deletion_receipts WHERE user_id=? AND request_id=? ORDER BY step_id`,
      )
      .all(userId, requestId)
      .map((row) =>
        Object.freeze({
          id: row.step_id,
          requestId: row.request_id,
          userId: row.user_id,
          action: row.action,
          status: row.status,
          resultSha256: row.result_sha256,
          irreversible: Number(row.irreversible) === 1,
          occurredAt: row.occurred_at,
        }),
      );
  }
}

// Runs the frozen plan. Resumable, idempotent, and unable to walk backwards
// over the crypto-shred.
async function executeDeletion({
  userId,
  requestId,
  receiptStore,
  handlers,
  now = () => new Date().toISOString(),
}) {
  requireUserId(userId);
  if (
    !receiptStore ||
    typeof receiptStore.get !== "function" ||
    typeof receiptStore.put !== "function"
  ) {
    throw new LifecycleError("LIFECYCLE_RECEIPT_STORE_REQUIRED", "receiptStore");
  }
  const plan = buildDeletionPlan({ userId, requestId });
  const receipts = [];

  for (const step of plan) {
    const existing = receiptStore.get({ userId, idempotencyKey: step.idempotencyKey });
    if (existing && existing.status === "succeeded" && existing.userId === userId) {
      // Already done. An irreversible step is never re-run: repeating a
      // crypto-shred is at best a no-op and at worst destroys a key that was
      // legitimately re-issued after this request began.
      receipts.push(existing);
      continue;
    }
    const handler = handlers && handlers[step.action];
    if (typeof handler !== "function") {
      throw new LifecycleError("DELETION_HANDLER_MISSING", step.action);
    }
    const result = await handler({
      userId,
      requestId,
      action: step.action,
      idempotencyKey: step.idempotencyKey,
      occurredAt: now(),
    });
    receipts.push(
      receiptStore.put({
        userId,
        requestId,
        step,
        status: "succeeded",
        resultSha256: sha256Json(result ?? null),
      }),
    );
  }

  if (!validateDeletionReceipts(plan, receipts)) {
    throw new LifecycleError("DELETION_RECEIPTS_INCOMPLETE", requestId);
  }
  return Object.freeze({
    ok: true,
    userId,
    requestId,
    completedAt: now(),
    receipts: Object.freeze(receipts),
    // The canonical fact that leaves the box is a tombstone, not the data.
    tombstoneRequired: true,
  });
}

// The tombstone records that a user existed and was deleted, with no field
// that could reconstitute what was deleted.
function buildDeletionTombstone({ userId, requestId, occurredAt, receipts }) {
  requireUserId(userId);
  const timestamp = new Date(occurredAt);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new LifecycleError("LIFECYCLE_OCCURRED_AT_INVALID", "occurredAt");
  }
  const steps = (Array.isArray(receipts) ? receipts : []).map((receipt) => receipt.action).sort();
  const payload = {
    schema: "cyberboss.deletion-tombstone.v1",
    // The user id is hashed: the tombstone proves a deletion happened without
    // keeping a durable pointer to the person it happened to.
    user_ref: createHash("sha256").update(`tombstone ${userId}`).digest("hex").slice(0, 32),
    request_ref: createHash("sha256").update(`tombstone ${requestId}`).digest("hex").slice(0, 32),
    occurred_at: timestamp.toISOString(),
    completed_steps: steps,
    crypto_shred_completed: steps.includes("destroy_user_data_key"),
  };
  return Object.freeze({ ...payload, tombstone_sha256: sha256Json(payload) });
}

function writeTombstone({ database, userId, phase, objectHash, occurredAt }) {
  requireUserId(userId);
  const tombstoneId = `tmb_${randomUUID().replaceAll("-", "")}`;
  database
    .prepare(
      `INSERT INTO deletion_tombstones(tombstone_id, user_id, phase, object_hash, occurred_at)
       VALUES (?,?,?,?,?)`,
    )
    .run(tombstoneId, userId, phase, objectHash ?? null, occurredAt);
  return tombstoneId;
}

module.exports = {
  DeletionPlanError,
  EXCLUDED_FROM_EXPORT,
  EXPORTABLE,
  EXPORT_SCHEMA,
  LifecycleError,
  SqliteDeletionReceiptStore,
  SqliteUserExporter,
  buildDeletionPlan,
  buildDeletionTombstone,
  buildUserExportManifest,
  executeDeletion,
  resumePoint,
  sha256Json,
  validateDeletionReceipts,
  writeTombstone,
};
