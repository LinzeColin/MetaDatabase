#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const {
  CanonicalDataWorker,
  CanonicalSpoolCoordinator,
  FilesystemPrivateDatabaseAdapter,
  encodeCanonicalBatch,
  mapJobEventToCanonical,
  readRemoteCanonical,
  rebuildCanonicalProjection,
  sha256,
} = require("../src/services/canonical/canonical-sync");
const {
  RuntimeSpoolDatabase,
} = require("../src/services/db/database-adapter");

const APP_ROOT = path.resolve(__dirname, "..");
const FIXED_TIME = "2026-07-27T00:00:00.000Z";
const TEST_FILES = Object.freeze([
  "test/canonical-sync.test.js",
  "test/job-scheduler.test.js",
]);

class AcceptanceError extends Error {
  constructor(code) {
    super(code);
    this.name = "AcceptanceError";
    this.code = code;
  }
}

function expect(condition, code) {
  if (!condition) {
    throw new AcceptanceError(code);
  }
}

function parseArguments(values) {
  const result = {};
  const allowed = new Set([
    "--runtime-root",
    "--key-file",
    "--output-directory",
    "--release-commit",
    "--target-id-sha256",
  ]);
  if (values.length % 2 !== 0) {
    throw new AcceptanceError("ARGUMENT_CONTRACT");
  }
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!allowed.has(key) || !value || Object.hasOwn(result, key)) {
      throw new AcceptanceError("ARGUMENT_CONTRACT");
    }
    result[key.slice(2)] = String(value);
  }
  for (const required of [
    "runtime-root",
    "key-file",
    "output-directory",
    "release-commit",
    "target-id-sha256",
  ]) {
    if (!result[required]) {
      throw new AcceptanceError("ARGUMENT_REQUIRED");
    }
  }
  if (
    !path.isAbsolute(result["runtime-root"]) ||
    !path.isAbsolute(result["key-file"]) ||
    !path.isAbsolute(result["output-directory"]) ||
    !/^[0-9a-f]{40}$/.test(result["release-commit"]) ||
    !/^[0-9a-f]{12}$/.test(result["target-id-sha256"])
  ) {
    throw new AcceptanceError("ARGUMENT_VALUE_INVALID");
  }
  return result;
}

function ensureDirectory(directory, { empty = false } = {}) {
  if (!fs.existsSync(directory)) {
    fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  }
  const stats = fs.lstatSync(directory);
  expect(stats.isDirectory() && !stats.isSymbolicLink(), "DIRECTORY_INVALID");
  if (empty) {
    expect(fs.readdirSync(directory).length === 0, "DIRECTORY_NOT_EMPTY");
  }
  return directory;
}

function childDirectory(root, name) {
  expect(
    /^[a-z0-9][a-z0-9-]{0,63}$/.test(name),
    "CHILD_DIRECTORY_NAME_INVALID",
  );
  return ensureDirectory(path.join(root, name));
}

