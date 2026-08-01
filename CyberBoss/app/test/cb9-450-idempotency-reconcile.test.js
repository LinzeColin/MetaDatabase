"use strict";

// CB9-450 Inbox/Journal/Outbox 幂等与未知结果对账（AC-023 / AC-024 / FR-023、FR-024）
//
//   AC-023 重复微信 message_id、网络重试、send failure、crash-cut；
//          每个 idempotency_key 最多一个业务副作用。
//   AC-024 分别重启 bridge、app、Codex App Server；任务恢复到确定状态，
//          session_key 不漂移，未知结果进入 reconcile。
//
// 这一节点的核心是**第三种结果**。发一条消息出去只有两种结果是确定的：成功
// （对面回了 200）和失败（对面回了明确的错误码）。但最常见的那种是超时、连接
// 断开、502——这时候我们不知道消息到没到。
//
//   当失败重试 → 用户收到两条一模一样的。
//   当成功不管 → 用户什么都没收到，而系统认为发过了。
//
// 两种都错，而且错得不对称。所以未知不许被归到任何一边。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const {
  DEFINITE_FAILURE,
  RESULTS,
  classifySendOutcome,
  idempotencyKeyFor,
  planForUnknown,
} = require("../src/services/outbox/unknown-result");

// ── AC-023 三态分类 ───────────────────────────────────────

test("AC-023 只有对面明确说了才算失败", () => {
  // 明确失败可以安全重试（换个 token、改个参数）。把不确定的也归到这里，
  // 就是在赌它没到达。
  for (const errorCode of DEFINITE_FAILURE) {
    assert.equal(classifySendOutcome({ ok: false, errorCode }), "failed", errorCode);
  }
  assert.equal(classifySendOutcome({ ok: true }), "succeeded");
});

test("AC-023 传输层的症状一律是未知，不是失败", () => {
  // 业务层没说话，就不能替它说。
  const TRANSPORT = [
    "ETIMEDOUT", "ECONNRESET", "socket hang up", "aborted",
    "502 Bad Gateway", "503 Service Unavailable", "504 Gateway Timeout",
    "network error", "request timeout",
  ];
  for (const errorMessage of TRANSPORT) {
    assert.equal(classifySendOutcome({ ok: false, errorMessage }), "unknown",
      `${errorMessage} 被判成了确定结果`);
  }
});

test("AC-023 认不出来的错误当未知，不当失败", () => {
  // 当失败会重试，而重试一个没看懂的错误就是在赌它没到达。赌错的代价是用户
  // 收到两条；当未知的代价只是多一次查询——那次查询本来也该做。
  assert.equal(classifySendOutcome({ ok: false, errorCode: "SOMETHING_NOBODY_LISTED" }), "unknown");
  assert.equal(classifySendOutcome({ ok: false, errorMessage: "谁知道这是什么" }), "unknown");
});

test("AC-023 明确的业务错误码压过传输层症状", () => {
  // 顺序反过来的话，一个「token 过期」的响应如果恰好也超时了会被判成未知——
  // 而它其实是确定失败的，重试一次换个 token 就能修好。
  assert.equal(classifySendOutcome({
    ok: false, errorCode: "WEIXIN_TOKEN_EXPIRED", errorMessage: "socket hang up",
  }), "failed");
});

test("AC-023 三种结果就是三种，没有第四种", () => {
  const seen = new Set();
  for (const probe of [
    { ok: true }, { ok: false, errorCode: "WEIXIN_FORBIDDEN" },
    { ok: false, errorMessage: "ETIMEDOUT" }, { ok: false }, {},
  ]) {
    seen.add(classifySendOutcome(probe));
  }
  for (const result of seen) {
    assert.ok(RESULTS.includes(result), `冒出了第四种结果：${result}`);
  }
});

// ── AC-023 未知的处置 ─────────────────────────────────────

test("AC-023 未知时**不重发**——在查清楚之前重发就是在赌", () => {
  for (const attempts of [0, 1, 2, 3, 10]) {
    assert.equal(planForUnknown({ attempts }).resend, false,
      `第 ${attempts} 次时重发了`);
  }
});

test("AC-024 未知先进 reconcile，由查询定性", () => {
  const first = planForUnknown({ attempts: 0 });
  assert.equal(first.action, "reconcile");
  assert.equal(first.reason, "outcome_unknown");
  assert.equal(first.next_attempt, 1);
  assert.equal(first.presumed, false);
});

test("AC-024 查不出来时按已送达记，但标成**推定**", () => {
  // 两害相权取了「宁可不重发」。但既然是权衡，就必须让它可见——推定送达和
  // 真送达在证据里是两种东西，否则「他到底收到没有」这个问题永远答不出来。
  const exhausted = planForUnknown({ attempts: 3 });
  assert.equal(exhausted.action, "assume_delivered");
  assert.equal(exhausted.presumed, true, "推定送达没有被标出来");
  assert.equal(exhausted.resend, false);
  assert.equal(exhausted.reason, "reconcile_exhausted");
});

test("AC-024 对账次数有上限——不会无限查下去", () => {
  assert.equal(planForUnknown({ attempts: 2 }).action, "reconcile");
  assert.equal(planForUnknown({ attempts: 3 }).action, "assume_delivered");
  // 负数和非整数按 0 算，不会绕过上限。
  assert.equal(planForUnknown({ attempts: -5 }).action, "reconcile");
  assert.equal(planForUnknown({ attempts: 1.5 }).action, "reconcile");
});

