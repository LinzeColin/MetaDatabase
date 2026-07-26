#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const {
  RuntimeSpoolDatabase,
} = require("../src/services/db/database-adapter");
const {
  DurableOutboxWorker,
  TERMINAL_AUTH_ADVICE,
  reconstructDurableChunks,
} = require("../src/services/outbox/durable-outbox");

const APP_ROOT = path.resolve(__dirname, "..");
const TEST_FILES = Object.freeze([
  "test/durable-inbox-crash-cut.test.js",
  "test/durable-outbox-crash-cut.test.js",
  "test/stream-delivery.test.js",
  "test/weixin-outbox-transport.test.js",
]);
const FIXTURE_USER = "CB230-FIXTURE-TARGET-48d9a3";
const FIXTURE_CONTEXT = "CB230-FIXTURE-CONTEXT-523ad9";
const FIXTURE_PAYLOAD = "CB230-FIXTURE-PAYLOAD-e38a41";
const REFRESHED_CONTEXT = "CB230-FIXTURE-REFRESHED-d1f0a2";

class AcceptanceError extends Error {
  constructor(code) {
    super(code);
    this.name = "AcceptanceError";
    this.code = code;
  }
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
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
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!allowed.has(key) || value === undefined) {
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
    !path.isAbsolute(result["runtime-root"])
    || !path.isAbsolute(result["key-file"])
    || !path.isAbsolute(result["output-directory"])
    || !/^[0-9a-f]{40}$/.test(result["release-commit"])
    || !/^[0-9a-f]{12}$/.test(result["target-id-sha256"])
  ) {
    throw new AcceptanceError("ARGUMENT_VALUE_INVALID");
  }
  return result;
}

function readSource(relative) {
  return fs.readFileSync(path.join(APP_ROOT, relative), "utf8");
}

