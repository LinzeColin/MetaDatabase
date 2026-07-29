'use strict';

const { deriveUserId, principalHashHex } = require('./user-identity');

class SqliteUserRepository {
  constructor({ db, identityKey, clock = () => new Date().toISOString() }) {
    if (!db || typeof db.prepare !== 'function') throw new TypeError('db is required');
    if (!Buffer.isBuffer(identityKey) || identityKey.length < 32) throw new TypeError('identityKey must be at least 32 bytes');
    this.db = db;
    this.identityKey = identityKey;
    this.clock = clock;
  }

  identity(principal) {
    const input = { identityKey: this.identityKey, channel: principal.channel || 'weixin', botAccountId: principal.botAccountId, senderId: principal.senderId };
    return { userId: deriveUserId(input), principalHash: principalHashHex(input), channel: input.channel };
  }

  resolveByPrincipal(principal) {
    const identity = this.identity(principal);
    const row = this.db.prepare(`SELECT u.user_id AS userId,u.role,u.status,u.consent_version AS consentVersion,
      c.principal_hash AS principalHash,c.channel
      FROM user_channels c JOIN users u ON u.user_id=c.user_id
      WHERE c.channel=? AND c.bot_account_ref=? AND c.principal_hash=? AND c.revoked_at IS NULL`)
      .get(identity.channel, principal.botAccountId, identity.principalHash);
    return row || null;
  }

  ensurePending({ principal, role = 'user', principalCiphertext = null }) {
    const identity = this.identity(principal);
    const now = this.clock();
    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.db.prepare(`INSERT INTO users(user_id,role,status,created_at,updated_at)
        VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO NOTHING`)
        .run(identity.userId, role, role === 'owner' ? 'active' : 'pending_consent', now, now);
      this.db.prepare(`INSERT INTO user_channels(channel,bot_account_ref,principal_hash,user_id,principal_ciphertext,created_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(channel,bot_account_ref,principal_hash) DO UPDATE SET revoked_at=NULL`)
        .run(identity.channel, principal.botAccountId, identity.principalHash, identity.userId, principalCiphertext, now);
      this.db.prepare(`INSERT INTO user_settings(user_id,locale,checkin_enabled,updated_at)
        VALUES(?,?,0,?) ON CONFLICT(user_id) DO NOTHING`).run(identity.userId, 'zh-CN', now);
      this.db.exec('COMMIT');
    } catch (error) {
      try { this.db.exec('ROLLBACK'); } catch {}
      throw error;
    }
    return this.getById(identity.userId);
  }

  activateConsent({ userId, policyVersion }) {
    const now = this.clock();
    const info = this.db.prepare(`UPDATE users SET status='active',consent_version=?,consented_at=?,updated_at=?
      WHERE user_id=? AND status='pending_consent'`).run(policyVersion, now, now, userId);
    if (Number(info.changes) !== 1) throw Object.assign(new Error('CONSENT_STATE_INVALID'), { code: 'CONSENT_STATE_INVALID' });
    return this.getById(userId);
  }

  getById(userId) {
    return this.db.prepare(`SELECT user_id AS userId,role,status,consent_version AS consentVersion,consented_at AS consentedAt,
      created_at AS createdAt,updated_at AS updatedAt FROM users WHERE user_id=?`).get(userId) || null;
  }

  suspend(userId) {
    const now = this.clock();
    return Number(this.db.prepare(`UPDATE users SET status='suspended',updated_at=? WHERE user_id=? AND status!='deleted'`).run(now, userId).changes);
  }
}

module.exports = { SqliteUserRepository };
