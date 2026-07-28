"use strict";

// CB-800 acceptance: AC-029 (export and deletion), AC-030 (data boundary),
// AC-035 (backup and restore).

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { SqliteUserRepository } = require("../src/services/users/user-repository");
const { SqliteInviteCodeStore } = require("../src/services/users/invite-code-store");
const { RegistrationService } = require("../src/services/users/registration-service");
const {
  CredentialVaultError,
  SqliteCredentialVault,
} = require("../src/services/secrets/credential-vault");
const {
  CanonicalEnvelopeError,
  FORBIDDEN_FIELDS,
  assertCommitAllowed,
  buildUserFact,
  planCanonicalSync,
} = require("../src/services/canonical/user-fact-envelope");
const {
  ObjectKeyError,
  assertKeyBelongsToUser,
  keyBelongsToUser,
  previousVersionKey,
  userObjectKey,
  userObjectPrefix,
} = require("../src/services/canonical/object-key");
const {
  DualCopyBackupCoordinator,
  DualCopyBackupError,
} = require("../src/services/backup/dual-copy-receipt");
const {
  IRREVERSIBLE_ACTIONS,
  ORDER,
  buildDeletionPlan,
  resumePoint,
} = require("../src/services/privacy/deletion-plan");
const {
  EXCLUDED_FROM_EXPORT,
  LifecycleError,
  SqliteDeletionReceiptStore,
  SqliteUserExporter,
  buildDeletionTombstone,
  buildUserExportManifest,
  executeDeletion,
  writeTombstone,
} = require("../src/services/privacy/user-data-lifecycle");

const KEY = Buffer.alloc(32, 3);
const IDENTITY_KEY = Buffer.alloc(32, 5);
const INVITE_SECRET = Buffer.alloc(32, 13);
const MASTER_KEY = Buffer.alloc(32, 17);
const BOT = "bot-account-800";
const NOW = "2026-07-28T09:00:00.000Z";

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb800-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const databasePath = path.join(directory, "runtime.db");
  const spool = new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  const database = new DatabaseSync(databasePath);
  t.after(() => database.close());
  database.exec("PRAGMA foreign_keys=ON");
  const users = new SqliteUserRepository({ database, identityKey: IDENTITY_KEY });
  const invites = new SqliteInviteCodeStore({ database, secret: INVITE_SECRET });
  const registration = new RegistrationService({ userRepository: users, inviteStore: invites });
  const activate = (senderRef) => {
    const invite = invites.issue({ maxUses: 1, ttlMs: 60_000 });
    registration.start({ botAccountRef: BOT, senderRef, inviteCode: invite.code });
    return registration.consent({ botAccountRef: BOT, senderRef, accepted: true }).user;
  };
  return { directory, database, spool, users, activate };
}

function stubUserId(seed) {
  return `usr_${"a".repeat(10)}${seed}${"b".repeat(10)}`;
}

// ---------------------------------------------------------------------------
// AC-030 — canonical envelope and data boundary
// ---------------------------------------------------------------------------

test("AC-030 migration 7 is additive and the ledger records every version", (t) => {
  const { database } = harness(t);
  const versions = database
    .prepare("SELECT version, source_commit FROM schema_migrations ORDER BY version")
    .all();
  assert.deepEqual(
    versions.map((row) => row.version),
    [1, 2, 3, 4, 5, 6, 7],
  );
  assert.equal(versions.at(-1).source_commit, "CB-800");
  for (const table of ["inbox_messages", "jobs", "outbox_messages", "sync_spool", "users"]) {
    assert.ok(
      database
        .prepare("SELECT 1 AS present FROM sqlite_schema WHERE type='table' AND name=?")
        .get(table),
      `${table} survived migration 7`,
    );
  }
  for (const table of ["deletion_requests", "deletion_receipts", "export_receipts"]) {
    assert.ok(
      database
        .prepare("SELECT 1 AS present FROM sqlite_schema WHERE type='table' AND name=?")
        .get(table),
      `${table} was created`,
    );
  }
});

test("AC-030 the envelope refuses every frozen forbidden field at the top level", () => {
  for (const field of FORBIDDEN_FIELDS) {
    assert.throws(
      () =>
        buildUserFact({
          userId: stubUserId("1"),
          type: "note.created",
          occurredAt: NOW,
          payload: { [field]: "anything" },
          sourceEventId: "evt-1",
        }),
      (error) => error.code === "CANONICAL_RAW_CONTENT_FORBIDDEN",
      `${field} must be refused`,
    );
  }
});

