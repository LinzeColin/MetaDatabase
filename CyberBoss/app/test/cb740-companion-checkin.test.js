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
  UserContext,
  resolveServerOwnedUserContext,
} = require("../src/services/users/user-context");
const {
  COMPANION_CAPABILITIES,
  UserCompanionService,
} = require("../src/services/companion/user-companion-service");
const {
  TEMPLATES,
  decideCheckin,
  inQuietHours,
} = require("../src/services/checkin/deterministic-checkin");
const {
  OWNER_ONLY_CAPABILITIES,
} = require("../src/services/users/user-context");

const KEY = Buffer.alloc(32, 7);
const IDENTITY_KEY = Buffer.alloc(32, 9);
const INVITE_SECRET = Buffer.alloc(32, 11);
const BOT = "bot-account-1";
const HOUR = 60 * 60 * 1000;

function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb740-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const databasePath = path.join(directory, "runtime.db");
  const spool = new RuntimeSpoolDatabase({
    databasePath, encryptionKey: KEY, identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  const database = new DatabaseSync(databasePath);
  t.after(() => database.close());
  database.exec("PRAGMA foreign_keys=ON");
  const users = new SqliteUserRepository({ database, identityKey: IDENTITY_KEY });
  const invites = new SqliteInviteCodeStore({ database, secret: INVITE_SECRET });
  const registration = new RegistrationService({ userRepository: users, inviteStore: invites });
  const activate = (senderRef) => {
    const invite = invites.issue({ maxUses: 1, ttlMs: 60_000 });
    registration.start({ botAccountRef: BOT, senderRef, inviteCode: invite.code });
    return registration.consent({ botAccountRef: BOT, senderRef, accepted: true }).user;
  };
  const contextFor = (senderRef) =>
    resolveServerOwnedUserContext({ userRepository: users, botAccountRef: BOT, senderRef });
  return {
    database, spool, users, activate, contextFor,
    companion: new UserCompanionService({ database }),
  };
}

test("AC-031 timeline, diary and reminders are isolated per user", (t) => {
  const h = harness(t);
  const alice = h.activate("c-alice");
  const bob = h.activate("c-bob");
  const a = h.contextFor("c-alice");
  const b = h.contextFor("c-bob");

  const aliceDiary = h.companion.writeDiary(a, { text: "今天跑了五公里" });
  h.companion.writeDiary(b, { text: "今天在看书" });
  h.companion.createReminder(a, { title: "交房租", dueAt: "2026-08-01T09:00:00Z" });

  const aliceTimeline = h.companion.timeline(a);
  const bobTimeline = h.companion.timeline(b);
  assert.equal(aliceTimeline.length, 2);
  assert.equal(bobTimeline.length, 1);
  assert.ok(
    aliceTimeline.every((row) => row.user_id === alice.user_id),
    "Alice's timeline contains only her rows",
  );
  assert.ok(!JSON.stringify(bobTimeline).includes("跑了五公里"));
  assert.equal(h.companion.listReminders(a).length, 1);
  assert.equal(h.companion.listReminders(b).length, 0);

  // Deleting another user's entry changes nothing.
  assert.equal(h.companion.deleteEntry(b, aliceDiary.factId), false);
  assert.equal(h.companion.timeline(a).length, 2, "Alice's entry survived Bob's delete");
  assert.equal(h.companion.deleteEntry(a, aliceDiary.factId), true);
  assert.equal(h.companion.timeline(a).length, 1);

  // A suspended user loses the surface entirely.
  h.users.setStatus(alice.user_id, "suspended");
  assert.throws(() => h.companion.timeline(h.contextFor("c-alice")), /USER_NOT_ACTIVE/);
});

test("AC-031 the companion surface reaches no Owner capability", (t) => {
  const h = harness(t);
  h.activate("c-user");
  const user = h.contextFor("c-user");

  for (const capability of COMPANION_CAPABILITIES) {
    assert.ok(
      !OWNER_ONLY_CAPABILITIES.includes(capability),
      `${capability} is an Owner capability`,
    );
    assert.equal(user.may(capability), true);
  }
  for (const capability of OWNER_ONLY_CAPABILITIES) {
    assert.equal(user.may(capability), false);
  }
  // No context at all, and a forged one, are both refused.
  assert.throws(() => h.companion.timeline(null), /USER_CONTEXT_REQUIRED/);
  assert.throws(
    () => h.companion.timeline({ userId: "usr_" + "z".repeat(24) }),
    /USER_CONTEXT_REQUIRED/,
  );
  // An Owner context may use the same surface; it simply sees its own scope.
  const owner = new UserContext({
    userId: h.spool.ownerUserId, role: "owner", status: "active",
  });
  assert.deepEqual(h.companion.timeline(owner), []);
});

test("AC-043 check-in decisions are deterministic and cost nothing", () => {
  // 08:00 local on 2026-07-01, +08:00.
  const morning = Date.parse("2026-07-01T00:30:00Z");
  const evening = Date.parse("2026-07-01T09:00:00Z");
  const night = Date.parse("2026-07-01T15:00:00Z");

  const decisions = [
    [{ enabled: true, nowMs: morning }, true, "morning"],
    [{ enabled: true, nowMs: evening }, true, "evening"],
    [{ enabled: true, nowMs: night }, false, null],
    [{ enabled: false, nowMs: morning }, false, null],
  ];
  for (const [input, shouldSend, slot] of decisions) {
    const result = decideCheckin(input);
    assert.equal(result.send, shouldSend, JSON.stringify(input));
    assert.equal(result.modelCalls, 0, "no path may consume a model call");
    if (shouldSend) {
      assert.equal(result.slot, slot);
      assert.match(result.text, /[一-龥]/);
      assert.equal(result.text, TEMPLATES[slot]);
    }
    // Identical input always produces an identical decision.
    assert.deepEqual(decideCheckin(input), result);
  }

  assert.equal(decideCheckin({ enabled: false, nowMs: morning }).reason, "disabled_by_user");
  assert.equal(decideCheckin({ enabled: true, nowMs: night }).reason, "quiet_hours");
  assert.equal(
    decideCheckin({ enabled: true, nowMs: morning, lastCheckinMs: morning - HOUR }).reason,
    "too_soon",
  );

  // Quiet hours wrap around midnight.
  assert.equal(inQuietHours(23, { start: 22, end: 8 }), true);
  assert.equal(inQuietHours(3, { start: 22, end: 8 }), true);
  assert.equal(inQuietHours(9, { start: 22, end: 8 }), false);
  // A same-day window works too.
  assert.equal(inQuietHours(13, { start: 12, end: 14 }), true);
  assert.equal(inQuietHours(15, { start: 12, end: 14 }), false);
});

test("AC-043 turning check-in off produces exactly zero proactive messages", (t) => {
  const h = harness(t);
  h.activate("c-quiet");
  const user = h.contextFor("c-quiet");

  // Off by default until the user opts in.
  assert.equal(h.companion.checkinEnabled(user), false);
  let sent = 0;
  const sweepDays = (days) => {
    for (let day = 0; day < days; day += 1) {
      for (let hour = 0; hour < 24; hour += 1) {
        const plan = h.companion.planProactiveMessage(user, {
          nowMs: Date.parse("2026-07-01T00:00:00Z") + day * 24 * HOUR + hour * HOUR,
          lastCheckinMs: null,
        });
        assert.equal(plan.modelCalls, 0);
        if (plan.send) {
          sent += 1;
        }
      }
    }
  };
  sweepDays(7);
  assert.equal(sent, 0, "a disabled user receives zero proactive messages over a week");

  h.companion.setCheckinEnabled(user, true);
  assert.equal(h.companion.checkinEnabled(user), true);
  sent = 0;
  sweepDays(1);
  assert.ok(sent > 0, "an opted-in user does receive check-ins");

  h.companion.setCheckinEnabled(user, false);
  sent = 0;
  sweepDays(7);
  assert.equal(sent, 0, "turning it back off silences it again");
});

test("AC-028 the same principal keeps one companion state across clients", (t) => {
  const h = harness(t);
  const user = h.activate("c-continuity");
  const first = h.contextFor("c-continuity");
  h.companion.writeDiary(first, { text: "第一台设备写的" });

  // A second client is the same principal: same user id, same entries.
  const second = h.contextFor("c-continuity");
  assert.equal(second.userId, first.userId);
  assert.equal(h.companion.timeline(second).length, 1);
  assert.equal(h.users.countByRole("user"), 1, "no second account is created");
  h.companion.writeDiary(second, { text: "第二台设备写的" });
  assert.equal(h.companion.timeline(first).length, 2, "both clients share one timeline");
  assert.equal(user.user_id, first.userId);

  // Entries written inside the same millisecond must not collide: a timestamp
  // alone is not a unique identity.
  const burst = Array.from({ length: 25 }, (_unused, index) =>
    h.companion.writeDiary(first, { text: `连发第 ${index} 条` }),
  );
  assert.equal(new Set(burst.map((entry) => entry.factId)).size, 25);
  assert.equal(h.companion.timeline(first, { limit: 100 }).length, 27);
  const reminders = Array.from({ length: 25 }, (_unused, index) =>
    h.companion.createReminder(first, { title: `任务 ${index}`, dueAt: "2026-08-01T09:00:00Z" }),
  );
  assert.equal(new Set(reminders.map((entry) => entry.factId)).size, 25);
  assert.equal(h.companion.listReminders(first, { limit: 100 }).length, 25);
});

test("the companion and check-in path reaches no model", () => {
  const checkin = fs.readFileSync(
    path.join(__dirname, "../src/services/checkin/deterministic-checkin.js"),
    "utf8",
  );
  assert.ok(!checkin.includes("require("), "the check-in module imports nothing at all");
  const companion = fs.readFileSync(
    path.join(__dirname, "../src/services/companion/user-companion-service.js"),
    "utf8",
  ).toLowerCase();
  for (const marker of ["openai", "anthropic", "generativelanguage", "fetch(", "sendtext"]) {
    assert.ok(!companion.includes(marker), `companion must not reach a provider (${marker})`);
  }
});
