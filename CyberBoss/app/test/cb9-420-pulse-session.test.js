"use strict";

// CB9-420 Owner Pulse 与 Companion Check-in 各自接同一 Session（AC-018 / FR-018）
//
// FR-018：「Owner 的随机脉冲唤醒同一 Boss Agent；Companion 的主动关心唤醒其
// 同一个人 Session，受同意、预算和安静时段约束。」
//
// AC-018 两半：
//   ① 各自恢复各自既有 Session —— 新开一个的话，模型不知道之前说过什么，
//      「主动关心」就变成了「陌生人搭讪」。
//   ② 禁用 / 安静时段 / 预算熔断时**发送数 = 0**。
//
// 第三条抑制（预算）在这个节点之前**根本没查**。主动问候不花用户的钱，但它花
// 的是同一份共享额度：熔断之后还继续主动找人，等于用可有可无的问候把「他真的
// 问一句话」那次调用挤掉了——而后者才是他要的。
//
// 时钟全部注入，一次系统时间都不读：读的话，这份测试在半夜跑和白天跑结论会
// 不一样，而不一样的那次你会以为是代码坏了。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { SystemMessageQueueStore } = require("../src/core/system-message-queue-store");
const { CyberbossApp } = require("../src/core/app");

const OWNER = "wx-owner";
const GUEST = "wx-guest";
const ALICE = `usr_${"a".repeat(24)}`;
const SESSION_A = `comp_${"1".repeat(32)}`;

// ── ① 会话身份跟着脉冲走 ──────────────────────────────────

test("AC-018 排队的脉冲带着会话身份，且能落盘熬过重启", (t) => {
  // 不落盘的话，进程一重启这条排着的问候就丢了归属——发出去时会新开一个会话。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-420-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "queue.json");

  new SystemMessageQueueStore({ filePath: file }).enqueue({
    id: "sys-1", accountId: "acct", senderId: GUEST, workspaceRoot: "/ws",
    text: "该问候一下了", createdAt: "2026-07-29T14:48:00.000Z",
    userScope: ALICE, sessionKey: SESSION_A, pulseKind: "companion_checkin",
  });

  // 换一个 store 读＝最接近重启。
  const reloaded = new SystemMessageQueueStore({ filePath: file }).drainAll();
  assert.equal(reloaded.length, 1);
  assert.equal(reloaded[0].userScope, ALICE, "user_scope 没落盘");
  assert.equal(reloaded[0].sessionKey, SESSION_A, "session_key 没落盘");
  assert.equal(reloaded[0].pulseKind, "companion_checkin");
});

test("AC-018 主人的脉冲和访客的关心在事件里分得开", (t) => {
  // 混在一起的话，「boss 是不是只找主人」这个问题又要靠翻队列文件来答。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-420-b-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const store = new SystemMessageQueueStore({ filePath: path.join(dir, "q.json") });
  const base = { accountId: "acct", workspaceRoot: "/ws", text: "x", createdAt: "2026-07-29T14:48:00.000Z" };
  store.enqueue({ ...base, id: "s1", senderId: OWNER, pulseKind: "owner_pulse" });
  store.enqueue({ ...base, id: "s2", senderId: GUEST, pulseKind: "companion_checkin" });
  const kinds = store.drainAll().map((m) => m.pulseKind).sort();
  assert.deepEqual(kinds, ["companion_checkin", "owner_pulse"]);
});

test("AC-018 认不出来的 pulseKind 落成空串，不静默改成某一类", (t) => {
  // 悄悄归到某一类的话，运维面上的两个计数会有一个是错的，而没人知道。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-420-c-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const store = new SystemMessageQueueStore({ filePath: path.join(dir, "q.json") });
  store.enqueue({
    id: "s1", accountId: "a", senderId: OWNER, workspaceRoot: "/ws", text: "x",
    createdAt: "2026-07-29T14:48:00.000Z", pulseKind: "something_else",
  });
  assert.equal(store.drainAll()[0].pulseKind, "");
});

test("AC-018 缺会话身份的脉冲照样能排，但如实标成空", (t) => {
  // 一条没有会话键的问候仍然比不发好。但它不能假装唤醒了什么。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-420-d-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const store = new SystemMessageQueueStore({ filePath: path.join(dir, "q.json") });
  const queued = store.enqueue({
    id: "s1", accountId: "a", senderId: GUEST, workspaceRoot: "/ws", text: "x",
    createdAt: "2026-07-29T14:48:00.000Z",
  });
  assert.equal(queued.userScope, "");
  assert.equal(queued.sessionKey, "");
});

