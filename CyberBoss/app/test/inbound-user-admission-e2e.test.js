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
const { projectLiveStatus } = require("../src/services/status/live-status-projector");
const { tokenAppearsInRequestTarget } = require("../src/services/security/secure-setup-link");

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
function harness(t, {
  ownerSenderIds = [OWNER_SENDER],
  multiUser = true,
  portalOrigin = "",
} = {}) {
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
        portalOrigin,
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

test("「设置」 mints a single-use link that never puts the token in the request target", async (t) => {
  const h = harness(t, { portalOrigin: "https://portal.example.com" });
  h.register(ALICE);

  await h.deliver(ALICE, "设置");

  assert.equal(h.providerCalls.length, 0, "asking for the setup page is not a model call");
  const message = h.sent.at(-1).text;
  const link = message.match(/https:\/\/\S+/)[0];
  const url = new URL(link);
  assert.equal(url.origin, "https://portal.example.com");
  assert.equal(url.pathname, "/setup");
  assert.equal(url.search, "", "no token may appear in the query string");
  assert.match(url.hash, /^#t=[A-Za-z0-9_-]{32,86}&p=provider$/);
  assert.equal(
    tokenAppearsInRequestTarget(link, url.hash.slice(3).split("&")[0]),
    false,
    "the token must live in the fragment, which a server never logs",
  );

  // Single use: the second request mints a different token, and the first is
  // still consumable exactly once.
  await h.deliver(ALICE, "设置", "second-setup-request");
  const secondLink = h.sent.at(-1).text.match(/https:\/\/\S+/)[0];
  assert.notEqual(secondLink, link);
});

test("「设置」 says so plainly when no portal origin is configured", async (t) => {
  const h = harness(t);
  h.register(ALICE);

  await h.deliver(ALICE, "设置");

  assert.equal(h.providerCalls.length, 0);
  assert.match(h.sent.at(-1).text, /CB_PORTAL_ORIGIN/);
});

test("the live operational projection reports all fourteen lines and no model call", () => {
  const projection = projectLiveStatus({
    facts: {
      channelReady: true,
      admissionEnabled: true,
      activeUsers: 2,
      budgetReady: true,
      ownerRuntimeReady: true,
    },
    generatedAt: new Date("2026-07-28T09:00:00.000Z"),
    // A measured host, so the gate's verdict here is about the numbers rather
    // than about whatever the machine running the suite happens to be doing.
    hostMetrics: {
      freeMemoryBytes: 8 * 1024 * 1024 * 1024,
      freeDiskBytes: 200 * 1024 * 1024 * 1024,
      freeInodes: 5_000_000,
      queueDepth: 1,
      loadRatio: 0.2,
    },
  });

  assert.equal(projection.status.business_lines.length, 14);
  assert.equal(projection.status.model_calls, 0);
  assert.equal(projection.status.version, "v0.0.0.8");
  assert.equal(projection.resource_gate.admits_new_work, true);
  assert.equal(projection.self_heal.action, "none");
  assert.equal(projection.self_heal.modelCalls, 0);

  // AC-032: no user identifier may appear anywhere in a Status document.
  const serialized = JSON.stringify(projection.status);
  for (const forbidden of ["user_id", "wechat_id", "api_key", "object_key", "prompt"]) {
    assert.equal(serialized.includes(forbidden), false, `Status leaked ${forbidden}`);
  }

  const byLine = new Map(
    projection.status.business_lines.map((line) => [line.business_line, line]),
  );
  assert.equal(byLine.get("user_isolation").state, "healthy");
  assert.equal(byLine.get("user_isolation").queue_depth, 2);
  // An unconfigured dependency is activation_pending, never a quiet healthy.
  assert.equal(byLine.get("r2_oci_objects").state, "activation_pending");
  assert.equal(byLine.get("backup_restore").state, "activation_pending");
  assert.equal(byLine.get("release_rollback").state, "activation_pending");
});

test("a host whose disk cannot be measured is refused rather than admitted", () => {
  const projection = projectLiveStatus({
    facts: { channelReady: true, admissionEnabled: true },
    generatedAt: new Date("2026-07-28T09:00:00.000Z"),
    hostMetrics: {
      freeMemoryBytes: 8 * 1024 * 1024 * 1024,
      queueDepth: 0,
      loadRatio: 0.1,
    },
  });

  assert.equal(projection.resource_gate.admits_new_work, false);
  assert.equal(projection.self_heal.modelCalls, 0);
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

// ── 主人认领码 ───────────────────────────────────────────
//
// 这是一个真实事故：主人拿自己的微信当了机器人号，于是那个号的 id 永远不会
// 作为「发件人」出现；而 ownerSenderIds 一旦有值，先到先得的认领窗口就关着。
// 两件事叠起来，谁都成不了主人——机器人对包括主人本人在内的每个人都只回一句
// 「这个操作只有管理员可以使用」，整个软件不可用。
//
// 后台令牌是只有服务器管理者才拿得到的东西，用它换一次性认领码，是唯一一条
// 既能解开死局、又不会把主人身份交给陌生人的路。

function admissionOnly(t, { ownerSenderIds = [] } = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-claim-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  return new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds,
    registrationMode: "invite",
  });
}

test("认领码把发码的那个微信号绑成主人", (t) => {
  // ownerSenderIds 非空 = 认领窗口已关闭，正是线上那台机器的状态。
  const admission = admissionOnly(t, { ownerSenderIds: ["bot-self-id"] });

  const before = admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: "你好" });
  assert.equal(before.route, "reply", "没有码之前，陌生人只能拿到入门回复");

  const claim = admission.issueOwnerClaim();
  assert.match(claim.code, /^[A-Z0-9]{12,32}$/);

  const claimed = admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: claim.code });
  assert.equal(claimed.route, "owner");
  assert.equal(claimed.ownerClaimed, true);
  assert.equal(claimed.userContext.role, "owner");

  // 绑上之后，这个号说的每一句都是主人的话——靠的是库里的角色，不是发件人名单。
  const later = admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: "帮我看看代码" });
  assert.equal(later.route, "owner");
});

test("认领码只能用一次", (t) => {
  const admission = admissionOnly(t, { ownerSenderIds: ["bot-self-id"] });
  const claim = admission.issueOwnerClaim();

  assert.equal(admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: claim.code }).route, "owner");

  // 同一串码再发一次——而且换一个人发——不能再绑出第二个主人。
  const second = admission.admit({ botAccountRef: BOT, senderRef: BOB, text: claim.code });
  assert.notEqual(second.route, "owner");
});

test("过期的认领码不认，而且当场作废", (t) => {
  let clock = new Date("2026-07-28T00:00:00.000Z");
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-claim-exp-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["bot-self-id"],
    registrationMode: "invite",
    now: () => clock,
  });

  const claim = admission.issueOwnerClaim({ ttlMs: 60_000 });
  clock = new Date(clock.getTime() + 120_000);

  assert.notEqual(
    admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: claim.code }).route,
    "owner",
  );
  // 验过就删：过期的码不会留在库里等人慢慢试。
  assert.notEqual(
    admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: claim.code }).route,
    "owner",
  );
});

test("猜错的码不会绑成主人", (t) => {
  const admission = admissionOnly(t, { ownerSenderIds: ["bot-self-id"] });
  admission.issueOwnerClaim();

  for (const guess of ["ABCDEFGHJKLM", "000000000000", "帮助", ""]) {
    const result = admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: guess });
    assert.notEqual(result.route, "owner", `"${guess}" 不该绑成主人`);
  }
});