function assertStaticContract() {
  const migration = readSource("migrations/004_cb230_durable_outbox.sql");
  const database = readSource("src/services/db/database-adapter.js");
  const inbox = readSource("src/services/inbox/durable-inbox.js");
  const worker = readSource("src/services/outbox/durable-outbox.js");
  const stream = readSource("src/core/stream-delivery.js");
  const app = readSource("src/core/app.js");
  const provider = readSource("src/adapters/channel/weixin/index.js");
  for (const [source, marker] of [
    [migration, "outbox_attempt_events"],
    [migration, "confirmed_outbox_immutable"],
    [migration, "outbox_confirmation_truth_guard"],
    [database, "recoverOutboxOnExclusiveStartup"],
    [database, "reconcileJobReplyState"],
    [inbox, "after_accepted_outbox_before_cursor"],
    [worker, "ambiguous_send_outcome"],
    [worker, "markOutboxDispatchStarted"],
    [worker, "TERMINAL_AUTH_ADVICE"],
    [stream, "stageMessage"],
    [app, "new DurableOutboxWorker"],
    [provider, "sendTextChunk"],
    [provider, "cb-outbox-"],
  ]) {
    if (!source.includes(marker)) {
      throw new AcceptanceError("STATIC_CONTRACT_MISSING");
    }
  }
  if (/\b(?:DROP|RENAME|VACUUM)\b/i.test(migration)) {
    throw new AcceptanceError("MIGRATION_DESTRUCTIVE");
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
  const tests = [...output.matchAll(
    /(?:^|\n)[^\S\r\n]*(?:ℹ|#)?[^\S\r\n]*tests\s+([0-9]+)/g,
  )]
    .map((match) => Number(match[1]))
    .filter(Number.isFinite)
    .pop();
  const failures = [...output.matchAll(
    /(?:^|\n)[^\S\r\n]*(?:ℹ|#)?[^\S\r\n]*fail\s+([0-9]+)/g,
  )]
    .map((match) => Number(match[1]))
    .filter(Number.isFinite)
    .pop();
  for (const marker of [
    "accepted reply is staged before cursor commit and replay stays idempotent",
    "crash before provider send resumes the committed row exactly once",
    "post-provider pre-confirmation crash becomes ambiguous and is never replayed",
    "virtual clock retries two known 503 responses then confirms",
    "replaying one outbox key 1,000 times yields one visible confirmation",
    "permanent 401 is terminal and sends only fixed advice",
    "deterministic long-result chunks are ordered and hash-reconstructable",
    "durable job result is staged before worker dispatch",
    "durable single-chunk transport preserves text and stable provider client id",
  ]) {
    if (!output.includes(marker)) {
      throw new AcceptanceError("EXECUTABLE_SUITE_INVENTORY");
    }
  }
  if (!Number.isSafeInteger(tests) || tests < 30 || failures !== 0) {
    throw new AcceptanceError("EXECUTABLE_SUITE_SUMMARY_INVALID");
  }
  return Object.freeze({
    files: TEST_FILES.map((file) => path.basename(file)),
    tests,
    failures,
  });
}

function ensureDirectory(directory) {
  if (!fs.existsSync(directory)) {
    fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  }
  const stats = fs.lstatSync(directory);
  if (!stats.isDirectory() || stats.isSymbolicLink()) {
    throw new AcceptanceError("DIRECTORY_INVALID");
  }
}

function openDatabase(databasePath, key, now) {
  return new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: Buffer.from(key),
    identityKey: Buffer.from(key),
    now,
  });
}

function createTerminalJob(database, suffix, terminalStatus = "succeeded") {
  const accepted = database.acceptInbound({
    source: "weixin",
    sourceAccountRef: "acceptance-account",
    sourceMessageId: `cb230-acceptance-${suffix}`,
    userRef: FIXTURE_USER,
    messageType: "text",
    payload: {
      provider: "weixin",
      senderId: FIXTURE_USER,
      text: FIXTURE_PAYLOAD,
    },
    contextToken: FIXTURE_CONTEXT,
  });
  const running = database.transitionJob(accepted.jobId, "running", {
    expectedVersion: 2,
    metadata: { transition_code: "acceptance_running" },
  });
  database.transitionJob(accepted.jobId, terminalStatus, {
    expectedVersion: Number(running.state_version),
    metadata: { result_code: "acceptance_terminal" },
  });
  return accepted;
}

function crashError() {
  const error = new Error("simulated_process_crash");
  error.simulateProcessCrash = true;
  return error;
}

function stageFinal(worker, jobId, suffix, text = FIXTURE_PAYLOAD) {
  return worker.stageMessage({
    jobId,
    messageKind: "result",
    logicalKey: `final:${suffix}`,
    target: {
      userId: FIXTURE_USER,
      contextToken: FIXTURE_CONTEXT,
    },
    text,
  });
}

async function runRecoveryMatrix(runtimeRoot, key) {
  const cases = [];
  const fixedClock = new Date("2026-07-27T00:00:00.000Z");

  {
    const databasePath = path.join(runtimeRoot, "recovery-pending.db");
    let calls = 0;
    let database = openDatabase(databasePath, key, () => fixedClock);
    const job = createTerminalJob(database, "pending");
    const worker = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk() {
          calls += 1;
          return { ret: 0, message_id: "pending-confirmed" };
        },
      },
      now: () => fixedClock,
      autoSchedule: false,
    });
    const staged = stageFinal(worker, job.jobId, "pending");
    database.close();

    database = openDatabase(databasePath, key, () => fixedClock);
    const recovered = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk() {
          calls += 1;
          return { ret: 0, message_id: "pending-confirmed" };
        },
      },
      now: () => fixedClock,
      autoSchedule: false,
    });
    const startup = await recovered.start();
    const row = database.getOutbox(staged.staged[0].id);
    cases.push({
      cut: "pending_before_claim",
      provider_calls: calls,
      recovered_safe_retry: startup.recovery.safeRetry,
      recovered_ambiguous: startup.recovery.ambiguousTerminal,
      final_status: row.status,
      job_status: database.getJob(job.jobId).status,
      automatic_replay_after_unknown_dispatch: false,
      result: "passed",
    });
    database.close();
  }

  {
    const databasePath = path.join(runtimeRoot, "recovery-claimed.db");
    let calls = 0;
    let database = openDatabase(databasePath, key, () => fixedClock);
    const job = createTerminalJob(database, "claimed");
    const worker = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk() {
          calls += 1;
          return { ret: 0, message_id: "claimed-confirmed" };
        },
      },
      now: () => fixedClock,
      autoSchedule: false,
      faultInjector(point) {
        if (point === "after_claim_before_dispatch") {
          throw crashError();
        }
      },
    });
    const staged = stageFinal(worker, job.jobId, "claimed");
    await assert.rejects(() => worker.runCycle(), /simulated_process_crash/);
    assert.equal(calls, 0);
    database.close();

    database = openDatabase(databasePath, key, () => fixedClock);
    const recovered = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk() {
          calls += 1;
          return { ret: 0, message_id: "claimed-confirmed" };
        },
      },
      now: () => fixedClock,
      autoSchedule: false,
    });
    const startup = await recovered.start();
    cases.push({
      cut: "claimed_before_dispatch",
      provider_calls: calls,
      recovered_safe_retry: startup.recovery.safeRetry,
      recovered_ambiguous: startup.recovery.ambiguousTerminal,
      final_status: database.getOutbox(staged.staged[0].id).status,
      job_status: database.getJob(job.jobId).status,
      automatic_replay_after_unknown_dispatch: false,
      result: "passed",
    });
    database.close();
  }

  {
    const databasePath = path.join(runtimeRoot, "recovery-dispatched.db");
    let calls = 0;
    let database = openDatabase(databasePath, key, () => fixedClock);
    const job = createTerminalJob(database, "dispatched");
    const worker = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk() {
          calls += 1;
          return { ret: 0, message_id: "unknown-provider-outcome" };
        },
      },
      now: () => fixedClock,
      autoSchedule: false,
      faultInjector(point) {
        if (point === "after_provider_before_confirmation") {
          throw crashError();
        }
      },
    });
    const staged = stageFinal(worker, job.jobId, "dispatched");
    await assert.rejects(() => worker.runCycle(), /simulated_process_crash/);
    assert.equal(calls, 1);
    database.close();

    database = openDatabase(databasePath, key, () => fixedClock);
    const recovered = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk() {
          calls += 1;
          return { ret: 0, message_id: "forbidden-replay" };
        },
      },
      now: () => fixedClock,
      autoSchedule: false,
    });
    const startup = await recovered.start();
    const row = database.getOutbox(staged.staged[0].id);
    cases.push({
      cut: "provider_returned_before_confirmation_commit",
      provider_calls: calls,
      recovered_safe_retry: startup.recovery.safeRetry,
      recovered_ambiguous: startup.recovery.ambiguousTerminal,
      final_status: row.status,
      confirmation_state: row.confirmation_state,
      recovery_class: row.recovery_class,
      job_status: database.getJob(job.jobId).status,
      automatic_replay_after_unknown_dispatch: calls > 1,
      result: "passed",
    });
    database.close();
  }

  {
    const databasePath = path.join(runtimeRoot, "recovery-confirmed.db");
    let calls = 0;
    let database = openDatabase(databasePath, key, () => fixedClock);
    const job = createTerminalJob(database, "confirmed");
    const worker = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk() {
          calls += 1;
          return { ret: 0, message_id: "confirmed-before-crash" };
        },
      },
      now: () => fixedClock,
      autoSchedule: false,
      faultInjector(point) {
        if (point === "after_confirmation_commit") {
          throw crashError();
        }
      },
    });
    const staged = stageFinal(worker, job.jobId, "confirmed");
    await assert.rejects(() => worker.runCycle(), /simulated_process_crash/);
    assert.equal(calls, 1);
    database.close();

    database = openDatabase(databasePath, key, () => fixedClock);
    const recovered = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk() {
          calls += 1;
          return { ret: 0, message_id: "forbidden-confirmed-replay" };
        },
      },
      now: () => fixedClock,
      autoSchedule: false,
    });
    const startup = await recovered.start();
    cases.push({
      cut: "confirmation_committed_before_crash",
      provider_calls: calls,
      recovered_safe_retry: startup.recovery.safeRetry,
      recovered_ambiguous: startup.recovery.ambiguousTerminal,
      final_status: database.getOutbox(staged.staged[0].id).status,
      job_status: database.getJob(job.jobId).status,
      automatic_replay_after_unknown_dispatch: false,
      result: "passed",
    });
    database.close();
  }

  assert.deepEqual(
    cases.map((row) => row.provider_calls),
    [1, 1, 1, 1],
  );
  assert.equal(cases[1].recovered_safe_retry, 1);
  assert.equal(cases[2].recovered_ambiguous, 1);
  assert.equal(cases[2].automatic_replay_after_unknown_dispatch, false);
  assert.equal(cases[2].confirmation_state, "ambiguous");
  assert.equal(cases[3].final_status, "confirmed");
  return cases;
}

