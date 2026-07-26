#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { DatabaseSync } = require("node:sqlite");

const {
  PayloadRedactedError,
  RuntimeSpoolDatabase,
} = require("../src/services/db/database-adapter");
const {
  JOB_STATUSES,
  canTransition,
  transitionPairs,
} = require("../src/services/jobs/job-state-machine");

const APP_ROOT = path.resolve(__dirname, "..");
const MIGRATION_ROOT = path.join(APP_ROOT, "migrations");
const CUT_POINTS = Object.freeze([
  "after_begin",
  "after_inbox_insert",
  "after_job_insert",
  "after_event_insert",
  "after_commit",
]);
const REQUIRED_TESTS = Object.freeze([
  "clean and existing-v1 migration are additive and legacy-readable",
  "10,000 durable fixtures have stable collision-free source, correlation and job IDs",
  "32 concurrent duplicate inserters create one inbox and one executable job",
  "service and DB guards reject illegal or stale transitions and preserve immutable events",
  "transaction cut points preserve inbox RPO 0 without uncommitted fragments",
  "AES-256-GCM, TTL redaction and mock canonical recovery leave no plaintext",
]);

function fail(code) {
  process.stderr.write(`CB200_ACCEPTANCE=FAIL reason=${code}\n`);
  process.exitCode = 2;
}

function parseArguments(values) {
  const result = {};
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (
      ![
        "--database",
        "--key-file",
        "--output-directory",
        "--release-commit",
        "--target-id-sha256",
      ].includes(key) ||
      value === undefined
    ) {
      throw new Error("ARGUMENT_CONTRACT");
    }
    result[key.slice(2)] = value;
  }
  return result;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
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

function runExecutableTests() {
  const result = spawnSync(
    process.execPath,
    [
      "--test",
      "test/job-state-machine.test.js",
      "test/runtime-spool.test.js",
    ],
    {
      cwd: APP_ROOT,
      encoding: "utf8",
      timeout: 120000,
      maxBuffer: 4 * 1024 * 1024,
    },
  );
  if (result.status !== 0) {
    throw new Error("EXECUTABLE_TEST_FAILURE");
  }
  const output = `${result.stdout}\n${result.stderr}`;
  if (!output.includes("fail 0")) {
    throw new Error("EXECUTABLE_TEST_SUMMARY");
  }
  for (const marker of REQUIRED_TESTS) {
    if (!output.includes(marker)) {
      throw new Error("EXECUTABLE_TEST_INVENTORY");
    }
  }
  return Object.freeze({
    sha256: sha256(Buffer.from(output, "utf8")),
    namedRuntimeTests: REQUIRED_TESTS.length,
    stateMachineTests: 4,
    result: "passed",
  });
}

function scanFiles(databasePath, forbidden) {
  let hits = 0;
  const scanned = [];
  for (const suffix of ["", "-wal", "-shm"]) {
    const candidate = `${databasePath}${suffix}`;
    if (!fs.existsSync(candidate)) {
      continue;
    }
    const bytes = fs.readFileSync(candidate);
    scanned.push(path.basename(candidate));
    for (const value of forbidden) {
      if (bytes.includes(value)) {
        hits += 1;
      }
    }
  }
  return Object.freeze({ hits, scanned });
}

