"use strict";

// 解析器对不对是一回事，**它在线上跑不跑得到**是另一回事。
//
// 这个仓已经在同一件事上栽过七次：runUserModelTurn 写好了但只挂在 durable 之外
// 那条分支上、context_token 从来没被记过、主动打招呼的倒计时只活在内存里⋯⋯
// 每一次单元测试都是绿的，每一次线上都没发生。
//
// 所以这一份不测 parseReminderIntent，测的是：一条微信真的走进
// admissionHandledBeforeJob 之后，队列里有没有多出来一条；到点之后
// flushDueReminders 有没有真的把它发出去，而且**没有唤醒模型**。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { ReminderQueueStore } = require("../src/adapters/channel/weixin/reminder-queue-store");
const { CyberbossApp } = require("../src/core/app");

const OWNER_WECHAT = "wx-owner";
const OWNER_BOT = "5552be32014a-im.bot";
const GUEST_WECHAT = "wx-guest";
const GUEST_BOT = "18bb28ef8228-im.bot";

function queueIn(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-reminder-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return new ReminderQueueStore({ filePath: path.join(directory, "reminder-queue.json") });
}

// 一个刚好够走完这条路的 app：准入认得出人，出站记得下发了什么。
function bootApp(t, { route = "owner" } = {}) {
  const app = Object.create(CyberbossApp.prototype);
  const sent = [];
  app.reminderQueue = queueIn(t);
  app.userAdmission = {
    admit: () => ({ route, userContext: { userId: "usr_x" }, ownerClaimed: false }),
  };
  app.channelAdapter = {
    rememberContextToken: () => "",
    sendText: async (args) => { sent.push(args); },
  };
  app.noteBotInitiated = () => true;
  app.noteDirectReply = () => true;
  app.noteForDashboard = () => {};
  app.sent = sent;
  return app;
}

function inbound(text, overrides = {}) {
  return {
    senderId: OWNER_WECHAT,
    accountId: OWNER_BOT,
    contextToken: "ctx-owner",
    text,
    ...overrides,
  };
}

// ── 一、这条消息要在准入层就被办掉，不进 job 队列 ────────────

test("「1分钟后提醒我」在准入层就办完了，不排队、不唤醒模型", async (t) => {
  const app = bootApp(t);

  const handled = app.admissionHandledBeforeJob(inbound("1分钟后提醒我"));

  assert.equal(handled, true, "返回 false 就会进 job 队列，又要等模型决定要不要建");
  const queued = app.reminderQueue.listDue(Date.now() + 120_000);
  assert.equal(queued.length, 1, "队列里没有东西＝主人又白等一场");
  assert.equal(queued[0].direct, true);
  assert.equal(queued[0].senderId, OWNER_WECHAT);
  assert.equal(queued[0].accountId, OWNER_BOT);
  assert.equal(queued[0].contextToken, "ctx-owner");
});

test("建完当场回一句确认，而不是等到点才让主人知道", async (t) => {
  const app = bootApp(t);

  app.admissionHandledBeforeJob(inbound("10分钟后提醒我喝水"));
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(app.sent.length, 1);
  assert.match(app.sent[0].text, /^好，\d{2}:\d{2} 提醒你喝水。$/);
  assert.equal(app.sent[0].accountId, OWNER_BOT, "用收到它的那个号回");
});

test("普通用户也能定——提醒不是主人的特权", async (t) => {
  const app = bootApp(t, { route: "user" });

  const handled = app.admissionHandledBeforeJob(inbound("20分钟后提醒我", {
    senderId: GUEST_WECHAT,
    accountId: GUEST_BOT,
    contextToken: "ctx-guest",
  }));

  assert.equal(handled, true);
  const queued = app.reminderQueue.listDue(Date.now() + 30 * 60_000);
  assert.equal(queued.length, 1);
  assert.equal(queued[0].accountId, GUEST_BOT, "访客的提醒必须挂在访客那个号下面");
});

test("认不出来就放行，交回模型——不能把闲聊吃掉", (t) => {
  const app = bootApp(t);

  for (const text of ["我三点才下班", "今天好累", "提醒我买菜"]) {
    assert.equal(
      app.admissionHandledBeforeJob(inbound(text)),
      false,
      `「${text}」被当成提醒吃掉了，主人会觉得机器人不理他`,
    );
  }
  assert.equal(app.reminderQueue.listDue(Date.now() + 86_400_000).length, 0);
});

test("没有 context_token 就不接这一单——答应了却投不出去更糟", (t) => {
  const app = bootApp(t);

  const handled = app.admissionHandledBeforeJob(inbound("5分钟后提醒我", {
    contextToken: "",
  }));

  assert.equal(handled, false);
  assert.equal(app.reminderQueue.listDue(Date.now() + 86_400_000).length, 0);
});