test("AC-030 a forbidden field nested below the top level is still refused", () => {
  // The starter reference only checked the top level; a nested prompt walked
  // straight into the canonical area.
  assert.throws(
    () =>
      buildUserFact({
        userId: stubUserId("1"),
        type: "note.created",
        occurredAt: NOW,
        payload: { meta: { context: { prompt: "the whole conversation" } } },
        sourceEventId: "evt-2",
      }),
    (error) =>
      error.code === "CANONICAL_RAW_CONTENT_FORBIDDEN" &&
      error.detail === "payload.meta.context.prompt",
  );
  assert.throws(
    () =>
      buildUserFact({
        userId: stubUserId("1"),
        type: "note.created",
        occurredAt: NOW,
        payload: { items: [{ ok: 1 }, { raw_chat: "..." }] },
        sourceEventId: "evt-3",
      }),
    (error) => error.code === "CANONICAL_RAW_CONTENT_FORBIDDEN",
  );
});

test("AC-030 a forbidden name embedded in a longer name is refused", () => {
  for (const field of ["user_api_key", "openai_secret", "msg_raw_chat", "PROMPT", "api-key"]) {
    assert.throws(
      () =>
        buildUserFact({
          userId: stubUserId("1"),
          type: "note.created",
          occurredAt: NOW,
          payload: { [field]: "x" },
          sourceEventId: "evt-4",
        }),
      (error) => error.code === "CANONICAL_RAW_CONTENT_FORBIDDEN",
      `${field} must be refused`,
    );
  }
});

test("AC-030 a secret value in an innocuously named field is refused", () => {
  const secrets = [
    "sk-proj-abcdefghijklmnopqrstuvwxyz012345",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "AIzaSyA0123456789abcdefghijklmnopqrstuvw",
    "wxid_abcd1234",
    "Bearer abcdefghijklmnop",
    "-----BEGIN PRIVATE KEY-----",
  ];
  for (const value of secrets) {
    assert.throws(
      () =>
        buildUserFact({
          userId: stubUserId("1"),
          type: "note.created",
          occurredAt: NOW,
          payload: { note: value },
          sourceEventId: "evt-5",
        }),
      (error) => error.code === "CANONICAL_SECRET_VALUE_FORBIDDEN",
      `${value.slice(0, 12)} must be refused on its value`,
    );
  }
});

test("AC-030 an ordinary fact is daily and a critical fact is immediate", () => {
  const userId = stubUserId("1");
  const ordinary = buildUserFact({
    userId,
    type: "note.created",
    occurredAt: NOW,
    payload: { count: 3 },
    sourceEventId: "evt-6",
  });
  assert.equal(ordinary.sync_priority, "daily");
  for (const type of [
    "release.published",
    "incident.opened",
    "recovery.completed",
    "user.deleted",
    "security.credential_revoked",
  ]) {
    const critical = buildUserFact({
      userId,
      type,
      occurredAt: NOW,
      payload: {},
      sourceEventId: `evt-${type}`,
    });
    assert.equal(critical.sync_priority, "immediate", type);
  }
});

test("AC-030 no new fact means no commit at all", () => {
  const empty = planCanonicalSync([], { now: NOW });
  assert.equal(empty.create_commit, false);
  assert.equal(empty.reason, "no_new_facts");
  assert.throws(() => assertCommitAllowed(empty), (error) =>
    error.code === "CANONICAL_EMPTY_COMMIT_FORBIDDEN");

  const userId = stubUserId("1");
  const ordinary = buildUserFact({
    userId,
    type: "note.created",
    occurredAt: NOW,
    payload: {},
    sourceEventId: "evt-7",
  });
  // Daily not yet due and nothing critical: still no commit.
  const deferred = planCanonicalSync([ordinary], {
    now: NOW,
    lastDailySyncAt: "2026-07-28T08:00:00.000Z",
  });
  assert.equal(deferred.create_commit, false);
  assert.equal(deferred.deferred_daily_count, 1);

  // A critical fact commits immediately even inside the daily window.
  const critical = buildUserFact({
    userId,
    type: "incident.opened",
    occurredAt: NOW,
    payload: {},
    sourceEventId: "evt-8",
  });
  const now = planCanonicalSync([ordinary, critical], {
    now: NOW,
    lastDailySyncAt: "2026-07-28T08:00:00.000Z",
  });
  assert.equal(now.create_commit, true);
  assert.equal(now.reason, "critical_event");
  assert.equal(now.immediate.length, 1);
  assert.equal(now.daily.length, 0);
  assert.equal(assertCommitAllowed(now), true);
});