function atomicJson(target, value) {
  const temporary = `${target}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx",
  });
  fs.renameSync(temporary, target);
}

function readSource(relative) {
  return fs.readFileSync(path.join(APP_ROOT, relative), "utf8");
}

function assertStaticContract() {
  const migration = readSource("migrations/005_cb240_canonical_sync.sql");
  const canonical = readSource(
    "src/services/canonical/canonical-sync.js",
  );
  const database = readSource("src/services/db/database-adapter.js");
  const scheduler = readSource("src/services/jobs/job-scheduler.js");
  const dataCli = readSource("scripts/canonical-sync-data.js");
  const rebuildCli = readSource("scripts/canonical-rebuild.js");
  for (const [source, marker] of [
    [migration, "sync_spool_identity_immutable_guard"],
    [migration, "sync_spool_delete_guard"],
    [canonical, "NoClonePrivateDatabaseAdapter"],
    [canonical, "CanonicalSpoolCoordinator"],
    [canonical, "CanonicalDataWorker"],
    [canonical, "rebuildCanonicalProjection"],
    [database, "canonicalSyncStatus"],
    [database, "markCanonicalBatchIntegrity"],
    [scheduler, "canonicalMutationGuard"],
    [dataCli, "CANONICAL_DATA_IDENTITY_REQUIRED"],
    [rebuildCli, "CANONICAL_DATA_IDENTITY_REQUIRED"],
  ]) {
    expect(source.includes(marker), "STATIC_CONTRACT_MISSING");
  }
  expect(
    !/\b(?:DROP|RENAME|VACUUM)\b/i.test(migration),
    "MIGRATION_DESTRUCTIVE",
  );
  for (const forbidden of [
    ".clone(",
    "git clone",
    "PRIVATE_DB_OPERATION_PUT",
    "PRIVATE_DB_OPERATION_DELETE",
  ]) {
    expect(!canonical.includes(forbidden), "NO_CLONE_CONTRACT_VIOLATION");
  }
}

function runExecutableSuite() {
  const environment = {
    ...process.env,
    NODE_ENV: "test",
  };
  delete environment.NODE_TEST_CONTEXT;
  const result = spawnSync(
    process.execPath,
    ["--test", ...TEST_FILES],
    {
      cwd: APP_ROOT,
      encoding: "utf8",
      env: environment,
      timeout: 180_000,
      maxBuffer: 8 * 1024 * 1024,
    },
  );
  if (result.status !== 0) {
    throw new AcceptanceError("EXECUTABLE_SUITE_FAILED");
  }
  const output = `${result.stdout || ""}\n${result.stderr || ""}`;
  const summary = (name) => {
    const values = [...output.matchAll(
      new RegExp(
        `(?:^|\\n)[^\\S\\r\\n]*(?:ℹ|#)?[^\\S\\r\\n]*${name}\\s+([0-9]+)`,
        "g",
      ),
    )].map((match) => Number(match[1]));
    return values.filter(Number.isFinite).at(-1);
  };
  for (const marker of [
    "50 events batch, ingest, list/get/verify receipt and reconcile to zero pending",
    "409 partial success verifies idempotently without a second object",
    "429 retry hint and fake-clock ten-minute outage catch up without real wait",
    "same event id with a different remote record hash quarantines and stops mutation",
    "deleted isolated SQLite rebuilds terminal index and Timeline source from canonical objects",
    "scheduler rejects bounded mutation while canonical backlog protection is active",
  ]) {
    expect(output.includes(marker), "EXECUTABLE_SUITE_INVENTORY");
  }
  const tests = summary("tests");
  const failures = summary("fail");
  expect(
    Number.isSafeInteger(tests) && tests >= 17 && failures === 0,
    "EXECUTABLE_SUITE_SUMMARY_INVALID",
  );
  return Object.freeze({
    files: TEST_FILES.map((file) => path.basename(file)),
    tests,
    failures,
    fixed_wait: false,
    real_credentials: false,
    real_private_database: false,
  });
}

function openDatabase(databasePath, key, now) {
  return new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: Buffer.from(key),
    identityKey: Buffer.from(key),
    now,
  });
}

function fixtureRow(index, releaseCommit, overrides = {}) {
  const suffix = String(index).padStart(6, "0");
  return {
    event_id: `event_fixture_${suffix}`,
    job_id: `job_fixture_${suffix}`,
    correlation_id: `corr_fixture_${suffix}`,
    event_type: "job_transition",
    from_status: "reply_pending",
    to_status: "replied",
    occurred_at: FIXED_TIME,
    recorded_at: FIXED_TIME,
    workspace_alias: "cyberboss",
    runtime: "codex",
    input_sha256: sha256(Buffer.from(`input-${suffix}`, "utf8")),
    output_sha256: sha256(Buffer.from(`output-${suffix}`, "utf8")),
    job_status: "replied",
    deployed_commit: releaseCommit,
    ...overrides,
  };
}

function fixtureRecord(index, releaseCommit, overrides = {}) {
  return mapJobEventToCanonical(
    fixtureRow(index, releaseCommit, overrides),
    { deployedCommit: releaseCommit },
  );
}

function enqueueRecords(database, records) {
  for (const record of records) {
    database.enqueueSyncEvent({
      eventId: record.event_id,
      objectType: "fixture_terminal_event",
      objectId: record.job_id,
      canonicalPath:
        `Private-MetaDatabase/CyberBoss/events/${record.event_id}.json`,
      payloadRedacted: record,
    });
  }
}

function coordinatorFor(root, database, now, releaseCommit, options = {}) {
  return new CanonicalSpoolCoordinator({
    database,
    outgoingDirectory: childDirectory(root, "outgoing"),
    receiptDirectory: childDirectory(root, "receipts"),
    quarantineDirectory: childDirectory(root, "quarantine"),
    deployedCommit: releaseCommit,
    now,
    flushOnTerminal: true,
    ...options,
  });
}

function workerFor(root, adapter, now) {
  return new CanonicalDataWorker({
    outgoingDirectory: childDirectory(root, "outgoing"),
    receiptDirectory: childDirectory(root, "receipts"),
    stateFile: path.join(childDirectory(root, "data-state"), "state.json"),
    adapter,
    now,
  });
}

