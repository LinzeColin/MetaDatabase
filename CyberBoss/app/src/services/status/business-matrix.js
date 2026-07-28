"use strict";

// CB-810 / AC-032: the business-line Status matrix.
//
// The matrix is the surface an operator looks at when something is wrong, so
// it is exactly the surface most likely to grow a convenient identifier. Every
// row is therefore checked twice before it can be published: the frozen field
// list must be present and complete, and both field names and field values are
// scanned recursively for anything that could identify a person.
//
// The scan fails closed. An unrecognised business line, a missing required
// field, an extra field, a forbidden name at any depth or a value matching a
// sensitive pattern all refuse the whole snapshot rather than dropping one row
// and publishing the rest — a partially redacted snapshot reads as complete.

const { createHash } = require("node:crypto");

// Frozen by machine/status_business_matrix.json.
const BUSINESS_LINES = Object.freeze([
  "wechat_channel",
  "user_registration_consent",
  "user_isolation",
  "secure_setup_portal",
  "ai_provider_connection",
  "four_source_import",
  "profile_memory",
  "timeline_diary_reminder",
  "canonical_sync",
  "r2_oci_objects",
  "backup_restore",
  "owner_codex_runtime",
  "release_rollback",
  "model_usage_budget_circuit",
]);

const REQUIRED_FIELDS = Object.freeze([
  "business_line",
  "stage",
  "state",
  "upstream",
  "downstream",
  "slo",
  "queue_depth",
  "oldest_job_seconds",
  "error_rate",
  "last_success_at",
  "last_recovery_at",
  "release",
  "rollback_release",
  "reason_code",
]);

const FORBIDDEN_FIELDS = Object.freeze([
  "wechat_id",
  "user_id",
  "name",
  "message",
  "prompt",
  "response",
  "api_key",
  "file_name",
  "profile",
  "object_key",
]);

// Additive protection over the frozen ten. These are the names the same data
// arrives under when someone adds a field without reading the contract.
//
// Note what is deliberately absent: the bare fragment "token". The frozen
// model-usage contract requires `reserved_tokens` and `charged_tokens`, so a
// blanket ban on the substring would forbid the very fields AC-048 mandates.
// The credential-bearing token names are listed individually instead.
const FORBIDDEN_FIELD_FRAGMENTS = Object.freeze([
  "wechat", "weixin", "wxid", "userid", "user_id", "sender", "person",
  "message", "prompt", "response", "api_key", "apikey", "filename",
  "file_name", "profile", "object_key", "objectkey", "secret",
  "password", "authorization", "credential", "email", "phone", "nickname",
  "avatar", "private_key",
  "access_token", "refresh_token", "session_token", "setup_token",
  "csrf_token", "auth_token", "bearer_token", "id_token", "api_token",
  "token_value", "token_hash", "token_secret", "token_raw",
]);

const FORBIDDEN_VALUE =
  /-----BEGIN |\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b|\bAIza[A-Za-z0-9_-]{30,}\b|\bwxid_[A-Za-z0-9_-]+\b|\busr_[A-Za-z0-9_-]{20,}\b|\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\/(?:root|home|Users)\//i;

const STATES = Object.freeze([
  "healthy",
  "degraded",
  "blocked",
  "activation_pending",
  "not_started",
]);
const MAX_SCAN_DEPTH = 8;
const SAFE_TEXT = /^[A-Za-z0-9 _.:+/-]{0,160}$/;

class StatusMatrixError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "StatusMatrixError";
    this.code = code;
    // A path or a field name, never a field value.
    this.detail = detail;
  }
}

function normalizedKey(key) {
  return String(key).toLowerCase().replace(/[^a-z0-9]/g, "_");
}

function assertKeyAllowed(key, path) {
  const normalized = normalizedKey(key);
  if (FORBIDDEN_FIELDS.includes(normalized)) {
    throw new StatusMatrixError("STATUS_FIELD_FORBIDDEN", path);
  }
  for (const fragment of FORBIDDEN_FIELD_FRAGMENTS) {
    if (normalized.includes(fragment)) {
      throw new StatusMatrixError("STATUS_FIELD_FORBIDDEN", path);
    }
  }
}

function assertNoSensitiveValues(value, path = "$", depth = 0) {
  if (depth > MAX_SCAN_DEPTH) {
    throw new StatusMatrixError("STATUS_SNAPSHOT_TOO_DEEP", path);
  }
  if (value === null || value === undefined) {
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new StatusMatrixError("STATUS_VALUE_INVALID", path);
    }
    return;
  }
  if (typeof value === "boolean") {
    return;
  }
  if (typeof value === "string") {
    if (FORBIDDEN_VALUE.test(value)) {
      throw new StatusMatrixError("STATUS_VALUE_FORBIDDEN", path);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoSensitiveValues(item, `${path}[${index}]`, depth + 1));
    return;
  }
  if (typeof value !== "object") {
    throw new StatusMatrixError("STATUS_VALUE_INVALID", path);
  }
  for (const [key, nested] of Object.entries(value)) {
    const childPath = `${path}.${key}`;
    assertKeyAllowed(key, childPath);
    assertNoSensitiveValues(nested, childPath, depth + 1);
  }
}

function requireSafeText(value, field, allowNull = true) {
  if (value === null || value === undefined) {
    if (allowNull) {
      return null;
    }
    throw new StatusMatrixError("STATUS_FIELD_MISSING", field);
  }
  const text = String(value);
  if (!SAFE_TEXT.test(text)) {
    throw new StatusMatrixError("STATUS_FIELD_UNSAFE", field);
  }
  return text;
}