test("AC-030 the same source event produces one fact, not two", () => {
  const userId = stubUserId("1");
  const build = () =>
    buildUserFact({
      userId,
      type: "note.created",
      occurredAt: NOW,
      payload: { a: 1, b: 2 },
      sourceEventId: "evt-9",
    });
  const first = build();
  const second = build();
  assert.equal(first.fact_id, second.fact_id);
  assert.equal(first.content_hash, second.content_hash);
  assert.equal(first.idempotency_key, second.idempotency_key);
  const plan = planCanonicalSync([first, second], { now: NOW });
  assert.equal(plan.daily.length, 1);
  assert.equal(plan.duplicate_count, 1);
});

test("AC-030 the envelope module is not a second fact store", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/services/canonical/user-fact-envelope.js"),
    "utf8",
  );
  assert.ok(!source.includes("CREATE TABLE"), "no table of its own");
  assert.ok(!source.includes("fetch("), "no remote path of its own");
  assert.ok(!source.includes("node:fs"), "no file store of its own");
  assert.ok(!source.includes("DatabaseSync"), "no database of its own");
});

test("AC-030 object keys stay inside the owning user's prefix", () => {
  const alice = stubUserId("1");
  const bob = stubUserId("2");
  const key = userObjectKey({ userId: alice, category: "export", objectId: "obj1", version: 1 });
  assert.ok(key.startsWith(userObjectPrefix(alice)));
  assert.equal(keyBelongsToUser(key, bob), false);
  assert.throws(() => assertKeyBelongsToUser(key, bob), (error) =>
    error.code === "OBJECT_KEY_SCOPE_VIOLATION");

  for (const bad of ["../escape", "a/b", "..", "obj id", ""]) {
    assert.throws(
      () => userObjectKey({ userId: alice, category: "export", objectId: bad, version: 1 }),
      ObjectKeyError,
      `objectId ${JSON.stringify(bad)} must be refused`,
    );
  }
  assert.throws(
    () => userObjectKey({ userId: alice, category: "arbitrary", objectId: "o", version: 1 }),
    (error) => error.code === "OBJECT_CATEGORY_NOT_ALLOWED",
  );
  // Rollback support: a new version is a new key, so the old object survives.
  const v2 = userObjectKey({ userId: alice, category: "export", objectId: "obj1", version: 2 });
  assert.notEqual(v2, key);
  assert.equal(previousVersionKey({ userId: alice, category: "export", objectId: "obj1", version: 2 }), key);
});

// ---------------------------------------------------------------------------
// AC-035 — encrypted backup, dual copy, isolated restore
// ---------------------------------------------------------------------------

function objectClient() {
  const store = new Map();
  let counter = 0;
  return {
    store,
    async putObject({ key, body }) {
      counter += 1;
      store.set(key, Buffer.from(body));
      return { versionId: `v${counter}` };
    },
    async getObject({ key }) {
      if (!store.has(key)) {
        const error = new Error("NOT_FOUND");
        error.code = "NOT_FOUND";
        throw error;
      }
      return store.get(key);
    },
  };
}

