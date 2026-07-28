"use strict";

// The test whose absence let the v0.0.0.8 overlay be built without being live.
//
// Every other suite proves a property of a MODULE. This one drives a simulated
// inbound WeChat message through CyberbossApp#handleIncomingMessage — the real
// live path — against a real SQLite runtime database, and asserts the property
// of the PRODUCT: that an ordinary sender is scoped, that a pre-active sender
// costs zero model calls, and that only the Owner reaches the Owner runtime.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const { CyberbossApp } = require("../src/core/app");
const { UserAdmissionService } = require("../src/core/user-admission");
const { UserTurnRuntime } = require("../src/core/user-turn-runtime");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { OFFICIAL_ORIGINS } = require("../src/services/providers/router");
const { SqliteCredentialVault } = require("../src/services/secrets/credential-vault");
const { deriveSubKey } = require("../src/core/user-turn-runtime");
const { createInboundFilter } = require("../src/adapters/channel/weixin/message-utils");

const ENCRYPTION_KEY = Buffer.alloc(32, 3);
const IDENTITY_KEY = Buffer.alloc(32, 5);
const BOT = "bot-account-e2e";
const OWNER_SENDER = "owner-sender";
const ALICE = "alice-sender";
const BOB = "bob-sender";

const POLICIES = Object.freeze({
  openai: { providerId: "openai", origin: OFFICIAL_ORIGINS.openai, models: ["gpt-5-mini"] },
  deepseek: { providerId: "deepseek", origin: OFFICIAL_ORIGINS.deepseek, models: ["deepseek-chat"] },
  google: { providerId: "google", origin: OFFICIAL_ORIGINS.google, models: ["gemini-2.5-flash"] },
  anthropic: { providerId: "anthropic", origin: OFFICIAL_ORIGINS.anthropic, models: ["claude-sonnet-5"] },
});

// A harness that is deliberately close to the real app: the admission service,
// the user turn runtime and the runtime database are the production classes.
// Only the two outer edges — the WeChat channel and the Owner runtime — are fakes,
// and both of them count every call so "zero model calls" is measured, not
// asserted from a comment.
function harness(t, { ownerSenderIds = [OWNER_SENDER], multiUser = true } = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-e2e-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const databasePath = path.join(directory, "runtime.db");
  const spool = new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());

  const sent = [];
  const typing = [];
  const runtimeTurns = [];
  const providerCalls = [];

  const fetchImpl = async (url, init) => {
    providerCalls.push({ url: String(url), method: init && init.method });
    return {
      ok: true,
      status: 200,
      async text() {
        return JSON.stringify({
          output_text: "provider answer",
          usage: { input_tokens: 11, output_tokens: 7 },
        });
      },
    };
  };

  const admission = multiUser
    ? new UserAdmissionService({
        database: spool.database,
        identityKey: IDENTITY_KEY,
        ownerUserId: spool.ownerUserId,
        ownerSenderIds,
        registrationMode: "invite",
      })
    : null;

  const app = {
    config: { multiUser, allowedUserIds: ownerSenderIds, ownerSenderIds },
    userAdmission: admission,
    userTurnRuntime: multiUser
      ? new UserTurnRuntime({
          database: spool.database,
          userRepository: admission.users,
          encryptionKey: ENCRYPTION_KEY,
          providerPolicies: POLICIES,
          fetchImpl,
        })
      : null,
    channelAdapter: {
      normalizeIncomingMessage: (message) => message,
      async sendText(payload) {
        sent.push(payload);
      },
      async sendTyping(payload) {
        typing.push(payload);
      },
    },
    walkingSkeletonTrace: { beginInbound: () => "" },
    primeDeferredRepliesForSender() {},
    // The Owner lane. Reaching it at all is what an ordinary user must never do.
    async handlePreparedMessage(normalized, options) {
      runtimeTurns.push({ senderId: normalized.senderId, options });
    },
    admitInboundMessage: CyberbossApp.prototype.admitInboundMessage,
    sendAdmissionReply: CyberbossApp.prototype.sendAdmissionReply,
    runUserModelTurn: CyberbossApp.prototype.runUserModelTurn,
    stopTypingForUser: CyberbossApp.prototype.stopTypingForUser,
  };

  const deliver = (senderId, text, messageId = `msg-${sent.length}-${runtimeTurns.length}`) =>
    CyberbossApp.prototype.handleIncomingMessage.call(app, {
      provider: "weixin",
      accountId: BOT,
      workspaceId: "default",
      senderId,
      messageId,
      text,
      contextToken: `ctx-${senderId}`,
      receivedAt: "2026-07-28T09:00:00.000Z",
      policyDecision: { accepted: true, code: "accepted" },
    });

  const configureProvider = (userId, providerId = "openai", model = "gpt-5-mini") => {
    const vault = new SqliteCredentialVault({
      database: spool.database,
      masterKey: deriveSubKey(ENCRYPTION_KEY, "cyberboss-credential-vault-kek"),
    });
    vault.putCredential({ userId, providerId, apiKey: `sk-${userId}-secret` });
    spool.database
      .prepare("UPDATE user_settings SET provider_id=?, model_id=?, updated_at=? WHERE user_id=?")
      .run(providerId, model, new Date().toISOString(), userId);
  };

  const register = (senderRef) => {
    const invite = admission.issueInvite({ maxUses: 1, ttlMs: 600_000 });
    admission.admit({ botAccountRef: BOT, senderRef, text: invite.code });
    const decision = admission.admit({
      botAccountRef: BOT,
      senderRef,
      text: "同意并开始",
    });
    assert.equal(decision.route, "reply");
    const active = admission.admit({ botAccountRef: BOT, senderRef, text: "hello" });
    assert.equal(active.route, "user");
    return active.userContext;
  };

  return {
    app,
    spool,
    admission,
    deliver,
    register,
    configureProvider,
    sent,
    typing,
    runtimeTurns,
    providerCalls,
  };
}

