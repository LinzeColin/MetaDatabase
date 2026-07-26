"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const PROJECT_ROOT = path.resolve(__dirname, "..");

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb220-contract-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

test("CB-220 code surface retains the frozen TaskPack and source boundary", () => {
  const dag = fs.readFileSync(
    path.join(
      PROJECT_ROOT,
      "docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml",
    ),
    "utf8",
  );
  const task = dag.slice(
    dag.indexOf("- id: CB-220"),
    dag.indexOf("- id: CB-230"),
  );
  for (const marker of [
    "phase: P2.3",
    "- CB-200",
    "- CB-120",
    "- AC-012",
    "- AC-013",
    "- AC-014",
    "- AC-015",
    "- AC-045",
    "- AC-064",
    "pass_gate: PG-2",
  ]) {
    assert.match(task, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  const sourceLock = JSON.parse(
    fs.readFileSync(path.join(PROJECT_ROOT, "machine/source-lock.json"), "utf8"),
  );
  assert.deepEqual(
    new Set(
      sourceLock.whereabouts_license_conflict.compliance_expression
        .split("AND")
        .map((value) => value.trim()),
    ),
    new Set(["AGPL-3.0-only", "GPL-3.0-only"]),
  );
  assert.equal(
    sourceLock.whereabouts_license_conflict
      .preserve_original_license_and_source,
    true,
  );
  assert.equal(
    sourceLock.whereabouts_license_conflict.upstream_clarification_received,
    false,
  );
  assert.deepEqual(
    Object.values(sourceLock.upstream_relationship),
    Object.values(sourceLock.upstream_relationship).map(() => false),
  );
});

test("CB-220 executable acceptance emits only bounded fixture claims", (t) => {
  const directory = temporaryDirectory(t);
  const output = path.join(directory, "acceptance.json");
  const result = spawnSync(
    process.execPath,
    [
      path.join(PROJECT_ROOT, "app/scripts/job-scheduler-acceptance.js"),
      "--output",
      output,
    ],
    {
      cwd: PROJECT_ROOT,
      encoding: "utf8",
      timeout: 180_000,
      maxBuffer: 8 * 1024 * 1024,
    },
  );
  assert.equal(
    result.status,
    0,
    `status=${result.status} stdout=${result.stdout} stderr=${result.stderr}`,
  );
  assert.match(result.stdout, /CB220_JOB_SCHEDULER_ACCEPTANCE=PASS/);
  const report = JSON.parse(fs.readFileSync(output, "utf8"));
  assert.equal(report.result, "passed");
  assert.equal(report.scheduler.max_active_runtime_leases, 1);
  assert.equal(report.scheduler.fifo_dispatch_order, true);
  assert.equal(report.workspace.absolute_path_dispatched, false);
  assert.equal(report.workspace.symlink_escape_dispatched, false);
  assert.equal(report.resource_gate.protect_blocks_mutation, true);
  assert.equal(report.stop.acknowledgement_claimed_terminal, false);
  assert.equal(report.stop.terminal_by_runtime_status.interrupted, "cancelled");
  assert.equal(report.recovery.ambiguous_mutation_replayed, false);
  assert.equal(report.phase_boundary.outbox_worker_integrated, false);
  assert.equal(report.phase_boundary.pg_2_executed, false);
  assert.equal(report.executable_suite.real_credentials, false);
  assert.equal(report.executable_suite.real_provider, false);
  assert.doesNotMatch(
    JSON.stringify(report),
    /(?:wxid_|Authorization|\/Users\/|\/var\/lib\/|thread-[A-Za-z0-9])/,
  );
});