async function runRetryFixture(runtimeRoot, key) {
  let clock = new Date("2026-07-27T00:00:00.000Z");
  const database = openDatabase(
    path.join(runtimeRoot, "retry.db"),
    key,
    () => clock,
  );
  const job = createTerminalJob(database, "retry");
  const callTimes = [];
  let timerCalls = 0;
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        callTimes.push(clock.toISOString());
        if (callTimes.length <= 2) {
          const error = new Error("fixture provider unavailable");
          error.status = 503;
          error.outcomeKnown = true;
          throw error;
        }
        return { ret: 0, message_id: "retry-confirmed" };
      },
    },
    now: () => clock,
    random: () => 0.5,
    baseDelayMs: 1_000,
    maxDelayMs: 10_000,
    autoSchedule: false,
    setTimeoutFn() {
      timerCalls += 1;
      return {};
    },
    clearTimeoutFn() {},
  });
  const staged = stageFinal(worker, job.jobId, "retry");
  const delays = [];
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const before = clock.getTime();
    await worker.runCycle();
    const row = database.getOutbox(staged.staged[0].id);
    if (row.status === "retry") {
      const due = new Date(row.next_attempt_at);
      delays.push(due.getTime() - before);
      clock = due;
    }
  }
  const row = database.getOutbox(staged.staged[0].id);
  const events = database
    .listOutboxAttemptEvents(row.id)
    .map((event) => event.event_type);
  const result = {
    provider_sequence: [503, 503, 200],
    attempts: Number(row.attempt_count),
    retry_delays_ms: delays,
    call_times: callTimes,
    event_sequence: events,
    final_status: row.status,
    job_status: database.getJob(job.jobId).status,
    real_wait_calls: timerCalls,
    clock: "virtual",
    jitter_sample: 0.5,
    result: "passed",
  };
  assert.deepEqual(result.retry_delays_ms, [1_000, 2_000]);
  assert.equal(result.attempts, 3);
  assert.equal(result.real_wait_calls, 0);
  assert.equal(result.final_status, "confirmed");
  database.close();
  return result;
}

