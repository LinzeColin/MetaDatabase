import assert from "node:assert/strict";
import test from "node:test";
import {
  buildAuthRequest,
  resolveCaptchaResponse,
  safeAuthFailureMessage,
  SIGN_UP_VERIFICATION_PATH,
  VERIFIED_LOGIN_PATH,
} from "../app/auth/_components/auth-flow.ts";
import {
  getAuthRuntimeMissingCategories,
  getPublicAuthPageConfig,
  readAuthRuntimeConfig,
} from "../server/auth/runtime.ts";
import { rateLimit } from "../db/schema.ts";
import {
  ReauthenticationRequiredError,
  requireFreshVerifiedIdentity,
  requireVerifiedIdentity,
  rejectClientTenantFields,
} from "../server/security/tenant.ts";
import { SameOriginRequiredError, assertSameOriginMutation } from "../server/security/mutation-origin.ts";

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
  assert.equal(readAuthRuntimeConfig(validRuntime)?.mailProvider, "resend");
  assert.equal(readAuthRuntimeConfig({ ...validRuntime, BETTER_AUTH_SECRET: "short" }), null);
  assert.deepEqual(
    getAuthRuntimeMissingCategories({ ...validRuntime, BETTER_AUTH_SECRET: "short" }),
    ["auth_secret"],
  );
  assert.equal(readAuthRuntimeConfig({ ...validRuntime, APP_ORIGIN: "http://example.test" }), null);
});

test("Better Auth rate-limit timestamp remains an epoch-millisecond number", () => {
  assert.equal(rateLimit.lastRequest.mapToDriverValue(1_234_567_890), 1_234_567_890);
});

test("managed Turnstile retains a rendered response during callback timing", () => {
  assert.equal(resolveCaptchaResponse("callback-token", "rendered-token"), "callback-token");
  assert.equal(resolveCaptchaResponse("", "rendered-token"), "rendered-token");
  assert.equal(resolveCaptchaResponse("  ", "  "), "");
});

test("rate limits show a neutral retry message without claiming email delivery", () => {
  for (const mode of ["sign-in", "sign-up", "forgot-password", "verify-email"] as const) {
    assert.equal(safeAuthFailureMessage(429, mode), "操作次数较多，请稍后再试。");
  }
  assert.equal(
    safeAuthFailureMessage(400, "forgot-password"),
    "如果该邮箱可以接收重设邮件，我们已发送下一步说明。",
  );
});

test("NitroSend is a fail-closed alternate MailPort while Resend remains default", () => {
  const nitrosendRuntime = {
    ...validRuntime,
    RESEND_API_KEY: undefined,
    NITROSEND_API_KEY: "nitro-key",
    MAIL_PROVIDER: "nitrosend",
  };
  assert.equal(readAuthRuntimeConfig(nitrosendRuntime)?.mailProvider, "nitrosend");
  assert.equal(readAuthRuntimeConfig({ ...nitrosendRuntime, NITROSEND_API_KEY: undefined }), null);
  assert.equal(readAuthRuntimeConfig({ ...nitrosendRuntime, MAIL_PROVIDER: undefined }), null);
  assert.equal(readAuthRuntimeConfig({ ...validRuntime, MAIL_PROVIDER: "unsupported" }), null);
  assert.equal(readAuthRuntimeConfig({ ...validRuntime, MAIL_PROVIDER: "nitrosend", NITROSEND_API_KEY: undefined }), null);
});

test("mail sender accepts the frozen binding name and rejects conflicting aliases", () => {
  const bindingOnly = { ...validRuntime, AUTH_FROM_EMAIL: undefined, MAIL_FROM: "noreply@example.test" };
  assert.equal(readAuthRuntimeConfig(bindingOnly)?.fromEmail, "noreply@example.test");
  assert.equal(readAuthRuntimeConfig({ ...validRuntime, MAIL_FROM: "other@example.test" }), null);
  assert.deepEqual(
    getPublicAuthPageConfig({
      ...validRuntime,
      LEGAL_OPERATOR_NAME: "Example Operator",
      PRIVACY_CONTACT_EMAIL: "privacy@example.test",
    }),
    {
      turnstileSiteKey: "turnstile-site-key",
      legalOperatorName: "Example Operator",
      privacyContactEmail: "privacy@example.test",
    },
  );
});

