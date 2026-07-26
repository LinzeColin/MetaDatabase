"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
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
  stableProviderMessageIdentity,
} = require("../src/services/inbox/durable-inbox");
const {
  DurableOutboxWorker,
} = require("../src/services/outbox/durable-outbox");

const FIXTURE_KEY = Buffer.from(
  "5d62ec7e99da044398b8f49535797033df92ad84577c88a86279b0a36e3ef2ee",
  "hex",
);
const CRASH_POINTS = [
  "after_fetch_before_durable",
  "after_durable_before_cursor",
  "after_cursor",
];

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb210-inbox-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function runtimeConfig(directory) {
  return {
    accountId: "fixture-account",
    workspaceAlias: "cyberboss",
    runtime: "codex",
    syncBufferDir: path.join(directory, "sync-buffers"),
  };
}

function fixtureMessage({
  sequence = 1,
  messageId = `fixture-message-${sequence}`,
  text = `fixture payload ${sequence}`,
  sender = "fixture-sender",
  policyAccepted = true,
} = {}) {
  return {
    message_type: 1,
    message_id: messageId,
    seq: sequence,
    client_id: `fixture-client-${sequence}`,
    from_user_id: sender,
    context_token: `fixture-context-${sequence}`,
    create_time_ms: 1700000000000 + sequence,
    item_list: [{ type: 1, text_item: { text } }],
    fixture_policy_accepted: policyAccepted,
  };
}

function normalizeFixture(message, config) {
  return {
    provider: "weixin",
    accountId: config.accountId,
    workspaceId: "fixture-workspace",
    senderId: message.from_user_id,
    chatId: message.from_user_id,
    messageId: String(message.message_id),
    threadKey: "",
    text: message.item_list[0].text_item.text,
    attachments: [],
    contextToken: message.context_token,
    receivedAt: new Date(message.create_time_ms).toISOString(),
    policyDecision: message.fixture_policy_accepted === false
      ? {
          accepted: false,
          code: "sender_not_allowed",
          inputBytes: 10,
          maxInputBytes: 32768,
        }
      : {
          accepted: true,
          code: "accepted",
          inputBytes: 10,
          maxInputBytes: 32768,
        },
  };
}

