"use strict";

const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const {
  RuntimeSpoolDatabase,
} = require("../src/services/db/database-adapter");
const {
  DurableOutboxWorker,
  TERMINAL_AUTH_ADVICE,
  computeBackoffDelayMs,
  reconstructDurableChunks,
  splitDurableText,
} = require("../src/services/outbox/durable-outbox");

const FIXTURE_KEY = Buffer.from(
  "62d5603eb175c7a86b254828509b145be58d49557a2503340844f20d55a7bf6c",
  "hex",
);

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb230-outbox-"));
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

function createJob(database, index, terminalStatus = "succeeded") {
  const accepted = database.acceptInbound({
    source: "weixin",
    sourceAccountRef: "fixture-account",
    sourceMessageId: `outbox-message-${index}`,
    userRef: "fixture-user",
    messageType: "text",
    payload: {
      provider: "weixin",
      accountId: "fixture-account",
      workspaceId: "fixture-workspace",
      senderId: "fixture-user",
      text: `fixture-${index}`,
    },
    contextToken: "fixture-context",
  });
  const running = database.transitionJob(accepted.jobId, "running", {
    expectedVersion: 2,
    metadata: { transition_code: "fixture_running" },
  });
  const terminal = database.transitionJob(accepted.jobId, terminalStatus, {
    expectedVersion: Number(running.state_version),
    metadata: { result_code: "fixture_terminal" },
  });
  return { ...accepted, terminal };
}

function crashError() {
  const error = new Error("simulated_process_crash");
  error.simulateProcessCrash = true;
  return error;
}

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

test("AC-020 crash before provider send resumes the committed row exactly once", async (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "before-send.db");
  let clock = new Date("2026-07-27T00:00:00.000Z");
  let providerCalls = 0;
  let database = openDatabase(databasePath, () => clock);
  const job = createJob(database, "before-send");
  const firstWorker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        providerCalls += 1;
        return { ret: 0, message_id: "unexpected" };
      },
    },
    now: () => clock,
    autoSchedule: false,
    faultInjector(point) {
      if (point === "after_claim_before_dispatch") {
        throw crashError();
      }
    },
  });
  const staged = firstWorker.stageMessage({
    jobId: job.jobId,
    messageKind: "result",
    logicalKey: "final",
    target: { userId: "fixture-user", contextToken: "fixture-context" },
    text: "durable result",
  });
  await assert.rejects(() => firstWorker.runCycle(), {
    message: "simulated_process_crash",
  });
  assert.equal(providerCalls, 0);
  assert.equal(database.getOutbox(staged.staged[0].id).status, "sending");
  assert.equal(
    database.getOutbox(staged.staged[0].id).dispatch_started_at,
    null,
  );
  database.close();

  database = openDatabase(databasePath, () => clock);
  const secondWorker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk({ clientId }) {
        providerCalls += 1;
        return { ret: 0, message_id: `receipt-${clientId}` };
      },
    },
    now: () => clock,
    autoSchedule: false,
  });
  const startup = await secondWorker.start();
  assert.deepEqual(startup.recovery, {
    inspected: 1,
    safeRetry: 1,
    ambiguousTerminal: 0,
    affectedJobs: 0,
  });
  assert.equal(providerCalls, 1);
  assert.equal(database.getOutbox(staged.staged[0].id).status, "confirmed");
  assert.equal(database.getJob(job.jobId).status, "replied");
  database.close();
});

test("post-provider pre-confirmation crash becomes ambiguous and is never replayed", async (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "ambiguous.db");
  const clock = new Date("2026-07-27T00:00:00.000Z");
  let providerCalls = 0;
  let database = openDatabase(databasePath, () => clock);
  const job = createJob(database, "ambiguous");
  const firstWorker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        providerCalls += 1;
        return { ret: 0, message_id: "provider-may-have-delivered" };
      },
    },
    now: () => clock,
    autoSchedule: false,
    faultInjector(point) {
      if (point === "after_provider_before_confirmation") {
        throw crashError();
      }
    },
  });
  const staged = firstWorker.stageMessage({
    jobId: job.jobId,
    messageKind: "result",
    logicalKey: "final",
    target: { userId: "fixture-user", contextToken: "fixture-context" },
    text: "ambiguous result",
  });
  await assert.rejects(() => firstWorker.runCycle(), {
    message: "simulated_process_crash",
  });
  assert.equal(providerCalls, 1);
  assert.ok(database.getOutbox(staged.staged[0].id).dispatch_started_at);
  database.close();

  database = openDatabase(databasePath, () => clock);
  const secondWorker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        providerCalls += 1;
        return { ret: 0 };
      },
    },
    now: () => clock,
    autoSchedule: false,
  });
  const startup = await secondWorker.start();
  assert.deepEqual(startup.recovery, {
    inspected: 1,
    safeRetry: 0,
    ambiguousTerminal: 1,
    affectedJobs: 1,
  });
  assert.equal(providerCalls, 1);
  const row = database.getOutbox(staged.staged[0].id);
  assert.equal(row.status, "failed_terminal");
  assert.equal(row.confirmation_state, "ambiguous");
  assert.equal(row.recovery_class, "manual_reconcile_required");
  assert.equal(database.getJob(job.jobId).status, "reply_failed");
  database.close();
});

