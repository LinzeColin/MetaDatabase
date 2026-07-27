const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const PRODUCT_VERSION = "v0.0.0.5";
const ACCESS_SCHEMA = "cyberboss.access-domain.v1";
const CANONICAL_HOSTNAME = "cyberboss.linzezhang.com";
const RUNTIME_LISTENER = "ws://127.0.0.1:8765";
const ORIGIN_HTTP_PORT = 8780;
const ACCESS_POLICY_SLOTS = Object.freeze([
  "cloudflare-access-owner-identity",
  "cloudflare-access-status-service-token",
]);
const ROUTES = Object.freeze([
  Object.freeze({ path: "/", surface: "cyberboss_dashboard", protection: "access_jwt" }),
  Object.freeze({ path: "/timeline/", surface: "timeline_read_only", protection: "access_jwt" }),
  Object.freeze({ path: "/status/", surface: "status_summary", protection: "access_jwt" }),
  Object.freeze({ path: "/healthz", surface: "minimal_health", protection: "access_jwt" }),
  Object.freeze({ path: "/readyz", surface: "readiness", protection: "access_jwt" }),
  Object.freeze({ path: "/status/snapshot.json", surface: "redacted_snapshot", protection: "access_jwt" }),
]);
const ANALYTICS_PATHS = new Set(["/", "/timeline/", "/status/"]);
const ANALYTICS_METRICS = new Set(["page_view", "LCP", "FCP", "TTFB"]);
const ANALYTICS_FORBIDDEN_KEYS = new Set([
  "raw_prompt",
  "raw_result",
  "raw_private_message",
  "wechat_user_id",
  "access_identity",
  "job_id",
  "thread_id",
  "secret",
  "token",
  "cookie",
  "full_query_string",
  "prompt",
  "result",
  "title",
  "url",
  "query",
  "fragment",
  "database",
  "storage",
]);
const PLAN_FORBIDDEN_VALUE = /-----BEGIN|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|\bBearer\s+[A-Za-z0-9._~-]{12,}|\b[^\s@]+@[^\s@]+\b|\/(?:root|home|etc)\//i;

class CanonicalAccessError extends Error {
  constructor(code) {
    super(code);
    this.name = "CanonicalAccessError";
    this.code = code;
  }
}

function buildAccessDomainPlan({
  policy,
  audienceReference,
  issuerReference,
  keysetReference,
} = {}) {
  const normalizedPolicy = validateIdentityScopePolicy(policy);
  const audience = normalizeReference(audienceReference, "ACCESS_AUDIENCE_REFERENCE_INVALID");
  const issuer = normalizeReference(issuerReference, "ACCESS_ISSUER_REFERENCE_INVALID");
  const keyset = normalizeReference(keysetReference, "ACCESS_KEYSET_REFERENCE_INVALID");
  const basis = {
    schema_version: ACCESS_SCHEMA,
    product_version: PRODUCT_VERSION,
    hostname: CANONICAL_HOSTNAME,
    route: {
      record_type: normalizedPolicy.cloudflare.dns.type,
      proxied: true,
      origin_reference: normalizedPolicy.cloudflare.dns.content_slot,
      activation_after: ["access_application", "access_policy"],
      state: "activation_pending",
    },
    access: {
      application_type: "self_hosted",
      application_name: "CyberBoss Cloud",
      default_action: "deny",
      allowed_identity_sources: ["google", "github"],
      owner_allowlist_slots: [...ACCESS_POLICY_SLOTS],
      service_token_decision: "non_identity",
      forbidden_policy_rules: ["bypass", "everyone", "any_valid_service_token"],
      state: "activation_pending",
    },
    origin: {
      transport: "cloudflare_tunnel",
      listener: `http://127.0.0.1:${ORIGIN_HTTP_PORT}`,
      access_jwt_required: true,
      direct_origin_bypass_forbidden: true,
      jwt_algorithm: "RS256",
      audience_reference: audience,
      issuer_reference: issuer,
      keyset_reference: keyset,
    },
    routes: ROUTES.map((route) => ({ ...route })),
    runtime: {
      codex_listener: RUNTIME_LISTENER,
      public_runtime_listener_allowed: false,
      codex_app_server_proxied: false,
      external_8765: "unreachable",
    },
    analytics: {
      provider: "Cloudflare Web Analytics",
      state: "activation_pending",
      allowed_surfaces: ["cyberboss_dashboard", "timeline_read_only", "status_public_summary_if_owner_enables"],
      required_metrics: ["page_views", "visits_or_visitors", "page_load_time", "core_web_vitals"],
      second_analytics_database_allowed: false,
      url_policy: "no_private_content_or_stable_execution_identifiers",
    },
    activation: {
      access_application: "activation_pending",
      access_policy: "activation_pending",
      dns_route: "activation_pending",
      analytics: "activation_pending",
      real_cloudflare_operations: 0,
    },
    counters: {
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      macos_launchd_dependency: false,
    },
  };
  const plan = {
    ...basis,
    plan_id: sha256(stableJson(basis)).slice(0, 24),
  };
  assertAccessDomainPlan(plan);
  return Object.freeze(cloneJson(plan));
}

