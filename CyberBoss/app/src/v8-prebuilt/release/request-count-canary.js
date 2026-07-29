'use strict';

const DEFAULT_CANARY = Object.freeze({ minRequests: 20, maxErrorRatio: 0.05, maxP95Ms: 15_000 });

function evaluateRequestCountCanary(sample, thresholds = DEFAULT_CANARY) {
  const total = Number(sample && sample.totalRequests);
  const errors = Number(sample && sample.errorCount);
  const p95 = Number(sample && sample.p95Ms);
  const privacy = Number(sample && sample.privacyViolations || 0);
  const duplicate = Number(sample && sample.duplicateSideEffects || 0);
  if (![total, errors, p95, privacy, duplicate].every((value) => Number.isFinite(value) && value >= 0)) {
    return Object.freeze({ decision: 'rollback', reasonCode: 'CANARY_MEASUREMENT_INVALID', modelCalls: 0 });
  }
  if (privacy > 0) return Object.freeze({ decision: 'rollback', reasonCode: 'PRIVACY_VIOLATION', modelCalls: 0 });
  if (duplicate > 0) return Object.freeze({ decision: 'rollback', reasonCode: 'DUPLICATE_SIDE_EFFECT', modelCalls: 0 });
  if (total < thresholds.minRequests) return Object.freeze({ decision: 'continue_by_request_count', remainingRequests: thresholds.minRequests - total, modelCalls: 0 });
  const ratio = total === 0 ? 0 : errors / total;
  if (ratio > thresholds.maxErrorRatio) return Object.freeze({ decision: 'rollback', reasonCode: 'ERROR_RATIO_EXCEEDED', errorRatio: ratio, modelCalls: 0 });
  if (p95 > thresholds.maxP95Ms) return Object.freeze({ decision: 'rollback', reasonCode: 'LATENCY_EXCEEDED', p95Ms: p95, modelCalls: 0 });
  return Object.freeze({ decision: 'promote', reasonCode: 'CANARY_PASS', errorRatio: ratio, modelCalls: 0 });
}

module.exports = { DEFAULT_CANARY, evaluateRequestCountCanary };
