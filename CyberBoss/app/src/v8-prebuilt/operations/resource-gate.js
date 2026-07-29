'use strict';

const DEFAULT_THRESHOLDS = Object.freeze({
  minFreeMemoryBytes: 1_280 * 1024 * 1024,
  minFreeDiskBytes: 8 * 1024 * 1024 * 1024,
  minFreeInodes: 10_000,
  maxQueueDepth: 25,
  maxLoadRatio: 1.5,
});

function finiteNonNegative(value) {
  return Number.isFinite(Number(value)) && Number(value) >= 0;
}

function evaluateResourceGate(metrics, thresholds = DEFAULT_THRESHOLDS) {
  const required = ['freeMemoryBytes', 'freeDiskBytes', 'freeInodes', 'queueDepth', 'loadRatio'];
  const missing = required.filter((key) => !finiteNonNegative(metrics && metrics[key]));
  if (missing.length) return Object.freeze({ state: 'reject', reasonCode: 'RESOURCE_MEASUREMENT_UNAVAILABLE', missing, modelCalls: 0 });
  const checks = [
    ['freeMemoryBytes', 'MIN_FREE_MEMORY', 'minFreeMemoryBytes', 'reject'],
    ['freeDiskBytes', 'MIN_FREE_DISK', 'minFreeDiskBytes', 'reject'],
    ['freeInodes', 'MIN_FREE_INODES', 'minFreeInodes', 'reject'],
  ];
  for (const [metric, reasonCode, threshold] of checks) {
    if (Number(metrics[metric]) < Number(thresholds[threshold])) return Object.freeze({ state: 'reject', reasonCode, modelCalls: 0 });
  }
  if (Number(metrics.queueDepth) > Number(thresholds.maxQueueDepth)) return Object.freeze({ state: 'degraded', reasonCode: 'QUEUE_PRESSURE', modelCalls: 0 });
  if (Number(metrics.loadRatio) > Number(thresholds.maxLoadRatio)) return Object.freeze({ state: 'degraded', reasonCode: 'LOAD_PRESSURE', modelCalls: 0 });
  return Object.freeze({ state: 'allow', reasonCode: 'RESOURCE_OK', modelCalls: 0 });
}

module.exports = { DEFAULT_THRESHOLDS, evaluateResourceGate };
