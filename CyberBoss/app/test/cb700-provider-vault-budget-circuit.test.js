"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { SqliteUserRepository } = require("../src/services/users/user-repository");
const { SqliteInviteCodeStore } = require("../src/services/users/invite-code-store");
const { RegistrationService } = require("../src/services/users/registration-service");
const {
  CredentialVaultError,
  SqliteCredentialVault,
  createWrappedUserKey,
  decryptCredential,
  encryptCredential,
  unwrapUserKey,
} = require("../src/services/secrets/credential-vault");
const {
  ProviderPolicyError,
  assertPolicy,
} = require("../src/services/providers/policy");
const { OFFICIAL_ORIGINS, ProviderRouter } = require("../src/services/providers/router");
const { normalizeHttpError } = require("../src/services/providers/errors");
const {
  SqliteCircuitStore,
  SqliteModelBudgetLedger,
} = require("../src/services/runtime/sqlite-model-budget-store");
const { ModelBudgetGuard } = require("../src/services/runtime/model-budget-guard");
const {
  ProviderCircuitBreaker,
} = require("../src/services/runtime/provider-circuit-breaker");
const {
  ModelRuntimeController,
} = require("../src/services/runtime/model-runtime-controller");
const {
  normalizeProviderUsage,
} = require("../src/services/runtime/usage-normalizer");

const KEY = Buffer.alloc(32, 7);
const IDENTITY_KEY = Buffer.alloc(32, 9);
const INVITE_SECRET = Buffer.alloc(32, 11);
const MASTER_KEK = Buffer.alloc(32, 17);
const BOT = "bot-account-1";
const API_KEY = "sk-test-abcdefghijklmnop1234";

const POLICIES = Object.freeze({
  openai: { providerId: "openai", origin: OFFICIAL_ORIGINS.openai, models: ["gpt-5-mini"] },
  deepseek: { providerId: "deepseek", origin: OFFICIAL_ORIGINS.deepseek, models: ["deepseek-v4-flash"] },
  google: { providerId: "google", origin: OFFICIAL_ORIGINS.google, models: ["gemini-3-flash"] },
  anthropic: { providerId: "anthropic", origin: OFFICIAL_ORIGINS.anthropic, models: ["claude-sonnet-5"] },
});

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb700-"));
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

  const users = new SqliteUserRepository({ database, identityKey: IDENTITY_KEY });
  const invites = new SqliteInviteCodeStore({ database, secret: INVITE_SECRET });
  const registration = new RegistrationService({
    userRepository: users,
    inviteStore: invites,
  });
  const activate = (senderRef) => {
    const invite = invites.issue({ maxUses: 1, ttlMs: 60_000 });
    registration.start({ botAccountRef: BOT, senderRef, inviteCode: invite.code });
    return registration.consent({ botAccountRef: BOT, senderRef, accepted: true }).user;
  };
  const vault = new SqliteCredentialVault({ database, masterKey: MASTER_KEK });
  return { database, spool, users, vault, activate };
}

// A fake clock the whole runtime shares, so no test ever waits on real time.
function fakeClock(start = 1_700_000_000_000) {
  let now = start;
  return {
    now: () => now,
    advance: (ms) => {
      now += ms;
    },
  };
}

function stack(t, { fetchImpl, clock = fakeClock(), timeoutMs = 60_000 } = {}) {
  const h = harness(t);
  const ledger = new SqliteModelBudgetLedger({
    database: h.database,
    clock: clock.now,
  });
  const budgetGuard = new ModelBudgetGuard({ ledger, clock: clock.now });
  const circuitBreaker = new ProviderCircuitBreaker({
    store: new SqliteCircuitStore({ database: h.database, clock: clock.now }),
    clock: clock.now,
  });
  const router = new ProviderRouter({ policies: POLICIES, fetchImpl });
  const timers = [];
  const controller = new ModelRuntimeController({
    router,
    budgetGuard,
    circuitBreaker,
    requestTimeoutMs: timeoutMs,
    // A fake timer: nothing fires unless a test fires it.
    setTimeoutImpl: (fn) => {
      const entry = { fn, fired: false };
      timers.push(entry);
      return entry;
    },
    clearTimeoutImpl: (entry) => {
      if (entry) {
        entry.cleared = true;
      }
    },
  });
  return { ...h, ledger, budgetGuard, circuitBreaker, router, controller, clock, timers };
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  };
}

