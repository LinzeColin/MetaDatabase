"use strict";

const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  CanonicalDataWorker,
  CanonicalIntegrityError,
  CanonicalSpoolCoordinator,
  FilesystemPrivateDatabaseAdapter,
  decodeCanonicalBatch,
  encodeCanonicalBatch,
  eventSetSha256,
  mapJobEventToCanonical,
  rebuildCanonicalProjection,
  validateReceipt,
} = require("../src/services/canonical/canonical-sync");
const {
  RuntimeSpoolDatabase,
} = require("../src/services/db/database-adapter");

const FIXTURE_KEY = Buffer.from("71".repeat(32), "hex");
const RELEASE_COMMIT = "a".repeat(40);

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb240-sync-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function openDatabase(databasePath, now) {
  return new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: Buffer.from(FIXTURE_KEY),
    identityKey: Buffer.from(FIXTURE_KEY),
    now,
  });
}

function fixtureRow(index, overrides = {}) {
  const suffix = String(index).padStart(5, "0");
  return {
    event_id: `event_fixture_${suffix}`,
    job_id: `job_fixture_${suffix}`,
    correlation_id: `corr_fixture_${suffix}`,
    event_type: "job_transition",
    from_status: "reply_pending",
    to_status: "replied",
    occurred_at: "2026-07-27T00:00:00.000Z",
    recorded_at: "2026-07-27T00:00:00.000Z",
    workspace_alias: "cyberboss",
    runtime: "codex",
    input_sha256: hash(`input-${suffix}`),
    output_sha256: hash(`output-${suffix}`),
    job_status: "replied",
    ...overrides,
  };
}

function fixtureRecord(index, overrides = {}) {
  return mapJobEventToCanonical(fixtureRow(index, overrides), {
    deployedCommit: RELEASE_COMMIT,
  });
}

function createCoordinator(root, database, now, options = {}) {
  return new CanonicalSpoolCoordinator({
    database,
    outgoingDirectory: path.join(root, "spool", "outgoing"),
    receiptDirectory: path.join(root, "spool", "receipts"),
    quarantineDirectory: path.join(root, "spool", "quarantine"),
    deployedCommit: RELEASE_COMMIT,
    now,
    flushOnTerminal: true,
    ...options,
  });
}

function enqueueRecords(database, count, offset = 0) {
  const records = [];
  for (let index = 0; index < count; index += 1) {
    const record = fixtureRecord(index + offset);
    database.enqueueSyncEvent({
      eventId: record.event_id,
      objectType: "fixture_terminal_event",
      objectId: record.job_id,
      canonicalPath:
        `Private-MetaDatabase/CyberBoss/events/${record.event_id}.json`,
      payloadRedacted: record,
    });
    records.push(record);
  }
  return records;
}

test("canonical mapper emits only strict redacted stable fields", () => {
  const record = fixtureRecord(1);
  assert.equal(record.schema_version, 1);
  assert.equal(record.source, "cyberboss-cloud");
  assert.equal(record.event_type, "job.job_transition");
  assert.equal(record.status, "replied");
  assert.equal(record.summary_redacted, "Job event: job_transition.");
  assert.match(record.record_sha256, /^[0-9a-f]{64}$/);
  const serialized = JSON.stringify(record);
  for (const forbidden of [
    "prompt",
    "result_text",
    "context_token",
    "user_id",
    "thread_id",
    "target_ref",
  ]) {
    assert.equal(serialized.includes(forbidden), false);
  }
  assert.deepEqual(fixtureRecord(1), record);
  assert.throws(
    () =>
      mapJobEventToCanonical(fixtureRow(1, {
        to_status: "unsafe status",
      }), {
        deployedCommit: RELEASE_COMMIT,
      }),
    /CANONICAL_STATUS_INVALID/,
  );
});

test("deterministic compressed object is order independent and tamper evident", () => {
  const records = [fixtureRecord(2), fixtureRecord(1), fixtureRecord(3)];
  const first = encodeCanonicalBatch(records);
  const second = encodeCanonicalBatch(records.slice().reverse());
  assert.equal(first.eventCount, 3);
  assert.equal(first.objectSha256, second.objectSha256);
  assert.equal(first.eventSetSha256, second.eventSetSha256);
  assert.equal(
    eventSetSha256(records),
    eventSetSha256(records.slice().reverse()),
  );
  assert.equal(first.compressed.equals(second.compressed), true);
  const decoded = decodeCanonicalBatch(first.compressed, {
    expectedObjectSha256: first.objectSha256,
  });
  assert.deepEqual(
    decoded.records.map((record) => record.event_id),
    [
      "event_fixture_00001",
      "event_fixture_00002",
      "event_fixture_00003",
    ],
  );
  const corrupt = Buffer.from(first.compressed);
  corrupt[Math.floor(corrupt.length / 2)] ^= 0xff;
  assert.throws(
    () => decodeCanonicalBatch(corrupt),
    CanonicalIntegrityError,
  );
});

