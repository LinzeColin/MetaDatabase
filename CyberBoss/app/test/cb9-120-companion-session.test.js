"use strict";

// CB9-120 Companion 稳定 Session 与有界上下文（AC-004 / AC-038 / AC-044）
//
//   AC-004 连续上下文：同一普通用户连续两轮，第二轮引用第一轮已确认事实；
//          session_key 相同；另一用户无法读取。
//   AC-038 上下文有界：只含同用户最近窗口、已确认事实、未完成事项和近期
//          Timeline；超预算按**冻结优先级**截断。
//   AC-044 跨会话恢复：服务重启后恢复稳定 session_key 和最近已确认事实，
//          且不会加载其他用户。
//
// 在这个模块之前，普通用户这条路是完全无状态的（runUserModelTurn 只传
// contextToken）。所以这三条以前不是"没测"，是**不可能成立**。

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  DEFAULTS,
  EVICTION_ORDER,
  buildBoundedContext,
  stableSessionKey,
} = require("../src/services/companion/companion-session-context");

const SECRET = "x".repeat(32);
const ALICE = `usr_${"a".repeat(24)}`;
const BOB = `usr_${"b".repeat(24)}`;

const turn = (scope, text, i = 0) => ({ user_scope: scope, text, seq: i });
const fact = (scope, text) => ({ user_scope: scope, fact: text, accepted: true });

// ── AC-044 跨重启稳定 ───────────────────────────────────────

test("AC-044 session_key 跨重启不变——同一个人永远是同一个 Agent", () => {
  // 用随机数或内存 Map 的实现在这里会红：进程一重启这个人就换了个 Agent，
  // 而用户侧看到的是"它忘了我是谁"。
  const first = stableSessionKey(ALICE, SECRET);
  const afterRestart = stableSessionKey(ALICE, SECRET);
  assert.equal(afterRestart, first);
  assert.match(first, /^comp_[0-9a-f]{32}$/);
});

test("AC-044 不同用户必须是不同 session_key", () => {
  assert.notEqual(stableSessionKey(ALICE, SECRET), stableSessionKey(BOB, SECRET));
});

test("AC-044 session_key 不能反推出 user_id——它会进日志和证据", () => {
  const key = stableSessionKey(ALICE, SECRET);
  assert.ok(!key.includes(ALICE), "session_key 里出现了原始 user_id");
  assert.ok(!key.includes(ALICE.slice(4, 16)), "session_key 里出现了 user_id 片段");
});

test("AC-044 弱 secret 直接拒绝，不静默降级", () => {
  assert.throws(() => stableSessionKey(ALICE, "short"), TypeError);
  assert.throws(() => stableSessionKey("", SECRET), TypeError);
});

// ── AC-004 连续上下文 + 跨用户隔离 ──────────────────────────

test("AC-004 第二轮能看到第一轮已确认的事实", () => {
  const key = stableSessionKey(ALICE, SECRET);
  const ctx = buildBoundedContext({
    userScope: ALICE,
    sessionKey: key,
    turns: [turn(ALICE, "我下周三要去广州", 1)],
    acceptedFacts: [fact(ALICE, "用户下周三在广州")],
  });
  assert.equal(ctx.session_key, key);
  assert.equal(ctx.turns.length, 1);
  assert.equal(ctx.accepted_facts[0].fact, "用户下周三在广州");
});

test("AC-004 另一个用户的行一条都进不来", () => {
  const ctx = buildBoundedContext({
    userScope: ALICE,
    sessionKey: stableSessionKey(ALICE, SECRET),
    turns: [turn(ALICE, "我的"), turn(BOB, "别人的"), turn(undefined, "无主的")],
    acceptedFacts: [fact(BOB, "别人的事实"), fact(ALICE, "我的事实")],
    unresolvedItems: [{ user_scope: BOB, item: "别人的待办" }],
    timeline: [{ user_scope: BOB, event: "别人的事件" }],
  });
  const all = JSON.stringify(ctx);
  assert.ok(!all.includes("别人的"), "别的用户的内容进了上下文");
  assert.ok(!all.includes("无主的"), "没有 user_scope 的行也应被拒");
  assert.equal(ctx.turns.length, 1);
  assert.equal(ctx.accepted_facts.length, 1);
  assert.equal(ctx.unresolved_items.length, 0);
  assert.equal(ctx.recent_timeline.length, 0);
});