function backupHarness(overrides = {}) {
  const snapshot = Buffer.from("SQLite format 3\u0000runtime-snapshot-bytes");
  const decryptCalls = [];
  const restored = [];
  const r2 = overrides.r2 || objectClient();
  const oci = overrides.oci || objectClient();
  const coordinator = new DualCopyBackupCoordinator({
    snapshotRuntimeDb: overrides.snapshotRuntimeDb || (async () => snapshot),
    // A deliberately reversible stand-in: the real cipher is exercised by the
    // credential vault suite. What matters here is that the bytes change and
    // that integrity is proved before the cipher is reached.
    encryptSnapshot: overrides.encryptSnapshot || (async (plain) =>
      Buffer.from(plain.map((byte) => byte ^ 0x5a))),
    decryptSnapshot: overrides.decryptSnapshot || (async (cipher) => {
      decryptCalls.push(cipher.length);
      return Buffer.from(cipher.map((byte) => byte ^ 0x5a));
    }),
    validateSnapshot: overrides.validateSnapshot || (async (plain) => {
      if (!plain.subarray(0, 15).toString().startsWith("SQLite format")) {
        throw new Error("NOT_A_SQLITE_IMAGE");
      }
    }),
    restoreRuntimeDbIsolated:
      overrides.restoreRuntimeDbIsolated ||
      (async ({ snapshot: image, restoreRoot }) => {
        restored.push(restoreRoot);
        return { restoreRoot, bytes: image.length };
      }),
    verifyRelations: overrides.verifyRelations || (async () => ({ ok: true, tables: 19 })),
    r2,
    oci,
  });
  return { coordinator, snapshot, r2, oci, decryptCalls, restored };
}

test("AC-035 a receipt is only issued when both copies landed", async () => {
  const { coordinator, r2, oci } = backupHarness();
  const receipt = await coordinator.create({
    backupId: "backup-2026-07-28",
    releaseId: "release-v0.0.0.8",
    createdAt: NOW,
  });
  assert.equal(receipt.dualCopy, true);
  assert.ok(receipt.copies.r2 && receipt.copies.oci);
  assert.equal(r2.store.size, 1);
  assert.equal(oci.store.size, 1);
  assert.equal(receipt.key, "CyberBoss/backups/2026-07-28/backup-2026-07-28.enc");
});

test("AC-035 a failed second copy produces no receipt at all", async () => {
  const failing = objectClient();
  failing.putObject = async () => {
    const error = new Error("OCI_UNAVAILABLE");
    error.code = "OCI_UNAVAILABLE";
    throw error;
  };
  const { coordinator } = backupHarness({ oci: failing });
  await assert.rejects(
    coordinator.create({ backupId: "backup-b", releaseId: "release-x", createdAt: NOW }),
    (error) =>
      error instanceof DualCopyBackupError &&
      error.code === "BACKUP_DUAL_COPY_INCOMPLETE" &&
      error.detail.includes("oci:OCI_UNAVAILABLE"),
  );
});

test("AC-035 a snapshot that was not actually encrypted is refused", async () => {
  const { coordinator } = backupHarness({ encryptSnapshot: async (plain) => plain });
  await assert.rejects(
    coordinator.create({ backupId: "backup-c", releaseId: "release-x", createdAt: NOW }),
    (error) => error.code === "BACKUP_NOT_ENCRYPTED",
  );
});

test("AC-035 integrity is proved before the ciphertext reaches the cipher", async () => {
  const { coordinator, r2, decryptCalls } = backupHarness();
  const receipt = await coordinator.create({
    backupId: "backup-d",
    releaseId: "release-x",
    createdAt: NOW,
  });
  const corrupted = Buffer.from(r2.store.get(receipt.key));
  corrupted[0] ^= 0xff;
  r2.store.set(receipt.key, corrupted);

  await assert.rejects(
    coordinator.restore({ receipt, source: "r2", restoreRoot: "/tmp/isolated" }),
    (error) => error.code === "BACKUP_INTEGRITY_FAILED",
  );
  assert.deepEqual(decryptCalls, [], "decryption was never attempted on a corrupt object");
});

test("AC-035 the second copy carries the restore when the first is unreadable", async () => {
  const { coordinator, r2 } = backupHarness();
  const receipt = await coordinator.create({
    backupId: "backup-e",
    releaseId: "release-x",
    createdAt: NOW,
  });
  r2.store.delete(receipt.key);

  const outcome = await coordinator.restore({
    receipt,
    source: "oci",
    restoreRoot: "/tmp/isolated-oci",
  });
  assert.equal(outcome.ok, true);
  assert.equal(outcome.source, "oci");
  assert.equal(outcome.isolated, true);
  assert.equal(outcome.relations.ok, true);

  const both = await coordinator.verifyBothCopies({ receipt, restoreRoot: "/tmp/verify" });
  assert.equal(both.bothRestorable, false);
  assert.equal(both.degraded, true);
  assert.equal(both.oci.ok, true);
  assert.equal(both.r2.ok, false);
});

