"use strict";

// CB-800 / AC-029: the frozen deletion order.
//
// The order is not cosmetic. Access is cut before data is touched, so nothing
// can be written back mid-deletion; objects and projections go before the
// tombstone, so the tombstone is only written once there is nothing left to
// describe; the key is destroyed second-to-last, because after that step no
// later step can read anything it might have needed.

const ORDER = Object.freeze([
  "suspend_user",
  "revoke_web_sessions",
  "revoke_provider_credentials",
  "cancel_pending_jobs",
  "delete_r2_user_objects",
  "delete_search_and_profile_projections",
  "write_private_database_tombstone",
  "destroy_user_data_key",
  "mark_user_deleted",
]);

// Steps that cannot be undone once they have succeeded. The CB-800 rollback
// plan says a completed crypto-shred is never reversed; encoding that here
// means a resumed run can recognise it rather than rely on an operator
// remembering.
const IRREVERSIBLE_ACTIONS = Object.freeze([
  "delete_r2_user_objects",
  "destroy_user_data_key",
]);

const REQUEST_ID_PATTERN = /^[A-Za-z0-9_.:-]{8,120}$/;

class DeletionPlanError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "DeletionPlanError";
    this.code = code;
    this.detail = detail;
  }
}

function stepId(requestId, index) {
  return `${requestId}:${String(index + 1).padStart(2, "0")}`;
}

function buildDeletionPlan({ userId, requestId }) {
  if (typeof userId !== "string" || !/^usr_[A-Za-z0-9_-]{20,}$/.test(userId)) {
    throw new DeletionPlanError("DELETION_USER_ID_INVALID", "userId");
  }
  if (typeof requestId !== "string" || !REQUEST_ID_PATTERN.test(requestId)) {
    throw new DeletionPlanError("DELETION_REQUEST_ID_INVALID", "requestId");
  }
  return Object.freeze(
    ORDER.map((action, index) =>
      Object.freeze({
        id: stepId(requestId, index),
        sequence: index + 1,
        userId,
        action,
        dependsOn: index === 0 ? Object.freeze([]) : Object.freeze([stepId(requestId, index - 1)]),
        // The idempotency key carries the user, so a receipt from one user's
        // request can never satisfy another user's step.
        idempotencyKey: `${userId}:${requestId}:${action}`,
        irreversible: IRREVERSIBLE_ACTIONS.includes(action),
      }),
    ),
  );
}

// A plan is only complete when every step has a succeeded receipt belonging to
// the same user, in the same order. A missing or foreign receipt fails closed.
function validateDeletionReceipts(plan, receipts) {
  if (!Array.isArray(plan) || !Array.isArray(receipts)) {
    return false;
  }
  const byId = new Map(receipts.map((receipt) => [receipt && receipt.id, receipt]));
  for (const step of plan) {
    const receipt = byId.get(step.id);
    if (!receipt) {
      return false;
    }
    if (receipt.status !== "succeeded") {
      return false;
    }
    if (receipt.userId !== step.userId) {
      return false;
    }
    if (receipt.action !== step.action) {
      return false;
    }
  }
  return true;
}

// Where a partially-completed request stopped, so a resume starts at the right
// step instead of at the beginning.
function resumePoint(plan, receipts) {
  const byKey = new Map(
    (Array.isArray(receipts) ? receipts : []).map((receipt) => [receipt && receipt.id, receipt]),
  );
  for (const step of plan) {
    const receipt = byKey.get(step.id);
    if (!receipt || receipt.status !== "succeeded") {
      return Object.freeze({
        complete: false,
        nextAction: step.action,
        nextSequence: step.sequence,
        // Once the key is gone the request must be finished, never restarted.
        pastIrreversible: plan
          .slice(0, step.sequence - 1)
          .some((prior) => prior.irreversible && byKey.get(prior.id)?.status === "succeeded"),
      });
    }
  }
  return Object.freeze({
    complete: true,
    nextAction: null,
    nextSequence: null,
    pastIrreversible: true,
  });
}

module.exports = {
  DeletionPlanError,
  IRREVERSIBLE_ACTIONS,
  ORDER,
  buildDeletionPlan,
  resumePoint,
  validateDeletionReceipts,
};