test("AC-012 the vault wraps a per-user DEK and binds every layer to its scope", (t) => {
  const h = harness(t);
  const alice = h.activate("v-alice");
  const bob = h.activate("v-bob");

  h.vault.putCredential({ userId: alice.user_id, providerId: "openai", apiKey: API_KEY });
  h.vault.putCredential({ userId: bob.user_id, providerId: "openai", apiKey: "sk-bob-999988887777" });

  assert.equal(h.vault.getCredential({ userId: alice.user_id, providerId: "openai" }), API_KEY);
  assert.notEqual(
    h.vault.getCredential({ userId: bob.user_id, providerId: "openai" }),
    API_KEY,
  );

  // No plaintext anywhere in the database.
  const dump = JSON.stringify(
    h.database.prepare("SELECT * FROM provider_credentials").all(),
  );
  assert.ok(!dump.includes(API_KEY), "plaintext key must never be stored");
  assert.ok(dump.includes("abcd".slice(0, 0) + API_KEY.slice(-4)), "only last4 is visible");
  assert.ok(
    !JSON.stringify(h.database.prepare("SELECT * FROM user_data_keys").all()).includes(
      MASTER_KEK.toString("base64url"),
    ),
  );

  // Scope binding: Alice's ciphertext cannot be read as Bob's, nor as another
  // provider, even with the same master key.
  const aliceRow = JSON.parse(
    h.database
      .prepare(
        "SELECT ciphertext_json FROM provider_credentials WHERE user_id=? AND provider_id='openai'",
      )
      .get(alice.user_id).ciphertext_json,
  );
  const aliceKeyRow = JSON.parse(
    h.database.prepare("SELECT wrapped_key_json FROM user_data_keys WHERE user_id=?").get(alice.user_id)
      .wrapped_key_json,
  );
  const aliceKey = unwrapUserKey({
    masterKey: MASTER_KEK,
    userId: alice.user_id,
    envelope: aliceKeyRow,
  });
  assert.throws(
    () =>
      decryptCredential({
        userKey: aliceKey,
        userId: bob.user_id,
        providerId: "openai",
        record: aliceRow,
      }),
    (error) => error.code === "VAULT_SCOPE_MISMATCH",
  );
  assert.throws(
    () =>
      decryptCredential({
        userKey: aliceKey,
        userId: alice.user_id,
        providerId: "anthropic",
        record: aliceRow,
      }),
    (error) => error.code === "VAULT_SCOPE_MISMATCH",
  );
  assert.throws(
    () =>
      unwrapUserKey({
        masterKey: MASTER_KEK,
        userId: bob.user_id,
        envelope: aliceKeyRow,
      }),
    (error) => error.code === "USER_KEY_SCOPE_MISMATCH",
  );
  // A wrong master key cannot unwrap either.
  assert.throws(
    () =>
      unwrapUserKey({
        masterKey: Buffer.alloc(32, 99),
        userId: alice.user_id,
        envelope: aliceKeyRow,
      }),
    (error) => error.code === "USER_KEY_AUTHENTICATION_FAILED",
  );

  // Rotation keeps the credential readable under a new key version.
  const rotated = h.vault.rotateUserKey(alice.user_id);
  assert.equal(rotated.keyVersion, 2);
  assert.equal(h.vault.getCredential({ userId: alice.user_id, providerId: "openai" }), API_KEY);

  // Crypto-shred destroys the wrapped DEK: residual ciphertext is unreadable.
  h.vault.cryptoShred(alice.user_id);
  assert.throws(
    () => h.vault.getCredential({ userId: alice.user_id, providerId: "openai" }),
    (error) => error instanceof CredentialVaultError,
  );
  assert.equal(
    h.vault.getCredential({ userId: bob.user_id, providerId: "openai" }),
    "sk-bob-999988887777",
    "shredding one user leaves the other intact",
  );
  // Listing is safe to show a user: no ciphertext, no plaintext.
  const listed = h.vault.listCredentials(bob.user_id);
  assert.equal(listed.length, 1);
  assert.ok(!JSON.stringify(listed).includes("sk-bob-999988887777"));
});