function validateIdentityScopePolicy(value) {
  assertPlainObject(value, "ACCESS_POLICY_INVALID");
  const cloudflare = value.cloudflare;
  assertPlainObject(cloudflare, "ACCESS_POLICY_INVALID");
  if (value.schema_version !== 1 || cloudflare.hostname !== CANONICAL_HOSTNAME || cloudflare.zone !== "linzezhang.com") {
    throw new CanonicalAccessError("ACCESS_POLICY_INVALID");
  }
  const access = cloudflare.access;
  const dns = cloudflare.dns;
  const analytics = cloudflare.analytics;
  assertPlainObject(access, "ACCESS_POLICY_INVALID");
  assertPlainObject(dns, "ACCESS_POLICY_INVALID");
  assertPlainObject(analytics, "ACCESS_POLICY_INVALID");
  if (
    access.application_type !== "self_hosted" ||
    access.application_name !== "CyberBoss Cloud" ||
    access.deny_by_default !== true ||
    access.service_auth_api_decision !== "non_identity" ||
    access.service_auth_selector !== "service_token" ||
    !sameStrings(access.allowed_identity_slots, ACCESS_POLICY_SLOTS) ||
    !sameStrings(access.forbidden_decisions, ["bypass"]) ||
    !sameStrings(access.forbidden_include_rules, ["everyone", "any_valid_service_token"]) ||
    dns.type !== "CNAME" ||
    dns.name !== CANONICAL_HOSTNAME ||
    dns.proxied !== true ||
    dns.content_slot !== "cloudflare-origin-hostname" ||
    !sameStrings(dns.activation_after, ["access_application", "access_policy"]) ||
    analytics.hostname !== CANONICAL_HOSTNAME ||
    analytics.activation_mode !== "cloudflare_dashboard_automatic_setup" ||
    !Array.isArray(analytics.forbidden_fields)
  ) {
    throw new CanonicalAccessError("ACCESS_POLICY_INVALID");
  }
  for (const slot of ACCESS_POLICY_SLOTS) {
    normalizeReference(slot, "ACCESS_POLICY_INVALID");
  }
  normalizeReference(dns.content_slot, "ACCESS_POLICY_INVALID");
  return cloneJson(value);
}

