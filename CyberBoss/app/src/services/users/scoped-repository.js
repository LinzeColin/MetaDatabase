"use strict";

// CB-630 / AC-007: every read, write and delete carries the user scope in the
// SQL predicate itself, so a caller cannot reach another user's row even with a
// valid record id. Table and column names are validated as trusted identifiers
// because they are interpolated; all values remain bound parameters.

const { UserContextError } = require("./user-context");

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;
const MAX_LIMIT = 200;
const DEFAULT_LIMIT = 100;

class ScopedRepositoryError extends Error {
  constructor(code) {
    super(code);
    this.name = "ScopedRepositoryError";
    this.code = code;
  }
}

function trustedIdentifier(value, label) {
  if (typeof value !== "string" || !IDENTIFIER.test(value) || value.length > 64) {
    throw new ScopedRepositoryError(`UNTRUSTED_${label.toUpperCase()}`);
  }
  return value;
}

function boundedInteger(value, fallback, minimum, maximum) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(minimum, Math.min(maximum, Math.trunc(parsed)));
}

class UserScopedRepository {
  constructor({
    database,
    table,
    idColumn = "id",
    userColumn = "user_id",
    readableColumns = ["*"],
    orderColumn = null,
  }) {
    if (!database || typeof database.prepare !== "function") {
      throw new ScopedRepositoryError("DATABASE_REQUIRED");
    }
    this.database = database;
    this.table = trustedIdentifier(table, "table");
    this.idColumn = trustedIdentifier(idColumn, "id_column");
    this.userColumn = trustedIdentifier(userColumn, "user_column");
    this.orderColumn = orderColumn
      ? trustedIdentifier(orderColumn, "order_column")
      : this.idColumn;
    this.readableColumns = (
      Array.isArray(readableColumns) && readableColumns.length > 0
        ? readableColumns
        : ["*"]
    ).map((column) =>
      column === "*" ? "*" : trustedIdentifier(column, "readable_column"),
    );
  }

  #context(context) {
    if (!context || typeof context.userId !== "string" || !context.may) {
      throw new UserContextError("USER_CONTEXT_REQUIRED");
    }
    return context.requireActive();
  }

  #columns() {
    return this.readableColumns.join(", ");
  }

  getById(context, id) {
    const user = this.#context(context);
    const row = this.database
      .prepare(
        `SELECT ${this.#columns()} FROM ${this.table}
         WHERE ${this.idColumn}=? AND ${this.userColumn}=?`,
      )
      .get(id, user.userId);
    return row ? Object.freeze({ ...row }) : null;
  }

  // Reading another user's record by id is refused loudly rather than silently
  // returning null, so an IDOR probe is distinguishable from a missing row.
  requireById(context, id) {
    const row = this.getById(context, id);
    if (!row) {
      const exists = this.database
        .prepare(`SELECT 1 AS present FROM ${this.table} WHERE ${this.idColumn}=?`)
        .get(id);
      throw new UserContextError(
        exists ? "USER_SCOPE_VIOLATION" : "RECORD_NOT_FOUND",
      );
    }
    return row;
  }

  list(context, { limit = DEFAULT_LIMIT, offset = 0 } = {}) {
    const user = this.#context(context);
    return this.database
      .prepare(
        `SELECT ${this.#columns()} FROM ${this.table}
         WHERE ${this.userColumn}=?
         ORDER BY ${this.orderColumn} LIMIT ? OFFSET ?`,
      )
      .all(
        user.userId,
        boundedInteger(limit, DEFAULT_LIMIT, 1, MAX_LIMIT),
        boundedInteger(offset, 0, 0, Number.MAX_SAFE_INTEGER),
      )
      .map((row) => Object.freeze({ ...row }));
  }

  count(context) {
    const user = this.#context(context);
    return Number(
      this.database
        .prepare(
          `SELECT COUNT(*) AS count FROM ${this.table} WHERE ${this.userColumn}=?`,
        )
        .get(user.userId).count,
    );
  }

  // A LIKE search is still confined to the caller's own rows.
  search(context, column, needle, { limit = DEFAULT_LIMIT } = {}) {
    const user = this.#context(context);
    const searchColumn = trustedIdentifier(column, "search_column");
    if (typeof needle !== "string" || needle.length === 0 || needle.length > 200) {
      throw new ScopedRepositoryError("SEARCH_TERM_INVALID");
    }
    return this.database
      .prepare(
        `SELECT ${this.#columns()} FROM ${this.table}
         WHERE ${this.userColumn}=? AND ${searchColumn} LIKE ? ESCAPE '\\'
         ORDER BY ${this.orderColumn} LIMIT ?`,
      )
      .all(
        user.userId,
        `%${needle.replace(/[\\%_]/g, "\\$&")}%`,
        boundedInteger(limit, DEFAULT_LIMIT, 1, MAX_LIMIT),
      )
      .map((row) => Object.freeze({ ...row }));
  }

  updateById(context, id, patch) {
    const user = this.#context(context);
    if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
      throw new ScopedRepositoryError("PATCH_INVALID");
    }
    const columns = Object.keys(patch).map((column) =>
      trustedIdentifier(column, "patch_column"),
    );
    if (columns.length === 0) {
      throw new ScopedRepositoryError("PATCH_EMPTY");
    }
    if (columns.includes(this.userColumn)) {
      // Re-homing a record to another user is never an update.
      throw new UserContextError("USER_SCOPE_VIOLATION");
    }
    const assignments = columns.map((column) => `${column}=?`).join(", ");
    return Number(
      this.database
        .prepare(
          `UPDATE ${this.table} SET ${assignments}
           WHERE ${this.idColumn}=? AND ${this.userColumn}=?`,
        )
        .run(...columns.map((column) => patch[column]), id, user.userId).changes,
    );
  }

  deleteById(context, id) {
    const user = this.#context(context);
    return Number(
      this.database
        .prepare(
          `DELETE FROM ${this.table}
           WHERE ${this.idColumn}=? AND ${this.userColumn}=?`,
        )
        .run(id, user.userId).changes,
    );
  }

  // Used by the export path: still scoped, still bounded.
  exportAll(context, { limit = MAX_LIMIT } = {}) {
    return this.list(context, { limit, offset: 0 });
  }
}

module.exports = {
  DEFAULT_LIMIT,
  MAX_LIMIT,
  ScopedRepositoryError,
  UserScopedRepository,
};