test("an unknown WeChat sender reaches the invite prompt and zero model calls", async (t) => {
  const h = harness(t);

  await h.deliver(ALICE, "你好");

  assert.equal(h.runtimeTurns.length, 0, "an unregistered sender must not reach the Owner runtime");
  assert.equal(h.providerCalls.length, 0, "an unregistered sender must not reach a provider");
  assert.equal(h.sent.length, 1);
  assert.equal(h.sent[0].userId, ALICE);
  assert.match(h.sent[0].text, /邀请码/);
});

test("consent is the only transition that admits a user, and it costs no model call", async (t) => {
  const h = harness(t);
  const invite = h.admission.issueInvite({ maxUses: 1, ttlMs: 600_000 });

  await h.deliver(ALICE, "开始");
  await h.deliver(ALICE, invite.code);
  assert.match(h.sent.at(-1).text, /同意并开始/, "the consent text is shown before activation");

  await h.deliver(ALICE, "不同意");
  assert.match(h.sent.at(-1).text, /已停止开通/);

  await h.deliver(ALICE, "同意并开始");
  assert.match(h.sent.at(-1).text, /已开通/);

  assert.equal(h.providerCalls.length, 0, "no pre-active transition may reach a provider");
  assert.equal(h.runtimeTurns.length, 0, "no pre-active transition may reach the Owner runtime");
});

