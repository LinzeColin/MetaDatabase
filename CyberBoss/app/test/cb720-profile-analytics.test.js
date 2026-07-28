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
  ALLOWED_CATEGORIES,
  ProfileError,
  SENSITIVE_CATEGORIES,
  explainFact,
  projectProfile,
  sensitiveInferenceCount,
  validateFact,
} = require("../src/services/profile/profile-projector");
const { SqliteProfileStore } = require("../src/services/profile/profile-store");
const {
  AnalyticsError,
  SqliteActivityAggregator,
  aggregateDaily,
  seriesForUser,
} = require("../src/services/analytics/activity-aggregator");

const KEY = Buffer.alloc(32, 7);
const IDENTITY_KEY = Buffer.alloc(32, 9);
const INVITE_SECRET = Buffer.alloc(32, 11);
const BOT = "bot-account-1";

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb720-"));
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
  return {
    database,
    activate,
    profiles: new SqliteProfileStore({ database }),
    analytics: new SqliteActivityAggregator({ database }),
  };
}

test("AC-024 every inference carries source, evidence, confidence and counterevidence", () => {
  const good = {
    userId: "usr_" + "a".repeat(24),
    kind: "inferred",
    category: "routine",
    key: "wake_time",
    value: "07:00",
    sourceRef: "import:chatgpt:conv-1",
    evidenceRef: "msg:conv-1:12",
    confidence: 0.72,
    counterevidence: ["msg:conv-3:4"],
  };
  assert.equal(validateFact(good), good);
  assert.deepEqual(explainFact(good), {
    category: "routine",
    key: "wake_time",
    kind: "inferred",
    sourceRef: "import:chatgpt:conv-1",
    evidenceRef: "msg:conv-1:12",
    confidence: 0.72,
    counterevidence: ["msg:conv-3:4"],
    decision: "proposed",
    frozen: false,
  });

  // Each missing element on its own makes the inference unstorable.
  for (const missing of ["sourceRef", "evidenceRef", "confidence", "counterevidence"]) {
    const broken = { ...good };
    delete broken[missing];
    assert.throws(
      () => validateFact(broken),
      (error) => error instanceof ProfileError && error.code === "INFERENCE_EVIDENCE_REQUIRED",
      `an inference without ${missing} must be refused`,
    );
  }
  // Confidence must be a real probability.
  for (const confidence of [0, -1, 1.5, "high", Number.NaN]) {
    assert.throws(
      () => validateFact({ ...good, confidence }),
      /INFERENCE_EVIDENCE_REQUIRED/,
      `confidence ${confidence} must be refused`,
    );
  }
  // An explicit user statement needs no inference machinery.
  assert.doesNotThrow(() =>
    validateFact({ ...good, kind: "explicit", sourceRef: undefined, evidenceRef: undefined, confidence: undefined, counterevidence: undefined }),
  );
  assert.throws(
    () => validateFact({ ...good, category: "astrology" }),
    /PROFILE_CATEGORY_NOT_ALLOWED/,
  );
});

test("AC-026 sensitive attributes are never inferred and need per-category consent", () => {
  const base = {
    userId: "usr_" + "a".repeat(24),
    key: "value",
    value: "x",
    sourceRef: "import:chatgpt:c",
    evidenceRef: "msg:c:1",
    confidence: 0.9,
    counterevidence: [],
  };
  let blocked = 0;
  for (const category of SENSITIVE_CATEGORIES) {
    // No confidence and no consent flag ever permits an inference here.
    assert.throws(
      () => validateFact({ ...base, kind: "inferred", category, explicitSensitiveConsent: category }),
      (error) => error.code === "SENSITIVE_INFERENCE_FORBIDDEN",
      `${category} must never be inferable`,
    );
    // An explicit statement still needs consent for that exact category.
    assert.throws(
      () => validateFact({ ...base, kind: "explicit", category }),
      (error) => error.code === "SENSITIVE_PROFILE_BLOCKED",
    );
    assert.throws(
      () =>
        validateFact({ ...base, kind: "explicit", category, explicitSensitiveConsent: "basic" }),
      (error) => error.code === "SENSITIVE_PROFILE_BLOCKED",
      "consent for one category must not unlock another",
    );
    assert.doesNotThrow(() =>
      validateFact({ ...base, kind: "explicit", category, explicitSensitiveConsent: category }),
    );
    blocked += 1;
  }
  assert.equal(blocked, SENSITIVE_CATEGORIES.length);
  assert.equal(blocked, 9);

  // The default projection contains zero sensitive inferences.
  const projected = projectProfile([
    { ...base, kind: "inferred", category: "routine", key: "wake_time", version: 1 },
  ]);
  assert.equal(sensitiveInferenceCount(projected), 0);
  for (const category of SENSITIVE_CATEGORIES) {
    assert.ok(!ALLOWED_CATEGORIES.includes(category));
  }
});

