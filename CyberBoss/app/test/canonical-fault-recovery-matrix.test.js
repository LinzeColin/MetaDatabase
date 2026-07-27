"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  FAULT_RECOVERY_SCHEMA,
  FROZEN_FAULT_RECOVERY_RECEIPTS,
  POSTDEPLOY_FAULT_PLAN_SCHEMA,
  FaultRecoveryError,
  assertFrozenFaultRecoveryCases,
  buildFaultRecoveryMatrix,
  buildPostdeployFaultMatrixPlan,
} = require("../src/services/assurance/canonical-fault-recovery-matrix");

function mutableReceipts() {
  return JSON.parse(JSON.stringify(FROZEN_FAULT_RECOVERY_RECEIPTS));
}

test("fault recovery matrix is deterministic across fake-clock, crash-cut, recovery, and isolated restore cases", () => {
  const first = buildFaultRecoveryMatrix();
  const second = buildFaultRecoveryMatrix();
  assert.deepEqual(second, first);
  assert.equal(assertFrozenFaultRecoveryCases(), true);
  assert.equal(first.schema_version, FAULT_RECOVERY_SCHEMA);
  assert.equal(first.product_version, "v0.0.0.5");
  assert.equal(first.evaluation_mode, "local_deterministic_fixture_matrix");
  assert.equal(first.status, "passed");
  assert.equal(first.frozen_case_count, 14);
  assert.equal(first.underlying_suite_count, 7);
  assert.match(first.report_digest, /^[0-9a-f]{64}$/);
  assert.equal(first.aggregate.lost_messages, 0);
  assert.equal(first.aggregate.duplicate_execution, 0);
  assert.equal(first.aggregate.duplicate_side_effects, 0);
  assert.equal(first.aggregate.unbounded_retries, 0);
  assert.equal(first.aggregate.rollback_restore_valid, true);
  assert.equal(first.aggregate.real_time_waits, 0);
  assert.equal(first.aggregate.network_or_provider_operations, 0);
  assert.equal(first.aggregate.control_plane_llm_calls, 0);
  assert.equal(first.aggregate.operations_llm_calls, 0);
  assert.equal(first.aggregate.macos_launchd_dependency, false);
  assert.equal(first.recovery_boundary.external_recovery_execution, "activation_pending");
  assert.ok(first.results.some((entry) => entry.id === "backup_isolated_restore"));
  assert.ok(first.results.some((entry) => entry.id === "canonical_unknown_outcome"));
});

test("fault matrix fails closed for loss, duplicate, wait, model, and external provider mutations", () => {
  const loss = mutableReceipts();
  loss[0].loss_count = 1;
  assert.throws(
    () => buildFaultRecoveryMatrix({ receipts: loss }),
    (caught) => caught instanceof FaultRecoveryError && caught.code === "FAULT_RECOVERY_LOSS_DETECTED",
  );

  const duplicate = mutableReceipts();
  duplicate[7].duplicate_execution_count = 1;
  assert.throws(
    () => buildFaultRecoveryMatrix({ receipts: duplicate }),
    (caught) => caught instanceof FaultRecoveryError && caught.code === "FAULT_RECOVERY_DUPLICATE_EXECUTION_DETECTED",
  );

  const wait = mutableReceipts();
  wait[0].real_time_waits = 1;
  assert.throws(
    () => buildFaultRecoveryMatrix({ receipts: wait }),
    (caught) => caught instanceof FaultRecoveryError && caught.code === "FAULT_RECOVERY_WAIT_DETECTED",
  );

  const model = mutableReceipts();
  model[0].operations_llm_calls = 1;
  assert.throws(
    () => buildFaultRecoveryMatrix({ receipts: model }),
    (caught) => caught instanceof FaultRecoveryError && caught.code === "FAULT_RECOVERY_MODEL_OPERATION_FORBIDDEN",
  );

  const provider = mutableReceipts();
  provider[0].network_or_provider_operations = 1;
  assert.throws(
    () => buildFaultRecoveryMatrix({ receipts: provider }),
    (caught) => caught instanceof FaultRecoveryError && caught.code === "FAULT_RECOVERY_PROVIDER_OPERATION_FORBIDDEN",
  );
});

test("postdeploy fault plan is nonblocking and keeps real activation pending", () => {
  const plan = buildPostdeployFaultMatrixPlan();
  assert.equal(plan.schema_version, POSTDEPLOY_FAULT_PLAN_SCHEMA);
  assert.equal(plan.status, "passed");
  assert.equal(plan.mode, "manual_or_ci_nonblocking");
  assert.equal(plan.trigger, "manual_or_ci");
  assert.equal(plan.full_matrix_case_count, 14);
  assert.equal(plan.timer_installation, "activation_pending");
  assert.equal(plan.timer_enabled, false);
  assert.equal(plan.current_deployment_blocked, false);
  assert.equal(plan.next_native_task_blocked, false);
  assert.equal(plan.blocking_wait_nodes, 0);
  assert.equal(plan.real_time_waits, 0);
  assert.equal(plan.deployment_mutations, 0);
  assert.equal(plan.network_or_provider_operations, 0);
  assert.equal(plan.control_plane_llm_calls, 0);
  assert.equal(plan.operations_llm_calls, 0);
  assert.equal(plan.macos_launchd_dependency, false);
  assert.match(plan.plan_digest, /^[0-9a-f]{64}$/);
});
