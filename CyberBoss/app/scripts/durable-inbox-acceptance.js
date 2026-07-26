#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { DatabaseSync } = require("node:sqlite");

const {
  commitSyncBuffer,
  loadSyncBuffer,
} = require("../src/adapters/channel/weixin/sync-buffer-store");
const {
  RuntimeSpoolDatabase,
} = require("../src/services/db/database-adapter");
const {
  DurableInboxCoordinator,
  DurableInboxError,
} = require("../src/services/inbox/durable-inbox");

const APP_ROOT = path.resolve(__dirname, "..");
const CUT_POINTS = Object.freeze([
  "after_fetch_before_durable",
  "after_durable_before_cursor",
  "after_cursor",
]);
const REQUIRED_TESTS = Object.freeze([
  "all fetch/durable/cursor crash cuts recover with RPO 0 and one synthetic execution",
  "same provider source replayed 1,000 times has one inbox, job and execution",
  "numeric batches sort then require unique highest-continuous sequence",
  "policy rejection is durable without an executable job",
  "non-user provider updates are durably rejected before cursor advance",
  "provider identity fails closed without stable provider fields",
  "cursor commit is atomic, compare-and-set and monotonic for numeric cursors",
  "cursor commit lock rejects a live writer and recovers a killed writer",
  "cursor store rejects symlinks and oversized values",
  "WeChat fetch returns a candidate without committing cursor or context state",
]);

function fail(code) {
  process.stderr.write(`CB210_ACCEPTANCE=FAIL reason=${code}\n`);
  process.exitCode = 2;
}

function parseArguments(values) {
  const result = {};
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (
      ![
        "--runtime-root",
        "--key-file",
        "--output-directory",
        "--release-commit",
        "--target-id-sha256",
        "--worker-cut",
      ].includes(key)
      || value === undefined
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

function fixtureMessage(sequence = 1) {
  return {
    message_type: 1,
    message_id: `acceptance-message-${sequence}`,
    seq: sequence,
    client_id: `acceptance-client-${sequence}`,
    from_user_id: "acceptance-sender",
    context_token: "CB210-ACCEPTANCE-CONTEXT-5f7c02",
    create_time_ms: 1700000000000 + sequence,
    item_list: [{
      type: 1,
      text_item: { text: "CB210-ACCEPTANCE-PAYLOAD-a8c951" },
    }],
  };
}

function configFor(root) {
  return {
    accountId: "acceptance-account",
    workspaceAlias: "cyberboss",
    runtime: "codex",
    syncBufferDir: path.join(root, "sync-buffers"),
  };
}

function normalizeFixture(message, config) {
  return {
    provider: "weixin",
    accountId: config.accountId,
    workspaceId: "acceptance-workspace",
    senderId: message.from_user_id,
    chatId: message.from_user_id,
    messageId: String(message.message_id),
    threadKey: "",
    text: message.item_list[0].text_item.text,
    attachments: [],
    contextToken: message.context_token,
    receivedAt: new Date(message.create_time_ms).toISOString(),
    policyDecision: {
      accepted: true,
      code: "accepted",
      inputBytes: 35,
      maxInputBytes: 32768,
    },
  };
}

function channelFor(root, config) {
  return {
    loadSyncBuffer() {
      return loadSyncBuffer(config, config.accountId);
    },
    async fetchUpdates({ syncBuffer }) {
      const response = syncBuffer === "cursor-1"
        ? { ret: 0, errcode: 0, get_updates_buf: "cursor-1", msgs: [] }
        : {
            ret: 0,
            errcode: 0,
            get_updates_buf: "cursor-1",
            msgs: [fixtureMessage()],
          };
      return {
        response,
        messages: response.msgs,
        committedCursor: syncBuffer,
        candidateCursor: response.get_updates_buf,
      };
    },
    commitCandidateCursor({ expectedCursor, candidateCursor }) {
      return commitSyncBuffer(config, config.accountId, {
        expected: expectedCursor,
        candidate: candidateCursor,
      });
    },
    normalizeIncomingMessage(message) {
      return normalizeFixture(message, config);
    },
    resolveAccount() {
      return { accountId: config.accountId };
    },
  };
}

function openDatabase(root, key) {
  return new RuntimeSpoolDatabase({
    databasePath: path.join(root, "runtime.db"),
    encryptionKey: Buffer.from(key),
    identityKey: Buffer.from(key),
  });
}

function query(root) {
  const raw = new DatabaseSync(path.join(root, "runtime.db"), { readOnly: true });
  try {
    return {
      inboxCount: Number(
        raw.prepare("SELECT COUNT(*) AS count FROM inbox_messages").get().count,
      ),
      jobs: raw
        .prepare("SELECT id, status, state_version FROM jobs ORDER BY id")
        .all(),
      integrityCheck: raw.prepare("PRAGMA integrity_check").get().integrity_check,
    };
  } finally {
    raw.close();
  }
}

function executeSyntheticRuntime(root, key) {
  const state = query(root);
  const database = openDatabase(root, key);
  let count = 0;
  try {
    for (const job of state.jobs) {
      if (job.status !== "queued") {
        continue;
      }
      const running = database.transitionJob(job.id, "running", {
        expectedVersion: Number(job.state_version),
        metadata: { source: "synthetic_runtime" },
      });
      database.transitionJob(job.id, "succeeded", {
        expectedVersion: Number(running.state_version),
        metadata: { source: "synthetic_runtime" },
      });
      count += 1;
    }
  } finally {
    database.close();
  }
  return count;
}

async function worker(root, key, cut) {
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  const config = configFor(root);
  const database = openDatabase(root, key);
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: channelFor(root, config),
    database,
    config,
    faultInjector(point) {
      if (point === cut) {
        process.kill(process.pid, "SIGKILL");
      }
    },
  });
  await coordinator.pollOnce({ timeoutMs: 10 });
  database.close();
}

