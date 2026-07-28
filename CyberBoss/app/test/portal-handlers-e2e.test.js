"use strict";

// The setup portal, end to end: a WeChat user takes the single-use link,
// exchanges it for a session, and saves a real provider key — after which the
// same user's next WeChat message is answered by that provider.
//
// The portal here is the production SetupPortal with the production handlers
// bound. Only the provider HTTP call is a fake, and it records every request so
// "the key reached the right origin" is measured rather than asserted.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { UserAdmissionService } = require("../src/core/user-admission");
const { UserTurnRuntime } = require("../src/core/user-turn-runtime");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { SetupPortal } = require("../src/services/portal/setup-portal");
const { buildPortalHandlers } = require("../src/services/portal/portal-handlers");
const { OFFICIAL_ORIGINS } = require("../src/services/providers/router");

const ENCRYPTION_KEY = Buffer.alloc(32, 13);
const IDENTITY_KEY = Buffer.alloc(32, 17);
const BOT = "bot-portal";
const ALICE = "alice-portal";
const BOB = "bob-portal";
const ORIGIN = "https://portal.example.com";

const POLICIES = Object.freeze({
  openai: { providerId: "openai", origin: OFFICIAL_ORIGINS.openai, models: ["gpt-5-mini"] },
  deepseek: { providerId: "deepseek", origin: OFFICIAL_ORIGINS.deepseek, models: ["deepseek-chat"] },
  google: { providerId: "google", origin: OFFICIAL_ORIGINS.google, models: ["gemini-2.5-flash"] },
  anthropic: { providerId: "anthropic", origin: OFFICIAL_ORIGINS.anthropic, models: ["claude-sonnet-5"] },
});

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-portal-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());

  const providerCalls = [];
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: [],
    registrationMode: "invite",
    portalOrigin: ORIGIN,
  });
  const turnRuntime = new UserTurnRuntime({
    database: spool.database,
    userRepository: admission.users,
    encryptionKey: ENCRYPTION_KEY,
    providerPolicies: POLICIES,
    fetchImpl: async (url, init) => {
      providerCalls.push({
        url: String(url),
        authorization: init?.headers?.Authorization || init?.headers?.authorization || "",
      });
      return {
        ok: true,
        status: 200,
        async text() {
          return JSON.stringify({ output_text: "答案", usage: { input_tokens: 5, output_tokens: 3 } });
        },
      };
    },
  });
  const portal = new SetupPortal({
    database: spool.database,
    allowedOrigins: [ORIGIN],
    userRepository: admission.users,
    handlers: buildPortalHandlers({
      database: spool.database,
      vault: turnRuntime.vault,
      userRepository: admission.users,
      providerPolicies: POLICIES,
    }),
  });

  const register = (senderRef) => {
    const invite = admission.issueInvite({ maxUses: 1, ttlMs: 600_000 });
    admission.admit({ botAccountRef: BOT, senderRef, text: invite.code });
    admission.admit({ botAccountRef: BOT, senderRef, text: "同意并开始" });
    return admission.admit({ botAccountRef: BOT, senderRef, text: "hi" }).userContext;
  };

  // The real flow: 「设置」 mints the link, the browser exchanges its token.
  const openSession = (senderRef) => {
    const decision = admission.admit({ botAccountRef: BOT, senderRef, text: "设置" });
    const url = new URL(decision.text.match(/https:\/\/\S+/)[0]);
    const params = new URLSearchParams(url.hash.slice(1));
    return portal.handle({
      method: "POST",
      action: "session.exchange",
      headers: { host: new URL(ORIGIN).host, origin: ORIGIN },
      body: JSON.stringify({ token: params.get("t"), purpose: params.get("p") }),
    });
  };

  const call = (session, action, payload) =>
    portal.handle({
      method: "POST",
      action,
      headers: {
        host: new URL(ORIGIN).host,
        origin: ORIGIN,
        cookie: session.setCookie,
        "x-csrf-token": session.csrf,
      },
      body: JSON.stringify(payload),
    });

  return { spool, admission, turnRuntime, portal, register, openSession, call, providerCalls };
}

test("a user saves a key on the setup page and their next message reaches that provider", async (t) => {
  const h = harness(t);
  const alice = h.register(ALICE);

  const session = h.openSession(ALICE);
  const saved = h.call(session, "provider.save", {
    provider_id: "openai",
    api_key: "sk-alice-real-key",
    model_id: "gpt-5-mini",
  });

  assert.equal(saved.ok, true);
  assert.equal(saved.provider_id, "openai");
  assert.equal(saved.model_id, "gpt-5-mini");
  assert.equal(saved.last4, "-key");
  // The key itself never comes back out of the portal.
  assert.equal(JSON.stringify(saved).includes("sk-alice-real-key"), false);

  const reply = await h.turnRuntime.handleTurn({
    userContext: alice,
    text: "今天天气怎么样",
    requestId: "utr_after_setup",
  });

  assert.equal(reply.ok, true);
  assert.equal(reply.text, "答案");
  assert.equal(h.providerCalls.length, 1);
  assert.match(h.providerCalls[0].url, /^https:\/\/api\.openai\.com\//);
  assert.match(h.providerCalls[0].authorization, /sk-alice-real-key$/);
});

test("the setup link is single use and cannot be replayed", (t) => {
  const h = harness(t);
  h.register(ALICE);

  const decision = h.admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: "设置" });
  const url = new URL(decision.text.match(/https:\/\/\S+/)[0]);
  const params = new URLSearchParams(url.hash.slice(1));
  const exchange = () =>
    h.portal.handle({
      method: "POST",
      action: "session.exchange",
      headers: { host: new URL(ORIGIN).host, origin: ORIGIN },
      body: JSON.stringify({ token: params.get("t"), purpose: params.get("p") }),
    });

  assert.ok(exchange().setCookie);
  assert.throws(exchange, (error) => error.status === 401);
});

