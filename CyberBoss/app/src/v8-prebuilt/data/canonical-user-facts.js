'use strict';
const crypto = require('node:crypto');

const IMMEDIATE_TYPES = new Set([
  'release.published',
  'incident.opened',
  'incident.resolved',
  'recovery.completed',
  'user.deleted',
  'security.credential_revoked',
]);

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function buildCanonicalFact({ userId, type, occurredAt, payload = {}, objectRefs = [], sourceEventId }) {
  if (!/^usr_[A-Za-z0-9_-]{20,}$/.test(userId || '')) throw new TypeError('valid userId required');
  if (!/^[a-z][a-z0-9_.-]{2,80}$/.test(type || '')) throw new TypeError('valid type required');
  const timestamp = new Date(occurredAt);
  if (Number.isNaN(timestamp.getTime())) throw new TypeError('valid occurredAt required');
  if (Object.hasOwn(payload, 'raw_message') || Object.hasOwn(payload, 'prompt') || Object.hasOwn(payload, 'response') || Object.hasOwn(payload, 'api_key')) {
    throw Object.assign(new Error('CANONICAL_RAW_CONTENT_FORBIDDEN'), { code: 'CANONICAL_RAW_CONTENT_FORBIDDEN' });
  }
  const normalized = {
    schema_version: 1,
    domain: 'CyberBoss',
    user_id: userId,
    type,
    occurred_at: timestamp.toISOString(),
    payload,
    object_refs: [...new Set(objectRefs.map(String))].sort(),
    source_event_id: String(sourceEventId || ''),
  };
  if (!normalized.source_event_id) throw new TypeError('sourceEventId required');
  const contentHash = sha256(stableJson(normalized));
  return {
    ...normalized,
    fact_id: `cbf_${contentHash.slice(0, 32)}`,
    content_hash: contentHash,
    idempotency_key: `${userId}:${type}:${normalized.source_event_id}`,
    sync_priority: IMMEDIATE_TYPES.has(type) ? 'immediate' : 'daily',
  };
}

function planCanonicalSync(facts, { now, lastDailySyncAt = null, dailyIntervalMs = 24 * 60 * 60 * 1000 } = {}) {
  const current = new Date(now).getTime();
  if (!Number.isFinite(current)) throw new TypeError('valid now required');
  const last = lastDailySyncAt === null ? null : new Date(lastDailySyncAt).getTime();
  const dailyDue = last === null || !Number.isFinite(last) || current - last >= dailyIntervalMs;
  const immediate = [];
  const daily = [];
  for (const fact of facts) {
    if (fact.sync_priority === 'immediate') immediate.push(fact);
    else if (dailyDue) daily.push(fact);
  }
  return {
    immediate,
    daily,
    deferred_daily_count: dailyDue ? 0 : facts.filter((fact) => fact.sync_priority !== 'immediate').length,
    create_commit: immediate.length + daily.length > 0,
  };
}

module.exports = { IMMEDIATE_TYPES, stableJson, buildCanonicalFact, planCanonicalSync };