test("AC-025 accept, modify, reject, freeze and delete take effect immediately", (t) => {
  const h = harness(t);
  const user = h.activate("p-user");
  const inference = {
    userId: user.user_id,
    category: "routine",
    factKey: "wake_time",
    value: "07:00",
    kind: "inferred",
    sourceRef: "import:chatgpt:conv-1",
    evidenceRef: "msg:conv-1:12",
    confidence: 0.72,
    counterevidence: [],
  };
  h.profiles.suggest(inference);
  let projection = h.profiles.projection(user.user_id);
  assert.equal(projection.length, 1);
  assert.equal(projection[0].decision, "proposed");

  // Accept.
  projection = h.profiles.decide({
    userId: user.user_id,
    category: "routine",
    factKey: "wake_time",
    decision: "accepted",
  });
  assert.equal(projection[0].decision, "accepted");

  // Modify changes the stored value immediately.
  projection = h.profiles.decide({
    userId: user.user_id,
    category: "routine",
    factKey: "wake_time",
    decision: "modified",
    value: "06:30",
  });
  assert.equal(projection[0].value, "06:30");

  // Freeze blocks any later suggestion for the same key.
  h.profiles.decide({
    userId: user.user_id,
    category: "routine",
    factKey: "wake_time",
    decision: "frozen",
  });
  assert.equal(h.profiles.projection(user.user_id)[0].frozen, true);
  assert.throws(
    () => h.profiles.suggest({ ...inference, value: "09:00" }),
    (error) => error.code === "PROFILE_FACT_FROZEN",
  );

  // Accepting after a freeze must not silently unfreeze the fact.
  h.profiles.decide({
    userId: user.user_id,
    category: "routine",
    factKey: "wake_time",
    decision: "accepted",
  });
  assert.equal(h.profiles.projection(user.user_id)[0].frozen, true);

  // Reject removes it from the projection and refuses future re-suggestion.
  // These decisions all land in the same millisecond, so the store must order
  // them by insertion rather than by timestamp.
  projection = h.profiles.decide({
    userId: user.user_id,
    category: "routine",
    factKey: "wake_time",
    decision: "rejected",
  });
  assert.equal(projection.length, 0, "a rejected fact leaves the projection at once");
  assert.throws(
    () => h.profiles.suggest({ ...inference, value: "08:00" }),
    (error) => error.code === "PROFILE_SUGGESTION_REFUSED_BY_USER",
    "a rejected inference must not reappear",
  );

  // Delete on another key behaves the same way.
  h.profiles.suggest({ ...inference, factKey: "sleep_time", value: "23:00" });
  assert.equal(h.profiles.projection(user.user_id).length, 1);
  assert.equal(
    h.profiles.decide({
      userId: user.user_id,
      category: "routine",
      factKey: "sleep_time",
      decision: "deleted",
    }).length,
    0,
  );
  assert.throws(
    () => h.profiles.decide({ userId: user.user_id, category: "routine", factKey: "nope", decision: "accepted" }),
    (error) => error.code === "PROFILE_FACT_NOT_FOUND",
  );
});

test("AC-025 one user's profile decisions never touch another user", (t) => {
  const h = harness(t);
  const alice = h.activate("p-alice");
  const bob = h.activate("p-bob");
  const fact = (userId) => ({
    userId,
    category: "preference",
    factKey: "tea",
    value: "green",
    kind: "explicit",
  });
  h.profiles.suggest(fact(alice.user_id));
  h.profiles.suggest(fact(bob.user_id));

  h.profiles.decide({
    userId: alice.user_id,
    category: "preference",
    factKey: "tea",
    decision: "rejected",
  });
  assert.equal(h.profiles.projection(alice.user_id).length, 0);
  assert.equal(
    h.profiles.projection(bob.user_id).length,
    1,
    "Bob's profile is untouched by Alice's rejection",
  );
  // Bob may still be suggested the key Alice rejected.
  assert.doesNotThrow(() =>
    h.profiles.suggest({ ...fact(bob.user_id), factKey: "coffee", value: "black" }),
  );
});

