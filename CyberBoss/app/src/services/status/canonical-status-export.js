const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const PRODUCT_VERSION = "v0.0.0.5";
const STATUS_SCHEMA = "cyberboss.status.v2";
const COMPONENT_IDS = Object.freeze([
  "process",
  "wechat_poll",
  "wechat_send",
  "runtime",
  "e2e",
  "queue",
  "canonical",
  "timeline",
  "r2",
  "oci",
  "resources",
  "self_heal",
]);
const COMPONENT_STATES = new Set([
  "healthy",
  "degraded",
  "activation_pending",
  "failed",
  "unknown",
  "disabled",
]);
const ADAPTER_STATES = new Set([
  "verified",
  "activation_pending",
  "hazard_blocked",
  "failed",
  "disabled",
]);
const ADAPTER_IDS = Object.freeze([
  "private_database",
  "r2",
  "cloudflare_access",
  "oci",
  "timeline",
  "global_status",
]);
const METRIC_KEYS = Object.freeze([
  "queue_depth",
  "oldest_job_age_seconds",
  "outbox_pending",
  "canonical_pending",
  "control_plane_llm_calls_total",
  "business_runtime_model_calls_total",
  "self_heal_agent_invocations_total",
  "memory_available_bytes",
  "disk_available_bytes",
]);
const FORBIDDEN_KEY_FRAGMENTS = Object.freeze([
  "token",
  "secret",
  "password",
  "authorization",
  "prompt",
  "message",
  "thread",
  "account",
  "private_key",
  "auth",
  "path",
  "filename",
]);
const FORBIDDEN_VALUE = /-----BEGIN|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|\bwxid_[A-Za-z0-9_-]+\b|\bBearer\s+[A-Za-z0-9._~-]{12,}|\/(?:root|home|etc)\//i;
const GLOBAL_STATUS_ADAPTER_PATH = path.resolve(
  __dirname,
  "../../../../docs/product_design/v0.0.0.4/implementation-kit/status/global-status-adapter.js",
);

class CanonicalStatusError extends Error {
  constructor(code) {
    super(code);
    this.name = "CanonicalStatusError";
    this.code = code;
  }
}

function buildRedactedStatusSnapshot({
  generatedAt,
  sourceCommit,
  runtimeSnapshot = {},
  components = {},
  metrics = {},
  adapters = {},
  release = {},
  previousSnapshot = null,
} = {}) {
  const generated = normalizeTimestamp(generatedAt);
  const commit = normalizeCommit(sourceCommit);
  if (!generated || !commit) {
    throw new CanonicalStatusError("STATUS_REQUIRED_FACT_INVALID");
  }
  rejectSensitiveValue(runtimeSnapshot);
  rejectSensitiveValue(components);
  rejectSensitiveValue(metrics);
  rejectSensitiveValue(adapters);
  rejectSensitiveValue(release);

  const normalizedComponents = normalizeComponents(components, runtimeSnapshot);
  const normalizedMetrics = normalizeMetrics(metrics);
  const normalizedAdapters = normalizeAdapters(adapters);
  const normalizedRelease = normalizeRelease(release, commit);
  const overall = calculateOverall(normalizedComponents);
  const basis = {
    schema_version: STATUS_SCHEMA,
    generated_at: generated,
    source_commit: commit,
    overall,
    components: normalizedComponents,
    metrics: normalizedMetrics,
    adapters: normalizedAdapters,
    release: normalizedRelease,
  };
  const snapshot = {
    ...basis,
    generation_id: createGenerationId(generated, basis),
  };
  assertStatusSnapshot(snapshot);
  if (previousSnapshot) {
    assertStatusSnapshot(previousSnapshot);
    assertNewerGeneration(previousSnapshot, snapshot);
  }
  return Object.freeze(cloneJson(snapshot));
}

function writeStatusSnapshotAtomic({ snapshot, outputPath, crashPoint = "" } = {}) {
  assertStatusSnapshot(snapshot);
  const output = resolveOutputPath(outputPath);
  const previous = fs.existsSync(output) ? readStatusSnapshot(output) : null;
  if (previous) {
    assertNewerGeneration(previous, snapshot);
  }
  const payload = Buffer.from(`${stableJson(snapshot)}\n`, "utf8");
  atomicWriteJson({ output, payload, crashPoint, failurePrefix: "STATUS_SNAPSHOT" });
  return Object.freeze({
    generationId: snapshot.generation_id,
    sha256: sha256(payload),
    overall: snapshot.overall,
  });
}