test("data-plane receipts reject fields outside the metadata-only contract", () => {
  const record = fixtureRecord(1);
  const batch = encodeCanonicalBatch([record]);
  const receipt = {
    schema_version: 1,
    task_id: "CB-240",
    status: "verified",
    batch_id: batch.batchId,
    object_sha256: batch.objectSha256,
    event_set_sha256: batch.eventSetSha256,
    manifest_record_sha256: hash("manifest-record"),
    remote_object_path: `objects/${batch.objectSha256.slice(0, 2)}/object`,
    verified_at: "2026-07-27T00:00:00.000Z",
    remote_event_count: 1,
    no_clone: true,
    real_data_operation: false,
  };
  assert.deepEqual(validateReceipt(receipt), receipt);
  assert.throws(
    () => validateReceipt({
      ...receipt,
      full_prompt: "must never cross the identity boundary",
    }),
    /CANONICAL_RECEIPT_FIELDS_INVALID/,
  );
});

test("50 events batch, ingest, list/get/verify receipt and reconcile to zero pending", async (t) => {
  const root = temporaryDirectory(t);
  let clock = new Date("2026-07-27T00:00:00.000Z");
  const now = () => clock;
  const databasePath = path.join(root, "runtime.db");
  const database = openDatabase(databasePath, now);
  const records = enqueueRecords(database, 50);
  const coordinator = createCoordinator(root, database, now);
  const first = await coordinator.runCycle({ force: true });
  assert.equal(first.batch.eventCount, 50);
  assert.equal(first.status.pendingEvents, 50);

  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: path.join(root, "private-db"),
    now,
  });
  const worker = new CanonicalDataWorker({
    outgoingDirectory: path.join(root, "spool", "outgoing"),
    receiptDirectory: path.join(root, "spool", "receipts"),
    stateFile: path.join(root, "data-state", "state.json"),
    adapter,
    now,
  });
  const synced = await worker.runOnce();
  assert.equal(synced.inspected, 1);
  assert.equal(synced.results[0].status, "verified");
  assert.ok(synced.operations.ingest >= 1);
  assert.ok(synced.operations.list >= 2);
  assert.ok(synced.operations.get >= 2);
  assert.ok(synced.operations.verify >= 2);

  clock = new Date("2026-07-27T00:00:01.000Z");
  const second = await coordinator.runCycle();
  assert.equal(second.receipts.verified, 50);
  assert.equal(second.status.pendingEvents, 0);
  assert.equal(second.status.state, "synced");
  assert.equal(second.status.mutationAllowed, true);
  assert.deepEqual(
    database.reconcileCanonicalEventIds(
      records.map((record) => record.event_id),
    ),
    {
      missingCanonical: [],
      missingLocal: [],
      setDiff: 0,
    },
  );
  database.close();
});

test("409 partial success verifies idempotently without a second object", async (t) => {
  const root = temporaryDirectory(t);
  const now = () => new Date("2026-07-27T00:00:00.000Z");
  const database = openDatabase(path.join(root, "runtime.db"), now);
  enqueueRecords(database, 3);
  const coordinator = createCoordinator(root, database, now);
  const built = await coordinator.runCycle({ force: true });
  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: path.join(root, "private-db"),
    now,
    faults: [{
      httpStatus: 409,
      afterWrite: true,
      outcomeUnknown: true,
    }],
  });
  const worker = new CanonicalDataWorker({
    outgoingDirectory: path.join(root, "spool", "outgoing"),
    receiptDirectory: path.join(root, "spool", "receipts"),
    stateFile: path.join(root, "data-state", "state.json"),
    adapter,
    now,
  });
  const result = await worker.runOnce();
  assert.equal(result.results[0].status, "verified");
  assert.equal(adapter.operationCounts.ingest, 1);
  const manifest = fs.readFileSync(
    path.join(root, "private-db", "Private-MetaDatabase", "manifest.jsonl"),
    "utf8",
  ).trim().split("\n");
  assert.equal(manifest.length, 1);
  assert.equal(JSON.parse(manifest[0]).sha256, built.batch.objectSha256);
  await coordinator.runCycle();
  assert.equal(coordinator.status().pendingEvents, 0);
  database.close();
});

test("429 retry hint and fake-clock ten-minute outage catch up without real wait", async (t) => {
  const root = temporaryDirectory(t);
  let clock = new Date("2026-07-27T00:00:00.000Z");
  const now = () => clock;
  const database = openDatabase(path.join(root, "runtime.db"), now);
  enqueueRecords(database, 5);
  const coordinator = createCoordinator(root, database, now);
  await coordinator.runCycle({ force: true });
  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: path.join(root, "private-db"),
    now,
    faults: [{
      httpStatus: 429,
      retryAfterMs: 120_000,
    }],
  });
  let worker = new CanonicalDataWorker({
    outgoingDirectory: path.join(root, "spool", "outgoing"),
    receiptDirectory: path.join(root, "spool", "receipts"),
    stateFile: path.join(root, "data-state", "state.json"),
    adapter,
    now,
  });
  const limited = await worker.runOnce();
  assert.equal(limited.results[0].status, "retry");
  assert.equal(limited.results[0].retry_after_ms, 120_000);
  await coordinator.runCycle();
  assert.equal(coordinator.status().pendingEvents, 5);

  clock = new Date("2026-07-27T00:10:00.000Z");
  worker = new CanonicalDataWorker({
    outgoingDirectory: path.join(root, "spool", "outgoing"),
    receiptDirectory: path.join(root, "spool", "receipts"),
    stateFile: path.join(root, "data-state", "state.json"),
    adapter,
    now,
  });
  const recovered = await worker.runOnce();
  assert.equal(recovered.results[0].status, "verified");
  await coordinator.runCycle();
  assert.equal(coordinator.status().pendingEvents, 0);
  database.close();
});