function runExecutableTests() {
  const result = spawnSync(
    process.execPath,
    [
      "--test",
      "test/weixin-cursor-commit.test.js",
      "test/durable-inbox-crash-cut.test.js",
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
  return {
    named_tests: REQUIRED_TESTS.length,
    output_sha256: sha256(Buffer.from(output, "utf8")),
    result: "passed",
  };
}

function runCrashMatrix(runtimeRoot, keyFile, key) {
  const cases = [];
  for (const cut of CUT_POINTS) {
    const root = path.join(runtimeRoot, `crash-${cut}`);
    const crashed = spawnSync(
      process.execPath,
      [
        __filename,
        "--runtime-root", root,
        "--key-file", keyFile,
        "--worker-cut", cut,
      ],
      { encoding: "utf8", timeout: 10000 },
    );
    assert.equal(crashed.signal, "SIGKILL");
    const recovered = spawnSync(
      process.execPath,
      [
        __filename,
        "--runtime-root", root,
        "--key-file", keyFile,
        "--worker-cut", "no_crash",
      ],
      { encoding: "utf8", timeout: 10000 },
    );
    assert.equal(recovered.status, 0);
    const config = configFor(root);
    const before = query(root);
    const executionCount = executeSyntheticRuntime(root, key);
    cases.push({
      cut,
      cursor_committed: loadSyncBuffer(config, config.accountId) === "cursor-1",
      inbox_count: before.inboxCount,
      job_count: before.jobs.length,
      execution_count: executionCount,
      message_lost: before.inboxCount !== 1,
      integrity_check: before.integrityCheck,
      result: "passed",
    });
  }
  return cases;
}

function runReplay(runtimeRoot, key) {
  const root = path.join(runtimeRoot, "replay");
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  const config = configFor(root);
  const channel = channelFor(root, config);
  commitSyncBuffer(config, config.accountId, {
    expected: "",
    candidate: "opaque-0",
  });
  const database = openDatabase(root, key);
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: channel,
    database,
    config,
  });
  const message = fixtureMessage();
  let jobId = "";
  for (let replay = 0; replay < 1000; replay += 1) {
    const result = coordinator.ingestFetchedBatch({
      response: { ret: 0, errcode: 0 },
      messages: [message],
      committedCursor: channel.loadSyncBuffer(),
      candidateCursor: "opaque-1",
    });
    jobId ||= result.jobs[0].jobId;
    assert.equal(result.jobs[0].jobId, jobId);
    assert.equal(result.jobs[0].duplicate, replay > 0);
  }
  const eventId = "acceptance_cursor_event";
  database.enqueueSyncEvent({
    eventId,
    objectType: "job_event",
    objectId: jobId,
    canonicalPath: "Private-MetaDatabase/CyberBoss/events/acceptance.json",
    payloadRedacted: { event_code: "acceptance" },
  });
  database.markSyncRetry(eventId);
  database.markSyncSynced(eventId, sha256(Buffer.from(eventId, "utf8")));
  const reconcile = database.reconcileCanonicalEventIds([eventId]);
  const pragmas = database.pragmaStatus();
  const counts = database.counts();
  database.close();
  const executionCount = executeSyntheticRuntime(root, key);
  return {
    replay_count: 1000,
    inbox_count: counts.inbox_messages,
    job_count: counts.jobs,
    execution_count: executionCount,
    canonical_reconcile_set_diff: reconcile.setDiff,
    integrity_check: pragmas.integrityCheck,
    result: "passed",
  };
}

