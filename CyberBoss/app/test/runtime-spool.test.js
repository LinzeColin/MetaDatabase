"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");
const {
  isMainThread,
  parentPort,
  Worker,
  workerData,
} = require("node:worker_threads");

const {
  IntegrityConflictError,
  PayloadRedactedError,
  RuntimeSpoolDatabase,
} = require("../src/services/db/database-adapter");

const FIXTURE_KEY = Buffer.from(
  "8f4cb5db5aa765f11f782f87371dba5f9fde8cbe0f20d08c96f2ea2a9d58e8f2",
  "hex",
);
const MIGRATION_ROOT = path.resolve(__dirname, "../migrations");
const ADAPTER_PATH = path.resolve(
  __dirname,
  "../src/services/db/database-adapter.js",
);

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb200-spool-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function openSpool(databasePath, options = {}) {
  return new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: Buffer.from(FIXTURE_KEY),
    ...options,
  });
}

function fixture(index, overrides = {}) {
  return {
    source: "weixin",
    sourceAccountRef: "fixture-account",
    sourceMessageId: `fixture-message-${index}`,
    userRef: "fixture-user",
    messageType: "text",
    payload: `fixture-payload-${index}`,
    ...overrides,
  };
}

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function duplicateWorker(databasePath) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(__filename, {
      workerData: {
        mode: "duplicate",
        databasePath,
        keyHex: FIXTURE_KEY.toString("hex"),
      },
    });
    worker.once("message", resolve);
    worker.once("error", reject);
    worker.once("exit", (code) => {
      if (code !== 0) {
        reject(new Error(`duplicate_worker_exit:${code}`));
      }
    });
  });
}

