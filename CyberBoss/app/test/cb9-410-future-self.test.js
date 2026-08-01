"use strict";

// CB9-410 Future-self Reminder 接入同一 Session 与 lineage（AC-017 / FR-017）
//
// FR-017：「提醒触发时恢复创建提醒时的意图、上下文摘要、Session 和目标用户，
// 而不是只发送固定字符串。」
//
// AC-017 三条，各自要挡一种真实会发生的坏法：
//
//   ① 触发时读得到创建时的意图摘要和 session_key
//        —— 读不到的话，到点只能吐一句「到点了」，模型不知道为什么。
//   ② 删除原消息不导致跨用户恢复
//        —— 触发时才去推导身份的实现，在原消息被删或多号场景下会推给另一个人。
//   ③ 固定字符串路径不冒充 Agent 唤醒
//        —— 把 direct 记成 agent 唤醒，排查时会看到一次根本没发生过的模型调用。
//           假记录比没有记录更难查。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  buildAgentWakePrompt,
  buildFiredEvent,
  restoreContext,
  wakeKindOf,
} = require("../src/services/reminder/future-self");
const { ReminderQueueStore } = require("../src/adapters/channel/weixin/reminder-queue-store");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { UserAdmissionService } = require("../src/core/user-admission");
const { CyberbossApp } = require("../src/core/app");

const ALICE = `usr_${"a".repeat(24)}`;
const BOB = `usr_${"b".repeat(24)}`;
const SESSION_A = `comp_${"1".repeat(32)}`;
const SESSION_B = `comp_${"2".repeat(32)}`;
const AT = new Date("2026-07-29T14:48:00.000Z");

const reminder = (over = {}) => ({
  id: "rem-1", accountId: "acct", senderId: "wx-1", contextToken: "ctx",
  text: "到点了，喝水。", dueAtMs: AT.getTime(), createdAt: "2026-07-29T14:38:00.000Z",
  userScope: ALICE, sessionKey: SESSION_A, intent: "喝水", direct: false, ...over,
});

// ── ① 触发时读得到创建时的东西 ─────────────────────────────

test("AC-017 到点时能读回创建时的意图摘要和 session_key", () => {
  const restored = restoreContext(reminder());
  assert.equal(restored.wake_kind, "agent");
  assert.equal(restored.session_key, SESSION_A);
  assert.equal(restored.intent, "喝水");
  assert.equal(restored.user_scope, ALICE);
  assert.equal(restored.created_at, "2026-07-29T14:38:00.000Z");
  assert.ok(Object.isFrozen(restored));
});

test("AC-017 这三样在**存**的时候就落盘，不是触发时补的", (t) => {
  // 落不了盘的话，进程一重启这条提醒就退化成一句固定字符串——而重启是常态。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-410-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "reminders.json");
  new ReminderQueueStore({ filePath: file }).enqueue(reminder());

  // 换一个进程读（新建一个 store 就是最接近重启的模拟）。
  const reloaded = new ReminderQueueStore({ filePath: file }).listDue(AT.getTime() + 1);
  assert.equal(reloaded.length, 1);
  assert.equal(reloaded[0].userScope, ALICE, "user_scope 没落盘");
  assert.equal(reloaded[0].sessionKey, SESSION_A, "session_key 没落盘");
  assert.equal(reloaded[0].intent, "喝水", "意图摘要没落盘");
});

test("AC-017 缺字段落盘成空串而不是消失", (t) => {
  // JSON 里 undefined 会让整个字段消失，而消失的字段和「这个人没有会话」在
  // 读回来的时候长得一模一样——排查时分不出是没存还是存了个空。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-410-b-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "reminders.json");
  new ReminderQueueStore({ filePath: file })
    .enqueue(reminder({ userScope: undefined, sessionKey: undefined, intent: undefined }));
  const raw = JSON.parse(fs.readFileSync(file, "utf8"));
  const row = raw.reminders[0];
  assert.equal(row.userScope, "");
  assert.equal(row.sessionKey, "");
  assert.equal(row.intent, "");
});

