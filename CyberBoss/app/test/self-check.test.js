"use strict";

// 「我的意思是不依赖开发agent去运维。」
//
// 今天查出来的三个故障，主人一个都发现不了。这一份的每一条判据都对着其中一个：
// 如果这套体检当时就在跑，他会在微信里直接收到人话，而不是等我 ssh 上去。

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  buildAlertMessage,
  buildRecoveryMessage,
  diffFindings,
  evaluateHealth,
} = require("../src/services/health/self-check");

const NOW = Date.parse("2026-07-29T08:00:00.000Z");
const HOUR = 3_600_000;

// 一切正常的一组数字。每个测试只改动它关心的那一项。
function facts(overrides = {}) {
  return {
    canonicalSyncedAt: new Date(NOW - 2 * HOUR).toISOString(),
    backupAt: new Date(NOW - 5 * HOUR).toISOString(),
    recentJobs: Array.from({ length: 6 }, () => ({
      queuedAt: new Date(NOW - HOUR).toISOString(),
      startedAt: new Date(NOW - HOUR + 400).toISOString(),
    })),
    runningJobs: [],
    outbox: { confirmed: 40, failed: 0 },
    checkinSilentStreak: 0,
    schema: 13,
    schemaExpected: 13,
    ...overrides,
  };
}

function ids(report) {
  return report.findings.map((finding) => finding.id);
}

test("一切正常的时候不说话——每轮都报等于没报", () => {
  const report = evaluateHealth(facts(), { now: NOW });

  assert.equal(report.healthy, true);
  assert.deepEqual(report.findings, []);
});

// ── 今天真出过的三个 ────────────────────────────────────────

test("回复延迟：消息 07:11 入队 07:14 才被取走，这一条要报出来", () => {
  // 今天的真实数字：190 秒。
  const report = evaluateHealth(facts({
    recentJobs: Array.from({ length: 5 }, () => ({
      queuedAt: new Date(NOW - HOUR).toISOString(),
      startedAt: new Date(NOW - HOUR + 190_000).toISOString(),
    })),
  }), { now: NOW });

  assert.deepEqual(ids(report), ["reply_slow"]);
  assert.match(report.findings[0].detail, /190 秒/);
});

test("全量同步停了：EACCES 那次在日志里躺了好几天，没人看", () => {
  const report = evaluateHealth(facts({
    canonicalSyncedAt: new Date(NOW - 30 * HOUR).toISOString(),
  }), { now: NOW });

  assert.deepEqual(ids(report), ["sync_stale"]);
  assert.match(report.findings[0].detail, /30 小时前/);
});

test("从来没同步成功过，和「停了」要分开说", () => {
  const report = evaluateHealth(facts({ canonicalSyncedAt: "" }), { now: NOW });

  assert.deepEqual(ids(report), ["sync_never"]);
});

test("迁移没跑上去：页面打得开、聊天也通，只有新功能永远是空的", () => {
  const report = evaluateHealth(facts({ schema: 12, schemaExpected: 13 }), { now: NOW });

  assert.deepEqual(ids(report), ["schema_behind"]);
  assert.match(report.findings[0].detail, /第 12 版.*第 13 版/);
});

// ── 其余判据 ────────────────────────────────────────────────

test("主动打招呼在空转——花了额度，他一条都没收到", () => {
  const report = evaluateHealth(facts({ checkinSilentStreak: 6 }), { now: NOW });

  assert.deepEqual(ids(report), ["checkin_silent"]);
  assert.match(report.findings[0].hint, /间隔调长/);
});

test("有回复没送出去：对方在等，这边以为已经回了", () => {
  const report = evaluateHealth(facts({
    outbox: { confirmed: 5, failed: 5 },
  }), { now: NOW });

  assert.deepEqual(ids(report), ["delivery_bad"]);
});

test("有消息卡住十分钟以上", () => {
  const report = evaluateHealth(facts({
    runningJobs: [{ startedAt: new Date(NOW - 20 * 60_000).toISOString() }],
  }), { now: NOW });

  assert.deepEqual(ids(report), ["job_stuck"]);
});

test("冷备停了", () => {
  const report = evaluateHealth(facts({
    backupAt: new Date(NOW - 40 * HOUR).toISOString(),
  }), { now: NOW });

  assert.deepEqual(ids(report), ["backup_stale"]);
});