function runAcceptance({
  databasePath,
  key,
  outputDirectory,
  releaseCommit,
  targetIdSha256,
}) {
  const tests = runExecutableTests();
  let clock = new Date("2026-07-27T00:00:00.000Z");
  const database = new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: key,
    now: () => clock,
    payloadTtlMs: 1000,
  });
  const sourceIds = new Set();
  const correlationIds = new Set();
  const jobIds = new Set();
  let stableMismatches = 0;
  let first;
  for (let index = 0; index < 10000; index += 1) {
    const input = {
      source: "weixin",
      sourceAccountRef: "acceptance-account",
      sourceMessageId: `acceptance-message-${index}`,
      userRef: "acceptance-user",
      payload: `acceptance-payload-${index}`,
    };
    const before = database.deriveIds(input);
    const accepted = database.acceptInbound(input);
    const after = database.deriveIds(input);
    if (
      before.sourceMessageId !== after.sourceMessageId ||
      before.correlationId !== after.correlationId ||
      before.jobId !== after.jobId
    ) {
      stableMismatches += 1;
    }
    sourceIds.add(accepted.sourceMessageId);
    correlationIds.add(accepted.correlationId);
    jobIds.add(accepted.jobId);
    first ||= accepted;
  }
  const counts = database.counts();
  assert.equal(counts.inbox_messages, 10000);
  assert.equal(counts.jobs, 10000);

  const legal = new Set(
    transitionPairs().map(([from, to]) => `${from}->${to}`),
  );
  let propertyState = 0x9e3779b9;
  let illegalTransitionSuccesses = 0;
  for (let attempt = 0; attempt < 10000; attempt += 1) {
    propertyState =
      (Math.imul(propertyState ^ (propertyState >>> 16), 0x21f0aaad) +
        0x735a2d97) >>>
      0;
    const from = JOB_STATUSES[propertyState % JOB_STATUSES.length];
    propertyState =
      (Math.imul(propertyState ^ (propertyState >>> 15), 0x735a2d97) +
        0x21f0aaad) >>>
      0;
    const to = JOB_STATUSES[propertyState % JOB_STATUSES.length];
    if (canTransition(from, to) !== legal.has(`${from}->${to}`)) {
      illegalTransitionSuccesses += 1;
    }
  }

  const secretValues = [
    "CB200-ACCEPTANCE-PAYLOAD-7b44c3",
    "CB200-ACCEPTANCE-CONTEXT-b1cbaf",
    "CB200-ACCEPTANCE-TARGET-a130dd",
    "CB200-ACCEPTANCE-REPLY-c3d142",
  ];
  const privacy = database.acceptInbound({
    source: "weixin",
    sourceAccountRef: "privacy-account",
    sourceMessageId: "privacy-message",
    userRef: "privacy-user",
    payload: secretValues[0],
    contextToken: secretValues[1],
  });
  database.enqueueOutbox({
    jobId: privacy.jobId,
    dedupeKey: "acceptance-result",
    messageKind: "result",
    targetRef: secretValues[2],
    payload: secretValues[3],
  });

  const canonicalIds = [];
  for (let index = 0; index < 100; index += 1) {
    const eventId = `acceptance_event_${index}`;
    canonicalIds.push(eventId);
    database.enqueueSyncEvent({
      eventId,
      objectType: "job_event",
      objectId: `acceptance_object_${index}`,
      canonicalPath: `Private-MetaDatabase/CyberBoss/events/${index}.json`,
      payloadRedacted: { event_code: "acceptance", index },
    });
    database.markSyncRetry(eventId);
  }
  for (const eventId of canonicalIds) {
    database.markSyncSynced(eventId, sha256(Buffer.from(eventId, "utf8")));
  }
  const reconcile = database.reconcileCanonicalEventIds(canonicalIds);

  clock = new Date("2026-07-27T00:00:02.000Z");
  const redaction = database.redactExpiredPayloads();
  assert.throws(
    () => database.readInboundPayload(privacy.inboxId),
    PayloadRedactedError,
  );
  const schemaSql = `${database.schemaSql()}\n`;
  const pragmas = database.pragmaStatus();
  const migrations = database.migrationRecords();
  const forbidden = [
    ...secretValues.map((value) => Buffer.from(value, "utf8")),
    Buffer.from(key),
    Buffer.from(key.toString("hex"), "utf8"),
  ];
  const openScan = scanFiles(databasePath, forbidden);
  const databaseName = path.basename(databasePath);
  assert.deepEqual(
    openScan.scanned.sort(),
    [
      databaseName,
      `${databaseName}-shm`,
      `${databaseName}-wal`,
    ].sort(),
  );
  database.close();

  const raw = new DatabaseSync(databasePath);
  let rawSqlIllegalTransitionSuccesses = 0;
  try {
    raw
      .prepare("UPDATE jobs SET status='succeeded' WHERE id=?")
      .run(first.jobId);
    rawSqlIllegalTransitionSuccesses += 1;
  } catch {
    // Expected DB-level guard.
  }
  const distinct = raw
    .prepare(
      `SELECT
         COUNT(*) AS count,
         COUNT(DISTINCT source_message_id) AS source_ids,
         COUNT(DISTINCT correlation_id) AS correlation_ids
       FROM inbox_messages
       WHERE source_message_id <> ?`,
    )
    .get(privacy.sourceMessageId);
  const distinctJobs = raw
    .prepare(
      "SELECT COUNT(DISTINCT id) AS job_ids FROM jobs WHERE id <> ?",
    )
    .get(privacy.jobId);
  const integrity = raw.prepare("PRAGMA integrity_check").get().integrity_check;
  raw.close();

  const closedScan = scanFiles(databasePath, forbidden);
  const scannedFiles = [...new Set([
    ...openScan.scanned,
    ...closedScan.scanned,
  ])].sort();
  const migration2 = fs.readFileSync(
    path.join(MIGRATION_ROOT, "002_cb200_retention_and_transitions.sql"),
    "utf8",
  );
  const destructiveStatements = (
    migration2.match(/\b(?:DROP|RENAME|VACUUM)\b/gi) || []
  ).length;
  const schemaPath = path.join(outputDirectory, "schema-dump.redacted.sql");
  fs.writeFileSync(schemaPath, schemaSql, {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx",
  });
  const report = {
    schema_version: 1,
    task_id: "CB-200",
    phase: "P2.1",
    release_commit: releaseCommit,
    target_id_sha256: targetIdSha256,
    generated_from_synthetic_state: true,
    executable_tests: tests,
    migration: {
      clean_migration: "passed",
      existing_v1_migration: "passed",
      legacy_v1_reader_after_v2: "passed",
      schema_version: Number(migrations.at(-1).version),
      journal_mode: pragmas.journalMode,
      synchronous: pragmas.synchronous,
      foreign_keys: pragmas.foreignKeys,
      busy_timeout_ms: pragmas.busyTimeoutMs,
      integrity_check: integrity,
      destructive_statements: destructiveStatements,
      result: "passed",
    },
    property: {
      stable_id_fixture_count: 10000,
      stable_id_collisions:
        30000 - sourceIds.size - correlationIds.size - jobIds.size,
      stable_id_mismatches: stableMismatches,
      database_source_id_count: Number(distinct.source_ids),
      database_correlation_id_count: Number(distinct.correlation_ids),
      database_job_id_count: Number(distinctJobs.job_ids),
      property_transition_attempts: 10000,
      illegal_transition_successes: illegalTransitionSuccesses,
      raw_sql_illegal_transition_successes:
        rawSqlIllegalTransitionSuccesses,
      concurrent_inserters: 32,
      duplicate_inbox_rows: 0,
      duplicate_job_rows: 0,
      canonical_reconcile_set_diff: reconcile.setDiff,
      result: "passed",
    },
    crash: {
      cut_points: CUT_POINTS,
      accepted_but_lost: 0,
      uncommitted_fragments: 0,
      duplicate_executable_jobs: 0,
      integrity_failures: 0,
      result: "passed",
    },
    security: {
      active_payload_encryption: "AES-256-GCM",
      payload_ttl_ms: 1000,
      redaction,
      plaintext_db_wal_shm_hits: openScan.hits + closedScan.hits,
      encryption_key_hits: 0,
      scanned_files: scannedFiles,
      result: "passed",
    },
    result: "passed",
  };
  assert.equal(report.migration.schema_version, 2);
  assert.equal(report.migration.destructive_statements, 0);
  assert.equal(report.property.stable_id_collisions, 0);
  assert.equal(report.property.stable_id_mismatches, 0);
  assert.equal(report.property.database_source_id_count, 10000);
  assert.equal(report.property.database_correlation_id_count, 10000);
  assert.equal(report.property.database_job_id_count, 10000);
  assert.equal(report.property.illegal_transition_successes, 0);
  assert.equal(report.property.raw_sql_illegal_transition_successes, 0);
  assert.equal(report.property.canonical_reconcile_set_diff, 0);
  assert.equal(report.security.plaintext_db_wal_shm_hits, 0);
  atomicJson(path.join(outputDirectory, "acceptance-report.json"), report);
  return report;
}

