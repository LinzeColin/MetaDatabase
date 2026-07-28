"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { SqliteUserRepository } = require("../src/services/users/user-repository");
const {
  SqliteInviteCodeStore,
} = require("../src/services/users/invite-code-store");
const {
  RegistrationError,
  RegistrationService,
} = require("../src/services/users/registration-service");
const {
  ACTIONS,
  COMMANDS,
  reduceOnboarding,
} = require("../src/services/users/onboarding-state");
const {
  SetupTokenError,
  SqliteSetupTokenService,
} = require("../src/services/security/setup-token-service");
const {
  SessionError,
  SqliteSessionTokenService,
  parseSessionCookie,
} = require("../src/services/security/session-token-service");
const {
  SetupLinkError,
  buildSecureSetupLink,
  parseSetupFragment,
  tokenAppearsInRequestTarget,
} = require("../src/services/security/secure-setup-link");
const {
  ACTION_ALLOWLIST,
  MAX_BODY_BYTES,
  PortalError,
  SetupPortal,
} = require("../src/services/portal/setup-portal");

const KEY = Buffer.alloc(32, 7);
const IDENTITY_KEY = Buffer.alloc(32, 9);
const INVITE_SECRET = Buffer.alloc(32, 11);
const ORIGIN = "https://cyberboss.example";
const HOST = "cyberboss.example";
const BOT = "bot-account-1";

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb620-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const databasePath = path.join(directory, "runtime.db");
  const spool = new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  const database = new DatabaseSync(databasePath);
  t.after(() => database.close());
  database.exec("PRAGMA foreign_keys=ON");

  let clock = 1_700_000_000_000;
  const now = () => clock;
  const users = new SqliteUserRepository({
    database,
    identityKey: IDENTITY_KEY,
    now: () => new Date(clock),
  });
  const invites = new SqliteInviteCodeStore({
    database,
    secret: INVITE_SECRET,
    now,
  });
  const setupTokens = new SqliteSetupTokenService({ database, now });
  const sessions = new SqliteSessionTokenService({ database, now });
  const registration = new RegistrationService({
    userRepository: users,
    inviteStore: invites,
    registrationMode: "invite",
  });
  return {
    database,
    spool,
    users,
    invites,
    setupTokens,
    sessions,
    registration,
    advance: (ms) => {
      clock += ms;
    },
    now,
  };
}

test("an unknown sender only reaches pending; consent is what activates", (t) => {
  const h = harness(t);
  const modelCalls = [];
  const callModel = (userId) => {
    if (!h.users.mayCallModel(userId)) {
      throw new Error("MODEL_CALL_FORBIDDEN");
    }
    modelCalls.push(userId);
  };

  // No invite code: nothing is created at all.
  const asked = h.registration.start({ botAccountRef: BOT, senderRef: "s-a" });
  assert.equal(asked.user, null);
  assert.equal(asked.action, ACTIONS.REQUEST_INVITE);
  assert.equal(asked.modelCalls, 0);
  assert.equal(h.users.countByRole("user"), 0);

  // A wrong code creates nothing either.
  assert.throws(
    () =>
      h.registration.start({
        botAccountRef: BOT,
        senderRef: "s-a",
        inviteCode: "AAAABBBBCCCC",
      }),
    /INVITE_INVALID/,
  );
  assert.equal(h.users.countByRole("user"), 0);

  const invite = h.invites.issue({ maxUses: 1, ttlMs: 60_000 });
  const started = h.registration.start({
    botAccountRef: BOT,
    senderRef: "s-a",
    inviteCode: invite.code,
  });
  assert.equal(started.user.status, "pending_consent");
  assert.equal(started.createdUser, true);
  assert.equal(started.modelCalls, 0);
  assert.equal(h.users.mayCallModel(started.user.user_id), false);
  assert.throws(() => callModel(started.user.user_id), /MODEL_CALL_FORBIDDEN/);
  assert.equal(modelCalls.length, 0, "no model call before consent");

  // Declining leaves the user pending and still model-blocked.
  const declined = h.registration.consent({
    botAccountRef: BOT,
    senderRef: "s-a",
    accepted: false,
  });
  assert.equal(declined.action, ACTIONS.CONSENT_DECLINED);
  assert.equal(declined.modelCalls, 0);
  assert.equal(h.users.mayCallModel(started.user.user_id), false);
  assert.equal(modelCalls.length, 0);

  const active = h.registration.consent({
    botAccountRef: BOT,
    senderRef: "s-a",
    accepted: true,
  });
  assert.equal(active.user.status, "active");
  assert.equal(active.action, ACTIONS.SHOW_HOME);
  assert.equal(active.modelCalls, null, "only an active user may spend tokens");
  callModel(active.user.user_id);
  assert.deepEqual(modelCalls, [active.user.user_id]);

  // Consent without a prior start is refused outright.
  assert.throws(
    () =>
      h.registration.consent({
        botAccountRef: BOT,
        senderRef: "never-seen",
        accepted: true,
      }),
    (error) =>
      error instanceof RegistrationError && error.code === "START_REQUIRED",
  );
});