// ── 不能误报 ────────────────────────────────────────────────

test("样本太少不下结论——刚重启那几条不算数", () => {
  const report = evaluateHealth(facts({
    recentJobs: [{
      queuedAt: new Date(NOW - HOUR).toISOString(),
      startedAt: new Date(NOW - HOUR + 300_000).toISOString(),
    }],
  }), { now: NOW });

  assert.equal(report.healthy, true, "一条慢的就报，主人会学会忽略这套体检");
});

test("出站量太小不下结论", () => {
  const report = evaluateHealth(facts({ outbox: { confirmed: 1, failed: 1 } }), { now: NOW });
  assert.equal(report.healthy, true);
});

test("刚跑起来的 job 不算卡住", () => {
  const report = evaluateHealth(facts({
    runningJobs: [{ startedAt: new Date(NOW - 30_000).toISOString() }],
  }), { now: NOW });

  assert.equal(report.healthy, true);
});

test("空的、缺字段的 facts 不会把体检本身搞崩", () => {
  for (const value of [undefined, {}, { recentJobs: null, outbox: null }]) {
    const report = evaluateHealth(value, { now: NOW });
    assert.ok(Array.isArray(report.findings));
  }
});

// ── 只在翻转时说话 ──────────────────────────────────────────

test("上一轮报过的这一轮不再报", () => {
  const current = evaluateHealth(facts({ checkinSilentStreak: 6 }), { now: NOW }).findings;

  const first = diffFindings([], current);
  assert.deepEqual(first.appeared.map((f) => f.id), ["checkin_silent"]);

  const second = diffFindings(first.active, current);
  assert.deepEqual(second.appeared, [], "每轮都报一遍等于没报");
  assert.deepEqual(second.recovered, []);
});

test("好了要说一句——只报坏不报好，他永远不知道现在到底行不行", () => {
  const diff = diffFindings(["checkin_silent", "sync_stale"], []);

  assert.deepEqual(diff.appeared, []);
  assert.deepEqual(diff.recovered, ["checkin_silent", "sync_stale"]);
  assert.equal(
    buildRecoveryMessage(diff.recovered),
    "主动打招呼、全量数据库同步恢复正常了。",
  );
});

test("认不出来的旧码不会变成一句半截话", () => {
  assert.equal(buildRecoveryMessage(["某个已经删掉的判据"]), "");
  assert.equal(buildRecoveryMessage([]), "");
});

// ── 那条微信长什么样 ────────────────────────────────────────

test("告警是人话：出了什么事、要不要他管", () => {
  const report = evaluateHealth(facts({
    canonicalSyncedAt: new Date(NOW - 30 * HOUR).toISOString(),
  }), { now: NOW });

  const message = buildAlertMessage(report.findings);

  assert.match(message, /有件事你得知道/);
  assert.match(message, /全量数据库同步停了/);
  assert.ok(!message.includes("EACCES"), "别把错误码甩给他");
  assert.ok(!message.includes("sync_stale"), "别把内部代号甩给他");
});

test("两件以上就说清楚是几件", () => {
  const report = evaluateHealth(facts({
    canonicalSyncedAt: new Date(NOW - 30 * HOUR).toISOString(),
    checkinSilentStreak: 6,
  }), { now: NOW });

  assert.match(buildAlertMessage(report.findings), /有 2 件事/);
});

test("没有新问题就不发消息", () => {
  assert.equal(buildAlertMessage([]), "");
});

// ── 承诺过的口令必须真的存在 ────────────────────────────────
//
// 告警里写着「回一句『体检』」。写了做不到的提示比不写更糟：他照做之后发现
// 没反应，下次连告警本身都不信了。

test("告警里承诺的那个口令，代码里真的认", () => {
  const source = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "../src/core/app.js"), "utf8",
  );
  const alert = buildAlertMessage(
    evaluateHealth(facts({ canonicalSyncedAt: "" }), { now: NOW }).findings,
  );
  const promised = alert.match(/回一句「(.+?)」/)?.[1];

  assert.equal(promised, "体检");
  assert.match(source, /HEALTH_KEYWORD\s*=\s*\/\^\(体检/);
  assert.match(source, /handleHealthCommand\(normalized\)/);
});