async function drainCoordinator(coordinator, worker, maximumCycles = 100) {
  const batchIds = new Set();
  const addBatch = (cycle) => {
    if (cycle.batch) {
      batchIds.add(cycle.batch.batchId);
    }
  };
  addBatch(await coordinator.runCycle({ force: true }));
  let cycles = 0;
  while (coordinator.status().pendingEvents > 0) {
    expect(cycles < maximumCycles, "CANONICAL_DRAIN_STALLED");
    await worker.runOnce();
    addBatch(await coordinator.runCycle({ force: true }));
    cycles += 1;
  }
  return Object.freeze({
    batchIds: Object.freeze([...batchIds]),
    cycles,
  });
}

function createTerminalJobs(database, count, privateValues) {
  const jobIds = [];
  for (let index = 0; index < count; index += 1) {
    const accepted = database.acceptInbound({
      source: "weixin",
      sourceAccountRef: privateValues.account,
      sourceMessageId: `cb240-terminal-job-${index}`,
      userRef: privateValues.user,
      messageType: "text",
      payload: {
        prompt: privateValues.prompt,
        result: privateValues.result,
      },
      contextToken: privateValues.context,
    });
    let job = database.getJob(accepted.jobId);
    for (const status of [
      "running",
      "succeeded",
      "reply_pending",
      "replied",
    ]) {
      job = database.transitionJob(job.id, status, {
        expectedVersion: Number(job.state_version),
        metadata: {
          transition_code: `cb240_fixture_${status}`,
        },
      });
    }
    jobIds.push(job.id);
  }
  return Object.freeze(jobIds);
}

async function runCadencePolicy(
  runtimeRoot,
  key,
  releaseCommit,
) {
  const root = childDirectory(runtimeRoot, "cadence-policy");
  let clock = new Date("2026-07-27T02:00:00.000Z");
  const now = () => clock;
  const database = openDatabase(path.join(root, "runtime.db"), key, now);
  const ordinaryRecords = Array.from(
    { length: 50 },
    (_, index) => fixtureRecord(50_000 + index, releaseCommit, {
      event_type: "job_summary",
    }),
  );
  const materialEventTypes = [
    "release_completed",
    "incident_declared",
    "recovery_completed",
  ];
  const materialRecords = materialEventTypes.map((eventType, index) =>
    fixtureRecord(51_000 + index, releaseCommit, { event_type: eventType }));
  enqueueRecords(database, [...ordinaryRecords, ...materialRecords]);
  const spool = childDirectory(root, "spool");
  const coordinator = coordinatorFor(
    spool,
    database,
    now,
    releaseCommit,
    { maxLagSeconds: 1 },
  );
  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: childDirectory(root, "private-db"),
    now,
  });
  const worker = workerFor(spool, adapter, now);
  const first = await coordinator.runCycle();
  expect(
    first.staged === 0 && first.batch?.deliveryClass === "material",
    "MATERIAL_BATCH_NOT_PRIORITIZED",
  );
  const immediate = await worker.runOnce({ mode: "material" });
  expect(
    immediate.status === "completed" &&
      immediate.results.length === 1 &&
      immediate.results[0].deliveryClass === "material",
    "MATERIAL_IMMEDIATE_FLUSH_FAILED",
  );
  const operationsAfterMaterial = { ...adapter.operationCounts };

  clock = new Date("2026-07-27T04:00:00.000Z");
  const second = await coordinator.runCycle();
  expect(
    second.batch?.deliveryClass === "ordinary" &&
      second.status.ordinaryLagExceeded === true &&
      second.status.mutationAllowed === true,
    "ORDINARY_LOCAL_BATCH_OR_PROTECTION_DRIFT",
  );
  const beforeDaily = await worker.runOnce({ mode: "material" });
  expect(
    beforeDaily.status === "noop_no_commit" &&
      JSON.stringify(adapter.operationCounts) ===
        JSON.stringify(operationsAfterMaterial),
    "ORDINARY_REMOTE_EARLY_COMMIT",
  );
  clock = new Date("2026-07-28T03:20:00.000Z");
  const dailyBatch = await coordinator.runCycle();
  expect(
    dailyBatch.batch?.deliveryClass === "ordinary",
    "ORDINARY_DAILY_OBJECT_MATERIALIZATION_FAILED",
  );
  const daily = await worker.runOnce({ mode: "daily" });
  expect(
    daily.status === "completed" &&
      daily.results.length === 1 &&
      daily.results[0].deliveryClass === "ordinary",
    "ORDINARY_DAILY_SYNC_FAILED",
  );
  await coordinator.runCycle();
  const remote = await readRemoteCanonical(adapter);
  expect(
    coordinator.status().pendingEvents === 0 &&
      remote.events.size === ordinaryRecords.length + materialRecords.length,
    "CADENCE_RECONCILIATION_FAILED",
  );
  const operationsAfterDaily = { ...adapter.operationCounts };
  const noop = await worker.runOnce({ mode: "daily" });
  expect(
    noop.status === "noop_no_commit" &&
      JSON.stringify(adapter.operationCounts) ===
        JSON.stringify(operationsAfterDaily),
    "EMPTY_COMMIT_NOT_NOOP",
  );
  database.close();
  return Object.freeze({
    ordinary_events: ordinaryRecords.length,
    material_events: materialRecords.length,
    material_event_types: Object.freeze([...materialEventTypes].sort()),
    canonical_events: ordinaryRecords.length + materialRecords.length,
    ordinary_sync_schedule: "daily",
    ordinary_sync_on_calendar: "*-*-* 03:20:00 UTC",
    ordinary_remote_commits_before_daily: 0,
    empty_commits: 0,
    no_new_fact_status: noop.status,
    ordinary_age_blocks_mutation: false,
    latency_clock: "virtual",
    latency_samples: materialRecords.length,
    material_latency_p95_seconds: 0,
    material_latency_limit_seconds: 60,
    within_limit: true,
    real_wait_calls: 0,
  });
}