function assertAccessDomainPlan(plan) {
  assertPlainObject(plan, "ACCESS_PLAN_INVALID");
  const expectedKeys = new Set([
    "schema_version", "product_version", "hostname", "route", "access", "origin",
    "routes", "runtime", "analytics", "activation", "counters", "plan_id",
  ]);
  assertExactKeys(plan, expectedKeys, "ACCESS_PLAN_INVALID");
  if (
    plan.schema_version !== ACCESS_SCHEMA ||
    plan.product_version !== PRODUCT_VERSION ||
    plan.hostname !== CANONICAL_HOSTNAME ||
    !/^[a-f0-9]{24}$/.test(plan.plan_id)
  ) {
    throw new CanonicalAccessError("ACCESS_PLAN_INVALID");
  }
  const { plan_id: planId, ...basis } = plan;
  if (sha256(stableJson(basis)).slice(0, 24) !== planId) {
    throw new CanonicalAccessError("ACCESS_PLAN_TAMPERED");
  }
  assertPlainObject(plan.route, "ACCESS_PLAN_INVALID");
  assertPlainObject(plan.access, "ACCESS_PLAN_INVALID");
  assertPlainObject(plan.origin, "ACCESS_PLAN_INVALID");
  assertPlainObject(plan.runtime, "ACCESS_PLAN_INVALID");
  assertPlainObject(plan.analytics, "ACCESS_PLAN_INVALID");
  assertPlainObject(plan.activation, "ACCESS_PLAN_INVALID");
  assertPlainObject(plan.counters, "ACCESS_PLAN_INVALID");
  if (
    plan.route.record_type !== "CNAME" ||
    plan.route.proxied !== true ||
    plan.route.origin_reference !== "cloudflare-origin-hostname" ||
    !sameStrings(plan.route.activation_after, ["access_application", "access_policy"]) ||
    plan.route.state !== "activation_pending" ||
    plan.access.application_type !== "self_hosted" ||
    plan.access.application_name !== "CyberBoss Cloud" ||
    plan.access.default_action !== "deny" ||
    !sameStrings(plan.access.allowed_identity_sources, ["google", "github"]) ||
    !sameStrings(plan.access.owner_allowlist_slots, ACCESS_POLICY_SLOTS) ||
    plan.access.service_token_decision !== "non_identity" ||
    !sameStrings(plan.access.forbidden_policy_rules, ["bypass", "everyone", "any_valid_service_token"]) ||
    plan.access.state !== "activation_pending" ||
    plan.origin.transport !== "cloudflare_tunnel" ||
    plan.origin.listener !== `http://127.0.0.1:${ORIGIN_HTTP_PORT}` ||
    plan.origin.access_jwt_required !== true ||
    plan.origin.direct_origin_bypass_forbidden !== true ||
    plan.origin.jwt_algorithm !== "RS256" ||
    plan.runtime.codex_listener !== RUNTIME_LISTENER ||
    plan.runtime.public_runtime_listener_allowed !== false ||
    plan.runtime.codex_app_server_proxied !== false ||
    plan.runtime.external_8765 !== "unreachable" ||
    plan.analytics.provider !== "Cloudflare Web Analytics" ||
    plan.analytics.state !== "activation_pending" ||
    plan.analytics.second_analytics_database_allowed !== false ||
    !sameStrings(plan.analytics.allowed_surfaces, ["cyberboss_dashboard", "timeline_read_only", "status_public_summary_if_owner_enables"]) ||
    !sameStrings(plan.analytics.required_metrics, ["page_views", "visits_or_visitors", "page_load_time", "core_web_vitals"]) ||
    plan.analytics.url_policy !== "no_private_content_or_stable_execution_identifiers" ||
    plan.activation.access_application !== "activation_pending" ||
    plan.activation.access_policy !== "activation_pending" ||
    plan.activation.dns_route !== "activation_pending" ||
    plan.activation.analytics !== "activation_pending" ||
    plan.activation.real_cloudflare_operations !== 0 ||
    plan.counters.control_plane_llm_calls !== 0 ||
    plan.counters.operations_llm_calls !== 0 ||
    plan.counters.macos_launchd_dependency !== false
  ) {
    throw new CanonicalAccessError("ACCESS_PLAN_INVALID");
  }
  for (const reference of [
    plan.route.origin_reference,
    plan.origin.audience_reference,
    plan.origin.issuer_reference,
    plan.origin.keyset_reference,
    ...plan.access.owner_allowlist_slots,
  ]) {
    normalizeReference(reference, "ACCESS_PLAN_INVALID");
  }
  if (!Array.isArray(plan.routes) || plan.routes.length !== ROUTES.length) {
    throw new CanonicalAccessError("ACCESS_PLAN_INVALID");
  }
  for (let index = 0; index < ROUTES.length; index += 1) {
    if (!sameRoute(plan.routes[index], ROUTES[index])) {
      throw new CanonicalAccessError("ACCESS_PLAN_INVALID");
    }
  }
  const serialized = stableJson(plan);
  if (PLAN_FORBIDDEN_VALUE.test(serialized)) {
    throw new CanonicalAccessError("ACCESS_PLAN_PRIVACY_VIOLATION");
  }
}

