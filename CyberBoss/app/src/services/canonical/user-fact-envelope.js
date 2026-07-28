"use strict";

// CB-800 / AC-030: the user-scoped canonical fact envelope.
//
// This module is a validator and normaliser, not a second fact store. Records
// it produces are handed to the existing sync_spool and the existing
// CanonicalSpoolCoordinator in ../canonical/canonical-sync.js, which remains
// the only long-term fact authority. Nothing here opens a table, a file or a
// remote connection of its own.
//
// The frozen data contract names six forbidden envelope fields. The starter
// reference only rejects them at the top level of the payload; a nested
// `{ meta: { prompt: "..." } }` walked straight through. Here the scan is
// recursive over keys AND values, so raw chat and secrets cannot reach the
// canonical area by being one level deeper.

const { createHash } = require("node:crypto");

// Frozen by machine/data_contract.json -> canonical_envelope_forbidden_fields.
const FORBIDDEN_FIELDS = Object.freeze([
  "raw_message",
  "raw_chat",
  "prompt",
  "response",
  "api_key",
  "secret",
]);

// Fields whose names differ from the frozen six but carry the same content.
// Rejecting these is additive protection, never a relaxation.
const FORBIDDEN_FIELD_ALIASES = Object.freeze([
  "raw_text",
  "message_text",
  "chat_log",
  "transcript",
  "completion",
  "system_prompt",
  "access_token",
  "refresh_token",
  "bearer_token",
  "password",
  "private_key",
  "credential",
  "wxid",
]);

// Value-level scan. A payload may carry an innocuously named field whose value
// is a live credential; the envelope refuses on the value alone.
const SECRET_VALUE_PATTERN =
  /-----BEGIN |\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b|\bAIza[A-Za-z0-9_-]{30,}\b|\bwxid_[A-Za-z0-9_-]+\b|\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b/i;

// Frozen by machine/data_contract.json -> canonical_sync.critical. These sync
// immediately; everything else waits for the daily batch.
const IMMEDIATE_TYPES = Object.freeze([
  "release.published",
  "incident.opened",
  "incident.resolved",
  "recovery.completed",
  "user.deleted",
  "user.export_completed",
  "security.credential_revoked",
  "security.credential_rotated",
  "backup.restored",
]);

const MAX_PAYLOAD_DEPTH = 6;
const MAX_PAYLOAD_KEYS = 64;
const MAX_STRING_LENGTH = 2_048;
const MAX_OBJECT_REFS = 256;
const USER_ID_PATTERN = /^usr_[A-Za-z0-9_-]{20,}$/;
const TYPE_PATTERN = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/;

class CanonicalEnvelopeError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "CanonicalEnvelopeError";
    this.code = code;
    // The detail is a field path, never a field value: an error message must
    // not become the leak the envelope just prevented.
    this.detail = detail;
  }
}

function stableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value === undefined ? null : value);
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function normalizedFieldName(key) {
  return String(key).toLowerCase().replace(/[^a-z0-9]/g, "_");
}

function assertFieldAllowed(key, path) {
  const normalized = normalizedFieldName(key);
  if (FORBIDDEN_FIELDS.includes(normalized)) {
    throw new CanonicalEnvelopeError("CANONICAL_RAW_CONTENT_FORBIDDEN", path);
  }
  if (FORBIDDEN_FIELD_ALIASES.includes(normalized)) {
    throw new CanonicalEnvelopeError("CANONICAL_RAW_CONTENT_FORBIDDEN", path);
  }
  // `user_api_key`, `vendor_secret`, `msg_raw_chat` and friends: a forbidden
  // name embedded in a longer name is still the same content.
  for (const forbidden of FORBIDDEN_FIELDS) {
    if (normalized.includes(forbidden)) {
      throw new CanonicalEnvelopeError("CANONICAL_RAW_CONTENT_FORBIDDEN", path);
    }
  }
}

// Recursive: every key and every string value in the payload is inspected,
// at every depth, before a fact is allowed to exist.
function scanPayload(value, path, depth) {
  if (depth > MAX_PAYLOAD_DEPTH) {
    throw new CanonicalEnvelopeError("CANONICAL_PAYLOAD_TOO_DEEP", path);
  }
  if (value === null || value === undefined) {
    return;
  }
  if (typeof value === "string") {
    if (value.length > MAX_STRING_LENGTH) {
      throw new CanonicalEnvelopeError("CANONICAL_PAYLOAD_STRING_TOO_LONG", path);
    }
    if (SECRET_VALUE_PATTERN.test(value)) {
      throw new CanonicalEnvelopeError("CANONICAL_SECRET_VALUE_FORBIDDEN", path);
    }
    return;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    if (typeof value === "number" && !Number.isFinite(value)) {
      throw new CanonicalEnvelopeError("CANONICAL_PAYLOAD_VALUE_INVALID", path);
    }
    return;
  }
  if (Array.isArray(value)) {
    if (value.length > MAX_PAYLOAD_KEYS) {
      throw new CanonicalEnvelopeError("CANONICAL_PAYLOAD_TOO_WIDE", path);
    }
    value.forEach((item, index) => scanPayload(item, `${path}[${index}]`, depth + 1));
    return;
  }
  if (typeof value !== "object") {
    throw new CanonicalEnvelopeError("CANONICAL_PAYLOAD_VALUE_INVALID", path);
  }
  const keys = Object.keys(value);
  if (keys.length > MAX_PAYLOAD_KEYS) {
    throw new CanonicalEnvelopeError("CANONICAL_PAYLOAD_TOO_WIDE", path);
  }
  for (const key of keys) {
    const childPath = path ? `${path}.${key}` : key;
    assertFieldAllowed(key, childPath);
    scanPayload(value[key], childPath, depth + 1);
  }
}

