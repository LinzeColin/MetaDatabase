"use strict";

// 同时管多个微信号。
//
// 这是「每人扫码绑自己微信」的地基。iLink 的授权码扫一次就生成一个**属于扫码
// 那个人**的 bot 号（ilink_bot_id + bot_token + ilink_user_id），所以「五个人用」
// 在盘上就是五个 account 文件。
//
// 在这之前，整个进程只认一个号，而且失败方式比「忽略」更糟：
//   · resolveSelectedAccount 一看到两个号就抛 "Multiple WeChat accounts were
//     detected"——服务连启动都启动不了。第二个人扫码 = 全体停机。
//   · 适配器把 selectedAccount / contextTokenCache 存成两个闭包变量，一个进程
//     一个号，第二个号的消息没有任何路径能进来。
//
// 所以下面这些测试不是"多加一个功能"，是在守一条一旦破掉就会全线停摆的边界。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createWeixinChannelAdapter } = require("../src/adapters/channel/weixin");
const {
  listActiveAccounts,
  listWeixinAccounts,
  pickPrimaryAccount,
  resolveSelectedAccount,
  saveWeixinAccount,
} = require("../src/adapters/channel/weixin/account-store");
const {
  buildSenderIndex,
  resolveAccountForUser,
} = require("../src/adapters/channel/weixin/account-routing");
const {
  loadPersistedContextTokens,
  persistContextToken,
} = require("../src/adapters/channel/weixin/context-token-store");
const { CyberbossApp } = require("../src/core/app");

const OWNER_BOT = "owner-bot";
const OWNER_WECHAT = "wxid_owner";
const GUEST_BOT = "guest-bot";
const GUEST_WECHAT = "wxid_guest";

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-multi-account-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function fixtureConfig(directory, baseUrl = "https://example.invalid/") {
  const stateDir = path.join(directory, "state");
  return {
    stateDir,
    accountsDir: path.join(stateDir, "accounts"),
    syncBufferDir: path.join(stateDir, "sync-buffers"),
    weixinConfigFile: path.join(stateDir, "weixin-config.json"),
    weixinBaseUrl: baseUrl,
    weixinCdnBaseUrl: baseUrl,
    accountId: "",
    workspaceId: "fixture-workspace",
    ownerSenderIds: [OWNER_WECHAT],
    allowedUserIds: [],
    maxInputBytes: 32_768,
  };
}

// 主人先扫，访客后扫——这是真实顺序，也是「按时间挑」会挑错的那个顺序的反面，
// 所以两种排序都要在测试里出现过。
function saveTwoAccounts(config, { ownerBaseUrl = config.weixinBaseUrl, guestBaseUrl = config.weixinBaseUrl } = {}) {
  saveWeixinAccount(config, OWNER_BOT, {
    token: "owner-token",
    baseUrl: ownerBaseUrl,
    userId: OWNER_WECHAT,
  });
  saveWeixinAccount(config, GUEST_BOT, {
    token: "guest-token",
    baseUrl: guestBaseUrl,
    userId: GUEST_WECHAT,
  });
}

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return `http://127.0.0.1:${server.address().port}/`;
}

// ── 账号仓：两个号不再是启动失败 ────────────────────────────

test("两个号同时存在时，服务照常启动——以前这里直接抛错，第二个人扫码等于全体停机", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);

  const accounts = listActiveAccounts(config);
  assert.equal(accounts.length, 2);
  assert.doesNotThrow(() => resolveSelectedAccount(config));
});

test("主号按主人的微信身份认，不按保存时间认", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);

  // 主人重新扫一次码：他的 savedAt 变成最新的。按时间挑就会挑到访客头上，
  // 主人的提醒和主动消息会发进别人微信里。
  saveWeixinAccount(config, OWNER_BOT, {
    token: "owner-token-v2",
    baseUrl: config.weixinBaseUrl,
    userId: OWNER_WECHAT,
  });

  assert.equal(resolveSelectedAccount(config).accountId, OWNER_BOT);
  assert.equal(resolveSelectedAccount(config).token, "owner-token-v2");
});

