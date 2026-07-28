'use strict';
const crypto = require('node:crypto');

function sha256(value) {
  return crypto.createHash('sha256').update(String(value)).digest('hex');
}

class SessionTokenService {
  constructor({ store, clock = () => Date.now(), ttlMs = 7 * 24 * 60 * 60 * 1000 }) {
    this.store = store;
    this.clock = clock;
    this.ttlMs = ttlMs;
  }

  issue({ userId }) {
    const now = this.clock();
    const token = crypto.randomBytes(32).toString('base64url');
    const csrf = crypto.randomBytes(24).toString('base64url');
    const expiresAt = now + this.ttlMs;
    this.store.insert({
      tokenHash: sha256(token),
      csrfHash: sha256(csrf),
      userId,
      expiresAt,
      revokedAt: null,
      createdAt: now,
    });
    return {
      token,
      csrf,
      expiresAt,
      cookie: `cb_session=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${Math.floor(this.ttlMs / 1000)}`,
    };
  }

  verify({ token, csrf }) {
    const row = this.store.get(sha256(token));
    if (!row || row.revokedAt || row.expiresAt < this.clock() || row.csrfHash !== sha256(csrf)) {
      throw Object.assign(new Error('SESSION_INVALID'), { code: 'SESSION_INVALID' });
    }
    return { userId: row.userId };
  }

  revokeAll(userId) {
    return this.store.revokeAll(userId, this.clock());
  }
}

class MemorySessionStore {
  constructor() {
    this.rows = new Map();
  }
  insert(record) {
    if (this.rows.has(record.tokenHash)) throw new Error('duplicate session');
    this.rows.set(record.tokenHash, { ...record });
  }
  get(hash) {
    const row = this.rows.get(hash);
    return row && { ...row };
  }
  revokeAll(userId, now) {
    let count = 0;
    for (const row of this.rows.values()) {
      if (row.userId === userId && !row.revokedAt) {
        row.revokedAt = now;
        count += 1;
      }
    }
    return count;
  }
}

module.exports = { SessionTokenService, MemorySessionStore };