test("AC-027 daily aggregates are deterministic and call no model", (t) => {
  const h = harness(t);
  const user = h.activate("a-user");
  const events = [
    { userId: user.user_id, type: "message", occurredAt: "2026-07-01T10:00:00Z" },
    { userId: user.user_id, type: "message", occurredAt: "2026-07-01T22:00:00Z" },
    { userId: user.user_id, type: "ai_turn", occurredAt: "2026-07-01T10:05:00Z" },
    { userId: user.user_id, type: "import_completed", occurredAt: "2026-07-02T09:00:00Z" },
    { userId: user.user_id, type: "reminder_completed", occurredAt: "2026-07-02T09:30:00Z" },
    { userId: user.user_id, type: "unknown_event", occurredAt: "2026-07-02T09:40:00Z" },
  ];
  const aggregate = aggregateDaily(events);
  assert.equal(aggregate.length, 2);
  assert.equal(aggregate[0].day, "2026-07-01");
  assert.equal(aggregate[0].messages, 2);
  assert.equal(aggregate[0].aiTurns, 1);
  assert.equal(aggregate[1].imports, 1);
  assert.equal(aggregate[1].remindersCompleted, 1);

  // Determinism: any input order yields the same output.
  const shuffled = [...events].reverse();
  assert.deepEqual(aggregateDaily(shuffled), aggregate);
  assert.deepEqual(aggregateDaily(events), aggregate);

  assert.throws(
    () => aggregateDaily([{ type: "message", occurredAt: "2026-07-01T00:00:00Z" }]),
    (error) => error instanceof AnalyticsError,
  );
  assert.throws(
    () => aggregateDaily([{ userId: user.user_id, type: "message", occurredAt: "nope" }]),
    /OCCURRED_AT_INVALID/,
  );
  assert.throws(
    () => seriesForUser(aggregate, user.user_id, "secretMetric"),
    /METRIC_NOT_SUPPORTED/,
  );
  assert.deepEqual(seriesForUser(aggregate, user.user_id, "messages"), [
    { day: "2026-07-01", value: 2 },
    { day: "2026-07-02", value: 0 },
  ]);

  // The aggregate is a projection, not a second authority: rebuilding from a
  // reduced event set removes what is no longer there.
  h.analytics.rebuildForUser(user.user_id, events);
  assert.equal(h.analytics.readForUser(user.user_id).length, 2);
  h.analytics.rebuildForUser(
    user.user_id,
    events.filter((event) => event.occurredAt.startsWith("2026-07-01")),
  );
  const rebuilt = h.analytics.readForUser(user.user_id);
  assert.equal(rebuilt.length, 1, "a deleted event disappears from the aggregate");
  assert.equal(rebuilt[0].day, "2026-07-01");
});

test("AC-027 aggregates never cross a user boundary", (t) => {
  const h = harness(t);
  const alice = h.activate("a-alice");
  const bob = h.activate("a-bob");
  const events = [
    { userId: alice.user_id, type: "message", occurredAt: "2026-07-01T10:00:00Z" },
    { userId: bob.user_id, type: "message", occurredAt: "2026-07-01T10:00:00Z" },
    { userId: bob.user_id, type: "message", occurredAt: "2026-07-01T11:00:00Z" },
  ];
  h.analytics.rebuildForUser(alice.user_id, events);
  h.analytics.rebuildForUser(bob.user_id, events);

  assert.equal(h.analytics.readForUser(alice.user_id)[0].messages, 1);
  assert.equal(h.analytics.readForUser(bob.user_id)[0].messages, 2);
  assert.deepEqual(
    seriesForUser(aggregateDaily(events), alice.user_id, "messages"),
    [{ day: "2026-07-01", value: 1 }],
    "a per-user series contains only that user's counts",
  );
  // Rebuilding one user leaves the other's rows intact.
  h.analytics.rebuildForUser(alice.user_id, []);
  assert.equal(h.analytics.readForUser(alice.user_id).length, 0);
  assert.equal(h.analytics.readForUser(bob.user_id).length, 1);
});

test("profile and analytics reach no model and hold no raw chat", () => {
  for (const relative of [
    "profile/profile-projector.js",
    "profile/profile-store.js",
    "analytics/activity-aggregator.js",
  ]) {
    const source = fs.readFileSync(
      path.join(__dirname, "../src/services", relative),
      "utf8",
    ).toLowerCase();
    for (const marker of ["openai", "anthropic", "generativelanguage", "deepseek", "fetch("]) {
      assert.ok(!source.includes(marker), `${relative} must not reach a provider (${marker})`);
    }
  }
  // The projection stores references to evidence, never the evidence text.
  const projected = projectProfile([
    {
      userId: "usr_" + "a".repeat(24),
      kind: "inferred",
      category: "routine",
      key: "wake_time",
      value: "07:00",
      sourceRef: "import:chatgpt:conv-1",
      evidenceRef: "msg:conv-1:12",
      confidence: 0.5,
      counterevidence: [],
      version: 1,
    },
  ]);
  assert.equal(projected[0].evidenceRef, "msg:conv-1:12");
  assert.ok(!JSON.stringify(projected).includes("我今天早上"));
});
