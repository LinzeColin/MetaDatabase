"use strict";

const crypto = require("node:crypto");

const {
  ResourceReadinessError,
  ResourceReadinessGate,
} = require("../jobs/resource-readiness-gate");

const PRODUCT_VERSION = "v0.0.0.5";
const OPERATIONS_SCHEMA = "cyberboss.deterministic-operations.v1";
const RETENTION_SCHEMA = "cyberboss.retention.v2";
const RESTART_COOLDOWN_MS = 120_000;
const RESTART_WINDOW_MS = 600_000;
const RESTART_ATTEMPT_LIMIT = 3;
const ACTIONS = Object.freeze([
  "none",
  "refresh_status",
  "try_restart_single_service",
  "reclaim_explicit_cache",
  "pause_intake",
  "trigger_local_backup",
]);
const ACTION_TARGETS = Object.freeze({
  none: "none",
  refresh_status: "redacted_status_snapshot",
  try_restart_single_service: "cyberboss-cloud.service",
  reclaim_explicit_cache: "reconstructable_cache",
  pause_intake: "bounded_mutation_intake",
  trigger_local_backup: "local_runtime_snapshot",
});
const GUARD_STATES = Object.freeze(["recover", "warn", "protect"]);
const SENSITIVE_PATTERN = /-----BEGIN|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|\bwxid_[A-Za-z0-9_-]+\b|\bBearer\s+[A-Za-z0-9._~-]{12,}/i;

class CanonicalOperationsError extends Error {
  constructor(code) {
    super(code);
    this.name = "CanonicalOperationsError";
    this.code = code;
  }
}

function buildOperationsPlan({
  now,
  resourceSnapshot,
  retentionPolicy,
  retentionInventory,
  priorReceipt = null,
  operationClass = "bounded_mutation",
  backupEligible = false,
} = {}) {
  const generatedAt = normalizeTimestamp(now);
  if (!generatedAt) {
    throw new CanonicalOperationsError("OPERATIONS_NOW_INVALID");
  }
  if (typeof backupEligible !== "boolean") {
    throw new CanonicalOperationsError("OPERATIONS_BACKUP_ELIGIBILITY_INVALID");
  }
  const policy = validateRetentionPolicy(retentionPolicy);
  const inventory = validateRetentionInventory(retentionInventory, generatedAt);
  const receipt = normalizeReceipt(priorReceipt, generatedAt);
  const retention = buildRetentionReport({ policy, inventory, now: generatedAt });
  const readiness = evaluateReadiness({ generatedAt, resourceSnapshot, operationClass });
  const guardState = deriveGuardState(readiness.guardState, receipt.guard_state);
  const restartBudget = computeRestartBudget({ generatedAt, receipt });
  const action = chooseAction({
    readiness,
    guardState,
    restartBudget,
    retention,
    backupEligible,
  });
  const plan = {
    schema_version: OPERATIONS_SCHEMA,
    product_version: PRODUCT_VERSION,
    generated_at: generatedAt,
    resource: {
      state: readiness.state,
      reason: readiness.reason,
      guard_state: guardState,
      dispatch_allowed: readiness.dispatchAllowed,
      protect_reasons: [...readiness.protectReasons],
      warn_reasons: [...readiness.warnReasons],
    },
    action,
    restart_budget: restartBudget,
    retention,
    timer_contract: {
      installed: false,
      activation: "activation_pending",
      dispatch: "operator_or_future_systemd_only",
      macos_launchd_dependency: false,
      real_time_waits: 0,
    },
    counters: {
      action_invocations: 0,
      real_service_operations: 0,
      real_backup_operations: 0,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
    },
  };
  assertPlan(plan);
  return freezeJson(plan);
}