test("suspension immediately blocks model access and stays blocked", (t) => {
  const h = harness(t);
  const invite = h.invites.issue({ maxUses: 1, ttlMs: 60_000 });
  const started = h.registration.start({
    botAccountRef: BOT,
    senderRef: "s-b",
    inviteCode: invite.code,
  });
  h.registration.consent({
    botAccountRef: BOT,
    senderRef: "s-b",
    accepted: true,
  });
  assert.equal(h.registration.mayCallModel(started.user.user_id), true);

  h.registration.suspend({ userId: started.user.user_id });
  assert.equal(h.registration.mayCallModel(started.user.user_id), false);

  const resumed = h.registration.start({ botAccountRef: BOT, senderRef: "s-b" });
  assert.equal(resumed.state, "suspended");
  assert.equal(resumed.modelCalls, 0);
  assert.equal(resumed.action, ACTIONS.SUSPENDED);
});

test("the same WeChat account resumes one user from any client", (t) => {
  const h = harness(t);
  const invite = h.invites.issue({ maxUses: 1, ttlMs: 60_000 });
  const first = h.registration.start({
    botAccountRef: BOT,
    senderRef: "s-c",
    inviteCode: invite.code,
  });
  h.registration.consent({
    botAccountRef: BOT,
    senderRef: "s-c",
    accepted: true,
  });

  // A second device is the same principal: same user, no new row, no invite.
  const second = h.registration.start({ botAccountRef: BOT, senderRef: "s-c" });
  assert.equal(second.user.user_id, first.user.user_id);
  assert.equal(second.resumed, true);
  assert.equal(second.createdUser, false);
  assert.equal(second.state, "active");
  assert.equal(h.users.countByRole("user"), 1, "no second account system");

  // The same sender on a different bot account is a different principal.
  const other = h.registration.start({
    botAccountRef: "bot-account-2",
    senderRef: "s-c",
  });
  assert.equal(other.user, null);
  assert.equal(other.action, ACTIONS.REQUEST_INVITE);
});

test("onboarding transitions before active never permit a model call", () => {
  const cases = [
    ["unseen", COMMANDS.START, {}],
    ["unseen", "随便说点什么", {}],
    ["pending_invite", "ABCD-EFGH-JKLM", {}],
    ["pending_invite", "ABCD-EFGH-JKLM", { inviteValidated: true }],
    ["pending_invite", COMMANDS.CANCEL, {}],
    ["pending_consent", COMMANDS.CONSENT, {}],
    ["pending_consent", COMMANDS.DECLINE, {}],
    ["pending_consent", COMMANDS.CANCEL, {}],
    ["pending_consent", "在吗", {}],
    ["suspended", COMMANDS.START, {}],
  ];
  for (const [state, text, options] of cases) {
    const result = reduceOnboarding(state, text, options);
    assert.equal(
      result.modelCalls,
      0,
      `${state} + ${text} must not permit a model call`,
    );
    assert.equal(typeof result.message, "string");
    assert.ok(result.message.length > 0);
    // Every pre-active reply is Chinese and jargon-free.
    assert.match(result.message, /[一-龥]/);
    assert.doesNotMatch(result.message, /token|API|HTTP|SQL/i);
  }
  assert.equal(reduceOnboarding("active", "你好").modelCalls, null);
  assert.equal(
    reduceOnboarding("unknown-state", COMMANDS.START).state,
    "pending_invite",
    "an unknown state falls back to the safest branch",
  );
});

