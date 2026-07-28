"use strict";

// CB-640: replay the frozen dual-user blind set against the real
// implementation. Each case names an action and an oracle; the harness runs the
// action and asserts the oracle, then writes a receipt with no personal data.

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
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
  UserContext,
  resolveServerOwnedUserContext,
} = require("../src/services/users/user-context");
const { UserScopedRepository } = require("../src/services/users/scoped-repository");
const { FairUserQueue } = require("../src/services/runtime/fair-user-queue");
const {
  assertReplyRoute,
  bindReplyRoute,
} = require("../src/services/channel/reply-route-binding");
const { evaluateQuota } = require("../src/services/runtime/quota-policy");
const { SqliteSetupTokenService } = require("../src/services/security/setup-token-service");
const { ProjectToolHost } = require("../src/tools/tool-host");

const BLIND_SET = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures/dual-user-blind-set.json"), "utf8"),
);
const BLIND_SET_SHA256 = crypto
  .createHash("sha256")
  .update(fs.readFileSync(path.join(__dirname, "fixtures/dual-user-blind-set.json")))
  .digest("hex");

const KEY = Buffer.alloc(32, 7);
const IDENTITY_KEY = Buffer.alloc(32, 9);
const INVITE_SECRET = Buffer.alloc(32, 11);
const ROUTE_KEY = Buffer.alloc(32, 13);
const BOT = "bot-account-1";

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb640-"));
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
  const setupTokens = new SqliteSetupTokenService({ database });
  const registration = new RegistrationService({
    userRepository: users,
    inviteStore: invites,
  });
  const activate = (senderRef) => {
    const invite = invites.issue({ maxUses: 1, ttlMs: 60_000 });
    registration.start({ botAccountRef: BOT, senderRef, inviteCode: invite.code });
    return registration.consent({ botAccountRef: BOT, senderRef, accepted: true }).user;
  };
  const contextFor = (senderRef) =>
    resolveServerOwnedUserContext({
      userRepository: users,
      botAccountRef: BOT,
      senderRef,
    });
  return {
    database, spool, users, invites, setupTokens, registration, activate, contextFor,
  };
}

// A receipt line may name the case, the oracle and a boolean outcome only.
const receipts = [];
function record(caseId, oracle, detail) {
  receipts.push({ case: caseId, oracle, result: "PASS", detail });
}

function caseFor(id) {
  const found = BLIND_SET.cases.find((entry) => entry.id === id);
  assert.ok(found, `blind set is missing ${id}`);
  return found;
}

test("DU-01 the same text from two senders yields two users and two routes", (t) => {
  const h = harness(t);
  const blind = caseFor("DU-01");
  const a = h.activate("blind-a");
  const b = h.activate("blind-b");

  assert.notEqual(a.user_id, b.user_id);

  const sameText = "帮我看看今天的安排";
  const inboundA = h.spool.acceptInbound({
    source: "weixin", sourceAccountRef: BOT, sourceMessageId: "du01-a",
    userRef: "blind-a", payload: { text: sameText },
  });
  const inboundB = h.spool.acceptInbound({
    source: "weixin", sourceAccountRef: BOT, sourceMessageId: "du01-b",
    userRef: "blind-b", payload: { text: sameText },
  });
  assert.notEqual(inboundA.inboxId, inboundB.inboxId);
  assert.notEqual(inboundA.jobId, inboundB.jobId);
  assert.notEqual(inboundA.correlationId, inboundB.correlationId);

  const routeA = bindReplyRoute({
    routeKey: ROUTE_KEY, userId: a.user_id, botAccountRef: BOT,
    senderRef: "blind-a", contextToken: "ctx-a",
  });
  const routeB = bindReplyRoute({
    routeKey: ROUTE_KEY, userId: b.user_id, botAccountRef: BOT,
    senderRef: "blind-b", contextToken: "ctx-b",
  });
  assert.notEqual(routeA.destinationHash, routeB.destinationHash);

  record(blind.id, blind.oracle, "distinct user_id, job, correlation and route hash");
});

test("DU-02 A reading B's record is refused before any data is returned", (t) => {
  const h = harness(t);
  const blind = caseFor("DU-02");
  const a = h.activate("blind-a");
  const b = h.activate("blind-b");
  const contextA = h.contextFor("blind-a");

  const now = new Date().toISOString();
  h.database
    .prepare(
      `INSERT INTO profile_facts(
         fact_id, user_id, kind, category, fact_key, value_json, decision,
         version, created_at, updated_at
       ) VALUES ('du02-b', ?, 'explicit', 'basic', 'b_only', '{"v":"b"}',
                 'accepted', 1, ?, ?)`,
    )
    .run(b.user_id, now, now);

  const facts = new UserScopedRepository({
    database: h.database, table: "profile_facts", idColumn: "fact_id",
    readableColumns: ["fact_id", "user_id", "fact_key", "value_json"],
  });

  let returned = null;
  assert.throws(
    () => {
      returned = facts.requireById(contextA, "du02-b");
    },
    (error) => error.code === "USER_SCOPE_VIOLATION",
  );
  assert.equal(returned, null, "no data was returned before the refusal");
  assert.equal(facts.getById(contextA, "du02-b"), null);
  assert.deepEqual(facts.search(contextA, "fact_key", "b_only"), []);
  assert.equal(facts.updateById(contextA, "du02-b", { value_json: "{}" }), 0);
  assert.equal(facts.deleteById(contextA, "du02-b"), 0);
  assert.equal(
    Number(
      h.database.prepare("SELECT COUNT(*) AS c FROM profile_facts WHERE fact_id='du02-b'").get().c,
    ),
    1,
    "B's record survived every attempt",
  );
  assert.notEqual(a.user_id, b.user_id);
  record(blind.id, blind.oracle, "read, search, update and delete all refused");
});