function executeSingleBoundedAction({ plan, actionExecutor = null } = {}) {
  assertPlan(plan);
  if (actionExecutor !== null && typeof actionExecutor !== "function") {
    throw new CanonicalOperationsError("OPERATIONS_EXECUTOR_INVALID");
  }
  const action = plan.action;
  if (action.kind === "none") {
    return freezeJson({
      status: "not_required",
      action: "none",
      invocations: 0,
      real_service_operations: 0,
      real_backup_operations: 0,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      receipt: buildReceipt({ plan, invoked: false, outcome: "not_required" }),
    });
  }
  if (actionExecutor === null) {
    return freezeJson({
      status: "activation_pending",
      action: action.kind,
      invocations: 0,
      real_service_operations: 0,
      real_backup_operations: 0,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      receipt: buildReceipt({ plan, invoked: false, outcome: "executor_missing" }),
    });
  }
  let outcome = "simulator_failed";
  try {
    const result = actionExecutor(Object.freeze({
      kind: action.kind,
      target: action.target,
      reason: action.reason,
      bounded: true,
      max_invocations: 1,
    }));
    if (result && result.status === "simulator_applied") {
      outcome = "simulator_applied";
    }
  } catch {
    outcome = "simulator_failed";
  }
  return freezeJson({
    status: outcome,
    action: action.kind,
    invocations: 1,
    real_service_operations: 0,
    real_backup_operations: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    receipt: buildReceipt({ plan, invoked: true, outcome }),
  });
}

function buildRetentionReport({ policy, inventory, now } = {}) {
  const normalizedPolicy = validateRetentionPolicy(policy);
  const generatedAt = normalizeTimestamp(now);
  if (!generatedAt) {
    throw new CanonicalOperationsError("RETENTION_NOW_INVALID");
  }
  const normalizedInventory = validateRetentionInventory(inventory, generatedAt);
  const nowMs = new Date(generatedAt).getTime();
  const verified = normalizedInventory.local_backups
    .filter((entry) => entry.status === "local_verified")
    .sort(compareNewestFirst);
  const failed = normalizedInventory.local_backups
    .filter((entry) => entry.status === "failed")
    .sort(compareNewestFirst);
  const backupPruneCandidateIds = verified
    .slice(normalizedPolicy.local_verified_backups)
    .map((entry) => entry.id);
  const expiredLogIds = expiredIds(
    normalizedInventory.runtime_logs,
    nowMs,
    normalizedPolicy.runtime_logs_days,
  );
  const expiredDiagnosticIds = expiredIds(
    normalizedInventory.diagnostic_summaries,
    nowMs,
    normalizedPolicy.diagnostic_summaries_days,
  );
  const cacheReclaimBytes = Math.max(
    0,
    normalizedInventory.build_cache_bytes - normalizedPolicy.build_cache_max_bytes,
  );
  const reviewRequired = backupPruneCandidateIds.length > 0
    || expiredLogIds.length > 0
    || expiredDiagnosticIds.length > 0
    || failed.length > 0;
  const state = cacheReclaimBytes > 0
    ? "reclaim_required"
    : reviewRequired
      ? "review_required"
      : "within_cap";
  return freezeJson({
    schema_version: RETENTION_SCHEMA,
    state,
    local_verified_backups: verified.length,
    local_verified_backup_limit: normalizedPolicy.local_verified_backups,
    backup_prune_candidate_ids: backupPruneCandidateIds,
    isolate_backup_ids: failed.map((entry) => entry.id),
    expired_runtime_log_ids: expiredLogIds,
    expired_diagnostic_summary_ids: expiredDiagnosticIds,
    cache_reclaim_bytes: cacheReclaimBytes,
    spool_entries_protected: normalizedInventory.spool_entries,
    immutable_release_slots_protected: [...normalizedPolicy.immutable_release_slots],
    raw_private_messages_in_github: false,
    auth_cache_in_standard_backup: false,
    automatic_backup_or_log_delete: false,
  });
}

function validateRetentionPolicy(policy) {
  assertPlainObject(policy, "RETENTION_POLICY_INVALID");
  assertExactKeys(policy, new Set([
    "schema_version",
    "runtime_logs_days",
    "diagnostic_summaries_days",
    "local_verified_backups",
    "immutable_release_slots",
    "build_cache_max_bytes",
    "raw_private_messages_in_github",
    "auth_cache_in_standard_backup",
    "no_empty_canonical_commit",
  ]), "RETENTION_POLICY_INVALID");
  if (
    policy.schema_version !== RETENTION_SCHEMA
    || policy.runtime_logs_days !== 7
    || policy.diagnostic_summaries_days !== 30
    || policy.local_verified_backups !== 2
    || policy.build_cache_max_bytes !== 536870912
    || policy.raw_private_messages_in_github !== false
    || policy.auth_cache_in_standard_backup !== false
    || policy.no_empty_canonical_commit !== true
    || !sameStrings(policy.immutable_release_slots, ["current", "previous"])
  ) {
    throw new CanonicalOperationsError("RETENTION_POLICY_INVALID");
  }
  return freezeJson(policy);
}