test("confirmation-commit crash reconciles replied state without provider replay", async (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "confirmed-reconcile.db");
  const clock = new Date("2026-07-27T00:00:00.000Z");
  let providerCalls = 0;
  let database = openDatabase(databasePath, () => clock);
  const job = createJob(database, "confirmed-reconcile");
  const firstWorker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        providerCalls += 1;
        return { ret: 0, message_id: "confirmed-before-crash" };
      },
    },
    now: () => clock,
    autoSchedule: false,
    faultInjector(point) {
      if (point === "after_confirmation_commit") {
        throw crashError();
      }
    },
  });
  const staged = firstWorker.stageMessage({
    jobId: job.jobId,
    messageKind: "result",
    logicalKey: "final",
    target: { userId: "fixture-user", contextToken: "fixture-context" },
    text: "confirmed result",
  });
  await assert.rejects(() => firstWorker.runCycle(), {
    message: "simulated_process_crash",
  });
  assert.equal(providerCalls, 1);
  assert.equal(database.getOutbox(staged.staged[0].id).status, "confirmed");
  assert.equal(database.getJob(job.jobId).status, "reply_pending");
  database.close();

  database = openDatabase(databasePath, () => clock);
  const secondWorker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        providerCalls += 1;
        return { ret: 0, message_id: "forbidden-replay" };
      },
    },
    now: () => clock,
    autoSchedule: false,
  });
  const startup = await secondWorker.start();
  assert.deepEqual(startup.recovery, {
    inspected: 0,
    safeRetry: 0,
    ambiguousTerminal: 0,
    affectedJobs: 0,
  });
  assert.equal(providerCalls, 1);
  assert.equal(database.getOutbox(staged.staged[0].id).status, "confirmed");
  assert.equal(database.getJob(job.jobId).status, "replied");
  database.close();
});

test("AC-021 virtual clock retries two known 503 responses then confirms", async (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "retry.db");
  let clock = new Date("2026-07-27T00:00:00.000Z");
  const callTimes = [];
  const database = openDatabase(databasePath, () => clock);
  const job = createJob(database, "retry");
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        callTimes.push(clock.toISOString());
        if (callTimes.length <= 2) {
          const error = new Error("provider unavailable");
          error.status = 503;
          error.outcomeKnown = true;
          throw error;
        }
        return { ret: 0, message_id: "third-attempt-confirmed" };
      },
    },
    now: () => clock,
    random: () => 0.5,
    baseDelayMs: 1_000,
    maxDelayMs: 10_000,
    autoSchedule: false,
  });
  const staged = worker.stageMessage({
    jobId: job.jobId,
    messageKind: "result",
    logicalKey: "final",
    target: { userId: "fixture-user", contextToken: "fixture-context" },
    text: "retry result",
  });

  assert.deepEqual(await worker.runCycle(), {
    ambiguous: 0,
    confirmed: 0,
    processed: 1,
    retryScheduled: 1,
    terminal: 0,
  });
  assert.equal(
    database.getOutbox(staged.staged[0].id).next_attempt_at,
    "2026-07-27T00:00:01.000Z",
  );
  clock = new Date("2026-07-27T00:00:00.999Z");
  assert.equal((await worker.runCycle()).processed, 0);
  clock = new Date("2026-07-27T00:00:01.000Z");
  await worker.runCycle();
  assert.equal(
    database.getOutbox(staged.staged[0].id).next_attempt_at,
    "2026-07-27T00:00:03.000Z",
  );
  clock = new Date("2026-07-27T00:00:03.000Z");
  await worker.runCycle();

  const row = database.getOutbox(staged.staged[0].id);
  assert.equal(row.status, "confirmed");
  assert.equal(Number(row.attempt_count), 3);
  assert.equal(database.getJob(job.jobId).status, "replied");
  assert.deepEqual(callTimes, [
    "2026-07-27T00:00:00.000Z",
    "2026-07-27T00:00:01.000Z",
    "2026-07-27T00:00:03.000Z",
  ]);
  assert.deepEqual(
    database
      .listOutboxAttemptEvents(row.id)
      .map((event) => event.event_type),
    [
      "started",
      "retry_scheduled",
      "started",
      "retry_scheduled",
      "started",
      "confirmed",
    ],
  );
  database.close();
});

