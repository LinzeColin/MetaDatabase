"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const {
  MIGRATIONS,
  RuntimeSpoolDatabase,
  RuntimeSpoolError,
  USER_SCOPED_LEGACY_TABLES,
  deriveOwnerUserId,
} = require("../src/services/db/database-adapter");
const {
  UserIdentityError,
  deriveUserIdentity,
  matchesDerivedIdentity,
} = require("../src/services/users/user-identity");
const {
  SqliteUserRepository,
  UserRepositoryError,
} = require("../src/services/users/user-repository");
const {
  InviteCodeError,
  MIN_CODE_LENGTH,
  SqliteInviteCodeStore,
  generateCode,
  hashCode,
  normalizeCode,
} = require("../src/services/users/invite-code-store");

const KEY = Buffer.alloc(32, 7);
const IDENTITY_KEY = Buffer.alloc(32, 9);
const INVITE_SECRET = Buffer.alloc(32, 11);

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb610-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function openSpool(databasePath, options = {}) {
  return new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: KEY,
    identityKey: IDENTITY_KEY,
    ...options,
  });
}

function inbound(overrides = {}) {
  return {
    source: "weixin",
    sourceAccountRef: "bot-account-1",
    sourceMessageId: "msg-1",
    userRef: "sender-a",
    payload: { text: "hello" },
    ...overrides,
  };
}

test("migration 006 is additive, dynamically numbered and registered", (t) => {
  const directory = temporaryDirectory(t);
  const spool = openSpool(path.join(directory, "runtime.db"));
  t.after(() => spool.close());

  const versions = spool.migrationRecords().map((row) => Number(row.version));
  assert.deepEqual(versions, [1, 2, 3, 4, 5, 6, 7, 8, 9]);
  // Addressed by version rather than by position: CB-800 appends migration 7,
  // and this node's claim is that 006 is registered, not that it stays last.
  const migration006 = MIGRATIONS.find((migration) => migration.version === 6);
  assert.equal(migration006.name, "006_multiuser_foundation.sql");
  assert.equal(migration006.sourceCommit, "CB-610");

  const source = fs.readFileSync(
    path.join(__dirname, "../migrations/006_multiuser_foundation.sql"),
    "utf8",
  );
  assert.doesNotMatch(source, /\b(?:DROP|RENAME|VACUUM|DELETE FROM)\b/i);
  assert.match(source, /BEGIN IMMEDIATE;/);
  assert.match(source, /PRAGMA integrity_check;/);

  const schema = spool.schemaSql();
  for (const table of [
    "users",
    "user_channels",
    "invite_codes",
    "user_settings",
    "setup_tokens",
    "web_sessions",
    "user_data_keys",
    "provider_credentials",
    "imports",
    "profile_facts",
    "activity_daily",
    "consent_events",
    "deletion_tombstones",
    "model_budget_settings",
    "model_token_usage_daily",
    "model_budget_reservations",
    "provider_circuits",
  ]) {
    assert.ok(
      schema.includes(`CREATE TABLE ${table}`),
      `missing table ${table}`,
    );
  }
  assert.equal(spool.pragmaStatus().integrityCheck, "ok");
  assert.equal(spool.pragmaStatus().foreignKeys, true);
});

test("re-opening the database is idempotent and never re-applies migration 006", (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "runtime.db");

  const first = openSpool(databasePath);
  first.acceptInbound(inbound());
  const ownerUserId = first.ownerUserId;
  const firstRecords = first.migrationRecords();
  first.close();

  const second = openSpool(databasePath);
  t.after(() => second.close());
  assert.equal(second.ownerUserId, ownerUserId);
  assert.deepEqual(
    second.migrationRecords().map((row) => Number(row.version)),
    firstRecords.map((row) => Number(row.version)),
  );
  const users = new DatabaseSync(databasePath, { readOnly: true });
  t.after(() => users.close());
  assert.equal(
    Number(users.prepare("SELECT COUNT(*) AS c FROM users").get().c),
    1,
  );
});

