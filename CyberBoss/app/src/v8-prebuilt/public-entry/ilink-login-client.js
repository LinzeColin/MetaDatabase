'use strict';
const DEFAULT_TIMEOUT_MS = 35_000;
const MAX_BODY_BYTES = 1 << 20;

function normalizeBaseUrl(value, { allowInsecureLoopback = false } = {}) {
  const url = new URL(String(value));
  const loopback = ['127.0.0.1','localhost','::1'].includes(url.hostname);
  if (url.protocol !== 'https:' && !(allowInsecureLoopback && loopback && url.protocol === 'http:')) {
    throw Object.assign(new Error('ILINK_BASE_URL_REQUIRES_HTTPS'), { code:'ILINK_BASE_URL_REQUIRES_HTTPS' });
  }
  if (url.username || url.password) throw Object.assign(new Error('ILINK_BASE_URL_CREDENTIALS_FORBIDDEN'), { code:'ILINK_BASE_URL_CREDENTIALS_FORBIDDEN' });
  if (!url.pathname.endsWith('/')) url.pathname += '/';
  return url;
}

async function readJsonBounded(response) {
  const reader = response.body?.getReader?.();
  if (!reader) return response.json();
  const parts=[]; let total=0;
  for (;;) {
    const {done,value}=await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BODY_BYTES) { await reader.cancel().catch(()=>{}); throw Object.assign(new Error('ILINK_RESPONSE_TOO_LARGE'),{code:'ILINK_RESPONSE_TOO_LARGE'}); }
    parts.push(Buffer.from(value));
  }
  return JSON.parse(Buffer.concat(parts).toString('utf8'));
}

class ILinkLoginClient {
  constructor({ baseUrl, botType = '3', fetchImpl = globalThis.fetch, clock = () => Date.now(), timeoutMs = DEFAULT_TIMEOUT_MS, allowInsecureLoopback = false }) {
    if (typeof fetchImpl !== 'function') throw new TypeError('fetchImpl required');
    this.baseUrl=normalizeBaseUrl(baseUrl,{allowInsecureLoopback}); this.botType=String(botType); this.fetch=fetchImpl; this.clock=clock; this.timeoutMs=timeoutMs;
  }
  async request(path, { headers = {} } = {}) {
    const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),this.timeoutMs);
    try {
      const response=await this.fetch(new URL(path,this.baseUrl),{headers,signal:controller.signal,redirect:'error'});
      if (!response.ok) throw Object.assign(new Error(`ILINK_HTTP_${response.status}`),{code:`ILINK_HTTP_${response.status}`,status:response.status});
      return await readJsonBounded(response);
    } catch (error) {
      if (error?.name==='AbortError') throw Object.assign(new Error('ILINK_TIMEOUT'),{code:'ILINK_TIMEOUT'});
      throw error;
    } finally { clearTimeout(timer); }
  }
  async createQr() {
    const data=await this.request(`ilink/bot/get_bot_qrcode?bot_type=${encodeURIComponent(this.botType)}`);
    if (!data?.qrcode || !data?.qrcode_img_content) throw Object.assign(new Error('ILINK_QR_RESPONSE_INVALID'),{code:'ILINK_QR_RESPONSE_INVALID'});
    return { qrId:String(data.qrcode), content:String(data.qrcode_img_content), createdAt:this.clock() };
  }
  async pollStatus(qrId) {
    const data=await this.request(`ilink/bot/get_qrcode_status?qrcode=${encodeURIComponent(String(qrId))}`,{headers:{'iLink-App-ClientVersion':'1'}});
    const raw=String(data?.status||'wait');
    const status=raw==='scaned'?'scanned':raw;
    if (!['wait','scanned','expired','confirmed'].includes(status)) return { status:'wait' };
    if (status!=='confirmed') return { status };
    if (!data.bot_token || !data.ilink_bot_id) throw Object.assign(new Error('ILINK_CONFIRMATION_INCOMPLETE'),{code:'ILINK_CONFIRMATION_INCOMPLETE'});
    return { status:'confirmed', accountId:String(data.ilink_bot_id), botToken:String(data.bot_token), baseUrl:String(data.baseurl||this.baseUrl), weixinUserId:String(data.ilink_user_id||'') };
  }
}
module.exports={ ILinkLoginClient, normalizeBaseUrl };