function validateRetentionInventory(inventory, now) {
  assertPlainObject(inventory, "RETENTION_INVENTORY_INVALID");
  assertExactKeys(inventory, new Set([
    "local_backups",
    "runtime_logs",
    "diagnostic_summaries",
    "build_cache_bytes",
    "spool_entries",
  ]), "RETENTION_INVENTORY_INVALID");
  if (
    !Number.isSafeInteger(inventory.build_cache_bytes)
    || inventory.build_cache_bytes < 0
    || !Number.isSafeInteger(inventory.spool_entries)
    || inventory.spool_entries < 0
  ) {
    throw new CanonicalOperationsError("RETENTION_INVENTORY_INVALID");
  }
  const nowMs = new Date(now).getTime();
  const localBackups = normalizeInventoryEntries(
    inventory.local_backups,
    nowMs,
    new Set(["local_verified", "activation_pending", "failed"]),
  );
  const runtimeLogs = normalizeInventoryEntries(inventory.runtime_logs, nowMs, null);
  const diagnostics = normalizeInventoryEntries(inventory.diagnostic_summaries, nowMs, null);
  assertNoSensitiveText(stableJson(inventory));
  return freezeJson({
    local_backups: localBackups,
    runtime_logs: runtimeLogs,
    diagnostic_summaries: diagnostics,
    build_cache_bytes: inventory.build_cache_bytes,
    spool_entries: inventory.spool_entries,
  });
}

function evaluateReadiness({ generatedAt, resourceSnapshot, operationClass }) {
  try {
    const gate = new ResourceReadinessGate({ now: () => new Date(generatedAt) });
    return gate.evaluate({ operationClass, snapshot: resourceSnapshot });
  } catch (error) {
    if (error instanceof ResourceReadinessError) {
      throw new CanonicalOperationsError(`OPERATIONS_RESOURCE_${error.code}`);
    }
    throw new CanonicalOperationsError("OPERATIONS_RESOURCE_INVALID");
  }
}

function deriveGuardState(rawGuardState, previousGuardState) {
  if (!GUARD_STATES.includes(rawGuardState)) {
    throw new CanonicalOperationsError("OPERATIONS_GUARD_INVALID");
  }
  if (rawGuardState === "recover") {
    return "recover";
  }
  if (rawGuardState === "warn" && previousGuardState === "protect") {
    return "protect";
  }
  return rawGuardState;
}

function computeRestartBudget({ generatedAt, receipt }) {
  const nowMs = new Date(generatedAt).getTime();
  const priorWindowMs = new Date(receipt.restart_window_started_at).getTime();
  const windowReset = nowMs - priorWindowMs >= RESTART_WINDOW_MS;
  const windowStartedAt = windowReset ? generatedAt : receipt.restart_window_started_at;
  const attempts = windowReset ? 0 : receipt.restart_attempts;
  const lastActionMs = receipt.last_action === "try_restart_single_service" && receipt.last_action_at
    ? new Date(receipt.last_action_at).getTime()
    : null;
  const cooldownActive = lastActionMs !== null && nowMs - lastActionMs < RESTART_COOLDOWN_MS;
  const attemptsExhausted = attempts >= RESTART_ATTEMPT_LIMIT;
  return freezeJson({
    window_started_at: windowStartedAt,
    attempts,
    limit: RESTART_ATTEMPT_LIMIT,
    cooldown_ms: RESTART_COOLDOWN_MS,
    window_ms: RESTART_WINDOW_MS,
    action_allowed: !cooldownActive && !attemptsExhausted,
    block_reason: cooldownActive
      ? "cooldown_active"
      : attemptsExhausted
        ? "restart_budget_exhausted"
        : null,
  });
}