test("legacy rows are backfilled to Owner and no unscoped row survives", (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "legacy.db");

  // Build a genuine pre-v8 database by applying only migrations 1-5, exactly
  // as an accepted Stage 0-5 deployment would look, then insert rows that
  // predate user scope.
  const preV8 = new DatabaseSync(databasePath);
  const checksums = new Map(
    MIGRATIONS.map((migration) => [
      migration.version,
      require("node:crypto")
        .createHash("sha256")
        .update(
          fs.readFileSync(
            path.join(__dirname, "../migrations", migration.name),
          ),
        )
        .digest("hex"),
    ]),
  );
  for (const migration of MIGRATIONS.filter((row) => row.version <= 5)) {
    let source = fs.readFileSync(
      path.join(__dirname, "../migrations", migration.name),
      "utf8",
    );
    for (const [version, checksum] of checksums) {
      source = source.replaceAll(
        `__MIGRATION_${String(version).padStart(3, "0")}_CHECKSUM__`,
        checksum,
      );
    }
    preV8.exec(source);
  }
  assert.deepEqual(
    preV8
      .prepare("SELECT version FROM schema_migrations ORDER BY version")
      .all()
      .map((row) => Number(row.version)),
    [1, 2, 3, 4, 5],
  );
  preV8.exec(`
    INSERT INTO inbox_messages(
      id, source, source_account_hash, source_message_id, correlation_id,
      user_ref_hash, message_type, payload_sha256, status, received_at,
      durable_at
    ) VALUES (
      'legacy-inbox', 'weixin', 'acct_legacy', 'srcmsg_legacy',
      'corr_legacy', 'user_legacy', 'text', '${"a".repeat(64)}',
      'accepted', '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z'
    );
  `);
  preV8.exec(`
    INSERT INTO jobs(
      id, correlation_id, inbox_id, workspace_alias, runtime, operation_class,
      status, state_version, max_attempts, input_sha256, created_at, updated_at
    ) VALUES (
      'legacy-job', 'corr_legacy', 'legacy-inbox', 'cyberboss', 'codex',
      'read_only', 'received', 1, 1, '${"a".repeat(64)}',
      '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z'
    );
  `);
  preV8.close();

  const upgraded = openSpool(databasePath);
  t.after(() => upgraded.close());
  const ownerUserId = upgraded.ownerUserId;
  assert.deepEqual(
    upgraded.migrationRecords().map((row) => Number(row.version)),
    [1, 2, 3, 4, 5, 6, 7, 8, 9],
  );

  const reader = new DatabaseSync(databasePath, { readOnly: true });
  t.after(() => reader.close());
  for (const table of USER_SCOPED_LEGACY_TABLES) {
    const unscoped = reader
      .prepare(
        `SELECT COUNT(*) AS c FROM ${table}
         WHERE user_id IS NULL OR user_id=''`,
      )
      .get();
    assert.equal(Number(unscoped.c), 0, `${table} still has unscoped rows`);
    const foreign = reader
      .prepare(
        `SELECT COUNT(*) AS c FROM ${table}
         WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id=${table}.user_id)`,
      )
      .get();
    assert.equal(Number(foreign.c), 0, `${table} references an unknown user`);
  }
  assert.equal(
    reader
      .prepare("SELECT user_id FROM inbox_messages WHERE id='legacy-inbox'")
      .get().user_id,
    ownerUserId,
  );
  assert.equal(
    reader.prepare("SELECT role FROM users WHERE user_id=?").get(ownerUserId)
      .role,
    "owner",
  );
});

test("valid-user triggers reject unscoped and unknown-user writes", (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "guard.db");
  const spool = openSpool(databasePath);
  spool.acceptInbound(inbound());
  spool.close();

  const raw = new DatabaseSync(databasePath);
  t.after(() => raw.close());
  raw.exec("PRAGMA foreign_keys=ON");

  const insert = (rowId, userIdLiteral) => () =>
    raw.exec(`
      INSERT INTO inbox_messages(
        id, source, source_account_hash, source_message_id, correlation_id,
        user_ref_hash, message_type, payload_sha256, status, received_at,
        durable_at, user_id
      ) VALUES (
        '${rowId}', 'weixin', 'acct_${rowId}', 'srcmsg_${rowId}',
        'corr_${rowId}', 'user_g', 'text', '${"b".repeat(64)}', 'accepted',
        '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z', ${userIdLiteral}
      );
    `);

  assert.throws(insert("guard-null", "NULL"), /valid_user_id_required/);
  assert.throws(insert("guard-empty", "''"), /valid_user_id_required/);
  assert.throws(
    insert("guard-unknown", "'usr_not_a_real_user_000000'"),
    /valid_user_id_required/,
  );

  assert.throws(
    () =>
      raw.exec(
        "UPDATE jobs SET user_id='usr_not_a_real_user_000000' WHERE 1=1",
      ),
    /valid_user_id_required/,
  );
  assert.throws(
    () => raw.exec("DELETE FROM users WHERE role='owner'"),
    /user_has_scoped_rows/,
  );
});

