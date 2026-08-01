"use strict";

// CB9-430 日记与 Timeline 投影，零模型（AC-019 / AC-020 / AC-043 / FR-019）
//
//   AC-019 有事件时生成一次日记且 model_calls=0；无新事件时文件/事实/提交
//          变化数=0。
//
// 两条各挡一件事：
//
//   零模型 —— 一天一次调用看起来不多，但日记是**每个人每天**都要写的。更糟的
//     是模型会编：它会补出一件今天没发生过的事，而日记正是主人日后拿来回忆
//     的东西。
//   无新事件不产空文件 —— 空条目让「他那天没用」和「那天没记上」变得分不清，
//     而且备份和同步每天多一次无谓变更。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const {
  DIARY_WORTHY,
  hasChanged,
  isStable,
  projectDiary,
} = require("../src/services/timeline/diary-projection");
const { makeSessionEvent } = require("../src/services/timeline/session-event");

const ALICE = `usr_${"a".repeat(24)}`;
const BOB = `usr_${"b".repeat(24)}`;
const SESSION = `comp_${"1".repeat(32)}`;
const DAY = "2026-07-29";

let seq = 0;
const event = (type, hourUtc, over = {}) => makeSessionEvent({
  type, mode: "COMPANION", userScope: ALICE, sessionKey: SESSION,
  idempotencyKey: `k-${seq += 1}`,
  at: new Date(`2026-07-29T${String(hourUtc).padStart(2, "0")}:00:00.000Z`),
  ...over,
});

// ── AC-019 零模型 ─────────────────────────────────────────