test("AC-022 replaying one outbox key 1,000 times yields one visible confirmation", { timeout: 60_000 }, async (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "replay.db");
  const clock = new Date("2026-07-27T00:00:00.000Z");
  let confirmedDeliveryCount = 0;
  const database = openDatabase(databasePath, () => clock);
  const job = createJob(database, "replay");
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk() {
        confirmedDeliveryCount += 1;
        return { ret: 0, message_id: "one-visible-result" };
      },
    },
    now: () => clock,
    autoSchedule: false,
  });
  const outboxIds = new Set();
  const clientIds = new Set();
  for (let index = 0; index < 1_000; index += 1) {
    const staged = worker.stageMessage({
      jobId: job.jobId,
      messageKind: "result",
      logicalKey: "stable-final",
      target: { userId: "fixture-user", contextToken: "fixture-context" },
      text: "stable result",
    });
    outboxIds.add(staged.staged[0].id);
    clientIds.add(staged.staged[0].provider_client_id);
  }
  assert.equal(outboxIds.size, 1);
  assert.equal(clientIds.size, 1);
  await worker.runCycle();
  await worker.runCycle();
  assert.equal(confirmedDeliveryCount, 1);
  assert.equal(database.outboxMetrics().confirmed, 1);
  database.close();
});

test("AC-024 permanent 401 is terminal and sends only fixed advice with a refreshed context", async (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "terminal-advice.db");
  const clock = new Date("2026-07-27T00:00:00.000Z");
  const calls = [];
  const database = openDatabase(databasePath, () => clock);
  const job = createJob(database, "terminal-advice");
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      getKnownContextTokens() {
        return { "fixture-user": "refreshed-context" };
      },
      async sendTextChunk(payload) {
        calls.push(payload);
        if (payload.contextToken === "expired-context") {
          const error = new Error(
            "raw-provider-detail-that-must-not-reach-user",
          );
          error.status = 401;
          error.outcomeKnown = true;
          throw error;
        }
        return { ret: 0, message_id: "advice-confirmed" };
      },
    },
    now: () => clock,
    autoSchedule: false,
  });
  worker.stageMessage({
    jobId: job.jobId,
    messageKind: "result",
    logicalKey: "final",
    target: { userId: "fixture-user", contextToken: "expired-context" },
    text: "private final result",
  });
  await worker.runCycle();

  assert.equal(calls.length, 2);
  assert.equal(calls[1].text, TERMINAL_AUTH_ADVICE);
  assert.doesNotMatch(
    calls[1].text,
    /raw-provider-detail|expired-context|private final/i,
  );
  assert.equal(calls[1].contextToken, "refreshed-context");
  assert.deepEqual(database.outboxMetrics(), {
    pending: 0,
    sending: 0,
    retry: 0,
    confirmed: 1,
    failedTerminal: 1,
    ambiguous: 0,
  });
  assert.equal(database.getJob(job.jobId).status, "reply_failed");
  database.close();
});

