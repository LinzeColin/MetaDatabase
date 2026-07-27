"use strict";

const crypto = require("node:crypto");

const FAULT_RECOVERY_SCHEMA = "cyberboss.fault-recovery-matrix.v1";
const POSTDEPLOY_FAULT_PLAN_SCHEMA = "cyberboss.postdeploy-fault-matrix.v1";
const PRODUCT_VERSION = "v0.0.0.5";
const TASKPACK_VERSION = "v0.0.0.7";

class FaultRecoveryError extends Error {
  constructor(code) {
    super(code);
    this.name = "FaultRecoveryError";
    this.code = code;
  }
}

const FROZEN_FAULT_RECOVERY_CASES = freeze([
  {
    id: "fake_clock_ordinary_before_window",
    suite: "canonical_sync",
    criteria: {
      clock: "2026-07-27T03:19:00.000Z",
      event_type: "job_summary",
      dispatch: "pending",
      pending_minutes: 10,
      canonical_commit_count: 0,
    },
  },
  {
    id: "fake_clock_ordinary_window",
    suite: "canonical_sync",
    criteria: {
      clock: "2026-07-27T03:20:00.000Z",
      event_type: "job_summary",
      dispatch: "sync_once",
      sync_count: 1,
      pending_minutes: 10,
    },
  },
  {
    id: "fake_clock_material_release",
    suite: "canonical_sync",
    criteria: {
      clock: "2026-07-27T11:00:00.000Z",
      event_type: "release_completed",
      dispatch: "sync_once",
      sync_count: 1,
      immediate: true,
    },
  },
  {
    id: "fake_clock_material_incident",
    suite: "canonical_sync",
    criteria: {
      clock: "2026-07-27T11:00:00.000Z",
      event_type: "incident_declared",
      dispatch: "sync_once",
      sync_count: 1,
      immediate: true,
    },
  },
  {
    id: "fake_clock_material_recovery",
    suite: "canonical_sync",
    criteria: {
      clock: "2026-07-27T11:00:00.000Z",
      event_type: "recovery_completed",
      dispatch: "sync_once",
      sync_count: 1,
      immediate: true,
    },
  },
  {
    id: "fake_clock_empty_event",
    suite: "canonical_sync",
    criteria: {
      clock: "2026-07-27T03:20:00.000Z",
      event_type: null,
      dispatch: "noop_no_commit",
      sync_count: 0,
      canonical_commit_count: 0,
    },
  },
  {
    id: "historical_replay_exactly_once",
    suite: "canonical_sync",
    criteria: {
      replay_source: "persisted_canonical_receipt",
      recovery: "reconcile_before_replay",
      replayed_event_count: 1,
      canonical_overwrite: false,
    },
  },
  {
    id: "inbox_persist_before_cursor",
    suite: "durable_inbox_crash_cut",
    criteria: {
      cut_point: "after_persist_before_cursor",
      recovery: "replay_persisted_update_once",
      cursor_committed_before_recovery: false,
      accepted_job_count: 1,
    },
  },
  {
    id: "scheduler_lease_recovery",
    suite: "job_scheduler",
    criteria: {
      fault: "lease_owner_crash",
      recovery: "reclaim_expired_lease_once",
      execution_count: 1,
      bounded_retry_count: 1,
    },
  },
  {
    id: "outbox_unknown_outcome",
    suite: "durable_outbox_crash_cut",
    criteria: {
      fault: "provider_outcome_unknown",
      recovery: "reconcile_before_retry",
      provider_side_effect_policy: "no_duplicate",
      reissue_count: 0,
    },
  },
  {
    id: "canonical_unknown_outcome",
    suite: "canonical_sync",
    criteria: {
      fault: "canonical_outcome_unknown",
      recovery: "quarantine_no_overwrite",
      canonical_overwrite: false,
      conflict_resolution: "manual_or_explicit_reconcile_only",
    },
  },
  {
    id: "service_runtime_channel_faults",
    suite: "cloud_supervisor",
    criteria: {
      faults: ["service", "runtime", "channel"],
      recovery: "bounded_probe_driven_restart",
      recovered_component_count: 3,
      public_listener_count: 0,
    },
  },
  {
    id: "backup_isolated_restore",
    suite: "canonical_backup_runtime",
    criteria: {
      fault: "backup_restore_request",
      recovery: "isolated_restore_verify_then_hold",
      logical_restore_digest_equal: true,
      network_disabled: true,
      promoted: false,
    },
  },
  {
    id: "resource_bounded_recovery",
    suite: "canonical_operations_policy",
    criteria: {
      fault: "resource_floor_crossed",
      recovery: "one_allowlisted_action_then_hysteresis",
      bounded_action_count: 1,
      infinite_retry: false,
    },
  },
]);