function verifyAccessJwt({
  jwt,
  expectedAudience,
  expectedIssuer,
  publicKeys,
  nowEpochSeconds,
} = {}) {
  const compact = normalizeText(jwt);
  const audience = normalizeText(expectedAudience);
  const issuer = normalizeText(expectedIssuer);
  if (!compact || !audience || !issuer || !Number.isSafeInteger(nowEpochSeconds) || nowEpochSeconds < 0) {
    throw new CanonicalAccessError("ACCESS_JWT_REQUIRED");
  }
  const parts = compact.split(".");
  if (parts.length !== 3 || parts.some((part) => !/^[A-Za-z0-9_-]+$/.test(part))) {
    throw new CanonicalAccessError("ACCESS_JWT_INVALID");
  }
  const header = parseJwtSegment(parts[0]);
  const claims = parseJwtSegment(parts[1]);
  if (header.alg !== "RS256" || !/^[A-Za-z0-9_-]{1,128}$/.test(normalizeText(header.kid))) {
    throw new CanonicalAccessError("ACCESS_JWT_ALGORITHM_DENIED");
  }
  const key = resolvePublicKey(publicKeys, header.kid);
  const validSignature = crypto.verify(
    "RSA-SHA256",
    Buffer.from(`${parts[0]}.${parts[1]}`, "utf8"),
    key,
    Buffer.from(parts[2], "base64url"),
  );
  if (!validSignature) {
    throw new CanonicalAccessError("ACCESS_JWT_SIGNATURE_INVALID");
  }
  if (claims.iss !== issuer || !audienceMatches(claims.aud, audience)) {
    throw new CanonicalAccessError("ACCESS_JWT_AUDIENCE_DENIED");
  }
  if (!Number.isSafeInteger(claims.exp) || claims.exp <= nowEpochSeconds) {
    throw new CanonicalAccessError("ACCESS_JWT_EXPIRED");
  }
  if (claims.nbf !== undefined && (!Number.isSafeInteger(claims.nbf) || claims.nbf > nowEpochSeconds)) {
    throw new CanonicalAccessError("ACCESS_JWT_NOT_ACTIVE");
  }
  if (!normalizeText(claims.sub)) {
    throw new CanonicalAccessError("ACCESS_JWT_SUBJECT_INVALID");
  }
  return Object.freeze({
    algorithm: "RS256",
    audience_verified: true,
    issuer_verified: true,
    expires_at_epoch: claims.exp,
  });
}

