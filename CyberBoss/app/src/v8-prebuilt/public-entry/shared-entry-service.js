'use strict';
const { renderQrSvg, svgDataUri } = require('./qr-svg');

function normalizeEntryUrl(value) {
  const text = String(value || '').trim();
  if (!text || text.length > 4096 || /[\r\n\0]/.test(text)) {
    throw Object.assign(new Error('PUBLIC_WECHAT_ENTRY_URL_INVALID'), { code: 'PUBLIC_WECHAT_ENTRY_URL_INVALID' });
  }
  let url;
  try { url = new URL(text); } catch { throw Object.assign(new Error('PUBLIC_WECHAT_ENTRY_URL_INVALID'), { code: 'PUBLIC_WECHAT_ENTRY_URL_INVALID' }); }
  if (!['https:', 'weixin:'].includes(url.protocol)) {
    throw Object.assign(new Error('PUBLIC_WECHAT_ENTRY_PROTOCOL_FORBIDDEN'), { code: 'PUBLIC_WECHAT_ENTRY_PROTOCOL_FORBIDDEN' });
  }
  if (url.username || url.password) throw Object.assign(new Error('PUBLIC_WECHAT_ENTRY_CREDENTIAL_FORBIDDEN'), { code: 'PUBLIC_WECHAT_ENTRY_CREDENTIAL_FORBIDDEN' });
  return text;
}

class SharedEntryService {
  constructor({ entryUrlProvider, sharedBotState, qrRenderer = renderQrSvg, clock = () => Date.now() } = {}) {
    if (typeof entryUrlProvider !== 'function' || typeof sharedBotState !== 'function' || typeof qrRenderer !== 'function') {
      throw new TypeError('entryUrlProvider, sharedBotState and qrRenderer are required');
    }
    this.entryUrlProvider = entryUrlProvider;
    this.sharedBotState = sharedBotState;
    this.qrRenderer = qrRenderer;
    this.clock = clock;
  }

  summary() {
    const bot = this.sharedBotState();
    if (!bot || bot.status !== 'active') {
      return Object.freeze({ status: 'pending_activation', ready: false, qrDataUri: null, message: 'CyberBoss 微信入口正在准备中，请稍后再试。' });
    }
    let entryUrl;
    try { entryUrl = normalizeEntryUrl(this.entryUrlProvider()); }
    catch {
      return Object.freeze({ status: 'pending_entry_qr', ready: false, qrDataUri: null, message: 'CyberBoss 微信入口二维码正在准备中，请稍后再试。' });
    }
    const svg = this.qrRenderer(entryUrl);
    return Object.freeze({
      status: 'ready',
      ready: true,
      qrDataUri: svgDataUri(svg),
      message: '使用微信扫码，进入 CyberBoss 后发送“开始”。',
      generatedAt: new Date(this.clock()).toISOString(),
    });
  }
}

module.exports = { SharedEntryService, normalizeEntryUrl };