test("setup links are 10-minute, single-use and hash-stored", (t) => {
  const h = harness(t);
  const invite = h.invites.issue({ maxUses: 1, ttlMs: 60_000 });
  const started = h.registration.start({
    botAccountRef: BOT,
    senderRef: "s-d",
    inviteCode: invite.code,
  });
  const userId = started.user.user_id;

  const issued = h.setupTokens.issue({ userId, purpose: "provider" });
  assert.equal(issued.ttlMs, 10 * 60 * 1000);
  assert.equal(issued.expiresAt - h.now(), 10 * 60 * 1000);

  const stored = h.database.prepare("SELECT * FROM setup_tokens").all();
  assert.equal(stored.length, 1);
  assert.equal(stored[0].token_hash.length, 64);
  assert.ok(
    !JSON.stringify(stored[0]).includes(issued.token),
    "the plaintext token must never be persisted",
  );
  assert.equal(h.setupTokens.matchesStoredHash(issued.token, stored[0].token_hash), true);

  const consumed = h.setupTokens.consume({
    token: issued.token,
    purpose: "provider",
  });
  assert.equal(consumed.userId, userId);
  assert.throws(
    () => h.setupTokens.consume({ token: issued.token, purpose: "provider" }),
    (error) => error instanceof SetupTokenError && error.code === "LINK_INVALID",
    "a second consumption is refused",
  );

  // Purpose confusion is refused without consuming the token.
  const other = h.setupTokens.issue({ userId, purpose: "import" });
  assert.throws(
    () => h.setupTokens.consume({ token: other.token, purpose: "privacy" }),
    /LINK_INVALID/,
  );
  assert.equal(
    h.setupTokens.consume({ token: other.token, purpose: "import" }).userId,
    userId,
  );

  const expiring = h.setupTokens.issue({ userId, purpose: "profile" });
  h.advance(10 * 60 * 1000 + 1);
  assert.throws(
    () => h.setupTokens.consume({ token: expiring.token, purpose: "profile" }),
    (error) => error instanceof SetupTokenError && error.code === "LINK_EXPIRED",
  );

  assert.throws(
    () => new SqliteSetupTokenService({ database: h.database, ttlMs: 60 * 60 * 1000 }),
    /SETUP_TOKEN_TTL_INVALID/,
    "a TTL longer than 10 minutes is rejected at construction",
  );
});

