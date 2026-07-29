'use strict';
class SqliteOwnerActivationStore {
  constructor(db) { if (!db?.prepare) throw new TypeError('db required'); this.db = db; }
  create(row) {
    this.db.prepare(`INSERT INTO owner_wechat_activation_sessions(
      session_id,qr_id,qr_content,status,created_at,expires_at,last_polled_at,attempt_count,error_code
    ) VALUES(?,?,?,?,?,?,NULL,0,NULL)`).run(row.sessionId,row.qrId,row.qrContent,'wait',row.createdAt,row.expiresAt);
    return this.get(row.sessionId);
  }
  get(id) { return this.db.prepare(`SELECT session_id AS sessionId,qr_id AS qrId,qr_content AS qrContent,
    status,created_at AS createdAt,expires_at AS expiresAt,last_polled_at AS lastPolledAt,
    attempt_count AS attemptCount,consumed_at AS consumedAt,error_code AS errorCode
    FROM owner_wechat_activation_sessions WHERE session_id=?`).get(id) || null; }
  notePolled(id, now) { this.db.prepare(`UPDATE owner_wechat_activation_sessions SET last_polled_at=?,attempt_count=attempt_count+1 WHERE session_id=?`).run(now,id); }
  setState(id, status, errorCode = null) { this.db.prepare(`UPDATE owner_wechat_activation_sessions SET status=?,error_code=? WHERE session_id=? AND consumed_at IS NULL`).run(status,errorCode,id); return this.get(id); }
  consumeConfirmedAtomic({ sessionId, now, activate }) {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const row = this.get(sessionId);
      if (!row || row.consumedAt !== null) { this.db.exec('ROLLBACK'); return { ok:false, code:'ACTIVATION_ALREADY_USED' }; }
      if (row.expiresAt < now) {
        this.db.prepare(`UPDATE owner_wechat_activation_sessions SET status='expired',error_code='ACTIVATION_EXPIRED' WHERE session_id=?`).run(sessionId);
        this.db.exec('COMMIT'); return { ok:false, code:'ACTIVATION_EXPIRED' };
      }
      const result = activate();
      const info = this.db.prepare(`UPDATE owner_wechat_activation_sessions SET status='confirmed',consumed_at=?,error_code=NULL
        WHERE session_id=? AND consumed_at IS NULL`).run(now,sessionId);
      if (Number(info.changes) !== 1) { this.db.exec('ROLLBACK'); return { ok:false, code:'ACTIVATION_ALREADY_USED' }; }
      this.db.exec('COMMIT'); return { ok:true, result };
    } catch (error) { try { this.db.exec('ROLLBACK'); } catch {} throw error; }
  }
}
module.exports = { SqliteOwnerActivationStore };