function normalizeObjectRefs(objectRefs) {
  if (!Array.isArray(objectRefs)) {
    throw new CanonicalEnvelopeError("CANONICAL_OBJECT_REFS_INVALID", "object_refs");
  }
  if (objectRefs.length > MAX_OBJECT_REFS) {
    throw new CanonicalEnvelopeError("CANONICAL_OBJECT_REFS_TOO_MANY", "object_refs");
  }
  const normalized = [...new Set(objectRefs.map((ref) => String(ref)))].sort();
  for (const ref of normalized) {
    if (!/^[A-Za-z0-9_./-]{1,300}$/.test(ref) || ref.includes("..")) {
      throw new CanonicalEnvelopeError("CANONICAL_OBJECT_REF_INVALID", "object_refs");
    }
  }
  return normalized;
}

function buildUserFact({
  userId,
  type,
  occurredAt,
  payload = {},
  objectRefs = [],
  sourceEventId,
}) {
  if (typeof userId !== "string" || !USER_ID_PATTERN.test(userId)) {
    throw new CanonicalEnvelopeError("CANONICAL_USER_ID_INVALID", "user_id");
  }
  if (typeof type !== "string" || !TYPE_PATTERN.test(type) || type.length > 80) {
    throw new CanonicalEnvelopeError("CANONICAL_TYPE_INVALID", "type");
  }
  const timestamp = new Date(occurredAt);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new CanonicalEnvelopeError("CANONICAL_OCCURRED_AT_INVALID", "occurred_at");
  }
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new CanonicalEnvelopeError("CANONICAL_PAYLOAD_INVALID", "payload");
  }
  scanPayload(payload, "payload", 0);

  const source = String(sourceEventId ?? "");
  if (!/^[A-Za-z0-9_.:-]{1,160}$/.test(source)) {
    throw new CanonicalEnvelopeError("CANONICAL_SOURCE_EVENT_ID_INVALID", "source_event_id");
  }

  const normalized = {
    schema_version: 1,
    domain: "CyberBoss",
    user_id: userId,
    type,
    occurred_at: timestamp.toISOString(),
    payload,
    object_refs: normalizeObjectRefs(objectRefs),
    source_event_id: source,
  };
  const contentHash = sha256(stableJson(normalized));
  return Object.freeze({
    ...normalized,
    fact_id: `cbf_${contentHash.slice(0, 32)}`,
    content_hash: contentHash,
    // Replaying the same source event produces the same key, so the canonical
    // area de-duplicates instead of growing a second copy of one fact.
    idempotency_key: `${userId}:${type}:${source}`,
    sync_priority: IMMEDIATE_TYPES.includes(type) ? "immediate" : "daily",
  });
}

// AC-030: ordinary facts go daily, critical facts go immediately, and a window
// with nothing new must not create a commit at all.
function planCanonicalSync(facts, {
  now,
  lastDailySyncAt = null,
  dailyIntervalMs = 24 * 60 * 60 * 1000,
} = {}) {
  if (!Array.isArray(facts)) {
    throw new CanonicalEnvelopeError("CANONICAL_FACTS_INVALID", "facts");
  }
  const current = new Date(now).getTime();
  if (!Number.isFinite(current)) {
    throw new CanonicalEnvelopeError("CANONICAL_CLOCK_INVALID", "now");
  }
  const last = lastDailySyncAt === null ? null : new Date(lastDailySyncAt).getTime();
  const dailyDue = last === null || !Number.isFinite(last) || current - last >= dailyIntervalMs;

  const seen = new Set();
  const immediate = [];
  const daily = [];
  let deferred = 0;
  let duplicates = 0;
  for (const fact of facts) {
    if (!fact || typeof fact !== "object" || !fact.idempotency_key) {
      throw new CanonicalEnvelopeError("CANONICAL_FACT_INVALID", "facts[]");
    }
    if (seen.has(fact.idempotency_key)) {
      duplicates += 1;
      continue;
    }
    seen.add(fact.idempotency_key);
    if (fact.sync_priority === "immediate") {
      immediate.push(fact);
    } else if (dailyDue) {
      daily.push(fact);
    } else {
      deferred += 1;
    }
  }
  const selected = immediate.length + daily.length;
  return Object.freeze({
    immediate: Object.freeze(immediate),
    daily: Object.freeze(daily),
    deferred_daily_count: deferred,
    duplicate_count: duplicates,
    daily_due: dailyDue,
    // The empty commit is forbidden outright, not merely discouraged.
    create_commit: selected > 0,
    reason: selected > 0
      ? (immediate.length > 0 ? "critical_event" : "daily_batch")
      : "no_new_facts",
  });
}

// A guard for callers: given a plan, refuse to hand an empty batch downstream.
function assertCommitAllowed(plan) {
  if (!plan || plan.create_commit !== true) {
    throw new CanonicalEnvelopeError("CANONICAL_EMPTY_COMMIT_FORBIDDEN", "plan");
  }
  return true;
}

// The same forbidden-field and secret-value scan the envelope applies, exposed
// so the canonical spool write path can refuse an event before it is staged.
// It is the identical code, not a second implementation of the same rule.
function assertPayloadSafe(value, path = "payload") {
  scanPayload(value, path, 0);
  return value;
}

module.exports = {
  CanonicalEnvelopeError,
  FORBIDDEN_FIELDS,
  assertPayloadSafe,
  FORBIDDEN_FIELD_ALIASES,
  IMMEDIATE_TYPES,
  MAX_PAYLOAD_DEPTH,
  SECRET_VALUE_PATTERN,
  assertCommitAllowed,
  buildUserFact,
  planCanonicalSync,
  sha256,
  stableJson,
};