function writeGlobalStatusRowAtomic({ row, outputPath, crashPoint = "" } = {}) {
  assertGlobalStatusRow(row);
  const output = resolveOutputPath(outputPath);
  if (fs.existsSync(output)) {
    const previous = readGlobalStatusRow(output);
    assertNewerGlobalRow(previous, row);
  }
  const payload = Buffer.from(`${stableJson(row)}\n`, "utf8");
  atomicWriteJson({ output, payload, crashPoint, failurePrefix: "STATUS_ROW" });
  return Object.freeze({
    generationId: row.generation_id,
    sha256: sha256(payload),
    status: row.status,
  });
}

function readStatusSnapshot(filePath) {
  const resolved = resolveExistingFile(filePath, "STATUS_SNAPSHOT_UNAVAILABLE");
  let snapshot;
  try {
    snapshot = JSON.parse(fs.readFileSync(resolved, "utf8"));
  } catch {
    throw new CanonicalStatusError("STATUS_SNAPSHOT_INVALID");
  }
  assertStatusSnapshot(snapshot);
  return Object.freeze(cloneJson(snapshot));
}

function buildGlobalStatusRow({ snapshot, observedAt, maxAgeSeconds = 120 } = {}) {
  assertStatusSnapshot(snapshot);
  const observed = normalizeTimestamp(observedAt);
  if (!observed) {
    throw new CanonicalStatusError("STATUS_OBSERVED_AT_REQUIRED");
  }
  const adapter = loadExistingGlobalStatusAdapter();
  const row = adapter.buildRow(buildLegacyCollectorSnapshot(snapshot), {
    now: new Date(observed),
    maxAgeSeconds: normalizeMaxAge(maxAgeSeconds),
  });
  const redacted = {
    ...row,
    generation_id: snapshot.generation_id,
    agent: "无",
    notify: "无",
  };
  assertGlobalStatusRow(redacted);
  return Object.freeze(cloneJson(redacted));
}

function normalizeComponents(overrides, runtimeSnapshot) {
  assertPlainObject(overrides, "STATUS_COMPONENTS_INVALID");
  assertAllowedKeys(overrides, new Set(COMPONENT_IDS), "STATUS_COMPONENT_UNKNOWN");
  const defaults = deriveDefaultComponents(runtimeSnapshot);
  return Object.fromEntries(COMPONENT_IDS.map((id) => [
    id,
    normalizeComponent(overrides[id] === undefined ? defaults[id] : overrides[id]),
  ]));
}

function deriveDefaultComponents(runtimeSnapshot) {
  const source = runtimeSnapshot && typeof runtimeSnapshot === "object" ? runtimeSnapshot : {};
  const healthy = source.healthy === true;
  const ready = source.ready === true;
  const supervised = source.process_family?.supervised === true;
  const runtimeProvider = normalizeProviderState(source.providers?.runtime);
  const channelProvider = normalizeProviderState(source.providers?.channel);
  const runtimeFailed = source.components?.runtime === false;
  const channelFailed = source.components?.channel === false;
  return {
    process: component(healthy && supervised ? "healthy" : "failed", healthy ? "process_not_supervised" : "process_unhealthy"),
    wechat_poll: providerComponent(channelProvider, channelFailed, "wechat_poll"),
    wechat_send: providerComponent(channelProvider, channelFailed, "wechat_send"),
    runtime: providerComponent(runtimeProvider, runtimeFailed, "runtime"),
    e2e: component(
      ready && runtimeProvider === "verified" && channelProvider === "verified" ? "healthy" : "activation_pending",
      ready ? "e2e_activation_pending" : "e2e_not_ready",
    ),
    queue: component("unknown", "queue_not_observed"),
    canonical: component("activation_pending", "canonical_activation_pending"),
    timeline: component("activation_pending", "timeline_activation_pending"),
    r2: component("activation_pending", "r2_hazard_blocked"),
    oci: component("activation_pending", "oci_activation_pending"),
    resources: component("unknown", "resources_not_observed"),
    self_heal: component("disabled", "self_heal_not_enabled"),
  };
}

