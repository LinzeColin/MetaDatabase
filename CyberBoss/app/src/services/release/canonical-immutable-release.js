"use strict";

const crypto = require("node:crypto");

const IMMUTABLE_RELEASE_SCHEMA = "cyberboss.immutable-release-candidate.v1";
const OPERATOR_RUNBOOK_SCHEMA = "cyberboss.immutable-release-runbook.v1";
const PRODUCT_VERSION = "v0.0.0.5";
const TASKPACK_VERSION = "v0.0.0.7";
const CB430_CLOSURE = "045682e330f20ce4a5271f1a444c17bf1e2bf42c";
const CB430_TREE = "e789acb494926742aa61c61dbac721807aae9f6c";
const CB420_CLOSURE = "9f70eb6629d84e675d8df7183ae072b7e9bff7d7";
const CB410_CLOSURE = "ea82f02b175e864d754ab5bdfaccd0e84a89e6d4";
const APP_LOCKFILE_SHA256 = "0932f1d169965da5453e0a5803457988840200b2489e914e3ace5238f714f555";
const SOURCE_LOCK_SHA256 = "796dd31d9d4e8b44f178b9243b28e852017437c8983e45a1f731788173086fbf";

class ImmutableReleaseError extends Error {
  constructor(code) {
    super(code);
    this.name = "ImmutableReleaseError";
    this.code = code;
  }
}

const FROZEN_FEATURE_FLAGS = freeze({
  enabled: [
    "CB_DURABLE_INBOX",
    "CB_DURABLE_OUTBOX",
    "CB_PRIVATE_DB_CANONICAL_SYNC",
    "CB_TIMELINE_WEB",
    "CB_STATUS_EXPORTER",
    "CB_R2_SNAPSHOT",
    "CB_JOB_SCHEDULER",
  ],
  disabled: [
    "CB_CLAUDE_RUNTIME",
    "CB_CLAUDE_EVAL_PASSED",
    "CB_FILE_ATTACHMENTS",
    "CB_STORE_FULL_CONTENT",
    "CB_AUTONOMOUS_MUTATION",
  ],
});

const FROZEN_CANARY_RECEIPTS = freeze([
  receipt("read_only_status", "read_only", "passed", "status_snapshot_redacted"),
  receipt("read_only_timeline", "read_only", "passed", "timeline_projection_redacted"),
  receipt("read_only_release_manifest", "read_only", "passed", "manifest_hash_only"),
  receipt("read_only_access_boundary", "read_only", "passed", "access_boundary_only"),
  receipt("read_only_backup_inventory", "read_only", "passed", "backup_metadata_only"),
  receipt("denied_untrusted_origin", "rejected", "passed", "rejected_no_side_effect"),
  receipt("cancelled_mutation", "cancelled", "passed", "cancelled_no_side_effect"),
  receipt("reversible_mutation", "reversible_mutation", "passed", "staged_then_rolled_back", {
    local_staged_mutation_count: 1,
    local_rollback_count: 1,
  }),
]);

const OPERATOR_COMMAND_CONTRACT = freeze([
  command("inspect_candidate", "read_only", false),
  command("verify_release_manifest", "read_only", false),
  command("verify_feature_flags", "read_only", false),
  command("verify_additive_migration", "local_staging_only", false),
  command("prepare_current_switch", "activation_authority_required", true),
  command("execute_request_count_canary", "activation_authority_required", true),
  command("rollback_to_previous", "activation_authority_required", true),
  command("discard_unaccepted_candidate", "local_cleanup_only", false),
]);

function receipt(id, kind, status, effect, extra = {}) {
  return { id, kind, status, effect, ...extra, ...zeroCounters() };
}

function command(id, mode, authorityRequired) {
  return { id, mode, authority_required: authorityRequired, real_execution: "activation_pending" };
}