function chooseAction({ readiness, guardState, restartBudget, retention, backupEligible }) {
  let kind = "none";
  let target = "none";
  let reason = readiness.reason;
  if (["runtime_unhealthy", "poll_stale"].includes(readiness.reason)) {
    if (restartBudget.action_allowed) {
      kind = "try_restart_single_service";
      target = "cyberboss-cloud.service";
    } else {
      reason = restartBudget.block_reason;
    }
  } else if (["disk_pressure", "inode_pressure"].includes(readiness.reason)) {
    kind = "reclaim_explicit_cache";
    target = "reconstructable_cache";
  } else if (["memory_pressure", "load_pressure", "queue_pressure"].includes(readiness.reason)) {
    kind = "pause_intake";
    target = "bounded_mutation_intake";
  } else if (["measurement_unavailable", "resource_warning", "queue_stuck"].includes(readiness.reason)) {
    kind = "refresh_status";
    target = "redacted_status_snapshot";
  } else if (guardState === "recover" && retention.cache_reclaim_bytes > 0) {
    kind = "reclaim_explicit_cache";
    target = "reconstructable_cache";
    reason = "cache_cap_exceeded";
  } else if (guardState === "recover" && backupEligible === true && retention.state === "within_cap") {
    kind = "trigger_local_backup";
    target = "local_runtime_snapshot";
    reason = "operator_backup_eligible";
  }
  return freezeJson({
    kind,
    target,
    reason,
    bounded: true,
    max_invocations: kind === "none" ? 0 : 1,
    requires_injected_executor: kind !== "none",
  });
}

function buildReceipt({ plan, invoked, outcome }) {
  const prior = plan.restart_budget;
  const action = plan.action.kind;
  const restartApplied = invoked && action === "try_restart_single_service";
  const lastAction = invoked ? action : "none";
  const lastActionAt = invoked ? plan.generated_at : null;
  const restartAttempts = restartApplied ? prior.attempts + 1 : prior.attempts;
  const payload = {
    schema_version: OPERATIONS_SCHEMA,
    generated_at: plan.generated_at,
    guard_state: plan.resource.guard_state,
    last_action: lastAction,
    last_action_at: lastActionAt,
    restart_window_started_at: prior.window_started_at,
    restart_attempts: restartAttempts,
    outcome,
  };
  return freezeJson({
    ...payload,
    receipt_id: `receipt_${sha256(stableJson(payload)).slice(0, 24)}`,
  });
}

function normalizeReceipt(value, generatedAt) {
  if (value === null || value === undefined) {
    return freezeJson({
      guard_state: "recover",
      last_action: "none",
      last_action_at: null,
      restart_window_started_at: generatedAt,
      restart_attempts: 0,
    });
  }
  assertPlainObject(value, "OPERATIONS_RECEIPT_INVALID");
  assertExactKeys(value, new Set([
    "schema_version",
    "generated_at",
    "guard_state",
    "last_action",
    "last_action_at",
    "restart_window_started_at",
    "restart_attempts",
    "outcome",
    "receipt_id",
  ]), "OPERATIONS_RECEIPT_INVALID");
  if (
    value.schema_version !== OPERATIONS_SCHEMA
    || !normalizeTimestamp(value.generated_at)
    || !GUARD_STATES.includes(value.guard_state)
    || !ACTIONS.includes(value.last_action)
    || (value.last_action_at !== null && !normalizeTimestamp(value.last_action_at))
    || !normalizeTimestamp(value.restart_window_started_at)
    || !Number.isSafeInteger(value.restart_attempts)
    || value.restart_attempts < 0
    || value.restart_attempts > RESTART_ATTEMPT_LIMIT
    || typeof value.outcome !== "string"
    || !/^receipt_[a-f0-9]{24}$/.test(value.receipt_id)
  ) {
    throw new CanonicalOperationsError("OPERATIONS_RECEIPT_INVALID");
  }
  const generatedMs = new Date(generatedAt).getTime();
  const windowMs = new Date(value.restart_window_started_at).getTime();
  const actionMs = value.last_action_at ? new Date(value.last_action_at).getTime() : null;
  if (windowMs > generatedMs || (actionMs !== null && actionMs > generatedMs)) {
    throw new CanonicalOperationsError("OPERATIONS_RECEIPT_INVALID");
  }
  assertNoSensitiveText(stableJson(value));
  return freezeJson({
    guard_state: value.guard_state,
    last_action: value.last_action,
    last_action_at: value.last_action_at,
    restart_window_started_at: value.restart_window_started_at,
    restart_attempts: value.restart_attempts,
  });
}

