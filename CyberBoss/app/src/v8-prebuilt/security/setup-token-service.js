'use strict';
const crypto = require('node:crypto');

function hashToken(token) {
  return crypto.createHash('sha256').update(String(token)).digest('hex');
}

class SetupTokenService {
  constructor({ store, clock = () => Date.now(), ttlMs = 10 * 60 * 1000 }) {
    this.store = store;
    this.clock = clock;
    this.ttlMs = ttlMs;
  }

  issue({ userId, purpose }) {
    const now = this.clock();
    const token = crypto.randomBytes(32).toString('base64url');
    const record = {
      tokenHash: hashToken(token),
      userId,
      purpose,
      createdAt: now,
      expiresAt: now + this.ttlMs,
      usedAt: null,
    };
    this.store.insert(record);
    return { token, expiresAt: record.expiresAt };
  }

  consume({ token, purpose }) {
    const result = this.store.consumeAtomic({
      tokenHash: hashToken(token),
      purpose,
      now: this.clock(),
    });
    if (!result.ok) {
      throw Object.assign(new Error(result.code), { code: result.code });
    }
    return { userId: result.record.userId, purpose: result.record.purpose };
  }
}

class MemorySetupTokenStore {
  constructor() {
    this.rows = new Map();
  }

  insert(record) {
    if (this.rows.has(record.tokenHash)) throw new Error('duplicate token');
    this.rows.set(record.tokenHash, { ...record });
  }

  consumeAtomic({ tokenHash, purpose, now }) {
    const row = this.rows.get(tokenHash);
    if (!row || row.usedAt !== null) return { ok: false, code: 'LINK_INVALID' };
    if (row.purpose !== purpose) return { ok: false, code: 'LINK_INVALID' };
    if (row.expiresAt < now) return { ok: false, code: 'LINK_EXPIRED' };
    row.usedAt = now;
    return { ok: true, record: { ...row } };
  }
}

module.exports = { SetupTokenService, MemorySetupTokenStore, hashToken };