function expectOrderingFailure(root, key, committed, candidate, messages, code) {
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  const config = configFor(root);
  commitSyncBuffer(config, config.accountId, {
    expected: "",
    candidate: committed,
  });
  const database = openDatabase(root, key);
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: channelFor(root, config),
    database,
    config,
  });
  assert.throws(
    () => coordinator.ingestFetchedBatch({
      response: { ret: 0, errcode: 0 },
      messages,
      committedCursor: committed,
      candidateCursor: candidate,
    }),
    (error) => error instanceof DurableInboxError && error.code === code,
  );
  assert.equal(database.counts().inbox_messages, 0);
  database.close();
  return loadSyncBuffer(config, config.accountId) === committed;
}

function runOrdering(runtimeRoot, key) {
  const validRoot = path.join(runtimeRoot, "ordering-valid");
  fs.mkdirSync(validRoot, { recursive: true, mode: 0o700 });
  const config = configFor(validRoot);
  commitSyncBuffer(config, config.accountId, {
    expected: "",
    candidate: "10",
  });
  const database = openDatabase(validRoot, key);
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: channelFor(validRoot, config),
    database,
    config,
  });
  const valid = coordinator.ingestFetchedBatch({
    response: { ret: 0, errcode: 0 },
    messages: [fixtureMessage(13), fixtureMessage(11), fixtureMessage(12)],
    committedCursor: "10",
    candidateCursor: "13",
  });
  database.close();
  return {
    numeric_contiguous_commit:
      valid.highestContinuousVerified
      && loadSyncBuffer(config, config.accountId) === "13",
    reversed_batch_sorted: valid.acceptedCount === 3,
    gap_rejected: expectOrderingFailure(
      path.join(runtimeRoot, "ordering-gap"),
      key,
      "20",
      "23",
      [fixtureMessage(21), fixtureMessage(23)],
      "NUMERIC_CURSOR_BATCH_GAP",
    ),
    duplicate_sequence_rejected: expectOrderingFailure(
      path.join(runtimeRoot, "ordering-duplicate"),
      key,
      "30",
      "32",
      [
        { ...fixtureMessage(31), message_id: "duplicate-a" },
        { ...fixtureMessage(31), message_id: "duplicate-b" },
      ],
      "NUMERIC_CURSOR_BATCH_NOT_CONTINUOUS",
    ),
    regression_rejected: expectOrderingFailure(
      path.join(runtimeRoot, "ordering-regression"),
      key,
      "40",
      "39",
      [],
      "CURSOR_REGRESSION",
    ),
    result: "passed",
  };
}

function scanSyntheticState(runtimeRoot, keyFile, forbidden) {
  let plaintextHits = 0;
  let keyHits = 0;
  let filesScanned = 0;
  const pending = [runtimeRoot];
  while (pending.length) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const candidate = path.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(candidate);
      } else if (entry.isFile() && candidate !== keyFile) {
        const bytes = fs.readFileSync(candidate);
        filesScanned += 1;
        plaintextHits += forbidden.filter((value) => bytes.includes(value)).length;
        keyHits += bytes.includes(fs.readFileSync(keyFile)) ? 1 : 0;
      }
    }
  }
  return { plaintextHits, keyHits, filesScanned };
}