function createFixtureChannel({
  directory,
  config,
  responseFactory = null,
}) {
  return {
    loadSyncBuffer() {
      return loadSyncBuffer(config, config.accountId);
    },
    async fetchUpdates({ syncBuffer }) {
      const response = responseFactory
        ? responseFactory(syncBuffer)
        : syncBuffer === "cursor-1"
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

function openDatabase(directory) {
  return new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: Buffer.from(FIXTURE_KEY),
    identityKey: Buffer.from(FIXTURE_KEY),
  });
}

function queryState(directory) {
  const database = new DatabaseSync(
    path.join(directory, "runtime.db"),
    { readOnly: true },
  );
  try {
    const inboxCount = Number(
      database.prepare("SELECT COUNT(*) AS count FROM inbox_messages").get().count,
    );
    const jobs = database
      .prepare("SELECT id, status, state_version FROM jobs ORDER BY id")
      .all();
    return {
      inboxCount,
      jobs,
      integrityCheck: database.prepare("PRAGMA integrity_check").get().integrity_check,
    };
  } finally {
    database.close();
  }
}

function executeSyntheticRuntimeOnce(directory) {
  const before = queryState(directory);
  let executionCount = 0;
  const database = openDatabase(directory);
  try {
    for (const job of before.jobs) {
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
      executionCount += 1;
    }
  } finally {
    database.close();
  }
  return executionCount;
}

async function runCrashWorker(directory, cut) {
  const config = runtimeConfig(directory);
  const database = openDatabase(directory);
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: createFixtureChannel({ directory, config }),
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

if (process.argv[2] === "--crash-worker") {
  runCrashWorker(process.argv[3], process.argv[4]).catch(() => {
    process.exitCode = 70;
  });
} else {
  test("all fetch/durable/cursor crash cuts recover with RPO 0 and one synthetic execution", { timeout: 30000 }, (t) => {
    for (const cut of CRASH_POINTS) {
      const directory = temporaryDirectory(t);
      const crashed = spawnSync(
        process.execPath,
        [__filename, "--crash-worker", directory, cut],
        { encoding: "utf8", timeout: 10000 },
      );
      assert.equal(crashed.signal, "SIGKILL", `${cut}:${crashed.stderr}`);

      const recovered = spawnSync(
        process.execPath,
        [__filename, "--crash-worker", directory, "no_crash"],
        { encoding: "utf8", timeout: 10000 },
      );
      assert.equal(recovered.status, 0, `${cut}:${recovered.stderr}`);
      const config = runtimeConfig(directory);
      assert.equal(loadSyncBuffer(config, config.accountId), "cursor-1");
      const state = queryState(directory);
      assert.equal(state.inboxCount, 1);
      assert.equal(state.jobs.length, 1);
      assert.equal(state.jobs[0].status, "queued");
      assert.equal(state.integrityCheck, "ok");
      assert.equal(executeSyntheticRuntimeOnce(directory), 1);
      assert.equal(queryState(directory).jobs[0].status, "succeeded");
    }
  });

  test("same provider source replayed 1,000 times has one inbox, job and execution", { timeout: 30000 }, (t) => {
    const directory = temporaryDirectory(t);
    const config = runtimeConfig(directory);
    commitSyncBuffer(config, config.accountId, {
      expected: "",
      candidate: "opaque-0",
    });
    const channelAdapter = createFixtureChannel({ directory, config });
    const database = openDatabase(directory);
    const coordinator = new DurableInboxCoordinator({
      channelAdapter,
      database,
      config,
    });
    const message = fixtureMessage();
    let first = null;
    for (let replay = 0; replay < 1000; replay += 1) {
      const committedCursor = channelAdapter.loadSyncBuffer();
      const result = coordinator.ingestFetchedBatch({
        response: { ret: 0, errcode: 0 },
        messages: [message],
        committedCursor,
        candidateCursor: "opaque-1",
      });
      if (replay === 0) {
        first = result.jobs[0];
        assert.equal(first.duplicate, false);
      } else {
        assert.equal(result.jobs[0].duplicate, true);
        assert.equal(result.jobs[0].jobId, first.jobId);
      }
    }
    assert.deepEqual(database.counts(), {
      inbox_messages: 1,
      jobs: 1,
      job_events: 2,
      outbox_messages: 0,
      sync_spool: 0,
      service_state: 0,
    });
    database.close();
    assert.equal(executeSyntheticRuntimeOnce(directory), 1);
    assert.equal(queryState(directory).jobs[0].status, "succeeded");
  });

  test("accepted reply is staged before cursor commit and replay stays idempotent", async (t) => {
    const directory = temporaryDirectory(t);
    const config = runtimeConfig(directory);
    const channelAdapter = createFixtureChannel({ directory, config });
    const database = openDatabase(directory);
    let providerCalls = 0;
    const outboxWorker = new DurableOutboxWorker({
      database,
      channelAdapter: {
        async sendTextChunk({ clientId }) {
          providerCalls += 1;
          return {
            ret: 0,
            message_id: `accepted-${clientId}`,
          };
        },
      },
      autoSchedule: false,
    });
    let crashOnce = true;
    const coordinator = new DurableInboxCoordinator({
      channelAdapter,
      database,
      config,
      onAccepted({ accepted, normalized }) {
        outboxWorker.stageMessage({
          jobId: accepted.jobId,
          messageKind: "accepted",
          logicalKey: `accepted:${accepted.jobId}`,
          target: {
            userId: normalized.senderId,
            contextToken: normalized.contextToken,
          },
          text: `✅ Accepted\njob: ${accepted.jobId}`,
        });
      },
      faultInjector(point) {
        if (point === "after_accepted_outbox_before_cursor" && crashOnce) {
          crashOnce = false;
          throw new Error("synthetic accepted-outbox crash");
        }
      },
    });

    await assert.rejects(
      () => coordinator.pollOnce({ timeoutMs: 10 }),
      /synthetic accepted-outbox crash/,
    );
    assert.equal(channelAdapter.loadSyncBuffer(), "");
    assert.equal(database.counts().inbox_messages, 1);
    assert.equal(database.counts().jobs, 1);
    assert.equal(database.counts().outbox_messages, 1);
    assert.equal(database.listOutbox()[0].status, "pending");
    assert.equal(providerCalls, 0);

    const replay = await coordinator.pollOnce({ timeoutMs: 10 });
    assert.equal(replay.jobs[0].duplicate, true);
    assert.equal(channelAdapter.loadSyncBuffer(), "cursor-1");
    assert.equal(database.counts().outbox_messages, 1);
    assert.equal(providerCalls, 0);

    assert.deepEqual(await outboxWorker.runCycle(), {
      ambiguous: 0,
      confirmed: 1,
      processed: 1,
      retryScheduled: 0,
      terminal: 0,
    });
    assert.equal(database.listOutbox()[0].status, "confirmed");
    assert.equal(providerCalls, 1);
    database.close();
  });

  test("numeric batches sort then require unique highest-continuous sequence", (t) => {
    const validDirectory = temporaryDirectory(t);
    const validConfig = runtimeConfig(validDirectory);
    commitSyncBuffer(validConfig, validConfig.accountId, {
      expected: "",
      candidate: "10",
    });
    const validDatabase = openDatabase(validDirectory);
    const validChannel = createFixtureChannel({
      directory: validDirectory,
      config: validConfig,
    });
    const validCoordinator = new DurableInboxCoordinator({
      channelAdapter: validChannel,
      database: validDatabase,
      config: validConfig,
    });
    const valid = validCoordinator.ingestFetchedBatch({
      response: { ret: 0, errcode: 0 },
      messages: [
        fixtureMessage({ sequence: 13 }),
        fixtureMessage({ sequence: 11 }),
        fixtureMessage({ sequence: 12 }),
      ],
      committedCursor: "10",
      candidateCursor: "13",
    });
    assert.equal(valid.cursorKind, "numeric");
    assert.equal(valid.highestContinuousVerified, true);
    assert.equal(valid.acceptedCount, 3);
    assert.equal(validChannel.loadSyncBuffer(), "13");
    validDatabase.close();

    for (const fixture of [
      {
        name: "gap",
        committed: "20",
        candidate: "23",
        messages: [
          fixtureMessage({ sequence: 21 }),
          fixtureMessage({ sequence: 23 }),
        ],
        code: "NUMERIC_CURSOR_BATCH_GAP",
      },
      {
        name: "duplicate sequence",
        committed: "30",
        candidate: "32",
        messages: [
          fixtureMessage({ sequence: 31, messageId: "duplicate-a" }),
          fixtureMessage({ sequence: 31, messageId: "duplicate-b" }),
        ],
        code: "NUMERIC_CURSOR_BATCH_NOT_CONTINUOUS",
      },
      {
        name: "regression",
        committed: "40",
        candidate: "39",
        messages: [],
        code: "CURSOR_REGRESSION",
      },
    ]) {
      const directory = temporaryDirectory(t);
      const config = runtimeConfig(directory);
      commitSyncBuffer(config, config.accountId, {
        expected: "",
        candidate: fixture.committed,
      });
      const database = openDatabase(directory);
      const channel = createFixtureChannel({ directory, config });
      const coordinator = new DurableInboxCoordinator({
        channelAdapter: channel,
        database,
        config,
      });
      assert.throws(
        () => coordinator.ingestFetchedBatch({
          response: { ret: 0, errcode: 0 },
          messages: fixture.messages,
          committedCursor: fixture.committed,
          candidateCursor: fixture.candidate,
        }),
        (error) =>
          error instanceof DurableInboxError
          && error.code === fixture.code,
        fixture.name,
      );
      assert.equal(channel.loadSyncBuffer(), fixture.committed);
      assert.equal(database.counts().inbox_messages, 0);
      database.close();
    }
  });

  test("policy rejection is durable without an executable job", (t) => {
    const directory = temporaryDirectory(t);
    const config = runtimeConfig(directory);
    const channel = createFixtureChannel({ directory, config });
    const database = openDatabase(directory);
    const coordinator = new DurableInboxCoordinator({
      channelAdapter: channel,
      database,
      config,
    });
    const result = coordinator.ingestFetchedBatch({
      response: { ret: 0, errcode: 0 },
      messages: [fixtureMessage({ policyAccepted: false })],
      committedCursor: "",
      candidateCursor: "opaque-rejected",
    });
    assert.equal(result.rejectedCount, 1);
    assert.equal(result.acceptedCount, 0);
    assert.equal(database.counts().inbox_messages, 1);
    assert.equal(database.counts().jobs, 0);
    const inbox = database.getInbox(result.rejections[0].inboxId);
    assert.equal(inbox.status, "rejected");
    assert.equal(inbox.reject_reason, "sender_not_allowed");
    database.close();
  });

  test("non-user provider updates are durably rejected before cursor advance", (t) => {
    const directory = temporaryDirectory(t);
    const config = runtimeConfig(directory);
    const channel = createFixtureChannel({ directory, config });
    const database = openDatabase(directory);
    const coordinator = new DurableInboxCoordinator({
      channelAdapter: channel,
      database,
      config,
    });
    const message = {
      ...fixtureMessage(),
      message_type: 2,
      from_user_id: "",
      context_token: "",
    };
    const result = coordinator.ingestFetchedBatch({
      response: { ret: 0, errcode: 0 },
      messages: [message],
      committedCursor: "",
      candidateCursor: "opaque-non-user",
    });
    assert.equal(result.durableCount, 1);
    assert.equal(result.ignoredCount, 1);
    assert.equal(result.rejectedCount, 1);
    assert.equal(result.acceptedCount, 0);
    assert.equal(database.counts().inbox_messages, 1);
    assert.equal(database.counts().jobs, 0);
    assert.equal(
      database.getInbox(result.rejections[0].inboxId).reject_reason,
      "non_user_update",
    );
    assert.equal(channel.loadSyncBuffer(), "opaque-non-user");
    database.close();
  });

  test("provider identity fails closed without stable provider fields", () => {
    assert.throws(
      () => stableProviderMessageIdentity({
        message_type: 1,
        from_user_id: "fixture-sender",
      }),
      (error) =>
        error instanceof DurableInboxError
        && error.code === "STABLE_SOURCE_MESSAGE_ID_REQUIRED",
    );
    assert.equal(
      stableProviderMessageIdentity({
        message_id: "provider-id",
      }).kind,
      "message_id",
    );
  });
}