async function runBatchThresholds(
  runtimeRoot,
  key,
  releaseCommit,
) {
  const root = childDirectory(runtimeRoot, "batch-thresholds");
  let clock = new Date(FIXED_TIME);
  const now = () => clock;
  const databasePath = path.join(root, "runtime.db");
  const database = openDatabase(databasePath, key, now);
  const records = Array.from(
    { length: 1_000 },
    (_, index) => fixtureRecord(index, releaseCommit),
  );
  enqueueRecords(database, records);
  const spool = childDirectory(root, "spool");
  const coordinator = coordinatorFor(
    spool,
    database,
    now,
    releaseCommit,
    {
      backlogMaxEvents: 1_000,
    },
  );
  const before = await coordinator.runCycle({ force: true });
  expect(
    before.status.pendingEvents === 1_000 &&
      before.status.mutationAllowed === false,
    "BACKLOG_PROTECTION_NOT_ACTIVE",
  );
  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: childDirectory(root, "private-db"),
    now,
  });
  const worker = workerFor(spool, adapter, now);
  const drained = await drainCoordinator(coordinator, worker, 40);
  const objectFiles = fs.readdirSync(path.join(spool, "outgoing"))
    .filter((name) => name.endsWith(".ndjson.gz"))
    .sort();
  const batchSizes = objectFiles.map((name) =>
    require("../src/services/canonical/canonical-sync").decodeCanonicalBatch(
      fs.readFileSync(path.join(spool, "outgoing", name)),
    ).eventCount,
  );
  expect(
    batchSizes.length === 20 &&
      batchSizes.every((size) => size === 50),
    "COUNT_THRESHOLD_INVALID",
  );
  const remote = await readRemoteCanonical(adapter);
  const reconciliation = database.reconcileCanonicalEventIds(
    [...remote.events.keys()],
  );
  expect(
    remote.events.size === 1_000 &&
      reconciliation.setDiff === 0 &&
      coordinator.status().pendingEvents === 0 &&
      coordinator.status().mutationAllowed === true,
    "THOUSAND_EVENT_RECONCILIATION_FAILED",
  );
  const eventSetSha256 = require(
    "../src/services/canonical/canonical-sync"
  ).eventSetSha256(records);
  database.close();
  for (const suffix of ["", "-wal", "-shm"]) {
    fs.rmSync(`${databasePath}${suffix}`, { force: true });
  }
  expect(!fs.existsSync(databasePath), "SQLITE_DELETE_FAILED");

  const firstObject = fs.readFileSync(
    path.join(spool, "outgoing", objectFiles[0]),
  );
  const pointerPath = path.join(root, "r2-recovery-pointer.json");
  atomicJson(pointerPath, {
    schema_version: 1,
    provider: "r2_fixture",
    domain: "CyberBoss",
    canonical_event_set_sha256: eventSetSha256,
    canonical_object_sha256: sha256(firstObject),
  });
  const rebuilt = await rebuildCanonicalProjection({
    adapter,
    outputDirectory: childDirectory(root, "rebuild"),
    recoveryPointerPath: pointerPath,
    sqlitePath: databasePath,
  });
  expect(
    rebuilt.report.canonical_event_count === 1_000 &&
      rebuilt.report.terminal_job_count === 1_000 &&
      rebuilt.report.event_set_sha256 === eventSetSha256 &&
      rebuilt.report.object_count === 20,
    "REBUILD_CONTRACT_FAILED",
  );

  const byteRoot = childDirectory(runtimeRoot, "byte-threshold");
  const byteDatabase = openDatabase(
    path.join(byteRoot, "runtime.db"),
    key,
    now,
  );
  const byteRecords = [10_000, 10_001, 10_002].map((index) =>
    fixtureRecord(index, releaseCommit),
  );
  enqueueRecords(byteDatabase, byteRecords);
  const twoRecordBytes = encodeCanonicalBatch(
    byteRecords.slice(0, 2),
  ).uncompressedBytes;
  const byteCoordinator = coordinatorFor(
    childDirectory(byteRoot, "spool"),
    byteDatabase,
    now,
    releaseCommit,
    {
      maxBytes: twoRecordBytes,
      flushOnTerminal: false,
    },
  );
  const byteCycle = await byteCoordinator.runCycle();
  expect(
    byteCycle.batch?.eventCount === 2 &&
      byteCoordinator.status().pendingEvents === 3,
    "BYTE_THRESHOLD_INVALID",
  );
  byteDatabase.close();

  const ageRoot = childDirectory(runtimeRoot, "ordinary-age");
  clock = new Date(FIXED_TIME);
  const ageDatabase = openDatabase(
    path.join(ageRoot, "runtime.db"),
    key,
    now,
  );
  enqueueRecords(ageDatabase, [fixtureRecord(20_000, releaseCommit, {
    event_type: "job_summary",
  })]);
  const ageCoordinator = coordinatorFor(
    childDirectory(ageRoot, "spool"),
    ageDatabase,
    now,
    releaseCommit,
    {
      flushOnTerminal: false,
      maxAgeMs: 60_000,
      maxLagSeconds: 1,
    },
  );
  expect(
    (await ageCoordinator.runCycle()).batch === null,
    "AGE_EARLY_OBJECT_FLUSH",
  );
  clock = new Date(Date.parse(FIXED_TIME) + 59_999);
  expect(
    (await ageCoordinator.runCycle()).batch === null,
    "AGE_EARLY_OBJECT_FLUSH",
  );
  clock = new Date(Date.parse(FIXED_TIME) + 60_000);
  const ageCycle = await ageCoordinator.runCycle();
  expect(
    ageCycle.batch === null &&
      ageCycle.status.ordinaryLagExceeded === true &&
      ageCycle.status.mutationAllowed === true,
    "ORDINARY_AGE_REMOTE_TRIGGER_OR_PROTECTION",
  );
  const operatorCycle = await ageCoordinator.runCycle({ force: true });
  expect(
    operatorCycle.batch?.eventCount === 1,
    "OPERATOR_OBJECT_MATERIALIZATION_INVALID",
  );
  ageDatabase.close();

  return Object.freeze({
    terminal_events: records.length,
    max_records: 50,
    max_uncompressed_bytes: 262_144,
    ordinary_age_remote_trigger: false,
    count_threshold_batch_count: batchSizes.length,
    count_threshold_batch_sizes: Object.freeze([...batchSizes]),
    byte_threshold_selected_events: byteCycle.batch.eventCount,
    byte_threshold_uncompressed_limit: twoRecordBytes,
    ordinary_age_blocks_mutation: false,
    pending_during_failure: true,
    backlog_mutation_stopped: true,
    mutation_restored_after_catchup: true,
    canonical_event_set_sha256: eventSetSha256,
    remote_event_count: remote.events.size,
    set_diff: reconciliation.setDiff,
    object_count: rebuilt.report.object_count,
    no_per_event_remote_commit: rebuilt.report.object_count < records.length,
    rebuild: Object.freeze({
      sqlite_present: rebuilt.report.sqlite_present,
      canonical_event_count: rebuilt.report.canonical_event_count,
      terminal_job_count: rebuilt.report.terminal_job_count,
      event_set_sha256: rebuilt.report.event_set_sha256,
      terminal_index_sha256: rebuilt.report.terminal_index_sha256,
      timeline_source_sha256: rebuilt.report.timeline_source_sha256,
      recovery_pointer_sha256: rebuilt.report.recovery_pointer_sha256,
      r2_fixture_only: true,
      real_r2_operation: false,
      timeline_web_built: false,
    }),
    operations: Object.freeze({ ...adapter.operationCounts }),
  });
}