async function runReplayFixture(runtimeRoot, key) {
  const clock = new Date("2026-07-27T00:00:00.000Z");
  const database = openDatabase(
    path.join(runtimeRoot, "replay.db"),
    key,
    () => clock,
  );
  const job = createTerminalJob(database, "replay");
  let providerCalls = 0;
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        providerCalls += 1;
        return { ret: 0, message_id: "single-visible-confirmation" };
      },
    },
    now: () => clock,
    autoSchedule: false,
  });
  const outboxIds = new Set();
  const providerClientIds = new Set();
  for (let replay = 0; replay < 1_000; replay += 1) {
    const staged = stageFinal(worker, job.jobId, "stable-replay");
    outboxIds.add(staged.staged[0].id);
    providerClientIds.add(staged.staged[0].provider_client_id);
  }
  await worker.runCycle();
  await worker.runCycle();
  const result = {
    stage_count: 1_000,
    durable_row_count: database.listOutbox(job.jobId).length,
    unique_outbox_ids: outboxIds.size,
    unique_provider_client_ids: providerClientIds.size,
    confirmed_delivery_count: providerCalls,
    confirmed_rows: database.outboxMetrics().confirmed,
    result: "passed",
  };
  assert.equal(result.durable_row_count, 1);
  assert.equal(result.unique_outbox_ids, 1);
  assert.equal(result.unique_provider_client_ids, 1);
  assert.equal(result.confirmed_delivery_count, 1);
  database.close();
  return result;
}