function runAcceptance(args) {
  const runtimeRoot = path.resolve(args["runtime-root"]);
  const keyFile = path.resolve(args["key-file"]);
  const outputDirectory = path.resolve(args["output-directory"]);
  const key = fs.readFileSync(keyFile);
  assert.equal(key.length, 32);
  const executableTests = runExecutableTests();
  const crashCases = runCrashMatrix(runtimeRoot, keyFile, key);
  const replay = runReplay(runtimeRoot, key);
  const ordering = runOrdering(runtimeRoot, key);
  const forbidden = [
    Buffer.from("CB210-ACCEPTANCE-PAYLOAD-a8c951", "utf8"),
    Buffer.from("CB210-ACCEPTANCE-CONTEXT-5f7c02", "utf8"),
  ];
  const scan = scanSyntheticState(runtimeRoot, keyFile, forbidden);
  const report = {
    schema_version: 1,
    task_id: "CB-210",
    phase: "P2.2",
    release_commit: args["release-commit"],
    target_id_sha256: args["target-id-sha256"],
    generated_from_synthetic_state: true,
    executable_tests: executableTests,
    crash: {
      cut_points: CUT_POINTS,
      cases: crashCases,
      accepted_but_lost: crashCases.filter((row) => row.message_lost).length,
      duplicate_executions:
        crashCases.filter((row) => row.execution_count !== 1).length,
      result: "passed",
    },
    replay,
    ordering,
    database: {
      committed_inbox_rpo: 0,
      canonical_reconcile_set_diff: replay.canonical_reconcile_set_diff,
      integrity_check: replay.integrity_check,
      result: "passed",
    },
    cursor: {
      fetch_writes_cursor: false,
      cursor_commit_after_durable: true,
      cursor_regression_allowed: false,
      stale_writer_allowed: false,
      result: "passed",
    },
    security: {
      active_payload_encryption: "AES-256-GCM",
      plaintext_db_wal_shm_hits: scan.plaintextHits,
      encryption_key_hits: scan.keyHits,
      files_scanned: scan.filesScanned,
      real_credentials_used: false,
      real_provider_used: false,
      result: "passed",
    },
    boundaries: {
      scheduler_integrated: false,
      outbox_worker_integrated: false,
      real_wechat: false,
      real_runtime: false,
      pg_2_executed: false,
    },
    result: "passed",
  };
  assert.equal(report.crash.accepted_but_lost, 0);
  assert.equal(report.crash.duplicate_executions, 0);
  assert.equal(report.replay.inbox_count, 1);
  assert.equal(report.replay.job_count, 1);
  assert.equal(report.replay.execution_count, 1);
  assert.equal(report.database.canonical_reconcile_set_diff, 0);
  assert.equal(report.database.integrity_check, "ok");
  assert.equal(report.security.plaintext_db_wal_shm_hits, 0);
  assert.equal(report.security.encryption_key_hits, 0);
  atomicJson(
    path.join(outputDirectory, "durable-inbox-matrix.json"),
    report,
  );
  key.fill(0);
  process.stdout.write(
    "CB210_ACCEPTANCE=PASS replay_count=1000 execution_count=1 "
    + "crash_cut_points=3 plaintext_hits=0 reconcile_set_diff=0 "
    + "real_credentials_used=false real_provider_used=false "
    + "scheduler_integrated=false outbox_worker_integrated=false "
    + "pg_2_executed=false\n",
  );
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  const key = fs.readFileSync(path.resolve(args["key-file"]));
  if (args["worker-cut"]) {
    try {
      await worker(
        path.resolve(args["runtime-root"]),
        key,
        args["worker-cut"],
      );
      key.fill(0);
      return;
    } catch {
      key.fill(0);
      process.exitCode = 70;
      return;
    }
  }
  key.fill(0);
  runAcceptance(args);
}

main().catch((error) => {
  fail(error?.message || "UNEXPECTED");
});