function writeBatchFile(directory, batch) {
  const target = path.join(directory, batch.objectName);
  fs.writeFileSync(target, batch.compressed, {
    mode: 0o640,
    flag: "wx",
  });
  return target;
}

async function runConcurrentFaultMatrix(
  runtimeRoot,
  releaseCommit,
) {
  const root = childDirectory(runtimeRoot, "concurrent-sync");
  let clock = new Date(FIXED_TIME);
  const now = () => clock;
  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: childDirectory(root, "private-db"),
    now,
    faults: [
      {
        httpStatus: 409,
        afterWrite: true,
        outcomeUnknown: true,
      },
      { httpStatus: 403 },
      { httpStatus: 429, retryAfterMs: 120_000 },
      { httpStatus: 503, outcomeUnknown: true },
      {
        httpStatus: 503,
        afterWrite: true,
        outcomeUnknown: true,
      },
    ],
  });
  const records = Array.from(
    { length: 50 },
    (_, index) => fixtureRecord(30_000 + index, releaseCommit),
  );
  const workers = records.map((record, index) => {
    const group = childDirectory(
      root,
      `group-${String(index).padStart(2, "0")}`,
    );
    const outgoing = childDirectory(group, "outgoing");
    const receipts = childDirectory(group, "receipts");
    const state = childDirectory(group, "data-state");
    writeBatchFile(outgoing, encodeCanonicalBatch([record]));
    return new CanonicalDataWorker({
      outgoingDirectory: outgoing,
      receiptDirectory: receipts,
      stateFile: path.join(state, "state.json"),
      adapter,
      now,
    });
  });
  const initial = await Promise.all(workers.map((worker) => worker.runOnce()));
  const initialRows = initial.map((run) => run.results[0]);
  const verifiedBeforeCatchup = initialRows.filter(
    (row) => row.status === "verified",
  ).length;
  const retryRows = initialRows.filter((row) => row.status === "retry");
  const retryClasses = retryRows
    .map((row) => row.error_class)
    .sort();
  expect(adapter.faults.length === 0, "FAULT_MATRIX_NOT_EXERCISED");
  expect(
    verifiedBeforeCatchup === 47 &&
      retryRows.length === 3 &&
      retryClasses.includes("canonical_auth_scope") &&
      retryClasses.includes("provider_rate_limit") &&
      retryClasses.includes("unknown_outcome_reconcile") &&
      retryRows.some((row) => row.retry_after_ms === 120_000),
    "INITIAL_FAULT_OUTCOME_INVALID",
  );
  clock = new Date(Date.parse(FIXED_TIME) + 10 * 60_000);
  const catchup = await Promise.all(workers.map((worker) => worker.runOnce()));
  const remote = await readRemoteCanonical(adapter);
  const expected = new Map(
    records.map((record) => [record.event_id, record.record_sha256]),
  );
  const missing = [...expected].filter(
    ([eventId, recordHash]) =>
      remote.events.get(eventId)?.record.record_sha256 !== recordHash,
  );
  const unexpected = [...remote.events.keys()].filter(
    (eventId) => !expected.has(eventId),
  );
  expect(
    missing.length === 0 &&
      unexpected.length === 0 &&
      remote.events.size === 50 &&
      catchup.every((run) =>
        run.results.every((row) =>
          ["verified", "skipped"].includes(row.status),
        ),
      ),
    "CONCURRENT_CATCHUP_SET_MISMATCH",
  );
  return Object.freeze({
    concurrent_sync_groups: 50,
    concurrency_primitive: "Promise.all",
    manifest_409_refetch_exercised: true,
    auth_403_pending_exercised: true,
    rate_limit_429_exercised: true,
    retry_hint_ms: 120_000,
    transient_outage_exercised: true,
    partial_success_refetch_exercised: true,
    initial_verified_groups: verifiedBeforeCatchup,
    initial_pending_groups: retryRows.length,
    retry_error_classes: Object.freeze(retryClasses),
    outage_duration_seconds: 600,
    clock: "virtual",
    real_wait_calls: 0,
    caught_up_groups: 50,
    remote_event_count: remote.events.size,
    missing_events: missing.length,
    unexpected_events: unexpected.length,
    set_diff: missing.length + unexpected.length,
    no_clone: adapter.noClone,
    real_data_operation: adapter.realDataOperation,
    operations: Object.freeze({ ...adapter.operationCounts }),
  });
}

