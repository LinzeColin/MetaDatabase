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
  RegistrationService,
} = require("../src/services/users/registration-service");
const {
  OWNER_ONLY_CAPABILITIES,
  USER_CAPABILITIES,
  UserContext,
  UserContextError,
  resolveServerOwnedUserContext,
} = require("../src/services/users/user-context");
const {
  ScopedRepositoryError,
  UserScopedRepository,
} = require("../src/services/users/scoped-repository");
const {
  FairQueueError,
  FairUserQueue,
} = require("../src/services/runtime/fair-user-queue");
const {
  ReplyRouteError,
  assertReplyRoute,
  bindReplyRoute,
  resolveOutboundDestination,
} = require("../src/services/channel/reply-route-binding");
const { LIMITS, evaluateQuota } = require("../src/services/runtime/quota-policy");
const { ProjectToolHost } = require("../src/tools/tool-host");

const KEY = Buffer.alloc(32, 7);
const IDENTITY_KEY = Buffer.alloc(32, 9);
const INVITE_SECRET = Buffer.alloc(32, 11);
const ROUTE_KEY = Buffer.alloc(32, 13);
const BOT = "bot-account-1";

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb630-"));
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
    return registration.consent({ botAccountRef: BOT, senderRef, accepted: true })
      .user;
  };

  return { database, spool, users, invites, registration, activate, directory };
}

function contextFor(h, senderRef) {
  return resolveServerOwnedUserContext({
    userRepository: h.users,
    botAccountRef: BOT,
    senderRef,
  });
}

test("UserContext is server-owned, frozen and fails closed", (t) => {
  const h = harness(t);
  const user = h.activate("s-a");
  const context = contextFor(h, "s-a");

  assert.equal(context.userId, user.user_id);
  assert.equal(context.role, "user");
  assert.equal(context.isOwner, false);
  assert.throws(() => {
    context.role = "owner";
  }, TypeError, "a context must be frozen");

  // The redacted projection must never carry an identifier.
  const redacted = context.toRedactedJson();
  assert.deepEqual(Object.keys(redacted).sort(), ["channel", "role", "status"]);
  assert.ok(!JSON.stringify(redacted).includes(user.user_id));

  assert.throws(
    () => new UserContext({ userId: "admin", role: "owner", status: "active" }),
    (error) => error instanceof UserContextError && error.code === "USER_CONTEXT_ID_INVALID",
  );
  assert.throws(
    () => new UserContext({ userId: user.user_id, role: "superuser" }),
    /USER_CONTEXT_ROLE_INVALID/,
  );
  assert.throws(
    () =>
      resolveServerOwnedUserContext({
        userRepository: h.users,
        botAccountRef: BOT,
        senderRef: "never-seen",
      }),
    /USER_NOT_FOUND/,
  );
  assert.throws(
    () =>
      resolveServerOwnedUserContext({
        userRepository: h.users,
        botAccountRef: BOT,
        senderRef: null,
      }),
    /PRINCIPAL_REQUIRED/,
  );

  // A suspended user keeps its identity but loses every capability.
  h.users.setStatus(user.user_id, "suspended");
  const suspended = contextFor(h, "s-a");
  assert.equal(suspended.may("chat.turn"), false);
  assert.throws(() => suspended.requireActive(), /USER_NOT_ACTIVE/);
});

