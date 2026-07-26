"use strict";

const JOB_TRANSITIONS = Object.freeze({
  received: Object.freeze(["queued", "rejected"]),
  queued: Object.freeze(["running", "expired"]),
  running: Object.freeze([
    "waiting_approval",
    "succeeded",
    "failed_retryable",
    "cancelled",
    "failed_terminal",
  ]),
  waiting_approval: Object.freeze(["running", "cancelled"]),
  failed_retryable: Object.freeze(["queued", "failed_terminal"]),
  succeeded: Object.freeze(["reply_pending"]),
  failed_terminal: Object.freeze(["reply_pending"]),
  cancelled: Object.freeze(["reply_pending"]),
  reply_pending: Object.freeze(["replied", "reply_failed"]),
  replied: Object.freeze(["canonical_pending"]),
  reply_failed: Object.freeze(["canonical_pending"]),
  canonical_pending: Object.freeze(["canonical_synced"]),
  expired: Object.freeze([]),
  rejected: Object.freeze([]),
  canonical_synced: Object.freeze([]),
});

const JOB_STATUSES = Object.freeze(Object.keys(JOB_TRANSITIONS));

class IllegalJobTransitionError extends Error {
  constructor(fromStatus, toStatus) {
    super(`illegal_job_transition:${fromStatus}->${toStatus}`);
    this.name = "IllegalJobTransitionError";
    this.code = "ILLEGAL_JOB_TRANSITION";
  }
}

function isJobStatus(status) {
  return (
    typeof status === "string" &&
    Object.prototype.hasOwnProperty.call(JOB_TRANSITIONS, status)
  );
}

function canTransition(fromStatus, toStatus) {
  return (
    isJobStatus(fromStatus) &&
    isJobStatus(toStatus) &&
    JOB_TRANSITIONS[fromStatus].includes(toStatus)
  );
}

function assertTransition(fromStatus, toStatus) {
  if (!canTransition(fromStatus, toStatus)) {
    throw new IllegalJobTransitionError(fromStatus, toStatus);
  }
  return true;
}

function transitionPairs() {
  return JOB_STATUSES.flatMap((fromStatus) =>
    JOB_TRANSITIONS[fromStatus].map((toStatus) => [fromStatus, toStatus]),
  );
}

module.exports = {
  JOB_STATUSES,
  JOB_TRANSITIONS,
  IllegalJobTransitionError,
  assertTransition,
  canTransition,
  isJobStatus,
  transitionPairs,
};