test("AC-035 both copies restore independently on a healthy backup", async () => {
  const { coordinator, restored } = backupHarness();
  const receipt = await coordinator.create({
    backupId: "backup-f",
    releaseId: "release-x",
    createdAt: NOW,
  });
  const both = await coordinator.verifyBothCopies({ receipt, restoreRoot: "/tmp/verify" });
  assert.equal(both.bothRestorable, true);
  assert.equal(both.degraded, false);
  assert.deepEqual(restored, ["/tmp/verify/r2", "/tmp/verify/oci"]);
  assert.ok(restored.every((root) => root.startsWith("/tmp/verify/")), "restore stayed isolated");
});

test("AC-035 a restore that breaks the relational shape is refused", async () => {
  const { coordinator } = backupHarness({
    verifyRelations: async () => ({ ok: false, reason: "orphan_jobs_rows" }),
  });
  const receipt = await coordinator.create({
    backupId: "backup-g",
    releaseId: "release-x",
    createdAt: NOW,
  });
  await assert.rejects(
    coordinator.restore({ receipt, source: "r2", restoreRoot: "/tmp/isolated" }),
    (error) =>
      error.code === "BACKUP_RELATION_CHECK_FAILED" && error.detail === "orphan_jobs_rows",
  );
});

test("AC-035 a receipt that never had two copies cannot be used to restore", async () => {
  const { coordinator } = backupHarness();
  const receipt = await coordinator.create({
    backupId: "backup-h",
    releaseId: "release-x",
    createdAt: NOW,
  });
  const forged = { ...receipt, copies: { r2: receipt.copies.r2, oci: null } };
  await assert.rejects(
    coordinator.restore({ receipt: forged, source: "r2", restoreRoot: "/tmp/x" }),
    (error) => error.code === "BACKUP_RECEIPT_NOT_DUAL_COPY",
  );
});

// ---------------------------------------------------------------------------
// AC-029 — scoped export, scoped deletion, crypto-shred, tombstone
// ---------------------------------------------------------------------------

test("AC-029 a user exports their own rows and never a neighbour's", (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const bob = activate("sender-bob");
  const insert = database.prepare(
    `INSERT INTO consent_events(event_id, user_id, policy_version, scope, decision, occurred_at)
     VALUES (?,?,?,?,?,?)`,
  );
  insert.run("evt-alice-1", alice.user_id, "v1", "profile", "accepted", NOW);
  insert.run("evt-alice-2", alice.user_id, "v1", "analytics", "accepted", NOW);
  insert.run("evt-bob-1", bob.user_id, "v1", "profile", "accepted", NOW);

  const exporter = new SqliteUserExporter({ database, now: () => NOW });
  const result = exporter.export({ userId: alice.user_id });
  const rows = result.data.consent_events;
  assert.equal(rows.length, 3, "two consent rows plus the registration consent");
  assert.ok(rows.every((row) => row.user_id === alice.user_id));
  assert.equal(result.manifest.userId, alice.user_id);

  const bobResult = exporter.export({ userId: bob.user_id });
  assert.ok(bobResult.data.consent_events.every((row) => row.user_id === bob.user_id));
  const allIds = new Set(rows.map((row) => row.event_id));
  assert.ok(
    bobResult.data.consent_events.every((row) => !allIds.has(row.event_id)),
    "the two exports share no row",
  );
});

test("AC-029 an export never carries key or credential material", (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const vault = new SqliteCredentialVault({ database, masterKey: MASTER_KEY });
  vault.putCredential({
    userId: alice.user_id,
    providerId: "openai",
    apiKey: "sk-proj-abcdefghijklmnopqrstuvwxyz012345",
  });

  const exporter = new SqliteUserExporter({ database, now: () => NOW });
  const result = exporter.export({ userId: alice.user_id });
  for (const excluded of Object.keys(EXCLUDED_FROM_EXPORT)) {
    assert.ok(!Object.hasOwn(result.data, excluded), `${excluded} is absent from the export`);
  }
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes("sk-proj-"), "no plaintext credential in the export");
  const wrapped = database
    .prepare("SELECT wrapped_key_json FROM user_data_keys WHERE user_id=?")
    .get(alice.user_id);
  assert.ok(!serialized.includes(wrapped.wrapped_key_json), "no wrapped key in the export");
  assert.equal(result.manifest.excluded.user_data_keys, "wrapped_key_material_is_never_exported");
});

