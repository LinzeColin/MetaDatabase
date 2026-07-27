"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  FROZEN_CORE_SLICES,
  SOFTWARE_CORRECTNESS_SCHEMA,
  assertFrozenCoreSuite,
  buildPostdeployAutomation,
  credentialFreeEnvironment,
  runFrozenCoreSuite,
} = require("../scripts/software-correctness-suite");

test("frozen high-risk software suite has exact safe slices for migration and rollback", () => {
  assert.equal(assertFrozenCoreSuite(), true);
  assert.equal(FROZEN_CORE_SLICES.length, 10);
  assert.deepEqual(
    FROZEN_CORE_SLICES.map((slice) => slice.id),
    [
      "install_build_start",
      "migration_compatibility",
      "inbox_crash_recovery",
      "outbox_crash_recovery",
      "scheduler_singleton",
      "canonical_conflict_privacy",
      "timeline_status_access",
      "backup_restore",
      "resource_self_heal",
      "rollback_discrimination",
    ],
  );
  for (const slice of FROZEN_CORE_SLICES) {
    for (const testFile of slice.test_files) {
      assert.match(testFile, /^(?:app\/test|tests)\/[A-Za-z0-9_.-]+\.test\.js$/);
      assert.equal(testFile.includes(".."), false);
    }
  }
});

test("frozen high-risk suite passes only when every slice reports a local passing test", () => {
  const calls = [];
  const receipt = runFrozenCoreSuite({
    environment: { SAFE_VALUE: "kept", CB_API_TOKEN: "removed" },
    runner: ({ slice, command, cwd, environment }) => {
      calls.push({ id: slice.id, command, cwd, environment });
      return { status: 0, stdout: "# fail 0\n", stderr: "" };
    },
  });
  assert.equal(receipt.schema_version, SOFTWARE_CORRECTNESS_SCHEMA);
  assert.equal(receipt.status, "passed");
  assert.equal(receipt.gate, "candidate_eligible_for_next_native_task");
  assert.equal(receipt.failed_slices.length, 0);
  assert.equal(receipt.migration_compatibility, "passed");
  assert.equal(receipt.rollback_discrimination, "passed");
  assert.equal(receipt.deployment_mutations, 0);
  assert.equal(receipt.network_or_provider_operations, 0);
  assert.equal(receipt.real_time_waits, 0);
  assert.equal(receipt.control_plane_llm_calls, 0);
  assert.equal(receipt.operations_llm_calls, 0);
  assert.equal(receipt.macos_launchd_dependency, false);
  assert.equal(calls.length, 10);
  assert.equal(calls[0].command[1], "--test");
  assert.equal("CB_API_TOKEN" in calls[0].environment, false);
  assert.equal(calls[0].environment.SAFE_VALUE, "kept");
});

test("a failed slice discriminates a rejected candidate and preserves the accepted baseline", () => {
  const receipt = runFrozenCoreSuite({
    runner: ({ slice }) => ({ status: slice.id === "rollback_discrimination" ? 1 : 0 }),
  });
  assert.equal(receipt.status, "failed");
  assert.equal(receipt.rollback_discrimination, "failed");
  assert.deepEqual(receipt.failed_slices, ["rollback_discrimination"]);
  assert.equal(receipt.gate, "discard_candidate_keep_accepted_baseline");
  assert.equal(receipt.deployment_mutations, 0);
});

test("postdeploy automation is manual-or-CI, nonblocking, and contains no waiting or provider action", () => {
  const plan = buildPostdeployAutomation();
  assert.equal(plan.schema_version, SOFTWARE_CORRECTNESS_SCHEMA);
  assert.equal(plan.status, "passed");
  assert.equal(plan.mode, "postdeploy_nonblocking");
  assert.equal(plan.trigger, "manual_or_ci");
  assert.equal(plan.current_deployment_blocked, false);
  assert.equal(plan.next_native_task_blocked, false);
  assert.equal(plan.blocking_wait_nodes, 0);
  assert.equal(plan.real_time_waits, 0);
  assert.equal(plan.deployment_mutations, 0);
  assert.equal(plan.network_or_provider_operations, 0);
  assert.equal(plan.control_plane_llm_calls, 0);
  assert.equal(plan.operations_llm_calls, 0);
  assert.equal(plan.macos_launchd_dependency, false);
  assert.deepEqual(plan.required_followup, [
    "status_summary",
    "incident_or_recovery_summary",
    "next_release_backlog",
  ]);
});

test("credential scrubbing removes named credentials without reporting their values", () => {
  const scrubbed = credentialFreeEnvironment({
    SAFE_VALUE: "kept",
    SOME_SECRET: "hidden",
    AWS_REGION: "hidden",
  });
  assert.deepEqual(scrubbed.environment, { SAFE_VALUE: "kept" });
  assert.equal(scrubbed.removed, 2);
});
