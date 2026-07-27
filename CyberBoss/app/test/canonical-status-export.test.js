const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const test = require("node:test");

const {
  ADAPTER_IDS,
  COMPONENT_IDS,
  CanonicalStatusError,
  buildGlobalStatusRow,
  buildRedactedStatusSnapshot,
  readStatusSnapshot,
  writeGlobalStatusRowAtomic,
  writeStatusSnapshotAtomic,
} = require("../src/services/status/canonical-status-export");

const COMMIT = "a".repeat(40);

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-status-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function healthyComponents(overrides = {}) {
  return Object.fromEntries(COMPONENT_IDS.map((id) => [id, {
    state: "healthy",
    reason_code: `${id}_verified`,
    age_seconds: 0,
    ...(overrides[id] || {}),
  }]));
}

function facts(overrides = {}) {
  const componentValues = healthyComponents(overrides.components || {});
  Object.assign(componentValues, overrides.componentExtras || {});
  return {
    sourceCommit: overrides.sourceCommit || COMMIT,
    generatedAt: overrides.generatedAt || "2026-07-27T00:00:00.000Z",
    components: componentValues,
    metrics: {
      queue_depth: 0,
      oldest_job_age_seconds: null,
      outbox_pending: 0,
      canonical_pending: 0,
      control_plane_llm_calls_total: 0,
      business_runtime_model_calls_total: 0,
      self_heal_agent_invocations_total: 0,
      memory_available_bytes: 1024,
      disk_available_bytes: 2048,
      ...(overrides.metrics || {}),
    },
    adapters: Object.fromEntries(ADAPTER_IDS.map((id) => [id, "verified"])),
    release: {
      version: "v0.0.0.5",
      commit: COMMIT,
      slot: "candidate",
      rollback_ready: true,
      ...(overrides.release || {}),
    },
    previousSnapshot: overrides.previousSnapshot || null,
    ...(overrides.extra || {}),
  };
}

function build(overrides = {}) {
  const value = facts(overrides);
  return buildRedactedStatusSnapshot({
    generatedAt: value.generatedAt,
    sourceCommit: value.sourceCommit,
    runtimeSnapshot: value.runtimeSnapshot || {},
    components: value.components,
    metrics: value.metrics,
    adapters: value.adapters,
    release: value.release,
    previousSnapshot: value.previousSnapshot || null,
  });
}

test("status snapshot is deterministic, redacted, zero-agent, and compatible with the existing global row", () => {
  const snapshot = build();
  assert.equal(snapshot.schema_version, "cyberboss.status.v2");
  assert.equal(snapshot.overall, "healthy");
  assert.match(snapshot.generation_id, /^[a-f0-9]{24}$/);
  assert.equal(snapshot.metrics.control_plane_llm_calls_total, 0);
  assert.equal(snapshot.metrics.self_heal_agent_invocations_total, 0);

  const row = buildGlobalStatusRow({
    snapshot,
    observedAt: "2026-07-27T00:00:30.000Z",
  });
  assert.equal(row.status, "access");
  assert.equal(row.generation_id, snapshot.generation_id);
  assert.deepEqual(row.parts, ["前台", "后台"]);
  assert.equal(row.agent, "无");
  assert.equal(row.notify, "无");
  const serialized = JSON.stringify({ snapshot, row });
  for (const forbidden of ["prompt", "thread", "token", "authorization", "wxid_", "/var/", "/home/"]) {
    assert.equal(serialized.toLowerCase().includes(forbidden), false);
  }
});

