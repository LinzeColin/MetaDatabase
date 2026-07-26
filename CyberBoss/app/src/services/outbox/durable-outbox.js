"use strict";

const { createHash, randomBytes } = require("node:crypto");

const {
  DEFAULT_OUTBOX_LEASE_MS,
  RuntimeSpoolError,
  stableJson,
} = require("../db/database-adapter");

const DEFAULT_OUTBOX_MAX_ATTEMPTS = 5;
const DEFAULT_OUTBOX_BASE_DELAY_MS = 1_000;
const DEFAULT_OUTBOX_MAX_DELAY_MS = 60_000;
const DEFAULT_OUTBOX_JITTER_RATIO = 0.2;
const DEFAULT_OUTBOX_CHUNK_CHARS = 3_600;
const MAX_PROVIDER_CHUNK_CHARS = 3_800;
const CHUNK_HEADER_RESERVE = 32;
const FINAL_MESSAGE_KINDS = new Set(["result", "error", "cancelled"]);
const MESSAGE_KINDS = new Set([
  "accepted",
  "progress",
  "result",
  "error",
  "cancelled",
]);
const TERMINAL_AUTH_ADVICE = [
  "⚠️ Delivery authentication expired.",
  "Action: re-login, then send a new message so CyberBoss can resume delivery.",
].join("\n");

class DurableOutboxError extends Error {
  constructor(code, options = {}) {
    super(code);
    this.name = "DurableOutboxError";
    this.code = code;
    if (options.cause !== undefined) {
      this.cause = options.cause;
    }
  }
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function normalizeIso(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) {
    throw new DurableOutboxError("OUTBOX_CLOCK_INVALID");
  }
  return date.toISOString();
}

function normalizedText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeDurableText(value) {
  const text = String(value ?? "").replace(/\r\n?/g, "\n").trim();
  if (!text) {
    throw new DurableOutboxError("OUTBOX_TEXT_REQUIRED");
  }
  return text;
}

function assertChunkLimit(maxChunkChars) {
  if (
    !Number.isSafeInteger(maxChunkChars)
    || maxChunkChars < 64
    || maxChunkChars > MAX_PROVIDER_CHUNK_CHARS
  ) {
    throw new DurableOutboxError("OUTBOX_CHUNK_LIMIT_INVALID");
  }
}

function splitDurableText(text, {
  maxChunkChars = DEFAULT_OUTBOX_CHUNK_CHARS,
} = {}) {
  assertChunkLimit(maxChunkChars);
  const normalized = normalizeDurableText(text);
  const runes = Array.from(normalized);
  const bodyLimit = maxChunkChars - CHUNK_HEADER_RESERVE;
  const bodies = [];
  for (let offset = 0; offset < runes.length; offset += bodyLimit) {
    bodies.push(runes.slice(offset, offset + bodyLimit).join(""));
  }
  const count = bodies.length;
  return Object.freeze(
    bodies.map((body, index) => {
      const chunkIndex = index + 1;
      const header = count > 1 ? `[${chunkIndex}/${count}] ` : "";
      const outgoingText = `${header}${body}`;
      if (Array.from(outgoingText).length > maxChunkChars) {
        throw new DurableOutboxError("OUTBOX_CHUNK_LIMIT_EXCEEDED");
      }
      return Object.freeze({
        index: chunkIndex,
        count,
        body,
        outgoingText,
        bodySha256: sha256(Buffer.from(body, "utf8")),
        payloadSha256: sha256(Buffer.from(outgoingText, "utf8")),
      });
    }),
  );
}

function reconstructDurableChunks(chunks) {
  if (!Array.isArray(chunks) || chunks.length === 0) {
    throw new DurableOutboxError("OUTBOX_CHUNKS_REQUIRED");
  }
  const ordered = chunks.slice().sort((left, right) => left.index - right.index);
  const expectedCount = Number(ordered[0].count);
  if (
    !Number.isSafeInteger(expectedCount)
    || expectedCount !== ordered.length
    || ordered.some(
      (chunk, index) =>
        Number(chunk.index) !== index + 1
        || Number(chunk.count) !== expectedCount
        || typeof chunk.body !== "string",
    )
  ) {
    throw new DurableOutboxError("OUTBOX_CHUNK_SEQUENCE_INVALID");
  }
  return ordered.map((chunk) => chunk.body).join("");
}

