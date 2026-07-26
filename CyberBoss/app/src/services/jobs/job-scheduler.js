"use strict";

const { randomBytes } = require("node:crypto");

const {
  ResourceReadinessGate,
  captureLiveResourceSnapshot,
  classifyRuntimeError,
} = require("./resource-readiness-gate");

const DEFAULT_RUNTIME_LEASE_MS = 30_000;
const DEFAULT_CONTROL_LEASE_MS = 10_000;
const DEFAULT_MAX_CONTROL_PER_CYCLE = 20;
const RUNTIME_EVENT_TYPES = new Set([
  "runtime.turn.started",
  "runtime.approval.requested",
  "runtime.turn.completed",
  "runtime.turn.failed",
]);

class JobSchedulerError extends Error {
  constructor(code) {
    super(code);
    this.name = "JobSchedulerError";
    this.code = code;
  }
}

function isoTimestamp(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) {
    throw new JobSchedulerError("CLOCK_INVALID");
  }
  return date.toISOString();
}

function normalizedText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function safeCode(value, fallback) {
  const normalized = normalizedText(value);
  return /^[A-Za-z0-9_.:/-]{1,160}$/.test(normalized)
    ? normalized
    : fallback;
}

function buildRunKey(threadId, turnId) {
  const thread = normalizedText(threadId);
  const turn = normalizedText(turnId);
  return thread && turn ? `${thread}\u0000${turn}` : "";
}

function parseControlCommand(text) {
  const normalized = normalizedText(text);
  if (!normalized.startsWith("/")) {
    throw new JobSchedulerError("CONTROL_COMMAND_REQUIRED");
  }
  const [name, ...args] = normalized.slice(1).split(/\s+/);
  const commandName = normalizedText(name).toLowerCase();
  if (!/^[a-z][a-z0-9_-]{0,31}$/.test(commandName)) {
    throw new JobSchedulerError("CONTROL_COMMAND_INVALID");
  }
  return Object.freeze({
    name: commandName,
    args: args.join(" ").trim(),
  });
}

function parseDurablePayload(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length === 0) {
    throw new JobSchedulerError("DURABLE_PAYLOAD_INVALID");
  }
  let parsed;
  try {
    parsed = JSON.parse(buffer.toString("utf8"));
  } catch {
    throw new JobSchedulerError("DURABLE_PAYLOAD_INVALID");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new JobSchedulerError("DURABLE_PAYLOAD_INVALID");
  }
  for (const field of ["provider", "accountId", "workspaceId", "senderId"]) {
    if (!normalizedText(parsed[field])) {
      throw new JobSchedulerError(`DURABLE_${field.toUpperCase()}_REQUIRED`);
    }
  }
  if (typeof parsed.text !== "string") {
    throw new JobSchedulerError("DURABLE_TEXT_REQUIRED");
  }
  return parsed;
}

function normalizeRuntimeTerminal(event) {
  if (event?.type === "runtime.turn.failed") {
    return Object.freeze({
      terminalStatus: "failed",
      classification: classifyRuntimeError({
        code: event?.payload?.errorClass,
        message: event?.payload?.text,
        retryable: event?.payload?.retryable === true,
        cancelled: event?.payload?.cancelled === true,
      }),
    });
  }
  const status = normalizedText(
    event?.payload?.status || event?.payload?.outcome,
  ).toLowerCase();
  if (["interrupted", "cancelled", "canceled"].includes(status)) {
    return Object.freeze({
      terminalStatus: "cancelled",
      classification: classifyRuntimeError({ cancelled: true }),
    });
  }
  return Object.freeze({
    terminalStatus: "succeeded",
    classification: null,
  });
}