test("AC-029 an export manifest cannot name another user's object", () => {
  const alice = stubUserId("1");
  const bob = stubUserId("2");
  const bobKey = userObjectKey({ userId: bob, category: "export", objectId: "o1", version: 1 });
  assert.throws(
    () => buildUserExportManifest({ userId: alice, generatedAt: NOW, objectRefs: [bobKey] }),
    (error) => error.code === "OBJECT_KEY_SCOPE_VIOLATION",
  );
  const ownKey = userObjectKey({ userId: alice, category: "export", objectId: "o1", version: 1 });
  const manifest = buildUserExportManifest({
    userId: alice,
    generatedAt: NOW,
    objectRefs: [ownKey],
  });
  assert.equal(manifest.objectRefs.length, 1);
  assert.match(manifest.manifestSha256, /^[0-9a-f]{64}$/);
});

test("AC-029 an export receipt is scoped and recorded", (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const bob = activate("sender-bob");
  const exporter = new SqliteUserExporter({ database, now: () => NOW });
  const result = exporter.export({ userId: alice.user_id });
  const receipt = exporter.recordReceipt({ userId: alice.user_id, manifest: result.manifest });
  assert.match(receipt.exportId, /^exp_[0-9a-f]{32}$/);
  assert.throws(
    () => exporter.recordReceipt({ userId: bob.user_id, manifest: result.manifest }),
    (error) => error.code === "EXPORT_MANIFEST_SCOPE_VIOLATION",
  );
  const stored = database
    .prepare("SELECT user_id, manifest_sha256 FROM export_receipts WHERE export_id=?")
    .get(receipt.exportId);
  assert.equal(stored.user_id, alice.user_id);
  assert.equal(stored.manifest_sha256, result.manifest.manifestSha256);
});

test("AC-029 the deletion order is frozen and access is cut before data is touched", () => {
  assert.deepEqual(ORDER, [
    "suspend_user",
    "revoke_web_sessions",
    "revoke_provider_credentials",
    "cancel_pending_jobs",
    "delete_r2_user_objects",
    "delete_search_and_profile_projections",
    "write_private_database_tombstone",
    "destroy_user_data_key",
    "mark_user_deleted",
  ]);
  assert.ok(ORDER.indexOf("suspend_user") < ORDER.indexOf("delete_r2_user_objects"));
  assert.ok(ORDER.indexOf("write_private_database_tombstone") < ORDER.indexOf("destroy_user_data_key"));
  assert.ok(ORDER.indexOf("destroy_user_data_key") < ORDER.indexOf("mark_user_deleted"));
  assert.deepEqual(IRREVERSIBLE_ACTIONS, ["delete_r2_user_objects", "destroy_user_data_key"]);

  const plan = buildDeletionPlan({ userId: stubUserId("1"), requestId: "req-00000001" });
  assert.equal(plan.length, ORDER.length);
  assert.deepEqual(plan[0].dependsOn, []);
  assert.deepEqual(plan[1].dependsOn, [plan[0].id]);
  assert.ok(plan.every((step) => step.idempotencyKey.startsWith(stubUserId("1"))));
});

test("AC-029 deletion runs every step once and is idempotent on re-run", async (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const store = new SqliteDeletionReceiptStore({ database, now: () => NOW });
  const calls = [];
  const handlers = Object.fromEntries(
    ORDER.map((action) => [action, async () => { calls.push(action); return { action }; }]),
  );

  const first = await executeDeletion({
    userId: alice.user_id,
    requestId: "req-00000001",
    receiptStore: store,
    handlers,
    now: () => NOW,
  });
  assert.equal(first.ok, true);
  assert.deepEqual(calls, [...ORDER]);
  assert.equal(first.receipts.length, ORDER.length);

  const second = await executeDeletion({
    userId: alice.user_id,
    requestId: "req-00000001",
    receiptStore: store,
    handlers,
    now: () => NOW,
  });
  assert.equal(second.ok, true);
  assert.deepEqual(calls, [...ORDER], "a completed request re-runs no handler");
});

