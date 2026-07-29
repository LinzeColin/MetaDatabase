"use strict";

const fs = require("node:fs");
const os = require("node:os");

const MIB = 1024 * 1024;
const DEFAULT_POLL_STALE_MS = 90_000;
const DEFAULT_QUEUE_STUCK_MS = 5 * 60_000;
const DEFAULT_QUEUE_LIMIT = 20;

const REASON_ACTION = Object.freeze({
  ready: "dispatch_fifo_head",
  resource_warning: "monitor_and_serialize",
  measurement_unavailable: "capture_live_resource_profile",
  poll_stale: "restart_channel_adapter",
  runtime_unhealthy: "restart_runtime_process_family",
  memory_pressure: "hold_new_runtime_jobs_and_free_memory",
  disk_pressure: "pause_mutations_and_cleanup_reconstructable_data",
  inode_pressure: "pause_mutations_and_cleanup_reconstructable_data",
  // 负载高只是慢，不是坏。串行跑（本来就是串行）比不回强。
  load_pressure: "monitor_and_serialize",
  queue_pressure: "drain_existing_queue_and_protect_ingress",
  queue_stuck: "inspect_active_lease_and_runtime",
});

class ResourceReadinessError extends Error {
  constructor(code) {
    super(code);
    this.name = "ResourceReadinessError";
    this.code = code;
  }
}

