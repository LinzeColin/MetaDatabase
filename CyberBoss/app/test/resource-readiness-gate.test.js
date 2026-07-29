"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  REASON_ACTION,
  ResourceReadinessGate,
  captureLiveResourceSnapshot,
  classifyRuntimeError,
} = require("../src/services/jobs/resource-readiness-gate");

const NOW = new Date("2026-07-27T01:00:00.000Z");

function snapshot(overrides = {}) {
  const base = {
    poll: { lastSuccessAt: "2026-07-27T00:59:30.000Z" },
    runtime: { ready: true, reason: "ready" },
    memory: { totalMb: 4096, availableMb: 3000 },
    storage: {
      freeMb: 25_000,
      usedPercent: 40,
      inodeUsedPercent: 10,
    },
    load: { oneMinute: 0.5, cpuCount: 2 },
    queue: { depth: 0, oldestQueuedAt: null, activeRuntime: false },
  };
  return {
    ...base,
    ...overrides,
    poll: { ...base.poll, ...(overrides.poll || {}) },
    runtime: { ...base.runtime, ...(overrides.runtime || {}) },
    memory: { ...base.memory, ...(overrides.memory || {}) },
    storage: { ...base.storage, ...(overrides.storage || {}) },
    load: { ...base.load, ...(overrides.load || {}) },
    queue: { ...base.queue, ...(overrides.queue || {}) },
  };
}

function gate() {
  return new ResourceReadinessGate({
    now: () => NOW,
    pollStaleMs: 90_000,
    queueStuckMs: 300_000,
    queueLimit: 20,
  });
}

test("recover, warn and protect ladder is immediate and deterministic", () => {
  const cases = [
    [snapshot(), "recover", true],
    [snapshot({ queue: { depth: 16, oldestQueuedAt: NOW.toISOString() } }), "warn", true],
    [snapshot({ memory: { availableMb: 400 } }), "protect", false],
    [snapshot({ storage: { usedPercent: 92 } }), "protect", false],
    [snapshot({ queue: { depth: 20, oldestQueuedAt: NOW.toISOString() } }), "protect", true],
    [snapshot(), "recover", true],
  ];
  const actual = cases.map(([fixture, expectedGuard, expectedDispatch]) => {
    const result = gate().evaluate({
      operationClass: "bounded_mutation",
      snapshot: fixture,
    });
    assert.equal(result.guardState, expectedGuard);
    assert.equal(result.dispatchAllowed, expectedDispatch);
    return result.guardState;
  });
  assert.deepEqual(actual, [
    "recover",
    "warn",
    "protect",
    "protect",
    "protect",
    "recover",
  ]);
});

test("degraded reason and action matrix is exact", () => {
  const fixtures = [
    [
      "poll_stale",
      snapshot({ poll: { lastSuccessAt: "2026-07-27T00:00:00.000Z" } }),
    ],
    [
      "runtime_unhealthy",
      snapshot({ runtime: { ready: false, reason: "transport" } }),
    ],
    ["disk_pressure", snapshot({ storage: { usedPercent: 92 } })],
    ["load_pressure", snapshot({ load: { oneMinute: 4, cpuCount: 2 } })],
    [
      "queue_stuck",
      snapshot({
        queue: {
          depth: 1,
          oldestQueuedAt: "2026-07-27T00:50:00.000Z",
          activeRuntime: false,
        },
      }),
    ],
  ];
  for (const [reason, fixture] of fixtures) {
    const result = gate().evaluate({
      operationClass: "bounded_mutation",
      snapshot: fixture,
    });
    assert.equal(result.reason, reason);
    assert.equal(result.action, REASON_ACTION[reason]);
  }
});

test("disk and inode protect block mutation but permit a read-only drain", () => {
  for (const fixture of [
    snapshot({ storage: { usedPercent: 90 } }),
    snapshot({ storage: { inodeUsedPercent: 90 } }),
  ]) {
    assert.equal(
      gate().evaluate({
        operationClass: "bounded_mutation",
        snapshot: fixture,
      }).dispatchAllowed,
      false,
    );
    assert.equal(
      gate().evaluate({
        operationClass: "read_only",
        snapshot: fixture,
      }).dispatchAllowed,
      true,
    );
  }
});