// ── AC-023 幂等键 ─────────────────────────────────────────

test("AC-023 同一件业务算出同一个键，跨重启稳定", () => {
  // 随机的话，重启后重放会算出新键，同一件事被当成两件，做了两次。
  const args = { channel: "weixin", accountId: "acct", messageId: "wx-1", kind: "reply" };
  assert.equal(idempotencyKeyFor(args), idempotencyKeyFor(args));
  assert.match(idempotencyKeyFor(args), /^idem_[0-9a-f]{32}$/);
});

test("AC-023 不同的业务算出不同的键", () => {
  const base = { channel: "weixin", accountId: "acct", messageId: "wx-1", kind: "reply" };
  const keys = new Set([
    idempotencyKeyFor(base),
    idempotencyKeyFor({ ...base, messageId: "wx-2" }),
    idempotencyKeyFor({ ...base, kind: "reminder" }),
    idempotencyKeyFor({ ...base, accountId: "other" }),
    idempotencyKeyFor({ ...base, target: "x" }),
  ]);
  assert.equal(keys.size, 5, "不同的业务撞成了同一个键");
});

test("AC-023 分界点错位的两组不能撞", () => {
  // target 可能是一整条命令行，含空格。用空格拼的话 ("a b","c") 和 ("a","b c")
  // 会拼出同一个串——而撞成一个键意味着第二件永远不会被执行。
  assert.notEqual(
    idempotencyKeyFor({ channel: "weixin", accountId: "a", messageId: "m", kind: "reply x", target: "y" }),
    idempotencyKeyFor({ channel: "weixin", accountId: "a", messageId: "m", kind: "reply", target: "x y" }),
  );
});

test("AC-023 缺关键段直接拒绝，不算出一个含糊的键", () => {
  // 算出来的话，两条各自缺了不同字段的业务会撞在一起。
  for (const missing of ["channel", "messageId", "kind"]) {
    assert.throws(
      () => idempotencyKeyFor({ channel: "weixin", messageId: "m", kind: "reply", [missing]: "" }),
      TypeError, `${missing} 空值被放行了`);
  }
});

// ── AC-023 入站去重（既有实现的性质，在这里再钉一次）─────

test("AC-023 同一个微信 message_id 只认一次", () => {
  // 微信会重复投递。第二次进来必须被认出是同一条，否则一条消息办两遍。
  const inbox = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "inbox", "durable-inbox.js"), "utf8");
  assert.match(inbox, /kind:\s*"message_id"/);
  assert.match(inbox, /sourceMessageId/);
  // 去重键由 message_id 推出，不是随机——随机的话重复投递认不出来。
  assert.match(inbox, /sha256\(`message_id/);
});

// ── AC-024 session_key 不漂移 ─────────────────────────────

test("AC-024 幂等键不含时间和随机数——重启后算得出同一个", () => {
  // 含时间的话，重启后同一件事算出新键，于是被当成新任务重做一遍。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "outbox", "unknown-result.js"), "utf8");
  const code = src.split("\n").map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1")).join("\n");
  for (const nondeterminism of ["Date.now", "Math.random", "randomUUID", "process.pid"]) {
    assert.ok(!code.includes(nondeterminism),
      `幂等键的计算里出现了 ${nondeterminism}——重启后会算出另一个键`);
  }
});

test("AC-024 分类和处置都是纯函数——不发请求、不写库", () => {
  // 定性和处置分开，是为了让定性这件事能单独测——而它正是最容易写错的一半。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "outbox", "unknown-result.js"), "utf8");
  const requires = [...src.matchAll(/require\("([^"]+)"\)/g)].map((m) => m[1]);
  assert.deepEqual(requires, ["node:crypto"],
    `这个模块 require 了别的东西：${requires.join(", ")}`);
});

test("AC-024 认得出的传输层症状和没见过的错误，原因要分开", () => {
  // 变异测试抓到的：第一版只回三个字符串，于是 UNKNOWN_SHAPES 那张表是**白写
  // 的**——删掉它，兜底那条「认不出来当未知」照样把传输层错误判成 unknown，
  // 行为一模一样。那一刀因此是活的，而根因不是测试没写到，是那段代码不承重。
  //
  // 两者在运维上是两件事：认得出的多半对账一次能查清；没见过的说明有一类错误
  // 我们还没理解，该有人去看。归到同一个原因里的话，它会永远藏在传输层抖动的
  // 噪声里。
  const { classifySendOutcomeDetailed } = require("../src/services/outbox/unknown-result");
  const known = classifySendOutcomeDetailed({ ok: false, errorMessage: "socket hang up" });
  assert.equal(known.result, "unknown");
  assert.equal(known.reason, "transport_interrupted");

  const strange = classifySendOutcomeDetailed({ ok: false, errorCode: "NOBODY_HAS_SEEN_THIS" });
  assert.equal(strange.result, "unknown");
  assert.equal(strange.reason, "unrecognized_error", "没见过的错误被归进了传输层噪声");

  assert.notEqual(known.reason, strange.reason);
  assert.equal(classifySendOutcomeDetailed({ ok: true }).reason, "acknowledged");
  assert.equal(classifySendOutcomeDetailed({ ok: false, errorCode: "WEIXIN_FORBIDDEN" }).reason,
    "declined_by_peer");
  assert.equal(classifySendOutcomeDetailed({ ok: false }).reason, "no_response_no_error");
});