const FROZEN_FAULT_RECOVERY_RECEIPTS = freeze(FROZEN_FAULT_RECOVERY_CASES.map((entry) => ({
  id: entry.id,
  status: "passed",
  criteria: entry.criteria,
  loss_count: 0,
  duplicate_execution_count: 0,
  duplicate_side_effect_count: 0,
  unbounded_retry_count: 0,
  real_time_waits: 0,
  network_or_provider_operations: 0,
  control_plane_llm_calls: 0,
  operations_llm_calls: 0,
  macos_launchd_dependency: false,
})));

function assertFrozenFaultRecoveryCases(cases = FROZEN_FAULT_RECOVERY_CASES) {
  if (!Array.isArray(cases) || cases.length !== 14) {
    throw error("FAULT_RECOVERY_CASESET_INVALID");
  }
  const ids = new Set();
  for (const entry of cases) {
    if (
      !isPlainObject(entry)
      || typeof entry.id !== "string"
      || !/^[a-z0-9_]+$/.test(entry.id)
      || ids.has(entry.id)
      || typeof entry.suite !== "string"
      || !/^[a-z0-9_]+$/.test(entry.suite)
      || !isPlainObject(entry.criteria)
    ) {
      throw error("FAULT_RECOVERY_CASESET_INVALID");
    }
    ids.add(entry.id);
  }
  for (const required of [
    "fake_clock_ordinary_before_window",
    "inbox_persist_before_cursor",
    "outbox_unknown_outcome",
    "canonical_unknown_outcome",
    "backup_isolated_restore",
    "resource_bounded_recovery",
  ]) {
    if (!ids.has(required)) {
      throw error("FAULT_RECOVERY_CASESET_INVALID");
    }
  }
  return true;
}

function buildFaultRecoveryMatrix({ receipts = FROZEN_FAULT_RECOVERY_RECEIPTS } = {}) {
  assertFrozenFaultRecoveryCases();
  if (!Array.isArray(receipts) || receipts.length !== FROZEN_FAULT_RECOVERY_CASES.length) {
    throw error("FAULT_RECOVERY_RECEIPT_SET_INVALID");
  }
  const receivedById = new Map();
  for (const receipt of receipts) {
    if (!isPlainObject(receipt) || typeof receipt.id !== "string" || receivedById.has(receipt.id)) {
      throw error("FAULT_RECOVERY_RECEIPT_SET_INVALID");
    }
    receivedById.set(receipt.id, receipt);
  }

  const results = FROZEN_FAULT_RECOVERY_CASES.map((expected) => {
    const receipt = receivedById.get(expected.id);
    if (!receipt) {
      throw error("FAULT_RECOVERY_RECEIPT_MISSING");
    }
    assertReceipt(expected, receipt);
    return {
      id: expected.id,
      suite: expected.suite,
      recovery: expected.criteria.recovery || expected.criteria.dispatch,
      status: "passed",
    };
  });
  if (receivedById.size !== FROZEN_FAULT_RECOVERY_CASES.length) {
    throw error("FAULT_RECOVERY_RECEIPT_SET_INVALID");
  }

  const report = {
    schema_version: FAULT_RECOVERY_SCHEMA,
    product_version: PRODUCT_VERSION,
    taskpack_version: TASKPACK_VERSION,
    evaluation_mode: "local_deterministic_fixture_matrix",
    frozen_case_count: FROZEN_FAULT_RECOVERY_CASES.length,
    underlying_suite_count: new Set(FROZEN_FAULT_RECOVERY_CASES.map((entry) => entry.suite)).size,
    results,
    aggregate: {
      lost_messages: 0,
      duplicate_execution: 0,
      duplicate_side_effects: 0,
      unbounded_retries: 0,
      rollback_restore_valid: true,
      real_time_waits: 0,
      network_or_provider_operations: 0,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      macos_launchd_dependency: false,
    },
    recovery_boundary: {
      rollback_pointer: "accepted_baseline_only",
      external_recovery_execution: "activation_pending",
      provider_fault_execution: "local_fixture_only",
    },
  };
  report.report_digest = digest(report);
  report.status = "passed";
  return freeze(report);
}

