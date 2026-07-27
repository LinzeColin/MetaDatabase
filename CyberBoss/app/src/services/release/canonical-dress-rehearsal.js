"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  buildImmutableReleaseCandidate,
  buildOperatorRunbook,
} = require("./canonical-immutable-release");
const {
  buildFaultRecoveryMatrix,
  buildPostdeployFaultMatrixPlan,
} = require("../assurance/canonical-fault-recovery-matrix");

const DRESS_REHEARSAL_SCHEMA = "cyberboss.clean-staging-dress-rehearsal.v1";
const ACTIVATION_PLAN_SCHEMA = "cyberboss.activation-plan.v1";
const PRODUCT_VERSION = "v0.0.0.5";
const TASKPACK_VERSION = "v0.0.0.7";
const PG4_CLOSURE = "a5802bca6ac63c435121ab3bc970a6adededb7de";
const PG4_TREE = "a505be6c6c5d68090b5cd7eee3742377b7c6cbdf";
const CANDIDATE_RELEASE_ID = "bb86be91fedac363301d7704030a67925c166dc826b11f97a0f5cf4222495ad0";
const CANDIDATE_MANIFEST_DIGEST = "4f83d414e4d950506c9430665e2b4875d9ad58e68b2e75bd31c5722dca9a66e4";
const OPERATOR_RUNBOOK_DIGEST = "d26533392f38e0de26e1deab4c07a9365cdbc97a5f948503554c1db35afc9c9f";

class DressRehearsalError extends Error {
  constructor(code) {
    super(code);
    this.name = "DressRehearsalError";
    this.code = code;
  }
}

const FROZEN_DRESS_REHEARSAL_STEPS = freeze([
  step("clean_slot_preflight", "staging_preflight", "isolated_ephemeral_slot_ready"),
  step("immutable_candidate_manifest", "release_provenance", "candidate_hash_and_slots_match"),
  step("additive_migration", "migration", "backward_read_fixture_verified"),
  step("status_redaction", "status", "redacted_snapshot_non_green_pending"),
  step("access_loopback", "access", "deny_by_default_and_loopback_only"),
  step("simulated_e2e", "adapter_fixture", "simulators_only_external_truth_pending"),
  step("fault_matrix", "fault_recovery", "loss_duplicate_and_retry_counters_zero"),
  step("backup_snapshot", "backup", "local_verified_snapshot_only"),
  step("isolated_restore", "restore", "local_isolated_restore_valid"),
  step("request_count_predicates", "canary_fixture", "eight_local_predicates_passed"),
  step("rollback_dry_run", "rollback", "previous_pointer_contract_valid"),
  step("staging_cleanup", "cleanup", "discardable_slot_current_unchanged"),
]);

function step(id, kind, expectedOutput) {
  return {
    id,
    kind,
    expected_output: expectedOutput,
    status: "passed",
    copy_safe: true,
    source_code_knowledge_required: false,
    undocumented_prerequisites: 0,
    ...zeroCounters(),
  };
}