test("Owner-only capabilities are unreachable for an ordinary user", (t) => {
  const h = harness(t);
  h.activate("s-b");
  const user = contextFor(h, "s-b");
  const owner = new UserContext({
    userId: h.spool.ownerUserId,
    role: "owner",
    status: "active",
  });

  // The two capability sets must be disjoint, or a "user" capability could
  // smuggle an Owner one.
  for (const capability of USER_CAPABILITIES) {
    assert.ok(
      !OWNER_ONLY_CAPABILITIES.includes(capability),
      `${capability} appears in both sets`,
    );
  }

  let refusals = 0;
  for (const capability of OWNER_ONLY_CAPABILITIES) {
    assert.equal(user.may(capability), false, `${capability} leaked to a user`);
    assert.equal(owner.may(capability), true, `${capability} denied to the Owner`);
    assert.throws(
      () => user.requireCapability(capability),
      (error) => error.code === "OWNER_ONLY_CAPABILITY",
    );
    refusals += 1;
  }
  assert.equal(refusals, OWNER_ONLY_CAPABILITIES.length);
  assert.equal(refusals, 11);

  for (const capability of USER_CAPABILITIES) {
    assert.equal(user.may(capability), true, `${capability} denied to a user`);
  }
  // An unknown capability is denied to everyone, including the Owner.
  assert.equal(user.may("not.a.capability"), false);
  assert.equal(owner.may("not.a.capability"), false);
});

test("the tool host refuses every non-Owner invocation before running a tool", async (t) => {
  const h = harness(t);
  h.activate("s-c");
  const user = contextFor(h, "s-c");
  const owner = new UserContext({
    userId: h.spool.ownerUserId,
    role: "owner",
    status: "active",
  });

  let sideEffects = 0;
  const host = new ProjectToolHost({
    services: {
      get timeline() {
        sideEffects += 1;
        return {};
      },
    },
    runtimeContextStore: { resolveActiveContext: () => ({}) },
  });

  const toolNames = host.listTools().map((tool) => tool.name);
  assert.ok(toolNames.length > 0);

  let denied = 0;
  for (const toolName of [...toolNames, "definitely_not_a_tool"]) {
    await assert.rejects(
      () => host.invokeTool(toolName, {}, { userContext: user }),
      (error) => error.code === "OWNER_ONLY_CAPABILITY",
      `${toolName} was reachable by an ordinary user`,
    );
    denied += 1;
  }
  assert.equal(denied, toolNames.length + 1);
  assert.equal(sideEffects, 0, "no tool body ran for an ordinary user");

  // An unknown tool still reaches the normal not-found path for the Owner,
  // proving the guard runs before lookup rather than replacing it.
  await assert.rejects(
    () => host.invokeTool("definitely_not_a_tool", {}, { userContext: owner }),
    /Unknown tool/,
  );

  // A forged context object that is not a real UserContext is refused too.
  await assert.rejects(
    () =>
      host.invokeTool(toolNames[0], {}, {
        userContext: { userId: "usr_" + "a".repeat(24), role: "owner" },
      }),
    (error) => error.code === "OWNER_ONLY_CAPABILITY",
  );
});