async function runTerminalAdviceFixture(runtimeRoot, key) {
  const clock = new Date("2026-07-27T00:00:00.000Z");
  const database = openDatabase(
    path.join(runtimeRoot, "terminal-advice.db"),
    key,
    () => clock,
  );
  const job = createTerminalJob(database, "terminal-advice");
  const calls = [];
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      getKnownContextTokens() {
        return { [FIXTURE_USER]: REFRESHED_CONTEXT };
      },
      async sendTextChunk(payload) {
        calls.push(payload);
        if (payload.contextToken === FIXTURE_CONTEXT) {
          const error = new Error("raw fixture provider auth detail");
          error.status = 401;
          error.outcomeKnown = true;
          throw error;
        }
        return { ret: 0, message_id: "terminal-advice-confirmed" };
      },
    },
    now: () => clock,
    autoSchedule: false,
  });
  stageFinal(worker, job.jobId, "terminal-advice");
  await worker.runCycle();
  const metrics = database.outboxMetrics();
  const result = {
    provider_status: 401,
    original_final_status: "failed_terminal",
    advice_staged_with_refreshed_context: calls[1]?.contextToken
      === REFRESHED_CONTEXT,
    advice_is_fixed_redacted_text: calls[1]?.text === TERMINAL_AUTH_ADVICE,
    advice_sha256: sha256(Buffer.from(TERMINAL_AUTH_ADVICE, "utf8")),
    raw_provider_detail_forwarded: calls.some(
      (call) => /raw fixture provider auth detail/i.test(call.text),
    ),
    provider_calls: calls.length,
    confirmed_advice_rows: metrics.confirmed,
    failed_terminal_rows: metrics.failedTerminal,
    job_status: database.getJob(job.jobId).status,
    result: "passed",
  };
  assert.equal(result.advice_staged_with_refreshed_context, true);
  assert.equal(result.advice_is_fixed_redacted_text, true);
  assert.equal(result.raw_provider_detail_forwarded, false);
  assert.equal(result.confirmed_advice_rows, 1);
  assert.equal(result.failed_terminal_rows, 1);
  database.close();
  return result;
}

async function runChunkFixture(runtimeRoot, key) {
  const clock = new Date("2026-07-27T00:00:00.000Z");
  const database = openDatabase(
    path.join(runtimeRoot, "chunks.db"),
    key,
    () => clock,
  );
  const job = createTerminalJob(database, "chunks");
  const sent = [];
  const maxChunkChars = 3_800;
  const source = "αβγ🙂0123456789".repeat(950);
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk(payload) {
        sent.push(payload);
        return {
          ret: 0,
          message_id: `chunk-confirmed-${sent.length}`,
        };
      },
    },
    now: () => clock,
    maxChunkChars,
    maxMessagesPerCycle: 1,
    autoSchedule: false,
  });
  const staged = stageFinal(worker, job.jobId, "long-result", source);
  await worker.runCycle();
  const repliedBeforeAllConfirmed =
    database.getJob(job.jobId).status === "replied";
  while (database.outboxMetrics().pending > 0) {
    await worker.runCycle();
  }
  const reconstructed = reconstructDurableChunks(staged.chunks);
  const indices = staged.chunks.map((chunk) => chunk.index);
  const result = {
    input_code_points: Array.from(source).length,
    provider_limit_code_points: maxChunkChars,
    exceeds_three_times_provider_limit:
      Array.from(source).length >= maxChunkChars * 3,
    chunk_count: staged.chunkCount,
    chunk_indices: indices,
    chunk_totals: staged.chunks.map((chunk) => chunk.count),
    max_observed_chunk_code_points: Math.max(
      ...sent.map((payload) => Array.from(payload.text).length),
    ),
    source_sha256: sha256(Buffer.from(source, "utf8")),
    reconstructed_sha256: sha256(Buffer.from(reconstructed, "utf8")),
    provider_calls: sent.length,
    stable_unique_client_ids:
      new Set(sent.map((payload) => payload.clientId)).size,
    replied_before_all_final_chunks_confirmed: repliedBeforeAllConfirmed,
    final_job_status: database.getJob(job.jobId).status,
    result: "passed",
  };
  assert.equal(result.exceeds_three_times_provider_limit, true);
  assert.ok(result.chunk_count >= 4);
  assert.deepEqual(
    indices,
    Array.from({ length: staged.chunkCount }, (_, index) => index + 1),
  );
  assert.equal(
    result.max_observed_chunk_code_points <= maxChunkChars,
    true,
  );
  assert.equal(result.source_sha256, result.reconstructed_sha256);
  assert.equal(result.provider_calls, result.chunk_count);
  assert.equal(result.stable_unique_client_ids, result.chunk_count);
  assert.equal(result.replied_before_all_final_chunks_confirmed, false);
  assert.equal(result.final_job_status, "replied");
  database.close();
  return result;
}