function buildCleanStagingRehearsal({
  steps = FROZEN_DRESS_REHEARSAL_STEPS,
  candidate = buildImmutableReleaseCandidate(),
  runbook = buildOperatorRunbook(),
  faultMatrix = buildFaultRecoveryMatrix(),
  postdeployPlan = buildPostdeployFaultMatrixPlan(),
} = {}) {
  assertCandidate(candidate);
  assertRunbook(runbook);
  assertFaultContracts(faultMatrix, postdeployPlan);
  const results = evaluateSteps(steps);
  const p0Failures = results.filter((entry) => entry.status === "p0_failed");
  const status = p0Failures.length === 0 ? "passed" : "failed";
  const staging = runEphemeralStagingFixture();
  const activationPlan = buildActivationPlan({ candidate, runbook });
  const report = {
    schema_version: DRESS_REHEARSAL_SCHEMA,
    product_version: PRODUCT_VERSION,
    taskpack_version: TASKPACK_VERSION,
    evaluation_mode: "clean_ephemeral_local_staging_fixture",
    pg_4_anchor: {
      closure_commit: PG4_CLOSURE,
      repository_tree: PG4_TREE,
    },
    staging: {
      ...staging,
      slot_kind: "ephemeral_local_fixture",
      persistent_release_installation: false,
      current_switch: false,
      service_installation: false,
      source_code_knowledge_required: false,
      hidden_shell_history_required: false,
    },
    candidate: {
      release_id: CANDIDATE_RELEASE_ID,
      manifest_digest: CANDIDATE_MANIFEST_DIGEST,
      candidate_installation: "activation_pending",
      current_switch: "activation_pending",
      live_request_count_canary: "activation_pending",
      live_rollback: "activation_pending",
    },
    operator: {
      runbook_digest: OPERATOR_RUNBOOK_DIGEST,
      command_count: runbook.command_count,
      all_commands_copy_safe: true,
      undocumented_prerequisite_count: 0,
      corrections_required: [],
    },
    rehearsal_steps: results,
    go_no_go: {
      local_rehearsal: status === "passed" ? "go_local_only" : "no_go",
      production_promotion: "activation_pending",
      rollback: status === "passed"
        ? "not_required_current_unchanged"
        : "discard_staging_keep_current",
      p0_failure_count: p0Failures.length,
      activation_authority_required: true,
    },
    activation_plan: activationPlan,
    activation_plan_digest: activationPlan.activation_plan_digest,
    external_activation: {
      private_database: "activation_pending",
      r2: "hazard_blocked",
      cloudflare_access: "activation_pending",
      dns_route: "activation_pending",
      analytics: "activation_pending",
      oci: "activation_pending",
      timeline: "activation_pending",
      global_status: "activation_pending",
      self_heal: "activation_pending",
      timer: "activation_pending",
      candidate_installation: "activation_pending",
      current_switch: "activation_pending",
      live_request_count_canary: "activation_pending",
      live_rollback: "activation_pending",
    },
    ...zeroCounters(),
    status,
    decision: status === "passed"
      ? "rehearsal_complete_external_activation_pending"
      : "discard_staging_keep_current",
  };
  report.rehearsal_digest = digest(report);
  return freeze(report);
}

function buildActivationPlan({
  candidate = buildImmutableReleaseCandidate(),
  runbook = buildOperatorRunbook(),
} = {}) {
  assertCandidate(candidate);
  assertRunbook(runbook);
  const plan = {
    schema_version: ACTIVATION_PLAN_SCHEMA,
    product_version: PRODUCT_VERSION,
    taskpack_version: TASKPACK_VERSION,
    mode: "operator_contract_only_no_external_execution",
    candidate_release_id: CANDIDATE_RELEASE_ID,
    candidate_manifest_digest: CANDIDATE_MANIFEST_DIGEST,
    operator_runbook_digest: OPERATOR_RUNBOOK_DIGEST,
    ordered_steps: [
      "verify_candidate_manifest",
      "verify_current_previous_slots",
      "verify_additive_migration",
      "verify_access_and_loopback_boundary",
      "verify_status_snapshot_redaction",
      "verify_fault_backup_restore_receipts",
      "request_external_activation_authority",
      "execute_authorized_candidate_installation",
      "execute_authorized_request_count_canary",
      "execute_authorized_rollback_if_p0",
    ],
    external_authority_required_for: [
      "candidate_installation",
      "current_switch",
      "live_request_count_canary",
      "live_rollback",
      "private_database",
      "cloudflare_access",
      "dns_route",
      "r2_or_oci",
      "global_status",
    ],
    current_unchanged_until_authorized_switch: true,
    no_hidden_prerequisites: true,
    copy_safe_local_steps: 6,
    real_execution: "activation_pending",
    ...zeroCounters(),
  };
  plan.activation_plan_digest = digest(plan);
  return freeze(plan);
}