test("only verified identities can enter tenant data handlers", () => {
  assert.deepEqual(
    requireVerifiedIdentity({ user: { id: "user_a", email: "a@example.test", emailVerified: true } }),
    { userId: "user_a", email: "a@example.test" },
  );
  assert.throws(() => requireVerifiedIdentity({ user: { id: "user_a", email: "a@example.test", emailVerified: false } }));
  assert.throws(() => requireVerifiedIdentity(null));
});

test("account deletion requires a recent verified session", () => {
  const now = 1_000_000;
  const identity = {
    user: { id: "user_a", email: "a@example.test", emailVerified: true },
    session: { createdAt: new Date(now - 1) },
  };
  assert.deepEqual(requireFreshVerifiedIdentity(identity, 10 * 60 * 1000, now), { userId: "user_a", email: "a@example.test" });
  assert.throws(
    () => requireFreshVerifiedIdentity({ ...identity, session: { createdAt: new Date(now - 10 * 60 * 1000) } }, 10 * 60 * 1000, now),
    ReauthenticationRequiredError,
  );
  assert.throws(() => requireFreshVerifiedIdentity({ user: identity.user }, 10 * 60 * 1000, now), ReauthenticationRequiredError);
});

test("custom mutations reject absent, cross-site, and mismatched origins", () => {
  const expected = "https://workbench.example.test";
  assert.doesNotThrow(() => assertSameOriginMutation(
    new Request(`${expected}/api/workbench/profile`, {
      method: "PUT",
      headers: { origin: expected, "sec-fetch-site": "same-origin" },
    }),
    expected,
  ));
  assert.throws(
    () => assertSameOriginMutation(new Request(`${expected}/api/workbench/profile`, { method: "PUT" }), expected),
    SameOriginRequiredError,
  );
  assert.throws(
    () => assertSameOriginMutation(
      new Request(`${expected}/api/workbench/profile`, { method: "PUT", headers: { origin: "https://evil.example.test" } }),
      expected,
    ),
    SameOriginRequiredError,
  );
});

test("nested tenant fields are rejected before a write can be prepared", () => {
  assert.throws(() => rejectClientTenantFields({ title: "x", nested: { user_id: "user_b" } }));
  assert.doesNotThrow(() => rejectClientTenantFields({ title: "x", values: [1, 2] }));
});

test("email verification resend stays same-origin and does not place email in the callback", () => {
  const request = buildAuthRequest("verify-email", {
    email: "member@example.test",
    password: "",
    name: "",
    captchaResponse: "",
    resetToken: "",
  });

  assert.equal(request.endpoint, "/api/auth/send-verification-email");
  assert.deepEqual(request.body, {
    email: "member@example.test",
    callbackURL: VERIFIED_LOGIN_PATH,
  });
  assert.equal(VERIFIED_LOGIN_PATH, "/auth/sign-in?verified=1");
  assert.equal(SIGN_UP_VERIFICATION_PATH, "/auth/verify-email");
  assert.equal(VERIFIED_LOGIN_PATH.includes("member@example.test"), false);
});

test("email sign-up and password reset keep the documented callback contracts", () => {
  const base = {
    email: "member@example.test",
    password: "correct-horse-battery-staple",
    name: "Member",
    captchaResponse: "captcha-token",
    resetToken: "reset-token",
  };

  assert.deepEqual(buildAuthRequest("sign-up", base), {
    endpoint: "/api/auth/sign-up/email",
    headers: { "x-captcha-response": "captcha-token" },
    body: {
      name: "Member",
      email: "member@example.test",
      password: "correct-horse-battery-staple",
      callbackURL: VERIFIED_LOGIN_PATH,
    },
  });
  assert.deepEqual(buildAuthRequest("sign-in", base).headers, {
    "x-captcha-response": "captcha-token",
  });
  assert.deepEqual(buildAuthRequest("forgot-password", base).headers, {
    "x-captcha-response": "captcha-token",
  });
  assert.deepEqual(buildAuthRequest("reset-password", base), {
    endpoint: "/api/auth/reset-password",
    body: { newPassword: "correct-horse-battery-staple", token: "reset-token" },
  });
});
