"use strict";

// CB-740 / AC-031, AC-043: the ordinary-user companion surface.
//
// Timeline, diary and reminders already exist as Owner-era services. This wraps
// them with a server-owned user scope rather than forking them: every read and
// write goes through a UserScopedRepository, so an ordinary user sees only
// their own entries, and the tool set an ordinary user can reach is disjoint
// from the Owner's.

const { randomUUID } = require("node:crypto");
const { UserScopedRepository } = require("../users/scoped-repository");
const { UserContextError } = require("../users/user-context");
const { decideCheckin } = require("../checkin/deterministic-checkin");

// Everything an ordinary user may do here. Deliberately contains no Codex,
// workspace, shell or project-tool capability.
const COMPANION_CAPABILITIES = Object.freeze([
  "timeline.read",
  "diary.write",
  "reminder.manage",
]);

class CompanionError extends Error {
  constructor(code) {
    super(code);
    this.name = "CompanionError";
    this.code = code;
  }
}

class UserCompanionService {
  constructor({ database, now = () => new Date() }) {
    if (!database || typeof database.prepare !== "function") {
      throw new CompanionError("DATABASE_REQUIRED");
    }
    this.database = database;
    this.now = now;
    // Reminders, diary entries and timeline items live in the canonical
    // profile/activity tables; each is reached only through a scoped view.
    this.facts = new UserScopedRepository({
      database,
      table: "profile_facts",
      idColumn: "fact_id",
      readableColumns: ["fact_id", "user_id", "category", "fact_key", "value_json", "updated_at"],
      orderColumn: "updated_at",
    });
    this.activity = new UserScopedRepository({
      database,
      table: "activity_daily",
      idColumn: "day",
      readableColumns: ["user_id", "day", "metrics_json", "updated_at"],
      orderColumn: "day",
    });
  }

  #timestamp() {
    const value = this.now();
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) {
      throw new CompanionError("CLOCK_INVALID");
    }
    return date.toISOString();
  }

  // Every entry point starts here, so there is no path that skips the scope.
  #require(context, capability) {
    if (!context || typeof context.requireCapability !== "function") {
      throw new UserContextError("USER_CONTEXT_REQUIRED");
    }
    context.requireCapability(capability);
    return context;
  }

  timeline(context, { limit = 50 } = {}) {
    this.#require(context, "timeline.read");
    return this.facts.list(context, { limit });
  }

  writeDiary(context, { text }) {
    this.#require(context, "diary.write");
    if (typeof text !== "string" || text.trim().length === 0 || text.length > 8000) {
      throw new CompanionError("DIARY_TEXT_INVALID");
    }
    const now = this.#timestamp();
    // A timestamp alone is not a unique entry identity: two entries written in
    // the same millisecond would collide on the primary key and on the
    // (user, category, fact_key, version) uniqueness constraint. The random
    // component makes each entry distinct regardless of clock resolution.
    const entryId = randomUUID();
    const factId = `diary_${entryId}`;
    this.database
      .prepare(
        `INSERT INTO profile_facts(
           fact_id, user_id, kind, category, fact_key, value_json, decision,
           frozen, version, created_at, updated_at
         ) VALUES (?, ?, 'explicit', 'routine', ?, ?, 'accepted', 0, 1, ?, ?)`,
      )
      .run(
        factId,
        context.userId,
        `diary:${now}:${entryId}`,
        JSON.stringify({ text }),
        now,
        now,
      );
    return Object.freeze({ factId, at: now });
  }

  listReminders(context, { limit = 50 } = {}) {
    this.#require(context, "reminder.manage");
    return this.facts
      .list(context, { limit: 200 })
      .filter((row) => row.fact_key.startsWith("reminder:"))
      .slice(0, limit);
  }

  createReminder(context, { title, dueAt }) {
    this.#require(context, "reminder.manage");
    if (typeof title !== "string" || title.trim().length === 0 || title.length > 200) {
      throw new CompanionError("REMINDER_TITLE_INVALID");
    }
    if (!Number.isFinite(new Date(dueAt).getTime())) {
      throw new CompanionError("REMINDER_DUE_INVALID");
    }
    const now = this.#timestamp();
    const entryId = randomUUID();
    const factId = `reminder_${entryId}`;
    this.database
      .prepare(
        `INSERT INTO profile_facts(
           fact_id, user_id, kind, category, fact_key, value_json, decision,
           frozen, version, created_at, updated_at
         ) VALUES (?, ?, 'explicit', 'routine', ?, ?, 'accepted', 0, 1, ?, ?)`,
      )
      .run(
        factId,
        context.userId,
        `reminder:${now}:${entryId}`,
        JSON.stringify({ title, dueAt }),
        now,
        now,
      );
    return Object.freeze({ factId, title, dueAt });
  }

  deleteEntry(context, factId) {
    this.#require(context, "timeline.read");
    // The scoped delete only matches rows the caller owns, so a foreign id
    // changes nothing.
    return this.facts.deleteById(context, factId) === 1;
  }

  setCheckinEnabled(context, enabled) {
    this.#require(context, "reminder.manage");
    this.database
      .prepare(
        `UPDATE user_settings SET checkin_enabled=?, updated_at=? WHERE user_id=?`,
      )
      .run(enabled ? 1 : 0, this.#timestamp(), context.userId);
    return Boolean(enabled);
  }

  checkinEnabled(context) {
    this.#require(context, "reminder.manage");
    const row = this.database
      .prepare("SELECT checkin_enabled FROM user_settings WHERE user_id=?")
      .get(context.userId);
    return Boolean(row && Number(row.checkin_enabled) === 1);
  }

  // AC-043: the proactive decision reads the user's own setting and is entirely
  // deterministic. It reports modelCalls on every path so the caller can assert
  // the background plane never spends tokens.
  planProactiveMessage(context, { nowMs, lastCheckinMs = null, timezoneOffsetMinutes = 480 }) {
    this.#require(context, "reminder.manage");
    return decideCheckin({
      enabled: this.checkinEnabled(context),
      nowMs,
      lastCheckinMs,
      timezoneOffsetMinutes,
    });
  }
}

module.exports = { COMPANION_CAPABILITIES, CompanionError, UserCompanionService };