test("还认不出主人的时候，退回最早保存的那个——第一个扫码的人就是主人", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  config.ownerSenderIds = [];
  saveTwoAccounts(config);

  const accounts = listActiveAccounts(config);
  const primary = pickPrimaryAccount(config, accounts);
  const earliest = accounts
    .slice()
    .sort((left, right) => String(left.savedAt).localeCompare(String(right.savedAt)))[0];
  assert.equal(primary.accountId, earliest.accountId);
});

test("没有 token 的号不参与轮询——拿一个空 token 去拉更新只会一直失败", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);
  saveWeixinAccount(config, "half-scanned", { token: "", baseUrl: config.weixinBaseUrl, userId: "wxid_x" });

  assert.equal(listWeixinAccounts(config).length, 3);
  assert.deepEqual(
    listActiveAccounts(config).map((account) => account.accountId).sort(),
    [GUEST_BOT, OWNER_BOT],
  );
});

test("CYBERBOSS_ACCOUNT_ID 钉死时只管那一个号——本机调试那条老路不变", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);
  config.accountId = GUEST_BOT;

  assert.deepEqual(listActiveAccounts(config).map((account) => account.accountId), [GUEST_BOT]);
  assert.equal(resolveSelectedAccount(config).accountId, GUEST_BOT);
});

test("一个号都没有、和有号但没 token，是两句不一样的话", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  assert.throws(() => resolveSelectedAccount(config), /No saved WeChat account/);

  saveWeixinAccount(config, "tokenless", { token: "", baseUrl: config.weixinBaseUrl, userId: "" });
  assert.throws(() => resolveSelectedAccount(config), /missing a token/);
});

// ── 归属：这个人挂在哪个号下面 ──────────────────────────────

test("按 context_token 的落盘位置定位归属——那是真实发生过的事实，不是推断", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);
  persistContextToken(config, OWNER_BOT, OWNER_WECHAT, "ctx-owner");
  persistContextToken(config, GUEST_BOT, GUEST_WECHAT, "ctx-guest");

  assert.equal(resolveAccountForUser(config, GUEST_WECHAT).accountId, GUEST_BOT);
  assert.equal(resolveAccountForUser(config, OWNER_WECHAT).accountId, OWNER_BOT);

  const index = buildSenderIndex(config);
  assert.equal(index.get(GUEST_WECHAT), GUEST_BOT);
  assert.equal(index.get(OWNER_WECHAT), OWNER_BOT);
});

test("认不出归属时退回主号，而不是抛错——新人的第一条回复就发生在落盘之前那一瞬", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);

  assert.equal(resolveAccountForUser(config, "wxid_new").accountId, OWNER_BOT);
});

// ── 适配器：一个进程管两个号 ────────────────────────────────

test("刚扫完码的号，下一轮就被看见——不用重启服务", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveWeixinAccount(config, OWNER_BOT, {
    token: "owner-token", baseUrl: config.weixinBaseUrl, userId: OWNER_WECHAT,
  });
  const adapter = createWeixinChannelAdapter(config);

  assert.deepEqual(adapter.listAccounts().map((account) => account.accountId), [OWNER_BOT]);

  // 有人扫码了。这一步在生产里是 pollWebLogin 落的盘。
  saveWeixinAccount(config, GUEST_BOT, {
    token: "guest-token", baseUrl: config.weixinBaseUrl, userId: GUEST_WECHAT,
  });

  assert.deepEqual(
    adapter.listAccounts().map((account) => account.accountId).sort(),
    [GUEST_BOT, OWNER_BOT],
  );
  // 主号不能因为来了新号就换人。
  assert.equal(adapter.resolveAccount().accountId, OWNER_BOT);
});

test("context_token 记在收到消息的那个号名下，不是一律记在主号名下", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);
  const adapter = createWeixinChannelAdapter(config);

  adapter.rememberContextToken(GUEST_WECHAT, "ctx-guest", GUEST_BOT);

  assert.deepEqual(loadPersistedContextTokens(config, GUEST_BOT), { [GUEST_WECHAT]: "ctx-guest" });
  assert.deepEqual(loadPersistedContextTokens(config, OWNER_BOT), {});
});

