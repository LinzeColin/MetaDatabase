'use strict';
const { encryptBotAccount, decryptBotAccount } = require('../public-entry/account-token-crypto');

class SharedBotAccountStore {
  constructor({ db, masterKey, ownerUserId, clock = () => Date.now() } = {}) {
    if (!db?.prepare) throw new TypeError('db required');
    if (!Buffer.isBuffer(masterKey) || masterKey.length !== 32) throw new TypeError('masterKey must be 32 bytes');
    if (typeof ownerUserId !== 'string' || ownerUserId.length < 3) throw new TypeError('ownerUserId required');
    this.db = db; this.masterKey = masterKey; this.ownerUserId = ownerUserId; this.clock = clock;
  }

  _activateNoTx({ accountId, botToken, baseUrl, weixinUserId = '' }) {
    if (![accountId, botToken, baseUrl].every((value) => typeof value === 'string' && value.length >= 3)) {
      throw new TypeError('shared bot account fields are required');
    }
    const now = this.clock();
    const encrypted = encryptBotAccount({ masterKey: this.masterKey, userId: this.ownerUserId, accountId, botToken, baseUrl });
    this.db.prepare(`INSERT INTO weixin_accounts(
        singleton_key,account_id,owner_user_id,weixin_user_id,base_url,token_ciphertext,status,created_at,updated_at
      ) VALUES('shared',?,?,?,?,?,'active',?,?)
      ON CONFLICT(singleton_key) DO UPDATE SET
        account_id=excluded.account_id,owner_user_id=excluded.owner_user_id,
        weixin_user_id=excluded.weixin_user_id,base_url=excluded.base_url,
        token_ciphertext=excluded.token_ciphertext,status='active',updated_at=excluded.updated_at`)
        .run(accountId, this.ownerUserId, weixinUserId, baseUrl, encrypted, now, now);
    return Object.freeze({ singletonKey: 'shared', accountId, ownerUserId: this.ownerUserId, status: 'active' });
  }

  activate(input) {
    this.db.exec('BEGIN IMMEDIATE');
    try { const result = this._activateNoTx(input); this.db.exec('COMMIT'); return result; }
    catch (error) { try { this.db.exec('ROLLBACK'); } catch {} throw error; }
  }

  activateInCurrentTransaction(input) { return this._activateNoTx(input); }

  getActive() {
    const row = this.db.prepare(`SELECT singleton_key AS singletonKey,account_id AS accountId,
      owner_user_id AS ownerUserId,weixin_user_id AS weixinUserId,base_url AS baseUrl,
      token_ciphertext AS tokenCiphertext,status
      FROM weixin_accounts WHERE singleton_key='shared' AND status='active'`).get();
    if (!row) return null;
    const credential = decryptBotAccount({
      masterKey: this.masterKey,
      userId: row.ownerUserId,
      accountId: row.accountId,
      record: row.tokenCiphertext,
    });
    return Object.freeze({
      singletonKey: 'shared', accountId: row.accountId, ownerUserId: row.ownerUserId,
      weixinUserId: row.weixinUserId || '', baseUrl: credential.baseUrl,
      botToken: credential.botToken, status: row.status,
    });
  }

  publicState() {
    const row = this.db.prepare(`SELECT account_id AS accountId,status,updated_at AS updatedAt
      FROM weixin_accounts WHERE singleton_key='shared'`).get();
    return Object.freeze(row ? { status: row.status, updatedAt: row.updatedAt } : { status: 'pending_activation', updatedAt: null });
  }

  markReauthRequired(now = this.clock()) {
    return this.db.prepare(`UPDATE weixin_accounts SET status='reauth_required',updated_at=?
      WHERE singleton_key='shared' AND status='active'`).run(now).changes === 1;
  }

  revoke(now = this.clock()) {
    return this.db.prepare(`UPDATE weixin_accounts SET status='revoked',updated_at=?
      WHERE singleton_key='shared' AND status!='revoked'`).run(now).changes === 1;
  }
}

module.exports = { SharedBotAccountStore };