test("a scoped repository cannot reach another user's row", (t) => {
  const h = harness(t);
  const alice = h.activate("s-alice");
  const bob = h.activate("s-bob");
  const aliceContext = contextFor(h, "s-alice");
  const bobContext = contextFor(h, "s-bob");

  const now = new Date().toISOString();
  for (const [userId, factKey] of [
    [alice.user_id, "alice-secret"],
    [bob.user_id, "bob-secret"],
  ]) {
    h.database
      .prepare(
        `INSERT INTO profile_facts(
           fact_id, user_id, kind, category, fact_key, value_json, decision,
           version, created_at, updated_at
         ) VALUES (?, ?, 'explicit', 'basic', ?, '{}', 'accepted', 1, ?, ?)`,
      )
      .run(`fact-${factKey}`, userId, factKey, now, now);
  }

  const facts = new UserScopedRepository({
    database: h.database,
    table: "profile_facts",
    idColumn: "fact_id",
    readableColumns: ["fact_id", "user_id", "fact_key", "value_json"],
  });

  assert.equal(facts.count(aliceContext), 1);
  assert.equal(facts.count(bobContext), 1);
  assert.equal(facts.getById(aliceContext, "fact-alice-secret").fact_key, "alice-secret");

  // Read, search, update and delete across the boundary all fail.
  assert.equal(facts.getById(aliceContext, "fact-bob-secret"), null);
  assert.throws(
    () => facts.requireById(aliceContext, "fact-bob-secret"),
    (error) => error.code === "USER_SCOPE_VIOLATION",
  );
  assert.throws(
    () => facts.requireById(aliceContext, "fact-does-not-exist"),
    (error) => error.code === "RECORD_NOT_FOUND",
  );
  assert.deepEqual(
    facts.search(aliceContext, "fact_key", "secret").map((row) => row.fact_key),
    ["alice-secret"],
  );
  assert.equal(facts.updateById(aliceContext, "fact-bob-secret", { value_json: "{}" }), 0);
  assert.equal(facts.deleteById(aliceContext, "fact-bob-secret"), 0);
  assert.equal(facts.count(bobContext), 1, "bob's row survived alice's delete");

  // Re-homing a record to another user is refused outright.
  assert.throws(
    () => facts.updateById(aliceContext, "fact-alice-secret", { user_id: bob.user_id }),
    (error) => error.code === "USER_SCOPE_VIOLATION",
  );

  // Identifier interpolation is guarded; values stay bound parameters.
  assert.throws(
    () =>
      new UserScopedRepository({
        database: h.database,
        table: "profile_facts; DROP TABLE users",
      }),
    (error) => error instanceof ScopedRepositoryError,
  );
  assert.throws(
    () => facts.search(aliceContext, "fact_key = 1 OR 1", "x"),
    (error) => error instanceof ScopedRepositoryError,
  );
  // A LIKE wildcard in user input is escaped, not honoured.
  assert.deepEqual(facts.search(aliceContext, "fact_key", "%"), []);

  // No context, or a suspended one, cannot read anything.
  assert.throws(() => facts.list(null), /USER_CONTEXT_REQUIRED/);
  h.users.setStatus(alice.user_id, "suspended");
  assert.throws(() => facts.list(contextFor(h, "s-alice")), /USER_NOT_ACTIVE/);
});

test("the fair queue keeps one active turn per user and rotates between users", () => {
  const queue = new FairUserQueue({ perUserActive: 1, perUserQueued: 3, globalActive: 2 });

  assert.equal(queue.enqueue({ jobId: "a1", userId: "usr_a" }).admitted, true);
  assert.equal(queue.enqueue({ jobId: "a2", userId: "usr_a" }).admitted, true);
  assert.equal(queue.enqueue({ jobId: "b1", userId: "usr_b" }).admitted, true);

  // AC-009: the same job id is never admitted twice.
  assert.deepEqual(queue.enqueue({ jobId: "a1", userId: "usr_a" }), {
    admitted: false,
    reason: "duplicate_job",
  });

  // AC-044: a fourth queued item for one user is refused.
  assert.equal(queue.enqueue({ jobId: "a3", userId: "usr_a" }).admitted, true);
  assert.deepEqual(queue.enqueue({ jobId: "a4", userId: "usr_a" }), {
    admitted: false,
    reason: "user_queue_full",
  });
  // The refusal is per user: usr_b is unaffected.
  assert.equal(queue.enqueue({ jobId: "b2", userId: "usr_b" }).admitted, true);

  const first = queue.claimNext();
  const second = queue.claimNext();
  assert.notEqual(first.userId, second.userId, "the queue rotates between users");
  assert.equal(queue.activeForUser("usr_a"), 1);
  assert.equal(queue.activeForUser("usr_b"), 1);

  // Global limit reached: nothing more is claimable even though work remains.
  assert.equal(queue.claimNext(), null);
  assert.equal(queue.metrics().active_total, 2);

  queue.complete(first.jobId);
  const third = queue.claimNext();
  assert.equal(third.userId, first.userId, "the freed user gets its next turn");
  assert.equal(queue.activeForUser(first.userId), 1);
  assert.throws(() => queue.complete("never-active"), (error) => error instanceof FairQueueError);

  // Metrics carry counts only, never a user identifier.
  const metrics = queue.metrics();
  assert.ok(!JSON.stringify(metrics).includes("usr_"));
});