test("两个号的游标各走各的——混用一条会让一个号的消息被当成收过了直接跳过", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);
  const adapter = createWeixinChannelAdapter(config);

  adapter.forAccount(OWNER_BOT).saveSyncBuffer("11");
  adapter.forAccount(GUEST_BOT).saveSyncBuffer("77");

  assert.equal(adapter.forAccount(OWNER_BOT).loadSyncBuffer(), "11");
  assert.equal(adapter.forAccount(GUEST_BOT).loadSyncBuffer(), "77");
});

test("单号视图给消息打的是自己的号，不是主号——收下来的归属全靠这一个字段", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);
  const adapter = createWeixinChannelAdapter(config);

  const normalized = adapter.forAccount(GUEST_BOT).normalizeIncomingMessage({
    message_type: 1,
    from_user_id: GUEST_WECHAT,
    context_token: "ctx-guest",
    create_time_ms: "1700000000000",
    item_list: [{ type: 1, text_item: { text: "在吗" } }],
  }, { durable: true });

  assert.equal(normalized.accountId, GUEST_BOT);
  assert.equal(normalized.senderId, GUEST_WECHAT);
});

test("已知的会话上下文是所有号合起来的一份，不是只报主号那几个", (t) => {
  const config = fixtureConfig(temporaryDirectory(t));
  saveTwoAccounts(config);
  const adapter = createWeixinChannelAdapter(config);
  adapter.rememberContextToken(OWNER_WECHAT, "ctx-owner", OWNER_BOT);
  adapter.rememberContextToken(GUEST_WECHAT, "ctx-guest", GUEST_BOT);

  assert.deepEqual(adapter.getKnownContextTokens(), {
    [OWNER_WECHAT]: "ctx-owner",
    [GUEST_WECHAT]: "ctx-guest",
  });
});

// ── 发信必须走对号（真发一次，看服务端收到的是谁的 token）────

test("给访客回话用的是访客那个号的 token 和地址，不是主号的", async (t) => {
  const directory = temporaryDirectory(t);
  const seen = [];
  const server = http.createServer((request, response) => {
    let raw = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => { raw += chunk; });
    request.on("end", () => {
      seen.push({
        authorization: request.headers.authorization || "",
        body: JSON.parse(raw || "{}"),
      });
      response.writeHead(200, { "content-type": "application/json" });
      // iLink 真实的成功响应就是这个形状：只有 message_id。
      response.end(JSON.stringify({ message_id: 7488003379736578000 }));
    });
  });
  t.after(() => server.close());
  const baseUrl = await listen(server);

  const config = fixtureConfig(directory, baseUrl);
  saveTwoAccounts(config, { ownerBaseUrl: baseUrl, guestBaseUrl: baseUrl });
  const adapter = createWeixinChannelAdapter(config);
  adapter.rememberContextToken(OWNER_WECHAT, "ctx-owner", OWNER_BOT);
  adapter.rememberContextToken(GUEST_WECHAT, "ctx-guest", GUEST_BOT);

  await adapter.sendText({ userId: GUEST_WECHAT, text: "在的", preserveBlock: true });
  await adapter.sendText({ userId: OWNER_WECHAT, text: "好", preserveBlock: true });

  assert.equal(seen.length, 2);
  assert.equal(seen[0].authorization, "Bearer guest-token");
  assert.equal(seen[0].body.msg.context_token, "ctx-guest");
  assert.equal(seen[1].authorization, "Bearer owner-token");
  assert.equal(seen[1].body.msg.context_token, "ctx-owner");
});