if (!isMainThread && workerData?.mode === "duplicate") {
  try {
    const database = new RuntimeSpoolDatabase({
      databasePath: workerData.databasePath,
      encryptionKey: Buffer.from(workerData.keyHex, "hex"),
    });
    const result = database.acceptInbound(fixture("concurrent"));
    database.close();
    parentPort.postMessage({
      duplicate: result.duplicate,
      inboxId: result.inboxId,
      jobId: result.jobId,
    });
  } catch (error) {
    parentPort.postMessage({
      errorCode: error?.code || error?.name || "unknown",
    });
    process.exitCode = 1;
  }
} else {
  test("clean and existing-v1 migration are additive and legacy-readable", (t) => {
    const directory = temporaryDirectory(t);
    const cleanPath = path.join(directory, "clean.db");
    const clean = openSpool(cleanPath);
    assert.deepEqual(
      clean.migrationRecords().map((row) => row.version),
      [1, 2, 3, 4],
    );
    assert.deepEqual(clean.pragmaStatus(), {
      journalMode: "wal",
      synchronous: "full",
      foreignKeys: true,
      busyTimeoutMs: 5000,
      integrityCheck: "ok",
    });
    const schema = clean.schemaSql();
    for (const marker of [
      "CREATE TABLE inbox_messages",
      "CREATE TABLE jobs",
      "CREATE TABLE job_events",
      "CREATE TABLE outbox_messages",
      "CREATE TABLE sync_spool",
      "CREATE TABLE service_state",
      "CREATE TABLE job_state_transitions",
      "CREATE TRIGGER jobs_status_transition_guard",
      "CREATE TRIGGER job_events_immutable_update_guard",
      "CREATE UNIQUE INDEX idx_jobs_single_active_runtime",
      "CREATE TRIGGER jobs_scheduler_runtime_lease_guard",
      "CREATE TABLE outbox_attempt_events",
      "CREATE TRIGGER outbox_confirmation_truth_guard",
    ]) {
      assert.match(schema, new RegExp(marker));
    }
    clean.close();

    const v1Path = path.join(directory, "existing-v1.db");
    const v1 = new DatabaseSync(v1Path);
    v1.exec(
      fs.readFileSync(path.join(MIGRATION_ROOT, "001_runtime_spool.sql"), "utf8"),
    );
    v1.exec(`
      INSERT INTO inbox_messages(
        id, source, source_account_hash, source_message_id, correlation_id,
        user_ref_hash, message_type, payload_ciphertext, payload_sha256,
        status, received_at, durable_at
      ) VALUES (
        'legacy-inbox', 'weixin', 'legacy-account', 'legacy-message',
        'legacy-correlation', 'legacy-user', 'text', X'01',
        '${"a".repeat(64)}', 'accepted',
        '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z'
      );
      INSERT INTO jobs(
        id, correlation_id, inbox_id, workspace_alias, runtime,
        operation_class, status, input_sha256, created_at, updated_at
      ) VALUES (
        'legacy-job', 'legacy-correlation', 'legacy-inbox', 'legacy',
        'codex', 'read_only', 'queued', '${"b".repeat(64)}',
        '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z'
      );
      INSERT INTO outbox_messages(
        id, job_id, correlation_id, target_type, target_ref_ciphertext,
        dedupe_key, message_kind, payload_ciphertext, payload_sha256,
        status, created_at, updated_at
      ) VALUES (
        'legacy-outbox', 'legacy-job', 'legacy-correlation', 'weixin', X'01',
        'legacy-result-1', 'result', X'01', '${"c".repeat(64)}',
        'pending', '2026-01-01T00:00:00.000Z',
        '2026-01-01T00:00:00.000Z'
      );
    `);
    v1.close();
    const upgraded = openSpool(v1Path);
    assert.deepEqual(
      upgraded.migrationRecords().map((row) => row.version),
      [1, 2, 3, 4],
    );
    const legacyOutbox = upgraded.getOutbox("legacy-outbox");
    assert.equal(
      legacyOutbox.logical_message_sha256,
      hash(
        Buffer.from(
          "legacy-job\u0000result\u0000legacy-result-1",
          "utf8",
        ),
      ),
    );
    assert.equal(
      legacyOutbox.provider_client_id,
      `cb-outbox-${hash(Buffer.from("legacy-result-1", "utf8")).slice(0, 32)}`,
    );
    const legacyClaim = upgraded.claimNextOutbox({
      ownerId: "legacy-upgrade-test",
      leaseMs: 1000,
    });
    assert.equal(legacyClaim.claimed, true);
    assert.equal(legacyClaim.row.id, "legacy-outbox");
    upgraded.close();

    const legacyReader = new DatabaseSync(v1Path, { readOnly: true });
    assert.doesNotThrow(() =>
      legacyReader
        .prepare(
          `SELECT version, applied_at, source_commit
           FROM schema_migrations ORDER BY version`,
        )
        .all(),
    );
    for (const query of [
      "SELECT id, source, source_message_id, correlation_id FROM inbox_messages",
      "SELECT id, correlation_id, status, state_version FROM jobs",
      "SELECT id, job_id, event_type FROM job_events",
      "SELECT id, job_id, dedupe_key, status FROM outbox_messages",
    ]) {
      assert.doesNotThrow(() => legacyReader.prepare(query).all());
    }
    legacyReader.close();

    const migration2 = fs.readFileSync(
      path.join(MIGRATION_ROOT, "002_cb200_retention_and_transitions.sql"),
      "utf8",
    );
    assert.doesNotMatch(migration2, /\b(?:DROP|RENAME|VACUUM)\b/i);
    assert.match(migration2, /ALTER TABLE .* ADD COLUMN/);
    const migration3 = fs.readFileSync(
      path.join(MIGRATION_ROOT, "003_cb220_scheduler_control.sql"),
      "utf8",
    );
    assert.doesNotMatch(migration3, /\b(?:DROP|RENAME|VACUUM)\b/i);
    assert.match(migration3, /ALTER TABLE jobs ADD COLUMN/);
    const migration4 = fs.readFileSync(
      path.join(MIGRATION_ROOT, "004_cb230_durable_outbox.sql"),
      "utf8",
    );
    assert.doesNotMatch(migration4, /\b(?:DROP|RENAME|VACUUM)\b/i);
    assert.match(migration4, /ALTER TABLE outbox_messages ADD COLUMN/);
  });

  test("10,000 durable fixtures have stable collision-free source, correlation and job IDs", { timeout: 60000 }, (t) => {
    const directory = temporaryDirectory(t);
    const databasePath = path.join(directory, "fixtures.db");
    const database = openSpool(databasePath);
    const sourceIds = new Set();
    const correlationIds = new Set();
    const jobIds = new Set();
    for (let index = 0; index < 10000; index += 1) {
      const input = fixture(index);
      const derivedBefore = database.deriveIds(input);
      const accepted = database.acceptInbound(input);
      const derivedAfter = database.deriveIds(input);
      assert.deepEqual(derivedAfter, derivedBefore);
      assert.equal(accepted.sourceMessageId, derivedBefore.sourceMessageId);
      assert.equal(accepted.correlationId, derivedBefore.correlationId);
      assert.equal(accepted.jobId, derivedBefore.jobId);
      assert.ok(accepted.sourceMessageId);
      assert.ok(accepted.correlationId);
      assert.ok(accepted.jobId);
      sourceIds.add(accepted.sourceMessageId);
      correlationIds.add(accepted.correlationId);
      jobIds.add(accepted.jobId);
    }
    assert.equal(sourceIds.size, 10000);
    assert.equal(correlationIds.size, 10000);
    assert.equal(jobIds.size, 10000);
    assert.deepEqual(database.counts(), {
      inbox_messages: 10000,
      jobs: 10000,
      job_events: 20000,
      outbox_messages: 0,
      sync_spool: 0,
      service_state: 0,
    });
    const replay = database.acceptInbound(fixture(9999));
    assert.equal(replay.duplicate, true);
    assert.throws(
      () =>
        database.acceptInbound(
          fixture(9999, { payload: "different-fixture-payload" }),
        ),
      (error) =>
        error instanceof IntegrityConflictError &&
        error.code === "INTEGRITY_CONFLICT" &&
        !error.message.includes("different-fixture-payload"),
    );
    database.close();

    const query = new DatabaseSync(databasePath, { readOnly: true });
    const distinct = query
      .prepare(
        `SELECT
           COUNT(*) AS inbox_count,
           COUNT(DISTINCT source_message_id) AS source_id_count,
           COUNT(DISTINCT correlation_id) AS correlation_id_count
         FROM inbox_messages`,
      )
      .get();
    const distinctJobs = query
      .prepare("SELECT COUNT(DISTINCT id) AS job_id_count FROM jobs")
      .get();
    query.close();
    assert.deepEqual(
      {
        inbox_count: Number(distinct.inbox_count),
        source_id_count: Number(distinct.source_id_count),
        correlation_id_count: Number(distinct.correlation_id_count),
        job_id_count: Number(distinctJobs.job_id_count),
      },
      {
        inbox_count: 10000,
        source_id_count: 10000,
        correlation_id_count: 10000,
        job_id_count: 10000,
      },
    );
  });

  test("32 concurrent duplicate inserters create one inbox and one executable job", { timeout: 60000 }, async (t) => {
    const directory = temporaryDirectory(t);
    const databasePath = path.join(directory, "concurrent.db");
    const bootstrap = openSpool(databasePath);
    bootstrap.close();

    const results = await Promise.all(
      Array.from({ length: 32 }, () => duplicateWorker(databasePath)),
    );
    assert.equal(results.filter((row) => row.errorCode).length, 0);
    assert.equal(results.filter((row) => row.duplicate === false).length, 1);
    assert.equal(results.filter((row) => row.duplicate === true).length, 31);
    assert.equal(new Set(results.map((row) => row.inboxId)).size, 1);
    assert.equal(new Set(results.map((row) => row.jobId)).size, 1);

    const database = openSpool(databasePath);
    assert.deepEqual(database.counts(), {
      inbox_messages: 1,
      jobs: 1,
      job_events: 2,
      outbox_messages: 0,
      sync_spool: 0,
      service_state: 0,
    });
    assert.equal(database.pragmaStatus().integrityCheck, "ok");
    database.close();
  });

  test("service and DB guards reject illegal or stale transitions and preserve immutable events", (t) => {
    const directory = temporaryDirectory(t);
    const databasePath = path.join(directory, "transitions.db");
    const database = openSpool(databasePath);
    const accepted = database.acceptInbound(fixture("transition"));
    assert.equal(accepted.status, "queued");
    assert.throws(
      () =>
        database.transitionJob(accepted.jobId, "succeeded", {
          expectedVersion: 2,
        }),
      { code: "ILLEGAL_JOB_TRANSITION" },
    );
    const running = database.transitionJob(accepted.jobId, "running", {
      expectedVersion: 2,
      metadata: { transition_code: "worker_claimed" },
    });
    assert.equal(running.status, "running");
    assert.equal(Number(running.state_version), 3);
    assert.throws(
      () =>
        database.transitionJob(accepted.jobId, "succeeded", {
          expectedVersion: 2,
        }),
      { code: "STATE_VERSION_CONFLICT" },
    );
    const succeeded = database.transitionJob(accepted.jobId, "succeeded", {
      expectedVersion: 3,
      metadata: { result_code: "ok" },
    });
    assert.equal(succeeded.status, "succeeded");
    assert.equal(database.listJobEvents(accepted.jobId).length, 4);
    const metadataGuard = database.acceptInbound(fixture("metadata-guard"));
    assert.throws(
      () =>
        database.transitionJob(metadataGuard.jobId, "running", {
          expectedVersion: 2,
          metadata: { token: "must_not_persist" },
        }),
      { code: "REDACTED_METADATA_KEY_INVALID" },
    );
    assert.equal(database.getJob(metadataGuard.jobId).status, "queued");
    database.close();

    const bypass = new DatabaseSync(databasePath);
    bypass.exec("PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;");
    assert.throws(
      () =>
        bypass
          .prepare("UPDATE jobs SET status='running' WHERE id=?")
          .run(accepted.jobId),
      /illegal_job_status_transition/,
    );
    const event = bypass.prepare("SELECT id FROM job_events LIMIT 1").get();
    assert.throws(
      () =>
        bypass
          .prepare(
            "UPDATE job_events SET payload_redacted_json='{\"tampered\":true}' WHERE id=?",
          )
          .run(event.id),
      /immutable_job_event/,
    );
    assert.throws(
      () => bypass.prepare("DELETE FROM job_events WHERE id=?").run(event.id),
      /immutable_job_event/,
    );
    assert.equal(
      bypass.prepare("PRAGMA integrity_check").get().integrity_check,
      "ok",
    );
    bypass.close();
  });

  test("transaction cut points preserve inbox RPO 0 without uncommitted fragments", { timeout: 60000 }, (t) => {
    const directory = temporaryDirectory(t);
    const cutPoints = [
      "after_begin",
      "after_inbox_insert",
      "after_job_insert",
      "after_event_insert",
      "after_commit",
    ];
    for (const cutPoint of cutPoints) {
      const databasePath = path.join(directory, `${cutPoint}.db`);
      const script = `
        const { RuntimeSpoolDatabase } = require(${JSON.stringify(ADAPTER_PATH)});
        const database = new RuntimeSpoolDatabase({
          databasePath: process.env.CB_DB,
          encryptionKey: Buffer.from(process.env.CB_KEY, "hex"),
          faultInjector(point) {
            if (point === process.env.CB_CUT) process.exit(91);
          },
        });
        database.acceptInbound({
          source: "weixin",
          sourceAccountRef: "crash-account",
          sourceMessageId: "crash-message",
          userRef: "crash-user",
          payload: "crash-fixture-payload",
        });
      `;
      const child = spawnSync(process.execPath, ["-e", script], {
        env: {
          ...process.env,
          CB_DB: databasePath,
          CB_KEY: FIXTURE_KEY.toString("hex"),
          CB_CUT: cutPoint,
        },
        encoding: "utf8",
        timeout: 15000,
      });
      assert.equal(child.status, 91, `${cutPoint}:${child.stderr}`);
      const recovered = openSpool(databasePath);
      const expected = cutPoint === "after_commit" ? 1 : 0;
      const counts = recovered.counts();
      assert.equal(counts.inbox_messages, expected, cutPoint);
      assert.equal(counts.jobs, expected, cutPoint);
      assert.equal(counts.job_events, expected * 2, cutPoint);
      assert.equal(recovered.pragmaStatus().integrityCheck, "ok", cutPoint);
      recovered.close();
    }
  });

  test("AES-256-GCM, TTL redaction and mock canonical recovery leave no plaintext", (t) => {
    const directory = temporaryDirectory(t);
    const databasePath = path.join(directory, "privacy.db");
    let clock = new Date("2026-07-27T00:00:00.000Z");
    const database = openSpool(databasePath, {
      now: () => clock,
      payloadTtlMs: 1000,
    });
    const secrets = {
      payload: "CB200-PLAINTEXT-PAYLOAD-7c2715",
      context: "CB200-PLAINTEXT-CONTEXT-0dd2d1",
      target: "CB200-PLAINTEXT-TARGET-87f893",
      reply: "CB200-PLAINTEXT-REPLY-8f098a",
    };
    const accepted = database.acceptInbound(
      fixture("privacy", {
        payload: secrets.payload,
        contextToken: secrets.context,
      }),
    );
    assert.equal(
      database.readInboundPayload(accepted.inboxId).toString("utf8"),
      secrets.payload,
    );
    database.enqueueOutbox({
      jobId: accepted.jobId,
      dedupeKey: "fixture-result-1",
      messageKind: "result",
      targetRef: secrets.target,
      payload: secrets.reply,
    });

    const canonicalIds = [];
    for (let index = 0; index < 100; index += 1) {
      const eventId = `fixture_event_${index}`;
      canonicalIds.push(eventId);
      database.enqueueSyncEvent({
        eventId,
        objectType: "job_event",
        objectId: `fixture_object_${index}`,
        canonicalPath: `Private-MetaDatabase/CyberBoss/events/${index}.json`,
        payloadRedacted: { event_code: "fixture", index },
      });
      database.markSyncRetry(eventId);
    }
    assert.equal(database.reconcileCanonicalEventIds([]).setDiff, 0);
    for (const eventId of canonicalIds) {
      database.markSyncSynced(eventId, hash(eventId));
    }
    assert.throws(
      () => database.markSyncSynced(canonicalIds[0], hash("different-object")),
      { code: "INTEGRITY_CONFLICT" },
    );
    assert.deepEqual(database.reconcileCanonicalEventIds(canonicalIds), {
      missingCanonical: [],
      missingLocal: [],
      setDiff: 0,
    });
    database.setServiceState("canonical_fixture", {
      state_code: "reconciled",
      event_count: 100,
    });

    clock = new Date("2026-07-27T00:00:02.000Z");
    assert.deepEqual(database.redactExpiredPayloads(), {
      inboxPayloads: 1,
      inboxContexts: 1,
      outboxPayloads: 1,
      outboxTargets: 1,
    });
    assert.throws(
      () => database.readInboundPayload(accepted.inboxId),
      (error) =>
        error instanceof PayloadRedactedError &&
        error.code === "PAYLOAD_REDACTED" &&
        !Object.values(secrets).some((secret) => error.message.includes(secret)),
    );
    assert.equal(database.pragmaStatus().integrityCheck, "ok");
    const forbidden = [
      ...Object.values(secrets).map((value) => Buffer.from(value, "utf8")),
      Buffer.from(FIXTURE_KEY),
      Buffer.from(FIXTURE_KEY.toString("hex"), "utf8"),
    ];
    for (const suffix of ["", "-wal", "-shm"]) {
      const candidate = `${databasePath}${suffix}`;
      assert.equal(fs.existsSync(candidate), true, `${suffix || "db"} missing`);
      const bytes = fs.readFileSync(candidate);
      for (const value of forbidden) {
        assert.equal(
          bytes.includes(value),
          false,
          `${path.basename(candidate)} contains forbidden bytes`,
        );
      }
      assert.equal(fs.statSync(candidate).mode & 0o777, 0o600);
    }
    database.close();

    for (const suffix of ["", "-wal", "-shm"]) {
      const candidate = `${databasePath}${suffix}`;
      if (!fs.existsSync(candidate)) {
        continue;
      }
      const bytes = fs.readFileSync(candidate);
      for (const value of forbidden) {
        assert.equal(
          bytes.includes(value),
          false,
          `${path.basename(candidate)} contains forbidden bytes`,
        );
      }
      assert.equal(fs.statSync(candidate).mode & 0o777, 0o600);
    }
  });
}