function providerComponent(providerState, failed, prefix) {
  if (failed) {
    return component("failed", `${prefix}_unhealthy`);
  }
  if (providerState === "verified") {
    return component("healthy", `${prefix}_verified`);
  }
  if (providerState === "activation_pending" || providerState === "simulator_verified") {
    return component("activation_pending", `${prefix}_activation_pending`);
  }
  return component("unknown", `${prefix}_not_observed`);
}

function component(state, reasonCode, ageSeconds = null) {
  return { state, reason_code: reasonCode, age_seconds: ageSeconds };
}

function normalizeComponent(value) {
  assertPlainObject(value, "STATUS_COMPONENT_INVALID");
  assertAllowedKeys(value, new Set(["state", "reason_code", "age_seconds"]), "STATUS_COMPONENT_FIELD_UNKNOWN");
  const state = normalizeText(value.state);
  const reasonCode = normalizeText(value.reason_code);
  const ageSeconds = normalizeOptionalInteger(value.age_seconds);
  if (
    !COMPONENT_STATES.has(state)
    || !/^[a-z][a-z0-9_.-]{0,95}$/.test(reasonCode)
    || FORBIDDEN_KEY_FRAGMENTS.some((fragment) => reasonCode.includes(fragment))
  ) {
    throw new CanonicalStatusError("STATUS_COMPONENT_INVALID");
  }
  rejectSensitiveValue(reasonCode);
  return { state, reason_code: reasonCode, age_seconds: ageSeconds };
}

function normalizeMetrics(value) {
  assertPlainObject(value, "STATUS_METRICS_INVALID");
  assertAllowedKeys(value, new Set(METRIC_KEYS), "STATUS_METRIC_UNKNOWN");
  const metrics = {
    queue_depth: normalizeNonNegativeInteger(value.queue_depth, 0),
    oldest_job_age_seconds: normalizeOptionalInteger(value.oldest_job_age_seconds),
    outbox_pending: normalizeNonNegativeInteger(value.outbox_pending, 0),
    canonical_pending: normalizeNonNegativeInteger(value.canonical_pending, 0),
    control_plane_llm_calls_total: normalizeNonNegativeInteger(value.control_plane_llm_calls_total, 0),
    business_runtime_model_calls_total: normalizeNonNegativeInteger(value.business_runtime_model_calls_total, 0),
    self_heal_agent_invocations_total: normalizeNonNegativeInteger(value.self_heal_agent_invocations_total, 0),
    memory_available_bytes: normalizeOptionalInteger(value.memory_available_bytes),
    disk_available_bytes: normalizeOptionalInteger(value.disk_available_bytes),
  };
  if (metrics.control_plane_llm_calls_total !== 0 || metrics.self_heal_agent_invocations_total !== 0) {
    throw new CanonicalStatusError("STATUS_ZERO_AGENT_COUNTER_VIOLATION");
  }
  return metrics;
}

function normalizeAdapters(value) {
  assertPlainObject(value, "STATUS_ADAPTERS_INVALID");
  assertAllowedKeys(value, new Set(ADAPTER_IDS), "STATUS_ADAPTER_UNKNOWN");
  const defaults = {
    private_database: "activation_pending",
    r2: "hazard_blocked",
    cloudflare_access: "activation_pending",
    oci: "activation_pending",
    timeline: "activation_pending",
    global_status: "activation_pending",
  };
  return Object.fromEntries(ADAPTER_IDS.map((id) => {
    const state = normalizeText(value[id] === undefined ? defaults[id] : value[id]);
    if (!ADAPTER_STATES.has(state)) {
      throw new CanonicalStatusError("STATUS_ADAPTER_INVALID");
    }
    return [id, state];
  }));
}

