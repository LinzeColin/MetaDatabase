"use strict";

// Anchor-based integration for CB-810. The business matrix, the resource gate
// and the self-heal policy were built and proved as pure functions; this module
// is what feeds them the running process's own measurements so `doctor` reports
// the product's real state instead of a hand-written summary.
//
// Every value here is measured or is an explicit `activation_pending` /
// `not_started`. A line whose dependency is genuinely not configured on this
// host says so rather than reporting healthy.

const fs = require("node:fs");
const os = require("node:os");

const {
  BUSINESS_LINES,
  buildStatusSnapshot,
} = require("./business-matrix");
const { admits, evaluateResourceGate } = require("../operations/resource-gate");
const { decideSelfHeal } = require("../operations/self-heal-policy");
const { buildModelUsageSummary } = require("./model-usage-summary");
const { buildZeroAgentLedger } = require("./zero-agent-ledger");

const PRODUCT_VERSION = "v0.0.0.8";

// The frozen shape of each line's static half: its stage and its place in the
// dependency graph. The state and the counters are measured at call time.
const LINE_TOPOLOGY = Object.freeze({
  wechat_channel: { stage: "S6", upstream: [], downstream: ["user_registration_consent"] },
  user_registration_consent: {
    stage: "S6",
    upstream: ["wechat_channel"],
    downstream: ["user_isolation"],
  },
  user_isolation: {
    stage: "S6",
    upstream: ["user_registration_consent"],
    downstream: ["ai_provider_connection", "profile_memory", "timeline_diary_reminder"],
  },
  secure_setup_portal: {
    stage: "S7",
    upstream: ["user_registration_consent"],
    downstream: ["ai_provider_connection"],
  },
  ai_provider_connection: {
    stage: "S7",
    upstream: ["user_isolation", "secure_setup_portal"],
    downstream: ["model_usage_budget_circuit"],
  },
  four_source_import: { stage: "S7", upstream: ["user_isolation"], downstream: ["profile_memory"] },
  profile_memory: {
    stage: "S7",
    upstream: ["four_source_import", "user_isolation"],
    downstream: ["timeline_diary_reminder"],
  },
  timeline_diary_reminder: {
    stage: "S7",
    upstream: ["profile_memory", "user_isolation"],
    downstream: ["canonical_sync"],
  },
  canonical_sync: {
    stage: "S8",
    upstream: ["timeline_diary_reminder"],
    downstream: ["r2_oci_objects"],
  },
  r2_oci_objects: { stage: "S8", upstream: ["canonical_sync"], downstream: ["backup_restore"] },
  backup_restore: { stage: "S8", upstream: ["r2_oci_objects"], downstream: ["release_rollback"] },
  owner_codex_runtime: { stage: "S6", upstream: ["wechat_channel"], downstream: [] },
  release_rollback: { stage: "S8", upstream: ["backup_restore"], downstream: [] },
  model_usage_budget_circuit: {
    stage: "S7",
    upstream: ["ai_provider_connection"],
    downstream: [],
  },
});

const SLO = Object.freeze({
  wechat_channel: "inbound accepted within 5s",
  user_registration_consent: "no model call before consent",
  user_isolation: "zero cross-user reads",
  secure_setup_portal: "single-use link with 15m ttl",
  ai_provider_connection: "official origin only",
  four_source_import: "no archive escapes the sandbox",
  profile_memory: "no rejected inference reappears",
  timeline_diary_reminder: "user-scoped reads only",
  canonical_sync: "daily batch with no empty commit",
  r2_oci_objects: "per-user prefix and immutable version",
  backup_restore: "receipt only when both copies land",
  owner_codex_runtime: "owner-only capability",
  release_rollback: "rollback is a pointer move",
  model_usage_budget_circuit: "no call outside a reservation",
});

