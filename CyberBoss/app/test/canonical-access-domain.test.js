const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  ACCESS_SCHEMA,
  CANONICAL_HOSTNAME,
  ORIGIN_HTTP_PORT,
  ROUTES,
  RUNTIME_LISTENER,
  CanonicalAccessError,
  assertAccessDomainPlan,
  assertRuntimeBoundary,
  authorizeOriginRequest,
  buildAccessDomainPlan,
  readAccessPlan,
  sanitizeAnalyticsEvent,
  verifyAccessJwt,
  writeAccessPlanAtomic,
} = require("../src/services/access/canonical-access-domain");

const policyPath = path.resolve(
  __dirname,
  "../../docs/product_design/v0.0.0.4/implementation-kit/config/identity-scope.policy.json",
);
const POLICY = JSON.parse(fs.readFileSync(policyPath, "utf8"));
const NOW = 1700000000;
const ISSUER = "https://access.example.invalid";
const AUDIENCE = "access-audience-fixture";
const { privateKey, publicKey } = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });

function buildPlan(overrides = {}) {
  return buildAccessDomainPlan({
    policy: POLICY,
    audienceReference: overrides.audienceReference || "access-audience-slot",
    issuerReference: overrides.issuerReference || "access-issuer-slot",
    keysetReference: overrides.keysetReference || "access-jwks-slot",
  });
}

function signJwt(overrides = {}) {
  const header = { alg: "RS256", kid: "fixture-key", typ: "JWT" };
  const claims = {
    iss: ISSUER,
    aud: AUDIENCE,
    sub: "subject-fixture",
    exp: NOW + 300,
    nbf: NOW - 1,
    ...overrides,
  };
  const signingInput = `${Buffer.from(JSON.stringify(header)).toString("base64url")}.${Buffer.from(JSON.stringify(claims)).toString("base64url")}`;
  return `${signingInput}.${crypto.sign("RSA-SHA256", Buffer.from(signingInput), privateKey).toString("base64url")}`;
}

function request(overrides = {}) {
  return {
    host: CANONICAL_HOSTNAME,
    path: "/",
    transport: "cloudflare_tunnel",
    origin_port: ORIGIN_HTTP_PORT,
    headers: { "CF-Access-Jwt-Assertion": signJwt() },
    ...overrides,
  };
}

function verifier() {
  return {
    expectedAudience: AUDIENCE,
    expectedIssuer: ISSUER,
    publicKeys: new Map([["fixture-key", publicKey]]),
    nowEpochSeconds: NOW,
  };
}

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-access-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

test("access domain plan reuses the locked policy, has a single route authority, and remains activation pending", () => {
  const plan = buildPlan();
  assert.equal(plan.schema_version, ACCESS_SCHEMA);
  assert.equal(plan.hostname, CANONICAL_HOSTNAME);
  assert.equal(plan.route.origin_reference, "cloudflare-origin-hostname");
  assert.equal(plan.access.default_action, "deny");
  assert.equal(plan.access.application_type, "self_hosted");
  assert.equal(plan.route.proxied, true);
  assert.equal(plan.runtime.codex_listener, RUNTIME_LISTENER);
  assert.equal(plan.runtime.public_runtime_listener_allowed, false);
  assert.equal(plan.runtime.codex_app_server_proxied, false);
  assert.equal(plan.activation.real_cloudflare_operations, 0);
  assert.equal(plan.counters.control_plane_llm_calls, 0);
  assert.equal(plan.counters.operations_llm_calls, 0);
  assert.equal(plan.counters.macos_launchd_dependency, false);
  assert.deepEqual(plan.routes.map((route) => route.path), ROUTES.map((route) => route.path));
  const serialized = JSON.stringify(plan);
  for (const forbidden of ["@", "Bearer ", "-----BEGIN", "/var/", "/home/"]) {
    assert.equal(serialized.includes(forbidden), false, forbidden);
  }
});

test("anonymous authorized matrix, JWT audience, and origin bypass all fail closed", () => {
  const authorized = authorizeOriginRequest(request(), verifier());
  assert.deepEqual(authorized, {
    allowed: true,
    status: 200,
    route: "/",
    protection: "access_jwt",
    identity: "access_verified",
  });
  assert.equal(authorizeOriginRequest(request({ headers: {} }), verifier()).status, 403);
  assert.equal(
    authorizeOriginRequest(request({ headers: { "CF-Access-Jwt-Assertion": signJwt({ aud: "wrong-audience" }) } }), verifier()).reason,
    "ACCESS_JWT_AUDIENCE_DENIED",
  );
  assert.equal(
    authorizeOriginRequest(request({ transport: "direct_origin" }), verifier()).reason,
    "ACCESS_ORIGIN_BYPASS_DENIED",
  );
  assert.equal(
    authorizeOriginRequest(request({ origin_port: 8765 }), verifier()).reason,
    "ACCESS_ORIGIN_PORT_DENIED",
  );
  assert.throws(
    () => verifyAccessJwt({ ...verifier(), jwt: `${signJwt()}x` }),
    (error) => error instanceof CanonicalAccessError && error.code === "ACCESS_JWT_SIGNATURE_INVALID",
  );
  assert.deepEqual(assertRuntimeBoundary({
    codexListener: RUNTIME_LISTENER,
    publicRuntimeListenerAllowed: false,
    codexAppServerProxied: false,
  }), { codex_listener: RUNTIME_LISTENER, external_8765: "unreachable" });
  assert.throws(
    () => assertRuntimeBoundary({
      codexListener: "ws://0.0.0.0:8765",
      publicRuntimeListenerAllowed: true,
      codexAppServerProxied: true,
    }),
    (error) => error instanceof CanonicalAccessError && error.code === "ACCESS_RUNTIME_BOUNDARY_DENIED",
  );
});