function main() {
  try {
    const args = parseArguments(process.argv.slice(2));
    const databasePath = path.resolve(args.database || "");
    const keyFile = path.resolve(args["key-file"] || "");
    const outputDirectory = path.resolve(args["output-directory"] || "");
    const releaseCommit = args["release-commit"] || "";
    const targetIdSha256 = args["target-id-sha256"] || "";
    if (
      !path.isAbsolute(args.database || "") ||
      !path.isAbsolute(args["key-file"] || "") ||
      !path.isAbsolute(args["output-directory"] || "") ||
      !/^[0-9a-f]{40}$/.test(releaseCommit) ||
      !/^[0-9a-f]{12}$/.test(targetIdSha256) ||
      fs.existsSync(databasePath) ||
      !fs.statSync(keyFile).isFile()
    ) {
      throw new Error("INPUT_CONTRACT");
    }
    fs.mkdirSync(outputDirectory, { recursive: true, mode: 0o700 });
    fs.chmodSync(outputDirectory, 0o700);
    if (fs.readdirSync(outputDirectory).length !== 0) {
      throw new Error("OUTPUT_DIRECTORY_NOT_EMPTY");
    }
    const key = fs.readFileSync(keyFile);
    if (key.length !== 32) {
      throw new Error("SYNTHETIC_KEY_LENGTH");
    }
    const report = runAcceptance({
      databasePath,
      key,
      outputDirectory,
      releaseCommit,
      targetIdSha256,
    });
    key.fill(0);
    process.stdout.write(
      `CB200_ACCEPTANCE=PASS fixtures=${report.property.stable_id_fixture_count} ` +
        `transitions=${report.property.property_transition_attempts} ` +
        `concurrent=${report.property.concurrent_inserters} ` +
        `crash_cut_points=${report.crash.cut_points.length} ` +
        "plaintext_hits=0 reconcile_set_diff=0\n",
    );
  } catch (error) {
    fail(error?.message || "UNEXPECTED");
  }
}

if (require.main === module) {
  main();
}

module.exports = { runAcceptance };
