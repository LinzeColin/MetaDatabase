const assert = require("node:assert/strict");
const test = require("node:test");

const {
  CanonicalOperationsError,
  buildOperationsPlan,
  buildRetentionReport,
  executeSingleBoundedAction,
} = require("../src/services/operations/canonical-operations-policy");

const NOW = "2026-07-27T03:20:00.000Z";

function retentionPolicy() {
  return {
    schema_version: "cyberboss.retention.v2",
    runtime_logs_days: 7,
    diagnostic_summaries_days: 30,
    local_verified_backups: 2,
    immutable_release_slots: ["current", "previous"],
    build_cache_max_bytes: 536870912,
    raw_private_messages_in_github: false,
    auth_cache_in_standard_backup: false,
    no_empty_canonical_commit: true,
  };
}

function inventory(overrides = {}) {
  return {
    local_backups: [],
    runtime_logs: [],
    diagnostic_summaries: [],
    build_cache_bytes: 0,
    spool_entries: 4,
    ...overrides,
  };
}

function resourceSnapshot(now = NOW, overrides = {}) {
  const snapshot = {
    poll: { lastSuccessAt: now },
    runtime: { ready: true },
    memory: { totalMb: 4096, availableMb: 3000 },
    storage: { usedPercent: 40, inodeUsedPercent: 10 },
    load: { oneMinute: 0.2, cpuCount: 2 },
    queue: { depth: 0, oldestQueuedAt: null, activeRuntime: false },
  };
  return {
    ...snapshot,
    ...overrides,
    poll: { ...snapshot.poll, ...overrides.poll },
    runtime: { ...snapshot.runtime, ...overrides.runtime },
    memory: { ...snapshot.memory, ...overrides.memory },
    storage: { ...snapshot.storage, ...overrides.storage },
    load: { ...snapshot.load, ...overrides.load },
    queue: { ...snapshot.queue, ...overrides.queue },
  };
}

function plan(overrides = {}) {
  return buildOperationsPlan({
    now: NOW,
    resourceSnapshot: resourceSnapshot(NOW),
    retentionPolicy: retentionPolicy(),
    retentionInventory: inventory(),
    ...overrides,
  });
}

test("fake resource matrix maps each deterministic condition to one bounded action", () => {
  const cases = [
    [resourceSnapshot(NOW), {}, "recover", "none"],
    [resourceSnapshot(NOW, { runtime: { ready: false } }), {}, "protect", "try_restart_single_service"],
    [resourceSnapshot(NOW, { memory: { availableMb: 400 } }), {}, "protect", "pause_intake"],
    [resourceSnapshot(NOW, { storage: { usedPercent: 92 } }), {}, "protect", "reclaim_explicit_cache"],
    [resourceSnapshot(NOW, { storage: { inodeUsedPercent: 92 } }), {}, "protect", "reclaim_explicit_cache"],
    [resourceSnapshot(NOW, { load: { oneMinute: 4.2 } }), {}, "protect", "pause_intake"],
    [resourceSnapshot(NOW, { queue: { depth: 20, oldestQueuedAt: NOW } }), {}, "protect", "pause_intake"],
    [resourceSnapshot(NOW, { memory: { availableMb: 700 } }), {}, "warn", "refresh_status"],
    [resourceSnapshot(NOW), { backupEligible: true }, "recover", "trigger_local_backup"],
  ];
  for (const [snapshot, extra, guardState, action] of cases) {
    const result = plan({ resourceSnapshot: snapshot, ...extra });
    assert.equal(result.resource.guard_state, guardState);
    assert.equal(result.action.kind, action);
    assert.equal(result.action.bounded, true);
    assert.equal(result.action.max_invocations, action === "none" ? 0 : 1);
  }
});

test("protect state has deterministic hysteresis and only a full recovery returns recover", () => {
  const protectedPlan = plan({
    resourceSnapshot: resourceSnapshot(NOW, { memory: { availableMb: 400 } }),
  });
  const protectedReceipt = executeSingleBoundedAction({
    plan: protectedPlan,
    actionExecutor: () => ({ status: "simulator_applied" }),
  }).receipt;
  const warningAt = "2026-07-27T03:22:00.000Z";
  const warningPlan = buildOperationsPlan({
    now: warningAt,
    resourceSnapshot: resourceSnapshot(warningAt, { storage: { usedPercent: 80 } }),
    retentionPolicy: retentionPolicy(),
    retentionInventory: inventory(),
    priorReceipt: protectedReceipt,
  });
  const recoveredAt = "2026-07-27T03:23:00.000Z";
  const recoveredPlan = buildOperationsPlan({
    now: recoveredAt,
    resourceSnapshot: resourceSnapshot(recoveredAt),
    retentionPolicy: retentionPolicy(),
    retentionInventory: inventory(),
    priorReceipt: protectedReceipt,
  });

  assert.equal(warningPlan.resource.guard_state, "protect");
  assert.equal(recoveredPlan.resource.guard_state, "recover");
  assert.equal(recoveredPlan.action.kind, "none");
});