test("AC-013..AC-016 four adapters use fixed origins and allowlisted models", async (t) => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, headers: options.headers, body: JSON.parse(options.body) });
    if (url.includes("openai")) {
      return jsonResponse({ output_text: "hi", usage: { input_tokens: 3, output_tokens: 4, total_tokens: 7 } });
    }
    if (url.includes("deepseek")) {
      return jsonResponse({
        choices: [{ message: { content: "hi" } }],
        usage: { prompt_tokens: 3, completion_tokens: 4, total_tokens: 7 },
      });
    }
    if (url.includes("generativelanguage")) {
      return jsonResponse({
        candidates: [{ content: { parts: [{ text: "hi" }] } }],
        usageMetadata: { promptTokenCount: 3, candidatesTokenCount: 4, totalTokenCount: 7 },
      });
    }
    return jsonResponse({
      content: [{ type: "text", text: "hi" }],
      usage: { input_tokens: 3, output_tokens: 4 },
    });
  };
  const router = new ProviderRouter({ policies: POLICIES, fetchImpl });
  const messages = [{ role: "user", content: "你好" }];

  for (const [providerId, model] of [
    ["openai", "gpt-5-mini"],
    ["deepseek", "deepseek-v4-flash"],
    ["google", "gemini-3-flash"],
    ["anthropic", "claude-sonnet-5"],
  ]) {
    const result = await router.sendText({
      providerId,
      apiKey: API_KEY,
      model,
      messages,
      maxOutputTokens: 100,
    });
    assert.equal(result.provider, providerId);
    assert.equal(result.text, "hi");
    const normalized = normalizeProviderUsage(providerId, result.usage);
    assert.equal(normalized.reported, true, `${providerId} usage must normalize`);
    assert.equal(normalized.totalTokens, 7);
  }

  // Every request went to the official origin over HTTPS.
  for (const call of calls) {
    assert.match(call.url, /^https:\/\//);
    assert.ok(
      Object.values(OFFICIAL_ORIGINS).some((origin) => call.url.startsWith(origin)),
      `unexpected origin ${call.url}`,
    );
  }
  // Gemini authenticates by header, not query string.
  const gemini = calls.find((call) => call.url.includes("generativelanguage"));
  assert.equal(gemini.headers["x-goog-api-key"], API_KEY);
  assert.ok(!gemini.url.includes(API_KEY), "the key must not appear in the URL");
  // Anthropic pins its version header.
  const anthropic = calls.find((call) => call.url.includes("api.anthropic.com"));
  assert.equal(anthropic.headers["anthropic-version"], "2023-06-01");
  assert.equal(anthropic.headers["x-api-key"], API_KEY);
  // OpenAI opts out of provider-side retention.
  const openai = calls.find((call) => call.url.includes("api.openai.com"));
  assert.equal(openai.body.store, false);

  // A model outside the allowlist is refused before any request is made.
  const before = calls.length;
  await assert.rejects(
    () =>
      router.sendText({
        providerId: "openai",
        apiKey: API_KEY,
        model: "gpt-5-mini-evil",
        messages,
      }),
    (error) => error.code === "MODEL_NOT_ALLOWED",
  );
  assert.equal(calls.length, before, "a rejected model must not reach the network");

  // A user cannot introduce a base URL: policies are constructed at startup and
  // a non-official origin is refused outright.
  assert.throws(
    () =>
      new ProviderRouter({
        policies: {
          ...POLICIES,
          openai: { providerId: "openai", origin: "https://evil.example", models: ["gpt-5-mini"] },
        },
        fetchImpl,
      }),
    (error) => error.code === "PROVIDER_ORIGIN_NOT_OFFICIAL",
  );
  assert.throws(
    () => assertPolicy({ providerId: "openai", origin: "http://api.openai.com", models: ["m"] }),
    (error) => error instanceof ProviderPolicyError,
  );
  assert.throws(
    () => assertPolicy({ providerId: "openai", origin: "https://api.openai.com/v1", models: ["m"] }),
    /PROVIDER_ORIGIN_MUST_BE_BARE_HTTPS/,
  );
});