function assertPlan(plan) {
  assertPlainObject(plan, "OPERATIONS_PLAN_INVALID");
  assertExactKeys(plan, new Set([
    "schema_version",
    "product_version",
    "generated_at",
    "resource",
    "action",
    "restart_budget",
    "retention",
    "timer_contract",
    "counters",
  ]), "OPERATIONS_PLAN_INVALID");
  if (
    plan.schema_version !== OPERATIONS_SCHEMA
    || plan.product_version !== PRODUCT_VERSION
    || !normalizeTimestamp(plan.generated_at)
    || !isPlainObject(plan.resource)
    || !isPlainObject(plan.action)
    || !isPlainObject(plan.restart_budget)
    || !isPlainObject(plan.retention)
    || !isPlainObject(plan.timer_contract)
    || !isPlainObject(plan.counters)
  ) {
    throw new CanonicalOperationsError("OPERATIONS_PLAN_INVALID");
  }
  assertExactKeys(plan.resource, new Set([
    "state", "reason", "guard_state", "dispatch_allowed", "protect_reasons", "warn_reasons",
  ]), "OPERATIONS_PLAN_INVALID");
  assertExactKeys(plan.action, new Set([
    "kind", "target", "reason", "bounded", "max_invocations", "requires_injected_executor",
  ]), "OPERATIONS_PLAN_INVALID");
  assertExactKeys(plan.restart_budget, new Set([
    "window_started_at", "attempts", "limit", "cooldown_ms", "window_ms", "action_allowed", "block_reason",
  ]), "OPERATIONS_PLAN_INVALID");
  assertExactKeys(plan.timer_contract, new Set([
    "installed", "activation", "dispatch", "macos_launchd_dependency", "real_time_waits",
  ]), "OPERATIONS_PLAN_INVALID");
  assertExactKeys(plan.counters, new Set([
    "action_invocations", "real_service_operations", "real_backup_operations", "control_plane_llm_calls", "operations_llm_calls",
  ]), "OPERATIONS_PLAN_INVALID");
  if (
    !["ready", "degraded", "blocked"].includes(plan.resource.state)
    || !/^[a-z_]{2,80}$/.test(plan.resource.reason)
    || !GUARD_STATES.includes(plan.resource.guard_state)
    || typeof plan.resource.dispatch_allowed !== "boolean"
    || !stringArray(plan.resource.protect_reasons)
    || !stringArray(plan.resource.warn_reasons)
    || !ACTIONS.includes(plan.action.kind)
    || plan.action.target !== ACTION_TARGETS[plan.action.kind]
    || !/^[a-z_]{2,80}$/.test(plan.action.reason)
    || plan.action.bounded !== true
    || plan.action.max_invocations !== (plan.action.kind === "none" ? 0 : 1)
    || plan.action.requires_injected_executor !== (plan.action.kind !== "none")
    || !normalizeTimestamp(plan.restart_budget.window_started_at)
    || !Number.isSafeInteger(plan.restart_budget.attempts)
    || plan.restart_budget.attempts < 0
    || plan.restart_budget.attempts > RESTART_ATTEMPT_LIMIT
    || plan.restart_budget.limit !== RESTART_ATTEMPT_LIMIT
    || plan.restart_budget.cooldown_ms !== RESTART_COOLDOWN_MS
    || plan.restart_budget.window_ms !== RESTART_WINDOW_MS
    || typeof plan.restart_budget.action_allowed !== "boolean"
    || ![null, "cooldown_active", "restart_budget_exhausted"].includes(plan.restart_budget.block_reason)
    || plan.timer_contract.installed !== false
    || plan.timer_contract.activation !== "activation_pending"
    || plan.timer_contract.dispatch !== "operator_or_future_systemd_only"
    || plan.timer_contract.macos_launchd_dependency !== false
    || plan.timer_contract.real_time_waits !== 0
    || plan.counters.action_invocations !== 0
    || plan.counters.real_service_operations !== 0
    || plan.counters.real_backup_operations !== 0
    || plan.counters.control_plane_llm_calls !== 0
    || plan.counters.operations_llm_calls !== 0
  ) {
    throw new CanonicalOperationsError("OPERATIONS_PLAN_INVALID");
  }
  assertNoSensitiveText(stableJson(plan));
}