test("AC-017 交给模型的那段话把「当时」和「现在」分开", () => {
  // 混在一起的话，模型会把一件过去的约定当成用户此刻发来的新指令去执行。
  const prompt = buildAgentWakePrompt(reminder(), { nowLabel: "2026-07-29 22:48 北京时间" });
  assert.match(prompt, /不是用户刚发来的消息/);
  assert.match(prompt, /2026-07-29T14:38/, "没说是什么时候让记的");
  // 钉住**那一行**，不是「文中出现过喝水」。
  // 第一版写成 /喝水/ 就被下一行的「到点该说的那句：到点了，喝水。」满足了——
  // 于是「唤醒提示词不带当时的意图」这一刀是活的：意图那行整个删掉，断言照样
  // 通过。两行说的是两件事：一个是他当时**要什么**，一个是到点**说什么**。
  assert.match(prompt, /当时他要的是：喝水/, "没带上当时的意图");
  assert.match(prompt, /到点该说的那句：/, "没带上到点要说的话");
  const intentless = buildAgentWakePrompt(reminder({ intent: "" }), { nowLabel: "x" });
  assert.ok(!/当时他要的是/.test(intentless), "没有意图时不该硬凑一行空的");
  assert.match(prompt, /不要当成一条新指令/);
});

test("AC-017 意图摘要有长度上限——它会进模型上下文", () => {
  const long = reminder({ intent: "字".repeat(500) });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-410-c-"));
  const store = new ReminderQueueStore({ filePath: path.join(dir, "r.json") });
  const saved = store.enqueue(long);
  assert.ok(saved.intent.length <= 200, `意图摘要 ${saved.intent.length} 字，没截断`);
  fs.rmSync(dir, { recursive: true, force: true });
});

// ── ② 删除原消息不导致跨用户恢复 ───────────────────────────

test("AC-017 恢复只看这条记录，一个字段都不重新推导", () => {
  // 这是「删除原消息不导致跨用户恢复」唯一可靠的实现方式：不去查原消息，
  // 就不可能查错人。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "reminder", "future-self.js"), "utf8");
  const code = src.split("\n").map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1")).join("\n");
  for (const lookup of ["listRecentInbound", "resolveByPrincipal", "identify(", "resolveUserIdForPersona"]) {
    assert.ok(!code.includes(lookup), `触发时又去查了 ${lookup}——原消息删了就会查错人`);
  }
});

test("AC-017 两个人的提醒各回各的会话，不会串", () => {
  const a = restoreContext(reminder({ id: "r-a", userScope: ALICE, sessionKey: SESSION_A }));
  const b = restoreContext(reminder({ id: "r-b", userScope: BOB, sessionKey: SESSION_B }));
  assert.equal(a.session_key, SESSION_A);
  assert.equal(b.session_key, SESSION_B);
  assert.notEqual(a.user_scope, b.user_scope);
});

test("AC-017 缺身份或缺会话的记录判成 orphan，不硬着头皮唤醒", () => {
  // 硬唤醒的两种做法都更糟：用一个猜出来的身份（可能是别人），或者新开一个
  // 会话（模型不知道之前说过什么）。如实说它成了孤儿，排查时才有得查。
  assert.equal(wakeKindOf(reminder({ userScope: "" })), "orphan");
  assert.equal(wakeKindOf(reminder({ sessionKey: "" })), "orphan");
  assert.equal(wakeKindOf(reminder({ userScope: "", sessionKey: "" })), "orphan");
  assert.equal(wakeKindOf(null), "orphan");
  assert.equal(buildAgentWakePrompt(reminder({ sessionKey: "" })), "",
    "孤儿记录不该生成唤醒提示词");
});

test("AC-017 孤儿也要有事件——「那条提醒为什么没响」是最想知道的", () => {
  const event = buildFiredEvent(reminder({ userScope: "" }), { at: AT });
  assert.equal(event.type, "reminder_fired");
  assert.equal(event.status, "failed");
  assert.equal(event.intent, "orphan_reminder");
  assert.equal(event.public_payload.wake_kind, "orphan");
  assert.equal(event.public_payload.reason, "missing_scope_or_session");
  // 没有身份也要能被检索到。
  assert.match(event.user_scope, /^orphan_rem-1$/);
});

// ── ③ 固定字符串不冒充 Agent 唤醒 ─────────────────────────

test("AC-017 direct 那条路记成 fixed_string，不是 agent_wake", () => {
  // 记错的后果：排查时看到一次根本没发生过的模型调用。假记录比没有记录更难查。
  const direct = buildFiredEvent(reminder({ direct: true }), { at: AT });
  assert.equal(direct.intent, "fixed_string");
  assert.equal(direct.public_payload.wake_kind, "direct");
  assert.equal(direct.mode, "SYSTEM", "固定字符串走的不该是 COMPANION 模式");

  const agent = buildFiredEvent(reminder({ direct: false }), { at: AT });
  assert.equal(agent.intent, "agent_wake");
  assert.equal(agent.public_payload.wake_kind, "agent");
  assert.equal(agent.mode, "COMPANION");
});

