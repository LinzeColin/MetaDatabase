'use strict';
const crypto = require('node:crypto');
const { renderQrSvg, svgDataUri } = require('./qr-svg');

class OwnerWeChatActivationService {
  constructor({ client, store, sharedBotAccounts, clock = () => Date.now(), ttlMs = 5 * 60_000 } = {}) {
    if (!client || !store || !sharedBotAccounts) throw new TypeError('client, store and sharedBotAccounts are required');
    this.client = client; this.store = store; this.sharedBotAccounts = sharedBotAccounts; this.clock = clock; this.ttlMs = ttlMs;
  }
  async create() {
    const qr = await this.client.createQr(); const now = this.clock();
    const sessionId = `opswx_${crypto.randomBytes(24).toString('base64url')}`;
    const row = this.store.create({ sessionId, qrId: qr.qrId, qrContent: qr.content, createdAt: now, expiresAt: now + this.ttlMs });
    return { sessionId, status:'wait', expiresAt:row.expiresAt, qrDataUri:svgDataUri(renderQrSvg(row.qrContent)) };
  }
  async status(sessionId) {
    const row = this.store.get(sessionId); if (!row) return { status:'invalid' };
    const now = this.clock();
    if (row.consumedAt !== null) return { status:'confirmed' };
    if (row.expiresAt < now) { this.store.setState(sessionId,'expired','ACTIVATION_EXPIRED'); return { status:'expired' }; }
    this.store.notePolled(sessionId,now);
    const result = await this.client.pollStatus(row.qrId);
    if (result.status === 'wait') return { status:'wait' };
    if (result.status === 'scanned') { this.store.setState(sessionId,'scanned'); return { status:'scanned' }; }
    if (result.status === 'expired') { this.store.setState(sessionId,'expired','ACTIVATION_EXPIRED'); return { status:'expired' }; }
    const consumed = this.store.consumeConfirmedAtomic({
      sessionId, now,
      activate: () => this.sharedBotAccounts.activateInCurrentTransaction({
        accountId: result.accountId, botToken: result.botToken,
        baseUrl: result.baseUrl, weixinUserId: result.weixinUserId,
      }),
    });
    return consumed.ok ? { status:'confirmed' } : { status:consumed.code === 'ACTIVATION_EXPIRED' ? 'expired' : 'confirmed' };
  }
}
module.exports = { OwnerWeChatActivationService };
