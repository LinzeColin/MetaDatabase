const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { createInboundFilter } = require("../src/adapters/channel/weixin/message-utils");
const { CyberbossApp } = require("../src/core/app");
const { StreamDelivery } = require("../src/core/stream-delivery");
const {
  TRACE_STAGE_ORDER,
  WalkingSkeletonTraceStore,
} = require("../src/core/walking-skeleton-trace");

function inboundMessage({ id, senderId, text }) {
  return {
    seq: Number(id),
    message_id: String(id),
    client_id: `client-${id}`,
    from_user_id: senderId,
    message_type: 1,
    create_time_ms: 1_700_000_000_000 + Number(id),
    session_id: "fixture-session",
    context_token: `context-${id}`,
    item_list: [{ type: 1, text_item: { text } }],
  };
}

function filterConfig() {
  return {
    workspaceId: "default",
    allowedUserIds: ["authorized-user"],
    maxInputBytes: 32 * 1024,
  };
}

test("inbound policy rejects unauthorized and 32KiB+1 before Runtime eligibility", () => {
  const filter = createInboundFilter();
  const unauthorized = filter.normalize(inboundMessage({
    id: 1,
    senderId: "unauthorized-user",
    text: "safe read-only request",
  }), filterConfig(), "sim-account");
  const boundary = filter.normalize(inboundMessage({
    id: 2,
    senderId: "authorized-user",
    text: "a".repeat(32 * 1024),
  }), filterConfig(), "sim-account");
  const oversized = filter.normalize(inboundMessage({
    id: 3,
    senderId: "authorized-user",
    text: "a".repeat((32 * 1024) + 1),
  }), filterConfig(), "sim-account");

  assert.deepEqual(unauthorized.policyDecision, {
    accepted: false,
    code: "sender_not_allowed",
    inputBytes: 22,
    maxInputBytes: 32 * 1024,
  });
  assert.equal(boundary.policyDecision.accepted, true);
  assert.equal(boundary.policyDecision.inputBytes, 32 * 1024);
  assert.deepEqual(oversized.policyDecision, {
    accepted: false,
    code: "input_too_large",
    inputBytes: (32 * 1024) + 1,
    maxInputBytes: 32 * 1024,
  });
});

test("App policy gate performs zero Runtime dispatches for rejected inbound", async () => {
  let preparedCalls = 0;
  const sent = [];
  const app = {
    channelAdapter: {
      normalizeIncomingMessage(message) {
        return message;
      },
      async sendText(payload) {
        sent.push(payload);
      },
    },
    walkingSkeletonTrace: {
      beginInbound() {
        return "cb140-0123456789abcdef01234567";
      },
    },
    primeDeferredRepliesForSender() {
      throw new Error("rejected input reached deferred-reply handling");
    },
    async handlePreparedMessage() {
      preparedCalls += 1;
    },
  };

  await CyberbossApp.prototype.handleIncomingMessage.call(app, {
    senderId: "unauthorized-user",
    contextToken: "context-1",
    policyDecision: {
      accepted: false,
      code: "sender_not_allowed",
      inputBytes: 4,
      maxInputBytes: 32 * 1024,
    },
  });
  await CyberbossApp.prototype.handleIncomingMessage.call(app, {
    senderId: "authorized-user",
    contextToken: "context-2",
    policyDecision: {
      accepted: false,
      code: "input_too_large",
      inputBytes: (32 * 1024) + 1,
      maxInputBytes: 32 * 1024,
    },
  });

  assert.equal(preparedCalls, 0);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].userId, "authorized-user");
  assert.match(sent[0].text, /32768-byte limit/);
});

test("walking-skeleton trace correlates one complete chain without raw content", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-cb140-trace-"));
  const traceFile = path.join(stateDir, "evidence", "walking-skeleton.ndjson");
  const traceStore = new WalkingSkeletonTraceStore({
    filePath: traceFile,
    stateDir,
  });
  const rawInput = "read-only fixture payload never persist me";
  const rawOutput = "SIMULATED_CODEX_RESULT: fixture output never persist me";
  const traceId = traceStore.beginInbound({
    provider: "weixin",
    accountId: "private-account",
    senderId: "private-sender",
    messageId: "message-1",
    receivedAt: "2026-07-27T00:00:00.000Z",
    text: rawInput,
    policyDecision: {
      accepted: true,
      inputBytes: Buffer.byteLength(rawInput),
      maxInputBytes: 32 * 1024,
    },
  });
  const sent = [];
  const delivery = new StreamDelivery({
    channelAdapter: {
      async sendText(payload) {
        sent.push(payload);
      },
    },
    sessionStore: {
      findBindingForThreadId() {
        return { bindingKey: "binding-1" };
      },
    },
    onTraceEvent: (event) => traceStore.record(event),
  });
  delivery.setReplyTarget("binding-1", {
    userId: "private-sender",
    contextToken: "private-context",
    provider: "weixin",
    traceId,
  });

  await delivery.handleRuntimeEvent({
    type: "runtime.turn.started",
    payload: { threadId: "private-thread", turnId: "private-turn" },
  });
  await delivery.handleRuntimeEvent({
    type: "runtime.reply.completed",
    payload: {
      threadId: "private-thread",
      turnId: "private-turn",
      itemId: "item-1",
      text: rawOutput,
    },
  });
  await delivery.handleRuntimeEvent({
    type: "runtime.turn.completed",
    payload: { threadId: "private-thread", turnId: "private-turn" },
  });

  const serialized = fs.readFileSync(traceFile, "utf8");
  const records = serialized.trim().split("\n").map((line) => JSON.parse(line));
  assert.deepEqual(records.map((record) => record.stage), TRACE_STAGE_ORDER);
  assert.equal(new Set(records.map((record) => record.trace_id)).size, 1);
  assert.equal(records.at(-1).completed, true);
  assert.equal(records.at(-1).stage_count, TRACE_STAGE_ORDER.length - 1);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].text, rawOutput);
  for (const forbidden of [
    rawInput,
    rawOutput,
    "private-account",
    "private-sender",
    "private-context",
    "private-thread",
    "private-turn",
  ]) {
    assert.equal(serialized.includes(forbidden), false);
  }
});

test("walking-skeleton trace file fails closed outside its state directory", () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-cb140-scope-"));
  assert.throws(() => new WalkingSkeletonTraceStore({
    filePath: path.join(path.dirname(stateDir), "outside.ndjson"),
    stateDir,
  }), /inside the state directory/);
});