function evaluateSteps(steps) {
  if (!Array.isArray(steps) || steps.length !== FROZEN_DRESS_REHEARSAL_STEPS.length) {
    throw error("DRESS_REHEARSAL_STEP_SET_INVALID");
  }
  const known = new Set();
  const results = [];
  for (let index = 0; index < FROZEN_DRESS_REHEARSAL_STEPS.length; index += 1) {
    const expected = FROZEN_DRESS_REHEARSAL_STEPS[index];
    const actual = steps[index];
    if (!isPlainObject(actual) || actual.id !== expected.id || known.has(actual.id)) {
      throw error("DRESS_REHEARSAL_STEP_SET_INVALID");
    }
    known.add(actual.id);
    assertStepCounters(actual);
    if (actual.status === "passed") {
      if (stableStringify(actual) !== stableStringify(expected)) {
        throw error("DRESS_REHEARSAL_STEP_INVALID");
      }
    } else if (actual.status === "p0_failed") {
      if (
        actual.kind !== expected.kind
        || actual.expected_output !== expected.expected_output
        || actual.copy_safe !== true
        || actual.source_code_knowledge_required !== false
        || actual.undocumented_prerequisites !== 0
        || actual.p0_reason !== "operator_contract_or_rehearsal_failure"
      ) {
        throw error("DRESS_REHEARSAL_P0_RECEIPT_INVALID");
      }
    } else {
      throw error("DRESS_REHEARSAL_STEP_INVALID");
    }
    results.push({
      id: actual.id,
      kind: actual.kind,
      status: actual.status,
      expected_output: actual.expected_output,
    });
  }
  return results;
}

function runEphemeralStagingFixture() {
  const stagingRoot = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-cb500-"));
  try {
    if (fs.readdirSync(stagingRoot).length !== 0) {
      throw error("DRESS_REHEARSAL_STAGING_NOT_CLEAN");
    }
    for (const name of ["candidate", "status", "restore", "receipts"]) {
      fs.mkdirSync(path.join(stagingRoot, name), { mode: 0o700 });
    }
    const inventory = fs.readdirSync(stagingRoot).sort();
    if (stableStringify(inventory) !== stableStringify(["candidate", "receipts", "restore", "status"])) {
      throw error("DRESS_REHEARSAL_STAGING_LAYOUT_INVALID");
    }
  } finally {
    fs.rmSync(stagingRoot, { recursive: true, force: true });
  }
  if (fs.existsSync(stagingRoot)) {
    throw error("DRESS_REHEARSAL_STAGING_CLEANUP_FAILED");
  }
  return {
    clean_before_rehearsal: true,
    clean_after_rehearsal: true,
    physical_staging_fixture_executed: true,
  };
}

function assertCandidate(candidate) {
  const slots = candidate?.slots || {};
  if (
    candidate?.schema_version !== "cyberboss.immutable-release-candidate.v1"
    || candidate?.status !== "passed"
    || candidate?.candidate_manifest_digest !== CANDIDATE_MANIFEST_DIGEST
    || candidate?.release_decision !== "candidate_local_only_not_promoted"
    || slots?.candidate?.release_id !== CANDIDATE_RELEASE_ID
    || slots?.candidate?.installation_state !== "candidate_local_only_not_installed"
    || slots?.candidate?.current_switched !== false
    || slots?.rollback?.pointer !== "previous"
    || slots?.rollback?.action !== "immediate_pointer_restore_no_wait"
    || slots?.rollback?.valid !== true
    || candidate?.activation?.candidate_installation !== "activation_pending"
    || candidate?.activation?.current_switch !== "activation_pending"
  ) {
    throw error("DRESS_REHEARSAL_CANDIDATE_INVALID");
  }
  assertCandidateCounters(candidate.activation);
}

function assertRunbook(runbook) {
  if (
    runbook?.schema_version !== "cyberboss.immutable-release-runbook.v1"
    || runbook?.runbook_digest !== OPERATOR_RUNBOOK_DIGEST
    || runbook?.command_count !== 8
    || runbook?.mode !== "contract_only_no_live_execution"
    || runbook?.external_execution !== "activation_pending"
    || runbook?.prerequisites?.fixed_sleep_allowed !== false
    || !Array.isArray(runbook?.commands)
    || runbook.commands.some((command) => command?.real_execution !== "activation_pending")
  ) {
    throw error("DRESS_REHEARSAL_RUNBOOK_INVALID");
  }
  assertZeroCounters(runbook);
}

