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
