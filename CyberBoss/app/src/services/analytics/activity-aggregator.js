"use strict";

// CB-720 / AC-027: daily behaviour aggregates.
//
// Pure counting over already-recorded events. It imports nothing that could
// reach a provider, so the aggregate can never consume model tokens, and it is
// a projection over the canonical fact path rather than a second authority:
// deleting the underlying events removes the aggregate on the next rebuild.

const EVENT_TYPES = Object.freeze({
  message: "messages",
  ai_turn: "aiTurns",
  import_completed: "imports",
  reminder_completed: "remindersCompleted",
  profile_changed: "profileChanges",
  checkin_answered: "checkinsAnswered",
});

class AnalyticsError extends Error {
  constructor(code) {
    super(code);
    this.name = "AnalyticsError";
    this.code = code;
  }
}

function utcDay(timestamp) {
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) {
    throw new AnalyticsError("OCCURRED_AT_INVALID");
  }
  return date.toISOString().slice(0, 10);
}

function emptyRow(userId, day) {
  const row = { userId, day };
  for (const field of Object.values(EVENT_TYPES)) {
    row[field] = 0;
  }
  return row;
}

// Deterministic: the same events in any order produce the same aggregate.
function aggregateDaily(events) {
  const rows = new Map();
  for (const event of events) {
    if (!event || !event.userId || !event.occurredAt) {
      throw new AnalyticsError("EVENT_IDENTITY_REQUIRED");
    }
    const day = utcDay(event.occurredAt);
    const key = `${event.userId}:${day}`;
    const row = rows.get(key) || emptyRow(event.userId, day);
    const field = EVENT_TYPES[event.type];
    if (field) {
      row[field] += 1;
    }
    rows.set(key, row);
  }
  return [...rows.values()]
    .map((row) => Object.freeze(row))
    .sort(
      (left, right) =>
        left.userId.localeCompare(right.userId) || left.day.localeCompare(right.day),
    );
}

// Chart-ready series for one user only. Nothing here crosses a user boundary,
// so an aggregate can never expose another user's activity.
function seriesForUser(aggregates, userId, metric) {
  if (!Object.values(EVENT_TYPES).includes(metric)) {
    throw new AnalyticsError("METRIC_NOT_SUPPORTED");
  }
  return aggregates
    .filter((row) => row.userId === userId)
    .map((row) => Object.freeze({ day: row.day, value: row[metric] }));
}

class SqliteActivityAggregator {
  constructor({ database, now = () => new Date() }) {
    if (!database || typeof database.prepare !== "function") {
      throw new AnalyticsError("DATABASE_REQUIRED");
    }
    this.database = database;
    this.now = now;
  }

  #timestamp() {
    const value = this.now();
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) {
      throw new AnalyticsError("CLOCK_INVALID");
    }
    return date.toISOString();
  }

  // A full rebuild rather than an increment, so a deleted event disappears from
  // the aggregate instead of lingering as a stale count.
  rebuildForUser(userId, events) {
    const rows = aggregateDaily(events).filter((row) => row.userId === userId);
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.database.prepare("DELETE FROM activity_daily WHERE user_id=?").run(userId);
      const insert = this.database.prepare(
        `INSERT INTO activity_daily(user_id, day, metrics_json, updated_at)
         VALUES (?, ?, ?, ?)`,
      );
      for (const row of rows) {
        const { userId: _scope, day, ...metrics } = row;
        insert.run(userId, day, JSON.stringify(metrics), now);
      }
      this.database.exec("COMMIT");
    } catch (error) {
      try {
        this.database.exec("ROLLBACK");
      } catch {
        // A commit may already have completed; the original error is preserved.
      }
      throw error;
    }
    return rows.length;
  }

  readForUser(userId, { limit = 90 } = {}) {
    return this.database
      .prepare(
        `SELECT day, metrics_json FROM activity_daily
         WHERE user_id=? ORDER BY day DESC LIMIT ?`,
      )
      .all(userId, Math.max(1, Math.min(400, Number(limit) || 90)))
      .map((row) => Object.freeze({ day: row.day, ...JSON.parse(row.metrics_json) }));
  }
}

module.exports = {
  AnalyticsError,
  EVENT_TYPES,
  SqliteActivityAggregator,
  aggregateDaily,
  seriesForUser,
  utcDay,
};