test("AC-017 direct 记录不生成唤醒提示词——它根本不该碰模型", () => {
  assert.equal(buildAgentWakePrompt(reminder({ direct: true })), "");
  assert.equal(wakeKindOf(reminder({ direct: true })), "direct");
  // 就算它带着完整的身份和会话，direct 也压过一切：那一位是「怎么响」的裁决。
  assert.equal(wakeKindOf(reminder({ direct: true, userScope: ALICE, sessionKey: SESSION_A })), "direct");
});

test("AC-017 has_intent 是运维面唯一看得见的「不是固定字符串」证据", () => {
  assert.equal(buildFiredEvent(reminder({ intent: "喝水" }), { at: AT }).public_payload.has_intent, true);
  assert.equal(buildFiredEvent(reminder({ intent: "" }), { at: AT }).public_payload.has_intent, false);
});

test("AC-017 同一条提醒只响一次——重放拿到同一个 event_id", () => {
  const first = buildFiredEvent(reminder(), { at: AT });
  const replay = buildFiredEvent(reminder(), { at: new Date(AT.getTime() + 5000) });
  assert.equal(first.event_id, replay.event_id, "重放算出了第二个 event_id");
  assert.notEqual(first.event_id, buildFiredEvent(reminder({ id: "rem-2" }), { at: AT }).event_id);
});

test("AC-017 事件的公开载荷里没有那句提醒原文", () => {
  // 提醒内容是私聊。运维面要知道「响了、是哪一类」，不需要知道说了什么。
  const event = buildFiredEvent(reminder({ text: "到点了，去医院复查。" }), { at: AT });
  assert.ok(!JSON.stringify(event.public_payload).includes("医院"), "提醒原文进了公开载荷");
});

// ── 接线：创建时真的把三样存进去了 ─────────────────────────

test("AC-017 会话键真的算得出来——不是永远返回空串", (t) => {
  // identityKey 构造完就被清零了（有意的）。第一版我去找它，于是每条提醒都会
  // 变成 orphan——模块写好了、单测全绿、线上一条 agent 唤醒都没有。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-410-d-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(dir, "runtime.db"),
    encryptionKey: Buffer.alloc(32, 11), identityKey: Buffer.alloc(32, 13),
  });
  t.after(() => { try { spool.close(); } catch { /* 已关 */ } });
  const admission = new UserAdmissionService({
    database: spool.database, identityKey: Buffer.alloc(32, 13),
    ownerUserId: spool.ownerUserId, ownerSenderIds: ["owner"], registrationMode: "open",
  });
  const app = Object.assign(Object.create(CyberbossApp.prototype), { userAdmission: admission });

  const key = app.companionSessionKeyFor(ALICE);
  assert.match(key, /^comp_[0-9a-f]{32}$/, `算不出会话键：${JSON.stringify(key)}`);
  assert.equal(key, app.companionSessionKeyFor(ALICE), "跨调用不稳定");
  assert.notEqual(key, app.companionSessionKeyFor(BOB), "两个人拿到同一个会话键");
  assert.ok(!key.includes(ALICE), "会话键里带出了 user_id");
  // 没有准入层时返回空串而不是抛：提醒必须能建出来。
  assert.equal(Object.assign(Object.create(CyberbossApp.prototype), {}).companionSessionKeyFor(ALICE), "");
});

test("AC-017 派生的是子钥，不是把 identityKey 传出去", () => {
  // 传出去的话，任何一个拿到它的模块都能伪造任何身份。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "core", "user-admission.js"), "utf8");
  assert.match(src, /companionSessionSecret = deriveSubKey\(identityKey, "cyberboss-companion-session-secret"\)/);
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  assert.match(app, /this\.userAdmission\?\.companionSessionSecret/);
  assert.ok(!/userAdmission\?\.identityKey|users\.identityKey/.test(app), "app 里直接摸了 identityKey");
});

test("AC-017 创建提醒时三样都填了——不是留给触发时", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const block = src.slice(src.indexOf("this.reminderQueue.enqueue({"),
    src.indexOf("this.reminderQueue.enqueue({") + 900);
  assert.match(block, /userScope: reminderUserId \|\| ""/);
  assert.match(block, /sessionKey: reminderUserId \? this\.companionSessionKeyFor\(reminderUserId\) : ""/);
  assert.match(block, /intent: intent\.body \|\| ""/);
});