// ── 负载不能拦回复 ──────────────────────────────────────────
//
// 主人说「他没回话」「过了五分钟才回」。线上那条消息 07:11:11.492 入队，
// 07:14:21.985 才被 claim——中间三分十秒闸门一直在说 load_pressure。
// 这台机器 2 核，loadProtect = max(3.5, 2×1.5) = 3.5，而它常年挂着 codex
// runtime、cloudflared 和另外几个服务，一分钟负载翻过 3.5 是常态。

test("负载高只让它慢，不让它闭嘴", () => {
  // 线上那台机器的真实数字：2 核，一分钟负载 4.2（阈值 3.5）。
  const result = gate().evaluate({
    operationClass: "bounded_mutation",
    snapshot: snapshot({ load: { oneMinute: 4.2, cpuCount: 2 } }),
  });

  assert.equal(
    result.dispatchAllowed,
    true,
    "负载高就不派发＝主人在微信那头等着的唯一一条回复被无限期推迟，而他什么解释都看不到",
  );
  assert.equal(result.state, "degraded");
  assert.equal(result.reason, "load_pressure");
  // 仍然记成 protect：面板上要看得出「现在很吃力」，只是不拿它当拒绝的理由。
  assert.equal(result.guardState, "protect");
  assert.ok(result.protectReasons.includes("load"));
});

test("内存和磁盘照样拦——那两样是真会把进程打死、把数据写坏", () => {
  for (const [name, fixture] of [
    ["内存", snapshot({ memory: { availableMb: 400 } })],
    ["磁盘", snapshot({ storage: { usedPercent: 92 } })],
  ]) {
    assert.equal(
      gate().evaluate({
        operationClass: "bounded_mutation",
        snapshot: fixture,
      }).dispatchAllowed,
      false,
      `${name}压到红线还继续派发，就不是慢的问题了`,
    );
  }
});

test("负载和内存一起红的时候，按内存拦——先保命", () => {
  const result = gate().evaluate({
    operationClass: "bounded_mutation",
    snapshot: snapshot({
      load: { oneMinute: 9, cpuCount: 2 },
      memory: { availableMb: 400 },
    }),
  });

  assert.equal(result.dispatchAllowed, false);
  assert.equal(result.reason, "memory_pressure");
});

test("missing, malformed or future measurements fail closed", () => {
  for (const fixture of [
    null,
    snapshot({ memory: { availableMb: -1 } }),
    snapshot({ storage: { usedPercent: 101 } }),
    snapshot({ poll: { lastSuccessAt: "2026-07-27T02:00:00.000Z" } }),
    snapshot({ queue: { depth: 1, oldestQueuedAt: null } }),
  ]) {
    const result = gate().evaluate({
      operationClass: "bounded_mutation",
      snapshot: fixture,
    });
    assert.equal(result.dispatchAllowed, false);
    assert.ok(["measurement_unavailable", "poll_stale"].includes(result.reason));
  }
});

test("Runtime errors map to fixed retry and action classes without raw details", () => {
  assert.equal(
    classifyRuntimeError({ code: "auth_required" }).errorClass,
    "auth_required",
  );
  assert.equal(
    classifyRuntimeError({ cancelled: true }).errorClass,
    "cancelled",
  );
  assert.deepEqual(
    classifyRuntimeError({
      code: "runtime_overloaded",
      message: "429",
      retryable: true,
    }),
    {
      errorClass: "runtime_overloaded",
      retryable: true,
      action: "bounded_retry_if_operation_safe",
    },
  );
  assert.equal(
    classifyRuntimeError({ message: "ECONNRESET" }).errorClass,
    "transport_unavailable",
  );
  assert.equal(
    classifyRuntimeError({ message: "private fixture detail" }).errorClass,
    "runtime_terminal",
  );
  assert.doesNotMatch(
    JSON.stringify(classifyRuntimeError({ message: "private fixture detail" })),
    /private fixture detail/,
  );
});

test("live probe returns bounded aggregate facts and no filesystem path", () => {
  const live = captureLiveResourceSnapshot({
    poll: { lastSuccessAt: NOW.toISOString() },
    runtime: { ready: true, reason: "ready" },
    queue: {
      queuedTotal: 2,
      oldestQueuedAt: NOW.toISOString(),
      activeRuntimeJobs: 0,
    },
  });
  assert.equal(live.source, "live");
  assert.ok(live.memory.totalMb > 0);
  assert.ok(live.storage.freeMb >= 0);
  assert.equal(live.queue.depth, 2);
  assert.doesNotMatch(JSON.stringify(live), /filesystemPath|\/Users\/|\/var\//);
});