test("刚绑上主人的那一句不解析——那一轮该说的是「绑好了」", (t) => {
  const app = bootApp(t);
  app.userAdmission = {
    admit: () => ({ route: "owner", userContext: {}, ownerClaimed: true }),
  };
  app.rememberOwnerSender = () => {};

  app.admissionHandledBeforeJob(inbound("1分钟后提醒我"));

  assert.equal(app.reminderQueue.listDue(Date.now() + 86_400_000).length, 0);
});

// ── 二、到点必须真的发出去，而且不经过模型 ─────────────────

test("到点了直接发，一次模型都不调", async (t) => {
  const app = bootApp(t);
  const systemQueued = [];
  app.liveAccountIds = () => [OWNER_BOT];
  app.systemMessageQueue = { enqueue: (message) => { systemQueued.push(message); } };
  app.reminderQueue.enqueue({
    id: "rem-1",
    accountId: OWNER_BOT,
    senderId: OWNER_WECHAT,
    contextToken: "ctx-owner",
    text: "到点了，喝水。",
    dueAtMs: Date.now() - 1_000,
    createdAt: new Date().toISOString(),
    direct: true,
  });

  await app.flushDueReminders();

  assert.equal(app.sent.length, 1, "到点没发＝这次修的病原样复发");
  assert.equal(app.sent[0].text, "到点了，喝水。");
  assert.equal(app.sent[0].contextToken, "ctx-owner");
  assert.equal(
    systemQueued.length,
    0,
    "走系统消息队列就等于唤醒模型，而模型每五分钟就静默一次——提醒没有重新判断的余地",
  );
});

test("模型建的那种照旧走系统消息队列，两条路不能混", async (t) => {
  const app = bootApp(t);
  const systemQueued = [];
  app.liveAccountIds = () => [OWNER_BOT];
  app.systemMessageQueue = { enqueue: (message) => { systemQueued.push(message); } };
  app.resolveReminderWorkspaceRoot = () => "/srv/w";
  app.config = { userName: "Linz" };
  app.reminderQueue.enqueue({
    id: "rem-2",
    accountId: OWNER_BOT,
    senderId: OWNER_WECHAT,
    contextToken: "ctx-owner",
    text: "看看他今天怎么样",
    dueAtMs: Date.now() - 1_000,
    createdAt: new Date().toISOString(),
    // direct 没给＝模型建的
  });

  await app.flushDueReminders();

  assert.equal(systemQueued.length, 1);
  assert.equal(app.sent.length, 0);
});

test("发失败要重排，不能默默丢掉", async (t) => {
  const app = bootApp(t);
  app.liveAccountIds = () => [OWNER_BOT];
  app.channelAdapter.sendText = async () => {
    const error = new Error("nope");
    error.code = "WEIXIN_CONTEXT_REQUIRED";
    throw error;
  };
  app.reminderQueue.enqueue({
    id: "rem-3",
    accountId: OWNER_BOT,
    senderId: OWNER_WECHAT,
    contextToken: "ctx-owner",
    text: "到点了。",
    dueAtMs: Date.now() - 1_000,
    createdAt: new Date().toISOString(),
    direct: true,
  });

  await app.flushDueReminders();

  const rescheduled = app.reminderQueue.listDue(Date.now() + 120_000);
  assert.equal(rescheduled.length, 1, "投递失败就消失＝主人定了提醒，然后什么都没有");
  assert.equal(rescheduled[0].attempts, 1);
});

test("重排到第四次就放弃，不无限重试", async (t) => {
  const app = bootApp(t);
  app.liveAccountIds = () => [OWNER_BOT];
  app.channelAdapter.sendText = async () => { throw new Error("nope"); };
  app.reminderQueue.enqueue({
    id: "rem-4",
    accountId: OWNER_BOT,
    senderId: OWNER_WECHAT,
    contextToken: "ctx-owner",
    text: "到点了。",
    dueAtMs: Date.now() - 1_000,
    createdAt: new Date().toISOString(),
    direct: true,
    attempts: 3,
  });

  await app.flushDueReminders();

  assert.equal(app.reminderQueue.listDue(Date.now() + 86_400_000).length, 0);
});

test("别的号下面的提醒不归这个进程发", async (t) => {
  const app = bootApp(t);
  app.liveAccountIds = () => [OWNER_BOT];
  app.systemMessageQueue = { enqueue: () => {} };
  app.reminderQueue.enqueue({
    id: "rem-5",
    accountId: "别的号-im.bot",
    senderId: GUEST_WECHAT,
    contextToken: "ctx-guest",
    text: "到点了。",
    dueAtMs: Date.now() - 1_000,
    createdAt: new Date().toISOString(),
    direct: true,
  });

  await app.flushDueReminders();

  assert.equal(app.sent.length, 0);
});