test("sync_spool allows system scope but rejects an unknown user scope", (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "sync.db");
  const spool = openSpool(databasePath);
  spool.close();

  const raw = new DatabaseSync(databasePath);
  t.after(() => raw.close());
  const insert = (rowId, literal) =>
    `INSERT INTO sync_spool(
       id, event_id, object_type, object_id, canonical_path,
       payload_redacted_json, payload_sha256, status, created_at, updated_at,
       user_id
     ) VALUES (
       '${rowId}', 'evt-${rowId}', 'job_event', 'job-1', 'a/b.json', '{}',
       '${"c".repeat(64)}', 'pending', '2026-01-01T00:00:00.000Z',
       '2026-01-01T00:00:00.000Z', ${literal}
     );`;
  assert.doesNotThrow(
    () => raw.exec(insert("sync-system", "NULL")),
    "system-scope canonical events stay allowed",
  );
  assert.throws(
    () => raw.exec(insert("sync-unknown", "'usr_not_a_real_user_000000'")),
    /valid_user_id_required/,
  );
});

test("inbound and outbox rows carry the resolved user scope", (t) => {
  const directory = temporaryDirectory(t);
  const spool = openSpool(path.join(directory, "scope.db"));
  t.after(() => spool.close());

  const accepted = spool.acceptInbound(inbound());
  const job = spool.getJob(accepted.jobId);
  assert.equal(job.user_id, spool.ownerUserId);
  assert.equal(spool.getInbox(accepted.inboxId).user_id, spool.ownerUserId);

  const outbox = spool.enqueueOutbox({
    jobId: accepted.jobId,
    dedupeKey: "reply-1",
    messageKind: "result",
    targetRef: "sender-a",
    payload: { text: "ok" },
  });
  // The reply scope is inherited from the job, never supplied by the caller.
  assert.equal(outbox.user_id, job.user_id);

  assert.throws(
    () => spool.acceptInbound(inbound({ sourceMessageId: "msg-2", userId: "usr_" + "z".repeat(24) })),
    (error) => error instanceof RuntimeSpoolError && error.code === "USER_NOT_FOUND",
  );
  assert.throws(
    () => spool.acceptInbound(inbound({ sourceMessageId: "msg-3", userId: "not-a-user-id" })),
    (error) => error instanceof RuntimeSpoolError && error.code === "INVALID_USER_ID",
  );
});

test("one bot account resolves two senders to two isolated users", (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "twouser.db");
  const spool = openSpool(databasePath);
  t.after(() => spool.close());

  const raw = new DatabaseSync(databasePath);
  t.after(() => raw.close());
  const repository = new SqliteUserRepository({
    database: raw,
    identityKey: IDENTITY_KEY,
  });

  const a = repository.ensurePending({
    botAccountRef: "bot-account-1",
    senderRef: "sender-a",
  });
  const b = repository.ensurePending({
    botAccountRef: "bot-account-1",
    senderRef: "sender-b",
  });

  assert.notEqual(a.user_id, b.user_id);
  assert.equal(a.status, "pending_consent");
  assert.equal(b.status, "pending_consent");
  assert.equal(repository.mayCallModel(a.user_id), false);
  assert.equal(repository.mayCallModel(b.user_id), false);

  const resolvedA = repository.resolveByPrincipal({
    botAccountRef: "bot-account-1",
    senderRef: "sender-a",
  });
  assert.equal(resolvedA.user_id, a.user_id);
  assert.equal(
    repository.resolveByPrincipal({
      botAccountRef: "bot-account-2",
      senderRef: "sender-a",
    }),
    null,
    "the same sender on a different bot account is a different principal",
  );

  const activatedA = repository.activateConsent({
    userId: a.user_id,
    policyVersion: "consent-v1",
  });
  assert.equal(activatedA.status, "active");
  assert.equal(repository.mayCallModel(a.user_id), true);
  assert.equal(
    repository.mayCallModel(b.user_id),
    false,
    "consent by A must not activate B",
  );
  assert.throws(
    () =>
      repository.activateConsent({
        userId: a.user_id,
        policyVersion: "consent-v1",
      }),
    (error) =>
      error instanceof UserRepositoryError &&
      error.code === "CONSENT_STATE_INVALID",
  );

  repository.setStatus(a.user_id, "suspended");
  assert.equal(repository.mayCallModel(a.user_id), false);
  assert.equal(repository.isOwner(a.user_id), false);
  assert.equal(repository.isOwner(spool.ownerUserId), true);
  assert.equal(repository.countByRole("owner"), 1);
});

