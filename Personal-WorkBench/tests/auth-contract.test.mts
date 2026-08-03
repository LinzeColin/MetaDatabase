import assert from "node:assert/strict";
import test from "node:test";
import { readAuthRuntimeConfig } from "../server/auth/runtime.ts";
import { requireVerifiedIdentity, rejectClientTenantFields } from "../server/security/tenant.ts";

const fakeDatabase = {} as D1Database;
const validRuntime = {
  DB: fakeDatabase,
  APP_ORIGIN: "https://workbench.example.test",
  BETTER_AUTH_SECRET: "a".repeat(32),
  GOOGLE_CLIENT_ID: "google-client",
  GOOGLE_CLIENT_SECRET: "google-secret",
  RESEND_API_KEY: "mail-key",
  AUTH_FROM_EMAIL: "noreply@example.test",
  TURNSTILE_SECRET_KEY: "turnstile-secret",
  TURNSTILE_SITE_KEY: "turnstile-site-key",
};

test("runtime readiness is all-or-nothing and does not expose field names", () => {
  assert.equal(readAuthRuntimeConfig(validRuntime)?.appOrigin, "https://workbench.example.test");
  assert.equal(readAuthRuntimeConfig({ ...validRuntime, BETTER_AUTH_SECRET: "short" }), null);
  assert.equal(readAuthRuntimeConfig({ ...validRuntime, APP_ORIGIN: "http://example.test" }), null);
});

test("only verified identities can enter tenant data handlers", () => {
  assert.deepEqual(
    requireVerifiedIdentity({ user: { id: "user_a", email: "a@example.test", emailVerified: true } }),
    { userId: "user_a", email: "a@example.test" },
  );
  assert.throws(() => requireVerifiedIdentity({ user: { id: "user_a", email: "a@example.test", emailVerified: false } }));
  assert.throws(() => requireVerifiedIdentity(null));
});

test("nested tenant fields are rejected before a write can be prepared", () => {
  assert.throws(() => rejectClientTenantFields({ title: "x", nested: { user_id: "user_b" } }));
  assert.doesNotThrow(() => rejectClientTenantFields({ title: "x", values: [1, 2] }));
});