test("a session cannot act for another user, whatever the body says", (t) => {
  const h = harness(t);
  const alice = h.register(ALICE);
  const bob = h.register(BOB);
  const session = h.openSession(ALICE);

  assert.throws(
    () => h.call(session, "provider.save", {
      user_id: bob.userId,
      provider_id: "openai",
      api_key: "sk-stolen",
    }),
    (error) => error.code === "USER_SCOPE_VIOLATION" && error.status === 403,
  );

  // Alice's own save still works, and lands under Alice's id only.
  h.call(session, "provider.save", { provider_id: "openai", api_key: "sk-alice" });
  assert.equal(h.turnRuntime.vault.listCredentials(alice.userId).length, 1);
  assert.equal(h.turnRuntime.vault.listCredentials(bob.userId).length, 0);
});

test("the portal refuses a wrong origin, a wrong host and a missing CSRF token", (t) => {
  const h = harness(t);
  h.register(ALICE);
  const session = h.openSession(ALICE);
  const body = JSON.stringify({ provider_id: "openai", api_key: "sk-x" });
  const host = new URL(ORIGIN).host;

  assert.throws(
    () => h.portal.handle({
      method: "POST",
      action: "provider.save",
      headers: { host, origin: "https://evil-portal.example.com", cookie: session.setCookie, "x-csrf-token": session.csrf },
      body,
    }),
    (error) => error.code === "ORIGIN_NOT_ALLOWED",
  );
  assert.throws(
    () => h.portal.handle({
      method: "POST",
      action: "provider.save",
      headers: { host: "portal.example.com.evil.test", origin: ORIGIN, cookie: session.setCookie, "x-csrf-token": session.csrf },
      body,
    }),
    (error) => error.code === "HOST_NOT_ALLOWED",
  );
  assert.throws(
    () => h.portal.handle({
      method: "POST",
      action: "provider.save",
      headers: { host, origin: ORIGIN, cookie: session.cookie },
      body,
    }),
    (error) => error.code === "CSRF_INVALID" || error.code === "SESSION_INVALID",
  );
});

test("removing a provider takes the user off the model path without deleting them", async (t) => {
  const h = harness(t);
  const alice = h.register(ALICE);
  const session = h.openSession(ALICE);
  h.call(session, "provider.save", { provider_id: "openai", api_key: "sk-alice" });

  const removed = h.call(session, "provider.remove", { provider_id: "openai" });
  assert.equal(removed.ok, true);

  const reply = await h.turnRuntime.handleTurn({
    userContext: alice,
    text: "在吗",
    requestId: "utr_after_remove",
  });
  assert.equal(reply.ok, false);
  assert.equal(reply.code, "PROVIDER_NOT_CONFIGURED");
  assert.equal(reply.modelCalls, 0);
  assert.equal(h.providerCalls.length, 0);
  assert.equal(h.admission.users.getById(alice.userId).status, "active");
});

test("the export carries this user's rows only", (t) => {
  const h = harness(t);
  const alice = h.register(ALICE);
  h.register(BOB);
  const session = h.openSession(ALICE);

  const result = h.call(session, "privacy.export", {});

  assert.equal(result.ok, true);
  const serialized = JSON.stringify(result.manifest);
  assert.equal(serialized.includes(alice.userId), true);
  assert.equal(
    serialized.includes(h.admission.users.resolveByPrincipal({
      channel: "weixin",
      botAccountRef: BOT,
      senderRef: BOB,
    }).user_id),
    false,
    "another user's id must not appear in an export",
  );
});

test("the deletion plan is returned for confirmation and names its irreversible steps", (t) => {
  const h = harness(t);
  h.register(ALICE);
  const session = h.openSession(ALICE);

  const result = h.call(session, "privacy.delete", { request_id: "del_00000000000000000001" });

  assert.equal(result.ok, true);
  assert.equal(result.steps.length, 9);
  assert.equal(result.completed_steps, 0, "returning a plan must not execute any step");
  assert.deepEqual(result.irreversible_steps, [
    "delete_r2_user_objects",
    "destroy_user_data_key",
  ]);
});

test("an action with no handler bound answers not-implemented rather than succeeding", (t) => {
  const h = harness(t);
  h.register(ALICE);
  const session = h.openSession(ALICE);

  assert.throws(
    () => h.call(session, "session.logout", {}),
    (error) => error.code === "ACTION_NOT_IMPLEMENTED" && error.status === 501,
  );
});
