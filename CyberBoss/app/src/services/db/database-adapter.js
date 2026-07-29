"use strict";

const {
  createCipheriv,
  createDecipheriv,
  createHash,
  createHmac,
  randomBytes,
} = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { DatabaseSync } = require("node:sqlite");

const { assertTransition } = require("../jobs/job-state-machine");

const MIGRATION_ROOT = path.resolve(__dirname, "../../../migrations");
const MIGRATIONS = Object.freeze([
  Object.freeze({
    version: 1,
    name: "001_runtime_spool.sql",
    sourceCommit: "taskpack-v0.0.0.4",
  }),
  Object.freeze({
    version: 2,
    name: "002_cb200_retention_and_transitions.sql",
    sourceCommit: "CB-200",
  }),
  Object.freeze({
    version: 3,
    name: "003_cb220_scheduler_control.sql",
    sourceCommit: "CB-220",
  }),
  Object.freeze({
    version: 4,
    name: "004_cb230_durable_outbox.sql",
    sourceCommit: "CB-230",
  }),
  Object.freeze({
    version: 5,
    name: "005_cb240_canonical_sync.sql",
    sourceCommit: "CB-240",
  }),
  Object.freeze({
    version: 6,
    name: "006_multiuser_foundation.sql",
    sourceCommit: "CB-610",
  }),
  Object.freeze({
    version: 7,
    name: "007_cb800_lifecycle_receipts.sql",
    sourceCommit: "CB-800",
  }),
  // 文件名是 010 而版本号是 8：008/009 两份 R19 迁移已经在 migrations/ 里，但
  // 还没有登记进这张表，因此运行时并不会执行它们。版本号必须连续 1..N，所以
  // 下一个真正会被执行的版本就是 8。等 008/009 登记进来时它们顺延即可——版本
  // 到文件的映射由这张表决定，不由文件名决定。
  Object.freeze({
    version: 8,
    name: "010_owner_persona.sql",
    sourceCommit: "PANEL-2",
  }),
  Object.freeze({
    version: 9,
    name: "011_admin_login_tickets.sql",
    sourceCommit: "LOGIN-2",
  }),
  Object.freeze({
    version: 10,
    name: "012_bot_initiated_messages.sql",
    sourceCommit: "PANEL-6",
  }),
]);
const OWNER_ROLE = "owner";
const OWNER_CONSENT_VERSION = "owner-existing-account-v8";
const USER_SCOPED_LEGACY_TABLES = Object.freeze([
  "inbox_messages",
  "jobs",
  "outbox_messages",
]);
const USER_ID_PATTERN = /^usr_[A-Za-z0-9_-]{20,64}$/;
const ENVELOPE_VERSION = 1;
const NONCE_BYTES = 12;
const TAG_BYTES = 16;
const REDACTED_SENTINEL = Buffer.from([0]);
const DEFAULT_PAYLOAD_TTL_MS = 24 * 60 * 60 * 1000;
const MIN_LEASE_MS = 100;
const MAX_LEASE_MS = 10 * 60 * 1000;
const DEFAULT_OUTBOX_LEASE_MS = 10_000;
const RUNTIME_LEASE_NAME = "runtime_job";
const CONTROL_LEASE_NAME = "command_control";
const ACTIVE_JOB_STATUSES = Object.freeze(["running", "waiting_approval"]);
const SAFE_TOKEN = /^[A-Za-z0-9_.:/-]{1,160}$/;
const SAFE_REDACTED_KEY =
  /^(?:source|index|attempt|[a-z][a-z0-9_]*(?:_code|_class|_count|_ms|_enabled|_allowed|_present|_pending))$/;
const CANONICAL_EVENT_FIELDS = Object.freeze([
  "schema_version",
  "event_id",
  "occurred_at",
  "recorded_at",
  "source",
  "event_type",
  "status",
  "job_id",
  "correlation_id",
  "workspace_alias",
  "runtime",
  "input_sha256",
  "output_sha256",
  "summary_redacted",
  "evidence_refs",
  "deployed_commit",
  "record_sha256",
]);
const CANONICAL_EVIDENCE_REF =
  /^(?:private-db|r2|receipt):\/\/[A-Za-z0-9._:/-]{1,480}$/;

class RuntimeSpoolError extends Error {
  constructor(code) {
    super(code);
    this.name = "RuntimeSpoolError";
    this.code = code;
  }
}

class IntegrityConflictError extends RuntimeSpoolError {
  constructor() {
    super("INTEGRITY_CONFLICT");
    this.name = "IntegrityConflictError";
  }
}

