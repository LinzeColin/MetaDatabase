"use strict";

// CB9-500 live parity receipt 与新鲜度状态机（AC-025 / FR-025）
//
// AC-025 把四种状态写死了：
//   配置存在但没有 live receipt → UNKNOWN
//   有新鲜的成功回执           → HEALTHY
//   回执过期                   → DEGRADED
//   最近一次是失败             → UNAVAILABLE
//
// 为什么必须分开「没测过」和「测过是坏的」：
//
// 刚部署完的系统每一项都是「还没被真实调用过」。这时候显示红色，主人会去查一个
// **不存在的故障**；查完发现只是没人用，下一次真的红了他就不会再当回事——这是
// 这套面板最容易毁掉自己的方式。
//
// 反过来显示绿色更糟：那是**配置性伪绿**，配置里写着开着于是说健康，而它可能
// 从第一天起就是坏的。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const {
  DEFAULT_FAILURE_STICKY_MS,
  DEFAULT_FRESH_MS,
  STATES,
  freshnessOf,
  rollup,
} = require("../src/services/status/parity-freshness");

const NOW = Date.parse("2026-08-02T12:00:00.000Z");
const ago = (ms) => new Date(NOW - ms).toISOString();

// ── AC-025 四种状态逐条 ───────────────────────────────────

test("AC-025 配置存在但没有 live receipt → UNKNOWN", () => {
  // 这一条是整个模块存在的理由。不知道，不是坏。
  const verdict = freshnessOf({ configured: true, now: NOW });
  assert.equal(verdict.state, "UNKNOWN");
  assert.equal(verdict.reason, "no_live_receipt");
  assert.equal(verdict.usable, false, "不知道被当成了能用——那就是伪绿");
});

test("AC-025 新鲜的成功 → HEALTHY", () => {
  const verdict = freshnessOf({ configured: true, lastSuccessAt: ago(60_000), now: NOW });
  assert.equal(verdict.state, "HEALTHY");
  assert.equal(verdict.usable, true);
  assert.equal(verdict.age_ms, 60_000);
});

test("AC-025 过期的成功 → DEGRADED，不是 HEALTHY", () => {
  // 旧的成功不是成功——它只证明那时候是好的。
  const verdict = freshnessOf({
    configured: true, lastSuccessAt: ago(DEFAULT_FRESH_MS + 1000), now: NOW,
  });
  assert.equal(verdict.state, "DEGRADED");
  assert.equal(verdict.reason, "stale_success");
  assert.equal(verdict.usable, false);
});

test("AC-025 最近失败 → UNAVAILABLE", () => {
  const verdict = freshnessOf({ configured: true, lastFailureAt: ago(60_000), now: NOW });
  assert.equal(verdict.state, "UNAVAILABLE");
  assert.equal(verdict.reason, "recent_failure");
});

test("AC-025 边界：恰好在新鲜窗口上算新鲜，过一毫秒就不算", () => {
  assert.equal(freshnessOf({
    configured: true, lastSuccessAt: ago(DEFAULT_FRESH_MS), now: NOW,
  }).state, "HEALTHY");
  assert.equal(freshnessOf({
    configured: true, lastSuccessAt: ago(DEFAULT_FRESH_MS + 1), now: NOW,
  }).state, "DEGRADED");
});

// ── AC-025 失败与成功同时存在 ─────────────────────────────

test("AC-025 失败之后紧接着一次成功——仍然是 UNAVAILABLE", () => {
  // 这条路在抖，而抖动对用户就是「有时候不行」。直接显示绿色会把它藏起来。
  const verdict = freshnessOf({
    configured: true,
    lastFailureAt: ago(60_000),
    lastSuccessAt: ago(120_000), // 失败比成功更近
    now: NOW,
  });
  assert.equal(verdict.state, "UNAVAILABLE");
});

test("AC-025 成功比失败更近，且失败已经不粘滞了 → HEALTHY", () => {
  const verdict = freshnessOf({
    configured: true,
    lastFailureAt: ago(DEFAULT_FAILURE_STICKY_MS + 1000),
    lastSuccessAt: ago(60_000),
    now: NOW,
  });
  assert.equal(verdict.state, "HEALTHY");
});

test("AC-025 失败粘滞窗口比新鲜窗口长——一次失败不会被立刻抹掉", () => {
  // 短于新鲜窗口的话，一次失败会被紧接着的一次成功立刻抹掉，而抖动正是这样
  // 被藏起来的。失败的信息价值比成功高：它说明这条路真的会坏。
  assert.ok(DEFAULT_FAILURE_STICKY_MS > DEFAULT_FRESH_MS,
    "失败粘滞窗口不比新鲜窗口长——抖动会被藏起来");
});

test("AC-025 只有旧失败、从来没成功过 → 仍然是 UNKNOWN", () => {
  // 失败已经不新鲜了，而且从没成功过——现在到底怎么样，还是不知道。
  // 判成 HEALTHY 是伪绿，判成 UNAVAILABLE 是指着一个可能已经不存在的故障。
  const verdict = freshnessOf({
    configured: true, lastFailureAt: ago(DEFAULT_FAILURE_STICKY_MS + 1000), now: NOW,
  });
  assert.equal(verdict.state, "UNKNOWN");
  assert.equal(verdict.reason, "stale_failure_no_success");
});