function normalizeInventoryEntries(entries, nowMs, allowedStatuses) {
  if (!Array.isArray(entries) || entries.length > 128) {
    throw new CanonicalOperationsError("RETENTION_INVENTORY_INVALID");
  }
  const result = entries.map((entry) => {
    assertPlainObject(entry, "RETENTION_INVENTORY_INVALID");
    const expected = allowedStatuses === null
      ? new Set(["id", "created_at", "bytes"])
      : new Set(["id", "created_at", "bytes", "status"]);
    assertExactKeys(entry, expected, "RETENTION_INVENTORY_INVALID");
    const id = typeof entry.id === "string" ? entry.id.trim() : "";
    const createdAt = normalizeTimestamp(entry.created_at);
    if (
      !/^[a-z][a-z0-9._-]{1,95}$/.test(id)
      || !createdAt
      || new Date(createdAt).getTime() > nowMs
      || !Number.isSafeInteger(entry.bytes)
      || entry.bytes < 0
      || (allowedStatuses !== null && !allowedStatuses.has(entry.status))
    ) {
      throw new CanonicalOperationsError("RETENTION_INVENTORY_INVALID");
    }
    return allowedStatuses === null
      ? { id, created_at: createdAt, bytes: entry.bytes }
      : { id, created_at: createdAt, bytes: entry.bytes, status: entry.status };
  });
  if (new Set(result.map((entry) => entry.id)).size !== result.length) {
    throw new CanonicalOperationsError("RETENTION_INVENTORY_INVALID");
  }
  return result.sort(compareNewestFirst);
}

function expiredIds(entries, nowMs, days) {
  const threshold = nowMs - days * 24 * 60 * 60 * 1000;
  return entries
    .filter((entry) => new Date(entry.created_at).getTime() < threshold)
    .map((entry) => entry.id);
}

function compareNewestFirst(left, right) {
  return new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
    || left.id.localeCompare(right.id);
}

function normalizeTimestamp(value) {
  const text = typeof value === "string" ? value.trim() : "";
  const parsed = new Date(text);
  return text && Number.isFinite(parsed.getTime()) && parsed.toISOString() === text ? text : "";
}

function assertNoSensitiveText(value) {
  if (SENSITIVE_PATTERN.test(value) || value.includes("/Users/") || value.includes("/var/")) {
    throw new CanonicalOperationsError("OPERATIONS_PRIVACY_VIOLATION");
  }
}

function assertPlainObject(value, code) {
  if (!isPlainObject(value)) {
    throw new CanonicalOperationsError(code);
  }
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assertExactKeys(value, expected, code) {
  const keys = Object.keys(value);
  if (keys.length !== expected.size || keys.some((key) => !expected.has(key))) {
    throw new CanonicalOperationsError(code);
  }
}

function sameStrings(value, expected) {
  return Array.isArray(value) && value.length === expected.length && value.every((item, index) => item === expected[index]);
}

function stringArray(value) {
  return Array.isArray(value) && value.every((item) => /^[a-z_]{2,80}$/.test(item));
}

function stableJson(value) {
  return JSON.stringify(sortJson(value));
}

function sortJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortJson);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortJson(value[key])]));
}

function freezeJson(value) {
  return Object.freeze(JSON.parse(JSON.stringify(value)));
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

module.exports = {
  ACTIONS,
  CanonicalOperationsError,
  OPERATIONS_SCHEMA,
  PRODUCT_VERSION,
  RETENTION_SCHEMA,
  RESTART_ATTEMPT_LIMIT,
  RESTART_COOLDOWN_MS,
  RESTART_WINDOW_MS,
  buildOperationsPlan,
  buildRetentionReport,
  executeSingleBoundedAction,
  validateRetentionInventory,
  validateRetentionPolicy,
};
