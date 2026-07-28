'use strict';

class SqliteSetupTokenStore {
  constructor(db) { this.db = db; }
  insert(r) { this.db.prepare(`INSERT INTO setup_tokens(token_hash,user_id,purpose,expires_at,used_at,created_at) VALUES(?,?,?,?,?,?)`).run(r.tokenHash,r.userId,r.purpose,r.expiresAt,r.usedAt,r.createdAt); }
  consumeAtomic({ tokenHash, purpose, now }) {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const row = this.db.prepare(`SELECT token_hash AS tokenHash,user_id AS userId,purpose,expires_at AS expiresAt,used_at AS usedAt,created_at AS createdAt FROM setup_tokens WHERE token_hash=?`).get(tokenHash);
      if (!row || row.usedAt !== null || row.purpose !== purpose) { this.db.exec('ROLLBACK'); return { ok:false, code:'LINK_INVALID' }; }
      if (row.expiresAt < now) { this.db.exec('ROLLBACK'); return { ok:false, code:'LINK_EXPIRED' }; }
      const info = this.db.prepare(`UPDATE setup_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL`).run(now, tokenHash);
      if (Number(info.changes) !== 1) { this.db.exec('ROLLBACK'); return { ok:false, code:'LINK_INVALID' }; }
      this.db.exec('COMMIT'); return { ok:true, record:{...row,usedAt:now} };
    } catch (error) { try { this.db.exec('ROLLBACK'); } catch {} throw error; }
  }
}

class SqliteSessionStore {
  constructor(db) { this.db = db; }
  insert(r) { this.db.prepare(`INSERT INTO web_sessions(token_hash,csrf_hash,user_id,expires_at,revoked_at,created_at) VALUES(?,?,?,?,?,?)`).run(r.tokenHash,r.csrfHash,r.userId,r.expiresAt,r.revokedAt,r.createdAt); }
  get(hash) { return this.db.prepare(`SELECT token_hash AS tokenHash,csrf_hash AS csrfHash,user_id AS userId,expires_at AS expiresAt,revoked_at AS revokedAt,created_at AS createdAt FROM web_sessions WHERE token_hash=?`).get(hash) || null; }
  revokeAll(userId, now) { return Number(this.db.prepare(`UPDATE web_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL`).run(now,userId).changes); }
}
module.exports = { SqliteSetupTokenStore, SqliteSessionStore };