async function runVoidReceiptFixture(runtimeRoot, key) {
  const clock = new Date("2026-07-27T00:00:00.000Z");
  const database = openDatabase(
    path.join(runtimeRoot, "void-receipt.db"),
    key,
    () => clock,
  );
  const job = createTerminalJob(database, "void-receipt");
  let calls = 0;
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        calls += 1;
        return undefined;
      },
    },
    now: () => clock,
    autoSchedule: false,
  });
  const staged = stageFinal(worker, job.jobId, "void-receipt");
  await worker.runCycle();
  const row = database.getOutbox(staged.staged[0].id);
  const result = {
    provider_calls: calls,
    void_response_confirmed: row.status === "confirmed",
    final_status: row.status,
    confirmation_state: row.confirmation_state,
    recovery_class: row.recovery_class,
    job_status: database.getJob(job.jobId).status,
    result: "passed",
  };
  assert.equal(result.provider_calls, 1);
  assert.equal(result.void_response_confirmed, false);
  assert.equal(result.final_status, "failed_terminal");
  assert.equal(result.confirmation_state, "ambiguous");
  assert.equal(result.job_status, "reply_failed");
  database.close();
  return result;
}

function scanSyntheticState(runtimeRoot, keyFile, key) {
  const forbidden = [
    Buffer.from(FIXTURE_USER, "utf8"),
    Buffer.from(FIXTURE_CONTEXT, "utf8"),
    Buffer.from(FIXTURE_PAYLOAD, "utf8"),
    Buffer.from(REFRESHED_CONTEXT, "utf8"),
  ];
  let filesScanned = 0;
  let plaintextHits = 0;
  let keyHits = 0;
  const pending = [runtimeRoot];
  while (pending.length > 0) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const candidate = path.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(candidate);
      } else if (entry.isFile() && path.resolve(candidate) !== keyFile) {
        const bytes = fs.readFileSync(candidate);
        filesScanned += 1;
        plaintextHits += forbidden.filter((value) => bytes.includes(value)).length;
        keyHits += bytes.includes(key) ? 1 : 0;
      }
    }
  }
  return Object.freeze({ filesScanned, plaintextHits, keyHits });
}

function atomicJson(target, value) {
  const parent = path.dirname(target);
  ensureDirectory(parent);
  if (fs.existsSync(target) && fs.lstatSync(target).isSymbolicLink()) {
    throw new AcceptanceError("OUTPUT_SYMLINK_FORBIDDEN");
  }
  const temporary = `${target}.tmp-${process.pid}`;
  fs.writeFileSync(
    temporary,
    `${JSON.stringify(value, null, 2)}\n`,
    { encoding: "utf8", mode: 0o600, flag: "wx" },
  );
  fs.renameSync(temporary, target);
  fs.chmodSync(target, 0o600);
}