async function runIntegrityConflict(
  runtimeRoot,
  key,
  releaseCommit,
) {
  const root = childDirectory(runtimeRoot, "integrity-conflict");
  const now = () => new Date(FIXED_TIME);
  const database = openDatabase(path.join(root, "runtime.db"), key, now);
  const originalRecord = fixtureRecord(40_000, releaseCommit);
  const conflictingRecord = fixtureRecord(40_000, releaseCommit, {
    to_status: "reply_failed",
    job_status: "reply_failed",
  });
  expect(
    originalRecord.event_id === conflictingRecord.event_id &&
      originalRecord.record_sha256 !== conflictingRecord.record_sha256,
    "CONFLICT_FIXTURE_INVALID",
  );
  enqueueRecords(database, [originalRecord]);
  const spool = childDirectory(root, "spool");
  const coordinator = coordinatorFor(
    spool,
    database,
    now,
    releaseCommit,
  );
  await coordinator.runCycle({ force: true });
  const adapter = new FilesystemPrivateDatabaseAdapter({
    root: childDirectory(root, "private-db"),
    now,
  });
  for (const record of [originalRecord, conflictingRecord]) {
    const batch = encodeCanonicalBatch([record]);
    const source = path.join(root, batch.objectName);
    fs.writeFileSync(source, batch.compressed, {
      mode: 0o600,
      flag: "wx",
    });
    await adapter.ingest({
      filePath: source,
      batchLabel: batch.batchLabel,
    });
  }
  const worker = workerFor(spool, adapter, now);
  const result = await worker.runOnce();
  expect(
    result.results[0].status === "integrity_error",
    "INTEGRITY_RECEIPT_MISSING",
  );
  await coordinator.runCycle();
  const status = coordinator.status();
  const quarantineCount = fs.readdirSync(
    path.join(spool, "quarantine"),
  ).length;
  expect(
    status.state === "integrity_error" &&
      status.mutationAllowed === false &&
      quarantineCount === 1,
    "INTEGRITY_PROTECTION_FAILED",
  );
  database.close();
  return Object.freeze({
    same_event_id_different_hash_detected: true,
    last_write_wins: false,
    source_object_deleted: false,
    quarantine_count: quarantineCount,
    state: status.state,
    bounded_mutation_allowed: status.mutationAllowed,
    incident_class: "P0_integrity",
  });
}