test("every required component independently controls severity and unsafe states never render green", () => {
  for (const id of COMPONENT_IDS) {
    const snapshot = build({
      components: { [id]: { state: "failed", reason_code: `${id}_failed`, age_seconds: 0 } },
    });
    assert.equal(snapshot.overall, "failed", id);
  }
  const unknown = build({
    components: { runtime: { state: "unknown", reason_code: "runtime_not_observed", age_seconds: null } },
  });
  const pending = build({
    components: { runtime: { state: "activation_pending", reason_code: "runtime_activation_pending", age_seconds: null } },
  });
  const degraded = build({
    components: { resources: { state: "degraded", reason_code: "disk_pressure", age_seconds: 0 } },
  });
  assert.equal(unknown.overall, "unknown");
  assert.equal(pending.overall, "activation_pending");
  assert.equal(degraded.overall, "degraded");
  assert.equal(buildGlobalStatusRow({ snapshot: unknown, observedAt: "2026-07-27T00:00:01.000Z" }).status, "down");
  assert.equal(buildGlobalStatusRow({ snapshot: pending, observedAt: "2026-07-27T00:00:01.000Z" }).status, "down");
  assert.equal(buildGlobalStatusRow({ snapshot: degraded, observedAt: "2026-07-27T00:00:01.000Z" }).status, "access");
});

test("snapshot and existing-collector row writes survive deterministic crash cuts without partial JSON", (t) => {
  const root = temporaryRoot(t);
  const snapshotPath = path.join(root, "snapshot.json");
  const rowPath = path.join(root, "row.json");
  const first = build();
  writeStatusSnapshotAtomic({ snapshot: first, outputPath: snapshotPath });
  const firstBytes = fs.readFileSync(snapshotPath, "utf8");

  const second = build({
    generatedAt: "2026-07-27T00:00:01.000Z",
    previousSnapshot: first,
  });
  assert.throws(
    () => writeStatusSnapshotAtomic({ snapshot: second, outputPath: snapshotPath, crashPoint: "before_rename" }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_SNAPSHOT_CRASH_BEFORE_RENAME",
  );
  assert.equal(fs.readFileSync(snapshotPath, "utf8"), firstBytes);
  assert.deepEqual(readStatusSnapshot(snapshotPath), first);

  assert.throws(
    () => writeStatusSnapshotAtomic({ snapshot: second, outputPath: snapshotPath, crashPoint: "after_rename_before_dirsync" }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_SNAPSHOT_CRASH_AFTER_RENAME",
  );
  assert.deepEqual(readStatusSnapshot(snapshotPath), second);

  const row = buildGlobalStatusRow({ snapshot: second, observedAt: "2026-07-27T00:00:02.000Z" });
  writeGlobalStatusRowAtomic({ row, outputPath: rowPath });
  assert.throws(
    () => writeGlobalStatusRowAtomic({ row, outputPath: rowPath, crashPoint: "before_rename" }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_ROW_CRASH_BEFORE_RENAME",
  );
  assert.equal(JSON.parse(fs.readFileSync(rowPath, "utf8")).generation_id, second.generation_id);
  const olderRow = buildGlobalStatusRow({ snapshot: first, observedAt: "2026-07-27T00:00:02.000Z" });
  assert.throws(
    () => writeGlobalStatusRowAtomic({ row: olderRow, outputPath: rowPath }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_GLOBAL_ROW_GENERATION_NON_MONOTONIC",
  );
});

test("schema, DLP, generation and zero-agent violations fail closed", () => {
  assert.throws(
    () => build({ metrics: { control_plane_llm_calls_total: 1 } }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_ZERO_AGENT_COUNTER_VIOLATION",
  );
  assert.throws(
    () => build({ components: { runtime: { state: "healthy", reason_code: "token_leak", age_seconds: 0 } } }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_COMPONENT_INVALID",
  );
  assert.throws(
    () => build({ componentExtras: { unknown_component: { state: "healthy", reason_code: "unknown_verified", age_seconds: 0 } } }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_COMPONENT_UNKNOWN",
  );
  assert.throws(
    () => build({ release: { version: "v9.9.9.9" } }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_RELEASE_INVALID",
  );
  const first = build();
  assert.throws(
    () => build({ previousSnapshot: first }),
    (error) => error instanceof CanonicalStatusError && error.code === "STATUS_GENERATION_NON_MONOTONIC",
  );
});