test("Owner Codex turns are limited on their own lane", () => {
  const queue = new FairUserQueue({
    perUserActive: 1,
    perUserQueued: 3,
    globalActive: 3,
    ownerActive: 1,
  });
  queue.enqueue({ jobId: "o1", userId: "usr_owner", isOwner: true });
  queue.enqueue({ jobId: "o2", userId: "usr_owner", isOwner: true });
  queue.enqueue({ jobId: "u1", userId: "usr_user" });

  const claimed = [queue.claimNext(), queue.claimNext(), queue.claimNext()].filter(
    Boolean,
  );
  const ownerClaims = claimed.filter((job) => job.isOwner);
  assert.equal(ownerClaims.length, 1, "the Owner lane stays at one active turn");
  assert.ok(
    claimed.some((job) => job.userId === "usr_user"),
    "a busy Owner does not starve an ordinary user",
  );
});

test("a reply route is bound once and cannot be redirected", () => {
  const binding = bindReplyRoute({
    routeKey: ROUTE_KEY,
    userId: "usr_" + "a".repeat(24),
    botAccountRef: BOT,
    senderRef: "sender-a",
    contextToken: "ctx-1",
  });

  assert.equal(
    assertReplyRoute({
      routeKey: ROUTE_KEY,
      binding,
      userId: binding.userId,
      botAccountRef: BOT,
      senderRef: "sender-a",
      contextToken: "ctx-1",
    }),
    true,
  );

  // Every single-field substitution must be refused with the same code.
  const mutations = [
    { userId: "usr_" + "b".repeat(24) },
    { botAccountRef: "bot-account-2" },
    { senderRef: "sender-b" },
    { contextToken: "ctx-2" },
  ];
  for (const mutation of mutations) {
    assert.throws(
      () =>
        assertReplyRoute({
          routeKey: ROUTE_KEY,
          binding,
          userId: binding.userId,
          botAccountRef: BOT,
          senderRef: "sender-a",
          contextToken: "ctx-1",
          ...mutation,
        }),
      (error) =>
        error instanceof ReplyRouteError && error.code === "REPLY_ROUTE_MISMATCH",
      `mutation ${JSON.stringify(mutation)} was accepted`,
    );
  }

  // A tampered binding object cannot redirect the outbound message.
  const tampered = { ...binding, senderRef: "sender-b" };
  assert.throws(
    () =>
      resolveOutboundDestination({
        routeKey: ROUTE_KEY,
        binding: tampered,
        expectedUserId: binding.userId,
      }),
    /REPLY_ROUTE_MISMATCH/,
  );
  // A's binding cannot be delivered on behalf of B.
  assert.throws(
    () =>
      resolveOutboundDestination({
        routeKey: ROUTE_KEY,
        binding,
        expectedUserId: "usr_" + "b".repeat(24),
      }),
    /REPLY_ROUTE_MISMATCH/,
  );
  assert.deepEqual(
    resolveOutboundDestination({
      routeKey: ROUTE_KEY,
      binding,
      expectedUserId: binding.userId,
    }),
    { botAccountRef: BOT, senderRef: "sender-a", contextToken: "ctx-1" },
  );

  // Field boundaries are unambiguous.
  const left = bindReplyRoute({
    routeKey: ROUTE_KEY,
    userId: "usr_" + "a".repeat(24),
    botAccountRef: "ab",
    senderRef: "c",
    contextToken: "ctx",
  });
  const right = bindReplyRoute({
    routeKey: ROUTE_KEY,
    userId: "usr_" + "a".repeat(24),
    botAccountRef: "a",
    senderRef: "bc",
    contextToken: "ctx",
  });
  assert.notEqual(left.destinationHash, right.destinationHash);

  assert.throws(
    () =>
      bindReplyRoute({
        routeKey: Buffer.alloc(16),
        userId: "usr_" + "a".repeat(24),
        botAccountRef: BOT,
        senderRef: "sender-a",
        contextToken: "ctx-1",
      }),
    /REPLY_ROUTE_KEY_MUST_BE_AT_LEAST_32_BYTES/,
  );
});