test("AC-045 the hard budget denies without ever calling the provider", async (t) => {
  let providerCalls = 0;
  const s = stack(t, {
    fetchImpl: async () => {
      providerCalls += 1;
      return jsonResponse({ output_text: "hi", usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 } });
    },
  });
  const user = s.activate("b-user");
  const base = {
    userId: user.user_id,
    providerId: "openai",
    model: "gpt-5-mini",
    apiKey: API_KEY,
    messages: [{ role: "user", content: "你好" }],
  };

  const ok = await s.controller.sendText({ ...base, requestId: "req-1" });
  assert.equal(ok.ok, true);
  assert.equal(providerCalls, 1);

  // A message larger than the per-request reservation cap is refused with zero
  // provider calls.
  const huge = await s.controller.sendText({
    ...base,
    requestId: "req-2",
    messages: [{ role: "user", content: "x".repeat(20_000) }],
  });
  assert.equal(huge.ok, false);
  assert.equal(huge.code, "REQUEST_TOKEN_BUDGET_EXCEEDED");
  assert.equal(huge.modelCalls, 0);
  assert.equal(providerCalls, 1);

  // Exhaust the daily budget, then prove the next call is denied before dispatch.
  const tight = new ModelBudgetGuard({
    ledger: s.ledger,
    clock: s.clock.now,
    policy: { perUserDailyTokens: 10 },
  });
  const controller = new ModelRuntimeController({
    router: s.router,
    budgetGuard: tight,
    circuitBreaker: s.circuitBreaker,
    setTimeoutImpl: () => ({}),
    clearTimeoutImpl: () => {},
  });
  const denied = await controller.sendText({ ...base, requestId: "req-3" });
  assert.equal(denied.ok, false);
  assert.equal(denied.code, "USER_DAILY_TOKEN_BUDGET_EXHAUSTED");
  assert.equal(denied.modelCalls, 0);
  assert.equal(providerCalls, 1, "a denied request calls the provider zero times");
  assert.match(denied.message, /[一-龥]/);

  // AC-046: request_id is idempotent inside the user scope.
  const replay = await s.controller.sendText({ ...base, requestId: "req-1" });
  assert.equal(replay.ok, false);
  assert.equal(replay.code, "DUPLICATE_MODEL_REQUEST");
  assert.equal(replay.modelCalls, 0);
  assert.equal(providerCalls, 1);

  // The same request id belonging to a different user is not a duplicate.
  const other = s.activate("b-other");
  const otherOk = await s.controller.sendText({
    ...base,
    userId: other.user_id,
    requestId: "req-1",
  });
  assert.equal(otherOk.ok, true, "request ids do not collide across users");
  assert.equal(providerCalls, 2);
});