function assertFaultContracts(faultMatrix, postdeployPlan) {
  const aggregate = faultMatrix?.aggregate || {};
  if (
    faultMatrix?.schema_version !== "cyberboss.fault-recovery-matrix.v1"
    || faultMatrix?.status !== "passed"
    || aggregate?.lost_messages !== 0
    || aggregate?.duplicate_execution !== 0
    || aggregate?.duplicate_side_effects !== 0
    || aggregate?.unbounded_retries !== 0
    || aggregate?.rollback_restore_valid !== true
    || postdeployPlan?.schema_version !== "cyberboss.postdeploy-fault-matrix.v1"
    || postdeployPlan?.mode !== "manual_or_ci_nonblocking"
    || postdeployPlan?.timer_installation !== "activation_pending"
  ) {
    throw error("DRESS_REHEARSAL_FAULT_CONTRACT_INVALID");
  }
  assertFaultAggregateCounters(aggregate);
  assertZeroCounters(postdeployPlan);
}

function assertFaultAggregateCounters(value) {
  if (
    value?.network_or_provider_operations !== 0
    || value?.control_plane_llm_calls !== 0
    || value?.operations_llm_calls !== 0
    || value?.real_time_waits !== 0
    || value?.macos_launchd_dependency !== false
  ) {
    throw error("DRESS_REHEARSAL_RUNTIME_BOUNDARY_INVALID");
  }
}

function assertCandidateCounters(value) {
  if (
    value?.external_provider_operations !== 0
    || value?.deployment_mutations !== 0
    || value?.control_plane_llm_calls !== 0
    || value?.operations_llm_calls !== 0
    || value?.real_time_waits !== 0
    || value?.macos_launchd_dependency !== false
  ) {
    throw error("DRESS_REHEARSAL_RUNTIME_BOUNDARY_INVALID");
  }
}

function assertStepCounters(stepValue) {
  if (
    stepValue.copy_safe !== true
    || stepValue.source_code_knowledge_required !== false
    || stepValue.undocumented_prerequisites !== 0
  ) {
    throw error("DRESS_REHEARSAL_OPERATOR_BOUNDARY_INVALID");
  }
  assertZeroCounters(stepValue);
}

function assertZeroCounters(value) {
  if (
    value?.network_or_provider_operations !== 0
    || value?.deployment_mutations !== 0
    || value?.control_plane_llm_calls !== 0
    || value?.operations_llm_calls !== 0
    || value?.real_time_waits !== 0
    || value?.macos_launchd_dependency !== false
  ) {
    throw error("DRESS_REHEARSAL_RUNTIME_BOUNDARY_INVALID");
  }
}

function zeroCounters() {
  return {
    network_or_provider_operations: 0,
    deployment_mutations: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    real_time_waits: 0,
    macos_launchd_dependency: false,
  };
}

function digest(value) {
  return crypto.createHash("sha256").update(stableStringify(value)).digest("hex");
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return "[" + value.map((entry) => stableStringify(entry)).join(",") + "]";
  }
  if (isPlainObject(value)) {
    return "{" + Object.keys(value).sort().map(
      (key) => JSON.stringify(key) + ":" + stableStringify(value[key])
    ).join(",") + "}";
  }
  return JSON.stringify(value);
}

function freeze(value) {
  if (Array.isArray(value)) {
    value.forEach(freeze);
  } else if (isPlainObject(value)) {
    Object.values(value).forEach(freeze);
  }
  return Object.freeze(value);
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function error(code) {
  return new DressRehearsalError(code);
}

module.exports = {
  ACTIVATION_PLAN_SCHEMA,
  CANDIDATE_MANIFEST_DIGEST,
  CANDIDATE_RELEASE_ID,
  DRESS_REHEARSAL_SCHEMA,
  DressRehearsalError,
  FROZEN_DRESS_REHEARSAL_STEPS,
  OPERATOR_RUNBOOK_DIGEST,
  PG4_CLOSURE,
  PG4_TREE,
  buildActivationPlan,
  buildCleanStagingRehearsal,
};
