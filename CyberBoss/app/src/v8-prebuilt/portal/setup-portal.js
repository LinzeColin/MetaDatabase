'use strict';
const http = require('node:http');
const { URL } = require('node:url');

function json(res, status, payload) {
  const body = Buffer.from(JSON.stringify(payload));
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': body.length,
    'cache-control': 'no-store',
    'pragma': 'no-cache',
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer',
    'content-security-policy': "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
  });
  res.end(body);
}

function parseCookies(header) {
  const out = {};
  for (const part of String(header || '').split(';')) {
    const index = part.indexOf('=');
    if (index <= 0) continue;
    out[part.slice(0, index).trim()] = decodeURIComponent(part.slice(index + 1).trim());
  }
  return out;
}

async function readJsonBody(req, maxBytes = 16 * 1024) {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of req) {
    bytes += chunk.length;
    if (bytes > maxBytes) throw Object.assign(new Error('BODY_TOO_LARGE'), { code: 'BODY_TOO_LARGE' });
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); }
  catch { throw Object.assign(new Error('BODY_INVALID'), { code: 'BODY_INVALID' }); }
}

function assertSameOrigin(req, host) {
  const origin = req.headers.origin;
  if (!origin || origin !== `https://${host}`) {
    throw Object.assign(new Error('ORIGIN_NOT_ALLOWED'), { code: 'ORIGIN_NOT_ALLOWED' });
  }
}

function createSetupPortal({ hostAllowlist, actionAllowlist, consumeSetupToken, issueSession, verifySession, handleAction }) {
  if (typeof verifySession !== 'function') throw new TypeError('verifySession is required');
  if (!Array.isArray(actionAllowlist) || actionAllowlist.length < 1) throw new TypeError('actionAllowlist is required');
  const allowed = new Set(hostAllowlist);
  const allowedActions = new Set(actionAllowlist);
  return http.createServer(async (req, res) => {
    try {
      const host = String(req.headers.host || '').split(':')[0];
      if (!allowed.has(host)) return json(res, 400, { ok: false, code: 'HOST_NOT_ALLOWED', message: '链接无效，请回微信重新打开。' });
      const url = new URL(req.url, `https://${host}`);

      if (req.method === 'POST' && url.pathname === '/api/exchange') {
        assertSameOrigin(req, host);
        const input = await readJsonBody(req);
        const claim = consumeSetupToken({ token: input.token, purpose: input.purpose });
        const session = issueSession({ userId: claim.userId });
        res.setHeader('set-cookie', session.cookie);
        return json(res, 200, { ok: true, csrf: session.csrf, expiresAt: session.expiresAt });
      }

      if (req.method === 'POST' && url.pathname.startsWith('/api/action/')) {
        const action = url.pathname.slice('/api/action/'.length);
        if (!allowedActions.has(action)) return json(res, 404, { ok: false, code: 'ACTION_NOT_ALLOWED', message: '这个操作不可用，请回微信重新打开。' });
        assertSameOrigin(req, host);
        const cookies = parseCookies(req.headers.cookie);
        const csrf = String(req.headers['x-csrf-token'] || '');
        const session = verifySession({ token: cookies.cb_session, csrf });
        const input = await readJsonBody(req);
        const result = await handleAction({
          action,
          userId: session.userId,
          input,
        });
        return json(res, 200, { ok: true, result });
      }

      return json(res, 404, { ok: false, code: 'NOT_FOUND', message: '页面不存在，请回微信重新打开。' });
    } catch (error) {
      const status = ['SESSION_INVALID', 'ORIGIN_NOT_ALLOWED'].includes(error.code) ? 403 : 400;
      return json(res, status, { ok: false, code: error.code || 'REQUEST_INVALID', message: '操作没有完成，请回微信重新打开后重试。' });
    }
  });
}

module.exports = { createSetupPortal, parseCookies, assertSameOrigin, readJsonBody };
