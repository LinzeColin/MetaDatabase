"use strict";

// CB-700 / AC-045, AC-046: the preflight guard. Nothing reaches a provider
// before a reservation exists, and a denial always reports modelCalls 0 so the
// "zero provider calls when over budget" claim is directly observable.

const { randomUUID } = require("node:crypto");
const { estimateInputTokenUpperBound } = require("./token-estimator");
const { normalizeProviderUsage } = require("./usage-normalizer");

const DEFAULT_BUDGET = Object.freeze({
  maxReservedTokensPerRequest: 16_000,
  maxOutputTokensPerRequest: 1_200,
  perUserDailyTokens: 100_000,
  perUserMonthlyTokens: 2_000_000,
  globalDailyTokens: 2_000_000,
  globalMonthlyTokens: 50_000_000,
  softWarningRatio: 0.8,
});

const MESSAGES = Object.freeze({
  DUPLICATE: "这条请求已经处理过了，不会重复消耗你的额度。",
  OVER_BUDGET: "本次 AI 用量已经到上限了，明天会自动恢复，也可以在设置页调整额度。",
  REQUEST_TOO_LARGE: "这条消息太长了，缩短一点我再帮你处理。",
  SOFT_WARNING: "提醒一下：你的 AI 用量快到上限了。",
});

class ModelBudgetError extends Error {
  constructor(code) {
    super(code);
    this.name = "ModelBudgetError";
    this.code = code;
  }
}

function assertPositiveInteger(name, value) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new ModelBudgetError(`${name.toUpperCase()}_INVALID`);
  }
}

function validateBudgetPolicy(input = {}) {
  const policy = { ...DEFAULT_BUDGET, ...input };
  for (const key of [
    "maxReservedTokensPerRequest",
    "maxOutputTokensPerRequest",
    "perUserDailyTokens",
    "perUserMonthlyTokens",
    "globalDailyTokens",
    "globalMonthlyTokens",
  ]) {
    assertPositiveInteger(key, policy[key]);
  }
  if (!(policy.softWarningRatio > 0 && policy.softWarningRatio < 1)) {
    throw new ModelBudgetError("SOFT_WARNING_RATIO_INVALID");
  }
  if (policy.maxOutputTokensPerRequest >= policy.maxReservedTokensPerRequest) {
    throw new ModelBudgetError("OUTPUT_CAP_MUST_BE_BELOW_RESERVATION_CAP");
  }
  return Object.freeze(policy);
}

class ModelBudgetGuard {
  constructor({ ledger, policy = DEFAULT_BUDGET, clock = () => Date.now() }) {
    if (!ledger) {
      throw new ModelBudgetError("BUDGET_LEDGER_REQUIRED");
    }
    this.ledger = ledger;
    this.policy = validateBudgetPolicy(policy);
    this.clock = clock;
  }

  preflight({ requestId, userId, providerId, messages, maxOutputTokens }) {
    if (!requestId || !userId || !providerId) {
      throw new ModelBudgetError("REQUEST_IDENTITY_REQUIRED");
    }
    // AC-046: request_id idempotency is scoped to the user, so two users may
    // use the same id without colliding and one user cannot be charged twice.
    const existing = this.ledger.findReservationByRequest({ userId, requestId });
    if (existing) {
      return Object.freeze({
        allowed: false,
        code: "DUPLICATE_MODEL_REQUEST",
        message: MESSAGES.DUPLICATE,
        modelCalls: 0,
        existingState: existing.state,
      });
    }

    const outputCap = Math.min(
      Number(maxOutputTokens || this.policy.maxOutputTokensPerRequest),
      this.policy.maxOutputTokensPerRequest,
    );
    assertPositiveInteger("maxOutputTokens", outputCap);
    const inputUpperBound = estimateInputTokenUpperBound(messages);
    const reservedTokens = inputUpperBound + outputCap;
    if (reservedTokens > this.policy.maxReservedTokensPerRequest) {
      return Object.freeze({
        allowed: false,
        code: "REQUEST_TOKEN_BUDGET_EXCEEDED",
        message: MESSAGES.REQUEST_TOO_LARGE,
        modelCalls: 0,
        reservedTokens,
        inputUpperBound,
        outputCap,
      });
    }

    const result = this.ledger.reserveIfWithinLimits({
      reservationId: `mbr_${randomUUID()}`,
      requestId,
      userId,
      providerId,
      reservedTokens,
      limits: this.policy,
      epochMs: this.clock(),
    });
    if (!result.allowed) {
      return Object.freeze({
        ...result,
        message:
          result.code === "DUPLICATE_MODEL_REQUEST"
            ? MESSAGES.DUPLICATE
            : MESSAGES.OVER_BUDGET,
        inputUpperBound,
        outputCap,
      });
    }
    return Object.freeze({
      allowed: true,
      code: "OK",
      reservationId: result.reservationId,
      reservedTokens,
      inputUpperBound,
      outputCap,
      warning:
        result.utilizationRatio >= this.policy.softWarningRatio
          ? MESSAGES.SOFT_WARNING
          : null,
      utilizationRatio: result.utilizationRatio,
      modelCalls: 0,
    });
  }

  settle({ reservationId, providerId, rawUsage }) {
    const normalized = normalizeProviderUsage(providerId, rawUsage);
    if (!normalized.reported) {
      // Missing usage charges the full reservation: never zero.
      const row = this.ledger.settle({
        reservationId,
        inputTokens: null,
        outputTokens: null,
        totalTokens: null,
        usageReported: false,
        chargeMode: "reserved",
        epochMs: this.clock(),
      });
      return Object.freeze({
        ...normalized,
        chargedTokens: row.totalTokens,
        fuseAccounting: "reservation_fallback",
      });
    }
    const row = this.ledger.settle({
      reservationId,
      inputTokens: normalized.inputTokens,
      outputTokens: normalized.outputTokens,
      totalTokens: normalized.totalTokens,
      usageReported: true,
      chargeMode: "actual",
      epochMs: this.clock(),
    });
    return Object.freeze({
      ...normalized,
      chargedTokens: row.totalTokens,
      fuseAccounting: "provider_reported",
    });
  }

  // The transport outcome is unknown (timeout, socket error): the request may
  // have reached the provider, so charge conservatively rather than release.
  settleUnknown({ reservationId, providerId }) {
    const normalized = normalizeProviderUsage(providerId, null);
    const row = this.ledger.settle({
      reservationId,
      inputTokens: null,
      outputTokens: null,
      totalTokens: null,
      usageReported: false,
      chargeMode: "reserved",
      epochMs: this.clock(),
    });
    return Object.freeze({
      ...normalized,
      chargedTokens: row.totalTokens,
      fuseAccounting: "transport_uncertain_reserved",
    });
  }

  // Only used when the provider certainly did no work (rejected credentials,
  // refused before dispatch), so releasing costs the user nothing.
  releaseNoCharge({ reservationId, reason }) {
    return this.ledger.release({ reservationId, reason, epochMs: this.clock() });
  }
}

module.exports = {
  DEFAULT_BUDGET,
  MESSAGES,
  ModelBudgetError,
  ModelBudgetGuard,
  validateBudgetPolicy,
};