class PayloadRedactedError extends RuntimeSpoolError {
  constructor() {
    super("PAYLOAD_REDACTED");
    this.name = "PayloadRedactedError";
  }
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function stableJson(value) {
  const seen = new Set();
  const encode = (candidate) => {
    if (
      candidate === null ||
      typeof candidate === "string" ||
      typeof candidate === "boolean"
    ) {
      return JSON.stringify(candidate);
    }
    if (typeof candidate === "number" && Number.isFinite(candidate)) {
      return JSON.stringify(candidate);
    }
    if (Array.isArray(candidate)) {
      return `[${candidate.map((item) => encode(item)).join(",")}]`;
    }
    if (candidate && typeof candidate === "object") {
      if (seen.has(candidate)) {
        throw new RuntimeSpoolError("PAYLOAD_NOT_SERIALIZABLE");
      }
      seen.add(candidate);
      const fields = Object.keys(candidate)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${encode(candidate[key])}`);
      seen.delete(candidate);
      return `{${fields.join(",")}}`;
    }
    throw new RuntimeSpoolError("PAYLOAD_NOT_SERIALIZABLE");
  };
  return encode(value);
}

function payloadBuffer(value) {
  if (Buffer.isBuffer(value)) {
    return Buffer.from(value);
  }
  if (typeof value === "string") {
    return Buffer.from(value, "utf8");
  }
  return Buffer.from(stableJson(value), "utf8");
}

function requireBoundedString(value, field, maximum = 512) {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > maximum ||
    value.includes("\u0000")
  ) {
    throw new RuntimeSpoolError(`INVALID_${field.toUpperCase()}`);
  }
  return value;
}

function requireSafeToken(value, field) {
  requireBoundedString(value, field, 160);
  if (!SAFE_TOKEN.test(value)) {
    throw new RuntimeSpoolError(`INVALID_${field.toUpperCase()}`);
  }
  return value;
}

function requireSha256(value, field) {
  if (typeof value !== "string" || !/^[0-9a-f]{64}$/.test(value)) {
    throw new RuntimeSpoolError(`INVALID_${field.toUpperCase()}`);
  }
  return value;
}

function requireKey(value, field) {
  if (!Buffer.isBuffer(value) || value.length !== 32) {
    throw new RuntimeSpoolError(`${field}_MUST_BE_32_BYTES`);
  }
  return Buffer.from(value);
}

function canonicalEventJson(value) {
  if (
    !value ||
    Array.isArray(value) ||
    typeof value !== "object"
  ) {
    throw new RuntimeSpoolError("CANONICAL_EVENT_OBJECT_REQUIRED");
  }
  const actualFields = Object.keys(value).sort();
  const expectedFields = [...CANONICAL_EVENT_FIELDS].sort();
  if (
    actualFields.length !== expectedFields.length ||
    actualFields.some((field, index) => field !== expectedFields[index])
  ) {
    throw new RuntimeSpoolError("CANONICAL_EVENT_FIELDS_INVALID");
  }
  if (value.schema_version !== 1 || value.source !== "cyberboss-cloud") {
    throw new RuntimeSpoolError("CANONICAL_EVENT_CONTRACT_INVALID");
  }
  for (const field of [
    "event_id",
    "event_type",
    "status",
    "job_id",
    "correlation_id",
    "workspace_alias",
    "runtime",
  ]) {
    requireSafeToken(value[field], field);
  }
  for (const field of ["input_sha256", "record_sha256"]) {
    requireSha256(value[field], field);
  }
  if (value.output_sha256 !== null) {
    requireSha256(value.output_sha256, "output_sha256");
  }
  for (const field of ["occurred_at", "recorded_at"]) {
    requireBoundedString(value[field], field, 32);
    const parsed = new Date(value[field]);
    if (
      !Number.isFinite(parsed.getTime()) ||
      parsed.toISOString() !== value[field]
    ) {
      throw new RuntimeSpoolError(`INVALID_${field.toUpperCase()}`);
    }
  }
  requireBoundedString(value.summary_redacted, "summary_redacted", 192);
  if (
    !/^Job (?:state|event): [A-Za-z0-9_.:/-]{1,160}\.$/.test(
      value.summary_redacted,
    )
  ) {
    throw new RuntimeSpoolError("CANONICAL_SUMMARY_INVALID");
  }
  if (
    !Array.isArray(value.evidence_refs) ||
    value.evidence_refs.length > 16 ||
    value.evidence_refs.some(
      (reference) =>
        typeof reference !== "string" ||
        !CANONICAL_EVIDENCE_REF.test(reference),
    )
  ) {
    throw new RuntimeSpoolError("CANONICAL_EVIDENCE_REFS_INVALID");
  }
  if (
    typeof value.deployed_commit !== "string" ||
    !/^[0-9a-f]{40}$/.test(value.deployed_commit)
  ) {
    throw new RuntimeSpoolError("CANONICAL_DEPLOYED_COMMIT_INVALID");
  }
  const hashInput = {};
  for (const field of CANONICAL_EVENT_FIELDS) {
    if (field !== "record_sha256") {
      hashInput[field] = value[field];
    }
  }
  const expectedHash = sha256(Buffer.from(stableJson(hashInput), "utf8"));
  if (value.record_sha256 !== expectedHash) {
    throw new RuntimeSpoolError("CANONICAL_RECORD_HASH_INVALID");
  }
  return stableJson(value);
}

function hmacHex(key, label, fields) {
  const hmac = createHmac("sha256", key);
  hmac.update(label);
  for (const field of fields) {
    const encoded = Buffer.from(String(field), "utf8");
    const size = Buffer.alloc(4);
    size.writeUInt32BE(encoded.length);
    hmac.update(size);
    hmac.update(encoded);
  }
  return hmac.digest("hex");
}

function deriveStableIds({
  source,
  sourceAccountRef,
  sourceMessageId,
  identityKey,
}) {
  const key = requireKey(identityKey, "IDENTITY_KEY");
  const boundedSource = requireSafeToken(source, "source");
  const account = requireBoundedString(
    sourceAccountRef,
    "source_account_ref",
    1024,
  );
  const message = requireBoundedString(
    sourceMessageId,
    "source_message_id",
    1024,
  );
  const identity = [boundedSource, account, message];
  try {
    return Object.freeze({
      sourceMessageId: `srcmsg_${hmacHex(key, "source-message", identity)}`,
      inboxId: `inbox_${hmacHex(key, "inbox", identity)}`,
      correlationId: `corr_${hmacHex(key, "correlation", identity)}`,
      jobId: `job_${hmacHex(key, "job", identity)}`,
      sourceAccountHash: `acct_${hmacHex(key, "account", [
        boundedSource,
        account,
      ])}`,
    });
  } finally {
    key.fill(0);
  }
}

function requireUserId(value, field = "user_id") {
  if (typeof value !== "string" || !USER_ID_PATTERN.test(value)) {
    throw new RuntimeSpoolError(`INVALID_${field.toUpperCase()}`);
  }
  return value;
}

// The Owner user id is derived server-side from the runtime identity key alone,
// so it is stable across restarts, never guessable from a client message and
// available before any real channel credential exists.
function deriveOwnerUserId(identityKey) {
  const key = requireKey(identityKey, "IDENTITY_KEY");
  try {
    const digest = createHmac("sha256", key)
      .update("cyberboss-owner-user")
      .digest();
    return `usr_${digest.toString("base64url").slice(0, 32)}`;
  } finally {
    key.fill(0);
  }
}

function redactedJson(value = {}) {
  if (
    value === null ||
    Array.isArray(value) ||
    typeof value !== "object"
  ) {
    throw new RuntimeSpoolError("REDACTED_METADATA_OBJECT_REQUIRED");
  }
  const output = {};
  for (const key of Object.keys(value).sort()) {
    if (key.length > 64 || !SAFE_REDACTED_KEY.test(key)) {
      throw new RuntimeSpoolError("REDACTED_METADATA_KEY_INVALID");
    }
    const item = value[key];
    if (
      item === null ||
      typeof item === "boolean" ||
      (typeof item === "number" && Number.isFinite(item))
    ) {
      output[key] = item;
      continue;
    }
    if (typeof item === "string" && SAFE_TOKEN.test(item)) {
      output[key] = item;
      continue;
    }
    throw new RuntimeSpoolError("REDACTED_METADATA_VALUE_INVALID");
  }
  return stableJson(output);
}

class PayloadCipher {
  constructor(key) {
    this.key = requireKey(key, "ENCRYPTION_KEY");
  }

  encrypt(plaintext, aad) {
    const nonce = randomBytes(NONCE_BYTES);
    const cipher = createCipheriv("aes-256-gcm", this.key, nonce, {
      authTagLength: TAG_BYTES,
    });
    cipher.setAAD(Buffer.from(aad, "utf8"));
    const ciphertext = Buffer.concat([
      cipher.update(payloadBuffer(plaintext)),
      cipher.final(),
    ]);
    return Buffer.concat([
      Buffer.from([ENVELOPE_VERSION]),
      nonce,
      cipher.getAuthTag(),
      ciphertext,
    ]);
  }

  decrypt(envelope, aad) {
    if (envelope === null || envelope === undefined) {
      throw new PayloadRedactedError();
    }
    const encoded = Buffer.isBuffer(envelope)
      ? envelope
      : ArrayBuffer.isView(envelope)
        ? Buffer.from(envelope.buffer, envelope.byteOffset, envelope.byteLength)
        : null;
    if (!encoded) {
      throw new RuntimeSpoolError("PAYLOAD_ENVELOPE_INVALID");
    }
    if (
      encoded.length === REDACTED_SENTINEL.length &&
      encoded.equals(REDACTED_SENTINEL)
    ) {
      throw new PayloadRedactedError();
    }
    if (
      encoded.length < 1 + NONCE_BYTES + TAG_BYTES ||
      encoded[0] !== ENVELOPE_VERSION
    ) {
      throw new RuntimeSpoolError("PAYLOAD_ENVELOPE_INVALID");
    }
    try {
      const nonce = encoded.subarray(1, 1 + NONCE_BYTES);
      const tag = encoded.subarray(
        1 + NONCE_BYTES,
        1 + NONCE_BYTES + TAG_BYTES,
      );
      const ciphertext = encoded.subarray(1 + NONCE_BYTES + TAG_BYTES);
      const decipher = createDecipheriv("aes-256-gcm", this.key, nonce, {
        authTagLength: TAG_BYTES,
      });
      decipher.setAAD(Buffer.from(aad, "utf8"));
      decipher.setAuthTag(tag);
      return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
    } catch {
      throw new RuntimeSpoolError("PAYLOAD_AUTHENTICATION_FAILED");
    }
  }

  destroy() {
    this.key.fill(0);
  }
}

function migrationSource(name) {
  const migrationPath = path.join(MIGRATION_ROOT, name);
  const source = fs.readFileSync(migrationPath, "utf8");
  return Object.freeze({
    path: migrationPath,
    source,
    checksum: sha256(Buffer.from(source, "utf8")),
  });
}

function timestampFrom(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) {
    throw new RuntimeSpoolError("CLOCK_INVALID");
  }
  return date.toISOString();
}

function leaseExpiry(now, leaseMs) {
  if (
    !Number.isSafeInteger(leaseMs)
    || leaseMs < MIN_LEASE_MS
    || leaseMs > MAX_LEASE_MS
  ) {
    throw new RuntimeSpoolError("LEASE_DURATION_INVALID");
  }
  return new Date(new Date(now).getTime() + leaseMs).toISOString();
}

function normalizePid(value) {
  if (value === null || value === undefined) {
    return null;
  }
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new RuntimeSpoolError("LEASE_PID_INVALID");
  }
  return value;
}

class RuntimeSpoolDatabase {
  constructor({
    databasePath,
    encryptionKey,
    identityKey = encryptionKey,
    ownerUserId = null,
    now = () => new Date(),
    payloadTtlMs = DEFAULT_PAYLOAD_TTL_MS,
    faultInjector = () => {},
  }) {
    if (
      typeof databasePath !== "string" ||
      !path.isAbsolute(databasePath) ||
      databasePath === ":memory:"
    ) {
      throw new RuntimeSpoolError("ABSOLUTE_FILE_DATABASE_REQUIRED");
    }
    if (
      !Number.isSafeInteger(payloadTtlMs) ||
      payloadTtlMs <= 0 ||
      payloadTtlMs > 7 * 24 * 60 * 60 * 1000
    ) {
      throw new RuntimeSpoolError("PAYLOAD_TTL_INVALID");
    }
    const parent = path.dirname(databasePath);
    fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
    fs.chmodSync(parent, 0o700);
    if (fs.existsSync(databasePath) && fs.lstatSync(databasePath).isSymbolicLink()) {
      throw new RuntimeSpoolError("DATABASE_SYMLINK_FORBIDDEN");
    }

    this.databasePath = databasePath;
    this.identityKey = requireKey(identityKey, "IDENTITY_KEY");
    this.ownerUserId =
      ownerUserId === null
        ? deriveOwnerUserId(this.identityKey)
        : requireUserId(ownerUserId, "owner_user_id");
    this.cipher = new PayloadCipher(encryptionKey);
    this.now = now;
    this.payloadTtlMs = payloadTtlMs;
    this.faultInjector =
      typeof faultInjector === "function" ? faultInjector : () => {};
    this.closed = false;
    this.database = new DatabaseSync(databasePath);
    try {
      this.#configure();
      this.#migrate();
      this.#backfillLegacyOutboxIdentity();
      this.#bootstrapOwnerScope();
      this.#verifyRuntimeContract();
      this.#secureDatabaseFiles();
    } catch (error) {
      this.database.close();
      this.cipher.destroy();
      this.identityKey.fill(0);
      throw error;
    }
  }

  #configure() {
    this.database.exec(`
      PRAGMA busy_timeout=5000;
      PRAGMA synchronous=FULL;
      PRAGMA foreign_keys=ON;
    `);
    const current = String(
      this.database.prepare("PRAGMA journal_mode").get().journal_mode,
    ).toLowerCase();
    if (current !== "wal") {
      this.database.exec("PRAGMA journal_mode=WAL");
    }
  }

  #migrate() {
    const sources = new Map(
      MIGRATIONS.map((migration) => [
        migration.version,
        { ...migration, ...migrationSource(migration.name) },
      ]),
    );
    const schemaTable = this.database
      .prepare(
        "SELECT 1 AS present FROM sqlite_schema WHERE type='table' AND name='schema_migrations'",
      )
      .get();
    if (!schemaTable) {
      this.database.exec(sources.get(1).source);
    }

    let versions = this.database
      .prepare(
        "SELECT version, source_commit FROM schema_migrations ORDER BY version",
      )
      .all();
    if (
      versions.length === 0 ||
      versions.some(
        (row, index) =>
          Number(row.version) !== index + 1 ||
          Number(row.version) > MIGRATIONS.length,
      )
    ) {
      throw new RuntimeSpoolError("MIGRATION_HISTORY_INVALID");
    }
    if (
      Number(versions[0].version) !== 1 ||
      versions[0].source_commit !== sources.get(1).sourceCommit
    ) {
      throw new RuntimeSpoolError("MIGRATION_V1_IDENTITY_INVALID");
    }
    for (
      let nextVersion = versions.length + 1;
      nextVersion <= MIGRATIONS.length;
      nextVersion += 1
    ) {
      let migrationSourceText = sources.get(nextVersion).source;
      for (const source of sources.values()) {
        migrationSourceText = migrationSourceText.replaceAll(
          `__MIGRATION_${String(source.version).padStart(3, "0")}_CHECKSUM__`,
          source.checksum,
        );
      }
      this.database.exec(migrationSourceText);
    }

    versions = this.database
      .prepare(
        "SELECT version, source_commit, checksum_sha256 FROM schema_migrations ORDER BY version",
      )
      .all();
    if (versions.length !== MIGRATIONS.length) {
      throw new RuntimeSpoolError("MIGRATION_VERSION_UNSUPPORTED");
    }
    for (const row of versions) {
      const expected = sources.get(Number(row.version));
      if (
        !expected ||
        row.source_commit !== expected.sourceCommit ||
        row.checksum_sha256 !== expected.checksum
      ) {
        throw new RuntimeSpoolError("MIGRATION_CHECKSUM_MISMATCH");
      }
    }
  }

  #backfillLegacyOutboxIdentity() {
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const rows = this.database
        .prepare(
          `SELECT id, job_id, message_kind, dedupe_key,
                  logical_message_sha256, provider_client_id
           FROM outbox_messages
           WHERE status<>'confirmed'
             AND (
               logical_message_sha256 IS NULL
               OR provider_client_id IS NULL
             )
           ORDER BY created_at, id`,
        )
        .all();
      for (const row of rows) {
        const logicalHash = row.logical_message_sha256
          || sha256(
            Buffer.from(
              `${row.job_id}\u0000${row.message_kind}\u0000${row.dedupe_key}`,
              "utf8",
            ),
          );
        const clientId = row.provider_client_id
          || `cb-outbox-${sha256(
            Buffer.from(row.dedupe_key, "utf8"),
          ).slice(0, 32)}`;
        const result = this.database
          .prepare(
            `UPDATE outbox_messages
             SET logical_message_sha256=?, provider_client_id=?
             WHERE id=? AND status<>'confirmed'
               AND (
                 logical_message_sha256 IS NULL
                 OR provider_client_id IS NULL
               )`,
          )
          .run(logicalHash, clientId, row.id);
        if (Number(result.changes) !== 1) {
          throw new RuntimeSpoolError(
            "LEGACY_OUTBOX_IDENTITY_BACKFILL_CONFLICT",
          );
        }
      }
      const incomplete = this.database
        .prepare(
          `SELECT COUNT(*) AS count
           FROM outbox_messages
           WHERE status<>'confirmed'
             AND (
               logical_message_sha256 IS NULL
               OR provider_client_id IS NULL
             )`,
        )
        .get();
      if (Number(incomplete.count) !== 0) {
        throw new RuntimeSpoolError(
          "LEGACY_OUTBOX_IDENTITY_BACKFILL_INCOMPLETE",
        );
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  // CB-610: create the Owner row once, backfill every legacy runtime-spool row
  // to the Owner, then prove no unscoped row survives. The valid-user triggers
  // installed by migration 006 reject anything unscoped from here on.
  // Read-only precheck: after the first bootstrap there is nothing to do, so a
  // normal open must not take a write lock. Without this every process start —
  // and every concurrent worker — would contend for the same IMMEDIATE
  // transaction and could exhaust busy_timeout under load.
  #ownerScopeSettled() {
    const owner = this.database
      .prepare("SELECT role, status FROM users WHERE user_id=?")
      .get(this.ownerUserId);
    if (!owner || owner.role !== OWNER_ROLE) {
      return false;
    }
    for (const table of USER_SCOPED_LEGACY_TABLES) {
      const unscoped = this.database
        .prepare(
          `SELECT EXISTS(
             SELECT 1 FROM ${table}
             WHERE user_id IS NULL
                OR user_id=''
                OR NOT EXISTS (SELECT 1 FROM users WHERE user_id=${table}.user_id)
           ) AS present`,
        )
        .get();
      if (Number(unscoped.present) !== 0) {
        return false;
      }
    }
    return true;
  }

  #bootstrapOwnerScope() {
    if (this.#ownerScopeSettled()) {
      return;
    }
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.database
        .prepare(
          `INSERT INTO users(
             user_id, role, status, consent_version, consented_at,
             created_at, updated_at
           ) VALUES (?, ?, 'active', ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET role=excluded.role,
             updated_at=excluded.updated_at`,
        )
        .run(
          this.ownerUserId,
          OWNER_ROLE,
          OWNER_CONSENT_VERSION,
          now,
          now,
          now,
        );
      this.database
        .prepare(
          `INSERT INTO user_settings(user_id, locale, checkin_enabled, updated_at)
           VALUES (?, 'zh-CN', 0, ?)
           ON CONFLICT(user_id) DO NOTHING`,
        )
        .run(this.ownerUserId, now);

      for (const table of USER_SCOPED_LEGACY_TABLES) {
        this.database
          .prepare(
            `UPDATE ${table} SET user_id=? WHERE user_id IS NULL OR user_id=''`,
          )
          .run(this.ownerUserId);
        const unscoped = this.database
          .prepare(
            `SELECT COUNT(*) AS count FROM ${table}
             WHERE user_id IS NULL
               OR user_id=''
               OR NOT EXISTS (SELECT 1 FROM users WHERE user_id=${table}.user_id)`,
          )
          .get();
        if (Number(unscoped.count) !== 0) {
          throw new RuntimeSpoolError("OWNER_SCOPE_BACKFILL_INCOMPLETE");
        }
      }

      const foreignKeyErrors = this.database
        .prepare("PRAGMA foreign_key_check")
        .all();
      if (foreignKeyErrors.length !== 0) {
        throw new RuntimeSpoolError("FOREIGN_KEY_CHECK_FAILED");
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  #resolveScopeUserId(userId) {
    if (userId === null || userId === undefined) {
      return this.ownerUserId;
    }
    requireUserId(userId);
    const known = this.database
      .prepare("SELECT status FROM users WHERE user_id=?")
      .get(userId);
    if (!known) {
      throw new RuntimeSpoolError("USER_NOT_FOUND");
    }
    return userId;
  }

  #verifyRuntimeContract() {
    const status = this.pragmaStatus();
    if (
      status.journalMode !== "wal" ||
      status.synchronous !== "full" ||
      status.foreignKeys !== true ||
      status.busyTimeoutMs !== 5000 ||
      status.integrityCheck !== "ok"
    ) {
      throw new RuntimeSpoolError("SQLITE_RUNTIME_CONTRACT_FAILED");
    }
  }

  #secureDatabaseFiles() {
    for (const suffix of ["", "-wal", "-shm"]) {
      const candidate = `${this.databasePath}${suffix}`;
      if (fs.existsSync(candidate)) {
        fs.chmodSync(candidate, 0o600);
      }
    }
  }

  #assertOpen() {
    if (this.closed) {
      throw new RuntimeSpoolError("DATABASE_CLOSED");
    }
  }

  #timestamp() {
    return timestampFrom(this.now());
  }

  #expiresAt(now) {
    return new Date(new Date(now).getTime() + this.payloadTtlMs).toISOString();
  }

  #identity(label, fields, prefix) {
    return `${prefix}_${hmacHex(this.identityKey, label, fields)}`;
  }

  #fault(point) {
    this.faultInjector(point);
  }

  #rollbackQuietly() {
    try {
      this.database.exec("ROLLBACK");
    } catch {
      // A commit may already have completed; no sensitive context is emitted.
    }
  }

  #appendJobEvent({
    jobId,
    correlationId,
    eventType,
    fromStatus,
    toStatus,
    stateVersion,
    metadata = {},
    at,
  }) {
    const payload = redactedJson(metadata);
    const eventId = this.#identity(
      "job-event",
      [jobId, stateVersion, eventType, fromStatus || "", toStatus || ""],
      "event",
    );
    this.database
      .prepare(
        `INSERT INTO job_events(
          id, job_id, correlation_id, event_type, from_status, to_status,
          payload_redacted_json, payload_sha256, occurred_at, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        eventId,
        jobId,
        correlationId,
        eventType,
        fromStatus,
        toStatus,
        payload,
        sha256(Buffer.from(payload, "utf8")),
        at,
        at,
      );
    return eventId;
  }

  #appendOutboxAttemptEvent({
    outboxId,
    attemptNumber,
    eventType,
    errorClass = null,
    retryAt = null,
    providerReceiptHash = null,
    at,
  }) {
    if (
      !Number.isSafeInteger(attemptNumber)
      || attemptNumber < 1
      || ![
        "started",
        "retry_scheduled",
        "confirmed",
        "failed_terminal",
        "ambiguous",
      ].includes(eventType)
    ) {
      throw new RuntimeSpoolError("OUTBOX_ATTEMPT_EVENT_INVALID");
    }
    if (errorClass !== null) {
      requireSafeToken(errorClass, "error_class");
    }
    if (providerReceiptHash !== null) {
      requireSha256(providerReceiptHash, "provider_receipt_hash");
    }
    const eventId = this.#identity(
      "outbox-attempt-event",
      [outboxId, attemptNumber, eventType],
      "outboxevent",
    );
    this.database
      .prepare(
        `INSERT INTO outbox_attempt_events(
          id, outbox_id, attempt_number, event_type, error_class, retry_at,
          provider_receipt_hash, occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        eventId,
        outboxId,
        attemptNumber,
        eventType,
        errorClass,
        retryAt,
        providerReceiptHash,
        at,
      );
    return eventId;
  }

  #managedJob(jobId) {
    return this.database
      .prepare(
        `SELECT id, correlation_id, inbox_id, workspace_alias, runtime,
                operation_class, status, state_version, attempt_count,
                max_attempts, scheduler_managed, lease_owner,
                lease_heartbeat_at, lease_expires_at, dispatch_started_at,
                cancel_requested_at, runtime_thread_hash, runtime_turn_hash,
                created_at, queued_at, started_at, finished_at, updated_at
         FROM jobs WHERE id=?`,
      )
      .get(jobId);
  }

  #assertManagedLease(job, ownerId, { command }) {
    if (!job) {
      throw new RuntimeSpoolError("JOB_NOT_FOUND");
    }
    const isCommand = job.operation_class === "command";
    if (
      Number(job.scheduler_managed) !== 1
      || isCommand !== command
      || job.lease_owner !== ownerId
    ) {
      throw new RuntimeSpoolError("LEASE_OWNER_CONFLICT");
    }
  }

  #transitionWaitingJobToRunning(job, now, metadata = {}) {
    if (job.status !== "waiting_approval") {
      return job;
    }
    const nextVersion = Number(job.state_version) + 1;
    const result = this.database
      .prepare(
        `UPDATE jobs
         SET status='running', state_version=?, updated_at=?,
             last_runtime_event_at=?
         WHERE id=? AND status='waiting_approval' AND state_version=?`,
      )
      .run(nextVersion, now, now, job.id, Number(job.state_version));
    if (Number(result.changes) !== 1) {
      throw new RuntimeSpoolError("STATE_VERSION_CONFLICT");
    }
    this.#appendJobEvent({
      jobId: job.id,
      correlationId: job.correlation_id,
      eventType: "job_transition",
      fromStatus: "waiting_approval",
      toStatus: "running",
      stateVersion: nextVersion,
      metadata: {
        transition_code: "runtime_terminal_observed",
        ...metadata,
      },
      at: now,
    });
    return this.#managedJob(job.id);
  }

  deriveIds({ source, sourceAccountRef, sourceMessageId }) {
    this.#assertOpen();
    return deriveStableIds({
      source,
      sourceAccountRef,
      sourceMessageId,
      identityKey: this.identityKey,
    });
  }

  acceptInbound({
    source,
    sourceAccountRef,
    sourceMessageId,
    userRef,
    messageType = "text",
    payload,
    contextToken = null,
    workspaceAlias = "cyberboss",
    runtime = "codex",
    operationClass = "read_only",
    maxAttempts = 1,
    cursorBatchId = null,
    userId = null,
  }) {
    this.#assertOpen();
    if (!["text", "command", "unsupported"].includes(messageType)) {
      throw new RuntimeSpoolError("MESSAGE_TYPE_INVALID");
    }
    if (!["codex", "claude"].includes(runtime)) {
      throw new RuntimeSpoolError("RUNTIME_INVALID");
    }
    if (
      !["read_only", "bounded_mutation", "command"].includes(operationClass)
    ) {
      throw new RuntimeSpoolError("OPERATION_CLASS_INVALID");
    }
    if (!Number.isSafeInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 20) {
      throw new RuntimeSpoolError("MAX_ATTEMPTS_INVALID");
    }
    requireSafeToken(workspaceAlias, "workspace_alias");
    if (cursorBatchId !== null) {
      requireSafeToken(cursorBatchId, "cursor_batch_id");
    }
    const boundedUserRef = requireBoundedString(userRef, "user_ref", 1024);
    const ids = this.deriveIds({ source, sourceAccountRef, sourceMessageId });
    const plain = payloadBuffer(payload);
    const payloadHash = sha256(plain);
    const userRefHash = this.#identity(
      "user",
      [source, boundedUserRef],
      "user",
    );
    const scopeUserId = this.#resolveScopeUserId(userId);
    const now = this.#timestamp();
    const expiresAt = this.#expiresAt(now);
    const payloadCiphertext = this.cipher.encrypt(
      plain,
      `inbox:${ids.inboxId}:payload`,
    );
    const contextCiphertext =
      contextToken === null
        ? null
        : this.cipher.encrypt(
            contextToken,
            `inbox:${ids.inboxId}:context`,
          );
    let inserted = false;

    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.#fault("after_begin");
      const result = this.database
        .prepare(
          `INSERT INTO inbox_messages(
            id, source, source_account_hash, source_message_id,
            correlation_id, user_ref_hash, message_type, payload_ciphertext,
            payload_sha256, context_token_ciphertext, cursor_batch_id, status,
            received_at, durable_at, payload_expires_at, context_expires_at,
            user_id
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?, ?, ?, ?)
          ON CONFLICT(source, source_account_hash, source_message_id)
          DO NOTHING`,
        )
        .run(
          ids.inboxId,
          source,
          ids.sourceAccountHash,
          ids.sourceMessageId,
          ids.correlationId,
          userRefHash,
          messageType,
          payloadCiphertext,
          payloadHash,
          contextCiphertext,
          cursorBatchId,
          now,
          now,
          expiresAt,
          contextCiphertext ? expiresAt : null,
          scopeUserId,
        );
      inserted = Number(result.changes) === 1;
      this.#fault("after_inbox_insert");

      const inbox = this.database
        .prepare(
          `SELECT id, correlation_id, payload_sha256, user_id
           FROM inbox_messages
           WHERE source = ? AND source_account_hash = ?
             AND source_message_id = ?`,
        )
        .get(source, ids.sourceAccountHash, ids.sourceMessageId);
      if (
        !inbox ||
        inbox.id !== ids.inboxId ||
        inbox.correlation_id !== ids.correlationId ||
        inbox.payload_sha256 !== payloadHash ||
        inbox.user_id !== scopeUserId
      ) {
        throw new IntegrityConflictError();
      }

      if (inserted) {
        this.database
          .prepare(
            `INSERT INTO jobs(
              id, correlation_id, inbox_id, workspace_alias, runtime,
              operation_class, status, state_version, max_attempts,
              input_sha256, created_at, updated_at, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'received', 1, ?, ?, ?, ?, ?)`,
          )
          .run(
            ids.jobId,
            ids.correlationId,
            ids.inboxId,
            workspaceAlias,
            runtime,
            operationClass,
            maxAttempts,
            payloadHash,
            now,
            now,
            scopeUserId,
          );
        this.#fault("after_job_insert");
        this.#appendJobEvent({
          jobId: ids.jobId,
          correlationId: ids.correlationId,
          eventType: "job_received",
          fromStatus: null,
          toStatus: "received",
          stateVersion: 1,
          metadata: { source },
          at: now,
        });
        this.#fault("after_event_insert");
        this.database
          .prepare(
            `UPDATE jobs
             SET status='queued', state_version=2, queued_at=?, updated_at=?
             WHERE id=? AND status='received' AND state_version=1`,
          )
          .run(now, now, ids.jobId);
        this.#appendJobEvent({
          jobId: ids.jobId,
          correlationId: ids.correlationId,
          eventType: "job_transition",
          fromStatus: "received",
          toStatus: "queued",
          stateVersion: 2,
          metadata: { transition_code: "accepted" },
          at: now,
        });
      } else {
        const job = this.database
          .prepare(
            "SELECT id, correlation_id FROM jobs WHERE inbox_id = ?",
          )
          .get(ids.inboxId);
        if (
          !job ||
          job.id !== ids.jobId ||
          job.correlation_id !== ids.correlationId
        ) {
          throw new IntegrityConflictError();
        }
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    } finally {
      plain.fill(0);
    }
    this.#fault("after_commit");
    this.#secureDatabaseFiles();
    return Object.freeze({
      ...ids,
      duplicate: !inserted,
      status: this.getJob(ids.jobId).status,
    });
  }

  rejectInbound({
    source,
    sourceAccountRef,
    sourceMessageId,
    userRef,
    messageType = "unsupported",
    payload,
    contextToken = null,
    rejectReason,
    cursorBatchId = null,
    userId = null,
  }) {
    this.#assertOpen();
    if (!["text", "command", "unsupported"].includes(messageType)) {
      throw new RuntimeSpoolError("MESSAGE_TYPE_INVALID");
    }
    requireSafeToken(rejectReason, "reject_reason");
    if (cursorBatchId !== null) {
      requireSafeToken(cursorBatchId, "cursor_batch_id");
    }
    const boundedUserRef = requireBoundedString(userRef, "user_ref", 1024);
    const ids = this.deriveIds({ source, sourceAccountRef, sourceMessageId });
    const plain = payloadBuffer(payload);
    const payloadHash = sha256(plain);
    const userRefHash = this.#identity(
      "user",
      [source, boundedUserRef],
      "user",
    );
    const scopeUserId = this.#resolveScopeUserId(userId);
    const now = this.#timestamp();
    const expiresAt = this.#expiresAt(now);
    const payloadCiphertext = this.cipher.encrypt(
      plain,
      `inbox:${ids.inboxId}:payload`,
    );
    const contextCiphertext =
      contextToken === null
        ? null
        : this.cipher.encrypt(
            contextToken,
            `inbox:${ids.inboxId}:context`,
          );
    let inserted = false;

    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.#fault("after_begin");
      const result = this.database
        .prepare(
          `INSERT INTO inbox_messages(
            id, source, source_account_hash, source_message_id,
            correlation_id, user_ref_hash, message_type, payload_ciphertext,
            payload_sha256, context_token_ciphertext, cursor_batch_id, status,
            reject_reason, received_at, durable_at, payload_expires_at,
            context_expires_at, user_id
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rejected', ?, ?, ?, ?, ?, ?)
          ON CONFLICT(source, source_account_hash, source_message_id)
          DO NOTHING`,
        )
        .run(
          ids.inboxId,
          source,
          ids.sourceAccountHash,
          ids.sourceMessageId,
          ids.correlationId,
          userRefHash,
          messageType,
          payloadCiphertext,
          payloadHash,
          contextCiphertext,
          cursorBatchId,
          rejectReason,
          now,
          now,
          expiresAt,
          contextCiphertext ? expiresAt : null,
          scopeUserId,
        );
      inserted = Number(result.changes) === 1;
      this.#fault("after_inbox_insert");
      const inbox = this.database
        .prepare(
          `SELECT id, correlation_id, payload_sha256, status, reject_reason,
                  user_id
           FROM inbox_messages
           WHERE source = ? AND source_account_hash = ?
             AND source_message_id = ?`,
        )
        .get(source, ids.sourceAccountHash, ids.sourceMessageId);
      if (
        !inbox
        || inbox.id !== ids.inboxId
        || inbox.correlation_id !== ids.correlationId
        || inbox.payload_sha256 !== payloadHash
        || inbox.status !== "rejected"
        || inbox.reject_reason !== rejectReason
        || inbox.user_id !== scopeUserId
      ) {
        throw new IntegrityConflictError();
      }
      const job = this.database
        .prepare("SELECT id FROM jobs WHERE inbox_id = ?")
        .get(ids.inboxId);
      if (job) {
        throw new IntegrityConflictError();
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    } finally {
      plain.fill(0);
    }
    this.#fault("after_commit");
    this.#secureDatabaseFiles();
    return Object.freeze({
      inboxId: ids.inboxId,
      correlationId: ids.correlationId,
      sourceMessageId: ids.sourceMessageId,
      duplicate: !inserted,
      status: "rejected",
      rejectReason,
    });
  }

  transitionJob(jobId, toStatus, { expectedVersion, metadata = {} } = {}) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    if (!Number.isSafeInteger(expectedVersion) || expectedVersion < 1) {
      throw new RuntimeSpoolError("EXPECTED_VERSION_REQUIRED");
    }
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const job = this.database
        .prepare(
          "SELECT id, correlation_id, status, state_version FROM jobs WHERE id=?",
        )
        .get(jobId);
      if (!job) {
        throw new RuntimeSpoolError("JOB_NOT_FOUND");
      }
      if (Number(job.state_version) !== expectedVersion) {
        throw new RuntimeSpoolError("STATE_VERSION_CONFLICT");
      }
      assertTransition(job.status, toStatus);
      const nextVersion = expectedVersion + 1;
      const result = this.database
        .prepare(
          `UPDATE jobs
           SET status=?,
               state_version=?,
               attempt_count=attempt_count + CASE WHEN ?='running' THEN 1 ELSE 0 END,
               queued_at=CASE WHEN ?='queued' THEN COALESCE(queued_at, ?) ELSE queued_at END,
               started_at=CASE WHEN ?='running' THEN ? ELSE started_at END,
               finished_at=CASE
                 WHEN ? IN ('succeeded','failed_terminal','cancelled','expired','rejected')
                 THEN ?
                 ELSE finished_at
               END,
               updated_at=?
           WHERE id=? AND state_version=?`,
        )
        .run(
          toStatus,
          nextVersion,
          toStatus,
          toStatus,
          now,
          toStatus,
          now,
          toStatus,
          now,
          now,
          jobId,
          expectedVersion,
        );
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("STATE_VERSION_CONFLICT");
      }
      this.#appendJobEvent({
        jobId,
        correlationId: job.correlation_id,
        eventType: "job_transition",
        fromStatus: job.status,
        toStatus,
        stateVersion: nextVersion,
        metadata,
        at: now,
      });
      this.database.exec("COMMIT");
      return this.getJob(jobId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  peekNextRuntimeJob({ operationClass = null } = {}) {
    this.#assertOpen();
    if (operationClass !== null && operationClass !== "read_only") {
      throw new RuntimeSpoolError("RUNTIME_OPERATION_FILTER_INVALID");
    }
    const row = this.database
      .prepare(
        `SELECT id
         FROM jobs
         WHERE status='queued'
           AND operation_class <> 'command'
           AND (? IS NULL OR operation_class=?)
           AND attempt_count < max_attempts
         ORDER BY created_at, id
         LIMIT 1`,
      )
      .get(operationClass, operationClass);
    return row ? this.getJob(row.id) : null;
  }

  peekNextControlJob() {
    this.#assertOpen();
    const row = this.database
      .prepare(
        `SELECT id
         FROM jobs
         WHERE status='queued' AND operation_class='command'
         ORDER BY created_at, id
         LIMIT 1`,
      )
      .get();
    return row ? this.getJob(row.id) : null;
  }

  getActiveRuntimeJob() {
    this.#assertOpen();
    const row = this.database
      .prepare(
        `SELECT id
         FROM jobs
         WHERE operation_class <> 'command'
           AND status IN ('running','waiting_approval')
         ORDER BY started_at, id
         LIMIT 1`,
      )
      .get();
    return row ? this.getJob(row.id) : null;
  }

  getActiveControlJob() {
    this.#assertOpen();
    const row = this.database
      .prepare(
        `SELECT id
         FROM jobs
         WHERE operation_class='command' AND status='running'
         ORDER BY started_at, id
         LIMIT 1`,
      )
      .get();
    return row ? this.getJob(row.id) : null;
  }

  queueMetrics() {
    this.#assertOpen();
    const row = this.database
      .prepare(
        `SELECT
           SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued_total,
           SUM(CASE
             WHEN status='queued' AND operation_class='command' THEN 1
             ELSE 0
           END) AS queued_control,
           SUM(CASE
             WHEN status='queued' AND operation_class<>'command' THEN 1
             ELSE 0
           END) AS queued_runtime,
           SUM(CASE
             WHEN status IN ('running','waiting_approval')
               AND operation_class<>'command' THEN 1
             ELSE 0
           END) AS active_runtime_jobs,
           SUM(CASE
             WHEN status IN ('running','waiting_approval')
               AND operation_class<>'command'
               AND lease_owner IS NOT NULL
               AND lease_expires_at IS NOT NULL THEN 1
             ELSE 0
           END) AS active_runtime_leases,
           SUM(CASE
             WHEN status='running' AND operation_class='command' THEN 1
             ELSE 0
           END) AS active_control_jobs,
           MIN(CASE WHEN status='queued' THEN created_at END) AS oldest_queued_at
         FROM jobs`,
      )
      .get();
    return Object.freeze({
      queuedTotal: Number(row.queued_total || 0),
      queuedControl: Number(row.queued_control || 0),
      queuedRuntime: Number(row.queued_runtime || 0),
      activeRuntimeJobs: Number(row.active_runtime_jobs || 0),
      activeRuntimeLeases: Number(row.active_runtime_leases || 0),
      activeControlJobs: Number(row.active_control_jobs || 0),
      oldestQueuedAt: row.oldest_queued_at || null,
    });
  }

  claimNextRuntimeJob({
    ownerId,
    leaseMs,
    expectedJobId = null,
    bootId = null,
    pid = null,
    operationClass = null,
  }) {
    return this.#claimManagedJob({
      command: false,
      ownerId,
      leaseMs,
      expectedJobId,
      bootId,
      pid,
      operationClass,
    });
  }

  claimNextControlJob({
    ownerId,
    leaseMs,
    expectedJobId = null,
    bootId = null,
    pid = null,
  }) {
    return this.#claimManagedJob({
      command: true,
      ownerId,
      leaseMs,
      expectedJobId,
      bootId,
      pid,
      operationClass: null,
    });
  }

  #claimManagedJob({
    command,
    ownerId,
    leaseMs,
    expectedJobId,
    bootId,
    pid,
    operationClass,
  }) {
    this.#assertOpen();
    requireSafeToken(ownerId, "lease_owner");
    if (expectedJobId !== null) {
      requireBoundedString(expectedJobId, "expected_job_id", 160);
    }
    if (bootId !== null) {
      requireSafeToken(bootId, "boot_id");
    }
    if (
      operationClass !== null &&
      (command || operationClass !== "read_only")
    ) {
      throw new RuntimeSpoolError("RUNTIME_OPERATION_FILTER_INVALID");
    }
    const normalizedPid = normalizePid(pid);
    const now = this.#timestamp();
    const expiresAt = leaseExpiry(now, leaseMs);
    const leaseName = command ? CONTROL_LEASE_NAME : RUNTIME_LEASE_NAME;
    const activeOperationPredicate = command ? "= 'command'" : "<> 'command'";
    const queuedOperationPredicate = command
      ? "= 'command'"
      : operationClass === "read_only"
        ? "= 'read_only'"
        : "<> 'command'";
    const activeStatuses = command
      ? "status='running'"
      : "status IN ('running','waiting_approval')";

    this.database.exec("BEGIN IMMEDIATE");
    try {
      const active = this.database
        .prepare(
          `SELECT id
           FROM jobs
           WHERE operation_class ${activeOperationPredicate}
             AND ${activeStatuses}
           ORDER BY started_at, id
           LIMIT 1`,
        )
        .get();
      if (active) {
        this.database.exec("COMMIT");
        return Object.freeze({
          claimed: false,
          reason: "active_job",
          activeJobId: active.id,
        });
      }

      const lease = this.database
        .prepare(
          "SELECT owner_id, expires_at FROM singleton_leases WHERE name=?",
        )
        .get(leaseName);
      if (lease && lease.expires_at > now) {
        this.database.exec("COMMIT");
        return Object.freeze({
          claimed: false,
          reason: "singleton_busy",
        });
      }
      if (lease) {
        this.database
          .prepare(
            "DELETE FROM singleton_leases WHERE name=? AND expires_at<=?",
          )
          .run(leaseName, now);
      }

      const head = this.database
        .prepare(
          `SELECT id, correlation_id, state_version
           FROM jobs
           WHERE status='queued'
             AND operation_class ${queuedOperationPredicate}
             ${command ? "" : "AND attempt_count < max_attempts"}
           ORDER BY created_at, id
           LIMIT 1`,
        )
        .get();
      if (!head) {
        this.database.exec("COMMIT");
        return Object.freeze({ claimed: false, reason: "queue_empty" });
      }
      if (expectedJobId !== null && head.id !== expectedJobId) {
        this.database.exec("COMMIT");
        return Object.freeze({
          claimed: false,
          reason: "fifo_head_changed",
          headJobId: head.id,
        });
      }

      const nextVersion = Number(head.state_version) + 1;
      const result = this.database
        .prepare(
          `UPDATE jobs
           SET status='running', state_version=?, scheduler_managed=1,
               lease_owner=?, lease_heartbeat_at=?, lease_expires_at=?,
               started_at=COALESCE(started_at, ?), updated_at=?
           WHERE id=? AND status='queued' AND state_version=?`,
        )
        .run(
          nextVersion,
          ownerId,
          now,
          expiresAt,
          now,
          now,
          head.id,
          Number(head.state_version),
        );
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("STATE_VERSION_CONFLICT");
      }
      this.database
        .prepare(
          `INSERT INTO singleton_leases(
             name, owner_id, boot_id, pid, acquired_at, heartbeat_at, expires_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          leaseName,
          ownerId,
          bootId,
          normalizedPid,
          now,
          now,
          expiresAt,
        );
      this.#appendJobEvent({
        jobId: head.id,
        correlationId: head.correlation_id,
        eventType: "job_transition",
        fromStatus: "queued",
        toStatus: "running",
        stateVersion: nextVersion,
        metadata: {
          lease_class_code: command ? "control" : "runtime",
          transition_code: "scheduler_claimed",
        },
        at: now,
      });
      this.database.exec("COMMIT");
      return Object.freeze({
        claimed: true,
        reason: "claimed",
        job: this.getJob(head.id),
      });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  markRuntimeDispatchStarted(jobId, { ownerId } = {}) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    requireSafeToken(ownerId, "lease_owner");
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const job = this.#managedJob(jobId);
      this.#assertManagedLease(job, ownerId, { command: false });
      if (
        job.status !== "running"
        || job.dispatch_started_at !== null
        || Number(job.attempt_count) >= Number(job.max_attempts)
      ) {
        throw new RuntimeSpoolError("RUNTIME_DISPATCH_NOT_ALLOWED");
      }
      const result = this.database
        .prepare(
          `UPDATE jobs
           SET dispatch_started_at=?, attempt_count=attempt_count+1,
               updated_at=?, last_runtime_event_at=?
           WHERE id=? AND status='running' AND lease_owner=?
             AND dispatch_started_at IS NULL`,
        )
        .run(now, now, now, jobId, ownerId);
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("LEASE_OWNER_CONFLICT");
      }
      this.#appendJobEvent({
        jobId,
        correlationId: job.correlation_id,
        eventType: "runtime_dispatch_started",
        fromStatus: "running",
        toStatus: "running",
        stateVersion: Number(job.state_version),
        metadata: { attempt_count: Number(job.attempt_count) + 1 },
        at: now,
      });
      this.database.exec("COMMIT");
      return this.getJob(jobId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  bindRuntimeRun(jobId, { ownerId, threadId, turnId }) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    requireSafeToken(ownerId, "lease_owner");
    const boundedThread = requireBoundedString(threadId, "runtime_thread_id", 1024);
    const boundedTurn = requireBoundedString(turnId, "runtime_turn_id", 1024);
    const threadHash = this.#identity(
      "runtime-thread",
      [jobId, boundedThread],
      "thread",
    );
    const turnHash = this.#identity(
      "runtime-turn",
      [jobId, boundedThread, boundedTurn],
      "turn",
    );
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const job = this.#managedJob(jobId);
      this.#assertManagedLease(job, ownerId, { command: false });
      if (!ACTIVE_JOB_STATUSES.includes(job.status) || !job.dispatch_started_at) {
        throw new RuntimeSpoolError("RUNTIME_BIND_NOT_ALLOWED");
      }
      if (
        (job.runtime_thread_hash && job.runtime_thread_hash !== threadHash)
        || (job.runtime_turn_hash && job.runtime_turn_hash !== turnHash)
      ) {
        throw new IntegrityConflictError();
      }
      const firstBinding = !job.runtime_thread_hash && !job.runtime_turn_hash;
      if (firstBinding) {
        this.database
          .prepare(
            `UPDATE jobs
             SET runtime_thread_hash=?, runtime_turn_hash=?,
                 last_runtime_event_at=?, updated_at=?
             WHERE id=? AND lease_owner=?`,
          )
          .run(threadHash, turnHash, now, now, jobId, ownerId);
        this.#appendJobEvent({
          jobId,
          correlationId: job.correlation_id,
          eventType: "runtime_run_bound",
          fromStatus: job.status,
          toStatus: job.status,
          stateVersion: Number(job.state_version),
          metadata: {
            runtime_thread_present: true,
            runtime_turn_present: true,
          },
          at: now,
        });
      }
      this.database.exec("COMMIT");
      return Object.freeze({
        jobId,
        threadHash,
        turnHash,
        duplicate: !firstBinding,
      });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  heartbeatManagedLease(jobId, { ownerId, leaseMs, command = false } = {}) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    requireSafeToken(ownerId, "lease_owner");
    const now = this.#timestamp();
    const expiresAt = leaseExpiry(now, leaseMs);
    const leaseName = command ? CONTROL_LEASE_NAME : RUNTIME_LEASE_NAME;
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const job = this.#managedJob(jobId);
      this.#assertManagedLease(job, ownerId, { command });
      const validStatus = command
        ? job.status === "running"
        : ACTIVE_JOB_STATUSES.includes(job.status);
      if (!validStatus || !job.lease_expires_at || job.lease_expires_at <= now) {
        throw new RuntimeSpoolError("LEASE_EXPIRED");
      }
      const jobResult = this.database
        .prepare(
          `UPDATE jobs
           SET lease_heartbeat_at=?, lease_expires_at=?, updated_at=?
           WHERE id=? AND lease_owner=? AND lease_expires_at>?`,
        )
        .run(now, expiresAt, now, jobId, ownerId, now);
      const singletonResult = this.database
        .prepare(
          `UPDATE singleton_leases
           SET heartbeat_at=?, expires_at=?
           WHERE name=? AND owner_id=? AND expires_at>?`,
        )
        .run(now, expiresAt, leaseName, ownerId, now);
      if (
        Number(jobResult.changes) !== 1
        || Number(singletonResult.changes) !== 1
      ) {
        throw new RuntimeSpoolError("LEASE_OWNER_CONFLICT");
      }
      this.database.exec("COMMIT");
      return Object.freeze({ heartbeatAt: now, expiresAt });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  markRuntimeCancelRequested(jobId, { ownerId } = {}) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    requireSafeToken(ownerId, "lease_owner");
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const job = this.#managedJob(jobId);
      this.#assertManagedLease(job, ownerId, { command: false });
      if (!ACTIVE_JOB_STATUSES.includes(job.status)) {
        throw new RuntimeSpoolError("ACTIVE_RUNTIME_JOB_REQUIRED");
      }
      if (!job.cancel_requested_at) {
        this.database
          .prepare(
            `UPDATE jobs
             SET cancel_requested_at=?, last_runtime_event_at=?, updated_at=?
             WHERE id=? AND lease_owner=?`,
          )
          .run(now, now, now, jobId, ownerId);
        this.#appendJobEvent({
          jobId,
          correlationId: job.correlation_id,
          eventType: "runtime_cancel_requested",
          fromStatus: job.status,
          toStatus: job.status,
          stateVersion: Number(job.state_version),
          metadata: { cancel_pending: true },
          at: now,
        });
      }
      this.database.exec("COMMIT");
      return this.getJob(jobId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  transitionManagedRuntimeJob(jobId, toStatus, {
    ownerId,
    metadata = {},
  } = {}) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    requireSafeToken(ownerId, "lease_owner");
    if (!["running", "waiting_approval"].includes(toStatus)) {
      throw new RuntimeSpoolError("MANAGED_RUNTIME_TRANSITION_INVALID");
    }
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const job = this.#managedJob(jobId);
      this.#assertManagedLease(job, ownerId, { command: false });
      assertTransition(job.status, toStatus);
      const nextVersion = Number(job.state_version) + 1;
      const result = this.database
        .prepare(
          `UPDATE jobs
           SET status=?, state_version=?, last_runtime_event_at=?, updated_at=?
           WHERE id=? AND status=? AND state_version=? AND lease_owner=?`,
        )
        .run(
          toStatus,
          nextVersion,
          now,
          now,
          jobId,
          job.status,
          Number(job.state_version),
          ownerId,
        );
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("STATE_VERSION_CONFLICT");
      }
      this.#appendJobEvent({
        jobId,
        correlationId: job.correlation_id,
        eventType: "job_transition",
        fromStatus: job.status,
        toStatus,
        stateVersion: nextVersion,
        metadata,
        at: now,
      });
      this.database.exec("COMMIT");
      return this.getJob(jobId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  finishRuntimeJob(jobId, toStatus, {
    ownerId,
    errorClass = null,
    metadata = {},
  } = {}) {
    return this.#finishManagedJob(jobId, toStatus, {
      command: false,
      ownerId,
      errorClass,
      metadata,
    });
  }

  finishControlJob(jobId, toStatus, {
    ownerId,
    errorClass = null,
    metadata = {},
  } = {}) {
    return this.#finishManagedJob(jobId, toStatus, {
      command: true,
      ownerId,
      errorClass,
      metadata,
    });
  }

  #finishManagedJob(jobId, toStatus, {
    command,
    ownerId,
    errorClass,
    metadata,
  }) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    requireSafeToken(ownerId, "lease_owner");
    if (!["succeeded", "failed_terminal", "cancelled"].includes(toStatus)) {
      throw new RuntimeSpoolError("MANAGED_TERMINAL_STATUS_INVALID");
    }
    if (errorClass !== null) {
      requireSafeToken(errorClass, "error_class");
    }
    const now = this.#timestamp();
    const leaseName = command ? CONTROL_LEASE_NAME : RUNTIME_LEASE_NAME;
    this.database.exec("BEGIN IMMEDIATE");
    try {
      let job = this.#managedJob(jobId);
      this.#assertManagedLease(job, ownerId, { command });
      const validStatus = command
        ? job.status === "running"
        : ACTIVE_JOB_STATUSES.includes(job.status);
      if (!validStatus) {
        throw new RuntimeSpoolError("ACTIVE_MANAGED_JOB_REQUIRED");
      }
      if (!command && job.status === "waiting_approval" && toStatus !== "cancelled") {
        job = this.#transitionWaitingJobToRunning(job, now);
      }
      assertTransition(job.status, toStatus);
      const nextVersion = Number(job.state_version) + 1;
      const result = this.database
        .prepare(
          `UPDATE jobs
           SET status=?, state_version=?, lease_owner=NULL,
               lease_heartbeat_at=NULL, lease_expires_at=NULL,
               error_class=?, error_redacted=?, finished_at=?,
               last_runtime_event_at=?, updated_at=?
           WHERE id=? AND status=? AND state_version=? AND lease_owner=?`,
        )
        .run(
          toStatus,
          nextVersion,
          errorClass,
          errorClass,
          now,
          now,
          now,
          jobId,
          job.status,
          Number(job.state_version),
          ownerId,
        );
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("STATE_VERSION_CONFLICT");
      }
      const leaseDelete = this.database
        .prepare(
          "DELETE FROM singleton_leases WHERE name=? AND owner_id=?",
        )
        .run(leaseName, ownerId);
      if (Number(leaseDelete.changes) !== 1) {
        throw new RuntimeSpoolError("LEASE_OWNER_CONFLICT");
      }
      this.#appendJobEvent({
        jobId,
        correlationId: job.correlation_id,
        eventType: "job_transition",
        fromStatus: job.status,
        toStatus,
        stateVersion: nextVersion,
        metadata,
        at: now,
      });
      this.database.exec("COMMIT");
      return this.getJob(jobId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  requeueRetryableRuntimeJob(jobId, {
    ownerId,
    errorClass,
    metadata = {},
  } = {}) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    requireSafeToken(ownerId, "lease_owner");
    requireSafeToken(errorClass, "error_class");
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      let job = this.#managedJob(jobId);
      this.#assertManagedLease(job, ownerId, { command: false });
      if (
        !ACTIVE_JOB_STATUSES.includes(job.status)
        || job.operation_class !== "read_only"
        || !job.dispatch_started_at
        || Number(job.attempt_count) >= Number(job.max_attempts)
      ) {
        throw new RuntimeSpoolError("SAFE_RETRY_NOT_PROVEN");
      }
      job = this.#transitionWaitingJobToRunning(job, now);
      assertTransition(job.status, "failed_retryable");
      const failedVersion = Number(job.state_version) + 1;
      this.database
        .prepare(
          `UPDATE jobs
           SET status='failed_retryable', state_version=?, error_class=?,
               error_redacted=?, last_runtime_event_at=?, updated_at=?
           WHERE id=? AND status='running' AND state_version=? AND lease_owner=?`,
        )
        .run(
          failedVersion,
          errorClass,
          errorClass,
          now,
          now,
          jobId,
          Number(job.state_version),
          ownerId,
        );
      this.#appendJobEvent({
        jobId,
        correlationId: job.correlation_id,
        eventType: "job_transition",
        fromStatus: "running",
        toStatus: "failed_retryable",
        stateVersion: failedVersion,
        metadata,
        at: now,
      });
      const queuedVersion = failedVersion + 1;
      this.database
        .prepare(
          `UPDATE jobs
           SET status='queued', state_version=?, lease_owner=NULL,
               lease_heartbeat_at=NULL, lease_expires_at=NULL,
               dispatch_started_at=NULL, cancel_requested_at=NULL,
               runtime_thread_hash=NULL, runtime_turn_hash=NULL,
               error_class=NULL, error_redacted=NULL, updated_at=?
           WHERE id=? AND status='failed_retryable' AND state_version=?`,
        )
        .run(queuedVersion, now, jobId, failedVersion);
      this.#appendJobEvent({
        jobId,
        correlationId: job.correlation_id,
        eventType: "job_transition",
        fromStatus: "failed_retryable",
        toStatus: "queued",
        stateVersion: queuedVersion,
        metadata: { transition_code: "safe_read_only_retry" },
        at: now,
      });
      const deleted = this.database
        .prepare(
          "DELETE FROM singleton_leases WHERE name=? AND owner_id=?",
        )
        .run(RUNTIME_LEASE_NAME, ownerId);
      if (Number(deleted.changes) !== 1) {
        throw new RuntimeSpoolError("LEASE_OWNER_CONFLICT");
      }
      this.database.exec("COMMIT");
      return this.getJob(jobId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  recoverExpiredRuntimeLease() {
    return this.#recoverExpiredManagedLease({ command: false });
  }

  recoverExpiredControlLease() {
    return this.#recoverExpiredManagedLease({ command: true });
  }

  #recoverExpiredManagedLease({ command }) {
    this.#assertOpen();
    const now = this.#timestamp();
    const leaseName = command ? CONTROL_LEASE_NAME : RUNTIME_LEASE_NAME;
    const operationPredicate = command ? "= 'command'" : "<> 'command'";
    const activeStatuses = command
      ? "status='running'"
      : "status IN ('running','waiting_approval')";
    this.database.exec("BEGIN IMMEDIATE");
    try {
      let job = this.database
        .prepare(
          `SELECT *
           FROM jobs
           WHERE operation_class ${operationPredicate}
             AND ${activeStatuses}
           ORDER BY started_at, id
           LIMIT 1`,
        )
        .get();
      if (!job) {
        const deleted = this.database
          .prepare(
            "DELETE FROM singleton_leases WHERE name=? AND expires_at<=?",
          )
          .run(leaseName, now);
        this.database.exec("COMMIT");
        return Object.freeze({
          recovered: Number(deleted.changes) > 0,
          classification: Number(deleted.changes) > 0
            ? "orphan_singleton_removed"
            : "none",
          requeued: false,
        });
      }
      if (!job.lease_expires_at || job.lease_expires_at > now) {
        this.database.exec("COMMIT");
        return Object.freeze({
          recovered: false,
          classification: "lease_active",
          requeued: false,
          jobId: job.id,
        });
      }

      const ownerId = job.lease_owner;
      if (!command && !job.dispatch_started_at && job.status === "running") {
        const failedVersion = Number(job.state_version) + 1;
        this.database
          .prepare(
            `UPDATE jobs
             SET status='failed_retryable', state_version=?,
                 error_class='lease_expired_before_dispatch',
                 error_redacted='lease_expired_before_dispatch', updated_at=?
             WHERE id=? AND status='running' AND state_version=?`,
          )
          .run(failedVersion, now, job.id, Number(job.state_version));
        this.#appendJobEvent({
          jobId: job.id,
          correlationId: job.correlation_id,
          eventType: "job_transition",
          fromStatus: "running",
          toStatus: "failed_retryable",
          stateVersion: failedVersion,
          metadata: { recovery_class_code: "safe_before_dispatch" },
          at: now,
        });
        const queuedVersion = failedVersion + 1;
        this.database
          .prepare(
            `UPDATE jobs
             SET status='queued', state_version=?, lease_owner=NULL,
                 lease_heartbeat_at=NULL, lease_expires_at=NULL,
                 error_class=NULL, error_redacted=NULL, updated_at=?
             WHERE id=? AND status='failed_retryable' AND state_version=?`,
          )
          .run(queuedVersion, now, job.id, failedVersion);
        this.#appendJobEvent({
          jobId: job.id,
          correlationId: job.correlation_id,
          eventType: "job_transition",
          fromStatus: "failed_retryable",
          toStatus: "queued",
          stateVersion: queuedVersion,
          metadata: { transition_code: "recovered_before_dispatch" },
          at: now,
        });
        this.database
          .prepare(
            "DELETE FROM singleton_leases WHERE name=? AND owner_id=?",
          )
          .run(leaseName, ownerId);
        this.database.exec("COMMIT");
        return Object.freeze({
          recovered: true,
          classification: "safe_before_dispatch",
          requeued: true,
          jobId: job.id,
        });
      }

      if (!command && job.status === "waiting_approval") {
        job = this.#transitionWaitingJobToRunning(job, now, {
          recovery_class_code: "ambiguous_after_dispatch",
        });
      }
      assertTransition(job.status, "failed_terminal");
      const nextVersion = Number(job.state_version) + 1;
      const errorClass = command
        ? "control_recovery_ambiguous"
        : "recovery_ambiguous_after_dispatch";
      this.database
        .prepare(
          `UPDATE jobs
           SET status='failed_terminal', state_version=?, lease_owner=NULL,
               lease_heartbeat_at=NULL, lease_expires_at=NULL,
               error_class=?, error_redacted=?, finished_at=?,
               last_runtime_event_at=?, updated_at=?
           WHERE id=? AND status=? AND state_version=?`,
        )
        .run(
          nextVersion,
          errorClass,
          errorClass,
          now,
          now,
          now,
          job.id,
          job.status,
          Number(job.state_version),
        );
      this.#appendJobEvent({
        jobId: job.id,
        correlationId: job.correlation_id,
        eventType: "job_transition",
        fromStatus: job.status,
        toStatus: "failed_terminal",
        stateVersion: nextVersion,
        metadata: {
          recovery_class_code: command
            ? "control_ambiguous"
            : "ambiguous_after_dispatch",
        },
        at: now,
      });
      this.database
        .prepare(
          "DELETE FROM singleton_leases WHERE name=? AND owner_id=?",
        )
        .run(leaseName, ownerId);
      this.database.exec("COMMIT");
      return Object.freeze({
        recovered: true,
        classification: command
          ? "control_ambiguous"
          : "ambiguous_after_dispatch",
        requeued: false,
        jobId: job.id,
      });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  enqueueOutbox({
    jobId,
    dedupeKey,
    messageKind,
    targetRef,
    payload,
    chunkIndex = 1,
    chunkCount = 1,
    maxAttempts = 5,
    logicalMessageSha256 = null,
    providerClientId = null,
  }) {
    this.#assertOpen();
    requireSafeToken(dedupeKey, "dedupe_key");
    if (!["accepted", "progress", "result", "error", "cancelled"].includes(messageKind)) {
      throw new RuntimeSpoolError("MESSAGE_KIND_INVALID");
    }
    if (
      !Number.isSafeInteger(chunkIndex) ||
      !Number.isSafeInteger(chunkCount) ||
      chunkIndex < 1 ||
      chunkCount < chunkIndex ||
      !Number.isSafeInteger(maxAttempts) ||
      maxAttempts < 1 ||
      maxAttempts > 20
    ) {
      throw new RuntimeSpoolError("OUTBOX_BOUNDS_INVALID");
    }
    const job = this.getJob(jobId);
    if (!job) {
      throw new RuntimeSpoolError("JOB_NOT_FOUND");
    }
    // The reply scope is inherited from the job and is never caller-supplied,
    // so an outbox row can only ever be addressed to the job's own user.
    const scopeUserId = requireUserId(
      this.database
        .prepare("SELECT user_id FROM jobs WHERE id=?")
        .get(jobId).user_id,
      "job_user_id",
    );
    const outboxId = this.#identity("outbox", [dedupeKey], "outbox");
    const now = this.#timestamp();
    const expiresAt = this.#expiresAt(now);
    const plain = payloadBuffer(payload);
    const payloadHash = sha256(plain);
    const logicalHash = logicalMessageSha256 === null
      ? sha256(
          Buffer.from(
            `${jobId}\u0000${messageKind}\u0000${dedupeKey}`,
            "utf8",
          ),
        )
      : requireSha256(logicalMessageSha256, "logical_message_sha256");
    const clientId = providerClientId === null
      ? `cb-outbox-${sha256(Buffer.from(dedupeKey, "utf8")).slice(0, 32)}`
      : requireSafeToken(providerClientId, "provider_client_id");
    const payloadCiphertext = this.cipher.encrypt(
      plain,
      `outbox:${outboxId}:payload`,
    );
    const targetCiphertext =
      targetRef === null || targetRef === undefined
        ? null
        : this.cipher.encrypt(targetRef, `outbox:${outboxId}:target`);
    try {
      this.database
        .prepare(
          `INSERT INTO outbox_messages(
            id, job_id, correlation_id, target_type, target_ref_ciphertext,
            dedupe_key, message_kind, chunk_index, chunk_count,
            payload_ciphertext, payload_sha256, status, max_attempts,
            created_at, updated_at, payload_expires_at, target_ref_expires_at,
            logical_message_sha256, provider_client_id, user_id
          ) VALUES (
            ?, ?, ?, 'weixin', ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?,
            ?, ?, ?
          )
          ON CONFLICT(dedupe_key) DO NOTHING`,
        )
        .run(
          outboxId,
          jobId,
          job.correlation_id,
          targetCiphertext,
          dedupeKey,
          messageKind,
          chunkIndex,
          chunkCount,
          payloadCiphertext,
          payloadHash,
          maxAttempts,
          now,
          now,
          expiresAt,
          targetCiphertext ? expiresAt : null,
          logicalHash,
          clientId,
          scopeUserId,
        );
      const row = this.database
        .prepare(
          `SELECT id, job_id, payload_sha256, status, message_kind,
                  chunk_index, chunk_count, max_attempts,
                  logical_message_sha256, provider_client_id, user_id
           FROM outbox_messages WHERE dedupe_key=?`,
        )
        .get(dedupeKey);
      if (
        !row ||
        row.id !== outboxId ||
        row.job_id !== jobId ||
        row.payload_sha256 !== payloadHash ||
        row.message_kind !== messageKind ||
        Number(row.chunk_index) !== chunkIndex ||
        Number(row.chunk_count) !== chunkCount ||
        Number(row.max_attempts) !== maxAttempts ||
        row.logical_message_sha256 !== logicalHash ||
        row.provider_client_id !== clientId ||
        row.user_id !== scopeUserId
      ) {
        throw new IntegrityConflictError();
      }
      return this.getOutbox(outboxId);
    } finally {
      plain.fill(0);
      this.#secureDatabaseFiles();
    }
  }

  getOutbox(outboxId) {
    this.#assertOpen();
    requireBoundedString(outboxId, "outbox_id", 160);
    const row = this.database
      .prepare(
        `SELECT id, job_id, correlation_id, target_type, dedupe_key,
                message_kind, chunk_index, chunk_count, payload_sha256,
                status, attempt_count, max_attempts, next_attempt_at,
                last_error_class, last_error_redacted, created_at, updated_at,
                confirmed_at, provider_receipt_hash, payload_expires_at,
                payload_redacted_at, target_ref_expires_at,
                target_ref_redacted_at, logical_message_sha256,
                provider_client_id, claim_owner, claim_expires_at,
                dispatch_started_at, last_attempt_at, confirmation_state,
                dispatch_outcome, recovery_class, user_id
         FROM outbox_messages WHERE id=?`,
      )
      .get(outboxId);
    return row ? Object.freeze({ ...row }) : null;
  }

  getOutboxByDedupeKey(dedupeKey) {
    this.#assertOpen();
    requireSafeToken(dedupeKey, "dedupe_key");
    const row = this.database
      .prepare("SELECT id FROM outbox_messages WHERE dedupe_key=?")
      .get(dedupeKey);
    return row ? this.getOutbox(row.id) : null;
  }

  listOutbox(jobId = null) {
    this.#assertOpen();
    if (jobId !== null) {
      requireBoundedString(jobId, "job_id", 160);
    }
    const rows = jobId === null
      ? this.database
          .prepare(
            `SELECT id FROM outbox_messages
             ORDER BY created_at, logical_message_sha256, chunk_index, id`,
          )
          .all()
      : this.database
          .prepare(
            `SELECT id FROM outbox_messages WHERE job_id=?
             ORDER BY created_at, logical_message_sha256, chunk_index, id`,
          )
          .all(jobId);
    return rows.map((row) => this.getOutbox(row.id));
  }

  listOutboxAttemptEvents(outboxId = null) {
    this.#assertOpen();
    if (outboxId !== null) {
      requireBoundedString(outboxId, "outbox_id", 160);
    }
    const rows = outboxId === null
      ? this.database
          .prepare(
            `SELECT id, outbox_id, attempt_number, event_type, error_class,
                    retry_at, provider_receipt_hash, occurred_at
             FROM outbox_attempt_events
             ORDER BY outbox_id, attempt_number,
                      CASE event_type
                        WHEN 'started' THEN 1
                        WHEN 'retry_scheduled' THEN 2
                        WHEN 'confirmed' THEN 2
                        WHEN 'failed_terminal' THEN 2
                        WHEN 'ambiguous' THEN 2
                        ELSE 3
                      END,
                      occurred_at, id`,
          )
          .all()
      : this.database
          .prepare(
            `SELECT id, outbox_id, attempt_number, event_type, error_class,
                    retry_at, provider_receipt_hash, occurred_at
             FROM outbox_attempt_events WHERE outbox_id=?
             ORDER BY attempt_number,
                      CASE event_type
                        WHEN 'started' THEN 1
                        WHEN 'retry_scheduled' THEN 2
                        WHEN 'confirmed' THEN 2
                        WHEN 'failed_terminal' THEN 2
                        WHEN 'ambiguous' THEN 2
                        ELSE 3
                      END,
                      occurred_at, id`,
          )
          .all(outboxId);
    return rows.map((row) => Object.freeze({ ...row }));
  }

  claimNextOutbox({
    ownerId,
    leaseMs = DEFAULT_OUTBOX_LEASE_MS,
  } = {}) {
    this.#assertOpen();
    requireSafeToken(ownerId, "claim_owner");
    const now = this.#timestamp();
    const expiresAt = leaseExpiry(now, leaseMs);
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const row = this.database
        .prepare(
          `SELECT candidate.id
           FROM outbox_messages AS candidate
           WHERE (
             candidate.status='pending'
             OR (
               candidate.status='retry'
               AND candidate.next_attempt_at IS NOT NULL
               AND candidate.next_attempt_at<=?
             )
           )
             AND candidate.attempt_count < candidate.max_attempts
             AND NOT EXISTS (
               SELECT 1
               FROM outbox_messages AS previous
               WHERE previous.job_id=candidate.job_id
                 AND previous.logical_message_sha256=
                   candidate.logical_message_sha256
                 AND previous.chunk_index<candidate.chunk_index
                 AND previous.status<>'confirmed'
             )
           ORDER BY candidate.created_at,
                    candidate.logical_message_sha256,
                    candidate.chunk_index,
                    candidate.id
           LIMIT 1`,
        )
        .get(now);
      if (!row) {
        this.database.exec("COMMIT");
        return Object.freeze({ claimed: false, reason: "queue_empty" });
      }
      const current = this.getOutbox(row.id);
      const attemptNumber = Number(current.attempt_count) + 1;
      const result = this.database
        .prepare(
          `UPDATE outbox_messages
           SET status='sending', attempt_count=?, next_attempt_at=NULL,
               claim_owner=?, claim_expires_at=?, dispatch_started_at=NULL,
               last_attempt_at=?, confirmation_state='unconfirmed',
               dispatch_outcome='not_started', recovery_class=NULL,
               updated_at=?
           WHERE id=? AND status IN ('pending','retry')
             AND attempt_count=?`,
        )
        .run(
          attemptNumber,
          ownerId,
          expiresAt,
          now,
          now,
          row.id,
          Number(current.attempt_count),
        );
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("OUTBOX_CLAIM_CONFLICT");
      }
      this.#appendOutboxAttemptEvent({
        outboxId: row.id,
        attemptNumber,
        eventType: "started",
        at: now,
      });
      this.database.exec("COMMIT");
      return Object.freeze({
        claimed: true,
        reason: "claimed",
        row: this.getOutbox(row.id),
      });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  readClaimedOutbox(outboxId, { ownerId } = {}) {
    this.#assertOpen();
    requireBoundedString(outboxId, "outbox_id", 160);
    requireSafeToken(ownerId, "claim_owner");
    const row = this.database
      .prepare(
        `SELECT id, payload_ciphertext, payload_sha256,
                target_ref_ciphertext, status, claim_owner,
                provider_client_id
         FROM outbox_messages WHERE id=?`,
      )
      .get(outboxId);
    if (!row) {
      throw new RuntimeSpoolError("OUTBOX_NOT_FOUND");
    }
    if (row.status !== "sending" || row.claim_owner !== ownerId) {
      throw new RuntimeSpoolError("OUTBOX_CLAIM_OWNER_CONFLICT");
    }
    const payload = this.cipher.decrypt(
      row.payload_ciphertext,
      `outbox:${outboxId}:payload`,
    );
    let target = null;
    try {
      if (sha256(payload) !== row.payload_sha256) {
        throw new IntegrityConflictError();
      }
      if (row.target_ref_ciphertext === null) {
        throw new RuntimeSpoolError("OUTBOX_TARGET_REDACTED");
      }
      const targetBuffer = this.cipher.decrypt(
        row.target_ref_ciphertext,
        `outbox:${outboxId}:target`,
      );
      try {
        target = JSON.parse(targetBuffer.toString("utf8"));
      } catch {
        throw new RuntimeSpoolError("OUTBOX_TARGET_INVALID");
      } finally {
        targetBuffer.fill(0);
      }
      if (!target || typeof target !== "object" || Array.isArray(target)) {
        throw new RuntimeSpoolError("OUTBOX_TARGET_INVALID");
      }
      return Object.freeze({
        payload: payload.toString("utf8"),
        target: Object.freeze({ ...target }),
        providerClientId: row.provider_client_id,
      });
    } finally {
      payload.fill(0);
    }
  }

  markOutboxDispatchStarted(outboxId, { ownerId } = {}) {
    this.#assertOpen();
    requireBoundedString(outboxId, "outbox_id", 160);
    requireSafeToken(ownerId, "claim_owner");
    const now = this.#timestamp();
    const result = this.database
      .prepare(
        `UPDATE outbox_messages
         SET dispatch_started_at=?, updated_at=?
         WHERE id=? AND status='sending' AND claim_owner=?
           AND dispatch_started_at IS NULL`,
      )
      .run(now, now, outboxId, ownerId);
    if (Number(result.changes) !== 1) {
      throw new RuntimeSpoolError("OUTBOX_DISPATCH_CONFLICT");
    }
    return this.getOutbox(outboxId);
  }

  markOutboxRetry(outboxId, {
    ownerId,
    errorClass,
    nextAttemptAt,
  } = {}) {
    this.#assertOpen();
    requireBoundedString(outboxId, "outbox_id", 160);
    requireSafeToken(ownerId, "claim_owner");
    requireSafeToken(errorClass, "error_class");
    const retryAt = timestampFrom(nextAttemptAt);
    const now = this.#timestamp();
    if (retryAt < now) {
      throw new RuntimeSpoolError("OUTBOX_RETRY_TIME_INVALID");
    }
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const row = this.getOutbox(outboxId);
      if (
        !row
        || row.status !== "sending"
        || row.claim_owner !== ownerId
        || !row.dispatch_started_at
        || Number(row.attempt_count) >= Number(row.max_attempts)
      ) {
        throw new RuntimeSpoolError("OUTBOX_RETRY_NOT_ALLOWED");
      }
      const result = this.database
        .prepare(
          `UPDATE outbox_messages
           SET status='retry', next_attempt_at=?, last_error_class=?,
               last_error_redacted=?, claim_owner=NULL,
               claim_expires_at=NULL, dispatch_started_at=NULL,
               dispatch_outcome='known_failure',
               confirmation_state='unconfirmed',
               recovery_class='provider_known_retryable', updated_at=?
           WHERE id=? AND status='sending' AND claim_owner=?
             AND attempt_count=?`,
        )
        .run(
          retryAt,
          errorClass,
          errorClass,
          now,
          outboxId,
          ownerId,
          Number(row.attempt_count),
        );
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("OUTBOX_CLAIM_OWNER_CONFLICT");
      }
      this.#appendOutboxAttemptEvent({
        outboxId,
        attemptNumber: Number(row.attempt_count),
        eventType: "retry_scheduled",
        errorClass,
        retryAt,
        at: now,
      });
      this.database.exec("COMMIT");
      return this.getOutbox(outboxId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  markOutboxConfirmed(outboxId, {
    ownerId,
    providerConfirmation,
  } = {}) {
    this.#assertOpen();
    requireBoundedString(outboxId, "outbox_id", 160);
    requireSafeToken(ownerId, "claim_owner");
    const row = this.getOutbox(outboxId);
    if (
      !row
      || row.status !== "sending"
      || row.claim_owner !== ownerId
      || !row.dispatch_started_at
      || !providerConfirmation
      || providerConfirmation.confirmed !== true
      || providerConfirmation.clientId !== row.provider_client_id
    ) {
      throw new RuntimeSpoolError("OUTBOX_CONFIRMATION_REQUIRED");
    }
    const receiptHash = requireSha256(
      providerConfirmation.receiptHash,
      "provider_receipt_hash",
    );
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const result = this.database
        .prepare(
          `UPDATE outbox_messages
           SET status='confirmed', confirmed_at=?,
               provider_receipt_hash=?, confirmation_state='confirmed',
               dispatch_outcome='confirmed', claim_owner=NULL,
               claim_expires_at=NULL, next_attempt_at=NULL,
               last_error_class=NULL, last_error_redacted=NULL,
               recovery_class=NULL, updated_at=?
           WHERE id=? AND status='sending' AND claim_owner=?
             AND attempt_count=?`,
        )
        .run(
          now,
          receiptHash,
          now,
          outboxId,
          ownerId,
          Number(row.attempt_count),
        );
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("OUTBOX_CLAIM_OWNER_CONFLICT");
      }
      this.#appendOutboxAttemptEvent({
        outboxId,
        attemptNumber: Number(row.attempt_count),
        eventType: "confirmed",
        providerReceiptHash: receiptHash,
        at: now,
      });
      this.database.exec("COMMIT");
      return this.getOutbox(outboxId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  markOutboxTerminal(outboxId, {
    ownerId,
    errorClass,
    ambiguous = false,
    recoveryClass = null,
  } = {}) {
    this.#assertOpen();
    requireBoundedString(outboxId, "outbox_id", 160);
    requireSafeToken(ownerId, "claim_owner");
    requireSafeToken(errorClass, "error_class");
    if (recoveryClass !== null) {
      requireSafeToken(recoveryClass, "recovery_class");
    }
    const row = this.getOutbox(outboxId);
    if (
      !row
      || row.status !== "sending"
      || row.claim_owner !== ownerId
    ) {
      throw new RuntimeSpoolError("OUTBOX_CLAIM_OWNER_CONFLICT");
    }
    if (ambiguous && !row.dispatch_started_at) {
      throw new RuntimeSpoolError("OUTBOX_AMBIGUOUS_DISPATCH_REQUIRED");
    }
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const result = this.database
        .prepare(
          `UPDATE outbox_messages
           SET status='failed_terminal', next_attempt_at=NULL,
               last_error_class=?, last_error_redacted=?,
               confirmation_state=?, dispatch_outcome=?,
               claim_owner=NULL, claim_expires_at=NULL,
               recovery_class=?, updated_at=?
           WHERE id=? AND status='sending' AND claim_owner=?
             AND attempt_count=?`,
        )
        .run(
          errorClass,
          errorClass,
          ambiguous ? "ambiguous" : "unconfirmed",
          ambiguous ? "ambiguous" : "known_failure",
          recoveryClass,
          now,
          outboxId,
          ownerId,
          Number(row.attempt_count),
        );
      if (Number(result.changes) !== 1) {
        throw new RuntimeSpoolError("OUTBOX_CLAIM_OWNER_CONFLICT");
      }
      this.#appendOutboxAttemptEvent({
        outboxId,
        attemptNumber: Number(row.attempt_count),
        eventType: ambiguous ? "ambiguous" : "failed_terminal",
        errorClass,
        at: now,
      });
      this.database.exec("COMMIT");
      return this.getOutbox(outboxId);
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  failOutboxDependents(outboxId) {
    this.#assertOpen();
    requireBoundedString(outboxId, "outbox_id", 160);
    const source = this.getOutbox(outboxId);
    if (!source || source.status !== "failed_terminal") {
      throw new RuntimeSpoolError("OUTBOX_TERMINAL_SOURCE_REQUIRED");
    }
    const now = this.#timestamp();
    const result = this.database
      .prepare(
        `UPDATE outbox_messages
         SET status='failed_terminal', next_attempt_at=NULL,
             last_error_class='previous_chunk_failed',
             last_error_redacted='previous_chunk_failed',
             confirmation_state='unconfirmed',
             dispatch_outcome='known_failure',
             claim_owner=NULL, claim_expires_at=NULL,
             recovery_class='blocked_by_previous_chunk', updated_at=?
         WHERE job_id=? AND logical_message_sha256=?
           AND chunk_index>? AND status IN ('pending','retry')`,
      )
      .run(
        now,
        source.job_id,
        source.logical_message_sha256,
        Number(source.chunk_index),
      );
    return Object.freeze({ failedDependents: Number(result.changes) });
  }

  recoverOutboxOnExclusiveStartup() {
    this.#assertOpen();
    const now = this.#timestamp();
    const rows = this.database
      .prepare(
        `SELECT id FROM outbox_messages
         WHERE status='sending'
         ORDER BY created_at, id`,
      )
      .all();
    let safeRetry = 0;
    let ambiguousTerminal = 0;
    const ambiguousOutboxIds = [];
    const affectedJobIds = new Set();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      for (const item of rows) {
        const row = this.getOutbox(item.id);
        if (!row || row.status !== "sending") {
          continue;
        }
        if (!row.dispatch_started_at) {
          this.database
            .prepare(
              `UPDATE outbox_messages
               SET status='retry', next_attempt_at=?,
                   last_error_class='recovery_before_dispatch',
                   last_error_redacted='recovery_before_dispatch',
                   claim_owner=NULL, claim_expires_at=NULL,
                   dispatch_outcome='not_started',
                   confirmation_state='unconfirmed',
                   recovery_class='safe_before_dispatch', updated_at=?
               WHERE id=? AND status='sending'`,
            )
            .run(now, now, row.id);
          this.#appendOutboxAttemptEvent({
            outboxId: row.id,
            attemptNumber: Number(row.attempt_count),
            eventType: "retry_scheduled",
            errorClass: "recovery_before_dispatch",
            retryAt: now,
            at: now,
          });
          safeRetry += 1;
          continue;
        }
        this.database
          .prepare(
            `UPDATE outbox_messages
             SET status='failed_terminal', next_attempt_at=NULL,
                 last_error_class='ambiguous_send_outcome',
                 last_error_redacted='ambiguous_send_outcome',
                 confirmation_state='ambiguous',
                 dispatch_outcome='ambiguous',
                 claim_owner=NULL, claim_expires_at=NULL,
                 recovery_class='manual_reconcile_required', updated_at=?
             WHERE id=? AND status='sending'`,
          )
          .run(now, row.id);
        this.#appendOutboxAttemptEvent({
          outboxId: row.id,
          attemptNumber: Number(row.attempt_count),
          eventType: "ambiguous",
          errorClass: "ambiguous_send_outcome",
          at: now,
        });
        ambiguousTerminal += 1;
        ambiguousOutboxIds.push(row.id);
        affectedJobIds.add(row.job_id);
      }
      this.database.exec("COMMIT");
      for (const outboxId of ambiguousOutboxIds) {
        this.failOutboxDependents(outboxId);
      }
      for (const jobId of affectedJobIds) {
        this.reconcileJobReplyState(jobId);
      }
      return Object.freeze({
        inspected: rows.length,
        safeRetry,
        ambiguousTerminal,
        affectedJobs: affectedJobIds.size,
      });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  nextOutboxDueAt() {
    this.#assertOpen();
    const row = this.database
      .prepare(
        `SELECT MIN(
           CASE
             WHEN candidate.status='pending' THEN candidate.created_at
             ELSE candidate.next_attempt_at
           END
         ) AS due_at
         FROM outbox_messages AS candidate
         WHERE candidate.status IN ('pending','retry')
           AND candidate.attempt_count < candidate.max_attempts
           AND NOT EXISTS (
             SELECT 1
             FROM outbox_messages AS previous
             WHERE previous.job_id=candidate.job_id
               AND previous.logical_message_sha256=
                 candidate.logical_message_sha256
               AND previous.chunk_index<candidate.chunk_index
               AND previous.status<>'confirmed'
           )`,
      )
      .get();
    return row?.due_at || null;
  }

  outboxMetrics() {
    this.#assertOpen();
    const row = this.database
      .prepare(
        `SELECT
           SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
           SUM(CASE WHEN status='sending' THEN 1 ELSE 0 END) AS sending,
           SUM(CASE WHEN status='retry' THEN 1 ELSE 0 END) AS retry,
           SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS confirmed,
           SUM(CASE WHEN status='failed_terminal' THEN 1 ELSE 0 END)
             AS failed_terminal,
           SUM(CASE WHEN confirmation_state='ambiguous' THEN 1 ELSE 0 END)
             AS ambiguous
         FROM outbox_messages`,
      )
      .get();
    return Object.freeze({
      pending: Number(row.pending || 0),
      sending: Number(row.sending || 0),
      retry: Number(row.retry || 0),
      confirmed: Number(row.confirmed || 0),
      failedTerminal: Number(row.failed_terminal || 0),
      ambiguous: Number(row.ambiguous || 0),
    });
  }

  hasFinalOutbox(jobId, messageKind = null) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    if (
      messageKind !== null
      && !["result", "error", "cancelled"].includes(messageKind)
    ) {
      throw new RuntimeSpoolError("MESSAGE_KIND_INVALID");
    }
    const row = messageKind === null
      ? this.database
          .prepare(
            `SELECT COUNT(*) AS count
             FROM outbox_messages
             WHERE job_id=?
               AND message_kind IN ('result','error','cancelled')`,
          )
          .get(jobId)
      : this.database
          .prepare(
            `SELECT COUNT(*) AS count
             FROM outbox_messages
             WHERE job_id=? AND message_kind=?`,
          )
          .get(jobId, messageKind);
    return Number(row.count) > 0;
  }

  reconcileAllFinalOutboxJobs() {
    this.#assertOpen();
    const rows = this.database
      .prepare(
        `SELECT DISTINCT job_id
         FROM outbox_messages
         WHERE message_kind IN ('result','error','cancelled')
         ORDER BY job_id`,
      )
      .all();
    const states = rows.map((row) => this.reconcileJobReplyState(row.job_id));
    return Object.freeze({
      inspectedJobs: rows.length,
      replied: states.filter((state) => state.status === "replied").length,
      replyFailed: states.filter(
        (state) => state.status === "reply_failed",
      ).length,
      replyPending: states.filter(
        (state) => state.status === "reply_pending",
      ).length,
    });
  }

  reconcileJobReplyState(jobId) {
    this.#assertOpen();
    requireBoundedString(jobId, "job_id", 160);
    let job = this.getJob(jobId);
    if (!job) {
      throw new RuntimeSpoolError("JOB_NOT_FOUND");
    }
    const final = this.database
      .prepare(
        `SELECT
           COUNT(*) AS total,
           SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS confirmed,
           SUM(CASE WHEN status='failed_terminal' THEN 1 ELSE 0 END)
             AS failed
         FROM outbox_messages
         WHERE job_id=?
           AND message_kind IN ('result','error','cancelled')`,
      )
      .get(jobId);
    const total = Number(final.total || 0);
    const confirmed = Number(final.confirmed || 0);
    const failed = Number(final.failed || 0);
    if (total === 0) {
      return Object.freeze({
        status: job.status,
        total,
        confirmed,
        failed,
        reason: "final_outbox_absent",
      });
    }
    if (["succeeded", "failed_terminal", "cancelled"].includes(job.status)) {
      job = this.transitionJob(jobId, "reply_pending", {
        expectedVersion: Number(job.state_version),
        metadata: {
          transition_code: "durable_final_staged",
        },
      });
    }
    if (job.status === "reply_pending" && failed > 0) {
      job = this.transitionJob(jobId, "reply_failed", {
        expectedVersion: Number(job.state_version),
        metadata: {
          receipt_count: confirmed,
          terminal_count: failed,
          transition_code: "outbox_terminal",
        },
      });
    } else if (job.status === "reply_pending" && confirmed === total) {
      job = this.transitionJob(jobId, "replied", {
        expectedVersion: Number(job.state_version),
        metadata: {
          receipt_count: confirmed,
          transition_code: "all_chunks_confirmed",
        },
      });
    }
    return Object.freeze({
      status: job.status,
      total,
      confirmed,
      failed,
      reason:
        job.status === "replied"
          ? "all_chunks_confirmed"
          : job.status === "reply_failed"
            ? "terminal_delivery_failure"
            : "confirmation_pending",
    });
  }

  enqueueSyncEvent({
    eventId,
    objectType,
    objectId,
    canonicalPath,
    payloadRedacted,
  }) {
    this.#assertOpen();
    requireSafeToken(eventId, "event_id");
    requireSafeToken(objectType, "object_type");
    requireSafeToken(objectId, "object_id");
    requireBoundedString(canonicalPath, "canonical_path", 512);
    if (
      path.posix.isAbsolute(canonicalPath) ||
      canonicalPath.split("/").includes("..") ||
      !canonicalPath.startsWith("Private-MetaDatabase/CyberBoss/")
    ) {
      throw new RuntimeSpoolError("CANONICAL_PATH_INVALID");
    }
    const payload =
      payloadRedacted?.schema_version === 1
        ? canonicalEventJson(payloadRedacted)
        : redactedJson(payloadRedacted);
    const payloadHash = sha256(Buffer.from(payload, "utf8"));
    const id = this.#identity("sync", [eventId], "sync");
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.database
        .prepare(
          `INSERT INTO sync_spool(
            id, event_id, object_type, object_id, canonical_path,
            payload_redacted_json, payload_sha256, status, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
          ON CONFLICT(event_id) DO NOTHING`,
        )
        .run(
          id,
          eventId,
          objectType,
          objectId,
          canonicalPath,
          payload,
          payloadHash,
          now,
          now,
        );
      const row = this.database
        .prepare(
          "SELECT id, payload_sha256, status FROM sync_spool WHERE event_id=?",
        )
        .get(eventId);
      if (!row || row.id !== id || row.payload_sha256 !== payloadHash) {
        throw new IntegrityConflictError();
      }
      if (objectType === "job_event") {
        this.database
          .prepare(
            `UPDATE job_events
             SET canonical_state='sync_pending'
             WHERE id=? AND canonical_state='pending'`,
          )
          .run(objectId);
        this.database
          .prepare(
            `UPDATE jobs
             SET canonical_state='sync_pending'
             WHERE id=(
               SELECT job_id FROM job_events WHERE id=?
             ) AND canonical_state='pending'`,
          )
          .run(objectId);
      }
      this.database.exec("COMMIT");
      return Object.freeze({ ...row, event_id: eventId });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  markSyncRetry(eventId, errorClass = "canonical_unavailable") {
    this.#assertOpen();
    requireSafeToken(eventId, "event_id");
    requireSafeToken(errorClass, "error_class");
    const now = this.#timestamp();
    const result = this.database
      .prepare(
        `UPDATE sync_spool
         SET status='retry', attempt_count=attempt_count + 1,
             last_error_class=?, last_error_redacted=?,
             next_attempt_at=?, updated_at=?
         WHERE event_id=? AND status IN ('pending','syncing','retry')`,
      )
      .run(errorClass, errorClass, now, now, eventId);
    if (Number(result.changes) !== 1) {
      throw new RuntimeSpoolError("SYNC_EVENT_NOT_RETRYABLE");
    }
  }

  markSyncSynced(eventId, canonicalObjectSha256) {
    this.#assertOpen();
    requireSafeToken(eventId, "event_id");
    if (!/^[0-9a-f]{64}$/.test(canonicalObjectSha256)) {
      throw new RuntimeSpoolError("CANONICAL_HASH_INVALID");
    }
    const now = this.#timestamp();
    const result = this.database
      .prepare(
        `UPDATE sync_spool
         SET status='synced', canonical_object_sha256=?, synced_at=?,
             updated_at=?, next_attempt_at=NULL, last_error_class=NULL,
             last_error_redacted=NULL
         WHERE event_id=?
           AND status IN ('pending','syncing','retry','synced')
           AND (
             status <> 'synced' OR canonical_object_sha256 = ?
           )`,
      )
      .run(
        canonicalObjectSha256,
        now,
        now,
        eventId,
        canonicalObjectSha256,
      );
    if (Number(result.changes) !== 1) {
      throw new IntegrityConflictError();
    }
  }

  listCanonicalCandidateEvents(limit = 1_000) {
    this.#assertOpen();
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 10_000) {
      throw new RuntimeSpoolError("CANONICAL_CANDIDATE_LIMIT_INVALID");
    }
    return this.database
      .prepare(
        `SELECT
           e.id AS event_id,
           e.job_id,
           e.correlation_id,
           e.event_type,
           e.from_status,
           e.to_status,
           e.occurred_at,
           e.recorded_at,
           j.workspace_alias,
           j.runtime,
           j.input_sha256,
           j.output_sha256,
           j.status AS job_status
         FROM job_events e
         JOIN jobs j ON j.id=e.job_id
         WHERE j.status IN ('replied','reply_failed')
           AND e.canonical_state IN ('pending','sync_pending')
           AND NOT EXISTS (
             SELECT 1 FROM sync_spool s WHERE s.event_id=e.id
           )
         ORDER BY e.recorded_at, e.id
         LIMIT ?`,
      )
      .all(limit)
      .map((row) => Object.freeze({ ...row }));
  }

  listUnbatchedCanonicalEvents({
    limit = 50,
    at = this.#timestamp(),
  } = {}) {
    this.#assertOpen();
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 10_000) {
      throw new RuntimeSpoolError("CANONICAL_BATCH_LIMIT_INVALID");
    }
    const now = timestampFrom(at);
    return this.database
      .prepare(
        `SELECT event_id, object_type, object_id, canonical_path,
                payload_redacted_json, payload_sha256, status, attempt_count,
                next_attempt_at, created_at, updated_at
         FROM sync_spool
         WHERE batch_id IS NULL
           AND status IN ('pending','retry')
           AND (next_attempt_at IS NULL OR next_attempt_at<=?)
           AND json_extract(payload_redacted_json, '$.schema_version')=1
         ORDER BY created_at, event_id
         LIMIT ?`,
      )
      .all(now, limit)
      .map((row) => Object.freeze({ ...row }));
  }

  assignCanonicalBatch({
    eventIds,
    batchId,
    eventSetSha256,
    objectSha256,
  }) {
    this.#assertOpen();
    requireSafeToken(batchId, "batch_id");
    requireSha256(eventSetSha256, "batch_event_set_sha256");
    requireSha256(objectSha256, "canonical_object_sha256");
    if (
      !Array.isArray(eventIds) ||
      eventIds.length < 1 ||
      eventIds.length > 50 ||
      new Set(eventIds).size !== eventIds.length
    ) {
      throw new RuntimeSpoolError("CANONICAL_BATCH_EVENTS_INVALID");
    }
    eventIds.forEach((eventId) => requireSafeToken(eventId, "event_id"));
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      for (const eventId of eventIds) {
        this.database
          .prepare(
            `UPDATE sync_spool
             SET batch_id=COALESCE(batch_id, ?),
                 batch_event_set_sha256=COALESCE(batch_event_set_sha256, ?),
                 canonical_object_sha256=COALESCE(canonical_object_sha256, ?),
                 status=CASE WHEN status='synced' THEN status ELSE 'syncing' END,
                 updated_at=?
             WHERE event_id=?
               AND status IN ('pending','retry','syncing')
               AND (batch_id IS NULL OR batch_id=?)
               AND (
                 batch_event_set_sha256 IS NULL
                 OR batch_event_set_sha256=?
               )
               AND (
                 canonical_object_sha256 IS NULL
                 OR canonical_object_sha256=?
               )`,
          )
          .run(
            batchId,
            eventSetSha256,
            objectSha256,
            now,
            eventId,
            batchId,
            eventSetSha256,
            objectSha256,
          );
        const row = this.database
          .prepare(
            `SELECT batch_id, batch_event_set_sha256,
                    canonical_object_sha256, status
             FROM sync_spool WHERE event_id=?`,
          )
          .get(eventId);
        if (
          !row ||
          row.batch_id !== batchId ||
          row.batch_event_set_sha256 !== eventSetSha256 ||
          row.canonical_object_sha256 !== objectSha256 ||
          !["syncing", "synced"].includes(row.status)
        ) {
          throw new IntegrityConflictError();
        }
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
    return Object.freeze({
      batchId,
      eventCount: eventIds.length,
      eventSetSha256,
      objectSha256,
    });
  }

  nextCanonicalBatch(at = this.#timestamp()) {
    this.#assertOpen();
    const now = timestampFrom(at);
    const row = this.database
      .prepare(
        `SELECT batch_id, MIN(created_at) AS created_at
         FROM sync_spool
         WHERE batch_id IS NOT NULL
           AND status IN ('syncing','retry')
           AND (next_attempt_at IS NULL OR next_attempt_at<=?)
         GROUP BY batch_id
         ORDER BY created_at, batch_id
         LIMIT 1`,
      )
      .get(now);
    return row ? Object.freeze({ ...row }) : null;
  }

  listCanonicalBatch(batchId) {
    this.#assertOpen();
    requireSafeToken(batchId, "batch_id");
    return this.database
      .prepare(
        `SELECT event_id, object_type, object_id, canonical_path,
                payload_redacted_json, payload_sha256, status, attempt_count,
                next_attempt_at, created_at, updated_at, batch_id,
                batch_event_set_sha256, canonical_object_sha256,
                manifest_record_sha256, remote_object_path, verified_at,
                retry_after_ms, last_receipt_sha256
         FROM sync_spool
         WHERE batch_id=?
         ORDER BY event_id`,
      )
      .all(batchId)
      .map((row) => Object.freeze({ ...row }));
  }

  recoverCanonicalSync() {
    this.#assertOpen();
    const now = this.#timestamp();
    const result = this.database
      .prepare(
        `UPDATE sync_spool
         SET status='retry', next_attempt_at=?, retry_after_ms=0,
             last_error_class='unknown_outcome_reconcile',
             last_error_redacted='unknown_outcome_reconcile', updated_at=?
         WHERE status='syncing' AND batch_id IS NOT NULL`,
      )
      .run(now, now);
    return Object.freeze({ recovered: Number(result.changes) });
  }

  markCanonicalBatchRetry(batchId, {
    errorClass = "canonical_unavailable",
    nextAttemptAt = this.#timestamp(),
    retryAfterMs = 0,
    receiptSha256 = null,
  } = {}) {
    this.#assertOpen();
    requireSafeToken(batchId, "batch_id");
    requireSafeToken(errorClass, "error_class");
    const due = timestampFrom(nextAttemptAt);
    if (
      !Number.isSafeInteger(retryAfterMs) ||
      retryAfterMs < 0 ||
      retryAfterMs > 24 * 60 * 60 * 1_000
    ) {
      throw new RuntimeSpoolError("CANONICAL_RETRY_HINT_INVALID");
    }
    if (receiptSha256 !== null) {
      requireSha256(receiptSha256, "last_receipt_sha256");
    }
    const now = this.#timestamp();
    const result = this.database
      .prepare(
        `UPDATE sync_spool
         SET status='retry', attempt_count=attempt_count + 1,
             last_error_class=?, last_error_redacted=?,
             next_attempt_at=?, retry_after_ms=?,
             last_receipt_sha256=COALESCE(?, last_receipt_sha256),
             updated_at=?
         WHERE batch_id=? AND status IN ('syncing','retry')`,
      )
      .run(
        errorClass,
        errorClass,
        due,
        retryAfterMs,
        receiptSha256,
        now,
        batchId,
      );
    if (Number(result.changes) < 1) {
      throw new RuntimeSpoolError("CANONICAL_BATCH_NOT_RETRYABLE");
    }
    return Object.freeze({
      batchId,
      eventCount: Number(result.changes),
      nextAttemptAt: due,
      retryAfterMs,
    });
  }

  markCanonicalBatchVerified(batchId, {
    objectSha256,
    manifestRecordSha256,
    remoteObjectPath,
    receiptSha256 = null,
  }) {
    this.#assertOpen();
    requireSafeToken(batchId, "batch_id");
    requireSha256(objectSha256, "canonical_object_sha256");
    requireSha256(manifestRecordSha256, "manifest_record_sha256");
    if (receiptSha256 !== null) {
      requireSha256(receiptSha256, "last_receipt_sha256");
    }
    requireBoundedString(remoteObjectPath, "remote_object_path", 512);
    if (
      path.posix.isAbsolute(remoteObjectPath) ||
      remoteObjectPath.split("/").includes("..") ||
      !remoteObjectPath.startsWith("objects/")
    ) {
      throw new RuntimeSpoolError("REMOTE_OBJECT_PATH_INVALID");
    }
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const result = this.database
        .prepare(
          `UPDATE sync_spool
           SET status='synced', canonical_object_sha256=?,
               manifest_record_sha256=?, remote_object_path=?,
               synced_at=COALESCE(synced_at, ?), verified_at=?,
               updated_at=?, next_attempt_at=NULL, retry_after_ms=NULL,
               last_receipt_sha256=COALESCE(?, last_receipt_sha256),
               last_error_class=NULL, last_error_redacted=NULL
           WHERE batch_id=?
             AND status IN ('syncing','retry','synced')
             AND canonical_object_sha256=?`,
        )
        .run(
          objectSha256,
          manifestRecordSha256,
          remoteObjectPath,
          now,
          now,
          now,
          receiptSha256,
          batchId,
          objectSha256,
        );
      if (Number(result.changes) < 1) {
        throw new IntegrityConflictError();
      }
      this.database
        .prepare(
          `UPDATE job_events
           SET canonical_state='synced', canonical_object_sha256=?
           WHERE id IN (
             SELECT object_id FROM sync_spool
             WHERE batch_id=? AND object_type='job_event'
           )`,
        )
        .run(objectSha256, batchId);
      this.database
        .prepare(
          `UPDATE jobs
           SET canonical_state='synced', canonical_object_sha256=?
           WHERE id IN (
             SELECT DISTINCT e.job_id
             FROM job_events e
             JOIN sync_spool s
               ON s.object_type='job_event' AND s.object_id=e.id
             WHERE s.batch_id=?
           )
             AND NOT EXISTS (
               SELECT 1 FROM job_events pending
               WHERE pending.job_id=jobs.id
                 AND pending.canonical_state<>'synced'
             )`,
        )
        .run(objectSha256, batchId);
      this.database.exec("COMMIT");
      return Object.freeze({
        batchId,
        eventCount: Number(result.changes),
        objectSha256,
        verifiedAt: now,
      });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  markCanonicalBatchIntegrity(
    batchId,
    errorClass = "event_hash_conflict",
    receiptSha256 = null,
  ) {
    this.#assertOpen();
    requireSafeToken(batchId, "batch_id");
    requireSafeToken(errorClass, "error_class");
    if (receiptSha256 !== null) {
      requireSha256(receiptSha256, "last_receipt_sha256");
    }
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const result = this.database
        .prepare(
          `UPDATE sync_spool
           SET status='integrity_error', last_error_class=?,
               last_error_redacted=?, next_attempt_at=NULL,
               retry_after_ms=NULL,
               last_receipt_sha256=COALESCE(?, last_receipt_sha256),
               updated_at=?
           WHERE batch_id=? AND status<>'synced'`,
        )
        .run(errorClass, errorClass, receiptSha256, now, batchId);
      this.database
        .prepare(
          `UPDATE job_events
           SET canonical_state='integrity_error'
           WHERE id IN (
             SELECT object_id FROM sync_spool
             WHERE batch_id=? AND object_type='job_event'
           )`,
        )
        .run(batchId);
      this.database
        .prepare(
          `UPDATE jobs
           SET canonical_state='integrity_error'
           WHERE id IN (
             SELECT DISTINCT e.job_id
             FROM job_events e
             JOIN sync_spool s
               ON s.object_type='job_event' AND s.object_id=e.id
             WHERE s.batch_id=?
           )`,
        )
        .run(batchId);
      this.database.exec("COMMIT");
      return Object.freeze({
        batchId,
        eventCount: Number(result.changes),
        errorClass,
      });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
  }

  canonicalSyncStatus({
    at = this.#timestamp(),
    maxPendingEvents = 10_000,
    maxPendingBytes = 64 * 1024 * 1024,
    maxLagSeconds = 900,
    materialEventTypes = [
      "incident_declared",
      "recovery_completed",
      "release_completed",
    ],
  } = {}) {
    this.#assertOpen();
    const now = timestampFrom(at);
    if (
      !Number.isSafeInteger(maxPendingEvents) ||
      maxPendingEvents < 1 ||
      !Number.isSafeInteger(maxPendingBytes) ||
      maxPendingBytes < 1 ||
      !Number.isSafeInteger(maxLagSeconds) ||
      maxLagSeconds < 1 ||
      !Array.isArray(materialEventTypes)
    ) {
      throw new RuntimeSpoolError("CANONICAL_STATUS_LIMIT_INVALID");
    }
    const normalizedMaterialEventTypes = [...new Set(
      materialEventTypes.map((value) => String(value || "").trim()),
    )].sort();
    const expectedMaterialEventTypes = [
      "incident_declared",
      "recovery_completed",
      "release_completed",
    ];
    if (
      normalizedMaterialEventTypes.length !== expectedMaterialEventTypes.length ||
      normalizedMaterialEventTypes.some(
        (value, index) => value !== expectedMaterialEventTypes[index],
      )
    ) {
      throw new RuntimeSpoolError("CANONICAL_MATERIAL_EVENT_TYPES_INVALID");
    }
    const materialCanonicalEventTypes = normalizedMaterialEventTypes.map(
      (value) => `job.${value}`,
    );
    const materialPlaceholders = materialCanonicalEventTypes
      .map(() => "?")
      .join(", ");
    const pending = this.database
      .prepare(
        `SELECT
           COUNT(*) AS event_count,
           COALESCE(SUM(LENGTH(CAST(payload_redacted_json AS BLOB))), 0)
             AS byte_count,
           MIN(created_at) AS oldest_at,
           SUM(CASE WHEN status='integrity_error' THEN 1 ELSE 0 END)
             AS integrity_count,
           SUM(
             CASE
               WHEN status='retry'
                 AND json_extract(payload_redacted_json, '$.event_type')
                   IN (${materialPlaceholders})
               THEN 1
               ELSE 0
             END
           ) AS material_retry_count,
           MAX(last_error_class) AS last_error_class
         FROM sync_spool
         WHERE status IN ('pending','syncing','retry','integrity_error')`,
      )
      .get(...materialCanonicalEventTypes);
    const last = this.database
      .prepare(
        `SELECT canonical_object_sha256, verified_at
         FROM sync_spool
         WHERE status='synced' AND verified_at IS NOT NULL
         ORDER BY verified_at DESC, event_id DESC
         LIMIT 1`,
      )
      .get();
    const pendingEvents = Number(pending.event_count || 0);
    const pendingBytes = Number(pending.byte_count || 0);
    const oldestPendingAgeSeconds = pending.oldest_at
      ? Math.max(
          0,
          Math.floor(
            (Date.parse(now) - Date.parse(pending.oldest_at)) / 1_000,
          ),
        )
      : 0;
    const integrityCount = Number(pending.integrity_count || 0);
    const materialRetryCount = Number(pending.material_retry_count || 0);
    const mutationAllowed =
      integrityCount === 0 &&
      pendingEvents < maxPendingEvents &&
      pendingBytes < maxPendingBytes &&
      materialRetryCount === 0;
    return Object.freeze({
      state:
        integrityCount > 0
          ? "integrity_error"
          : pendingEvents > 0
            ? mutationAllowed
              ? "sync_pending"
              : "degraded"
            : last
              ? "synced"
              : "unknown",
      pendingEvents,
      pendingBytes,
      oldestPendingAgeSeconds,
      ordinaryLagExceeded: oldestPendingAgeSeconds > maxLagSeconds,
      integrityCount,
      materialRetryCount,
      lastObjectSha256: last?.canonical_object_sha256 || null,
      lastVerifiedAt: last?.verified_at || null,
      lastErrorClass: pending.last_error_class || null,
      mutationAllowed,
    });
  }

  reconcileCanonicalEventIds(canonicalEventIds) {
    this.#assertOpen();
    if (!Array.isArray(canonicalEventIds)) {
      throw new RuntimeSpoolError("CANONICAL_EVENT_SET_REQUIRED");
    }
    const local = new Set(
      this.database
        .prepare("SELECT event_id FROM sync_spool WHERE status='synced'")
        .all()
        .map((row) => row.event_id),
    );
    const canonical = new Set(canonicalEventIds);
    const missingCanonical = [...local].filter((id) => !canonical.has(id)).sort();
    const missingLocal = [...canonical].filter((id) => !local.has(id)).sort();
    return Object.freeze({
      missingCanonical,
      missingLocal,
      setDiff: missingCanonical.length + missingLocal.length,
    });
  }

  setServiceState(key, valueRedacted) {
    this.#assertOpen();
    requireSafeToken(key, "service_state_key");
    const payload = redactedJson(valueRedacted);
    const now = this.#timestamp();
    this.database
      .prepare(
        `INSERT INTO service_state(key, value_redacted_json, value_sha256, updated_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(key) DO UPDATE SET
           value_redacted_json=excluded.value_redacted_json,
           value_sha256=excluded.value_sha256,
           updated_at=excluded.updated_at`,
      )
      .run(key, payload, sha256(Buffer.from(payload, "utf8")), now);
  }

  getServiceState(key) {
    this.#assertOpen();
    requireSafeToken(key, "service_state_key");
    const row = this.database
      .prepare(
        `SELECT value_redacted_json, value_sha256, updated_at
         FROM service_state WHERE key=?`,
      )
      .get(key);
    if (!row) {
      return null;
    }
    return Object.freeze({
      value: JSON.parse(row.value_redacted_json),
      valueSha256: row.value_sha256,
      updatedAt: row.updated_at,
    });
  }

  redactExpiredPayloads(at = this.#timestamp()) {
    this.#assertOpen();
    const cutoff = timestampFrom(at);
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const inboxPayload = this.database
        .prepare(
          `UPDATE inbox_messages
           SET payload_ciphertext=?, payload_redacted_at=?
           WHERE payload_expires_at <= ? AND payload_redacted_at IS NULL
             AND payload_ciphertext IS NOT NULL`,
        )
        .run(REDACTED_SENTINEL, cutoff, cutoff);
      const inboxContext = this.database
        .prepare(
          `UPDATE inbox_messages
           SET context_token_ciphertext=?, context_redacted_at=?
           WHERE context_expires_at <= ? AND context_redacted_at IS NULL
             AND context_token_ciphertext IS NOT NULL`,
        )
        .run(REDACTED_SENTINEL, cutoff, cutoff);
      const outboxPayload = this.database
        .prepare(
          `UPDATE outbox_messages
           SET payload_ciphertext=?, payload_redacted_at=?
           WHERE payload_expires_at <= ? AND payload_redacted_at IS NULL`,
        )
        .run(REDACTED_SENTINEL, cutoff, cutoff);
      const outboxTarget = this.database
        .prepare(
          `UPDATE outbox_messages
           SET target_ref_ciphertext=?, target_ref_redacted_at=?
           WHERE target_ref_expires_at <= ? AND target_ref_redacted_at IS NULL
             AND target_ref_ciphertext IS NOT NULL`,
        )
        .run(REDACTED_SENTINEL, cutoff, cutoff);
      this.database.exec("COMMIT");
      return Object.freeze({
        inboxPayloads: Number(inboxPayload.changes),
        inboxContexts: Number(inboxContext.changes),
        outboxPayloads: Number(outboxPayload.changes),
        outboxTargets: Number(outboxTarget.changes),
      });
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    } finally {
      this.#secureDatabaseFiles();
    }
  }

  readInboundPayload(inboxId) {
    this.#assertOpen();
    const row = this.database
      .prepare("SELECT payload_ciphertext FROM inbox_messages WHERE id=?")
      .get(inboxId);
    if (!row) {
      throw new RuntimeSpoolError("INBOX_NOT_FOUND");
    }
    return this.cipher.decrypt(
      row.payload_ciphertext,
      `inbox:${inboxId}:payload`,
    );
  }

  // ── 主人设定的语气 ─────────────────────────────────────────
  //
  // 走和 inbox/outbox 载荷同一套信封（AES-256-GCM + AAD）。不用 service_state：
  // 那张表是明文列，只收枚举和安全形状的短串，而这里有主人自己写的自由文本。

  writeOwnerPersona(value) {
    this.#assertOpen();
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      throw new RuntimeSpoolError("PERSONA_OBJECT_REQUIRED");
    }
    const plain = Buffer.from(stableJson(value), "utf8");
    if (plain.length > 8 * 1024) {
      throw new RuntimeSpoolError("PERSONA_TOO_LARGE");
    }
    const now = this.#timestamp();
    this.database
      .prepare(
        `INSERT INTO owner_persona(id, payload_ciphertext, payload_sha256, updated_at)
         VALUES (1, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET
           payload_ciphertext=excluded.payload_ciphertext,
           payload_sha256=excluded.payload_sha256,
           updated_at=excluded.updated_at`,
      )
      .run(
        this.cipher.encrypt(plain, "owner_persona:1:payload"),
        sha256(plain),
        now,
      );
    return Object.freeze({ updatedAt: now });
  }

  readOwnerPersona() {
    this.#assertOpen();
    const row = this.database
      .prepare(
        "SELECT payload_ciphertext, payload_sha256, updated_at FROM owner_persona WHERE id=1",
      )
      .get();
    if (!row) {
      return null;
    }
    const plain = this.cipher.decrypt(
      row.payload_ciphertext,
      "owner_persona:1:payload",
    );
    if (sha256(plain) !== row.payload_sha256) {
      throw new IntegrityConflictError();
    }
    return Object.freeze({
      value: JSON.parse(plain.toString("utf8")),
      updatedAt: row.updated_at,
    });
  }

  // user_id -> role。对话栏用它给发件人打「主人」标签。判权限不走这里，
  // 那条路在 UserAdmission；这里只是让主人在列表上分得清谁是谁。
  listUserRolesForOwner() {
    this.#assertOpen();
    const roles = new Map();
    try {
      for (const row of this.database.prepare("SELECT user_id, role FROM users").all()) {
        roles.set(row.user_id, row.role);
      }
    } catch {
      // 单人安装可能还没有 users 表，那就没有标签，不是错误。
    }
    return roles;
  }

  // ── 机器人自己先开口的那些消息 ───────────────────────────
  //
  // 主动打招呼、到点的提醒、入门引导都不经过 outbox（outbox 的每一行都要挂在
  // 一个 job 上，而它们没有 job），发出去之后在库里一个字都不留。于是后台
  // 「对话」栏看得见别人说的每一句、它答的每一句，唯独看不见它自己主动说的。
  //
  // 记录失败**绝不能**影响发送：宁可这条在面板上看不到，也不能因为记账出错就
  // 让主人收不到提醒。

  recordBotInitiatedMessage({ kind, senderId, text, delivered = false, errorClass = "" }) {
    this.#assertOpen();
    if (!["checkin", "reminder", "onboarding", "system"].includes(kind)) {
      throw new RuntimeSpoolError("BOT_MESSAGE_KIND_INVALID");
    }
    const body = String(text || "");
    if (!body.trim()) {
      throw new RuntimeSpoolError("BOT_MESSAGE_EMPTY");
    }
    const now = this.#timestamp();
    const id = this.#identity("botmsg", [kind, now, body.slice(0, 64)], "botmsg");
    // 收件人是微信号，属于真实 PII，和正文一起进信封，不单独明文存一列。
    const plain = Buffer.from(
      stableJson({ senderId: String(senderId || ""), text: body }),
      "utf8",
    );
    this.database
      .prepare(
        `INSERT INTO bot_initiated_messages(
           id, kind, payload_ciphertext, payload_sha256, delivered, error_class, created_at
         ) VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(id) DO NOTHING`,
      )
      .run(
        id,
        kind,
        this.cipher.encrypt(plain, `botmsg:${id}:payload`),
        sha256(plain),
        delivered ? 1 : 0,
        errorClass ? String(errorClass).slice(0, 64) : null,
        now,
      );
    return Object.freeze({ id, createdAt: now });
  }

  listBotInitiatedForOwner({ limit = 50, since = "", until = "" } = {}) {
    this.#assertOpen();
    const bounded = Math.max(1, Math.min(2000, Number(limit) || 50));
    const clauses = [];
    const params = [];
    if (typeof since === "string" && since) {
      clauses.push("created_at >= ?");
      params.push(since);
    }
    if (typeof until === "string" && until) {
      clauses.push("created_at <= ?");
      params.push(until);
    }
    const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
    return this.database
      .prepare(
        `SELECT id, kind, payload_ciphertext, delivered, error_class, created_at
         FROM bot_initiated_messages
         ${where}
         ORDER BY created_at DESC, id DESC
         LIMIT ?`,
      )
      .all(...params, bounded)
      .map((row) => {
        let payload = { senderId: "", text: "" };
        let available = false;
        try {
          payload = JSON.parse(
            this.cipher
              .decrypt(row.payload_ciphertext, `botmsg:${row.id}:payload`)
              .toString("utf8"),
          );
          available = true;
        } catch {
          // 单条读坏不该让整栏空白。
        }
        return Object.freeze({
          id: row.id,
          kind: row.kind,
          senderId: payload.senderId || "",
          text: payload.text || "",
          available,
          delivered: Number(row.delivered) === 1,
          errorClass: row.error_class || "",
          createdAt: row.created_at,
        });
      });
  }

  // ── 主人后台的「对话」一栏 ──────────────────────────────────
  //
  // 下面两个方法解密真实聊天内容，是这个类里权限最高的读。名字带 ForOwner 是为
  // 了让调用点一眼看出这件事：它们只允许挂在带真令牌的后台路由上，不得进日志、
  // 不得进证据文件、不得进 canonical 同步。
  //
  // 载荷过了保留期会被 redactExpiredPayloads 置空，那时 ciphertext 是 NULL；这
  // 里返回 payloadAvailable=false 而不是抛错——"已经按保留期清掉了"本身就是要显
  // 示给主人看的状态。

  // 时间范围在 SQL 里筛（received_at 上有序，走得动）；关键词只能在解密之后
  // 在内存里筛——正文是密文，SQL 看不见它，这是加密存储必然的代价。
  listRecentInboundForOwner({ limit = 50, since = "", until = "" } = {}) {
    this.#assertOpen();
    const bounded = Math.max(1, Math.min(2000, Number(limit) || 50));
    const clauses = [];
    const params = [];
    if (typeof since === "string" && since) {
      clauses.push("received_at >= ?");
      params.push(since);
    }
    if (typeof until === "string" && until) {
      clauses.push("received_at <= ?");
      params.push(until);
    }
    const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
    const rows = this.database
      .prepare(
        `SELECT id, correlation_id, user_id, message_type, status,
                reject_reason, received_at, payload_ciphertext
         FROM inbox_messages
         ${where}
         ORDER BY received_at DESC, id DESC
         LIMIT ?`,
      )
      .all(...params, bounded);
    return rows.map((row) => {
      let payload = null;
      let payloadAvailable = false;
      if (row.payload_ciphertext !== null) {
        try {
          payload = JSON.parse(
            this.cipher
              .decrypt(row.payload_ciphertext, `inbox:${row.id}:payload`)
              .toString("utf8"),
          );
          payloadAvailable = true;
        } catch {
          // 单条读坏不该让整栏空白。
          payload = null;
        }
      }
      return Object.freeze({
        inboxId: row.id,
        correlationId: row.correlation_id,
        userId: row.user_id || "",
        messageType: row.message_type,
        status: row.status,
        rejectReason: row.reject_reason || "",
        receivedAt: row.received_at,
        payloadAvailable,
        payload,
      });
    });
  }

  // 给了 correlationIds 就只取这些来信的回复——按人或按时间筛过之后，没必要
  // 把整张出站表都解密一遍。
  listRecentOutboundForOwner({ limit = 80, correlationIds = null } = {}) {
    this.#assertOpen();
    const bounded = Math.max(1, Math.min(2000, Number(limit) || 80));
    let rows;
    if (Array.isArray(correlationIds)) {
      if (!correlationIds.length) {
        return [];
      }
      // SQLite 的变量上限是 999，分批取。
      rows = [];
      for (let offset = 0; offset < correlationIds.length; offset += 400) {
        const slice = correlationIds.slice(offset, offset + 400);
        rows.push(...this.database
          .prepare(
            `SELECT id, job_id, correlation_id, message_kind, chunk_index,
                    chunk_count, status, attempt_count, last_error_class,
                    created_at, confirmed_at, payload_ciphertext
             FROM outbox_messages
             WHERE correlation_id IN (${slice.map(() => "?").join(",")})
             ORDER BY created_at DESC, id DESC`,
          )
          .all(...slice));
      }
    } else {
      rows = this.database
        .prepare(
          `SELECT id, job_id, correlation_id, message_kind, chunk_index,
                  chunk_count, status, attempt_count, last_error_class,
                  created_at, confirmed_at, payload_ciphertext
           FROM outbox_messages
           ORDER BY created_at DESC, id DESC
           LIMIT ?`,
        )
        .all(bounded);
    }
    return rows.map((row) => {
      let text = "";
      let payloadAvailable = false;
      if (row.payload_ciphertext !== null) {
        try {
          text = this.cipher
            .decrypt(row.payload_ciphertext, `outbox:${row.id}:payload`)
            .toString("utf8");
          payloadAvailable = true;
        } catch {
          text = "";
        }
      }
      return Object.freeze({
        outboxId: row.id,
        jobId: row.job_id,
        correlationId: row.correlation_id,
        messageKind: row.message_kind,
        chunkIndex: Number(row.chunk_index),
        chunkCount: Number(row.chunk_count),
        status: row.status,
        attemptCount: Number(row.attempt_count),
        lastErrorClass: row.last_error_class || "",
        createdAt: row.created_at,
        confirmedAt: row.confirmed_at || "",
        payloadAvailable,
        text,
      });
    });
  }

  listRecentJobsForOwner({ limit = 80, correlationIds = null } = {}) {
    this.#assertOpen();
    const bounded = Math.max(1, Math.min(2000, Number(limit) || 80));
    let rows;
    if (Array.isArray(correlationIds)) {
      if (!correlationIds.length) {
        return [];
      }
      rows = [];
      for (let offset = 0; offset < correlationIds.length; offset += 400) {
        const slice = correlationIds.slice(offset, offset + 400);
        rows.push(...this.database
          .prepare(
            `SELECT id, correlation_id, status, error_class, attempt_count,
                    created_at, finished_at
             FROM jobs
             WHERE correlation_id IN (${slice.map(() => "?").join(",")})`,
          )
          .all(...slice));
      }
    } else {
      rows = this.database
        .prepare(
          `SELECT id, correlation_id, status, error_class, attempt_count,
                  created_at, finished_at
           FROM jobs
           ORDER BY created_at DESC, id DESC
           LIMIT ?`,
        )
        .all(bounded);
    }
    return rows
      .map((row) => Object.freeze({
        jobId: row.id,
        correlationId: row.correlation_id,
        status: row.status,
        errorClass: row.error_class || "",
        attemptCount: Number(row.attempt_count),
        createdAt: row.created_at,
        finishedAt: row.finished_at || "",
      }));
  }

  readInboundContextToken(inboxId) {
    this.#assertOpen();
    const row = this.database
      .prepare(
        "SELECT context_token_ciphertext FROM inbox_messages WHERE id=?",
      )
      .get(inboxId);
    if (!row) {
      throw new RuntimeSpoolError("INBOX_NOT_FOUND");
    }
    if (row.context_token_ciphertext === null) {
      return null;
    }
    return this.cipher.decrypt(
      row.context_token_ciphertext,
      `inbox:${inboxId}:context`,
    );
  }

  getJob(jobId) {
    this.#assertOpen();
    const row = this.database
      .prepare(
        `SELECT id, correlation_id, inbox_id, workspace_alias, runtime,
                operation_class, status, state_version, attempt_count,
                max_attempts, input_sha256, output_sha256, created_at,
                queued_at, started_at, finished_at, updated_at, canonical_state,
                scheduler_managed, lease_owner, lease_heartbeat_at,
                lease_expires_at, dispatch_started_at, cancel_requested_at,
                runtime_thread_hash, runtime_turn_hash, last_runtime_event_at,
                error_class, error_redacted, user_id
         FROM jobs WHERE id=?`,
      )
      .get(jobId);
    return row ? Object.freeze({ ...row }) : null;
  }

  getInbox(inboxId) {
    this.#assertOpen();
    const row = this.database
      .prepare(
        `SELECT id, source, source_account_hash, source_message_id,
                correlation_id, user_ref_hash, message_type, payload_sha256,
                cursor_batch_id, status, reject_reason, received_at, durable_at,
                consumed_at, payload_expires_at, payload_redacted_at,
                context_redacted_at, user_id
         FROM inbox_messages WHERE id=?`,
      )
      .get(inboxId);
    return row ? Object.freeze({ ...row }) : null;
  }

  listJobEvents(jobId) {
    this.#assertOpen();
    return this.database
      .prepare(
        `SELECT id, job_id, correlation_id, event_type, from_status, to_status,
                payload_redacted_json, payload_sha256, occurred_at, recorded_at,
                canonical_state, canonical_object_sha256
         FROM job_events WHERE job_id=? ORDER BY recorded_at, id`,
      )
      .all(jobId)
      .map((row) => Object.freeze({ ...row }));
  }

  counts() {
    this.#assertOpen();
    const result = {};
    for (const table of [
      "inbox_messages",
      "jobs",
      "job_events",
      "outbox_messages",
      "sync_spool",
      "service_state",
    ]) {
      result[table] = Number(
        this.database.prepare(`SELECT COUNT(*) AS count FROM ${table}`).get()
          .count,
      );
    }
    return Object.freeze(result);
  }

  migrationRecords() {
    this.#assertOpen();
    return this.database
      .prepare(
        "SELECT version, applied_at, source_commit, checksum_sha256 FROM schema_migrations ORDER BY version",
      )
      .all()
      .map((row) => Object.freeze({ ...row }));
  }

  schemaSql() {
    this.#assertOpen();
    return this.database
      .prepare(
        `SELECT type, name, tbl_name, sql
         FROM sqlite_schema
         WHERE sql IS NOT NULL
         ORDER BY CASE type
           WHEN 'table' THEN 1 WHEN 'index' THEN 2 WHEN 'trigger' THEN 3 ELSE 4
         END, name`,
      )
      .all()
      .map((row) => `${row.sql};`)
      .join("\n\n");
  }

  pragmaStatus() {
    this.#assertOpen();
    const journalMode = this.database.prepare("PRAGMA journal_mode").get()
      .journal_mode;
    const synchronousValue = Number(
      this.database.prepare("PRAGMA synchronous").get().synchronous,
    );
    const foreignKeys = Number(
      this.database.prepare("PRAGMA foreign_keys").get().foreign_keys,
    );
    const busyTimeoutMs = Number(
      this.database.prepare("PRAGMA busy_timeout").get().timeout,
    );
    const integrityCheck = this.database.prepare("PRAGMA integrity_check").get()
      .integrity_check;
    return Object.freeze({
      journalMode: String(journalMode).toLowerCase(),
      synchronous:
        synchronousValue === 2 ? "full" : `unexpected:${synchronousValue}`,
      foreignKeys: foreignKeys === 1,
      busyTimeoutMs,
      integrityCheck,
    });
  }

  close() {
    if (this.closed) {
      return;
    }
    this.#secureDatabaseFiles();
    this.database.close();
    this.cipher.destroy();
    this.identityKey.fill(0);
    this.closed = true;
    this.#secureDatabaseFiles();
  }
}

module.exports = {
  DEFAULT_OUTBOX_LEASE_MS,
  DEFAULT_PAYLOAD_TTL_MS,
  IntegrityConflictError,
  MIGRATIONS,
  PayloadRedactedError,
  RuntimeSpoolDatabase,
  RuntimeSpoolError,
  USER_SCOPED_LEGACY_TABLES,
  canonicalEventJson,
  deriveOwnerUserId,
  deriveStableIds,
  redactedJson,
  requireUserId,
  stableJson,
};