function authorizeOriginRequest(request, verifier) {
  try {
    assertPlainObject(request, "ACCESS_REQUEST_INVALID");
    assertPlainObject(verifier, "ACCESS_REQUEST_INVALID");
    if (normalizeText(request.host).toLowerCase() !== CANONICAL_HOSTNAME) {
      throw new CanonicalAccessError("ACCESS_HOST_DENIED");
    }
    if (request.transport !== "cloudflare_tunnel") {
      throw new CanonicalAccessError("ACCESS_ORIGIN_BYPASS_DENIED");
    }
    if (request.origin_port !== ORIGIN_HTTP_PORT) {
      throw new CanonicalAccessError("ACCESS_ORIGIN_PORT_DENIED");
    }
    const route = ROUTES.find((candidate) => candidate.path === request.path);
    if (!route) {
      throw new CanonicalAccessError("ACCESS_ROUTE_DENIED");
    }
    const headers = request.headers && typeof request.headers === "object" && !Array.isArray(request.headers)
      ? request.headers
      : {};
    const jwt = headerValue(headers, "cf-access-jwt-assertion");
    verifyAccessJwt({
      jwt,
      expectedAudience: verifier.expectedAudience,
      expectedIssuer: verifier.expectedIssuer,
      publicKeys: verifier.publicKeys,
      nowEpochSeconds: verifier.nowEpochSeconds,
    });
    return Object.freeze({
      allowed: true,
      status: 200,
      route: route.path,
      protection: route.protection,
      identity: "access_verified",
    });
  } catch (error) {
    const code = error instanceof CanonicalAccessError ? error.code : "ACCESS_DENIED";
    return Object.freeze({ allowed: false, status: 403, reason: code });
  }
}

function assertRuntimeBoundary({
  codexListener,
  publicRuntimeListenerAllowed,
  codexAppServerProxied,
} = {}) {
  if (
    codexListener !== RUNTIME_LISTENER ||
    publicRuntimeListenerAllowed !== false ||
    codexAppServerProxied !== false
  ) {
    throw new CanonicalAccessError("ACCESS_RUNTIME_BOUNDARY_DENIED");
  }
  return Object.freeze({ codex_listener: RUNTIME_LISTENER, external_8765: "unreachable" });
}