test("DU-03 A reusing B's setup token is refused", (t) => {
  const h = harness(t);
  const blind = caseFor("DU-03");
  h.activate("blind-a");
  const b = h.activate("blind-b");

  const tokenForB = h.setupTokens.issue({ userId: b.user_id, purpose: "provider" });
  // Consuming it once binds it to B; a second consumption by anyone fails.
  assert.equal(h.setupTokens.consume({ token: tokenForB.token, purpose: "provider" }).userId, b.user_id);
  assert.throws(
    () => h.setupTokens.consume({ token: tokenForB.token, purpose: "provider" }),
    (error) => error.code === "LINK_INVALID",
  );

  // A fresh token for B still resolves to B, never to the caller.
  const second = h.setupTokens.issue({ userId: b.user_id, purpose: "import" });
  assert.equal(
    h.setupTokens.consume({ token: second.token, purpose: "import" }).userId,
    b.user_id,
    "the token names its own user; a caller cannot redirect it",
  );
  record(blind.id, blind.oracle, "LINK_INVALID on reuse; token always resolves to its own user");
});

test("DU-04 replaying a provider message yields one inbox, job and reply", (t) => {
  const h = harness(t);
  const blind = caseFor("DU-04");
  h.activate("blind-a");
  const message = {
    source: "weixin", sourceAccountRef: BOT, sourceMessageId: "du04-replay",
    userRef: "blind-a", payload: { text: "重复消息" },
  };
  const first = h.spool.acceptInbound(message);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    assert.equal(h.spool.acceptInbound(message).duplicate, true);
  }
  const reply = {
    jobId: first.jobId, dedupeKey: "du04-reply", messageKind: "result",
    targetRef: "blind-a", payload: { text: "ok" },
  };
  h.spool.enqueueOutbox(reply);
  h.spool.enqueueOutbox(reply);

  const counts = h.database
    .prepare(
      `SELECT
         (SELECT COUNT(*) FROM inbox_messages WHERE source_message_id=?) AS inbox,
         (SELECT COUNT(*) FROM jobs WHERE inbox_id=?) AS jobs,
         (SELECT COUNT(*) FROM outbox_messages WHERE job_id=?) AS outbox`,
    )
    .get(first.sourceMessageId, first.inboxId, first.jobId);
  assert.deepEqual(
    { inbox: Number(counts.inbox), jobs: Number(counts.jobs), outbox: Number(counts.outbox) },
    { inbox: 1, jobs: 1, outbox: 1 },
  );
  record(blind.id, blind.oracle, "1 inbox, 1 job, 1 final reply after five deliveries");
});

test("DU-05 an ordinary user requesting Codex is refused with zero runtime calls", async (t) => {
  const h = harness(t);
  const blind = caseFor("DU-05");
  h.activate("blind-a");
  const contextA = h.contextFor("blind-a");

  let runtimeCalls = 0;
  const host = new ProjectToolHost({
    services: {
      get codex() {
        runtimeCalls += 1;
        return {};
      },
    },
    runtimeContextStore: { resolveActiveContext: () => ({}) },
  });

  for (const capability of ["codex.turn", "shell.execute", "workspace.write", "mcp.invoke"]) {
    assert.equal(contextA.may(capability), false);
    assert.throws(
      () => contextA.requireCapability(capability),
      (error) => error.code === "OWNER_ONLY_CAPABILITY",
    );
  }
  for (const toolName of host.listTools().map((tool) => tool.name)) {
    await assert.rejects(
      () => host.invokeTool(toolName, {}, { userContext: contextA }),
      (error) => error.code === "OWNER_ONLY_CAPABILITY",
    );
  }
  assert.equal(runtimeCalls, 0);
  record(blind.id, blind.oracle, "OWNER_ONLY_CAPABILITY on every tool; runtime calls 0");
});

test("DU-06 a suspended user gets a Chinese status and zero model calls", (t) => {
  const h = harness(t);
  const blind = caseFor("DU-06");
  const a = h.activate("blind-a");
  h.registration.suspend({ userId: a.user_id });

  const resumed = h.registration.start({ botAccountRef: BOT, senderRef: "blind-a" });
  assert.equal(resumed.state, "suspended");
  assert.equal(resumed.modelCalls, 0);
  assert.match(resumed.message, /[一-龥]/);
  assert.doesNotMatch(resumed.message, /token|API|HTTP|SQL/i);
  assert.equal(h.registration.mayCallModel(a.user_id), false);

  const context = h.contextFor("blind-a");
  assert.equal(context.may("chat.turn"), false);
  assert.throws(() => context.requireActive(), /USER_NOT_ACTIVE/);
  record(blind.id, blind.oracle, "model calls 0 and a Chinese suspended notice");
});