// ── ② 三条抑制，发送数必须是 0 ────────────────────────────

test("AC-018 轮询器三条抑制齐了，且都排在 enqueue 之前", () => {
  // 排在之后就等于没有：排进去的消息一定会被发出去。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "app", "system-checkin-poller.js"), "utf8");
  const enqueueAt = src.indexOf("queue.enqueue({");
  assert.ok(enqueueAt > 0);
  const before = src.slice(0, enqueueAt);
  const gates = [
    { name: "禁用", pattern: /target\.settings\?\.enabled !== true/ },
    { name: "安静时段", pattern: /isQuietNow\(target\.settings, nowHour\(/ },
    { name: "资源降级", pattern: /allows\(readPressure\(\), capability\)/ },
    { name: "预算熔断", pattern: /budget\.ok !== true/ },
  ];
  for (const gate of gates) {
    assert.match(before, gate.pattern, `${gate.name} 这道闸不在 enqueue 之前`);
  }
});

test("AC-018 预算读不出来时按**不够**办，不按够办", () => {
  // 反过来的话，预算服务一挂主动消息就会不受限地发下去——而那正是最花钱的
  // 时候。和资源闸门的「没测过的地板不是满足的地板」是同一个道理。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "app", "system-checkin-poller.js"), "utf8");
  const block = src.slice(src.indexOf("let budget;"), src.indexOf("queue.enqueue({"));
  assert.match(block, /budget = \{ ok: false/, "读不出来时当成了额度充足");
  assert.match(block, /if \(!budget \|\| budget\.ok !== true\) \{\s*continue;/);
});

test("AC-018 proactiveBudgetFor 的失败态一律是 ok:false", () => {
  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    resolveUserIdForPersona: () => "",
  });
  assert.equal(app.proactiveBudgetFor(GUEST).ok, false, "认不出人也放行了");

  const throwing = Object.assign(Object.create(CyberbossApp.prototype), {
    resolveUserIdForPersona: () => { throw new Error("库挂了"); },
  });
  assert.equal(throwing.proactiveBudgetFor(GUEST).ok, false, "抛错时放行了");

  const exhausted = Object.assign(Object.create(CyberbossApp.prototype), {
    resolveUserIdForPersona: () => ALICE,
    modelBudgetGuard: { check: () => ({ allowed: false, reason: "daily_cap" }) },
  });
  const verdict = exhausted.proactiveBudgetFor(GUEST);
  assert.equal(verdict.ok, false);
  assert.equal(verdict.reason, "daily_cap");

  const fine = Object.assign(Object.create(CyberbossApp.prototype), {
    resolveUserIdForPersona: () => ALICE,
    modelBudgetGuard: { check: () => ({ allowed: true }) },
  });
  assert.equal(fine.proactiveBudgetFor(GUEST).ok, true);
});

test("AC-018 没装预算守卫的部署不被这条挡住", () => {
  // 本地跑 `cyberboss start --checkin` 时没有守卫。挡住的话，那条命令一条问候
  // 都发不出来，而用户看到的是「主动找我开了但它从来不找我」。
  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    resolveUserIdForPersona: () => ALICE,
  });
  const verdict = app.proactiveBudgetFor(GUEST);
  assert.equal(verdict.ok, true);
  assert.equal(verdict.reason, "no_guard");
});

// ── 假时钟：三条抑制各自把发送数压到 0 ────────────────────

// 轮询器是个长跑循环，整体拉起来测太重。这里复刻它那一段判定——判定逻辑本身
// 就是 AC-018 要的东西，而「这段判定真的在轮询器里、且在 enqueue 之前」由上面
// 那条结构性断言守住。两条合起来才是完整的。
function wouldSend({ enabled = true, hour = 14, quietStart = 23, quietEnd = 8,
  pressure = "normal", budget = { ok: true }, isOwner = false } = {}) {
  const { allows } = require("../src/services/operations/degradation-ladder");
  if (enabled !== true) return false;
  const quiet = quietStart < quietEnd
    ? hour >= quietStart && hour < quietEnd
    : hour >= quietStart || hour < quietEnd;
  if (quiet) return false;
  if (!allows(pressure, isOwner ? "owner_pulse" : "guest_proactive")) return false;
  if (!budget || budget.ok !== true) return false;
  return true;
}

test("AC-018 一切正常时会发", () => {
  assert.equal(wouldSend(), true, "四条闸门全开却不发——那这个功能根本不工作");
});