test("AC-025 没配置的能力只能是 UNKNOWN", () => {
  const verdict = freshnessOf({ configured: false, lastSuccessAt: ago(1000), now: NOW });
  assert.equal(verdict.state, "UNKNOWN");
  assert.equal(verdict.reason, "not_configured");
});

// ── AC-025 「最后一次真正评估的时间」 ────────────────────

test("AC-025 每份判定都带上评估时刻", () => {
  // 没有这个字段的话，面板上一个 UNKNOWN 和一个刚被评估过的 UNKNOWN 长得
  // 一模一样，而它们是两件事：前者是「系统还没跑起来」，后者是「跑起来了但
  // 这一项一直没人用」。
  for (const probe of [
    { configured: true },
    { configured: true, lastSuccessAt: ago(1000) },
    { configured: true, lastFailureAt: ago(1000) },
    { configured: false },
  ]) {
    const verdict = freshnessOf({ ...probe, now: NOW });
    assert.equal(verdict.evaluated_at, new Date(NOW).toISOString(),
      `${verdict.state} 没带评估时刻`);
  }
});

test("AC-025 判定是冻结的，且只出现四种状态", () => {
  const verdict = freshnessOf({ configured: true, now: NOW });
  assert.ok(Object.isFrozen(verdict));
  for (const probe of [
    {}, { configured: true }, { configured: true, lastSuccessAt: ago(1) },
    { configured: true, lastFailureAt: ago(1) },
    { configured: true, lastSuccessAt: ago(1e9) },
    { configured: true, lastSuccessAt: "不是时间", lastFailureAt: "也不是" },
  ]) {
    assert.ok(STATES.includes(freshnessOf({ ...probe, now: NOW }).state),
      `冒出了第五种状态：${JSON.stringify(probe)}`);
  }
});

test("AC-025 读不出来的时间戳当成没有，不当成新鲜", () => {
  // 当成新鲜的话，一个写坏的回执会让一项从没验过的能力显示健康。
  const verdict = freshnessOf({ configured: true, lastSuccessAt: "坏掉的时间", now: NOW });
  assert.equal(verdict.state, "UNKNOWN");
});

// ── AC-025 整体汇总 ───────────────────────────────────────

test("AC-025 整体取最差的那一项", () => {
  const entries = [
    freshnessOf({ configured: true, lastSuccessAt: ago(1000), now: NOW }),
    freshnessOf({ configured: true, lastSuccessAt: ago(DEFAULT_FRESH_MS + 1), now: NOW }),
  ];
  assert.equal(rollup(entries).state, "DEGRADED");
  entries.push(freshnessOf({ configured: true, lastFailureAt: ago(1000), now: NOW }));
  assert.equal(rollup(entries).state, "UNAVAILABLE");
});

test("AC-025 UNKNOWN 不拉低整体——它不是故障", () => {
  // 把「有一项没人用过」显示成「系统有问题」，是同一个「指着不存在的故障」
  // 的错误，只是换了个层级。
  const entries = [
    freshnessOf({ configured: true, lastSuccessAt: ago(1000), now: NOW }),
    freshnessOf({ configured: true, now: NOW }), // UNKNOWN
  ];
  assert.equal(rollup(entries).state, "HEALTHY");
  assert.equal(rollup(entries).counts.UNKNOWN, 1, "UNKNOWN 的数量没被记下来");
});

test("AC-025 一项都没验过时整体是 UNKNOWN，不是 HEALTHY", () => {
  // 上一条的反面。全是 UNKNOWN 的系统不该显示健康——那正是配置性伪绿。
  const entries = [
    freshnessOf({ configured: true, now: NOW }),
    freshnessOf({ configured: true, now: NOW }),
  ];
  const summary = rollup(entries);
  assert.equal(summary.state, "UNKNOWN");
  assert.equal(summary.reason, "nothing_verified_yet");
});

test("AC-025 空矩阵是 UNKNOWN，不是 HEALTHY", () => {
  assert.equal(rollup([]).state, "UNKNOWN");
  assert.equal(rollup().state, "UNKNOWN");
  assert.equal(rollup(null).state, "UNKNOWN");
});

// ── FR-025 绿色只能由真实链路换来 ─────────────────────────

test("FR-025 这个模块拿不到配置，只认回执", () => {
  // 「配置里开着」不许变成绿色。做法是让这个模块**够不着**配置——它只收
  // lastSuccessAt / lastFailureAt 两个时刻，而那两个时刻只能由真实链路写。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "status", "parity-freshness.js"), "utf8");
  const requires = [...src.matchAll(/require\("([^"]+)"\)/g)].map((m) => m[1]);
  assert.deepEqual(requires, [], `新鲜度模块 require 了别的东西：${requires.join(", ")}`);
  const code = src.split("\n").map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1")).join("\n");
  for (const hint of ["readFileSync", "process.env", "config."]) {
    assert.ok(!code.includes(hint), `新鲜度模块碰了 ${hint}——配置能变成绿色了`);
  }
});

test("FR-025 configured 单独一个字段不足以变绿", () => {
  // 直接的反面测试：只把 configured 设成 true，怎么都不该是 HEALTHY。
  assert.notEqual(freshnessOf({ configured: true, now: NOW }).state, "HEALTHY");
  assert.notEqual(freshnessOf({ configured: true, now: NOW }).usable, true);
});
