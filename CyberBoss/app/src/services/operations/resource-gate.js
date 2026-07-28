"use strict";

// CB-810 / AC-033: the resource admission gate.
//
// Pure arithmetic over measured numbers. It imports nothing, so there is no
// path from an admission decision to a model call.
//
// The important behaviour is what happens when a measurement is missing. An
// unmeasured floor is not a satisfied floor: the gate rejects, because the
// alternative is admitting work onto a host whose disk state nobody knows.

const DEFAULT_THRESHOLDS = Object.freeze({
  minFreeMemoryBytes: 1_280 * 1024 * 1024,
  minFreeDiskBytes: 8 * 1024 * 1024 * 1024,
  minFreeInodes: 10_000,
  maxQueueDepth: 25,
  maxLoadRatio: 1.5,
});

const REQUIRED_METRICS = Object.freeze([
  "freeMemoryBytes",
  "freeDiskBytes",
  "freeInodes",
  "queueDepth",
  "loadRatio",
]);

// Ordered: the hard floors are checked before the pressure signals, so a host
// that is both out of disk and busy reports the floor, which is the one that
// must be fixed first.
const FLOORS = Object.freeze([
  Object.freeze({ metric: "freeMemoryBytes", threshold: "minFreeMemoryBytes", reasonCode: "MIN_FREE_MEMORY" }),
  Object.freeze({ metric: "freeDiskBytes", threshold: "minFreeDiskBytes", reasonCode: "MIN_FREE_DISK" }),
  Object.freeze({ metric: "freeInodes", threshold: "minFreeInodes", reasonCode: "MIN_FREE_INODES" }),
]);

const PRESSURE = Object.freeze([
  Object.freeze({ metric: "queueDepth", threshold: "maxQueueDepth", reasonCode: "QUEUE_PRESSURE" }),
  Object.freeze({ metric: "loadRatio", threshold: "maxLoadRatio", reasonCode: "LOAD_PRESSURE" }),
]);

// null and undefined are explicitly rejected before the numeric coercion:
// Number(null) is 0, so an absent measurement would otherwise read as a
// perfectly plausible "zero" and satisfy a pressure ceiling.
function isFiniteNonNegative(value) {
  if (value === null || value === undefined || typeof value === "boolean") {
    return false;
  }
  const number = Number(value);
  return Number.isFinite(number) && number >= 0;
}

function normalizeThresholds(thresholds) {
  const merged = { ...DEFAULT_THRESHOLDS, ...(thresholds || {}) };
  for (const [key, value] of Object.entries(merged)) {
    if (!isFiniteNonNegative(value)) {
      return null;
    }
    merged[key] = Number(value);
  }
  return merged;
}

function evaluateResourceGate(metrics, thresholds = DEFAULT_THRESHOLDS) {
  const limits = normalizeThresholds(thresholds);
  if (limits === null) {
    return Object.freeze({
      state: "reject",
      reasonCode: "RESOURCE_THRESHOLD_INVALID",
      modelCalls: 0,
    });
  }
  const missing = REQUIRED_METRICS.filter(
    (key) => !isFiniteNonNegative(metrics && metrics[key]),
  );
  if (missing.length > 0) {
    // Fail closed: an unmeasured floor is not a satisfied floor.
    return Object.freeze({
      state: "reject",
      reasonCode: "RESOURCE_MEASUREMENT_UNAVAILABLE",
      missing: Object.freeze([...missing]),
      modelCalls: 0,
    });
  }
  for (const { metric, threshold, reasonCode } of FLOORS) {
    if (Number(metrics[metric]) < limits[threshold]) {
      return Object.freeze({ state: "reject", reasonCode, modelCalls: 0 });
    }
  }
  for (const { metric, threshold, reasonCode } of PRESSURE) {
    if (Number(metrics[metric]) > limits[threshold]) {
      return Object.freeze({ state: "degraded", reasonCode, modelCalls: 0 });
    }
  }
  return Object.freeze({ state: "allow", reasonCode: "RESOURCE_OK", modelCalls: 0 });
}

// Admission for one unit of work: degraded admits nothing new, it only lets
// what is already running finish.
function admits(decision) {
  return decision.state === "allow";
}

module.exports = {
  DEFAULT_THRESHOLDS,
  FLOORS,
  PRESSURE,
  REQUIRED_METRICS,
  admits,
  evaluateResourceGate,
};