test("AC-018 关掉「主动找我」→ 发送数 0", () => {
  assert.equal(wouldSend({ enabled: false }), false);
  // 关掉之后，别的条件再好也不发。
  assert.equal(wouldSend({ enabled: false, hour: 14, pressure: "normal" }), false);
});

test("AC-018 安静时段 → 发送数 0（用假时钟遍历一天 24 小时）", () => {
  // 遍历而不是抽查：跨零点的区间（23→8）是这类判断最容易写反的地方，
  // 只测一个 hour 的话，写成 `hour >= 23 && hour < 8`（永远为假）也是绿的。
  const quiet = [];
  for (let hour = 0; hour < 24; hour += 1) {
    if (!wouldSend({ hour })) quiet.push(hour);
  }
  assert.deepEqual(quiet, [0, 1, 2, 3, 4, 5, 6, 7, 23],
    `安静时段算错了：${quiet.join(",")}`);
});

test("AC-018 不跨零点的安静区间也要对", () => {
  const quiet = [];
  for (let hour = 0; hour < 24; hour += 1) {
    if (!wouldSend({ hour, quietStart: 13, quietEnd: 15 })) quiet.push(hour);
  }
  assert.deepEqual(quiet, [13, 14]);
});

test("AC-018 预算熔断 → 发送数 0", () => {
  assert.equal(wouldSend({ budget: { ok: false, reason: "daily_cap" } }), false);
  assert.equal(wouldSend({ budget: null }), false);
  assert.equal(wouldSend({ budget: {} }), false, "缺 ok 字段被当成了通过");
});

test("AC-018 资源降级 → 访客先停，主人后停", () => {
  // 顺序是 CB9-320 那条冻结阶梯。这里验的是脉冲这一侧真的按它办。
  assert.equal(wouldSend({ pressure: "low", isOwner: false }), false, "访客的关心该先停");
  assert.equal(wouldSend({ pressure: "low", isOwner: true }), true, "主人的脉冲停早了");
  assert.equal(wouldSend({ pressure: "elevated", isOwner: true }), false, "主人的脉冲该停了");
});

test("AC-018 四条抑制里任意一条成立就是 0——不需要凑齐", () => {
  const suppressors = [
    { enabled: false },
    { hour: 2 },
    { pressure: "critical" },
    { budget: { ok: false } },
  ];
  for (const one of suppressors) {
    assert.equal(wouldSend(one), false, `${JSON.stringify(one)} 单独没能压住`);
  }
});

test("AC-018 轮询器**自己**把会话身份和脉冲类型填进了 enqueue", () => {
  // 变异测试抓到的缺口：上面那些测的是队列层（落盘）和判定逻辑（四条闸门），
  // 但没有任何一条覆盖「轮询器在 enqueue 的时候真的把这两个字段传下去了」。
  // 把 userScope 改成空串、把 pulseKind 写死成 owner_pulse，全部绿——因为
  // 队列层照样能正确处理它收到的东西，只是收到的东西是错的。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "app", "system-checkin-poller.js"), "utf8");
  const call = src.slice(src.indexOf("queue.enqueue({"),
    src.indexOf("});", src.indexOf("queue.enqueue({")));
  assert.match(call, /userScope: String\(session\.userScope \|\| ""\)/,
    "轮询器没把 user_scope 传下去——脉冲会唤醒一个新会话");
  assert.match(call, /sessionKey: String\(session\.sessionKey \|\| ""\)/);
  assert.match(call, /pulseKind: target\.isOwner \? "owner_pulse" : "companion_checkin"/,
    "主人和访客的脉冲被归成了同一类");
});

test("AC-018 会话是**读**出来的，不是每次现造一个", () => {
  // 现造的话每次都是新会话，AC-018 的「恢复各自既有 Session」就不成立——
  // 而这件事在队列层和判定层都看不出来。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "app", "system-checkin-poller.js"), "utf8");
  assert.match(src, /const readSession = typeof options\.readSession === "function"/);
  assert.match(src, /return readSession\(target\.senderId\) \|\| \{\}/);
  // app 那一侧注入的必须是**这个人**的稳定会话键，不是随手生成的。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const inject = app.slice(app.indexOf("readSession: (senderId)"),
    app.indexOf("readSession: (senderId)") + 400);
  assert.match(inject, /this\.companionSessionKeyFor\(userId\)/);
  assert.ok(!/randomUUID|Math\.random/.test(inject), "会话键是现造的，不是这个人固定的那一个");
});
