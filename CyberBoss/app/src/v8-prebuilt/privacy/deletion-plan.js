'use strict';

const ORDER = Object.freeze([
  'suspend_user',
  'revoke_web_sessions',
  'release_user_seat',
  'cancel_pending_jobs',
  'delete_r2_user_objects',
  'delete_search_and_profile_projections',
  'anonymize_token_reservation_identity',
  'write_private_database_tombstone',
  'destroy_user_data_key',
  'mark_user_deleted',
]);

function buildDeletionPlan({ userId, requestId }) {
  if (!userId || !requestId) throw new TypeError('userId and requestId required');
  return ORDER.map((action, index) => ({
    id: `${requestId}:${String(index + 1).padStart(2, '0')}`,
    userId,
    action,
    dependsOn: index === 0 ? [] : [`${requestId}:${String(index).padStart(2, '0')}`],
    idempotencyKey: `${requestId}:${action}`,
  }));
}

function validateDeletionReceipts(plan, receipts) {
  const map = new Map(receipts.map((receipt) => [receipt.id, receipt]));
  for (const step of plan) {
    const receipt = map.get(step.id);
    if (!receipt || receipt.status !== 'succeeded' || receipt.userId !== step.userId) return false;
  }
  return true;
}

module.exports = { ORDER, buildDeletionPlan, validateDeletionReceipts };