function normalizeRelease(value, sourceCommit) {
  assertPlainObject(value, "STATUS_RELEASE_INVALID");
  assertAllowedKeys(value, new Set(["version", "commit", "slot", "rollback_ready"]), "STATUS_RELEASE_FIELD_UNKNOWN");
  const version = normalizeText(value.version || PRODUCT_VERSION);
  const commit = normalizeCommit(value.commit || sourceCommit);
  const slot = normalizeText(value.slot || "none");
  const rollbackReady = value.rollback_ready === true;
  if (version !== PRODUCT_VERSION || !commit || !["current", "candidate", "previous", "none"].includes(slot)) {
    throw new CanonicalStatusError("STATUS_RELEASE_INVALID");
  }
  return { version, commit, slot, rollback_ready: rollbackReady };
}

function calculateOverall(components) {
  const states = Object.values(components).map((componentValue) => componentValue.state);
  if (states.includes("failed")) {
    return "failed";
  }
  if (states.includes("degraded")) {
    return "degraded";
  }
  if (states.includes("unknown")) {
    return "unknown";
  }
  if (states.includes("activation_pending") || states.includes("disabled")) {
    return "activation_pending";
  }
  return "healthy";
}

function createGenerationId(generatedAt, basis) {
  const milliseconds = Date.parse(generatedAt);
  if (!Number.isSafeInteger(milliseconds) || milliseconds < 0) {
    throw new CanonicalStatusError("STATUS_GENERATION_INVALID");
  }
  const timestamp = milliseconds.toString(16).padStart(13, "0");
  if (timestamp.length !== 13) {
    throw new CanonicalStatusError("STATUS_GENERATION_INVALID");
  }
  return `${timestamp}${sha256(Buffer.from(stableJson(basis), "utf8")).slice(0, 11)}`;
}

function assertStatusSnapshot(snapshot) {
  assertPlainObject(snapshot, "STATUS_SNAPSHOT_INVALID");
  const expected = new Set([
    "schema_version",
    "generation_id",
    "generated_at",
    "source_commit",
    "overall",
    "components",
    "metrics",
    "adapters",
    "release",
  ]);
  assertExactKeys(snapshot, expected, "STATUS_SNAPSHOT_SCHEMA_INVALID");
  if (
    snapshot.schema_version !== STATUS_SCHEMA
    || !/^[a-f0-9]{24}$/.test(normalizeText(snapshot.generation_id))
    || !normalizeTimestamp(snapshot.generated_at)
    || !normalizeCommit(snapshot.source_commit)
    || !["healthy", "degraded", "activation_pending", "failed", "unknown"].includes(snapshot.overall)
  ) {
    throw new CanonicalStatusError("STATUS_SNAPSHOT_SCHEMA_INVALID");
  }
  const components = normalizeComponents(snapshot.components, {});
  const metrics = normalizeMetrics(snapshot.metrics);
  const adapters = normalizeAdapters(snapshot.adapters);
  const release = normalizeRelease(snapshot.release, snapshot.source_commit);
  if (
    snapshot.overall !== calculateOverall(components)
    || stableJson(components) !== stableJson(snapshot.components)
    || stableJson(metrics) !== stableJson(snapshot.metrics)
    || stableJson(adapters) !== stableJson(snapshot.adapters)
    || stableJson(release) !== stableJson(snapshot.release)
  ) {
    throw new CanonicalStatusError("STATUS_SNAPSHOT_SCHEMA_INVALID");
  }
}

function assertGlobalStatusRow(row) {
  assertPlainObject(row, "STATUS_GLOBAL_ROW_INVALID");
  const required = ["name", "url", "parts", "status", "generation_id", "agent", "notify"];
  if (
    !required.every((key) => Object.hasOwn(row, key))
    || row.name !== "CyberBoss Cloud"
    || row.url !== "https://cyberboss.linzezhang.com"
    || !Array.isArray(row.parts)
    || row.parts.join("|") !== "前台|后台"
    || !["access", "down"].includes(row.status)
    || !/^[a-f0-9]{24}$/.test(normalizeText(row.generation_id))
    || !normalizeTimestamp(row.source_generated_at)
    || row.agent !== "无"
    || row.notify !== "无"
  ) {
    throw new CanonicalStatusError("STATUS_GLOBAL_ROW_INVALID");
  }
  rejectSensitiveValue(row);
}