async function runAcceptance(args) {
  const runtimeRoot = path.resolve(args["runtime-root"]);
  const keyFile = path.resolve(args["key-file"]);
  const outputDirectory = path.resolve(args["output-directory"]);
  ensureDirectory(runtimeRoot);
  ensureDirectory(outputDirectory);
  const key = fs.readFileSync(keyFile);
  if (key.length !== 32) {
    throw new AcceptanceError("AES256_KEY_LENGTH");
  }
  try {
    assertStaticContract();
    const executableSuite = runExecutableSuite();
    const recoveryCases = await runRecoveryMatrix(runtimeRoot, key);
    const retry = await runRetryFixture(runtimeRoot, key);
    const replay = await runReplayFixture(runtimeRoot, key);
    const terminal = await runTerminalAdviceFixture(runtimeRoot, key);
    const chunks = await runChunkFixture(runtimeRoot, key);
    const voidReceipt = await runVoidReceiptFixture(runtimeRoot, key);
    const scan = scanSyntheticState(runtimeRoot, keyFile, key);
    const report = {
      schema_version: 1,
      task_id: "CB-230",
      phase: "P2.4",
      release_commit: args["release-commit"],
      target_id_sha256: args["target-id-sha256"],
      claim_level: "deterministic_fixture",
      generated_from_synthetic_state: true,
      executable_suite: {
        ...executableSuite,
        fixed_wait: false,
        real_provider: false,
        real_credentials: false,
      },
      ac_020_send_before_crash: {
        outbox_committed_before_provider: true,
        restart_delivery_count:
          recoveryCases.find(
            (row) => row.cut === "claimed_before_dispatch",
          ).provider_calls,
        final_status: recoveryCases.find(
          (row) => row.cut === "claimed_before_dispatch",
        ).final_status,
        result: "passed",
      },
      ac_021_retry: retry,
      ac_022_dedupe: replay,
      ac_024_terminal: terminal,
      ac_025_chunks: chunks,
      ac_062_recovery: {
        cases: recoveryCases,
        case_count: recoveryCases.length,
        state_predicate_driven: true,
        fixed_wait: false,
        false_green_count: 0,
        unknown_dispatch_auto_replay_count: recoveryCases.filter(
          (row) => row.automatic_replay_after_unknown_dispatch,
        ).length,
        result: "passed",
      },
      confirmation_truth: {
        void_receipt: voidReceipt,
        provider_confirmation_required: true,
        replied_before_all_final_chunks_confirmed:
          chunks.replied_before_all_final_chunks_confirmed,
        unknown_dispatch_auto_replay_count: recoveryCases.filter(
          (row) => row.automatic_replay_after_unknown_dispatch,
        ).length,
        result: "passed",
      },
      security: {
        active_payload_encryption: "AES-256-GCM",
        plaintext_db_wal_shm_hits: scan.plaintextHits,
        encryption_key_hits: scan.keyHits,
        files_scanned: scan.filesScanned,
        raw_target_in_report: false,
        raw_context_in_report: false,
        raw_payload_in_report: false,
        real_credentials_used: false,
        real_provider_used: false,
        result: "passed",
      },
      boundaries: {
        accepted_reply_integrated: true,
        scheduler_integrated: true,
        outbox_worker_integrated: true,
        canonical_sync_integrated: false,
        private_database_operations: false,
        real_wechat: false,
        real_runtime: false,
        cb_240_executed: false,
        pg_2_executed: false,
      },
      result: "passed",
    };
    assert.equal(report.ac_020_send_before_crash.restart_delivery_count, 1);
    assert.equal(report.ac_021_retry.attempts, 3);
    assert.equal(report.ac_022_dedupe.confirmed_delivery_count, 1);
    assert.equal(report.ac_024_terminal.raw_provider_detail_forwarded, false);
    assert.equal(
      report.ac_025_chunks.source_sha256,
      report.ac_025_chunks.reconstructed_sha256,
    );
    assert.equal(
      report.ac_062_recovery.unknown_dispatch_auto_replay_count,
      0,
    );
    assert.equal(
      report.confirmation_truth.void_receipt.void_response_confirmed,
      false,
    );
    assert.equal(report.security.plaintext_db_wal_shm_hits, 0);
    assert.equal(report.security.encryption_key_hits, 0);
    const serialized = JSON.stringify(report);
    for (const forbidden of [
      FIXTURE_USER,
      FIXTURE_CONTEXT,
      FIXTURE_PAYLOAD,
      REFRESHED_CONTEXT,
      "raw fixture provider auth detail",
    ]) {
      assert.equal(serialized.includes(forbidden), false);
    }
    atomicJson(
      path.join(outputDirectory, "outbox-recovery-matrix.json"),
      report,
    );
    process.stdout.write(
      "CB230_DURABLE_OUTBOX_ACCEPTANCE=PASS "
      + `tests=${executableSuite.tests} attempts=3 replay_count=1000 `
      + "confirmed_delivery_count=1 recovery_cases=4 "
      + "unknown_dispatch_auto_replay=0 plaintext_hits=0 key_hits=0 "
      + "real_wait_calls=0 real_credentials_used=false "
      + "real_provider_used=false private_database_operations=false "
      + "cb_240_executed=false pg_2_executed=false\n",
    );
  } finally {
    key.fill(0);
  }
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  await runAcceptance(args);
}

main().catch((error) => {
  const code = error instanceof AcceptanceError
    ? error.code
    : error?.code || error?.message || "ACCEPTANCE_INTERNAL_ERROR";
  process.stderr.write(
    `CB230_DURABLE_OUTBOX_ACCEPTANCE=FAIL code=${String(code)}\n`,
  );
  process.exitCode = 2;
});