test("durable outbox 那条路也按人定位号——它才是线上真正发消息的那条", async (t) => {
  const directory = temporaryDirectory(t);
  const seen = [];
  const server = http.createServer((request, response) => {
    let raw = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => { raw += chunk; });
    request.on("end", () => {
      seen.push(request.headers.authorization || "");
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ message_id: 7488003379736578001 }));
    });
  });
  t.after(() => server.close());
  const baseUrl = await listen(server);

  const config = fixtureConfig(directory, baseUrl);
  saveTwoAccounts(config, { ownerBaseUrl: baseUrl, guestBaseUrl: baseUrl });
  const adapter = createWeixinChannelAdapter(config);
  adapter.rememberContextToken(GUEST_WECHAT, "ctx-guest", GUEST_BOT);

  await adapter.sendTextChunk({
    userId: GUEST_WECHAT,
    text: "在的",
    clientId: `cb-outbox-${"a".repeat(32)}`,
  });

  assert.deepEqual(seen, ["Bearer guest-token"]);
});

// ── 桥接循环：每个号一条长轮询，互不牵连 ────────────────────

function borrowApp({ activeAccountId = OWNER_BOT } = {}) {
  const app = Object.create(CyberbossApp.prototype);
  app.activeAccountId = activeAccountId;
  app.durableInboxCoordinator = { pollOnce: async () => ({ acceptedCount: 0, rejectedCount: 0 }) };
  app.durableInboxCoordinators = new Map();
  app.accountPollsInFlight = new Map();
  app.accountPollFailureCounts = new Map();
  return app;
}

function stubAdapter(accountIds) {
  return {
    listAccounts: () => accountIds.map((accountId) => ({ accountId })),
    resolveAccount: () => ({ accountId: accountIds[0] }),
    forAccount: (accountId) => ({ accountId }),
  };
}

test("盘上有几个号就建几个协调器，号删掉了协调器也跟着丢", (t) => {
  const app = borrowApp();
  const accountIds = [OWNER_BOT, GUEST_BOT];
  app.channelAdapter = {
    listAccounts: () => accountIds.map((accountId) => ({ accountId })),
    resolveAccount: () => ({ accountId: OWNER_BOT }),
    forAccount: (accountId) => ({ accountId }),
  };
  app.buildInboxCoordinator = (view) => ({ view, pollOnce: async () => ({}) });

  assert.deepEqual(app.liveInboxCoordinators().map((entry) => entry.accountId), [OWNER_BOT, GUEST_BOT]);
  // 主号复用启动时就建好的那一个，不重复建。
  assert.equal(app.durableInboxCoordinators.get(OWNER_BOT), app.durableInboxCoordinator);

  accountIds.pop();
  assert.deepEqual(app.liveInboxCoordinators().map((entry) => entry.accountId), [OWNER_BOT]);
  assert.equal(app.durableInboxCoordinators.has(GUEST_BOT), false);
});

test("两个号一起轮询，谁先回来就先处理谁——不能等最慢的那个", async () => {
  const app = borrowApp();
  app.channelAdapter = stubAdapter([OWNER_BOT, GUEST_BOT]);
  let releaseSlow = null;
  const slow = new Promise((resolve) => { releaseSlow = resolve; });
  app.buildInboxCoordinator = (view) => ({
    pollOnce: async () => {
      if (view.accountId === GUEST_BOT) {
        await slow;
      }
      return { acceptedCount: 1, rejectedCount: 0 };
    },
  });
  app.durableInboxCoordinator = {
    pollOnce: async () => ({ acceptedCount: 2, rejectedCount: 0 }),
  };

  // 第一轮：主号回来了，访客那条还挂着。等齐了才返回的话这里会永远卡住。
  const first = await app.pollAccountsOnce({ timeoutMs: 1 });
  assert.deepEqual(first.map((entry) => entry.accountId), [OWNER_BOT]);
  assert.equal(first[0].durable.acceptedCount, 2);
  // 访客那条还在飞，不能被重发。
  assert.equal(app.accountPollsInFlight.size, 1);
  assert.equal(app.accountPollsInFlight.has(GUEST_BOT), true);

  releaseSlow();
  const second = await app.pollAccountsOnce({ timeoutMs: 1 });
  assert.equal(second.some((entry) => entry.accountId === GUEST_BOT), true);
});

