'use strict';

const RESTARTABLE = new Set(['PROCESS_EXITED', 'READYZ_FAILED', 'LOOPBACK_RUNTIME_DOWN', 'STALE_WORKER_LEASE']);

function decideSelfHeal({ reasonCode, healthy, nowMs, restartTimestamps = [] }, { maxRestarts = 3, windowMs = 15 * 60 * 1000 } = {}) {
  if (!Number.isFinite(nowMs)) throw new TypeError('valid nowMs required');
  if (healthy) return Object.freeze({ action: 'none', reasonCode: 'HEALTHY', modelCalls: 0 });
  if (!RESTARTABLE.has(reasonCode)) return Object.freeze({ action: 'isolate_and_alert', reasonCode: reasonCode || 'UNKNOWN_FAILURE', modelCalls: 0 });
  const recent = restartTimestamps.filter((value) => Number.isFinite(value) && nowMs - value >= 0 && nowMs - value <= windowMs);
  if (recent.length >= maxRestarts) return Object.freeze({ action: 'stop_restart_loop_and_alert', reasonCode: 'RESTART_BUDGET_EXHAUSTED', modelCalls: 0 });
  return Object.freeze({ action: 'restart_process_family', reasonCode, attempt: recent.length + 1, modelCalls: 0 });
}

module.exports = { RESTARTABLE, decideSelfHeal };