test("AC-046 missing usage and crashed reservations charge the full reservation", (t) => {
  const clock = fakeClock();
  const s = stack(t, { fetchImpl: async () => jsonResponse({}), clock });
  const user = s.activate("u-settle");

  // Missing usage settles at the reserved amount, not zero.
  const reserved = s.budgetGuard.preflight({
    requestId: "r-missing",
    userId: user.user_id,
    providerId: "openai",
    messages: [{ role: "user", content: "hello" }],
  });
  assert.equal(reserved.allowed, true);
  const settled = s.budgetGuard.settle({
    reservationId: reserved.reservationId,
    providerId: "openai",
    rawUsage: null,
  });
  assert.equal(settled.reported, false);
  assert.equal(settled.chargedTokens, reserved.reservedTokens);
  assert.equal(settled.fuseAccounting, "reservation_fallback");

  // A reservation whose process died is charged in full once its TTL passes.
  const orphan = s.budgetGuard.preflight({
    requestId: "r-crash",
    userId: user.user_id,
    providerId: "openai",
    messages: [{ role: "user", content: "hello" }],
  });
  const before = s.ledger.totals({ userId: user.user_id }).dailyUsedTokens;
  clock.advance(10 * 60 * 1000 + 1);
  assert.equal(s.ledger.expireReservations(), 1);
  const after = s.ledger.totals({ userId: user.user_id }).dailyUsedTokens;
  assert.equal(after - before, orphan.reservedTokens);
  const row = s.database
    .prepare("SELECT state, charge_mode, reason_code FROM model_budget_reservations WHERE reservation_id=?")
    .get(orphan.reservationId);
  assert.equal(row.state, "expired_charged");
  assert.equal(row.charge_mode, "reservation_fallback");
  assert.equal(row.reason_code, "RESERVATION_EXPIRED");

  // Reported usage settles at the actual amount.
  const actual = s.budgetGuard.preflight({
    requestId: "r-actual",
    userId: user.user_id,
    providerId: "anthropic",
    messages: [{ role: "user", content: "hello" }],
  });
  const settledActual = s.budgetGuard.settle({
    reservationId: actual.reservationId,
    providerId: "anthropic",
    rawUsage: { input_tokens: 11, output_tokens: 7 },
  });
  assert.equal(settledActual.reported, true);
  assert.equal(settledActual.chargedTokens, 18);
  assert.ok(settledActual.chargedTokens < actual.reservedTokens);
});

test("AC-046 a successful answer survives an accounting outage", async (t) => {
  const s = stack(t, {
    fetchImpl: async () =>
      jsonResponse({ output_text: "答案", usage: { input_tokens: 2, output_tokens: 3, total_tokens: 5 } }),
  });
  const user = s.activate("u-outage");
  // Break settlement only.
  s.budgetGuard.settle = () => {
    throw new Error("accounting store unavailable");
  };
  const result = await s.controller.sendText({
    requestId: "r-outage",
    userId: user.user_id,
    providerId: "openai",
    model: "gpt-5-mini",
    apiKey: API_KEY,
    messages: [{ role: "user", content: "你好" }],
  });
  assert.equal(result.ok, true, "the user keeps the answer they already paid for");
  assert.equal(result.response.text, "答案");
  assert.equal(result.accountingDegraded, true);
  assert.equal(result.response.usage.fuseAccounting, "pending_conservative_reservation");
  // The reservation stays active so its TTL charges conservatively.
  assert.equal(
    s.database
      .prepare("SELECT state FROM model_budget_reservations WHERE request_id=?")
      .get("r-outage").state,
    "reserved",
  );
});

test("AC-017 timeout and external cancel are handled differently", async (t) => {
  let providerCalls = 0;
  const s = stack(t, {
    fetchImpl: (url, options) =>
      new Promise((resolve, reject) => {
        providerCalls += 1;
        options.signal.addEventListener("abort", () => {
          const reason = options.signal.reason;
          reject(reason instanceof Error ? reason : Object.assign(new Error("aborted"), { code: "REQUEST_CANCELLED" }));
        });
      }),
  });
  const user = s.activate("u-timeout");
  const base = {
    userId: user.user_id,
    providerId: "openai",
    model: "gpt-5-mini",
    apiKey: API_KEY,
    messages: [{ role: "user", content: "你好" }],
  };

  // A bounded timeout exists by default and produces its own code.
  const pending = s.controller.sendText({ ...base, requestId: "r-timeout" });
  s.timers.at(-1).fn();
  const timedOut = await pending;
  assert.equal(timedOut.ok, false);
  assert.equal(timedOut.code, "TIMEOUT");
  assert.match(timedOut.message, /[一-龥]/);
  // A timeout is provider evidence, so it counts against the global circuit.
  assert.equal(
    s.database.prepare("SELECT consecutive_failures FROM provider_circuits WHERE circuit_key='global:openai'").get()
      .consecutive_failures,
    1,
  );

  // An external cancel is the user's choice and must not poison the circuit.
  const controllerAbort = new AbortController();
  const cancelling = s.controller.sendText({
    ...base,
    requestId: "r-cancel",
    signal: controllerAbort.signal,
  });
  controllerAbort.abort();
  const cancelled = await cancelling;
  assert.equal(cancelled.ok, false);
  assert.equal(cancelled.code, "REQUEST_CANCELLED");
  assert.equal(
    s.database.prepare("SELECT consecutive_failures FROM provider_circuits WHERE circuit_key='global:openai'").get()
      .consecutive_failures,
    1,
    "an external cancel does not increment provider failures",
  );
  assert.equal(providerCalls, 2);

  // Error messages carry no secret and no provider body.
  for (const result of [timedOut, cancelled]) {
    assert.ok(!JSON.stringify(result).includes(API_KEY));
  }
  const normalized = normalizeHttpError("openai", 401, "detailed provider body with sk-secret");
  assert.equal(normalized.code, "CREDENTIAL_INVALID");
  assert.ok(!JSON.stringify(normalized).includes("sk-secret"));
  assert.match(normalized.message, /[一-龥]/);
});