function buildImmutableReleaseCandidate({
  canaryReceipts = FROZEN_CANARY_RECEIPTS,
  featureFlags = FROZEN_FEATURE_FLAGS,
} = {}) {
  assertFeatureFlags(featureFlags);
  const slotPlan = buildSlotPlan(featureFlags);
  const canary = evaluateRequestCountCanary(canaryReceipts);
  const report = {
    schema_version: IMMUTABLE_RELEASE_SCHEMA,
    product_version: PRODUCT_VERSION,
    taskpack_version: TASKPACK_VERSION,
    evaluation_mode: "local_deterministic_manifest_and_request_predicates",
    source: {
      source_commit: CB430_CLOSURE,
      source_tree: CB430_TREE,
      app_lockfile_sha256: APP_LOCKFILE_SHA256,
      source_lock_sha256: SOURCE_LOCK_SHA256,
      local_archive_only: true,
      remote_publication: "none",
      git_tag_created: false,
      pull_request_created: false,
    },
    slots: slotPlan,
    feature_flags: featureFlags,
    migration: {
      mode: "additive_backward_compatible_fixture",
      prior_release_read: "local_fixture_verified",
      destructive_migration: false,
      staging_execution: "local_fixture_only",
    },
    canary,
    operator_contract: buildOperatorRunbook(),
    activation: {
      candidate_installation: "activation_pending",
      current_switch: "activation_pending",
      live_request_count_canary: "activation_pending",
      external_provider_operations: 0,
      deployment_mutations: 0,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      macos_launchd_dependency: false,
      real_time_waits: 0,
    },
  };
  report.candidate_manifest_digest = digest(report);
  report.status = canary.status === "passed" ? "passed" : "failed";
  report.release_decision = canary.status === "passed"
    ? "candidate_local_only_not_promoted"
    : "discard_candidate_keep_current";
  return freeze(report);
}

function buildSlotPlan(featureFlags) {
  const candidateIdentity = digest({
    product_version: PRODUCT_VERSION,
    source_commit: CB430_CLOSURE,
    source_tree: CB430_TREE,
    app_lockfile_sha256: APP_LOCKFILE_SHA256,
    feature_flags: featureFlags,
  });
  const slots = {
    layout_authority: "existing_immutable_release_layout",
    candidate: {
      release_id: candidateIdentity,
      source_commit: CB430_CLOSURE,
      immutable: true,
      installation_state: "candidate_local_only_not_installed",
      current_switched: false,
      service_enabled: false,
    },
    current: {
      release_id: CB420_CLOSURE,
      immutable: true,
      state: "local_fixture_current",
    },
    previous: {
      release_id: CB410_CLOSURE,
      immutable: true,
      state: "local_fixture_previous",
    },
    rollback: {
      pointer: "previous",
      target_release_id: CB410_CLOSURE,
      trigger: "p0_or_p1",
      action: "immediate_pointer_restore_no_wait",
      current_unchanged_until_authorized_switch: true,
      valid: true,
    },
  };
  assertSlotPlan(slots);
  return freeze(slots);
}

function buildOperatorRunbook() {
  const runbook = {
    schema_version: OPERATOR_RUNBOOK_SCHEMA,
    product_version: PRODUCT_VERSION,
    taskpack_version: TASKPACK_VERSION,
    mode: "contract_only_no_live_execution",
    command_count: OPERATOR_COMMAND_CONTRACT.length,
    commands: OPERATOR_COMMAND_CONTRACT,
    prerequisites: {
      exact_candidate_manifest: true,
      exact_current_and_previous_slots: true,
      external_authority_for_live_steps: true,
      fixed_sleep_allowed: false,
    },
    external_execution: "activation_pending",
    real_time_waits: 0,
    network_or_provider_operations: 0,
    deployment_mutations: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    macos_launchd_dependency: false,
  };
  runbook.runbook_digest = digest(runbook);
  return freeze(runbook);
}