function sanitizeAnalyticsEvent(payload) {
  assertPlainObject(payload, "ANALYTICS_PAYLOAD_INVALID");
  for (const key of Object.keys(payload)) {
    if (ANALYTICS_FORBIDDEN_KEYS.has(key)) {
      throw new CanonicalAccessError("ANALYTICS_PRIVACY_VIOLATION");
    }
  }
  const metric = normalizeText(payload.metric);
  if (!ANALYTICS_METRICS.has(metric)) {
    throw new CanonicalAccessError("ANALYTICS_METRIC_DENIED");
  }
  if (metric === "page_view") {
    assertExactKeys(payload, new Set(["metric", "path"]), "ANALYTICS_PAYLOAD_INVALID");
    const pagePath = normalizeText(payload.path);
    if (!ANALYTICS_PATHS.has(pagePath) || /[?#]/.test(pagePath)) {
      throw new CanonicalAccessError("ANALYTICS_PATH_DENIED");
    }
    return Object.freeze({ metric, path: pagePath });
  }
  assertExactKeys(payload, new Set(["metric", "value_ms"]), "ANALYTICS_PAYLOAD_INVALID");
  if (!Number.isFinite(payload.value_ms) || payload.value_ms < 0 || payload.value_ms > 600000) {
    throw new CanonicalAccessError("ANALYTICS_VALUE_INVALID");
  }
  return Object.freeze({ metric, value_ms: Math.round(payload.value_ms) });
}

function writeAccessPlanAtomic({ plan, outputPath, crashPoint = "" } = {}) {
  assertAccessDomainPlan(plan);
  const output = resolveOutputPath(outputPath);
  const payload = Buffer.from(`${stableJson(plan)}\n`, "utf8");
  atomicWrite({ output, payload, crashPoint, failurePrefix: "ACCESS_PLAN" });
  return Object.freeze({ plan_id: plan.plan_id, sha256: sha256(payload) });
}

function readAccessPlan(filePath) {
  const resolved = resolveExistingFile(filePath, "ACCESS_PLAN_UNAVAILABLE");
  try {
    const plan = JSON.parse(fs.readFileSync(resolved, "utf8"));
    assertAccessDomainPlan(plan);
    return Object.freeze(cloneJson(plan));
  } catch (error) {
    if (error instanceof CanonicalAccessError) {
      throw error;
    }
    throw new CanonicalAccessError("ACCESS_PLAN_INVALID");
  }
}

function atomicWrite({ output, payload, crashPoint, failurePrefix }) {
  if (!["", "before_rename", "after_rename_before_dirsync"].includes(crashPoint)) {
    throw new CanonicalAccessError(`${failurePrefix}_CRASH_POINT_INVALID`);
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
      throw new CanonicalAccessError(`${failurePrefix}_CRASH_BEFORE_RENAME`);
    }
    fs.renameSync(temporary, output);
    renamed = true;
    if (crashPoint === "after_rename_before_dirsync") {
      throw new CanonicalAccessError(`${failurePrefix}_CRASH_AFTER_RENAME`);
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

function parseJwtSegment(segment) {
  try {
    const parsed = JSON.parse(Buffer.from(segment, "base64url").toString("utf8"));
    assertPlainObject(parsed, "ACCESS_JWT_INVALID");
    return parsed;
  } catch (error) {
    if (error instanceof CanonicalAccessError) {
      throw error;
    }
    throw new CanonicalAccessError("ACCESS_JWT_INVALID");
  }
}

function resolvePublicKey(publicKeys, keyId) {
  let key;
  if (publicKeys instanceof Map) {
    key = publicKeys.get(keyId);
  } else if (publicKeys && typeof publicKeys === "object" && !Array.isArray(publicKeys)) {
    key = Object.prototype.hasOwnProperty.call(publicKeys, keyId) ? publicKeys[keyId] : undefined;
  }
  if (!key) {
    throw new CanonicalAccessError("ACCESS_JWT_KEY_UNAVAILABLE");
  }
  return key;
}

function audienceMatches(value, expectedAudience) {
  if (typeof value === "string") {
    return value === expectedAudience;
  }
  return Array.isArray(value) && value.every((item) => typeof item === "string") && value.includes(expectedAudience);
}

function headerValue(headers, name) {
  const expected = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === expected && typeof value === "string") {
      return value;
    }
  }
  return "";
}

function sameRoute(value, expected) {
  return Boolean(value) && value.path === expected.path && value.surface === expected.surface && value.protection === expected.protection && Object.keys(value).length === 3;
}

function sameStrings(value, expected) {
  return Array.isArray(value) && value.length === expected.length && value.every((item, index) => item === expected[index]);
}

function normalizeReference(value, code) {
  const text = normalizeText(value);
  if (!/^[a-z][a-z0-9-]{2,95}$/.test(text)) {
    throw new CanonicalAccessError(code);
  }
  return text;
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function resolveOutputPath(value) {
  const text = normalizeText(value);
  if (!text) {
    throw new CanonicalAccessError("ACCESS_OUTPUT_REQUIRED");
  }
  const output = path.resolve(text);
  if (fs.existsSync(output) && !fs.statSync(output).isFile()) {
    throw new CanonicalAccessError("ACCESS_OUTPUT_INVALID");
  }
  return output;
}

function resolveExistingFile(value, code) {
  const text = normalizeText(value);
  const candidate = text ? path.resolve(text) : "";
  if (!candidate || !fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
    throw new CanonicalAccessError(code);
  }
  return candidate;
}

function assertPlainObject(value, code) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CanonicalAccessError(code);
  }
}

function assertExactKeys(value, expected, code) {
  const keys = Object.keys(value);
  if (keys.length !== expected.size || keys.some((key) => !expected.has(key))) {
    throw new CanonicalAccessError(code);
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
  ACCESS_SCHEMA,
  ACCESS_POLICY_SLOTS,
  CANONICAL_HOSTNAME,
  ORIGIN_HTTP_PORT,
  PRODUCT_VERSION,
  ROUTES,
  RUNTIME_LISTENER,
  CanonicalAccessError,
  assertAccessDomainPlan,
  assertRuntimeBoundary,
  authorizeOriginRequest,
  buildAccessDomainPlan,
  readAccessPlan,
  sanitizeAnalyticsEvent,
  validateIdentityScopePolicy,
  verifyAccessJwt,
  writeAccessPlanAtomic,
};