function requireCount(value, field) {
  const count = Number(value);
  if (!Number.isFinite(count) || count < 0) {
    throw new StatusMatrixError("STATUS_FIELD_NOT_A_COUNT", field);
  }
  return count;
}

function requireLineList(value, field) {
  if (value === null || value === undefined) {
    return Object.freeze([]);
  }
  if (!Array.isArray(value)) {
    throw new StatusMatrixError("STATUS_FIELD_NOT_A_LIST", field);
  }
  const items = value.map((item) => String(item));
  for (const item of items) {
    if (!BUSINESS_LINES.includes(item)) {
      throw new StatusMatrixError("STATUS_DEPENDENCY_UNKNOWN", field);
    }
  }
  return Object.freeze([...items].sort());
}

function buildBusinessLine(line) {
  if (!line || typeof line !== "object" || Array.isArray(line)) {
    throw new StatusMatrixError("STATUS_LINE_INVALID", "line");
  }
  // Scan first: a forbidden field is refused before any of it is copied into
  // the output object.
  assertNoSensitiveValues(line, "$");

  const businessLine = String(line.business_line ?? "");
  if (!BUSINESS_LINES.includes(businessLine)) {
    throw new StatusMatrixError("STATUS_BUSINESS_LINE_UNKNOWN", "business_line");
  }
  const missing = REQUIRED_FIELDS.filter((field) => !Object.hasOwn(line, field));
  if (missing.length > 0) {
    throw new StatusMatrixError("STATUS_REQUIRED_FIELD_MISSING", missing.join(","));
  }
  const extra = Object.keys(line).filter((key) => !REQUIRED_FIELDS.includes(key));
  if (extra.length > 0) {
    throw new StatusMatrixError("STATUS_UNEXPECTED_FIELD", extra.join(","));
  }
  const state = String(line.state ?? "");
  if (!STATES.includes(state)) {
    throw new StatusMatrixError("STATUS_STATE_UNKNOWN", "state");
  }
  return Object.freeze({
    business_line: businessLine,
    stage: requireSafeText(line.stage, "stage", false),
    state,
    upstream: requireLineList(line.upstream, "upstream"),
    downstream: requireLineList(line.downstream, "downstream"),
    slo: requireSafeText(line.slo, "slo"),
    queue_depth: requireCount(line.queue_depth ?? 0, "queue_depth"),
    oldest_job_seconds: requireCount(line.oldest_job_seconds ?? 0, "oldest_job_seconds"),
    error_rate: requireCount(line.error_rate ?? 0, "error_rate"),
    last_success_at: requireSafeText(line.last_success_at, "last_success_at"),
    last_recovery_at: requireSafeText(line.last_recovery_at, "last_recovery_at"),
    release: requireSafeText(line.release, "release"),
    rollback_release: requireSafeText(line.rollback_release, "rollback_release"),
    reason_code: requireSafeText(line.reason_code, "reason_code"),
  });
}

// Every frozen business line must appear exactly once. A snapshot that quietly
// omits the line that is currently broken is worse than no snapshot.
function buildBusinessMatrix(lines) {
  if (!Array.isArray(lines)) {
    throw new StatusMatrixError("STATUS_LINES_INVALID", "lines");
  }
  const built = lines.map(buildBusinessLine);
  const seen = built.map((line) => line.business_line);
  const duplicates = seen.filter((name, index) => seen.indexOf(name) !== index);
  if (duplicates.length > 0) {
    throw new StatusMatrixError("STATUS_BUSINESS_LINE_DUPLICATED", duplicates.join(","));
  }
  const absent = BUSINESS_LINES.filter((name) => !seen.includes(name));
  if (absent.length > 0) {
    throw new StatusMatrixError("STATUS_BUSINESS_LINE_MISSING", absent.join(","));
  }
  return Object.freeze(
    [...built].sort((left, right) => left.business_line.localeCompare(right.business_line)),
  );
}

function buildStatusSnapshot({ version, generatedAt, lines, modelUsage = null }) {
  const timestamp = new Date(generatedAt);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new StatusMatrixError("STATUS_GENERATED_AT_INVALID", "generatedAt");
  }
  const payload = {
    schema_version: 1,
    product: "CyberBoss",
    version: requireSafeText(version, "version", false),
    generated_at: timestamp.toISOString(),
    business_lines: buildBusinessMatrix(lines),
    model_usage: modelUsage,
    // AC-033: the snapshot is a projection, and says so on its face.
    model_calls: 0,
  };
  // Final gate on the assembled document, including anything a caller passed
  // through modelUsage.
  assertNoSensitiveValues(payload, "$");
  return Object.freeze({
    ...payload,
    snapshot_sha256: createHash("sha256")
      .update(JSON.stringify(payload))
      .digest("hex"),
  });
}

module.exports = {
  BUSINESS_LINES,
  FORBIDDEN_FIELDS,
  FORBIDDEN_FIELD_FRAGMENTS,
  FORBIDDEN_VALUE,
  MAX_SCAN_DEPTH,
  REQUIRED_FIELDS,
  STATES,
  StatusMatrixError,
  assertKeyAllowed,
  assertNoSensitiveValues,
  buildBusinessLine,
  buildBusinessMatrix,
  buildStatusSnapshot,
};
