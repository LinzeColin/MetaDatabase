'use strict';

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

function trustedIdentifier(value, label) {
  if (!IDENTIFIER.test(value || '')) throw new TypeError(`${label} must be a trusted SQL identifier`);
  return value;
}

class UserScopedRepository {
  constructor({ db, table, idColumn = 'id', userColumn = 'user_id', readableColumns = ['*'] }) {
    if (!db || typeof db.prepare !== 'function') throw new TypeError('db is required');
    this.db = db;
    this.table = trustedIdentifier(table, 'table');
    this.idColumn = trustedIdentifier(idColumn, 'idColumn');
    this.userColumn = trustedIdentifier(userColumn, 'userColumn');
    this.readableColumns = readableColumns.map((column) => column === '*' ? '*' : trustedIdentifier(column, 'readableColumn'));
  }

  requireContext(context) {
    if (!context || !/^usr_[A-Za-z0-9_-]{20,}$/.test(context.userId || '')) {
      throw Object.assign(new Error('USER_CONTEXT_REQUIRED'), { code: 'USER_CONTEXT_REQUIRED' });
    }
    return context;
  }

  getById(context, id) {
    const user = this.requireContext(context);
    return this.db.prepare(`SELECT ${this.readableColumns.join(',')} FROM ${this.table} WHERE ${this.idColumn}=? AND ${this.userColumn}=?`)
      .get(id, user.userId) || null;
  }

  list(context, { limit = 100, offset = 0 } = {}) {
    const user = this.requireContext(context);
    const boundedLimit = Math.max(1, Math.min(200, Number(limit) || 100));
    const boundedOffset = Math.max(0, Number(offset) || 0);
    return this.db.prepare(`SELECT ${this.readableColumns.join(',')} FROM ${this.table} WHERE ${this.userColumn}=? ORDER BY ${this.idColumn} LIMIT ? OFFSET ?`)
      .all(user.userId, boundedLimit, boundedOffset);
  }

  deleteById(context, id) {
    const user = this.requireContext(context);
    return Number(this.db.prepare(`DELETE FROM ${this.table} WHERE ${this.idColumn}=? AND ${this.userColumn}=?`).run(id, user.userId).changes);
  }
}

module.exports = { UserScopedRepository };
