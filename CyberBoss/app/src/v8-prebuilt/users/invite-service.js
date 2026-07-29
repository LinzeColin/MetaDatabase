'use strict';
const crypto = require('node:crypto');

function normalizeCode(value) {
  return String(value || '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
}
function hashCode(secret, value) {
  if (!Buffer.isBuffer(secret) || secret.length < 32) throw new TypeError('invite secret required');
  return crypto.createHmac('sha256', secret).update(normalizeCode(value)).digest('hex');
}
function formatCode(raw) { return `${raw.slice(0,4)}-${raw.slice(4,8)}-${raw.slice(8,12)}`; }

class InviteService {
  constructor({ store, secret, clock = () => Date.now() }) {
    this.store = store; this.secret = secret; this.clock = clock;
  }
  issue({ createdByUserId, ttlMs = 7 * 24 * 60 * 60 * 1000, maxUses = 1 }) {
    if (!createdByUserId || !Number.isInteger(maxUses) || maxUses < 1 || maxUses > 20) throw new TypeError('invalid invite');
    const raw = crypto.randomBytes(9).toString('base64url').replace(/[^A-Z0-9]/gi, '').toUpperCase().padEnd(12, 'X').slice(0, 12);
    const code = formatCode(raw);
    const now = this.clock();
    this.store.insert({ codeHash: hashCode(this.secret, code), createdByUserId, createdAt: now, expiresAt: now + ttlMs, maxUses, uses: 0, revokedAt: null });
    return { code, expiresAt: now + ttlMs, maxUses };
  }
  consume({ code, userId }) {
    const result = this.store.consumeAtomic({ codeHash: hashCode(this.secret, code), userId, now: this.clock() });
    if (!result.ok) throw Object.assign(new Error(result.code), { code: result.code });
    return result.record;
  }
  revoke(code) { return this.store.revoke(hashCode(this.secret, code), this.clock()); }
}

class MemoryInviteStore {
  constructor() { this.rows = new Map(); this.userUses = new Set(); }
  insert(row) { if (this.rows.has(row.codeHash)) throw new Error('duplicate invite'); this.rows.set(row.codeHash, {...row}); }
  consumeAtomic({ codeHash, userId, now }) {
    const row = this.rows.get(codeHash);
    if (!row || row.revokedAt || row.expiresAt < now || row.uses >= row.maxUses) return { ok:false, code:'INVITE_INVALID' };
    const useKey = `${codeHash}:${userId}`;
    if (this.userUses.has(useKey)) return { ok:false, code:'INVITE_ALREADY_USED' };
    row.uses += 1; this.userUses.add(useKey);
    return { ok:true, record:{...row, userId} };
  }
  revoke(codeHash, now) { const row=this.rows.get(codeHash); if(!row)return false; row.revokedAt=now; return true; }
}
module.exports = { InviteService, MemoryInviteStore, normalizeCode, hashCode };