function readGlobalStatusRow(filePath) {
  const resolved = resolveExistingFile(filePath, "STATUS_GLOBAL_ROW_UNAVAILABLE");
  let row;
  try {
    row = JSON.parse(fs.readFileSync(resolved, "utf8"));
  } catch {
    throw new CanonicalStatusError("STATUS_GLOBAL_ROW_INVALID");
  }
  assertGlobalStatusRow(row);
  return Object.freeze(cloneJson(row));
}

function assertNewerGlobalRow(previous, next) {
  if (previous.generation_id === next.generation_id) {
    if (stableJson(previous) !== stableJson(next)) {
      throw new CanonicalStatusError("STATUS_GLOBAL_ROW_GENERATION_COLLISION");
    }
    return;
  }
  const previousTime = Date.parse(previous.source_generated_at);
  const nextTime = Date.parse(next.source_generated_at);
  if (!Number.isFinite(previousTime) || !Number.isFinite(nextTime) || nextTime <= previousTime) {
    throw new CanonicalStatusError("STATUS_GLOBAL_ROW_GENERATION_NON_MONOTONIC");
  }
}

function assertNewerGeneration(previous, next) {
  const previousTime = Date.parse(previous.generated_at);
  const nextTime = Date.parse(next.generated_at);
  if (!Number.isFinite(previousTime) || !Number.isFinite(nextTime) || nextTime <= previousTime) {
    throw new CanonicalStatusError("STATUS_GENERATION_NON_MONOTONIC");
  }
}

function buildLegacyCollectorSnapshot(snapshot) {
  const componentState = (id) => snapshot.components[id].state;
  const reasonCodes = Object.values(snapshot.components)
    .map((entry) => entry.reason_code)
    .filter((reason) => ["disk_pressure", "memory_pressure", "wechat_poll_stale", "wechat_poll_not_verified"].includes(reason));
  return {
    generation_id: snapshot.generation_id,
    generated_at: snapshot.generated_at,
    service: {
      state: legacyServiceState(snapshot.overall),
      version: snapshot.release.version.slice(1),
      source_commit: snapshot.source_commit,
    },
    wechat: { state: legacyComponentState(componentState("wechat_poll"), componentState("wechat_send")) },
    runtime: { state: legacyComponentState(componentState("runtime"), componentState("e2e")) },
    queue: { queued: snapshot.metrics.queue_depth },
    canonical: { state: legacyState(componentState("canonical")) },
    timeline: { build_state: legacyState(componentState("timeline")) },
    backup: {
      r2_state: legacyState(componentState("r2")),
      oci_state: legacyState(componentState("oci")),
    },
    resources: {
      profile: "unselected",
      memory_used_percent: null,
      disk_used_percent: null,
    },
    degraded_reasons: reasonCodes,
  };
}

function legacyServiceState(overall) {
  if (overall === "healthy") {
    return "healthy";
  }
  if (overall === "degraded") {
    return "degraded";
  }
  return "activation_pending";
}

function legacyComponentState(...states) {
  if (states.includes("failed")) {
    return "stopped";
  }
  if (states.includes("degraded")) {
    return "degraded";
  }
  if (states.every((state) => state === "healthy")) {
    return "healthy";
  }
  return "activation_pending";
}

function legacyState(state) {
  if (state === "healthy") {
    return "healthy";
  }
  if (state === "degraded") {
    return "degraded";
  }
  if (state === "failed") {
    return "failed";
  }
  return "activation_pending";
}

function atomicWriteJson({ output, payload, crashPoint, failurePrefix }) {
  if (!["", "before_rename", "after_rename_before_dirsync"].includes(crashPoint)) {
    throw new CanonicalStatusError(`${failurePrefix}_CRASH_POINT_INVALID`);
  }
  fs.mkdirSync(path.dirname(output), { recursive: true, mode: 0o700 });
  const temporary = path.join(path.dirname(output), `.${path.basename(output)}.${crypto.randomUUID()}.tmp`);
  let descriptor;
  let renamed = false;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, payload);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    if (crashPoint === "before_rename") {
      throw new CanonicalStatusError(`${failurePrefix}_CRASH_BEFORE_RENAME`);
    }
    fs.renameSync(temporary, output);
    renamed = true;
    if (crashPoint === "after_rename_before_dirsync") {
      throw new CanonicalStatusError(`${failurePrefix}_CRASH_AFTER_RENAME`);
    }
    const directory = fs.openSync(path.dirname(output), "r");
    try {
      fs.fsyncSync(directory);
    } finally {
      fs.closeSync(directory);
    }
  } finally {
    if (descriptor !== undefined) {
      fs.closeSync(descriptor);
    }
    if (!renamed && fs.existsSync(temporary)) {
      fs.rmSync(temporary, { force: true });
    }
  }
}