test("restart receipts enforce cooldown and a finite restart budget without waiting", () => {
  const unhealthyPlan = plan({
    resourceSnapshot: resourceSnapshot(NOW, { runtime: { ready: false } }),
  });
  let calls = 0;
  const applied = executeSingleBoundedAction({
    plan: unhealthyPlan,
    actionExecutor: (request) => {
      calls += 1;
      assert.deepEqual(request, {
        kind: "try_restart_single_service",
        target: "cyberboss-cloud.service",
        reason: "runtime_unhealthy",
        bounded: true,
        max_invocations: 1,
      });
      return { status: "simulator_applied" };
    },
  });
  const cooldownAt = "2026-07-27T03:21:00.000Z";
  const cooldownPlan = buildOperationsPlan({
    now: cooldownAt,
    resourceSnapshot: resourceSnapshot(cooldownAt, { runtime: { ready: false } }),
    retentionPolicy: retentionPolicy(),
    retentionInventory: inventory(),
    priorReceipt: applied.receipt,
  });
  const exhaustedReceipt = {
    ...applied.receipt,
    generated_at: "2026-07-27T03:22:00.000Z",
    last_action_at: "2026-07-27T03:22:00.000Z",
    restart_attempts: 3,
    outcome: "simulator_applied",
    receipt_id: "receipt_aaaaaaaaaaaaaaaaaaaaaaaa",
  };
  const exhaustedAt = "2026-07-27T03:24:00.000Z";
  const exhaustedPlan = buildOperationsPlan({
    now: exhaustedAt,
    resourceSnapshot: resourceSnapshot(exhaustedAt, { runtime: { ready: false } }),
    retentionPolicy: retentionPolicy(),
    retentionInventory: inventory(),
    priorReceipt: exhaustedReceipt,
  });

  assert.equal(calls, 1);
  assert.equal(applied.status, "simulator_applied");
  assert.equal(applied.invocations, 1);
  assert.equal(applied.real_service_operations, 0);
  assert.equal(cooldownPlan.action.kind, "none");
  assert.equal(cooldownPlan.action.reason, "cooldown_active");
  assert.equal(exhaustedPlan.action.kind, "none");
  assert.equal(exhaustedPlan.action.reason, "restart_budget_exhausted");
});

test("missing executor remains activation pending and never invokes a real service", () => {
  const result = executeSingleBoundedAction({
    plan: plan({ resourceSnapshot: resourceSnapshot(NOW, { runtime: { ready: false } }) }),
  });
  assert.equal(result.status, "activation_pending");
  assert.equal(result.invocations, 0);
  assert.equal(result.real_service_operations, 0);
  assert.equal(result.real_backup_operations, 0);
  assert.equal(result.control_plane_llm_calls, 0);
  assert.equal(result.operations_llm_calls, 0);
});

test("retention caps produce review-only backup/log candidates, cache reclaim, and protected spool", () => {
  const report = buildRetentionReport({
    policy: retentionPolicy(),
    now: "2026-07-27T04:00:00.000Z",
    inventory: inventory({
      local_backups: [
        { id: "backup-old", created_at: "2026-07-24T04:00:00.000Z", bytes: 10, status: "local_verified" },
        { id: "backup-middle", created_at: "2026-07-25T04:00:00.000Z", bytes: 10, status: "local_verified" },
        { id: "backup-new", created_at: "2026-07-26T04:00:00.000Z", bytes: 10, status: "local_verified" },
        { id: "backup-bad", created_at: "2026-07-26T03:00:00.000Z", bytes: 10, status: "failed" },
      ],
      runtime_logs: [
        { id: "log-old", created_at: "2026-07-19T03:59:59.000Z", bytes: 4 },
        { id: "log-new", created_at: "2026-07-27T03:00:00.000Z", bytes: 4 },
      ],
      diagnostic_summaries: [
        { id: "diag-old", created_at: "2026-06-26T03:59:59.000Z", bytes: 4 },
      ],
      build_cache_bytes: 536870913,
      spool_entries: 9,
    }),
  });

  assert.equal(report.state, "reclaim_required");
  assert.deepEqual(report.backup_prune_candidate_ids, ["backup-old"]);
  assert.deepEqual(report.isolate_backup_ids, ["backup-bad"]);
  assert.deepEqual(report.expired_runtime_log_ids, ["log-old"]);
  assert.deepEqual(report.expired_diagnostic_summary_ids, ["diag-old"]);
  assert.equal(report.cache_reclaim_bytes, 1);
  assert.equal(report.spool_entries_protected, 9);
  assert.equal(report.automatic_backup_or_log_delete, false);
  assert.equal(report.raw_private_messages_in_github, false);
  assert.equal(report.auth_cache_in_standard_backup, false);
});

test("invalid receipts and sensitive retention facts fail closed before any action", () => {
  const invalidReceipt = {
    schema_version: "cyberboss.deterministic-operations.v1",
    generated_at: NOW,
    guard_state: "recover",
    last_action: "none",
    last_action_at: null,
    restart_window_started_at: NOW,
    restart_attempts: 0,
    outcome: "-----BEGIN",
    receipt_id: "receipt_bbbbbbbbbbbbbbbbbbbbbbbb",
  };
  assert.throws(
    () => plan({ priorReceipt: invalidReceipt }),
    (error) => error instanceof CanonicalOperationsError && error.code === "OPERATIONS_PRIVACY_VIOLATION",
  );
  assert.throws(
    () => buildRetentionReport({
      policy: { ...retentionPolicy(), local_verified_backups: 3 },
      inventory: inventory(),
      now: NOW,
    }),
    (error) => error instanceof CanonicalOperationsError && error.code === "RETENTION_POLICY_INVALID",
  );
});