class JobScheduler {
  constructor({
    database,
    workspaceRegistry,
    dispatchRuntime,
    dispatchControl,
    runtimeReadiness = () => ({ ready: false, reason: "unavailable" }),
    snapshotProvider = captureLiveResourceSnapshot,
    gate = null,
    now = () => new Date(),
    ownerId = `scheduler_${randomBytes(16).toString("hex")}`,
    bootId = "boot_unknown",
    pid = process.pid,
    runtimeLeaseMs = DEFAULT_RUNTIME_LEASE_MS,
    controlLeaseMs = DEFAULT_CONTROL_LEASE_MS,
    maxControlPerCycle = DEFAULT_MAX_CONTROL_PER_CYCLE,
    setIntervalFn = setInterval,
    clearIntervalFn = clearInterval,
    onRuntimeTerminal = () => {},
    canonicalMutationGuard = () => ({
      mutationAllowed: true,
      reason: "canonical_ready",
    }),
  } = {}) {
    if (
      !database
      || typeof database.claimNextRuntimeJob !== "function"
      || typeof database.claimNextControlJob !== "function"
    ) {
      throw new JobSchedulerError("RUNTIME_SPOOL_REQUIRED");
    }
    if (!workspaceRegistry || typeof workspaceRegistry.resolve !== "function") {
      throw new JobSchedulerError("WORKSPACE_REGISTRY_REQUIRED");
    }
    if (typeof dispatchRuntime !== "function" || typeof dispatchControl !== "function") {
      throw new JobSchedulerError("DISPATCH_CALLBACKS_REQUIRED");
    }
    if (
      !Number.isSafeInteger(maxControlPerCycle)
      || maxControlPerCycle < 1
      || maxControlPerCycle > 100
    ) {
      throw new JobSchedulerError("CONTROL_BATCH_LIMIT_INVALID");
    }
    this.database = database;
    this.workspaceRegistry = workspaceRegistry;
    this.dispatchRuntime = dispatchRuntime;
    this.dispatchControl = dispatchControl;
    this.runtimeReadiness = runtimeReadiness;
    this.snapshotProvider = snapshotProvider;
    this.now = now;
    this.gate = gate || new ResourceReadinessGate({ now });
    this.ownerId = ownerId;
    this.bootId = bootId;
    this.pid = pid;
    this.runtimeLeaseMs = runtimeLeaseMs;
    this.controlLeaseMs = controlLeaseMs;
    this.maxControlPerCycle = maxControlPerCycle;
    this.setIntervalFn = setIntervalFn;
    this.clearIntervalFn = clearIntervalFn;
    this.onRuntimeTerminal = onRuntimeTerminal;
    if (typeof canonicalMutationGuard !== "function") {
      throw new JobSchedulerError("CANONICAL_MUTATION_GUARD_REQUIRED");
    }
    this.canonicalMutationGuard = canonicalMutationGuard;
    this.lastPollSuccessAt = null;
    this.lastPollErrorClass = null;
    this.lastGate = Object.freeze({
      state: "blocked",
      reason: "measurement_unavailable",
      action: "capture_live_resource_profile",
      dispatchAllowed: false,
      guardState: "protect",
    });
    this.lastSuccessfulTurnAt = null;
    this.runToJobId = new Map();
    this.jobIdToRun = new Map();
    this.pendingEventsByRun = new Map();
    this.cyclePromise = null;
    this.heartbeatTimer = null;
    this.started = false;
  }

  notePollSuccess(at = this.now()) {
    this.lastPollSuccessAt = isoTimestamp(at);
    this.lastPollErrorClass = null;
  }

  notePollFailure(error, at = this.now()) {
    isoTimestamp(at);
    this.lastPollErrorClass = classifyRuntimeError(error).errorClass;
  }

  start() {
    if (this.started) {
      return;
    }
    this.database.recoverExpiredControlLease();
    this.database.recoverExpiredRuntimeLease();
    const intervalMs = Math.max(
      50,
      Math.floor(Math.min(this.runtimeLeaseMs, this.controlLeaseMs) / 3),
    );
    this.heartbeatTimer = this.setIntervalFn(() => {
      try {
        this.heartbeat();
      } catch {
        // Expiry recovery is fail-closed and is performed by the next cycle.
      }
    }, intervalMs);
    this.heartbeatTimer?.unref?.();
    this.started = true;
  }

