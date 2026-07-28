'use strict';
const crypto = require('node:crypto');

function normalizeCode(code) {
  return String(code || '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
}
function hashCode(secret, code) {
  if (!Buffer.isBuffer(secret) || secret.length < 32) throw new TypeError('invite secret must be at least 32 bytes');
  return crypto.createHmac('sha256', secret).update(normalizeCode(code)).digest('hex');
}

class SqliteInviteCodeStore {
  constructor({ db, secret, clock = () => Date.now() }) {
    if (!db || typeof db.prepare !== 'function') throw new TypeError('db is required');
    if (!Buffer.isBuffer(secret) || secret.length < 32) throw new TypeError('invite secret must be at least 32 bytes');
    this.db = db;
    this.secret = secret;
    this.clock = clock;
  }
  create({ code, maxUses = 1, expiresAt = null }) {
    const normalized = normalizeCode(code);
    if (!/^[A-Z0-9]{12,32}$/.test(normalized)) throw new TypeError('invalid invite code');
    if (!Number.isInteger(maxUses) || maxUses < 1 || maxUses > 20) throw new TypeError('invalid maxUses');
    this.db.prepare('INSERT INTO invite_codes(code_hash,max_uses,expires_at,created_at) VALUES(?,?,?,?)')
      .run(hashCode(this.secret, normalized), maxUses, expiresAt, this.clock());
  }
  consume(code) {
    const now = this.clock();
    const codeHash = hashCode(this.secret, code);
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const row = this.db.prepare('SELECT * FROM invite_codes WHERE code_hash=?').get(codeHash);
      if (!row || row.disabled_at || (row.expires_at !== null && row.expires_at < now) || row.used_count >= row.max_uses) {
        throw Object.assign(new Error('INVITE_INVALID'), { code: 'INVITE_INVALID' });
      }
      const result = this.db.prepare('UPDATE invite_codes SET used_count=used_count+1 WHERE code_hash=? AND used_count < max_uses').run(codeHash);
      if (Number(result.changes) !== 1) throw Object.assign(new Error('INVITE_INVALID'), { code: 'INVITE_INVALID' });
      this.db.exec('COMMIT');
      return true;
    } catch (error) {
      try { this.db.exec('ROLLBACK'); } catch (_) { /* preserve original error */ }
      throw error;
    }
  }
}
module.exports = { normalizeCode, hashCode, SqliteInviteCodeStore };