test("AC-025 deterministic long-result chunks are ordered and hash-reconstructable", async (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "chunks.db");
  const clock = new Date("2026-07-27T00:00:00.000Z");
  const sent = [];
  const database = openDatabase(databasePath, () => clock);
  const job = createJob(database, "chunks");
  const worker = new DurableOutboxWorker({
    database,
    channelAdapter: {
      async sendTextChunk(payload) {
        sent.push(payload);
        return {
          ret: 0,
          message_id: `chunk-${sent.length}`,
        };
      },
    },
    now: () => clock,
    maxChunkChars: 100,
    autoSchedule: false,
  });
  const source = "0123456789".repeat(30);
  const staged = worker.stageMessage({
    jobId: job.jobId,
    messageKind: "result",
    logicalKey: "long-final",
    target: { userId: "fixture-user", contextToken: "fixture-context" },
    text: source,
  });
  await worker.runCycle();

  assert.ok(staged.chunkCount >= 3);
  assert.deepEqual(
    staged.chunks.map((chunk) => chunk.index),
    Array.from({ length: staged.chunkCount }, (_, index) => index + 1),
  );
  assert.ok(sent.every((payload) => Array.from(payload.text).length <= 100));
  assert.equal(reconstructDurableChunks(staged.chunks), source);
  assert.equal(hash(reconstructDurableChunks(staged.chunks)), hash(source));
  assert.equal(new Set(sent.map((payload) => payload.clientId)).size, sent.length);
  assert.equal(database.getJob(job.jobId).status, "replied");
  database.close();
});

test("void response is ambiguous, stale owners are fenced and receipt rows are immutable", async (t) => {
  const directory = temporaryDirectory(t);
  const databasePath = path.join(directory, "truth.db");
  const clock = new Date("2026-07-27T00:00:00.000Z");
  let calls = 0;
  const database = openDatabase(databasePath, () => clock);
  const job = createJob(database, "truth");
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
  const staged = worker.stageMessage({
    jobId: job.jobId,
    messageKind: "result",
    logicalKey: "truth",
    target: { userId: "fixture-user", contextToken: "fixture-context" },
    text: "truthful result",
  });
  await worker.runCycle();
  assert.equal(calls, 1);
  const ambiguous = database.getOutbox(staged.staged[0].id);
  assert.equal(ambiguous.status, "failed_terminal");
  assert.equal(ambiguous.confirmation_state, "ambiguous");
  assert.equal(database.getJob(job.jobId).status, "reply_failed");

  const second = createJob(database, "fencing");
  const row = database.enqueueOutbox({
    jobId: second.jobId,
    dedupeKey: "fencing-row",
    messageKind: "result",
    targetRef: {
      userId: "fixture-user",
      contextToken: "fixture-context",
    },
    payload: "fencing",
  });
  const claim = database.claimNextOutbox({
    ownerId: "owner-one",
    leaseMs: 10_000,
  });
  assert.equal(claim.row.id, row.id);
  assert.throws(
    () =>
      database.markOutboxDispatchStarted(row.id, {
        ownerId: "owner-two",
      }),
    { code: "OUTBOX_DISPATCH_CONFLICT" },
  );
  database.markOutboxDispatchStarted(row.id, { ownerId: "owner-one" });
  const receiptHash = hash("fencing-receipt");
  database.markOutboxConfirmed(row.id, {
    ownerId: "owner-one",
    providerConfirmation: {
      confirmed: true,
      clientId: row.provider_client_id,
      receiptHash,
    },
  });
  database.close();

  const bypass = new DatabaseSync(databasePath);
  assert.throws(
    () =>
      bypass
        .prepare("UPDATE outbox_messages SET status='retry' WHERE id=?")
        .run(row.id),
    /confirmed_outbox_immutable/,
  );
  const event = bypass
    .prepare(
      "SELECT id FROM outbox_attempt_events WHERE event_type='confirmed' LIMIT 1",
    )
    .get();
  assert.throws(
    () =>
      bypass
        .prepare("UPDATE outbox_attempt_events SET error_class='tamper' WHERE id=?")
        .run(event.id),
    /immutable_outbox_attempt_event/,
  );
  bypass.close();
});

test("jittered backoff remains bounded without sleeping", () => {
  const low = computeBackoffDelayMs({
    attemptNumber: 4,
    baseDelayMs: 1_000,
    maxDelayMs: 10_000,
    jitterRatio: 0.2,
    random: () => 0,
  });
  const high = computeBackoffDelayMs({
    attemptNumber: 4,
    baseDelayMs: 1_000,
    maxDelayMs: 10_000,
    jitterRatio: 0.2,
    random: () => 1,
  });
  assert.equal(low, 6_400);
  assert.equal(high, 9_600);
  assert.equal(
    computeBackoffDelayMs({
      attemptNumber: 20,
      baseDelayMs: 1_000,
      maxDelayMs: 10_000,
      jitterRatio: 0.2,
      random: () => 1,
    }),
    10_000,
  );
  const chunks = splitDurableText("a".repeat(300), { maxChunkChars: 100 });
  assert.equal(reconstructDurableChunks(chunks), "a".repeat(300));
});
