"use strict";

// CB-810 / AC-033: bounded, deterministic self-heal.
//
// Imports nothing, so a healing decision cannot reach a model. The decision is
// a function of the reason code, the health flag and the restart history — the
// same inputs always give the same answer.
//
// The failure this guards against is the restart storm: a process that dies on
// startup, gets restarted, dies again, and burns the host. The restart budget
// is counted inside a sliding window and, once exhausted, the policy stops
// restarting and asks for a human instead of trying harder.

// Failures a restart can plausibly fix. Anything else is isolated and reported
// rather than restarted, because restarting a corrupt database or a rejected
// credential just loses the evidence.
const RESTARTABLE = Object.freeze([
  "PROCESS_EXITED",
  "READYZ_FAILED",
  "LOOPBACK_RUNTIME_DOWN",
  "STALE_WORKER_LEASE",
]);

const ACTIONS = Object.freeze([
  "none",
  "restart_process_family",
  "stop_restart_loop_and_alert",
  "isolate_and_alert",
]);

const DEFAULT_POLICY = Object.freeze({
  maxRestarts: 3,
  windowMs: 15 * 60 * 1000,
  cooldownMs: 60 * 1000,
});

class SelfHealError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "SelfHealError";
    this.code = code;
    this.detail = detail;
  }
}

function recentRestarts(restartTimestamps, nowMs, windowMs) {
  if (!Array.isArray(restartTimestamps)) {
    throw new SelfHealError("SELF_HEAL_HISTORY_INVALID", "restartTimestamps");
  }
  return restartTimestamps.filter((value) => {
    const timestamp = Number(value);
    if (!Number.isFinite(timestamp)) {
      return false;
    }
    const age = nowMs - timestamp;
    // A future timestamp is a clock problem, not a restart that has not
    // happened yet: it is counted, so a skewed clock cannot buy extra restarts.
    return age <= windowMs;
  });
}

function decideSelfHeal(
  { reasonCode, healthy, nowMs, restartTimestamps = [] },
  policy = DEFAULT_POLICY,
) {
  const now = Number(nowMs);
  if (!Number.isFinite(now)) {
    throw new SelfHealError("SELF_HEAL_CLOCK_INVALID", "nowMs");
  }
  const limits = { ...DEFAULT_POLICY, ...(policy || {}) };
  if (
    !Number.isInteger(limits.maxRestarts) ||
    limits.maxRestarts < 0 ||
    !Number.isFinite(limits.windowMs) ||
    limits.windowMs <= 0
  ) {
    throw new SelfHealError("SELF_HEAL_POLICY_INVALID", "policy");
  }

  if (healthy === true) {
    return Object.freeze({ action: "none", reasonCode: "HEALTHY", modelCalls: 0 });
  }
  const code = typeof reasonCode === "string" && reasonCode.length > 0
    ? reasonCode
    : "UNKNOWN_FAILURE";
  if (!RESTARTABLE.includes(code)) {
    return Object.freeze({ action: "isolate_and_alert", reasonCode: code, modelCalls: 0 });
  }

  const recent = recentRestarts(restartTimestamps, now, limits.windowMs);
  if (recent.length >= limits.maxRestarts) {
    return Object.freeze({
      action: "stop_restart_loop_and_alert",
      reasonCode: "RESTART_BUDGET_EXHAUSTED",
      attemptsInWindow: recent.length,
      modelCalls: 0,
    });
  }
  // A restart inside the cooldown is not refused, it is deferred: restarting
  // twice in the same second only turns one failure into two.
  const lastRestart = recent.length > 0 ? Math.max(...recent.map(Number)) : null;
  if (lastRestart !== null && now - lastRestart < limits.cooldownMs) {
    return Object.freeze({
      action: "none",
      reasonCode: "RESTART_COOLDOWN",
      retryAfterMs: limits.cooldownMs - (now - lastRestart),
      modelCalls: 0,
    });
  }
  return Object.freeze({
    action: "restart_process_family",
    reasonCode: code,
    attempt: recent.length + 1,
    attemptsInWindow: recent.length,
    modelCalls: 0,
  });
}

module.exports = {
  ACTIONS,
  DEFAULT_POLICY,
  RESTARTABLE,
  SelfHealError,
  decideSelfHeal,
  recentRestarts,
};
