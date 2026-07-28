"use strict";

// CB-830 / AC-036: the canary decides on request count, never on elapsed time.
//
// A time-based canary ("watch it for ten minutes") is unfalsifiable on a quiet
// system: ten minutes of no traffic looks exactly like ten minutes of healthy
// traffic. Counting requests means the decision is only ever made on evidence
// that actually arrived.
//
// Every unhealthy outcome rolls back immediately. There is no "warn and keep
// going" state, because the point of a canary is that the previous release is
// still there and switching back is cheap.

const DEFAULT_CANARY = Object.freeze({
  minRequests: 20,
  maxErrorRatio: 0.05,
  maxP95Ms: 15_000,
});

const DECISIONS = Object.freeze(["promote", "rollback", "continue_by_request_count"]);

const REQUIRED_FIELDS = Object.freeze([
  "totalRequests",
  "errorCount",
  "p95Ms",
]);

const OPTIONAL_COUNTERS = Object.freeze([
  "privacyViolations",
  "duplicateSideEffects",
]);

function finiteNonNegative(value) {
  if (value === null || value === undefined || typeof value === "boolean") {
    return false;
  }
  const number = Number(value);
  return Number.isFinite(number) && number >= 0;
}

function evaluateRequestCountCanary(sample, thresholds = DEFAULT_CANARY) {
  const limits = { ...DEFAULT_CANARY, ...(thresholds || {}) };
  if (
    !finiteNonNegative(limits.minRequests) ||
    !finiteNonNegative(limits.maxErrorRatio) ||
    !finiteNonNegative(limits.maxP95Ms)
  ) {
    return Object.freeze({
      decision: "rollback",
      reasonCode: "CANARY_THRESHOLD_INVALID",
      modelCalls: 0,
    });
  }
  const missing = REQUIRED_FIELDS.filter((field) => !finiteNonNegative(sample && sample[field]));
  const badCounters = OPTIONAL_COUNTERS.filter(
    (field) =>
      sample &&
      sample[field] !== undefined &&
      sample[field] !== null &&
      !finiteNonNegative(sample[field]),
  );
  if (missing.length > 0 || badCounters.length > 0) {
    // An unmeasured canary is not a passing canary.
    return Object.freeze({
      decision: "rollback",
      reasonCode: "CANARY_MEASUREMENT_INVALID",
      missing: Object.freeze([...missing, ...badCounters]),
      modelCalls: 0,
    });
  }

  const total = Number(sample.totalRequests);
  const errors = Number(sample.errorCount);
  const p95 = Number(sample.p95Ms);
  const privacy = Number(sample.privacyViolations ?? 0);
  const duplicate = Number(sample.duplicateSideEffects ?? 0);

  if (errors > total) {
    return Object.freeze({
      decision: "rollback",
      reasonCode: "CANARY_MEASUREMENT_INCONSISTENT",
      modelCalls: 0,
    });
  }
  // A single privacy violation or duplicate side effect rolls back regardless
  // of how good the other numbers are; neither is a rate to be tolerated.
  if (privacy > 0) {
    return Object.freeze({
      decision: "rollback",
      reasonCode: "PRIVACY_VIOLATION",
      privacyViolations: privacy,
      modelCalls: 0,
    });
  }
  if (duplicate > 0) {
    return Object.freeze({
      decision: "rollback",
      reasonCode: "DUPLICATE_SIDE_EFFECT",
      duplicateSideEffects: duplicate,
      modelCalls: 0,
    });
  }
  if (total < limits.minRequests) {
    return Object.freeze({
      decision: "continue_by_request_count",
      reasonCode: "INSUFFICIENT_REQUESTS",
      remainingRequests: limits.minRequests - total,
      modelCalls: 0,
    });
  }
  const errorRatio = total === 0 ? 0 : errors / total;
  if (errorRatio > limits.maxErrorRatio) {
    return Object.freeze({
      decision: "rollback",
      reasonCode: "ERROR_RATIO_EXCEEDED",
      errorRatio,
      modelCalls: 0,
    });
  }
  if (p95 > limits.maxP95Ms) {
    return Object.freeze({
      decision: "rollback",
      reasonCode: "LATENCY_EXCEEDED",
      p95Ms: p95,
      modelCalls: 0,
    });
  }
  return Object.freeze({
    decision: "promote",
    reasonCode: "CANARY_PASS",
    errorRatio,
    observedRequests: total,
    modelCalls: 0,
  });
}

// The receipt an operator keeps. It records the decision and the numbers that
// produced it, and nothing that could identify whose requests they were.
function buildCanaryReceipt({ releaseId, previousReleaseId, sample, decision, decidedAt }) {
  const timestamp = new Date(decidedAt);
  if (!Number.isFinite(timestamp.getTime())) {
    throw Object.assign(new Error("CANARY_DECIDED_AT_INVALID"), {
      code: "CANARY_DECIDED_AT_INVALID",
    });
  }
  if (!DECISIONS.includes(decision.decision)) {
    throw Object.assign(new Error("CANARY_DECISION_UNKNOWN"), {
      code: "CANARY_DECISION_UNKNOWN",
    });
  }
  return Object.freeze({
    schema: "cyberboss.request-count-canary-receipt.v1",
    releaseId: String(releaseId),
    previousReleaseId: String(previousReleaseId),
    decidedAt: timestamp.toISOString(),
    decision: decision.decision,
    reasonCode: decision.reasonCode,
    // Aggregate counts only: no user, no message, no request body.
    observed: Object.freeze({
      totalRequests: Number(sample.totalRequests ?? 0),
      errorCount: Number(sample.errorCount ?? 0),
      p95Ms: Number(sample.p95Ms ?? 0),
      privacyViolations: Number(sample.privacyViolations ?? 0),
      duplicateSideEffects: Number(sample.duplicateSideEffects ?? 0),
    }),
    timeBasedWait: false,
    modelCalls: 0,
  });
}

// Promotion and rollback both resolve to a release pointer. Rollback names the
// exact previous release rather than "the one before", so a second rollback
// cannot walk further back by accident.
function resolveReleasePointer({ decision, releaseId, previousReleaseId }) {
  if (decision.decision === "promote") {
    return Object.freeze({ action: "promote", pointTo: String(releaseId), modelCalls: 0 });
  }
  if (decision.decision === "rollback") {
    if (!previousReleaseId) {
      throw Object.assign(new Error("ROLLBACK_TARGET_MISSING"), {
        code: "ROLLBACK_TARGET_MISSING",
      });
    }
    return Object.freeze({
      action: "rollback",
      pointTo: String(previousReleaseId),
      stopCandidate: true,
      modelCalls: 0,
    });
  }
  return Object.freeze({ action: "hold", pointTo: null, modelCalls: 0 });
}

module.exports = {
  DECISIONS,
  DEFAULT_CANARY,
  OPTIONAL_COUNTERS,
  REQUIRED_FIELDS,
  buildCanaryReceipt,
  evaluateRequestCountCanary,
  resolveReleasePointer,
};