test("a duplicated provider message yields one inbox, one job and one reply", (t) => {
  const h = harness(t);
  const message = {
    source: "weixin",
    sourceAccountRef: BOT,
    sourceMessageId: "provider-msg-1",
    userRef: "sender-a",
    payload: { text: "hello" },
  };

  const first = h.spool.acceptInbound(message);
  const second = h.spool.acceptInbound(message);
  const third = h.spool.acceptInbound(message);

  assert.equal(first.duplicate, false);
  assert.equal(second.duplicate, true);
  assert.equal(third.duplicate, true);
  assert.equal(second.inboxId, first.inboxId);
  assert.equal(second.jobId, first.jobId);

  const counts = h.database
    .prepare(
      `SELECT
         (SELECT COUNT(*) FROM inbox_messages WHERE source_message_id=?) AS inbox,
         (SELECT COUNT(*) FROM jobs WHERE inbox_id=?) AS jobs`,
    )
    .get(first.sourceMessageId, first.inboxId);
  assert.equal(Number(counts.inbox), 1);
  assert.equal(Number(counts.jobs), 1);

  // The final reply is enqueued once for the same dedupe key.
  const reply = { jobId: first.jobId, dedupeKey: "reply-1", messageKind: "result", targetRef: "sender-a", payload: { text: "ok" } };
  const enqueued = h.spool.enqueueOutbox(reply);
  const again = h.spool.enqueueOutbox(reply);
  assert.equal(again.id, enqueued.id);
  assert.equal(
    Number(
      h.database
        .prepare("SELECT COUNT(*) AS c FROM outbox_messages WHERE job_id=?")
        .get(first.jobId).c,
    ),
    1,
  );
});

test("quota refusals are deterministic Chinese and never consume a model call", () => {
  const allowed = evaluateQuota({ kind: "ai", text: "你好" });
  assert.equal(allowed.allowed, true);
  assert.equal(allowed.modelCalls, 0);

  const cases = [
    [{ kind: "ai", text: "x".repeat(LIMITS.maxTextBytes + 1) }, "TEXT_TOO_LARGE"],
    [{ kind: "ai", userActive: 1 }, "USER_ACTIVE_BUSY"],
    [{ kind: "ai", userQueued: 3 }, "USER_QUEUE_FULL"],
    [{ kind: "ai", globalProviderActive: 2 }, "GLOBAL_PROVIDER_BUSY"],
    [{ kind: "import", globalImportActive: 1 }, "IMPORT_BUSY"],
    [{ kind: "nonsense" }, "KIND_INVALID"],
  ];
  for (const [input, code] of cases) {
    const result = evaluateQuota(input);
    assert.equal(result.allowed, false, `${code} should refuse`);
    assert.equal(result.code, code);
    assert.equal(result.modelCalls, 0, `${code} must not consume a model call`);
    assert.match(result.message, /[一-龥]/, `${code} must answer in Chinese`);
    assert.doesNotMatch(result.message, /token|quota|HTTP|429|API/i);
    // The same input always yields the same wording: no model in the loop.
    assert.deepEqual(evaluateQuota(input), result);
  }

  assert.equal(LIMITS.perUserActive, 1);
  assert.equal(LIMITS.perUserQueued, 3);
  assert.equal(LIMITS.globalProviderActive, 2);
  assert.equal(LIMITS.globalImportActive, 1);
  assert.equal(LIMITS.maxTextBytes, 32768);

  // One user hitting a limit does not change another user's outcome.
  assert.equal(
    evaluateQuota({ kind: "ai", userActive: 0, userQueued: 0 }).allowed,
    true,
  );
});