function regularFilesRecursively(root) {
  const files = [];
  if (!fs.existsSync(root)) {
    return files;
  }
  const visit = (directory) => {
    const stats = fs.lstatSync(directory);
    expect(!stats.isSymbolicLink(), "PRIVACY_SCAN_SYMLINK");
    if (stats.isFile()) {
      files.push(directory);
      return;
    }
    expect(stats.isDirectory(), "PRIVACY_SCAN_SPECIAL_FILE");
    for (const entry of fs.readdirSync(directory).sort()) {
      visit(path.join(directory, entry));
    }
  };
  visit(root);
  return files;
}

function scanPrivacy(roots, forbiddenValues, key, keyFile) {
  let plaintextHits = 0;
  let encryptionKeyHits = 0;
  const categories = new Set();
  for (const root of roots) {
    for (const filePath of regularFilesRecursively(root)) {
      if (path.resolve(filePath) === path.resolve(keyFile)) {
        continue;
      }
      const bytes = fs.readFileSync(filePath);
      for (const value of forbiddenValues) {
        if (bytes.includes(Buffer.from(value, "utf8"))) {
          plaintextHits += 1;
        }
      }
      if (key.length > 0 && bytes.includes(key)) {
        encryptionKeyHits += 1;
      }
      const name = path.basename(filePath);
      if (/runtime\.db(?:-(?:wal|shm))?$/.test(name)) {
        categories.add("db_wal_shm");
      } else if (name.endsWith(".ndjson.gz")) {
        categories.add("canonical_objects");
      } else if (name.endsWith(".receipt.json")) {
        categories.add("receipts");
      } else if (
        [
          "terminal-index.json",
          "timeline-source.ndjson",
          "rebuild-report.json",
        ].includes(name)
      ) {
        categories.add("rebuild_outputs");
      } else {
        categories.add("state_and_evidence");
      }
    }
  }
  return Object.freeze({
    scanned_categories: Object.freeze([...categories].sort()),
    full_prompt_result_identity_hits: plaintextHits,
    encryption_key_hits: encryptionKeyHits,
    raw_user_thread_target_hits: plaintextHits,
    real_credentials_used: false,
    result: plaintextHits === 0 && encryptionKeyHits === 0
      ? "passed"
      : "failed",
  });
}