test("AC-017/AC-047 a bad key breaks only that user, an outage breaks the provider", async (t) => {
  const clock = fakeClock();
  let status = 401;
  const s = stack(t, {
    clock,
    fetchImpl: async () =>
      status === 200
        ? jsonResponse({
            output_text: "hi",
            usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
          })
        : jsonResponse({ error: "nope" }, status),
  });
  const alice = s.activate("c-alice");
  const bob = s.activate("c-bob");
  const call = (userId, requestId) =>
    s.controller.sendText({
      requestId,
      userId,
      providerId: "openai",
      model: "gpt-5-mini",
      apiKey: API_KEY,
      messages: [{ role: "user", content: "你好" }],
    });

  const aliceFail = await call(alice.user_id, "a-1");
  assert.equal(aliceFail.code, "CREDENTIAL_INVALID");
  // Alice's circuit is open; Bob is untouched.
  const aliceBlocked = await call(alice.user_id, "a-2");
  assert.equal(aliceBlocked.code, "USER_PROVIDER_CIRCUIT_OPEN");
  assert.equal(aliceBlocked.modelCalls, 0);
  status = 200;
  const bobOk = await call(bob.user_id, "b-1");
  assert.equal(bobOk.ok, true, "another user is unaffected by Alice's bad key");
  assert.equal(bobOk.response.text, "hi");

  // A rejected credential releases the reservation: the user is not charged.
  assert.equal(
    s.database.prepare("SELECT state FROM model_budget_reservations WHERE request_id='a-1'").get().state,
    "released",
  );

  // Global scope: repeated 5xx opens the provider for everyone.
  status = 503;
  for (let index = 0; index < 5; index += 1) {
    await call(bob.user_id, `b-5xx-${index}`);
  }
  const globalOpen = await call(bob.user_id, "b-after");
  assert.equal(globalOpen.code, "PROVIDER_CIRCUIT_OPEN");
  assert.equal(globalOpen.scope, "global");
  assert.equal(globalOpen.modelCalls, 0);

  // Fake clock cooldown, then exactly one half-open probe.
  clock.advance(60_001);
  status = 200;
  const probe = s.circuitBreaker.beforeRequest({ userId: bob.user_id, providerId: "openai" });
  assert.equal(probe.allowed, true);
  assert.equal(probe.probes.global, true);
  const second = s.circuitBreaker.beforeRequest({ userId: bob.user_id, providerId: "openai" });
  assert.equal(second.allowed, false, "only one half-open probe at a time");

  // A probe whose completion is lost recovers once its lease expires.
  clock.advance(30_001);
  const afterLease = s.circuitBreaker.beforeRequest({ userId: bob.user_id, providerId: "openai" });
  assert.equal(afterLease.allowed, true, "an expired probe lease releases the circuit");

  // Aggregate status carries no user dimension.
  const aggregate = s.circuitBreaker.aggregateStatus();
  assert.ok(aggregate.length >= 1);
  assert.ok(!JSON.stringify(aggregate).includes("usr_"));
});

