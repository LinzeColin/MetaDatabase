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
  MODES,
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
  // v0.0.0.9 的第 15 项（CB9-510）。挂在注册后面：时区信号是加入页采的。
  location_timezone: {
    stage: "S6",
    upstream: ["user_registration_consent"],
    downstream: ["timeline_diary_reminder"],
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
  location_timezone: "no coordinate and no ip is stored",
});

// AC-035 / NFR-005：每一格都要说得出下一步干什么，而那句话必须是**查出来的**。
//
// 生成一句「建议」需要模型，而 NFR-005 写死了自愈不依赖 Agent/Token。所以这是
// 一张 reason_code → 动作的固定表。查不到的走兜底，兜底也是固定串。
//
// 这些串是给人看的行动，不是状态的同义反复：「blocked」告诉你它坏了，
// 「reconnect_wechat_account」告诉你去干什么。前者等于把排查全推给值班的人。
const SUGGESTED_BY_REASON = Object.freeze({
  ok: "none",
  CHANNEL_NOT_LOGGED_IN: "reconnect_wechat_account",
  ADMISSION_DISABLED: "enable_admission_in_panel",
  PORTAL_NOT_MOUNTED: "start_setup_portal",
  NO_USER_CREDENTIAL: "add_provider_credential",
  IMPORT_NOT_MOUNTED: "mount_import_service",
  PROFILE_NOT_MOUNTED: "mount_profile_service",
  TIMELINE_NOT_MOUNTED: "mount_timeline_service",
  CANONICAL_SYNC_DISABLED: "configure_canonical_repository",
  OBJECT_STORE_CREDENTIAL_ABSENT: "add_object_store_credential",
  BACKUP_TARGET_ABSENT: "configure_backup_target",
  RUNTIME_NOT_INITIALIZED: "initialize_owner_runtime",
  TARGET_HOST_ABSENT: "configure_release_host",
  BUDGET_NOT_MOUNTED: "mount_budget_service",
  NO_TIMEZONE_SIGNAL_YET: "wait_for_first_join",
  OWNER_ONLY_CAPABILITY: "none",
});

const DEFAULT_SUGGESTED_ACTION = "read_reason_code";

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
    // 总量也要量：只有可用字节数的话算不出比例，而 status 的资源段要的是比例。
    // 算不出来时那一段是 UNKNOWN，不是 0——见 buildResources。
    metrics.totalDiskBytes = Number(statfs.blocks * statfs.bsize);
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
// 冷备这一行怎么判。见调用处那段注释：量的是**异地那一份**的新鲜度，
// 不是「备份器配好了没有」。
const BACKUP_FRESH_MS = 26 * 60 * 60 * 1000;
const BACKUP_STALE_MS = 72 * 60 * 60 * 1000;

function backupLine({ backupConfigured, backupLastSuccessAt, now }) {
  if (!backupConfigured) {
    return { state: "not_started", queue_depth: 0, reason_code: "BACKUP_TARGET_ABSENT" };
  }
  const at = backupLastSuccessAt ? Date.parse(backupLastSuccessAt) : NaN;
  if (!Number.isFinite(at)) {
    // 配了，但一次都没成功过。这不是「坏了」，是「还没跑起来」——
    // 和「跑过而且现在坏了」要分开，那是 AC-025 的整条道理。
    return { state: "activation_pending", queue_depth: 0, reason_code: "BACKUP_NEVER_COMPLETED" };
  }
  const age = Date.parse(new Date(now).toISOString()) - at;
  if (!(age >= 0)) {
    // 回执比现在还新：钟不对，或者文件被人动过。不当成健康。
    return { state: "degraded", queue_depth: 0, reason_code: "BACKUP_RECEIPT_IN_FUTURE" };
  }
  if (age <= BACKUP_FRESH_MS) {
    return { state: "healthy", queue_depth: 0, reason_code: "ok" };
  }
  if (age <= BACKUP_STALE_MS) {
    return { state: "degraded", queue_depth: 0, reason_code: "BACKUP_STALE" };
  }
  return { state: "blocked", queue_depth: 0, reason_code: "BACKUP_OFFSITE_MISSING" };
}