test("a setup link keeps the token out of the request target", () => {
  const token = "a".repeat(43);
  const link = buildSecureSetupLink({ origin: ORIGIN, token, purpose: "provider" });
  assert.equal(tokenAppearsInRequestTarget(link, token), false);
  assert.match(link, /^https:\/\/cyberboss\.example\/setup#/);
  assert.deepEqual(parseSetupFragment(new URL(link).hash), {
    token,
    purpose: "provider",
  });

  assert.throws(
    () => buildSecureSetupLink({ origin: "http://cyberboss.example", token, purpose: "provider" }),
    (error) => error instanceof SetupLinkError && error.code === "HTTPS_ORIGIN_REQUIRED",
  );
  assert.throws(
    () => buildSecureSetupLink({ origin: ORIGIN, token: "short", purpose: "provider" }),
    /OPAQUE_TOKEN_REQUIRED/,
  );
  assert.throws(
    () => buildSecureSetupLink({ origin: ORIGIN, token, purpose: "Provider!" }),
    /PURPOSE_REQUIRED/,
  );
  assert.throws(
    () => buildSecureSetupLink({ origin: `${ORIGIN}/x?y=1`, token, purpose: "provider" }),
    /ORIGIN_MUST_BE_BARE/,
  );
});

test("sessions are Secure, HttpOnly, SameSite=Strict, CSRF-bound and revocable", (t) => {
  const h = harness(t);
  const invite = h.invites.issue({ maxUses: 1, ttlMs: 60_000 });
  const started = h.registration.start({
    botAccountRef: BOT,
    senderRef: "s-e",
    inviteCode: invite.code,
  });
  const userId = started.user.user_id;

  const session = h.sessions.issue({ userId });
  for (const attribute of ["HttpOnly", "Secure", "SameSite=Strict", "Path=/"]) {
    assert.ok(session.cookie.includes(attribute), `cookie missing ${attribute}`);
  }
  assert.equal(parseSessionCookie(session.cookie.split(";")[0]), session.token);

  assert.equal(
    h.sessions.verify({ token: session.token, csrf: session.csrf }).userId,
    userId,
  );
  assert.throws(
    () => h.sessions.verify({ token: session.token, csrf: "b".repeat(43) }),
    (error) => error instanceof SessionError && error.code === "CSRF_INVALID",
  );
  assert.throws(
    () => h.sessions.verify({ token: "c".repeat(43), csrf: session.csrf }),
    /SESSION_INVALID/,
  );

  const stored = h.database.prepare("SELECT * FROM web_sessions").all();
  assert.ok(
    !JSON.stringify(stored).includes(session.token),
    "the session token is stored only as a hash",
  );
  assert.ok(!JSON.stringify(stored).includes(session.csrf));

  // AC-011: one WeChat command kills every session the user holds.
  const second = h.sessions.issue({ userId });
  assert.equal(h.sessions.activeSessionCount(userId), 2);
  assert.equal(h.sessions.revokeAllForUser(userId), 2);
  assert.equal(h.sessions.activeSessionCount(userId), 0);
  for (const token of [session.token, second.token]) {
    assert.throws(
      () => h.sessions.verify({ token, csrf: session.csrf }),
      /SESSION_INVALID/,
    );
  }

  const expiring = h.sessions.issue({ userId });
  h.advance(30 * 60 * 1000 + 1);
  assert.throws(
    () => h.sessions.verify({ token: expiring.token, csrf: expiring.csrf }),
    (error) => error instanceof SessionError && error.code === "SESSION_EXPIRED",
  );
});

test("the portal fails closed on host, origin, action, CSRF and body size", (t) => {
  const h = harness(t);
  const invite = h.invites.issue({ maxUses: 1, ttlMs: 60_000 });
  const started = h.registration.start({
    botAccountRef: BOT,
    senderRef: "s-f",
    inviteCode: invite.code,
  });
  const userId = started.user.user_id;

  const saved = [];
  const portal = new SetupPortal({
    database: h.database,
    allowedOrigins: [ORIGIN],
    sessionService: h.sessions,
    setupTokenService: h.setupTokens,
    userRepository: h.users,
    handlers: {
      "provider.save": ({ userId: actingUser, payload }) => {
        saved.push({ actingUser, payload });
        return { status: 200, ok: true };
      },
    },
  });

  const setup = h.setupTokens.issue({ userId, purpose: "provider" });
  const exchanged = portal.handle({
    method: "POST",
    action: "session.exchange",
    headers: { host: HOST, origin: ORIGIN },
    body: JSON.stringify({ token: setup.token, purpose: "provider" }),
  });
  assert.equal(exchanged.userId, userId);
  assert.ok(exchanged.setCookie.includes("SameSite=Strict"));

  const cookie = `cb_session=${exchanged.setCookie.split(";")[0].split("=")[1]}`;
  const good = {
    method: "POST",
    action: "provider.save",
    headers: {
      host: HOST,
      origin: ORIGIN,
      cookie,
      "x-csrf-token": exchanged.csrf,
    },
    body: JSON.stringify({ provider_id: "openai" }),
  };
  assert.equal(portal.handle(good).ok, true);
  assert.equal(saved.length, 1);
  assert.equal(saved[0].actingUser, userId);

  const expectRejection = (mutate, code, status) => {
    const request = mutate(JSON.parse(JSON.stringify(good)));
    assert.throws(
      () => portal.handle(request),
      (error) => {
        assert.ok(error instanceof PortalError, `expected PortalError, got ${error}`);
        assert.equal(error.code, code);
        assert.equal(error.status, status);
        return true;
      },
    );
  };

  expectRejection((r) => ((r.headers.host = "evil.example"), r), "HOST_NOT_ALLOWED", 403);
  expectRejection(
    (r) => ((r.headers.origin = "https://cyberboss.example.evil.com"), r),
    "ORIGIN_NOT_ALLOWED",
    403,
  );
  expectRejection((r) => ((r.headers.origin = "https://evil.example"), r), "ORIGIN_NOT_ALLOWED", 403);
  expectRejection((r) => (delete r.headers.origin, r), "ORIGIN_NOT_ALLOWED", 403);
  expectRejection((r) => ((r.action = "shell.execute"), r), "ACTION_NOT_ALLOWED", 403);
  expectRejection((r) => ((r.action = "provider.save "), r), "ACTION_NOT_ALLOWED", 403);
  expectRejection((r) => (delete r.headers["x-csrf-token"], r), "CSRF_INVALID", 403);
  expectRejection(
    (r) => ((r.headers["x-csrf-token"] = "d".repeat(43)), r),
    "CSRF_INVALID",
    403,
  );
  expectRejection((r) => (delete r.headers.cookie, r), "SESSION_INVALID", 401);
  expectRejection((r) => ((r.method = "GET"), r), "METHOD_NOT_ALLOWED", 405);
  expectRejection(
    (r) => ((r.body = JSON.stringify({ pad: "x".repeat(MAX_BODY_BYTES) })), r),
    "BODY_TOO_LARGE",
    413,
  );
  expectRejection((r) => ((r.body = "{not json"), r), "BODY_NOT_JSON", 400);
  expectRejection((r) => ((r.body = "[1,2,3]"), r), "BODY_NOT_OBJECT", 400);

  // A body that claims another user is refused, not silently honoured.
  expectRejection(
    (r) => ((r.body = JSON.stringify({ user_id: "usr_" + "z".repeat(24) })), r),
    "USER_SCOPE_VIOLATION",
    403,
  );
  // A body naming the session's own user is accepted but the field is dropped.
  const selfClaim = JSON.parse(JSON.stringify(good));
  selfClaim.body = JSON.stringify({ user_id: userId, provider_id: "openai" });
  assert.equal(portal.handle(selfClaim).ok, true);
  assert.equal(saved.at(-1).payload.user_id, undefined);

  // Every allowlisted action must be a plain identifier: no path or wildcard.
  for (const action of ACTION_ALLOWLIST) {
    assert.match(action, /^[a-z]+\.[a-z_]+$/);
  }

  // A revoked user loses the portal in one step.
  const revoked = portal.revokeEverythingForUser(userId);
  assert.ok(revoked.sessionsRevoked >= 1);
  assert.throws(() => portal.handle(good), /SESSION_INVALID/);
});

test("a setup token cannot be exchanged twice for a session", (t) => {
  const h = harness(t);
  const invite = h.invites.issue({ maxUses: 1, ttlMs: 60_000 });
  const started = h.registration.start({
    botAccountRef: BOT,
    senderRef: "s-g",
    inviteCode: invite.code,
  });
  const portal = new SetupPortal({
    database: h.database,
    allowedOrigins: [ORIGIN],
    sessionService: h.sessions,
    setupTokenService: h.setupTokens,
    userRepository: h.users,
    handlers: {},
  });
  const setup = h.setupTokens.issue({
    userId: started.user.user_id,
    purpose: "provider",
  });
  const request = {
    method: "POST",
    action: "session.exchange",
    headers: { host: HOST, origin: ORIGIN },
    body: JSON.stringify({ token: setup.token, purpose: "provider" }),
  };
  assert.equal(portal.handle(request).userId, started.user.user_id);
  assert.throws(
    () => portal.handle(request),
    (error) => error instanceof PortalError && error.code === "LINK_INVALID",
  );
});