test("user identity is server-derived and ignores client claims", () => {
  const base = {
    identityKey: IDENTITY_KEY,
    channel: "weixin",
    botAccountRef: "bot-account-1",
    senderRef: "sender-a",
  };
  const identity = deriveUserIdentity(base);
  assert.deepEqual(identity, deriveUserIdentity(base));
  assert.notEqual(
    identity.userId,
    deriveUserIdentity({ ...base, senderRef: "sender-b" }).userId,
  );
  assert.notEqual(
    identity.userId,
    deriveUserIdentity({ ...base, botAccountRef: "bot-account-2" }).userId,
  );
  assert.notEqual(
    identity.userId,
    deriveUserIdentity({ ...base, identityKey: Buffer.alloc(32, 3) }).userId,
  );
  // Length-prefixing prevents ("a","bc") from colliding with ("ab","c").
  assert.notEqual(
    deriveUserIdentity({ ...base, botAccountRef: "a", senderRef: "bc" }).userId,
    deriveUserIdentity({ ...base, botAccountRef: "ab", senderRef: "c" }).userId,
  );

  assert.equal(matchesDerivedIdentity(identity.userId, identity.userId), true);
  assert.equal(
    matchesDerivedIdentity("usr_" + "q".repeat(24), identity.userId),
    false,
  );
  assert.equal(matchesDerivedIdentity("admin", identity.userId), false);
  assert.throws(
    () => deriveUserIdentity({ ...base, identityKey: Buffer.alloc(16) }),
    (error) => error instanceof UserIdentityError,
  );
  assert.throws(
    () => deriveUserIdentity({ ...base, channel: "telegram" }),
    (error) => error.code === "CHANNEL_NOT_SUPPORTED",
  );
  assert.match(deriveOwnerUserId(IDENTITY_KEY), /^usr_[A-Za-z0-9_-]{20,64}$/);
});

test("invite codes are keyed-hashed, bounded, expirable and revocable", (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "invite.db");
  const spool = openSpool(databasePath);
  t.after(() => spool.close());
  const raw = new DatabaseSync(databasePath);
  t.after(() => raw.close());

  let clock = 1_000_000;
  const store = new SqliteInviteCodeStore({
    database: raw,
    secret: INVITE_SECRET,
    now: () => clock,
  });

  const single = store.issue({ maxUses: 1, ttlMs: 60_000 });
  assert.ok(single.code.length >= MIN_CODE_LENGTH);
  assert.match(single.code, /^[A-Z0-9]{12}$/);
  assert.match(single.display, /^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/);

  // Only the keyed hash is stored; the plaintext must not appear anywhere.
  const stored = raw.prepare("SELECT code_hash FROM invite_codes").all();
  assert.equal(stored.length, 1);
  assert.equal(stored[0].code_hash, hashCode(INVITE_SECRET, single.code));
  assert.ok(!stored[0].code_hash.includes(single.code));
  assert.equal(store.matchesStoredHash(single.code, stored[0].code_hash), true);
  assert.equal(
    hashCode(INVITE_SECRET, single.code) ===
      hashCode(Buffer.alloc(32, 12), single.code),
    false,
    "a different secret must produce a different hash",
  );

  assert.equal(store.consume(single.code).consumed, true);
  assert.throws(
    () => store.consume(single.code),
    (error) => error instanceof InviteCodeError && error.code === "INVITE_INVALID",
  );

  const multi = store.issue({ maxUses: 2, ttlMs: 60_000 });
  assert.equal(store.consume(multi.code).remainingUses, 1);
  store.revoke(multi.code);
  assert.throws(() => store.consume(multi.code), /INVITE_INVALID/);
  assert.equal(store.remainingUses(multi.code), 0);

  const expiring = store.issue({ maxUses: 1, ttlMs: 1_000 });
  clock += 2_000;
  assert.throws(() => store.consume(expiring.code), /INVITE_INVALID/);

  assert.throws(() => store.issue({ maxUses: 0 }), /INVITE_MAX_USES_INVALID/);
  assert.throws(() => store.issue({ maxUses: 21 }), /INVITE_MAX_USES_INVALID/);
  assert.throws(() => store.consume("SHORT"), /INVITE_CODE_INVALID/);
  assert.throws(() => generateCode(8), /INVITE_CODE_LENGTH_INVALID/);
  assert.equal(normalizeCode(" ab-cd ef "), "ABCDEF");

  // The generated alphabet omits the visually ambiguous I, O, 0 and 1.
  for (let index = 0; index < 64; index += 1) {
    assert.doesNotMatch(generateCode(32), /[IO01]/);
  }
});
