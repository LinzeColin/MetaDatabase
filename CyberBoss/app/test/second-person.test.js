"use strict";

// 第二个人真的扫码进来之后。
//
// 二维码放出去、朋友扫了、发了一句话——**没有回音**，而且后台里他显示成
// 「主人」。两个 bug，都只在有第二个人的时候才现形，而且都是我自己前面几轮
// 埋的。写在这里是因为它们各自都有一条便宜的守卫，只是当时没写。
//
// 一、他的消息被记在**主人**名下。
//     rejectInbound/acceptInbound 的 userId 不传时，数据库那边
//     #resolveScopeUserId(null) 一律返回主人的 user_id。durable inbox 从来
//     没传过。所以每个人发来的每一条都落进主人的隔离域——只有一个人在用的
//     时候完全看不出来。这是隔离破了，不是标签写错了。
//
// 二、他的入门回复发不出去。
//     sendAdmissionReply 不带 accountId，适配器只能按 senderId 反查归属；
//     而新人这一刻在任何一个号下面都还没有 context_token，反查必然落空，
//     退回主号——拿主人的 bot token 去回一个挂在别人号下的人，微信必拒。
//     更糟的是那一行是 .catch(() => {})：发失败一声不吭，后台还记成"已发出"。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { DurableInboxCoordinator } = require("../src/services/inbox/durable-inbox");
const { CyberbossApp } = require("../src/core/app");

const OWNER_BOT = "owner-bot";
const GUEST_BOT = "guest-bot";
const OWNER_WECHAT = "wx-owner";
const GUEST_WECHAT = "wx-guest";
const OWNER_USER = `usr_${"o".repeat(24)}`;
const GUEST_USER = `usr_${"g".repeat(24)}`;

// 真实形状：item_list 里是 { type: 1, text_item: { text } }。
function inboundMessage({ from = GUEST_WECHAT, text = "你好", seq = 1 } = {}) {
  return {
    message_type: 1,
    from_user_id: from,
    context_token: `ctx-${from}`,
    message_id: `mid-${seq}`,
    seq: String(seq),
    create_time_ms: String(1_700_000_000_000 + seq),
    item_list: [{ type: 1, text_item: { text } }],
  };
}

// 一个只记录写了什么的假库。它把 userId 原样收下——那正是要断言的东西。
function fakeSpool() {
  const writes = [];
  return {
    writes,
    acceptInbound(row) {
      writes.push({ kind: "accept", ...row });
      return Object.freeze({ inboxId: `in-${writes.length}`, jobId: `job-${writes.length}` });
    },
    rejectInbound(row) {
      writes.push({ kind: "reject", ...row });
      return Object.freeze({ inboxId: `in-${writes.length}` });
    },
  };
}

function fakeChannel(accountId) {
  return {
    fetchUpdates: async () => ({}),
    commitCandidateCursor: () => ({ changed: true }),
    loadSyncBuffer: () => "",
    resolveAccount: () => ({ accountId }),
    normalizeIncomingMessage: (message) => ({
      provider: "weixin",
      accountId,
      senderId: String(message.from_user_id || ""),
      contextToken: String(message.context_token || ""),
      text: message.item_list?.[0]?.text_item?.text || "",
      attachments: [],
      receivedAt: "2026-07-29T06:04:56.000Z",
      policyDecision: { accepted: true },
    }),
  };
}

function ingest(coordinator, messages) {
  return coordinator.ingestFetchedBatch({
    response: {},
    committedCursor: "",
    candidateCursor: "",
    messages,
  });
}

// ── 一、隔离：谁的消息记在谁名下 ────────────────────────────

test("访客的消息记在访客名下，不是记在主人名下", () => {
  const database = fakeSpool();
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: fakeChannel(GUEST_BOT),
    database,
    config: {},
    resolveUserId: (normalized) => (
      normalized.senderId === GUEST_WECHAT ? GUEST_USER : OWNER_USER
    ),
  });

  ingest(coordinator, [inboundMessage()]);

  assert.equal(database.writes.length, 1);
  assert.equal(
    database.writes[0].userId,
    GUEST_USER,
    "访客的话被记进了主人的隔离域——这是隔离破了，不是标签写错了",
  );
});

test("被准入层直接办掉的那条也要记在他自己名下——新人的第一句话正好走这条", () => {
  const database = fakeSpool();
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: fakeChannel(GUEST_BOT),
    database,
    config: {},
    admissionFilter: () => true,
    resolveUserId: () => GUEST_USER,
  });

  ingest(coordinator, [inboundMessage()]);

  assert.equal(database.writes[0].kind, "reject");
  assert.equal(database.writes[0].rejectReason, "handled_by_admission");
  assert.equal(database.writes[0].userId, GUEST_USER);
});

test("认不出来时传 null（退回主人名下），而不是抛错把整批消息卡死", () => {
  const database = fakeSpool();
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: fakeChannel(GUEST_BOT),
    database,
    config: {},
    resolveUserId: () => { throw new Error("users 表还没有他"); },
  });

  const result = ingest(coordinator, [inboundMessage()]);

  assert.equal(result.acceptedCount, 1, "认不出人就把消息弄丢，比记错域糟得多");
  assert.equal(database.writes[0].userId, null);
});

test("准入层每条消息只判一次——判两次会把入门回复发两遍", () => {
  const database = fakeSpool();
  let calls = 0;
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: fakeChannel(GUEST_BOT),
    database,
    config: {},
    admissionFilter: () => { calls += 1; return true; },
    resolveUserId: () => GUEST_USER,
  });

  ingest(coordinator, [inboundMessage()]);

  assert.equal(calls, 1, `准入层被调了 ${calls} 次`);
});

