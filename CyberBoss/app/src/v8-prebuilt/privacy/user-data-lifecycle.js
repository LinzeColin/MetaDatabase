'use strict';
const crypto = require('node:crypto');
const { buildDeletionPlan, validateDeletionReceipts } = require('./deletion-plan');

function hashJson(value) {
  return crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
}

function buildUserExportManifest({ userId, generatedAt, factRefs = [], objectRefs = [] }) {
  if (!/^usr_[A-Za-z0-9_-]{20,}$/.test(userId || '')) throw new TypeError('valid userId required');
  const timestamp = new Date(generatedAt);
  if (Number.isNaN(timestamp.getTime())) throw new TypeError('valid generatedAt required');
  const facts = [...new Set(factRefs.map(String))].sort();
  const objects = [...new Set(objectRefs.map(String))].sort();
  const payload = { schemaVersion: 1, userId, generatedAt: timestamp.toISOString(), factRefs: facts, objectRefs: objects };
  return Object.freeze({ ...payload, manifestSha256: hashJson(payload) });
}

async function executeDeletion({ userId, requestId, receiptStore, handlers }) {
  if (!receiptStore || typeof receiptStore.get !== 'function' || typeof receiptStore.put !== 'function') throw new TypeError('receiptStore required');
  const plan = buildDeletionPlan({ userId, requestId });
  const receipts = [];
  for (const step of plan) {
    const existing = await receiptStore.get({ userId, idempotencyKey: step.idempotencyKey });
    if (existing && existing.status === 'succeeded' && existing.userId === userId) {
      receipts.push(existing);
      continue;
    }
    const handler = handlers && handlers[step.action];
    if (typeof handler !== 'function') throw Object.assign(new Error('DELETION_HANDLER_MISSING'), { code: 'DELETION_HANDLER_MISSING', action: step.action });
    const result = await handler({ userId, requestId, idempotencyKey: step.idempotencyKey });
    const receipt = Object.freeze({ id: step.id, userId, action: step.action, status: 'succeeded', resultHash: hashJson(result || null) });
    await receiptStore.put({ userId, idempotencyKey: step.idempotencyKey, receipt });
    receipts.push(receipt);
  }
  if (!validateDeletionReceipts(plan, receipts)) throw Object.assign(new Error('DELETION_RECEIPTS_INCOMPLETE'), { code: 'DELETION_RECEIPTS_INCOMPLETE' });
  return Object.freeze({ ok: true, userId, requestId, receipts });
}

module.exports = { buildUserExportManifest, executeDeletion, hashJson };