function loadExistingGlobalStatusAdapter() {
  try {
    const adapter = require(GLOBAL_STATUS_ADAPTER_PATH);
    if (typeof adapter?.buildRow !== "function") {
      throw new Error("missing_build_row");
    }
    return adapter;
  } catch {
    throw new CanonicalStatusError("STATUS_GLOBAL_ADAPTER_UNAVAILABLE");
  }
}

function normalizeProviderState(value) {
  const text = normalizeText(value);
  return ["verified", "simulator_verified", "activation_pending"].includes(text) ? text : "unknown";
}

function normalizeTimestamp(value) {
  const text = normalizeText(value);
  const parsed = new Date(text);
  return text && Number.isFinite(parsed.getTime()) ? parsed.toISOString() : "";
}

function normalizeCommit(value) {
  const text = normalizeText(value);
  return /^[a-f0-9]{7,40}$/.test(text) ? text : "";
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeOptionalInteger(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return normalizeNonNegativeInteger(value, null);
}

function normalizeNonNegativeInteger(value, fallback) {
  if (value === undefined) {
    return fallback;
  }
  if (Number.isSafeInteger(value) && value >= 0) {
    return value;
  }
  throw new CanonicalStatusError("STATUS_METRIC_INVALID");
}

function normalizeMaxAge(value) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 3600 ? parsed : 120;
}

function resolveOutputPath(value) {
  const text = normalizeText(value);
  if (!text) {
    throw new CanonicalStatusError("STATUS_OUTPUT_REQUIRED");
  }
  const output = path.resolve(text);
  if (fs.existsSync(output) && !fs.statSync(output).isFile()) {
    throw new CanonicalStatusError("STATUS_OUTPUT_INVALID");
  }
  return output;
}

function resolveExistingFile(value, code) {
  const text = normalizeText(value);
  const output = text ? path.resolve(text) : "";
  if (!output || !fs.existsSync(output) || !fs.statSync(output).isFile()) {
    throw new CanonicalStatusError(code);
  }
  return output;
}

function assertPlainObject(value, code) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CanonicalStatusError(code);
  }
}

function assertAllowedKeys(value, allowed, code) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) {
      throw new CanonicalStatusError(code);
    }
  }
}

function assertExactKeys(value, expected, code) {
  const keys = Object.keys(value);
  if (keys.length !== expected.size || keys.some((key) => !expected.has(key))) {
    throw new CanonicalStatusError(code);
  }
}

function rejectSensitiveValue(value) {
  if (typeof value === "string") {
    if (FORBIDDEN_VALUE.test(value)) {
      throw new CanonicalStatusError("STATUS_PRIVACY_VIOLATION");
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach(rejectSensitiveValue);
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  for (const [key, nested] of Object.entries(value)) {
    const lower = key.toLowerCase();
    if (FORBIDDEN_KEY_FRAGMENTS.some((fragment) => lower.includes(fragment))) {
      throw new CanonicalStatusError("STATUS_PRIVACY_VIOLATION");
    }
    rejectSensitiveValue(nested);
  }
}

function stableJson(value) {
  return JSON.stringify(sortJson(value));
}

function sortJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortJson);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortJson(value[key])]));
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

module.exports = {
  ADAPTER_IDS,
  COMPONENT_IDS,
  PRODUCT_VERSION,
  STATUS_SCHEMA,
  CanonicalStatusError,
  buildGlobalStatusRow,
  buildRedactedStatusSnapshot,
  readGlobalStatusRow,
  readStatusSnapshot,
  writeGlobalStatusRowAtomic,
  writeStatusSnapshotAtomic,
};