function buildStableOutboxIdentity({
  jobId,
  messageKind,
  logicalKey,
  logicalMessageSha256,
  chunkIndex,
  chunkCount,
  payloadSha256,
}) {
  const encoded = stableJson({
    chunk_count: chunkCount,
    chunk_index: chunkIndex,
    job_id: jobId,
    logical_key_sha256: sha256(Buffer.from(String(logicalKey), "utf8")),
    logical_message_sha256: logicalMessageSha256,
    message_kind: messageKind,
    payload_sha256: payloadSha256,
  });
  const digest = sha256(Buffer.from(encoded, "utf8"));
  return Object.freeze({
    dedupeKey: `outbox_${digest}`,
    providerClientId: `cb-outbox-${digest.slice(0, 32)}`,
  });
}

function computeBackoffDelayMs({
  attemptNumber,
  baseDelayMs = DEFAULT_OUTBOX_BASE_DELAY_MS,
  maxDelayMs = DEFAULT_OUTBOX_MAX_DELAY_MS,
  jitterRatio = DEFAULT_OUTBOX_JITTER_RATIO,
  random = Math.random,
  retryAfterMs = null,
}) {
  if (
    !Number.isSafeInteger(attemptNumber)
    || attemptNumber < 1
    || !Number.isSafeInteger(baseDelayMs)
    || baseDelayMs < 1
    || !Number.isSafeInteger(maxDelayMs)
    || maxDelayMs < baseDelayMs
    || typeof jitterRatio !== "number"
    || jitterRatio < 0
    || jitterRatio > 0.5
    || typeof random !== "function"
  ) {
    throw new DurableOutboxError("OUTBOX_BACKOFF_CONFIG_INVALID");
  }
  const sample = Number(random());
  if (!Number.isFinite(sample) || sample < 0 || sample > 1) {
    throw new DurableOutboxError("OUTBOX_RANDOM_INVALID");
  }
  const exponential = Math.min(
    maxDelayMs,
    baseDelayMs * (2 ** Math.max(0, attemptNumber - 1)),
  );
  const jitter = exponential * jitterRatio * ((sample * 2) - 1);
  let delay = Math.max(0, Math.min(maxDelayMs, Math.round(exponential + jitter)));
  if (retryAfterMs !== null && retryAfterMs !== undefined) {
    const hint = Number(retryAfterMs);
    if (Number.isFinite(hint) && hint >= 0) {
      delay = Math.min(maxDelayMs, Math.max(delay, Math.round(hint)));
    }
  }
  return delay;
}

function numericCode(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const code = Number(value);
  return Number.isFinite(code) ? code : null;
}

function classifyProviderError(error) {
  const status = numericCode(error?.status ?? error?.httpStatus);
  const ret = numericCode(error?.ret);
  const errcode = numericCode(error?.errcode);
  const code = normalizedText(error?.code).toLowerCase();
  const message = normalizedText(error?.message).toLowerCase();
  const outcomeKnown = error?.outcomeKnown === true;
  const retryAfterMs = numericCode(error?.retryAfterMs);

  if (
    status === 401
    || status === 403
    || ret === -14
    || errcode === -14
    || /(?:invalid|expired).{0,24}(?:context|session|auth)|missing context/.test(
      `${code} ${message}`,
    )
  ) {
    return Object.freeze({
      kind: "terminal",
      errorClass:
        /context/.test(`${code} ${message}`) || ret === -14 || errcode === -14
          ? "context_invalid"
          : "auth_invalid",
      retryAfterMs: null,
      actionable: true,
    });
  }

  const explicitRetryable =
    [408, 425, 429].includes(status)
    || (status !== null && status >= 500 && status <= 599)
    || error?.retryable === true
    || ["provider_overload", "provider_unavailable"].includes(code);
  if (outcomeKnown && explicitRetryable) {
    return Object.freeze({
      kind: "retryable",
      errorClass:
        status === 429 || code === "provider_overload"
          ? "provider_overload"
          : "provider_transient",
      retryAfterMs,
      actionable: false,
    });
  }

  if (!outcomeKnown || error?.code === "OUTBOX_CONFIRMATION_REQUIRED") {
    return Object.freeze({
      kind: "ambiguous",
      errorClass: "ambiguous_send_outcome",
      retryAfterMs: null,
      actionable: false,
    });
  }

  return Object.freeze({
    kind: "terminal",
    errorClass: "provider_terminal",
    retryAfterMs: null,
    actionable: false,
  });
}