test("an active ordinary user is answered by the provider path, never the Owner runtime", async (t) => {
  const h = harness(t);
  const context = h.register(ALICE);
  h.configureProvider(context.userId);

  await h.deliver(ALICE, "帮我想个周末计划");

  assert.equal(h.runtimeTurns.length, 0, "an ordinary user must never reach the Owner runtime");
  assert.equal(h.providerCalls.length, 1, "an ordinary user's turn goes through the provider router");
  assert.match(h.providerCalls[0].url, /^https:\/\/api\.openai\.com\//);
  assert.equal(h.sent.at(-1).text, "provider answer");
  assert.equal(h.sent.at(-1).userId, ALICE);
});

test("an active user with no provider configured is told how to finish setup, not sent to a provider", async (t) => {
  const h = harness(t);
  h.register(ALICE);

  await h.deliver(ALICE, "帮我想个周末计划");

  assert.equal(h.providerCalls.length, 0);
  assert.equal(h.runtimeTurns.length, 0);
  assert.match(h.sent.at(-1).text, /设置/);
});

test("the Owner still reaches the Owner runtime, and carries an owner UserContext", async (t) => {
  const h = harness(t);

  await h.deliver(OWNER_SENDER, "read the repository and summarise it");

  assert.equal(h.providerCalls.length, 0, "the Owner keeps the pre-existing runtime, not the BYOK path");
  assert.equal(h.runtimeTurns.length, 1);
  const { options } = h.runtimeTurns[0];
  assert.equal(options.allowCommands, true);
  assert.ok(options.userContext, "the Owner turn must carry a UserContext");
  assert.equal(options.userContext.role, "owner");
  assert.equal(options.userContext.isOwner, true);
  assert.equal(options.userContext.may("codex.turn"), true);
  assert.equal(options.userContext.may("project.tool"), true);
});

test("two ordinary senders on one bot account are two isolated users", async (t) => {
  const h = harness(t);
  const alice = h.register(ALICE);
  const bob = h.register(BOB);

  assert.notEqual(alice.userId, bob.userId);
  assert.equal(alice.isOwner, false);
  assert.equal(bob.isOwner, false);
  // AC-006 restated on the live objects: neither ordinary user can reach any
  // Owner-only capability, and neither can act as the other.
  for (const context of [alice, bob]) {
    assert.equal(context.may("codex.turn"), false);
    assert.equal(context.may("claudecode.turn"), false);
    assert.equal(context.may("project.tool"), false);
    assert.equal(context.may("shell.execute"), false);
    assert.equal(context.may("chat.turn"), true);
  }
  assert.throws(
    () => alice.requireOwnRecord({ user_id: bob.userId }),
    /USER_SCOPE_VIOLATION/,
  );
});

test("a redelivered WeChat message is refused as a duplicate instead of charged twice", async (t) => {
  const h = harness(t);
  const context = h.register(ALICE);
  h.configureProvider(context.userId);

  await h.deliver(ALICE, "同一条消息", "duplicate-message-id");
  await h.deliver(ALICE, "同一条消息", "duplicate-message-id");

  assert.equal(h.providerCalls.length, 1, "the second delivery must not reach the provider");
  assert.equal(
    h.sent.filter((payload) => payload.text === "provider answer").length,
    1,
    "the duplicate is silent rather than answered twice",
  );
});

test("a suspended user is refused without a model call", async (t) => {
  const h = harness(t);
  const context = h.register(ALICE);
  h.configureProvider(context.userId);
  h.admission.users.setStatus(context.userId, "suspended");

  await h.deliver(ALICE, "在吗");

  assert.equal(h.providerCalls.length, 0);
  assert.equal(h.runtimeTurns.length, 0);
  assert.match(h.sent.at(-1).text, /暂停/);
});

test("with admission off the pre-existing single-user path is untouched", async (t) => {
  const h = harness(t, { multiUser: false });

  await h.deliver(OWNER_SENDER, "hello");

  assert.equal(h.runtimeTurns.length, 1);
  assert.equal(h.runtimeTurns[0].options.userContext, null);
  assert.equal(h.providerCalls.length, 0);
});

test("the channel allowlist stops rejecting non-Owner senders once admission is on", () => {
  const filter = createInboundFilter();
  const message = {
    seq: 1,
    message_id: "m-1",
    client_id: "c-1",
    from_user_id: ALICE,
    message_type: 1,
    create_time_ms: 1_700_000_000_000,
    session_id: "s-1",
    context_token: "ctx",
    item_list: [{ type: 1, text_item: { text: "你好" } }],
  };

  const singleUser = filter.normalize(
    message,
    { workspaceId: "default", allowedUserIds: [OWNER_SENDER], maxInputBytes: 32 * 1024 },
    BOT,
  );
  assert.equal(singleUser.policyDecision.accepted, false);
  assert.equal(singleUser.policyDecision.code, "sender_not_allowed");

  const multiUser = filter.normalize(
    { ...message, message_id: "m-2", client_id: "c-2" },
    {
      workspaceId: "default",
      allowedUserIds: [OWNER_SENDER],
      multiUser: true,
      maxInputBytes: 32 * 1024,
    },
    BOT,
  );
  assert.equal(multiUser.policyDecision.accepted, true, "admission, not the allowlist, decides");

  // The size limit is unconditional and still applies to an ordinary sender.
  const oversized = filter.normalize(
    {
      ...message,
      message_id: "m-3",
      client_id: "c-3",
      item_list: [{ type: 1, text_item: { text: "a".repeat(32 * 1024 + 1) } }],
    },
    {
      workspaceId: "default",
      allowedUserIds: [OWNER_SENDER],
      multiUser: true,
      maxInputBytes: 32 * 1024,
    },
    BOT,
  );
  assert.equal(oversized.policyDecision.code, "input_too_large");
});

test("the Owner runtime refuses a turn that arrives without an Owner context", async (t) => {
  const h = harness(t);
  const alice = h.register(ALICE);
  const refusals = [];

  const dispatched = await CyberbossApp.prototype.dispatchPreparedTurn.call(
    {
      userAdmission: h.admission,
      activeUserContext: alice,
      runtimeAdapter: { describe: () => ({ id: "codex" }) },
      channelAdapter: {
        async sendText(payload) {
          refusals.push(payload);
        },
        async sendTyping() {
          throw new Error("typing must not start for a refused turn");
        },
      },
      workspaceRegistry: {
        assertAllowedRoot() {
          throw new Error("workspace must not be resolved for a refused turn");
        },
      },
    },
    {
      bindingKey: "binding",
      workspaceRoot: "/workspace",
      prepared: { senderId: ALICE, contextToken: "ctx", provider: "weixin", userContext: alice },
    },
  );

  assert.equal(dispatched, false);
  assert.equal(refusals.length, 1);
  assert.match(refusals[0].text, /管理员/);
});