test("AC-004 上下文是深冻结的，下游改不动", () => {
  const ctx = buildBoundedContext({
    userScope: ALICE, sessionKey: stableSessionKey(ALICE, SECRET),
    turns: [turn(ALICE, "一句话")],
  });
  assert.ok(Object.isFrozen(ctx));
  assert.ok(Object.isFrozen(ctx.turns[0]), "嵌套对象没冻结，下游可以就地改");
});

test("AC-004 上下文与源数组脱钩——事后改源数据不能改已建好的上下文", () => {
  const rows = [turn(ALICE, "原文")];
  const ctx = buildBoundedContext({
    userScope: ALICE, sessionKey: stableSessionKey(ALICE, SECRET), turns: rows,
  });
  rows[0].text = "被改过";
  assert.equal(ctx.turns[0].text, "原文");
});

// ── AC-038 有界 ─────────────────────────────────────────────

test("AC-038 条数超限时只保留最近的窗口", () => {
  const many = Array.from({ length: 100 }, (_, i) => turn(ALICE, `第${i}轮`, i));
  const ctx = buildBoundedContext({
    userScope: ALICE, sessionKey: stableSessionKey(ALICE, SECRET),
    turns: many, maxTurns: 5,
  });
  assert.equal(ctx.turns.length, 5);
  assert.equal(ctx.turns[0].seq, 95, "保留的不是最近 5 条");
  assert.equal(ctx.turns[4].seq, 99);
});

test("AC-038 上限 0 就是 0，不能悄悄放开成全部", () => {
  const ctx = buildBoundedContext({
    userScope: ALICE, sessionKey: stableSessionKey(ALICE, SECRET),
    turns: [turn(ALICE, "a"), turn(ALICE, "b")], maxTurns: 0,
  });
  assert.equal(ctx.turns.length, 0);
});

test("AC-038 单条过大的行被丢掉，不拖垮整个上下文", () => {
  const huge = { user_scope: ALICE, text: "字".repeat(20000) };
  const ctx = buildBoundedContext({
    userScope: ALICE, sessionKey: stableSessionKey(ALICE, SECRET),
    turns: [turn(ALICE, "正常"), huge], maxItemBytes: 1024,
  });
  assert.equal(ctx.turns.length, 1);
  assert.equal(ctx.turns[0].text, "正常");
});

test("AC-038 总字节超限时按冻结优先级逐出，身份永不丢", () => {
  // 逐出顺序：turns → recent_timeline → unresolved_items → accepted_facts。
  // 已确认事实最后才动——它是"这个人是谁"的一部分，比闲聊值钱。
  const bulk = (scope, n, tag) =>
    Array.from({ length: n }, (_, i) => ({ user_scope: scope, text: `${tag}${"填".repeat(200)}${i}` }));
  const ctx = buildBoundedContext({
    userScope: ALICE, sessionKey: stableSessionKey(ALICE, SECRET),
    turns: bulk(ALICE, 20, "轮次"),
    acceptedFacts: bulk(ALICE, 20, "事实"),
    maxContextBytes: 8 * 1024,
  });
  assert.ok(Buffer.byteLength(JSON.stringify(ctx), "utf8") <= 8 * 1024);
  assert.equal(ctx.user_scope, ALICE, "身份被逐出了");
  assert.equal(ctx.session_key.startsWith("comp_"), true);
  assert.ok(ctx.forbidden_capabilities.length > 0, "能力策略被逐出了");
  assert.ok(
    ctx.accepted_facts.length >= ctx.turns.length,
    `逐出顺序反了：turns=${ctx.turns.length} facts=${ctx.accepted_facts.length}`,
  );
});

test("AC-038 逐出顺序是冻结的常量，不能被调用方改", () => {
  assert.deepEqual(EVICTION_ORDER, ["turns", "recent_timeline", "unresolved_items", "accepted_facts"]);
  assert.ok(Object.isFrozen(EVICTION_ORDER));
});

test("AC-038 缺身份直接拒绝，不建一个没有归属的上下文", () => {
  assert.throws(() => buildBoundedContext({ sessionKey: "comp_x" }), TypeError);
  assert.throws(() => buildBoundedContext({ userScope: ALICE }), TypeError);
  assert.throws(() => buildBoundedContext(), TypeError);
});

test("AC-038 默认上限存在且不是无穷大", () => {
  for (const [k, v] of Object.entries(DEFAULTS)) {
    assert.ok(Number.isInteger(v) && v > 0, `${k} 不是正整数上限`);
  }
});