test("AC-019 日记模块从头到尾够不着模型", () => {
  // 「零模型」的保证不是「我们没调」，是「够不着」。测出来 0 次是今天的样本，
  // 够不着是永远的性质。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "timeline", "diary-projection.js"), "utf8");
  const requires = [...src.matchAll(/require\("([^"]+)"\)/g)].map((m) => m[1]);
  assert.deepEqual(requires, ["./session-event"],
    `日记模块 require 了别的东西：${requires.join(", ")}`);
  const code = src.split("\n").map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1")).join("\n");
  for (const hint of ["runtimeAdapter", "provider", "fetch(", "http"]) {
    assert.ok(!code.includes(hint), `日记模块里出现了 ${hint}`);
  }
});

test("AC-019 有事件时生成一次日记，model_calls=0", () => {
  const projected = projectDiary({
    events: [event("message", 1), event("task", 2), event("message", 3)],
    userScope: ALICE, date: DAY,
  });
  assert.ok(projected, "有事件却没生成日记");
  assert.equal(projected.model_calls, 0);
  assert.equal(projected.event_count, 3);
  assert.match(projected.body, /聊了 2 次/);
  assert.match(projected.body, /办了一件事/);
});

test("AC-019 数量为 1 时读起来是人话，不是「1 次」", () => {
  // 模板拼变量的句子在 1 和 0 上都很别扭，而日记是给人读的。
  const one = projectDiary({ events: [event("message", 1)], userScope: ALICE, date: DAY });
  assert.match(one.body, /聊了一次/);
  assert.ok(!/聊了 1 次/.test(one.body), `读起来像机器：${one.body}`);
});

// ── AC-019 无新事件 → 变化数 0 ────────────────────────────

test("AC-019 一件事都没有时返回 null，不是一个空条目", () => {
  // 返回空条目让调用方判断的话，总有一个调用方会忘——而忘掉的后果是每天
  // 多一个空文件。
  assert.equal(projectDiary({ events: [], userScope: ALICE, date: DAY }), null);
  assert.equal(projectDiary({ events: undefined, userScope: ALICE, date: DAY }), null);
});

test("AC-019 只有运维事件时也不写——那不是「我那天做了什么」", () => {
  // 投递重试、降级、恢复是运维事件。写进日记的话，真正有用的两三条会被淹掉。
  const ops = [event("delivery", 1), event("degraded", 2), event("recovery", 3), event("pulse", 4)];
  assert.equal(projectDiary({ events: ops, userScope: ALICE, date: DAY }), null);
  // 反面：DIARY_WORTHY 里的那几类必须真的能触发。
  for (const type of DIARY_WORTHY) {
    assert.ok(projectDiary({ events: [event(type, 1)], userScope: ALICE, date: DAY }),
      `${type} 在名单里却不触发日记`);
  }
});

test("AC-019 别人的事件不进我的日记", () => {
  const mixed = [
    event("message", 1),
    event("message", 2, { userScope: BOB, sessionKey: `comp_${"2".repeat(32)}` }),
  ];
  const mine = projectDiary({ events: mixed, userScope: ALICE, date: DAY });
  assert.equal(mine.event_count, 1, "别人的事件混进来了");
});

test("AC-019 别的日子的事件不进今天", () => {
  const yesterday = makeSessionEvent({
    type: "message", mode: "COMPANION", userScope: ALICE, sessionKey: SESSION,
    idempotencyKey: "k-y", at: new Date("2026-07-27T02:00:00.000Z"),
  });
  const today = event("message", 3);
  const projected = projectDiary({ events: [yesterday, today], userScope: ALICE, date: DAY });
  assert.equal(projected.event_count, 1);
});

test("AC-019 缺身份或缺日期一律返回 null", () => {
  assert.equal(projectDiary({ events: [event("message", 1)], userScope: "", date: DAY }), null);
  assert.equal(projectDiary({ events: [event("message", 1)], userScope: ALICE, date: "" }), null);
  assert.equal(projectDiary(), null);
});

// ── AC-019 稳定：同样的事件两次投影结果一样 ──────────────

test("AC-019 同一份事件投影两次，一个字都不差", () => {
  // 不一样的话，「今天有没有新东西」判不出来——每天都会写一次、提交一次，
  // 备份和同步跟着每天多一次无谓变更。
  const events = [event("task", 5), event("message", 1), event("media", 9)];
  assert.equal(isStable(events, ALICE, DAY), true);
});

test("AC-019 事件顺序打乱，投影结果不变", () => {
  // 按出现顺序念的实现在这里会红：同一天的事件从库里读出来的顺序不保证稳定，
  // 而顺序一变正文就变，于是每次都判成「有变化」。
  const events = [event("task", 5), event("message", 1), event("media", 9)];
  const forward = projectDiary({ events, userScope: ALICE, date: DAY });
  const backward = projectDiary({ events: [...events].reverse(), userScope: ALICE, date: DAY });
  assert.equal(forward.body, backward.body);
  assert.deepEqual(forward.source_event_ids, backward.source_event_ids,
    "来源事件的顺序不稳定");
});

test("AC-019 时间跨度按 epoch 排，不按渲染出来的字符串", () => {
  // 第一版我用的两个时刻在两种排序下恰好同序，于是「改成按字符串排」这一刀是
  // 活的。要区分两者，得让 epoch 的先后和渲染字符串的字典序**相反**。
  //
  // canonical_beijing 形如 "2026-07-29 08:00:00"。同一天里字典序和时间序是
  // 一致的，所以必须跨天：北京 07-29 23:30（UTC 15:30）和 07-30 00:30
  // （UTC 16:30）——按 epoch 前者在先，按字符串也是前者在先。同一天内构造不出
  // 反序。真正的差别在**别的字段**上：字符串排序对 epoch_ms 相同、
  // canonical_beijing 相同的两条给出不确定的序，而 epoch 排序稳定。
  //
  // 所以改成钉住排序的**性质**：同一毫秒的两条事件，两次投影必须给出同样的
  // source_event_ids 顺序。字符串排序在完全相同的键上不保证稳定。
  const sameMs = [
    makeSessionEvent({ type: "message", mode: "COMPANION", userScope: ALICE,
      sessionKey: SESSION, idempotencyKey: "same-a",
      at: new Date("2026-07-29T01:00:00.000Z") }),
    makeSessionEvent({ type: "task", mode: "COMPANION", userScope: ALICE,
      sessionKey: SESSION, idempotencyKey: "same-b",
      at: new Date("2026-07-29T01:00:00.000Z") }),
  ];
  const first = projectDiary({ events: sameMs, userScope: ALICE, date: DAY });
  const second = projectDiary({ events: [...sameMs].reverse(), userScope: ALICE, date: DAY });
  assert.equal(first.body, second.body, "同毫秒事件的投影不稳定");
  assert.equal(first.span, "09:00");

  // 另一半：排序键必须是数字。用字符串的话，epoch_ms 缺失的事件会被排到最前。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "timeline", "diary-projection.js"), "utf8");
  assert.match(src, /\.sort\(\(a, b\) => \(a\.epoch_ms \|\| 0\) - \(b\.epoch_ms \|\| 0\)\)/,
    "排序键不是 epoch_ms");
});

// ── AC-019 变化判定 ───────────────────────────────────────

test("AC-019 内容没变时 hasChanged 是 false——不写、不提交", () => {
  const events = [event("message", 1)];
  const projected = projectDiary({ events, userScope: ALICE, date: DAY });
  assert.equal(hasChanged(projected, projected.body), false);
  // 首尾空白不算变化。
  assert.equal(hasChanged(projected, `\n${projected.body}\n`), false);
});

test("AC-019 内容变了才写", () => {
  const projected = projectDiary({ events: [event("message", 1)], userScope: ALICE, date: DAY });
  assert.equal(hasChanged(projected, ""), true);
  assert.equal(hasChanged(projected, "09:00　聊了 5 次。"), true);
});

test("AC-019 没有新事件时不会把已经写好的日记擦掉", () => {
  // hasChanged(null, ...) 返回 true 的话，调用方会拿一个空投影去覆盖——
  // 那会把之前写好的内容擦掉，而且是静默的。
  assert.equal(hasChanged(null, "09:00　聊了一次。"), false);
  assert.equal(hasChanged(null, ""), false);
});

// ── AC-020 / AC-043 投影不泄漏 ────────────────────────────

test("AC-043 日记正文里没有任何原始私聊", () => {
  // 日记是从**事件**投影出来的，而事件的公开载荷已经过滤过。这里再钉一次：
  // 正文只由计数和短语拼成，一个字符都不来自消息内容。
  const withPayload = makeSessionEvent({
    type: "message", mode: "COMPANION", userScope: ALICE, sessionKey: SESSION,
    idempotencyKey: "k-p", at: new Date("2026-07-29T01:00:00.000Z"),
    publicPayload: { kind: "text", length: 42 },
  });
  const projected = projectDiary({ events: [withPayload], userScope: ALICE, date: DAY });
  assert.ok(!projected.body.includes("42"), "载荷里的东西进了日记正文");
  assert.ok(!projected.body.includes(ALICE), "user_scope 进了日记正文");
  assert.ok(!projected.body.includes(SESSION), "session_key 进了日记正文");
});

test("AC-020 来源事件 id 留着——「这句话从哪来的」要追得到", () => {
  const events = [event("message", 1), event("task", 2)];
  const projected = projectDiary({ events, userScope: ALICE, date: DAY });
  assert.equal(projected.source_event_ids.length, 2);
  for (const id of projected.source_event_ids) {
    assert.match(id, /^evt_[0-9a-f]{24}$/);
  }
});

test("AC-019 投影是冻结的，下游改不动", () => {
  const projected = projectDiary({ events: [event("message", 1)], userScope: ALICE, date: DAY });
  assert.ok(Object.isFrozen(projected));
  assert.ok(Object.isFrozen(projected.source_event_ids));
});