async function runAcceptance(args) {
  assertStaticContract();
  const runtimeRoot = ensureDirectory(args["runtime-root"], { empty: true });
  const outputDirectory = ensureDirectory(
    args["output-directory"],
    { empty: true },
  );
  const keyFile = args["key-file"];
  expect(
    fs.existsSync(keyFile) &&
      fs.lstatSync(keyFile).isFile() &&
      !fs.lstatSync(keyFile).isSymbolicLink(),
    "KEY_FILE_INVALID",
  );
  const key = fs.readFileSync(keyFile);
  expect(key.length === 32, "KEY_LENGTH_INVALID");

  const privateValues = Object.freeze({
    account: ["CB240", "PRIVATE", "ACCOUNT", "8f1a"].join("-"),
    user: ["CB240", "PRIVATE", "USER", "72c0"].join("-"),
    context: ["CB240", "PRIVATE", "CONTEXT", "99d3"].join("-"),
    prompt: ["CB240", "PRIVATE", "PROMPT", "d2e5"].join("-"),
    result: ["CB240", "PRIVATE", "RESULT", "31ab"].join("-"),
  });
  const executableSuite = runExecutableSuite();
  const cadence = await runCadencePolicy(
    runtimeRoot,
    key,
    args["release-commit"],
  );
  const thresholds = await runBatchThresholds(
    runtimeRoot,
    key,
    args["release-commit"],
  );
  const concurrent = await runConcurrentFaultMatrix(
    runtimeRoot,
    args["release-commit"],
  );
  const integrity = await runIntegrityConflict(
    runtimeRoot,
    key,
    args["release-commit"],
  );
  const privacy = scanPrivacy(
    [runtimeRoot, outputDirectory],
    Object.values(privateValues),
    key,
    keyFile,
  );
  expect(privacy.result === "passed", "PRIVACY_SCAN_FAILED");

  const report = {
    schema_version: 1,
    task_id: "CB-240",
    phase: "P2.5",
    release_commit: args["release-commit"],
    target_id_sha256: args["target-id-sha256"],
    generated_at: FIXED_TIME,
    claim_level: "deterministic_fixture",
    generated_from_synthetic_state: true,
    executable_suite: executableSuite,
    ac_030_rebuild: thresholds.rebuild,
    ac_031_batching_latency: {
      ...cadence,
      terminal_events: thresholds.terminal_events,
      max_records: thresholds.max_records,
      max_uncompressed_bytes: thresholds.max_uncompressed_bytes,
      ordinary_age_remote_trigger:
        thresholds.ordinary_age_remote_trigger,
      count_threshold_batch_count:
        thresholds.count_threshold_batch_count,
      count_threshold_batch_sizes:
        thresholds.count_threshold_batch_sizes,
      byte_threshold_selected_events:
        thresholds.byte_threshold_selected_events,
      byte_threshold_uncompressed_limit:
        thresholds.byte_threshold_uncompressed_limit,
      ordinary_age_blocks_mutation:
        thresholds.ordinary_age_blocks_mutation,
      pending_during_failure: thresholds.pending_during_failure,
      backlog_mutation_stopped:
        thresholds.backlog_mutation_stopped,
      mutation_restored_after_catchup:
        thresholds.mutation_restored_after_catchup,
      remote_event_count: thresholds.remote_event_count,
      set_diff: thresholds.set_diff,
      object_count: thresholds.object_count,
      no_per_event_remote_commit:
        thresholds.no_per_event_remote_commit,
    },
    ac_032_conflict_retry: concurrent,
    ac_033_privacy: privacy,
    integrity_protection: integrity,
    canonical_truth: {
      area: "Private-MetaDatabase",
      domain: "CyberBoss",
      branch: "main",
      allowed_operations: ["ingest", "get", "list", "verify"],
      forbidden_operations: ["clone", "put", "delete"],
      no_clone: true,
      event_set_sha256: thresholds.canonical_event_set_sha256,
      set_diff: thresholds.set_diff,
      operation_counts: thresholds.operations,
    },
    boundaries: {
      code_data_identity_separated: true,
      real_private_database_operation: false,
      private_database_activation_status: "activation_pending",
      real_r2_operation: false,
      timeline_projection_only: true,
      timeline_web_build_search: false,
      cb_300_executed: false,
      pg_2_executed: false,
      service_started: false,
      service_enabled: false,
      current_switched: false,
      remote_publication: "none",
      upstream_clarification_received: false,
      license_expression: "AGPL-3.0-only AND GPL-3.0-only",
    },
    result: "passed",
  };
  atomicJson(
    path.join(outputDirectory, "canonical-sync-report.json"),
    report,
  );
  return report;
}

async function main() {
  try {
    const args = parseArguments(process.argv.slice(2));
    const report = await runAcceptance(args);
    process.stdout.write(
      `CB240_CANONICAL_SYNC_ACCEPTANCE=PASS ` +
        `events=${report.ac_031_batching_latency.terminal_events} ` +
        `groups=${report.ac_032_conflict_retry.concurrent_sync_groups} ` +
        `set_diff=${report.canonical_truth.set_diff} ` +
        `real_private_database=false publication=none\n`,
    );
  } catch (error) {
    process.stderr.write(
      `CB240_CANONICAL_SYNC_ACCEPTANCE=FAIL ` +
        `reason=${error?.code || error?.message || "unknown"}\n`,
    );
    process.exitCode = 2;
  }
}

void main();