test("AC-029 an interrupted deletion resumes without repeating the crypto-shred", async (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const store = new SqliteDeletionReceiptStore({ database, now: () => NOW });
  const calls = [];
  const failAfterShred = Object.fromEntries(
    ORDER.map((action) => [
      action,
      async () => {
        calls.push(action);
        if (action === "mark_user_deleted" && calls.filter((c) => c === action).length === 1) {
          throw new Error("PROCESS_KILLED");
        }
        return { action };
      },
    ]),
  );

  await assert.rejects(
    executeDeletion({
      userId: alice.user_id,
      requestId: "req-00000002",
      receiptStore: store,
      handlers: failAfterShred,
      now: () => NOW,
    }),
    /PROCESS_KILLED/,
  );
  assert.equal(calls.filter((c) => c === "destroy_user_data_key").length, 1);

  const plan = buildDeletionPlan({ userId: alice.user_id, requestId: "req-00000002" });
  const partial = store.listForRequest({ userId: alice.user_id, requestId: "req-00000002" });
  const point = resumePoint(plan, partial);
  assert.equal(point.complete, false);
  assert.equal(point.nextAction, "mark_user_deleted");
  assert.equal(point.pastIrreversible, true, "the resume knows the shred already happened");

  const resumed = await executeDeletion({
    userId: alice.user_id,
    requestId: "req-00000002",
    receiptStore: store,
    handlers: failAfterShred,
    now: () => NOW,
  });
  assert.equal(resumed.ok, true);
  assert.equal(
    calls.filter((c) => c === "destroy_user_data_key").length,
    1,
    "the crypto-shred ran exactly once across both attempts",
  );
  assert.equal(resumePoint(plan, resumed.receipts).complete, true);
});

test("AC-029 a deletion receipt cannot be rewritten or removed", async (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const store = new SqliteDeletionReceiptStore({ database, now: () => NOW });
  const plan = buildDeletionPlan({ userId: alice.user_id, requestId: "req-00000003" });
  store.put({
    userId: alice.user_id,
    requestId: "req-00000003",
    step: plan[0],
    status: "succeeded",
    resultSha256: "0".repeat(64),
  });
  assert.throws(
    () =>
      database
        .prepare("UPDATE deletion_receipts SET status='failed' WHERE step_id=?")
        .run(plan[0].id),
    /deletion_receipt_immutable/,
  );
  assert.throws(
    () => database.prepare("DELETE FROM deletion_receipts WHERE step_id=?").run(plan[0].id),
    /deletion_receipt_immutable/,
  );
});

test("AC-029 one user's receipt never satisfies another user's step", async (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const bob = activate("sender-bob");
  const store = new SqliteDeletionReceiptStore({ database, now: () => NOW });
  const alicePlan = buildDeletionPlan({ userId: alice.user_id, requestId: "req-00000004" });
  store.put({
    userId: alice.user_id,
    requestId: "req-00000004",
    step: alicePlan[0],
    status: "succeeded",
    resultSha256: "0".repeat(64),
  });
  const bobPlan = buildDeletionPlan({ userId: bob.user_id, requestId: "req-00000004" });
  assert.equal(
    store.get({ userId: bob.user_id, idempotencyKey: bobPlan[0].idempotencyKey }),
    null,
  );
  assert.notEqual(alicePlan[0].idempotencyKey, bobPlan[0].idempotencyKey);
});

test("AC-029 destroying the wrapped DEK makes residual ciphertext unrecoverable", (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const vault = new SqliteCredentialVault({ database, masterKey: MASTER_KEY });
  const apiKey = "sk-proj-abcdefghijklmnopqrstuvwxyz012345";
  vault.putCredential({ userId: alice.user_id, providerId: "openai", apiKey });
  assert.equal(vault.getCredential({ userId: alice.user_id, providerId: "openai" }), apiKey);

  const ciphertextBefore = database
    .prepare("SELECT ciphertext_json FROM provider_credentials WHERE user_id=? AND provider_id=?")
    .get(alice.user_id, "openai");
  assert.ok(ciphertextBefore, "ciphertext exists before the shred");

  const shred = vault.cryptoShred(alice.user_id);
  assert.equal(shred.destroyed, true);

  // The ciphertext may still sit on disk; what matters is that no key path
  // can turn it back into the credential.
  assert.throws(
    () => vault.getCredential({ userId: alice.user_id, providerId: "openai" }),
    CredentialVaultError,
  );
  assert.throws(() => vault.ensureUserKey(alice.user_id), (error) =>
    error.code === "USER_KEY_DESTROYED");
  const keyRow = database
    .prepare("SELECT wrapped_key_json, status FROM user_data_keys WHERE user_id=?")
    .get(alice.user_id);
  assert.equal(keyRow.status, "destroyed");
  assert.equal(keyRow.wrapped_key_json, '{"destroyed":true}');
});