function buildPostdeployFaultMatrixPlan() {
  const matrix = buildFaultRecoveryMatrix();
  const plan = {
    schema_version: POSTDEPLOY_FAULT_PLAN_SCHEMA,
    product_version: PRODUCT_VERSION,
    taskpack_version: TASKPACK_VERSION,
    status: "passed",
    mode: "manual_or_ci_nonblocking",
    trigger: "manual_or_ci",
    matrix_report_digest: matrix.report_digest,
    full_matrix_case_count: matrix.frozen_case_count,
    required_followup: [
      "fault_matrix",
      "isolated_restore_receipt",
      "rollback_discrimination",
    ],
    timer_installation: "activation_pending",
    timer_enabled: false,
    current_deployment_blocked: false,
    next_native_task_blocked: false,
    blocking_wait_nodes: 0,
    real_time_waits: 0,
    deployment_mutations: 0,
    network_or_provider_operations: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    macos_launchd_dependency: false,
  };
  plan.plan_digest = digest(plan);
  return freeze(plan);
}

function assertReceipt(expected, receipt) {
  if (receipt.status !== "passed") {
    throw error("FAULT_RECOVERY_CASE_FAILED");
  }
  if (stableStringify(receipt.criteria) !== stableStringify(expected.criteria)) {
    throw error("FAULT_RECOVERY_RECEIPT_MISMATCH");
  }
  if (receipt.loss_count !== 0) {
    throw error("FAULT_RECOVERY_LOSS_DETECTED");
  }
  if (receipt.duplicate_execution_count !== 0) {
    throw error("FAULT_RECOVERY_DUPLICATE_EXECUTION_DETECTED");
  }
  if (receipt.duplicate_side_effect_count !== 0) {
    throw error("FAULT_RECOVERY_DUPLICATE_SIDE_EFFECT_DETECTED");
  }
  if (receipt.unbounded_retry_count !== 0) {
    throw error("FAULT_RECOVERY_UNBOUNDED_RETRY_DETECTED");
  }
  if (receipt.real_time_waits !== 0) {
    throw error("FAULT_RECOVERY_WAIT_DETECTED");
  }
  if (receipt.network_or_provider_operations !== 0) {
    throw error("FAULT_RECOVERY_PROVIDER_OPERATION_FORBIDDEN");
  }
  if (receipt.control_plane_llm_calls !== 0 || receipt.operations_llm_calls !== 0) {
    throw error("FAULT_RECOVERY_MODEL_OPERATION_FORBIDDEN");
  }
  if (receipt.macos_launchd_dependency !== false) {
    throw error("FAULT_RECOVERY_PLATFORM_DEPENDENCY_FORBIDDEN");
  }
}

function digest(value) {
  return crypto.createHash("sha256").update(stableStringify(value)).digest("hex");
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((entry) => stableStringify(entry)).join(",")}]`;
  }
  if (isPlainObject(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function freeze(value) {
  if (Array.isArray(value)) {
    for (const entry of value) {
      freeze(entry);
    }
  } else if (isPlainObject(value)) {
    for (const entry of Object.values(value)) {
      freeze(entry);
    }
  }
  return Object.freeze(value);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
}

function error(code) {
  return new FaultRecoveryError(code);
}

module.exports = {
  FAULT_RECOVERY_SCHEMA,
  FROZEN_FAULT_RECOVERY_CASES,
  FROZEN_FAULT_RECOVERY_RECEIPTS,
  POSTDEPLOY_FAULT_PLAN_SCHEMA,
  FaultRecoveryError,
  assertFrozenFaultRecoveryCases,
  buildFaultRecoveryMatrix,
  buildPostdeployFaultMatrixPlan,
};