test("AC-047 a user-scope denial releases the global probe it did not use", (t) => {
  const clock = fakeClock();
  const s = stack(t, { clock, fetchImpl: async () => jsonResponse({}) });
  const user = s.activate("c-probe");

  // Open both circuits, then let only the global one become eligible.
  for (let index = 0; index < 5; index += 1) {
    s.circuitBreaker.recordFailure({
      userId: user.user_id,
      providerId: "openai",
      code: "PROVIDER_UNAVAILABLE",
    });
  }
  s.circuitBreaker.recordFailure({
    userId: user.user_id,
    providerId: "openai",
    code: "CREDENTIAL_INVALID",
  });
  clock.advance(60_001);

  const denied = s.circuitBreaker.beforeRequest({ userId: user.user_id, providerId: "openai" });
  assert.equal(denied.allowed, false);
  assert.equal(denied.scope, "user_provider");
  // The global probe granted a moment ago must have been released, otherwise
  // the provider would stay wedged behind a probe that never ran.
  const globalRow = s.database
    .prepare("SELECT probe_in_flight FROM provider_circuits WHERE circuit_key='global:openai'")
    .get();
  assert.equal(Number(globalRow.probe_in_flight), 0);
});

test("AC-048 usage observability is aggregate and carries no identity", (t) => {
  const clock = fakeClock();
  const s = stack(t, { clock, fetchImpl: async () => jsonResponse({}) });
  const alice = s.activate("o-alice");
  const bob = s.activate("o-bob");

  for (const [userId, providerId, requestId] of [
    [alice.user_id, "openai", "o-1"],
    [bob.user_id, "openai", "o-2"],
    [bob.user_id, "anthropic", "o-3"],
  ]) {
    const reserved = s.budgetGuard.preflight({
      requestId,
      userId,
      providerId,
      messages: [{ role: "user", content: "hello" }],
    });
    s.budgetGuard.settle({
      reservationId: reserved.reservationId,
      providerId,
      rawUsage:
        providerId === "anthropic"
          ? { input_tokens: 5, output_tokens: 5 }
          : { input_tokens: 5, output_tokens: 5, total_tokens: 10 },
    });
  }

  const aggregate = s.ledger.aggregateByProvider();
  const serialized = JSON.stringify(aggregate);
  assert.equal(aggregate.length, 2);
  assert.equal(aggregate.find((row) => row.providerId === "openai").calls, 2);
  assert.equal(aggregate.find((row) => row.providerId === "openai").totalTokens, 20);
  // No user id, prompt, response or secret in the observable projection.
  assert.ok(!serialized.includes("usr_"));
  assert.ok(!serialized.includes("hello"));
  assert.ok(!serialized.includes(API_KEY));
  assert.deepEqual(
    Object.keys(aggregate[0]).sort(),
    ["calls", "fallbackCharges", "inputTokens", "outputTokens", "providerId", "totalTokens"],
  );

  const circuitAggregate = s.circuitBreaker.aggregateStatus();
  assert.ok(!JSON.stringify(circuitAggregate).includes("usr_"));
});

test("the runtime performs no background model call", (t) => {
  let providerCalls = 0;
  const clock = fakeClock();
  const s = stack(t, {
    clock,
    fetchImpl: async () => {
      providerCalls += 1;
      return jsonResponse({});
    },
  });
  const user = s.activate("z-user");

  // Every control-plane operation the runtime performs on its own.
  s.ledger.totals({ userId: user.user_id });
  s.ledger.expireReservations();
  s.ledger.aggregateByProvider();
  s.circuitBreaker.aggregateStatus();
  s.circuitBreaker.beforeRequest({ userId: user.user_id, providerId: "openai" });
  s.vault.listCredentials(user.user_id);
  clock.advance(24 * 60 * 60 * 1000);
  s.ledger.expireReservations();
  s.ledger.aggregateByProvider();

  assert.equal(providerCalls, 0, "no background or health model call is made");
});