  stop() {
    if (this.heartbeatTimer) {
      this.clearIntervalFn(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    this.started = false;
  }

  heartbeat() {
    const active = this.database.getActiveRuntimeJob();
    if (
      active
      && active.lease_owner === this.ownerId
      && ["running", "waiting_approval"].includes(active.status)
    ) {
      this.database.heartbeatManagedLease(active.id, {
        ownerId: this.ownerId,
        leaseMs: this.runtimeLeaseMs,
        command: false,
      });
    }
    const metrics = this.database.queueMetrics();
    if (metrics.activeControlJobs > 0) {
      const control = this.database.getActiveControlJob?.();
      if (control?.lease_owner === this.ownerId) {
        this.database.heartbeatManagedLease(control.id, {
          ownerId: this.ownerId,
          leaseMs: this.controlLeaseMs,
          command: true,
        });
      }
    }
  }

  runCycle() {
    if (this.cyclePromise) {
      return this.cyclePromise;
    }
    this.cyclePromise = this.#runCycle().finally(() => {
      this.cyclePromise = null;
    });
    return this.cyclePromise;
  }

  async #runCycle() {
    const recoveredControl = this.database.recoverExpiredControlLease();
    const recoveredRuntime = this.database.recoverExpiredRuntimeLease();
    let controlsProcessed = 0;
    while (controlsProcessed < this.maxControlPerCycle) {
      const processed = await this.#dispatchNextControl();
      if (!processed) {
        break;
      }
      controlsProcessed += 1;
    }
    const runtime = await this.#dispatchNextRuntime();
    return Object.freeze({
      controlsProcessed,
      runtime,
      recoveredControl,
      recoveredRuntime,
    });
  }

  async #dispatchNextControl() {
    const head = this.database.peekNextControlJob();
    if (!head) {
      return false;
    }
    const claim = this.database.claimNextControlJob({
      ownerId: this.ownerId,
      leaseMs: this.controlLeaseMs,
      expectedJobId: head.id,
      bootId: this.bootId,
      pid: this.pid,
    });
    if (!claim.claimed) {
      return false;
    }
    const job = claim.job;
    let payloadBuffer = null;
    let contextBuffer = null;
    try {
      const workspace = this.workspaceRegistry.resolve(job.workspace_alias);
      payloadBuffer = this.database.readInboundPayload(job.inbox_id);
      contextBuffer = this.database.readInboundContextToken(job.inbox_id);
      const normalized = parseDurablePayload(payloadBuffer);
      normalized.contextToken = contextBuffer
        ? contextBuffer.toString("utf8")
        : "";
      const command = parseControlCommand(normalized.text);
      let activeRun = this.#activeRuntimeRun();
      if (command.name === "stop" && activeRun) {
        this.database.markRuntimeCancelRequested(activeRun.job.id, {
          ownerId: this.ownerId,
        });
        activeRun = this.#activeRuntimeRun();
      }
      const result = await this.dispatchControl({
        job,
        normalized,
        command,
        activeRun,
        workspace,
      });
      const terminal = result?.terminalStatus === "cancelled"
        ? "cancelled"
        : result?.terminalStatus === "failed_terminal"
          ? "failed_terminal"
          : "succeeded";
      this.database.finishControlJob(job.id, terminal, {
        ownerId: this.ownerId,
        errorClass:
          terminal === "failed_terminal"
            ? safeCode(result?.errorClass, "control_terminal")
            : null,
        metadata: {
          command_code: command.name,
          result_code: safeCode(result?.resultCode, "processed"),
        },
      });
      return true;
    } catch (error) {
      const current = this.database.getJob(job.id);
      if (current?.status === "running" && current.lease_owner === this.ownerId) {
        this.database.finishControlJob(job.id, "failed_terminal", {
          ownerId: this.ownerId,
          errorClass: "control_dispatch_failed",
          metadata: {
            error_class: safeCode(error?.code, "control_dispatch_failed"),
          },
        });
      }
      return true;
    } finally {
      payloadBuffer?.fill?.(0);
      contextBuffer?.fill?.(0);
    }
  }

  async #dispatchNextRuntime() {
    if (this.database.getActiveRuntimeJob()) {
      return Object.freeze({ dispatched: false, reason: "active_job" });
    }
    let head = this.database.peekNextRuntimeJob();
    if (!head) {
      return Object.freeze({ dispatched: false, reason: "queue_empty" });
    }
    let canonicalGuard;
    try {
      canonicalGuard = await this.canonicalMutationGuard();
    } catch {
      canonicalGuard = {
        mutationAllowed: false,
        reason: "canonical_guard_unavailable",
      };
    }
    let operationClassFilter = null;
    if (
      head.operation_class === "bounded_mutation" &&
      canonicalGuard?.mutationAllowed !== true
    ) {
      const reason = safeCode(
        canonicalGuard?.reason,
        "canonical_backlog_protect",
      );
      this.database.setServiceState("canonical_mutation_gate", {
        mutation_allowed: false,
        reason_code: reason,
        state_code: "blocked",
      });
      const readOnlyHead = this.database.peekNextRuntimeJob({
        operationClass: "read_only",
      });
      if (!readOnlyHead) {
        return Object.freeze({
          dispatched: false,
          reason,
          canonicalGuard,
        });
      }
      head = readOnlyHead;
      operationClassFilter = "read_only";
    }

    let workspace;
    try {
      workspace = this.workspaceRegistry.resolve(head.workspace_alias);
    } catch {
      const claim = this.database.claimNextRuntimeJob({
        ownerId: this.ownerId,
        leaseMs: this.runtimeLeaseMs,
        expectedJobId: head.id,
        bootId: this.bootId,
        pid: this.pid,
        operationClass: operationClassFilter,
      });
      if (claim.claimed) {
        const finalJob = this.database.finishRuntimeJob(
          claim.job.id,
          "failed_terminal",
          {
          ownerId: this.ownerId,
          errorClass: "workspace_alias_rejected",
          metadata: { error_class: "workspace_alias_rejected" },
          },
        );
        await this.onRuntimeTerminal({
          job: finalJob,
          event: null,
          terminalStatus: finalJob.status,
        });
      }
      return Object.freeze({
        dispatched: false,
        reason: "workspace_alias_rejected",
      });
    }

    const queue = this.database.queueMetrics();
    const runtime = await this.runtimeReadiness();
    let snapshot;
    try {
      snapshot = await this.snapshotProvider({
        poll: {
          lastSuccessAt: this.lastPollSuccessAt,
          errorClass: this.lastPollErrorClass,
        },
        runtime,
        queue,
      });
    } catch {
      snapshot = null;
    }
    const gate = this.gate.evaluate({
      operationClass: head.operation_class,
      snapshot,
    });
    this.lastGate = gate;
    this.database.setServiceState("scheduler_gate", {
      action_code: gate.action,
      dispatch_allowed: gate.dispatchAllowed,
      reason_code: gate.reason,
      state_code: gate.state,
    });
    if (!gate.dispatchAllowed) {
      return Object.freeze({ dispatched: false, reason: gate.reason, gate });
    }

    const claim = this.database.claimNextRuntimeJob({
      ownerId: this.ownerId,
      leaseMs: this.runtimeLeaseMs,
      expectedJobId: head.id,
      bootId: this.bootId,
      pid: this.pid,
      operationClass: operationClassFilter,
    });
    if (!claim.claimed) {
      return Object.freeze({
        dispatched: false,
        reason: claim.reason,
        gate,
      });
    }
    const job = claim.job;
    let payloadBuffer = null;
    let contextBuffer = null;
    let dispatchStarted = false;
    try {
      payloadBuffer = this.database.readInboundPayload(job.inbox_id);
      contextBuffer = this.database.readInboundContextToken(job.inbox_id);
      const normalized = parseDurablePayload(payloadBuffer);
      normalized.contextToken = contextBuffer
        ? contextBuffer.toString("utf8")
        : "";
      this.database.markRuntimeDispatchStarted(job.id, {
        ownerId: this.ownerId,
      });
      dispatchStarted = true;
      const run = await this.dispatchRuntime({
        job: this.database.getJob(job.id),
        normalized,
        workspace,
      });
      const threadId = normalizedText(run?.threadId);
      const turnId = normalizedText(run?.turnId);
      if (!threadId || !turnId) {
        throw new JobSchedulerError("RUNTIME_RUN_ID_REQUIRED");
      }
      this.database.bindRuntimeRun(job.id, {
        ownerId: this.ownerId,
        threadId,
        turnId,
      });
      const runKey = buildRunKey(threadId, turnId);
      this.runToJobId.set(runKey, job.id);
      this.jobIdToRun.set(job.id, Object.freeze({ threadId, turnId, runKey }));
      await this.#drainBufferedEvents(runKey);
      return Object.freeze({
        dispatched: true,
        reason: "dispatched",
        jobId: job.id,
        gate,
      });
    } catch (error) {
      const current = this.database.getJob(job.id);
      if (
        current
        && ["running", "waiting_approval"].includes(current.status)
        && current.lease_owner === this.ownerId
      ) {
        const classification = classifyRuntimeError(error);
        const finalJob = this.database.finishRuntimeJob(
          job.id,
          "failed_terminal",
          {
          ownerId: this.ownerId,
          errorClass: dispatchStarted
            ? "runtime_dispatch_ambiguous"
            : "runtime_dispatch_rejected",
          metadata: {
            error_class: classification.errorClass,
            replay_allowed: false,
          },
          },
        );
        await this.onRuntimeTerminal({
          job: finalJob,
          event: null,
          terminalStatus: finalJob.status,
        });
      }
      return Object.freeze({
        dispatched: false,
        reason: dispatchStarted
          ? "runtime_dispatch_ambiguous"
          : "runtime_dispatch_rejected",
      });
    } finally {
      payloadBuffer?.fill?.(0);
      contextBuffer?.fill?.(0);
    }
  }

  async handleRuntimeEvent(event) {
    if (!RUNTIME_EVENT_TYPES.has(event?.type)) {
      return Object.freeze({ handled: false, reason: "event_not_material" });
    }
    const runKey = buildRunKey(
      event?.payload?.threadId,
      event?.payload?.turnId,
    );
    if (!runKey) {
      return Object.freeze({ handled: false, reason: "run_id_missing" });
    }
    const jobId = this.runToJobId.get(runKey);
    if (!jobId) {
      const active = this.database.getActiveRuntimeJob();
      if (active?.dispatch_started_at && !active.runtime_turn_hash) {
        const pending = this.pendingEventsByRun.get(runKey) || [];
        if (pending.length < 20) {
          pending.push(event);
          this.pendingEventsByRun.set(runKey, pending);
        }
        return Object.freeze({ handled: false, reason: "binding_pending" });
      }
      return Object.freeze({ handled: false, reason: "late_or_unmatched" });
    }
    const job = this.database.getJob(jobId);
    if (
      !job
      || job.lease_owner !== this.ownerId
      || !["running", "waiting_approval"].includes(job.status)
    ) {
      this.#forgetRun(jobId, runKey);
      return Object.freeze({ handled: false, reason: "stale_binding" });
    }

    if (event.type === "runtime.turn.started") {
      return Object.freeze({ handled: true, terminal: false });
    }
    if (event.type === "runtime.approval.requested") {
      if (job.status === "running") {
        this.database.transitionManagedRuntimeJob(job.id, "waiting_approval", {
          ownerId: this.ownerId,
          metadata: { transition_code: "runtime_approval_requested" },
        });
      }
      return Object.freeze({ handled: true, terminal: false });
    }

    const terminal = normalizeRuntimeTerminal(event);
    let finalJob;
    if (terminal.terminalStatus === "succeeded") {
      finalJob = this.database.finishRuntimeJob(job.id, "succeeded", {
        ownerId: this.ownerId,
        metadata: { result_code: "runtime_completed" },
      });
      this.lastSuccessfulTurnAt = isoTimestamp(this.now());
    } else if (terminal.terminalStatus === "cancelled") {
      finalJob = this.database.finishRuntimeJob(job.id, "cancelled", {
        ownerId: this.ownerId,
        errorClass: "cancelled",
        metadata: { result_code: "runtime_interrupted" },
      });
    } else if (
      terminal.classification.retryable
      && job.operation_class === "read_only"
      && Number(job.attempt_count) < Number(job.max_attempts)
    ) {
      finalJob = this.database.requeueRetryableRuntimeJob(job.id, {
        ownerId: this.ownerId,
        errorClass: terminal.classification.errorClass,
        metadata: { retry_allowed: true },
      });
    } else {
      finalJob = this.database.finishRuntimeJob(job.id, "failed_terminal", {
        ownerId: this.ownerId,
        errorClass:
          terminal.classification.retryable
          && job.operation_class !== "read_only"
            ? "retryable_replay_unsafe"
            : terminal.classification.errorClass,
        metadata: {
          replay_allowed: false,
          retry_allowed: terminal.classification.retryable,
        },
      });
    }
    this.#forgetRun(jobId, runKey);
    await this.onRuntimeTerminal({
      job: finalJob,
      event,
      terminalStatus: finalJob.status,
    });
    return Object.freeze({
      handled: true,
      terminal: true,
      jobId: finalJob.id,
      terminalStatus: finalJob.status,
    });
  }

  async #drainBufferedEvents(runKey) {
    const pending = this.pendingEventsByRun.get(runKey) || [];
    this.pendingEventsByRun.delete(runKey);
    for (const event of pending) {
      await this.handleRuntimeEvent(event);
    }
    for (const key of this.pendingEventsByRun.keys()) {
      if (key !== runKey) {
        this.pendingEventsByRun.delete(key);
      }
    }
  }

  #forgetRun(jobId, runKey) {
    this.runToJobId.delete(runKey);
    this.jobIdToRun.delete(jobId);
    this.pendingEventsByRun.delete(runKey);
  }

  #activeRuntimeRun() {
    const job = this.database.getActiveRuntimeJob();
    if (!job) {
      return null;
    }
    const run = this.jobIdToRun.get(job.id) || null;
    return Object.freeze({
      job,
      threadId: run?.threadId || "",
      turnId: run?.turnId || "",
      runBound: Boolean(run),
    });
  }

  statusSnapshot() {
    const queue = this.database.queueMetrics();
    const active = this.database.getActiveRuntimeJob();
    return Object.freeze({
      schedulerEnabled: true,
      queuedTotal: queue.queuedTotal,
      queuedRuntime: queue.queuedRuntime,
      queuedControl: queue.queuedControl,
      activeRuntime: Boolean(active),
      activeRuntimeLeaseCount: queue.activeRuntimeLeases,
      activeStatus: active?.status || "idle",
      activeOperationClass: active?.operation_class || "none",
      cancelPending: Boolean(active?.cancel_requested_at),
      gateState: this.lastGate.state,
      gateReason: this.lastGate.reason,
      gateAction: this.lastGate.action,
      lastSuccessfulTurnAt: this.lastSuccessfulTurnAt,
      lastPollSuccessAt: this.lastPollSuccessAt,
    });
  }
}

module.exports = {
  DEFAULT_CONTROL_LEASE_MS,
  DEFAULT_MAX_CONTROL_PER_CYCLE,
  DEFAULT_RUNTIME_LEASE_MS,
  JobScheduler,
  JobSchedulerError,
  normalizeRuntimeTerminal,
  parseControlCommand,
  parseDurablePayload,
};