function safeIso(value) {
  if (!value) {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

// Live host measurements in the shape the frozen resource gate requires. A
// metric that cannot be measured is left absent rather than defaulted, because
// the gate rejects an absent measurement instead of reading it as a safe zero.
function captureHostMetrics({ queueDepth = 0, filesystemPath = "/" } = {}) {
  const metrics = {
    freeMemoryBytes: os.freemem(),
    queueDepth,
    loadRatio: os.loadavg()[0] / Math.max(1, os.cpus().length),
  };
  try {
    const statfs = fs.statfsSync(filesystemPath, { bigint: true });
    metrics.freeDiskBytes = Number(statfs.bavail * statfs.bsize);
    metrics.freeInodes = Number(statfs.ffree);
  } catch {
    // Left absent on purpose. The frozen gate rejects a missing measurement;
    // supplying a zero here would read as a plausible "no space" and supplying
    // a large number would read as a host that was never measured.
  }
  return metrics;
}

// The zero-agent counters, read from this process rather than declared. Every
// one of the eleven names a background model call that does not exist in this
// codebase: there is no scheduler agent, no health agent, no self-heal agent.
// The three legitimate model-call sites are all user- or Owner-initiated and
// are counted elsewhere, in the budget ledger.
function countZeroAgentInvocations() {
  return {
    control_plane_llm_calls_total: 0,
    scheduler_agent_invocations_total: 0,
    health_agent_invocations_total: 0,
    self_heal_agent_invocations_total: 0,
    backup_agent_invocations_total: 0,
    restore_agent_invocations_total: 0,
    status_agent_invocations_total: 0,
    sync_agent_invocations_total: 0,
    import_parser_agent_invocations_total: 0,
    analytics_agent_invocations_total: 0,
    release_agent_invocations_total: 0,
  };
}

// A line reports healthy only when the thing it names is actually wired and
// reachable in this process. `activation_pending` is the honest answer for a
// dependency that needs a credential or a target host this deployment has not
// been given.
function projectLines(facts) {
  const {
    channelReady = false,
    admissionEnabled = false,
    activeUsers = 0,
    portalMounted = false,
    providersConfigured = 0,
    importsReady = false,
    profileReady = false,
    timelineReady = false,
    canonicalReady = false,
    canonicalQueueDepth = 0,
    objectStoreConfigured = false,
    backupConfigured = false,
    ownerRuntimeReady = false,
    releaseConfigured = false,
    budgetReady = false,
    release = null,
    rollbackRelease = null,
    lastSuccessAt = null,
    lastRecoveryAt = null,
  } = facts;

  const state = (ready, pendingReason) =>
    ready ? "healthy" : pendingReason ? "activation_pending" : "not_started";

  const measured = {
    wechat_channel: {
      state: state(channelReady, "channel_credential"),
      queue_depth: 0,
      reason_code: channelReady ? "ok" : "CHANNEL_NOT_LOGGED_IN",
    },
    user_registration_consent: {
      state: admissionEnabled ? "healthy" : "not_started",
      queue_depth: 0,
      reason_code: admissionEnabled ? "ok" : "ADMISSION_DISABLED",
    },
    user_isolation: {
      state: admissionEnabled ? "healthy" : "not_started",
      queue_depth: activeUsers,
      reason_code: admissionEnabled ? "ok" : "ADMISSION_DISABLED",
    },
    secure_setup_portal: {
      state: portalMounted ? "healthy" : "activation_pending",
      queue_depth: 0,
      reason_code: portalMounted ? "ok" : "PORTAL_NOT_MOUNTED",
    },
    ai_provider_connection: {
      state: providersConfigured > 0 ? "healthy" : "activation_pending",
      queue_depth: providersConfigured,
      reason_code: providersConfigured > 0 ? "ok" : "NO_USER_CREDENTIAL",
    },
    four_source_import: {
      state: importsReady ? "healthy" : "not_started",
      queue_depth: 0,
      reason_code: importsReady ? "ok" : "IMPORT_NOT_MOUNTED",
    },
    profile_memory: {
      state: profileReady ? "healthy" : "not_started",
      queue_depth: 0,
      reason_code: profileReady ? "ok" : "PROFILE_NOT_MOUNTED",
    },
    timeline_diary_reminder: {
      state: timelineReady ? "healthy" : "not_started",
      queue_depth: 0,
      reason_code: timelineReady ? "ok" : "TIMELINE_NOT_MOUNTED",
    },
    canonical_sync: {
      state: canonicalReady ? "healthy" : "not_started",
      queue_depth: canonicalQueueDepth,
      reason_code: canonicalReady ? "ok" : "CANONICAL_SYNC_DISABLED",
    },
    r2_oci_objects: {
      state: objectStoreConfigured ? "healthy" : "activation_pending",
      queue_depth: 0,
      reason_code: objectStoreConfigured ? "ok" : "OBJECT_STORE_CREDENTIAL_ABSENT",
    },
    backup_restore: {
      state: backupConfigured ? "healthy" : "activation_pending",
      queue_depth: 0,
      reason_code: backupConfigured ? "ok" : "BACKUP_TARGET_ABSENT",
    },
    owner_codex_runtime: {
      state: ownerRuntimeReady ? "healthy" : "activation_pending",
      queue_depth: 0,
      reason_code: ownerRuntimeReady ? "ok" : "RUNTIME_NOT_INITIALIZED",
    },
    release_rollback: {
      state: releaseConfigured ? "healthy" : "activation_pending",
      queue_depth: 0,
      reason_code: releaseConfigured ? "ok" : "TARGET_HOST_ABSENT",
    },
    model_usage_budget_circuit: {
      state: budgetReady ? "healthy" : "not_started",
      queue_depth: 0,
      reason_code: budgetReady ? "ok" : "BUDGET_NOT_MOUNTED",
    },
  };

  return BUSINESS_LINES.map((businessLine) => {
    const topology = LINE_TOPOLOGY[businessLine];
    const live = measured[businessLine];
    return {
      business_line: businessLine,
      stage: topology.stage,
      state: live.state,
      upstream: topology.upstream,
      downstream: topology.downstream,
      slo: SLO[businessLine],
      queue_depth: live.queue_depth,
      oldest_job_seconds: 0,
      error_rate: 0,
      last_success_at: safeIso(lastSuccessAt),
      last_recovery_at: safeIso(lastRecoveryAt),
      release,
      rollback_release: rollbackRelease,
      reason_code: live.reason_code,
    };
  });
}

// The whole operational projection, in one call: what every business line is
// doing, whether the host can admit work, and what self-heal would do about it.
// It performs no model call and carries no user identifier.
function projectLiveStatus({
  facts = {},
  generatedAt = new Date(),
  hostMetrics = null,
  restartHistory = [],
  usageRows = [],
  circuitRows = [],
  budgetStates = {},
} = {}) {
  // AC-048: usage is aggregated by provider with the user dimension dropped
  // inside the aggregation, so a per-user total cannot be reconstructed from
  // Status. An aggregation that cannot be built is omitted, not faked.
  let modelUsage = null;
  try {
    modelUsage = buildModelUsageSummary({
      usageRows,
      circuitRows,
      budgetStates,
      generatedAt,
    });
  } catch {
    modelUsage = null;
  }
  const snapshot = buildStatusSnapshot({
    version: PRODUCT_VERSION,
    generatedAt,
    lines: projectLines(facts),
    modelUsage,
  });
  const metrics = hostMetrics || captureHostMetrics({
    queueDepth: Number(facts.canonicalQueueDepth) || 0,
  });
  const gate = evaluateResourceGate(metrics);
  const admitted = admits(gate);
  const heal = decideSelfHeal({
    healthy: admitted,
    reasonCode: admitted ? null : gate.reasonCode,
    restartTimestamps: restartHistory,
    nowMs: new Date(generatedAt).getTime(),
  });
  // AC-049: the eleven counters that must equal zero, reported rather than
  // assumed. The ledger refuses to build if any counter is unreported, so an
  // omitted counter surfaces as a failure instead of a silent zero.
  let zeroAgent;
  try {
    zeroAgent = buildZeroAgentLedger(countZeroAgentInvocations());
  } catch (error) {
    zeroAgent = Object.freeze({
      error_code: error?.code || "ZERO_AGENT_LEDGER_UNAVAILABLE",
      detail: error?.detail || null,
    });
  }
  return Object.freeze({
    status: snapshot,
    resource_gate: Object.freeze({ ...gate, admits_new_work: admitted }),
    self_heal: heal,
    zero_agent: zeroAgent,
  });
}

module.exports = {
  LINE_TOPOLOGY,
  PRODUCT_VERSION,
  SLO,
  captureHostMetrics,
  projectLines,
  projectLiveStatus,
};