test("AC-029 the tombstone proves the deletion without describing the user", (t) => {
  const { database, activate } = harness(t);
  const alice = activate("sender-alice");
  const receipts = ORDER.map((action) => ({ action }));
  const tombstone = buildDeletionTombstone({
    userId: alice.user_id,
    requestId: "req-00000005",
    occurredAt: NOW,
    receipts,
  });
  const serialized = JSON.stringify(tombstone);
  assert.ok(!serialized.includes(alice.user_id), "the raw user id is not in the tombstone");
  assert.equal(tombstone.crypto_shred_completed, true);
  assert.match(tombstone.tombstone_sha256, /^[0-9a-f]{64}$/);

  const tombstoneId = writeTombstone({
    database,
    userId: alice.user_id,
    phase: "completed",
    objectHash: tombstone.tombstone_sha256,
    occurredAt: NOW,
  });
  const stored = database
    .prepare("SELECT user_id, phase, object_hash FROM deletion_tombstones WHERE tombstone_id=?")
    .get(tombstoneId);
  assert.equal(stored.phase, "completed");
  assert.equal(stored.object_hash, tombstone.tombstone_sha256);
});

test("AC-029 the deletion of a user is a critical canonical fact", () => {
  const fact = buildUserFact({
    userId: stubUserId("1"),
    type: "user.deleted",
    occurredAt: NOW,
    payload: { crypto_shred_completed: true, steps: 9 },
    sourceEventId: "req-00000005",
  });
  assert.equal(fact.sync_priority, "immediate");
  const plan = planCanonicalSync([fact], {
    now: NOW,
    lastDailySyncAt: "2026-07-28T08:59:00.000Z",
  });
  assert.equal(plan.create_commit, true);
  assert.equal(plan.reason, "critical_event");
});

test("AC-029 lifecycle entry points refuse a malformed or missing scope", () => {
  for (const bad of [null, undefined, "", "usr_short", "not-a-user", 42]) {
    assert.throws(
      () => buildUserExportManifest({ userId: bad, generatedAt: NOW }),
      LifecycleError,
      `userId ${JSON.stringify(bad)} must be refused`,
    );
  }
  assert.throws(
    () => buildDeletionPlan({ userId: stubUserId("1"), requestId: "short" }),
    (error) => error.code === "DELETION_REQUEST_ID_INVALID",
  );
});

test("AC-030 the envelope refuses a payload that is too deep or too wide", () => {
  const userId = stubUserId("1");
  let deep = { value: 1 };
  for (let index = 0; index < 8; index += 1) {
    deep = { nested: deep };
  }
  assert.throws(
    () =>
      buildUserFact({ userId, type: "note.created", occurredAt: NOW, payload: deep, sourceEventId: "e" }),
    (error) => error.code === "CANONICAL_PAYLOAD_TOO_DEEP",
  );
  const wide = Object.fromEntries(
    Array.from({ length: 65 }, (_, index) => [`field_${index}`, index]),
  );
  assert.throws(
    () =>
      buildUserFact({ userId, type: "note.created", occurredAt: NOW, payload: wide, sourceEventId: "e" }),
    (error) => error.code === "CANONICAL_PAYLOAD_TOO_WIDE",
  );
  assert.throws(
    () =>
      buildUserFact({
        userId,
        type: "note.created",
        occurredAt: NOW,
        payload: { note: "x".repeat(2_049) },
        sourceEventId: "e",
      }),
    (error) => error.code === "CANONICAL_PAYLOAD_STRING_TOO_LONG",
  );
});

test("AC-030 an envelope error names the field path and never the value", () => {
  try {
    buildUserFact({
      userId: stubUserId("1"),
      type: "note.created",
      occurredAt: NOW,
      payload: { outer: { token: "sk-proj-abcdefghijklmnopqrstuvwxyz012345" } },
      sourceEventId: "evt",
    });
    assert.fail("expected a refusal");
  } catch (error) {
    assert.ok(error instanceof CanonicalEnvelopeError);
    assert.equal(error.detail, "payload.outer.token");
    assert.ok(!error.message.includes("sk-proj-"));
    assert.ok(!String(error.detail).includes("sk-proj-"));
  }
});