test("同一个号不会同时挂两条长轮询——两条各拿同一个起始游标，提交会互相覆盖", async () => {
  const app = borrowApp();
  app.channelAdapter = stubAdapter([OWNER_BOT]);
  let started = 0;
  let release = null;
  const gate = new Promise((resolve) => { release = resolve; });
  app.durableInboxCoordinator = {
    pollOnce: async () => {
      started += 1;
      await gate;
      return { acceptedCount: 0, rejectedCount: 0 };
    },
  };

  // 两轮都在那条长轮询还挂着的时候进来。第二轮不许再发一条。
  const firstRound = app.pollAccountsOnce({ timeoutMs: 1 });
  const secondRound = app.pollAccountsOnce({ timeoutMs: 1 });
  assert.equal(started, 1, `那条还在飞，第二轮却又发了一条（共 ${started} 条）`);
  release();
  await Promise.all([firstRound, secondRound]);
  assert.equal(started, 1, `同一个号被同时拉了 ${started} 次`);
});

test("访客的号过期不致命，主人的号过期才致命", () => {
  const app = borrowApp();
  // 会话过期在这条链路上的真实形状是 ret/errcode = -14（见 app.js 的
  // SESSION_EXPIRED_ERRCODE）。别自己编一个 401，编出来的形状测不到真东西。
  const expired = new Error("weixin update rejected");
  expired.ret = -14;

  const guestOnly = app.classifyPollResults([
    { accountId: OWNER_BOT, durable: { acceptedCount: 0, rejectedCount: 0 } },
    { accountId: GUEST_BOT, error: expired },
  ]);
  assert.equal(guestOnly.ownerSessionExpired, false);
  assert.equal(guestOnly.anyOk, true);
  assert.equal(guestOnly.allFailedError, null, "还有一个号活着就不该退避");

  const ownerDown = app.classifyPollResults([
    { accountId: OWNER_BOT, error: expired },
    { accountId: GUEST_BOT, durable: { acceptedCount: 0, rejectedCount: 0 } },
  ]);
  assert.equal(ownerDown.ownerSessionExpired, true);
});

test("全部号都挂了才退避", () => {
  const app = borrowApp();
  const boom = new Error("network down");
  const verdict = app.classifyPollResults([
    { accountId: OWNER_BOT, error: boom },
    { accountId: GUEST_BOT, error: new Error("also down") },
  ]);
  assert.equal(verdict.anyOk, false);
  assert.equal(verdict.allFailedError, boom);
});

test("一个号一直拉不动的时候日志不刷屏——第一次必报，之后每 20 次报一次", () => {
  const app = borrowApp();
  const lines = [];
  const original = console.error;
  console.error = (line) => lines.push(line);
  try {
    for (let index = 0; index < 41; index += 1) {
      app.noteAccountPollFailure(GUEST_BOT, new Error("still down"));
    }
  } finally {
    console.error = original;
  }
  assert.equal(lines.length, 3, `报了 ${lines.length} 次`);
  assert.match(lines[0], /guest-bot/);
});

// ── 提醒必须覆盖所有号 ──────────────────────────────────────

test("第二个号下面的人定的提醒也会到点——以前只刷主号，它会永远躺在队列里", async () => {
  const app = Object.create(CyberbossApp.prototype);
  app.activeAccountId = OWNER_BOT;
  app.channelAdapter = stubAdapter([OWNER_BOT, GUEST_BOT]);
  const due = [
    { id: "r1", accountId: OWNER_BOT, senderId: OWNER_WECHAT, text: "主人的" },
    { id: "r2", accountId: GUEST_BOT, senderId: GUEST_WECHAT, text: "访客的" },
    { id: "r3", accountId: "已经删掉的号", senderId: "wxid_gone", text: "不该发" },
  ];
  app.reminderQueue = { listDue: () => due, enqueue: () => {} };
  const queued = [];
  app.systemMessageQueue = { enqueue: (entry) => queued.push(entry) };
  app.resolveReminderWorkspaceRoot = () => "/srv/fixture";
  app.config = { userName: "User" };

  await app.flushDueReminders();

  assert.deepEqual(queued.map((entry) => entry.senderId), [OWNER_WECHAT, GUEST_WECHAT]);
});