test("resolveUserId 必须同步——一个 await 会把「已收下但游标未提交」的窗口拉长", () => {
  const database = fakeSpool();
  const coordinator = new DurableInboxCoordinator({
    channelAdapter: fakeChannel(GUEST_BOT),
    database,
    config: {},
    resolveUserId: async () => GUEST_USER,
  });

  assert.throws(
    () => ingest(coordinator, [inboundMessage()]),
    /RESOLVE_USER_ID_MUST_BE_SYNCHRONOUS/,
  );
});

test("app 只交出 users 表里真的有的那个 id——库对不认识的 id 会抛，那会让消息反复重投", () => {
  const app = Object.create(CyberbossApp.prototype);
  app.userAdmission = { users: { identify: () => ({ userId: GUEST_USER }) } };
  app.runtimeSpoolDatabase = {
    database: { prepare: () => ({ get: () => undefined }) },
  };

  assert.equal(app.scopeUserIdForInbound({ accountId: GUEST_BOT, senderId: GUEST_WECHAT }), null);

  app.runtimeSpoolDatabase = {
    database: { prepare: () => ({ get: () => ({ 1: 1 }) }) },
  };
  assert.equal(app.scopeUserIdForInbound({ accountId: GUEST_BOT, senderId: GUEST_WECHAT }), GUEST_USER);
});

// ── 二、入门回复要用**收到这条消息的那个号**发 ──────────────

test("入门回复用收到它的那个号发，不是用主号发", async () => {
  const sent = [];
  const app = Object.create(CyberbossApp.prototype);
  app.channelAdapter = {
    rememberContextToken: () => "",
    sendText: async (args) => { sent.push(args); },
  };
  app.noteBotInitiated = () => true;

  await app.sendAdmissionReply({
    senderId: GUEST_WECHAT,
    accountId: GUEST_BOT,
    contextToken: "ctx-guest",
  }, "你好，先说一句话就能用。");

  assert.equal(sent.length, 1);
  assert.equal(
    sent[0].accountId,
    GUEST_BOT,
    "不带 accountId 就会退回主号——拿主人的 token 回一个挂在别人号下的人，必被拒",
  );
  assert.equal(sent[0].contextToken, "ctx-guest");
});

test("回复之前先把这个人的 context_token 记下来——onAccepted 对这条路一次都不触发", async () => {
  const remembered = [];
  const app = Object.create(CyberbossApp.prototype);
  app.channelAdapter = {
    rememberContextToken: (userId, token, accountId) => {
      remembered.push({ userId, token, accountId });
      return token;
    },
    sendText: async () => {},
  };
  app.noteBotInitiated = () => true;

  await app.sendAdmissionReply({
    senderId: GUEST_WECHAT,
    accountId: GUEST_BOT,
    contextToken: "ctx-guest",
  }, "你好");

  assert.deepEqual(remembered, [{
    userId: GUEST_WECHAT, token: "ctx-guest", accountId: GUEST_BOT,
  }]);
});

test("发失败要如实记成没发出去——以前是 .catch(() => {})，面板还记成已发出", async () => {
  const noted = [];
  const app = Object.create(CyberbossApp.prototype);
  app.channelAdapter = {
    rememberContextToken: () => "",
    sendText: async () => {
      const error = new Error("weixin rejected");
      error.code = "WEIXIN_CONTEXT_REQUIRED";
      throw error;
    },
  };
  app.noteBotInitiated = (entry) => { noted.push(entry); return true; };

  const errors = [];
  const original = console.error;
  console.error = (line) => errors.push(line);
  try {
    await app.sendAdmissionReply({
      senderId: GUEST_WECHAT, accountId: GUEST_BOT, contextToken: "ctx-guest",
    }, "你好");
  } finally {
    console.error = original;
  }

  assert.equal(noted.length, 1);
  assert.equal(noted[0].delivered, false, "没送到却记成送到了，等于骗自己");
  assert.equal(noted[0].errorClass, "WEIXIN_CONTEXT_REQUIRED");
  assert.equal(errors.length, 1, "发失败必须留一行日志，不能一声不吭");
});

test("发成功时记成已发出", async () => {
  const noted = [];
  const app = Object.create(CyberbossApp.prototype);
  app.channelAdapter = { rememberContextToken: () => "", sendText: async () => {} };
  app.noteBotInitiated = (entry) => { noted.push(entry); return true; };

  await app.sendAdmissionReply({
    senderId: GUEST_WECHAT, accountId: GUEST_BOT, contextToken: "ctx-guest",
  }, "你好");

  assert.equal(noted[0].delivered, true);
  assert.equal(noted[0].errorClass, "");
});

// ── 接线守卫 ────────────────────────────────────────────────

test("resolveUserId 真的接到了 durable inbox 上，不是只写了个钩子", () => {
  const source = fs.readFileSync(path.join(__dirname, "../src/core/app.js"), "utf8");
  assert.match(source, /resolveUserId:\s*\(normalized\)\s*=>\s*this\.scopeUserIdForInbound\(normalized\)/);
  const inbox = fs.readFileSync(
    path.join(__dirname, "../src/services/inbox/durable-inbox.js"), "utf8",
  );
  // 三条写库的路都要带上，漏一条就等于那一类消息还是记在主人名下。
  assert.equal((inbox.match(/userId: scopeUserId,/g) || []).length, 3);
});