function normalizeProviderConfirmation(response, clientId) {
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    throw new DurableOutboxError("OUTBOX_CONFIRMATION_REQUIRED");
  }
  const ret = numericCode(response.ret);
  const errcode = numericCode(response.errcode);
  const acknowledged =
    ret === 0
    || errcode === 0
    || response.confirmed === true;
  if (
    !acknowledged
    || (ret !== null && ret !== 0)
    || (errcode !== null && errcode !== 0)
  ) {
    throw new DurableOutboxError("OUTBOX_CONFIRMATION_REQUIRED");
  }
  const providerMessageId = normalizedText(
    response.message_id ?? response.messageId,
  );
  const receipt = {
    client_id_sha256: sha256(Buffer.from(clientId, "utf8")),
    errcode,
    message_id_sha256: providerMessageId
      ? sha256(Buffer.from(providerMessageId, "utf8"))
      : null,
    ret,
  };
  return Object.freeze({
    confirmed: true,
    clientId,
    receiptHash: sha256(Buffer.from(stableJson(receipt), "utf8")),
    receipt: Object.freeze(receipt),
  });
}

function isSimulatedProcessCrash(error) {
  return error?.simulateProcessCrash === true;
}

class DurableOutboxWorker {
  constructor({
    database,
    channelAdapter,
    now = () => new Date(),
    random = Math.random,
    ownerId = `outbox_${randomBytes(16).toString("hex")}`,
    leaseMs = DEFAULT_OUTBOX_LEASE_MS,
    maxAttempts = DEFAULT_OUTBOX_MAX_ATTEMPTS,
    baseDelayMs = DEFAULT_OUTBOX_BASE_DELAY_MS,
    maxDelayMs = DEFAULT_OUTBOX_MAX_DELAY_MS,
    jitterRatio = DEFAULT_OUTBOX_JITTER_RATIO,
    maxChunkChars = DEFAULT_OUTBOX_CHUNK_CHARS,
    maxMessagesPerCycle = 100,
    setTimeoutFn = setTimeout,
    clearTimeoutFn = clearTimeout,
    autoSchedule = true,
    faultInjector = () => {},
  } = {}) {
    if (
      !database
      || typeof database.enqueueOutbox !== "function"
      || typeof database.claimNextOutbox !== "function"
    ) {
      throw new DurableOutboxError("OUTBOX_DATABASE_REQUIRED");
    }
    if (
      !channelAdapter
      || typeof channelAdapter.sendTextChunk !== "function"
    ) {
      throw new DurableOutboxError("OUTBOX_SINGLE_CHUNK_TRANSPORT_REQUIRED");
    }
    if (
      !Number.isSafeInteger(maxAttempts)
      || maxAttempts < 1
      || maxAttempts > 20
      || !Number.isSafeInteger(maxMessagesPerCycle)
      || maxMessagesPerCycle < 1
      || maxMessagesPerCycle > 1_000
      || typeof now !== "function"
      || typeof random !== "function"
      || typeof setTimeoutFn !== "function"
      || typeof clearTimeoutFn !== "function"
    ) {
      throw new DurableOutboxError("OUTBOX_WORKER_CONFIG_INVALID");
    }
    assertChunkLimit(maxChunkChars);
    computeBackoffDelayMs({
      attemptNumber: 1,
      baseDelayMs,
      maxDelayMs,
      jitterRatio,
      random: () => 0.5,
    });

    this.database = database;
    this.channelAdapter = channelAdapter;
    this.now = now;
    this.random = random;
    this.ownerId = ownerId;
    this.leaseMs = leaseMs;
    this.maxAttempts = maxAttempts;
    this.baseDelayMs = baseDelayMs;
    this.maxDelayMs = maxDelayMs;
    this.jitterRatio = jitterRatio;
    this.maxChunkChars = maxChunkChars;
    this.maxMessagesPerCycle = maxMessagesPerCycle;
    this.setTimeoutFn = setTimeoutFn;
    this.clearTimeoutFn = clearTimeoutFn;
    this.autoSchedule = autoSchedule;
    this.faultInjector =
      typeof faultInjector === "function" ? faultInjector : () => {};
    this.started = false;
    this.cyclePromise = null;
    this.timer = null;
    this.lastRecovery = Object.freeze({
      inspected: 0,
      safeRetry: 0,
      ambiguousTerminal: 0,
      affectedJobs: 0,
    });
  }