function evaluateRequestCountCanary(receipts = FROZEN_CANARY_RECEIPTS) {
  if (!Array.isArray(receipts) || receipts.length !== FROZEN_CANARY_RECEIPTS.length) {
    throw error("RELEASE_CANARY_RECEIPT_SET_INVALID");
  }
  const known = new Set();
  const results = [];
  let p0Failures = 0;
  for (let index = 0; index < FROZEN_CANARY_RECEIPTS.length; index += 1) {
    const expected = FROZEN_CANARY_RECEIPTS[index];
    const receiptValue = receipts[index];
    if (!isPlainObject(receiptValue) || receiptValue.id !== expected.id || known.has(receiptValue.id)) {
      throw error("RELEASE_CANARY_RECEIPT_SET_INVALID");
    }
    known.add(receiptValue.id);
    assertReceiptCounters(receiptValue);
    const status = receiptValue.status;
    if (status !== "passed" && status !== "p0_failed") {
      throw error("RELEASE_CANARY_RECEIPT_INVALID");
    }
    if (status === "passed" && stableStringify(receiptValue) !== stableStringify(expected)) {
      throw error("RELEASE_CANARY_RECEIPT_INVALID");
    }
    if (status === "p0_failed") {
      p0Failures += 1;
    }
    results.push({ id: expected.id, kind: expected.kind, status });
  }
  const status = p0Failures === 0 ? "passed" : "failed";
  return freeze({
    mode: "fixed_request_count_local_fixture",
    request_count: results.length,
    read_only_request_count: 5,
    rejected_request_count: 1,
    cancelled_request_count: 1,
    reversible_mutation_request_count: 1,
    p0_failures: p0Failures,
    status,
    promotion: status === "passed" ? "eligible_after_external_authority" : "blocked",
    rollback: status === "passed" ? "not_required" : "immediate_pointer_restore_no_wait",
    current_unchanged: true,
    results,
    real_time_waits: 0,
    network_or_provider_operations: 0,
    deployment_mutations: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    macos_launchd_dependency: false,
  });
}

function assertFeatureFlags(featureFlags) {
  if (!isPlainObject(featureFlags) || !Array.isArray(featureFlags.enabled) || !Array.isArray(featureFlags.disabled)) {
    throw error("RELEASE_FEATURE_FLAGS_INVALID");
  }
  if (stableStringify(featureFlags) !== stableStringify(FROZEN_FEATURE_FLAGS)) {
    throw error("RELEASE_FEATURE_FLAGS_OUT_OF_SCOPE");
  }
  const all = [...featureFlags.enabled, ...featureFlags.disabled];
  if (new Set(all).size !== all.length || !all.every((entry) => /^CB_[A-Z0-9_]+$/.test(entry))) {
    throw error("RELEASE_FEATURE_FLAGS_INVALID");
  }
  return true;
}

function assertSlotPlan(slots) {
  if (
    !isPlainObject(slots)
    || slots.layout_authority !== "existing_immutable_release_layout"
    || !isPlainObject(slots.candidate)
    || !isPlainObject(slots.current)
    || !isPlainObject(slots.previous)
    || !isPlainObject(slots.rollback)
    || !/^[0-9a-f]{64}$/.test(slots.candidate.release_id)
    || slots.current.release_id !== CB420_CLOSURE
    || slots.previous.release_id !== CB410_CLOSURE
    || slots.current.release_id === slots.previous.release_id
    || slots.candidate.release_id === slots.current.release_id
    || slots.candidate.current_switched !== false
    || slots.candidate.service_enabled !== false
    || slots.rollback.pointer !== "previous"
    || slots.rollback.target_release_id !== slots.previous.release_id
    || slots.rollback.action !== "immediate_pointer_restore_no_wait"
    || slots.rollback.valid !== true
  ) {
    throw error("RELEASE_SLOT_PLAN_INVALID");
  }
  return true;
}

function assertReceiptCounters(receiptValue) {
  for (const [key, value] of Object.entries(zeroCounters())) {
    if (receiptValue[key] !== value) {
      throw error("RELEASE_CANARY_SIDE_EFFECT_FORBIDDEN");
    }
  }
}

function zeroCounters() {
  return {
    real_time_waits: 0,
    network_or_provider_operations: 0,
    deployment_mutations: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    macos_launchd_dependency: false,
  };
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
  return new ImmutableReleaseError(code);
}

module.exports = {
  APP_LOCKFILE_SHA256,
  CB410_CLOSURE,
  CB420_CLOSURE,
  CB430_CLOSURE,
  CB430_TREE,
  FROZEN_CANARY_RECEIPTS,
  FROZEN_FEATURE_FLAGS,
  IMMUTABLE_RELEASE_SCHEMA,
  OPERATOR_RUNBOOK_SCHEMA,
  ImmutableReleaseError,
  assertFeatureFlags,
  buildImmutableReleaseCandidate,
  buildOperatorRunbook,
  evaluateRequestCountCanary,
};