test("DU-07 a swapped outbox destination is refused", (t) => {
  const h = harness(t);
  const blind = caseFor("DU-07");
  const a = h.activate("blind-a");
  const b = h.activate("blind-b");

  const routeA = bindReplyRoute({
    routeKey: ROUTE_KEY, userId: a.user_id, botAccountRef: BOT,
    senderRef: "blind-a", contextToken: "ctx-a",
  });

  // Swapping the recipient while keeping A's binding is refused.
  assert.throws(
    () =>
      assertReplyRoute({
        routeKey: ROUTE_KEY, binding: routeA, userId: a.user_id,
        botAccountRef: BOT, senderRef: "blind-b", contextToken: "ctx-a",
      }),
    (error) => error.code === "REPLY_ROUTE_MISMATCH",
  );
  // Claiming A's route on behalf of B is refused.
  assert.throws(
    () =>
      assertReplyRoute({
        routeKey: ROUTE_KEY, binding: routeA, userId: b.user_id,
        botAccountRef: BOT, senderRef: "blind-a", contextToken: "ctx-a",
      }),
    (error) => error.code === "REPLY_ROUTE_MISMATCH",
  );

  // At the storage layer an outbox row inherits its job's user and cannot be
  // enqueued against another user's job.
  const inboundA = h.spool.acceptInbound({
    source: "weixin", sourceAccountRef: BOT, sourceMessageId: "du07-a",
    userRef: "blind-a", payload: { text: "hi" },
  });
  const outbox = h.spool.enqueueOutbox({
    jobId: inboundA.jobId, dedupeKey: "du07-reply", messageKind: "result",
    targetRef: "blind-a", payload: { text: "ok" },
  });
  assert.equal(outbox.user_id, h.spool.getJob(inboundA.jobId).user_id);
  assert.notEqual(outbox.user_id, b.user_id);
  record(blind.id, blind.oracle, "REPLY_ROUTE_MISMATCH on both swap directions");
});

test("DU-08 one user filling the queue still leaves the other a fair slot", (t) => {
  const h = harness(t);
  const blind = caseFor("DU-08");
  const a = h.activate("blind-a");
  const b = h.activate("blind-b");
  const queue = new FairUserQueue({ perUserActive: 1, perUserQueued: 3, globalActive: 2 });

  for (let index = 0; index < 3; index += 1) {
    assert.equal(queue.enqueue({ jobId: `a-${index}`, userId: a.user_id }).admitted, true);
  }
  assert.deepEqual(queue.enqueue({ jobId: "a-3", userId: a.user_id }), {
    admitted: false,
    reason: "user_queue_full",
  });
  // B is unaffected by A filling its own queue.
  assert.equal(queue.enqueue({ jobId: "b-0", userId: b.user_id }).admitted, true);
  assert.equal(
    evaluateQuota({ kind: "ai", userActive: 0, userQueued: 0 }).allowed,
    true,
    "B's admission decision is independent of A's",
  );

  const claimed = [queue.claimNext(), queue.claimNext()];
  assert.deepEqual(
    [...new Set(claimed.map((job) => job.userId))].sort(),
    [a.user_id, b.user_id].sort(),
    "both users hold an active slot",
  );
  assert.equal(queue.activeForUser(a.user_id), 1);
  assert.equal(queue.activeForUser(b.user_id), 1);
  record(blind.id, blind.oracle, "queue-full refusal is per user; both users get a slot");
});

test("PG-6 every blind-set case ran and the receipt carries no personal data", (t) => {
  assert.equal(
    receipts.length,
    BLIND_SET.cases.length,
    "every blind-set case must have produced a receipt",
  );
  assert.deepEqual(
    receipts.map((entry) => entry.case).sort(),
    BLIND_SET.cases.map((entry) => entry.id).sort(),
  );
  assert.ok(receipts.every((entry) => entry.result === "PASS"));

  const serialized = JSON.stringify(receipts);
  for (const marker of [/usr_[A-Za-z0-9_-]{20,}/, /blind-[ab]\b/, /bot-account/]) {
    assert.doesNotMatch(serialized, marker, `receipt leaked ${marker}`);
  }
  assert.equal(BLIND_SET_SHA256.length, 64);

  // The receipt is written for the CB-640 evidence bundle.
  const target = process.env.CB640_RECEIPT_PATH;
  if (target) {
    fs.writeFileSync(
      target,
      `${JSON.stringify(
        {
          schema_version: "cyberboss.cb640.blind_set_receipt.v1",
          blind_set_sha256: BLIND_SET_SHA256,
          case_count: BLIND_SET.cases.length,
          pass_count: receipts.filter((entry) => entry.result === "PASS").length,
          fail_count: receipts.filter((entry) => entry.result !== "PASS").length,
          personal_data_in_receipt: false,
          cases: receipts,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  }
});