test("every protected route requires a valid Access JWT and never exposes anonymous detailed status", () => {
  for (const route of ROUTES) {
    const denied = authorizeOriginRequest(request({ path: route.path, headers: {} }), verifier());
    assert.equal(denied.allowed, false, route.path);
    assert.equal(denied.status, 403, route.path);
    const allowed = authorizeOriginRequest(request({ path: route.path }), verifier());
    assert.equal(allowed.allowed, true, route.path);
    assert.equal(allowed.protection, "access_jwt", route.path);
  }
  assert.equal(authorizeOriginRequest(request({ path: "/jobs/job_123" }), verifier()).reason, "ACCESS_ROUTE_DENIED");
});

test("privacy-first analytics keeps only aggregate page-view and performance fields", () => {
  assert.deepEqual(sanitizeAnalyticsEvent({ metric: "page_view", path: "/" }), { metric: "page_view", path: "/" });
  assert.deepEqual(sanitizeAnalyticsEvent({ metric: "LCP", value_ms: 900.4 }), { metric: "LCP", value_ms: 900 });
  for (const hostile of [
    { metric: "page_view", path: "/?prompt=private" },
    { metric: "page_view", path: "/jobs/job_123" },
    { metric: "page_view", title: "private title" },
    { metric: "page_view", raw_prompt: "private" },
    { metric: "page_view", path: "/", thread_id: "thread_123" },
    { metric: "LCP", value_ms: 900, database: "second" },
  ]) {
    assert.throws(
      () => sanitizeAnalyticsEvent(hostile),
      (error) => error instanceof CanonicalAccessError,
    );
  }
});

test("domain plan atomic writes preserve the previous valid plan across crash cuts", (t) => {
  const root = temporaryRoot(t);
  const output = path.join(root, "access-plan.json");
  const first = buildPlan();
  writeAccessPlanAtomic({ plan: first, outputPath: output });
  const firstBytes = fs.readFileSync(output, "utf8");
  const second = buildPlan({ audienceReference: "access-audience-slot-next" });
  assert.throws(
    () => writeAccessPlanAtomic({ plan: second, outputPath: output, crashPoint: "before_rename" }),
    (error) => error instanceof CanonicalAccessError && error.code === "ACCESS_PLAN_CRASH_BEFORE_RENAME",
  );
  assert.equal(fs.readFileSync(output, "utf8"), firstBytes);
  assert.deepEqual(readAccessPlan(output), first);
  assert.throws(
    () => writeAccessPlanAtomic({ plan: second, outputPath: output, crashPoint: "after_rename_before_dirsync" }),
    (error) => error instanceof CanonicalAccessError && error.code === "ACCESS_PLAN_CRASH_AFTER_RENAME",
  );
  assert.deepEqual(readAccessPlan(output), second);
});

test("policy schema, symbolic references, and plan tampering fail closed", () => {
  const broad = structuredClone(POLICY);
  broad.cloudflare.access.deny_by_default = false;
  assert.throws(
    () => buildAccessDomainPlan({
      policy: broad,
      audienceReference: "access-audience-slot",
      issuerReference: "access-issuer-slot",
      keysetReference: "access-jwks-slot",
    }),
    (error) => error instanceof CanonicalAccessError && error.code === "ACCESS_POLICY_INVALID",
  );
  assert.throws(
    () => buildAccessDomainPlan({
      policy: POLICY,
      audienceReference: "https://unexpected.example",
      issuerReference: "access-issuer-slot",
      keysetReference: "access-jwks-slot",
    }),
    (error) => error instanceof CanonicalAccessError && error.code === "ACCESS_AUDIENCE_REFERENCE_INVALID",
  );
  const tampered = structuredClone(buildPlan());
  tampered.activation.real_cloudflare_operations = 1;
  assert.throws(
    () => assertAccessDomainPlan(tampered),
    (error) => error instanceof CanonicalAccessError,
  );
});