test("same event id with a different remote record hash quarantines and stops mutation", async (t) => {
  const root = temporaryDirectory(t);
  const now = () => new Date("2026-07-27T00:00:00.000Z");
  const database = openDatabase(path.join(root, "runtime.db"), now);
  enqueueRecords(database, 1);
  const coordinator = createCoordinator(root, database, now);
  await coordinator.runCycle({ force: true });
  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: path.join(root, "private-db"),
    now,
  });
  const original = encodeCanonicalBatch([fixtureRecord(0)]);
  const conflicting = encodeCanonicalBatch([
    fixtureRecord(0, {
      from_status: "reply_pending",
      to_status: "reply_failed",
      job_status: "reply_failed",
    }),
  ]);
  const originalSeed = path.join(root, original.objectName);
  const conflictingSeed = path.join(root, conflicting.objectName);
  fs.writeFileSync(originalSeed, original.compressed);
  await adapter.ingest({
    filePath: originalSeed,
    batchLabel: original.batchLabel,
  });
  fs.writeFileSync(conflictingSeed, conflicting.compressed);
  await adapter.ingest({
    filePath: conflictingSeed,
    batchLabel: conflicting.batchLabel,
  });

  const worker = new CanonicalDataWorker({
    outgoingDirectory: path.join(root, "spool", "outgoing"),
    receiptDirectory: path.join(root, "spool", "receipts"),
    stateFile: path.join(root, "data-state", "state.json"),
    adapter,
    now,
  });
  const result = await worker.runOnce();
  assert.equal(result.results[0].status, "integrity_error");
  await coordinator.runCycle();
  const status = coordinator.status();
  assert.equal(status.state, "integrity_error");
  assert.equal(status.mutationAllowed, false);
  assert.equal(
    fs.readdirSync(path.join(root, "spool", "quarantine")).length,
    1,
  );
  database.close();
});

test("deleted isolated SQLite rebuilds terminal index and Timeline source from canonical objects", async (t) => {
  const root = temporaryDirectory(t);
  const now = () => new Date("2026-07-27T00:00:00.000Z");
  const databasePath = path.join(root, "runtime.db");
  const database = openDatabase(databasePath, now);
  const records = enqueueRecords(database, 4);
  const coordinator = createCoordinator(root, database, now);
  const built = await coordinator.runCycle({ force: true });
  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: path.join(root, "private-db"),
    now,
  });
  const worker = new CanonicalDataWorker({
    outgoingDirectory: path.join(root, "spool", "outgoing"),
    receiptDirectory: path.join(root, "spool", "receipts"),
    stateFile: path.join(root, "data-state", "state.json"),
    adapter,
    now,
  });
  await worker.runOnce();
  await coordinator.runCycle();
  database.close();
  for (const suffix of ["", "-wal", "-shm"]) {
    fs.rmSync(`${databasePath}${suffix}`, { force: true });
  }
  assert.equal(fs.existsSync(databasePath), false);

  const pointerPath = path.join(root, "r2-recovery-pointer.json");
  fs.writeFileSync(
    pointerPath,
    `${JSON.stringify({
      schema_version: 1,
      provider: "r2_fixture",
      domain: "CyberBoss",
      canonical_event_set_sha256: built.batch.eventSetSha256,
      canonical_object_sha256: built.batch.objectSha256,
    })}\n`,
    { mode: 0o600 },
  );
  const rebuilt = await rebuildCanonicalProjection({
    adapter,
    outputDirectory: path.join(root, "rebuild"),
    recoveryPointerPath: pointerPath,
    sqlitePath: databasePath,
  });
  assert.equal(rebuilt.report.canonical_event_count, 4);
  assert.equal(rebuilt.report.terminal_job_count, 4);
  assert.equal(
    rebuilt.report.event_set_sha256,
    built.batch.eventSetSha256,
  );
  assert.deepEqual(
    rebuilt.terminalIndex.jobs.map((job) => job.event_id).sort(),
    records.map((record) => record.event_id).sort(),
  );
  assert.equal(rebuilt.report.operations.list >= 1, true);
  assert.equal(rebuilt.report.operations.get >= 2, true);
  assert.equal(rebuilt.report.operations.verify >= 1, true);
});