  #fault(point, row = null) {
    this.faultInjector(point, row
      ? Object.freeze({
          attemptNumber: Number(row.attempt_count),
          outboxId: row.id,
          status: row.status,
        })
      : null);
  }

  stageMessage({
    jobId,
    messageKind,
    logicalKey,
    target,
    text,
    maxAttempts = this.maxAttempts,
    advisory = false,
  }) {
    if (!MESSAGE_KINDS.has(messageKind)) {
      throw new DurableOutboxError("OUTBOX_MESSAGE_KIND_INVALID");
    }
    if (
      !normalizedText(jobId)
      || !normalizedText(logicalKey)
      || String(logicalKey).length > 4_096
      || !target
      || typeof target !== "object"
      || !normalizedText(target.userId)
      || !normalizedText(target.contextToken)
      || !Number.isSafeInteger(maxAttempts)
      || maxAttempts < 1
      || maxAttempts > 20
    ) {
      throw new DurableOutboxError("OUTBOX_STAGE_INPUT_INVALID");
    }
    const normalized = normalizeDurableText(text);
    const sourceSha256 = sha256(Buffer.from(normalized, "utf8"));
    const logicalMessageSha256 = sha256(
      Buffer.from(
        stableJson({
          job_id: jobId,
          logical_key_sha256: sha256(Buffer.from(String(logicalKey), "utf8")),
          message_kind: messageKind,
          source_sha256: sourceSha256,
        }),
        "utf8",
      ),
    );
    const chunks = splitDurableText(normalized, {
      maxChunkChars: this.maxChunkChars,
    });
    const staged = chunks.map((chunk) => {
      const identity = buildStableOutboxIdentity({
        jobId,
        messageKind,
        logicalKey,
        logicalMessageSha256,
        chunkIndex: chunk.index,
        chunkCount: chunk.count,
        payloadSha256: chunk.payloadSha256,
      });
      return this.database.enqueueOutbox({
        jobId,
        dedupeKey: identity.dedupeKey,
        messageKind,
        targetRef: {
          advisory: advisory === true,
          contextToken: normalizedText(target.contextToken),
          preserveBlock: target.preserveBlock === true,
          userId: normalizedText(target.userId),
        },
        payload: chunk.outgoingText,
        chunkIndex: chunk.index,
        chunkCount: chunk.count,
        maxAttempts,
        logicalMessageSha256,
        providerClientId: identity.providerClientId,
      });
    });
    if (FINAL_MESSAGE_KINDS.has(messageKind)) {
      this.database.reconcileJobReplyState(jobId);
    }
    if (this.started) {
      this.#schedule(0);
    }
    return Object.freeze({
      chunkCount: chunks.length,
      chunks,
      logicalMessageSha256,
      sourceSha256,
      staged: Object.freeze(staged),
    });
  }

  async stageAndDrain(input) {
    const staged = this.stageMessage(input);
    const cycle = await this.runCycle();
    const rows = staged.staged.map((row) => this.database.getOutbox(row.id));
    return Object.freeze({
      ...staged,
      cycle,
      confirmed: rows.every((row) => row?.status === "confirmed"),
      rows: Object.freeze(rows),
    });
  }

  async ensureTerminalMessage({
    jobId,
    terminalStatus,
    target,
    logicalKey,
    text = "",
  }) {
    const messageKind =
      terminalStatus === "failed_terminal"
        ? "error"
        : terminalStatus === "cancelled"
          ? "cancelled"
          : "result";
    if (this.database.hasFinalOutbox(jobId, messageKind)) {
      const state = this.database.reconcileJobReplyState(jobId);
      return Object.freeze({ staged: false, state });
    }
    const safeText =
      messageKind === "error"
        ? "❌ Execution failed.\nAction: review the request and retry when ready."
        : messageKind === "cancelled"
          ? "⏹️ Execution cancelled."
          : normalizeDurableText(text || "✅ Completed.");
    const result = await this.stageAndDrain({
      jobId,
      messageKind,
      logicalKey,
      target,
      text: safeText,
    });
    return Object.freeze({
      staged: true,
      result,
      state: this.database.reconcileJobReplyState(jobId),
    });
  }

  async start() {
    if (this.started) {
      return Object.freeze({
        alreadyStarted: true,
        recovery: this.lastRecovery,
      });
    }
    this.lastRecovery = this.database.recoverOutboxOnExclusiveStartup();
    this.database.reconcileAllFinalOutboxJobs();
    this.started = true;
    const cycle = await this.runCycle();
    this.#scheduleNextDue();
    return Object.freeze({
      alreadyStarted: false,
      recovery: this.lastRecovery,
      cycle,
    });
  }

  stop() {
    this.started = false;
    if (this.timer) {
      this.clearTimeoutFn(this.timer);
      this.timer = null;
    }
  }

  runCycle() {
    if (this.cyclePromise) {
      return this.cyclePromise;
    }
    this.cyclePromise = this.#runCycle().finally(() => {
      this.cyclePromise = null;
      if (this.started) {
        this.#scheduleNextDue();
      }
    });
    return this.cyclePromise;
  }

  async #runCycle() {
    let processed = 0;
    let confirmed = 0;
    let retryScheduled = 0;
    let terminal = 0;
    let ambiguous = 0;
    while (processed < this.maxMessagesPerCycle) {
      const claim = this.database.claimNextOutbox({
        ownerId: this.ownerId,
        leaseMs: this.leaseMs,
      });
      if (!claim.claimed) {
        break;
      }
      const outcome = await this.#deliverClaim(claim.row);
      processed += 1;
      confirmed += outcome === "confirmed" ? 1 : 0;
      retryScheduled += outcome === "retry" ? 1 : 0;
      terminal += outcome === "terminal" ? 1 : 0;
      ambiguous += outcome === "ambiguous" ? 1 : 0;
    }
    return Object.freeze({
      ambiguous,
      confirmed,
      processed,
      retryScheduled,
      terminal,
    });
  }

  async #deliverClaim(claimedRow) {
    const material = this.database.readClaimedOutbox(claimedRow.id, {
      ownerId: this.ownerId,
    });
    this.#fault("after_claim_before_dispatch", claimedRow);
    try {
      const started = this.database.markOutboxDispatchStarted(claimedRow.id, {
        ownerId: this.ownerId,
      });
      this.#fault("after_dispatch_before_provider", started);
      const response = await this.channelAdapter.sendTextChunk({
        userId: material.target.userId,
        text: material.payload,
        contextToken: material.target.contextToken,
        clientId: material.providerClientId,
        preserveBlock: material.target.preserveBlock === true,
      });
      this.#fault("after_provider_before_confirmation", started);
      const confirmation = normalizeProviderConfirmation(
        response,
        material.providerClientId,
      );
      const confirmed = this.database.markOutboxConfirmed(claimedRow.id, {
        ownerId: this.ownerId,
        providerConfirmation: confirmation,
      });
      this.#fault("after_confirmation_commit", confirmed);
      this.database.reconcileJobReplyState(confirmed.job_id);
      return "confirmed";
    } catch (error) {
      if (isSimulatedProcessCrash(error)) {
        throw error;
      }
      const current = this.database.getOutbox(claimedRow.id);
      if (!current || current.status !== "sending") {
        throw error;
      }
      const classification = classifyProviderError(error);
      if (
        classification.kind === "retryable"
        && Number(current.attempt_count) < Number(current.max_attempts)
      ) {
        const delayMs = computeBackoffDelayMs({
          attemptNumber: Number(current.attempt_count),
          baseDelayMs: this.baseDelayMs,
          maxDelayMs: this.maxDelayMs,
          jitterRatio: this.jitterRatio,
          random: this.random,
          retryAfterMs: classification.retryAfterMs,
        });
        const nextAttemptAt = new Date(
          new Date(this.now()).getTime() + delayMs,
        );
        this.database.markOutboxRetry(current.id, {
          ownerId: this.ownerId,
          errorClass: classification.errorClass,
          nextAttemptAt,
        });
        return "retry";
      }
      const ambiguous = classification.kind === "ambiguous";
      const failed = this.database.markOutboxTerminal(current.id, {
        ownerId: this.ownerId,
        errorClass: ambiguous
          ? "ambiguous_send_outcome"
          : classification.kind === "retryable"
            ? "retry_budget_exhausted"
            : classification.errorClass,
        ambiguous,
        recoveryClass: ambiguous
          ? "manual_reconcile_required"
          : "provider_terminal",
      });
      this.database.failOutboxDependents(failed.id);
      this.database.reconcileJobReplyState(failed.job_id);
      if (classification.actionable && material.target.advisory !== true) {
        this.#stageTerminalAdvice(failed, material.target);
      }
      return ambiguous ? "ambiguous" : "terminal";
    }
  }

  #stageTerminalAdvice(failedRow, previousTarget) {
    if (typeof this.channelAdapter.getKnownContextTokens !== "function") {
      return null;
    }
    const tokens = this.channelAdapter.getKnownContextTokens();
    const refreshed = normalizedText(tokens?.[previousTarget.userId]);
    if (!refreshed || refreshed === normalizedText(previousTarget.contextToken)) {
      return null;
    }
    return this.stageMessage({
      jobId: failedRow.job_id,
      messageKind: "error",
      logicalKey: `terminal-advice:${failedRow.dedupe_key}`,
      target: {
        userId: previousTarget.userId,
        contextToken: refreshed,
        preserveBlock: true,
      },
      text: TERMINAL_AUTH_ADVICE,
      maxAttempts: 1,
      advisory: true,
    });
  }

  #schedule(delayMs) {
    if (!this.started || !this.autoSchedule) {
      return;
    }
    if (this.timer) {
      this.clearTimeoutFn(this.timer);
      this.timer = null;
    }
    const delay = Math.max(0, Math.min(this.maxDelayMs, Math.round(delayMs)));
    this.timer = this.setTimeoutFn(() => {
      this.timer = null;
      void this.runCycle().catch(() => {
        // Durable state remains authoritative; the next lifecycle probe retries.
      });
    }, delay);
    this.timer?.unref?.();
  }

  #scheduleNextDue() {
    if (!this.started || !this.autoSchedule) {
      return;
    }
    const dueAt = this.database.nextOutboxDueAt();
    if (!dueAt) {
      if (this.timer) {
        this.clearTimeoutFn(this.timer);
        this.timer = null;
      }
      return;
    }
    const delay = Math.max(
      0,
      new Date(dueAt).getTime() - new Date(this.now()).getTime(),
    );
    this.#schedule(delay);
  }

  statusSnapshot() {
    return Object.freeze({
      enabled: true,
      started: this.started,
      metrics: this.database.outboxMetrics(),
      nextDueAt: this.database.nextOutboxDueAt(),
      recovery: this.lastRecovery,
    });
  }
}

module.exports = {
  DEFAULT_OUTBOX_BASE_DELAY_MS,
  DEFAULT_OUTBOX_CHUNK_CHARS,
  DEFAULT_OUTBOX_JITTER_RATIO,
  DEFAULT_OUTBOX_MAX_ATTEMPTS,
  DEFAULT_OUTBOX_MAX_DELAY_MS,
  DurableOutboxError,
  DurableOutboxWorker,
  TERMINAL_AUTH_ADVICE,
  buildStableOutboxIdentity,
  classifyProviderError,
  computeBackoffDelayMs,
  normalizeProviderConfirmation,
  reconstructDurableChunks,
  splitDurableText,
};