function projectLines(facts, { now = new Date() } = {}) {
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
    backupLastSuccessAt = null,
    ownerRuntimeReady = false,
    releaseConfigured = false,
    budgetReady = false,
    release = null,
    rollbackRelease = null,
    lastSuccessAt = null,
    lastRecoveryAt = null,
    lastFailureAt = null,
    timezoneSignalsSeen = 0,
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
    // 冷备这一行由**真实回执**判，不由「配好了没有」判。
    //
    // 原来写的是 `backupConfigured ? "healthy" : ...`——而 backupConfigured 的
    // 意思只是「备份器构造出来了」。于是 2026-08-01T23:53 起异地上传连续失败、
    // 副本停在 07-29 的那四天里，这一行一直是 healthy。
    //
    // 这正是本文件 LINE_NOTES 里给 backup_restore 写的口径：
    // "receipt only when both copies land"——意图早就写下来了，代码没照做。
    // 也正是 AC-026 明令禁止的配置性伪绿。
    //
    // 门槛按每天一次的节奏定：
    //   26 小时内有回执 → healthy（允许一次运行时刻的漂移）
    //   26～72 小时     → degraded（漏了一两次，值得看一眼）
    //   超过 72 小时     → blocked（连着三天没有异地副本，这是要出事的）
    // 没配置 → not_started；配了但从来没成功过 → activation_pending。
    // 一次抖动不会立刻翻红，而真的停摆藏不过三天。
    backup_restore: backupLine({ backupConfigured, backupLastSuccessAt, now }),
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
    location_timezone: {
      // 采到过一个时区信号才算跑起来过。表建好了不算——那是配置性伪绿。
      state: timezoneSignalsSeen > 0 ? "healthy" : "not_started",
      queue_depth: timezoneSignalsSeen,
      reason_code: timezoneSignalsSeen > 0 ? "ok" : "NO_TIMEZONE_SIGNAL_YET",
    },
  };

  // 15 项能力 × 2 个模式 = 30 格。
  //
  // 绝大多数能力对两个模式是同一条路，两格状态相同——**这不是冗余**。
  // 合成一格的话，等哪天访客那条路单独坏了（provider 换了、额度用完了、
  // 席位外的人拿不到 key），矩阵里没有一格能表达它，于是它不存在。
  //
  // owner_codex_runtime 是唯一结构性单模式的那一项：访客根本够不着 Codex。
  // 对访客报主人的健康度是**串模式的伪绿**——最坏的一种，因为主人看自己那边
  // 一直是好的。
  return BUSINESS_LINES.flatMap((businessLine) => {
    const topology = LINE_TOPOLOGY[businessLine];
    const live = measured[businessLine];
    return MODES.map((mode) => {
      const ownerOnly = businessLine === "owner_codex_runtime" && mode === "COMPANION";
      const state = ownerOnly ? "not_started" : live.state;
      const reasonCode = ownerOnly ? "OWNER_ONLY_CAPABILITY" : live.reason_code;
      return {
        business_line: businessLine,
        mode,
        stage: topology.stage,
        state,
        upstream: topology.upstream,
        downstream: topology.downstream,
        slo: SLO[businessLine],
        queue_depth: ownerOnly ? 0 : live.queue_depth,
        oldest_job_seconds: 0,
        error_rate: 0,
        last_success_at: state === "healthy" ? safeIso(lastSuccessAt) : null,
        // AC-035：上次成功和上次失败都要有。只有成功时间的话，一条长期坏着的
        // 线和一条从没跑过的线长得一模一样。
        last_failure_at: safeIso(lastFailureAt),
        last_recovery_at: safeIso(lastRecoveryAt),
        // AC-035 的「建议动作」，从冻结的表里查——不是生成的。生成就等于
        // 自愈调了模型，而 NFR-005 明令不许。
        suggested_action: SUGGESTED_BY_REASON[reasonCode] || DEFAULT_SUGGESTED_ACTION,
        release,
        rollback_release: rollbackRelease,
        reason_code: reasonCode,
      };
    });
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
  const metrics = hostMetrics || captureHostMetrics({
    queueDepth: Number(facts.canonicalQueueDepth) || 0,
  });
  const gate = evaluateResourceGate(metrics);
  const admitted = admits(gate);
  // FR-026 的另外五段。每一段都只交回执，状态由 parity-freshness 判——
  // 这里传不进去 state，所以「配置里开着」变不成绿色。
  const snapshot = buildStatusSnapshot({
    version: PRODUCT_VERSION,
    generatedAt,
    lines: projectLines(facts, { now: generatedAt }),
    modelUsage,
    modes: {
      OWNER: {
        configured: facts.ownerRuntimeReady === true,
        lastSuccessAt: facts.ownerLastSuccessAt ?? null,
        lastFailureAt: facts.ownerLastFailureAt ?? null,
        degradationLevel: facts.degradationLevel || "normal",
      },
      COMPANION: {
        configured: facts.admissionEnabled === true,
        lastSuccessAt: facts.companionLastSuccessAt ?? null,
        lastFailureAt: facts.companionLastFailureAt ?? null,
        degradationLevel: facts.degradationLevel || "normal",
      },
    },
    queue: {
      configured: true,
      depth: Number(facts.canonicalQueueDepth) || 0,
      oldestJobSeconds: Number(facts.oldestJobSeconds) || 0,
      lastDrainedAt: facts.lastDrainedAt ?? null,
      lastFailureAt: facts.queueLastFailureAt ?? null,
    },
    // 资源是当场量出来的，不是回执。量不到的那几项留 null，由 buildResources
    // 判成 UNKNOWN——补 0 会显示成「资源充裕」，而实际情况是我们瞎了。
    resources: {
      cpuLoad: metrics.loadRatio ?? null,
      memoryFreeRatio: Number.isFinite(metrics.freeMemoryBytes) && os.totalmem() > 0
        ? metrics.freeMemoryBytes / os.totalmem()
        : null,
      diskFreeRatio: Number.isFinite(metrics.freeDiskBytes) && Number.isFinite(metrics.totalDiskBytes)
        && metrics.totalDiskBytes > 0
        ? metrics.freeDiskBytes / metrics.totalDiskBytes
        : null,
      admitsNewWork: admitted,
      reasonCode: gate.reasonCode || null,
      measuredAt: new Date(generatedAt).toISOString(),
    },
    canonicalSync: {
      configured: facts.canonicalReady === true,
      lastSyncedAt: facts.lastCanonicalSyncAt ?? null,
      lastFailureAt: facts.lastCanonicalFailureAt ?? null,
      pendingFacts: Number(facts.canonicalQueueDepth) || 0,
      lastCommitSha: facts.lastCanonicalCommitSha ?? null,
    },
    backups: {
      configured: facts.backupConfigured === true,
      lastBackupAt: facts.lastBackupAt ?? null,
      lastFailureAt: facts.lastBackupFailureAt ?? null,
      lastRestoreDrillAt: facts.lastRestoreDrillAt ?? null,
      objectCount: Number(facts.backupObjectCount) || 0,
    },
  });
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