function timestampMs(value) {
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function finiteInteger(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function decision({
  state,
  reason,
  dispatchAllowed,
  guardState,
  protectReasons = [],
  warnReasons = [],
  thresholds,
}) {
  return Object.freeze({
    state,
    reason,
    action: REASON_ACTION[reason],
    dispatchAllowed,
    guardState,
    protectReasons: Object.freeze([...protectReasons]),
    warnReasons: Object.freeze([...warnReasons]),
    thresholds: Object.freeze({ ...thresholds }),
  });
}

class ResourceReadinessGate {
  constructor({
    now = () => new Date(),
    pollStaleMs = DEFAULT_POLL_STALE_MS,
    queueStuckMs = DEFAULT_QUEUE_STUCK_MS,
    queueLimit = DEFAULT_QUEUE_LIMIT,
  } = {}) {
    for (const [name, value, minimum, maximum] of [
      ["POLL_STALE_MS", pollStaleMs, 1_000, 60 * 60_000],
      ["QUEUE_STUCK_MS", queueStuckMs, 1_000, 24 * 60 * 60_000],
      ["QUEUE_LIMIT", queueLimit, 1, 10_000],
    ]) {
      if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
        throw new ResourceReadinessError(`${name}_INVALID`);
      }
    }
    this.now = now;
    this.pollStaleMs = pollStaleMs;
    this.queueStuckMs = queueStuckMs;
    this.queueLimit = queueLimit;
  }

  evaluate({ operationClass, snapshot }) {
    if (!["read_only", "bounded_mutation"].includes(operationClass)) {
      throw new ResourceReadinessError("OPERATION_CLASS_INVALID");
    }
    const nowMs = timestampMs(this.now());
    const pollSuccessMs = timestampMs(snapshot?.poll?.lastSuccessAt);
    const oldestQueuedMs = snapshot?.queue?.oldestQueuedAt
      ? timestampMs(snapshot.queue.oldestQueuedAt)
      : null;
    const memory = snapshot?.memory || {};
    const storage = snapshot?.storage || {};
    const load = snapshot?.load || {};
    const queue = snapshot?.queue || {};
    const thresholds = {
      memoryProtectAvailableMb: 512,
      memoryRecoverAvailableMb: 768,
      memoryProtectUsedPercent: 92,
      memoryRecoverUsedPercent: 85,
      diskProtectUsedPercent: 90,
      diskRecoverUsedPercent: 80,
      inodeProtectUsedPercent: 90,
      inodeRecoverUsedPercent: 80,
      loadProtect: finiteInteger(load.cpuCount)
        ? Math.max(3.5, load.cpuCount * 1.5)
        : null,
      queueProtectDepth: this.queueLimit,
      queueRecoverDepth: Math.max(0, Math.floor(this.queueLimit * 0.8) - 1),
      pollStaleMs: this.pollStaleMs,
      queueStuckMs: this.queueStuckMs,
    };
    const measurementsValid = [
      finiteNumber(memory.totalMb),
      finiteNumber(memory.availableMb),
      finiteNumber(storage.usedPercent),
      finiteNumber(storage.inodeUsedPercent),
      finiteNumber(load.oneMinute),
      finiteInteger(load.cpuCount) && load.cpuCount >= 1,
      finiteInteger(queue.depth),
      nowMs !== null,
      pollSuccessMs !== null,
      oldestQueuedMs !== null || queue.depth === 0,
    ].every(Boolean)
      && memory.totalMb > 0
      && memory.availableMb <= memory.totalMb
      && storage.usedPercent <= 100
      && storage.inodeUsedPercent <= 100;
    if (!measurementsValid) {
      return decision({
        state: "blocked",
        reason: "measurement_unavailable",
        dispatchAllowed: false,
        guardState: "protect",
        protectReasons: ["measurement"],
        thresholds,
      });
    }

    if (snapshot?.runtime?.ready !== true) {
      return decision({
        state: "blocked",
        reason: "runtime_unhealthy",
        dispatchAllowed: false,
        guardState: "protect",
        protectReasons: ["runtime"],
        thresholds,
      });
    }
    if (nowMs - pollSuccessMs > this.pollStaleMs || pollSuccessMs > nowMs) {
      return decision({
        state: "blocked",
        reason: "poll_stale",
        dispatchAllowed: false,
        guardState: "protect",
        protectReasons: ["poll"],
        thresholds,
      });
    }

    const memoryUsedPercent =
      ((memory.totalMb - memory.availableMb) / memory.totalMb) * 100;
    const loadProtect = thresholds.loadProtect;
    const protectReasons = [];
    const warnReasons = [];
    if (memory.availableMb < 512 || memoryUsedPercent >= 92) {
      protectReasons.push("memory");
    } else if (memory.availableMb < 768 || memoryUsedPercent >= 85) {
      warnReasons.push("memory");
    }
    if (storage.usedPercent >= 90) {
      protectReasons.push("disk");
    } else if (storage.usedPercent >= 80) {
      warnReasons.push("disk");
    }
    if (storage.inodeUsedPercent >= 90) {
      protectReasons.push("inode");
    } else if (storage.inodeUsedPercent >= 80) {
      warnReasons.push("inode");
    }
    if (load.oneMinute > loadProtect) {
      protectReasons.push("load");
    } else if (load.oneMinute > loadProtect * 0.75) {
      warnReasons.push("load");
    }
    if (queue.depth >= this.queueLimit) {
      protectReasons.push("queue");
    } else if (queue.depth >= Math.floor(this.queueLimit * 0.8)) {
      warnReasons.push("queue");
    }

    if (
      queue.depth > 0
      && oldestQueuedMs !== null
      && nowMs - oldestQueuedMs >= this.queueStuckMs
      && snapshot?.queue?.activeRuntime !== true
    ) {
      return decision({
        state: "degraded",
        reason: "queue_stuck",
        dispatchAllowed: true,
        guardState: protectReasons.length ? "protect" : "warn",
        protectReasons,
        warnReasons,
        thresholds,
      });
    }
    if (protectReasons.includes("memory")) {
      return decision({
        state: "blocked",
        reason: "memory_pressure",
        dispatchAllowed: false,
        guardState: "protect",
        protectReasons,
        warnReasons,
        thresholds,
      });
    }
    // 负载高**不拦**回复。
    //
    // 这是「他没回话」和「过了五分钟才回」的真正原因。线上那条消息 07:11:11
    // 入队，07:14:21 才被 claim——中间三分十秒，闸门一直在说 load_pressure。
    // 这台机器只有 2 核，loadProtect = max(3.5, 2×1.5) = 3.5，而它常年挂着
    // codex runtime、cloudflared 和另外几个服务，一分钟负载翻过 3.5 太容易了。
    //
    // 拦住它换来了什么？什么都没有。#dispatchNextRuntime 开头就是
    // getActiveRuntimeJob()——**同一时刻本来就只可能有一个 runtime job 在跑**。
    // 不派发并不会少跑一个任务，只会让主人等着的那一条唯一的回复迟到，而且他
    // 在微信那头看不到任何解释，只会以为机器人坏了。
    //
    // 内存和磁盘不一样：那两样真的会把进程打死或者写坏数据，继续拦。负载只是
    // 「现在有点慢」，慢着回也比不回强。
    if (protectReasons.includes("load")) {
      return decision({
        state: "degraded",
        reason: "load_pressure",
        dispatchAllowed: true,
        guardState: "protect",
        protectReasons,
        warnReasons,
        thresholds,
      });
    }
    for (const [resource, reason] of [
      ["disk", "disk_pressure"],
      ["inode", "inode_pressure"],
    ]) {
      if (protectReasons.includes(resource)) {
        return decision({
          state: operationClass === "bounded_mutation" ? "blocked" : "degraded",
          reason,
          dispatchAllowed: operationClass === "read_only",
          guardState: "protect",
          protectReasons,
          warnReasons,
          thresholds,
        });
      }
    }
    if (protectReasons.includes("queue")) {
      return decision({
        state: "degraded",
        reason: "queue_pressure",
        dispatchAllowed: true,
        guardState: "protect",
        protectReasons,
        warnReasons,
        thresholds,
      });
    }
    if (warnReasons.length) {
      return decision({
        state: "degraded",
        reason: "resource_warning",
        dispatchAllowed: true,
        guardState: "warn",
        protectReasons,
        warnReasons,
        thresholds,
      });
    }
    return decision({
      state: "ready",
      reason: "ready",
      dispatchAllowed: true,
      guardState: "recover",
      thresholds,
    });
  }
}

function captureLiveResourceSnapshot({
  poll,
  runtime,
  queue,
  filesystemPath = "/",
} = {}) {
  let statfs;
  try {
    statfs = fs.statfsSync(filesystemPath, { bigint: true });
  } catch {
    throw new ResourceReadinessError("LIVE_STORAGE_MEASUREMENT_UNAVAILABLE");
  }
  const totalBytes = statfs.blocks * statfs.bsize;
  const availableBytes = statfs.bavail * statfs.bsize;
  const usedBytes = totalBytes - statfs.bfree * statfs.bsize;
  const files = statfs.files;
  const filesFree = statfs.ffree;
  if (totalBytes <= 0n || files <= 0n) {
    throw new ResourceReadinessError("LIVE_STORAGE_MEASUREMENT_INVALID");
  }
  const percent = (numerator, denominator) =>
    Number((numerator * 1000n) / denominator) / 10;
  return Object.freeze({
    source: "live",
    poll: Object.freeze({
      lastSuccessAt: poll?.lastSuccessAt || null,
      errorClass: poll?.errorClass || null,
    }),
    runtime: Object.freeze({
      ready: runtime?.ready === true,
      reason: runtime?.reason || (runtime?.ready === true ? "ready" : "unready"),
    }),
    memory: Object.freeze({
      totalMb: Math.floor(os.totalmem() / MIB),
      availableMb: Math.floor(os.freemem() / MIB),
    }),
    storage: Object.freeze({
      freeMb: Number(availableBytes / BigInt(MIB)),
      usedPercent: percent(usedBytes, totalBytes),
      inodeUsedPercent: percent(files - filesFree, files),
    }),
    load: Object.freeze({
      oneMinute: Number(os.loadavg()[0].toFixed(3)),
      cpuCount: Math.max(1, os.cpus().length),
    }),
    queue: Object.freeze({
      depth: Number(queue?.queuedTotal || 0),
      oldestQueuedAt: queue?.oldestQueuedAt || null,
      activeRuntime: Number(queue?.activeRuntimeJobs || 0) > 0,
    }),
  });
}

function classifyRuntimeError(error) {
  const code = String(error?.code || "").trim().toLowerCase();
  const message = String(error?.message || error || "").trim().toLowerCase();
  if (
    error?.cancelled === true
    || ["cancelled", "canceled", "interrupted"].includes(code)
    || /\b(cancelled|canceled|interrupted)\b/.test(message)
  ) {
    return Object.freeze({
      errorClass: "cancelled",
      retryable: false,
      action: "record_cancelled_terminal",
    });
  }
  if (
    ["auth_required", "unauthorized", "forbidden"].includes(code)
    || /\b(auth|login|credential|unauthorized|forbidden)\b/.test(message)
  ) {
    return Object.freeze({
      errorClass: "auth_required",
      retryable: false,
      action: "hold_queue_and_reauthenticate",
    });
  }
  if (
    error?.retryable === true
    && (code.includes("overload") || /\b(overload|too many requests|429)\b/.test(message))
  ) {
    return Object.freeze({
      errorClass: "runtime_overloaded",
      retryable: true,
      action: "bounded_retry_if_operation_safe",
    });
  }
  if (
    error?.retryable === true
    || /(?:econnreset|econnrefused|socket|transport|temporar|unavailable)/.test(
      `${code} ${message}`,
    )
  ) {
    return Object.freeze({
      errorClass: "transport_unavailable",
      retryable: true,
      action: "bounded_retry_if_operation_safe",
    });
  }
  return Object.freeze({
    errorClass: "runtime_terminal",
    retryable: false,
    action: "record_failed_terminal",
  });
}

module.exports = {
  DEFAULT_POLL_STALE_MS,
  DEFAULT_QUEUE_LIMIT,
  DEFAULT_QUEUE_STUCK_MS,
  REASON_ACTION,
  ResourceReadinessError,
  ResourceReadinessGate,
  captureLiveResourceSnapshot,
  classifyRuntimeError,
};
