#!/usr/bin/env node
import http from 'node:http';
import crypto from 'node:crypto';

const host = process.env.SIM_WEIXIN_HOST || '127.0.0.1';
const port = Number(process.env.SIM_WEIXIN_PORT || 19080);
const token = process.env.SIM_WEIXIN_TOKEN || 'sim-token-not-secret';
const accountId = 'sim-ilink-bot';
const userId = 'sim-authorized-user';
let sequence = 0;
let sendFailures = 0;
let updateFailures = 0;
const messages = [];
const sent = [];

function json(res, status, body) {
  const text = `${JSON.stringify(body)}\n`;
  res.writeHead(status, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(text) });
  res.end(text);
}

async function body(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const text = Buffer.concat(chunks).toString('utf8');
  return text.trim() ? JSON.parse(text) : {};
}

function inbound(text, overrides = {}) {
  sequence += 1;
  const now = Date.now();
  return {
    seq: sequence,
    message_id: overrides.message_id || sequence,
    client_id: overrides.client_id || `sim-client-${sequence}`,
    from_user_id: overrides.from_user_id || userId,
    to_user_id: accountId,
    message_type: 1,
    message_state: 2,
    create_time_ms: overrides.create_time_ms || now,
    session_id: overrides.session_id || 'sim-session',
    context_token: overrides.context_token || `sim-context-${sequence}`,
    item_list: [{ type: 1, text_item: { text: String(text) } }],
  };
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${host}:${port}`);
    if (req.method === 'GET' && url.pathname === '/ilink/bot/get_bot_qrcode') {
      return json(res, 200, {
        qrcode: 'sim-qrcode',
        qrcode_img_content: `http://${host}:${port}/admin/confirm`,
      });
    }
    if (req.method === 'GET' && url.pathname === '/ilink/bot/get_qrcode_status') {
      return json(res, 200, {
        status: 'confirmed',
        bot_token: token,
        ilink_bot_id: accountId,
        ilink_user_id: userId,
        baseurl: `http://${host}:${port}/`,
      });
    }
    if (req.method === 'POST' && url.pathname === '/ilink/bot/getupdates') {
      if (updateFailures > 0) {
        updateFailures -= 1;
        return json(res, 503, { ret: 1, errmsg: 'injected getupdates fault' });
      }
      const request = await body(req);
      const cursor = Number.parseInt(String(request.get_updates_buf || '0'), 10) || 0;
      const batch = messages.filter((item) => Number(item.seq) > cursor);
      const next = batch.length ? Number(batch.at(-1).seq) : cursor;
      return json(res, 200, { ret: 0, msgs: batch, get_updates_buf: String(next) });
    }
    if (req.method === 'POST' && url.pathname === '/ilink/bot/sendmessage') {
      const request = await body(req);
      if (sendFailures > 0) {
        sendFailures -= 1;
        return json(res, 503, { ret: 1, errcode: 50001, errmsg: 'injected send fault' });
      }
      const clientId = request?.msg?.client_id || crypto.randomUUID();
      sent.push({ received_at: new Date().toISOString(), client_id: clientId, body: request });
      return json(res, 200, { ret: 0, errcode: 0, client_id: clientId });
    }
    if (req.method === 'POST' && url.pathname === '/ilink/bot/getconfig') {
      return json(res, 200, { ret: 0, errcode: 0, typing_ticket: 'sim-typing-ticket' });
    }
    if (req.method === 'POST' && url.pathname === '/ilink/bot/sendtyping') {
      return json(res, 200, { ret: 0, errcode: 0 });
    }
    if (req.method === 'POST' && url.pathname === '/admin/inject') {
      const request = await body(req);
      const count = Math.max(1, Math.min(1000, Number(request.count || 1)));
      const created = [];
      for (let i = 0; i < count; i += 1) {
        const item = inbound(request.text || 'simulated message', request);
        messages.push(item);
        created.push(item.message_id);
      }
      return json(res, 200, { injected: created.length, message_ids: created, cursor: String(sequence) });
    }
    if (req.method === 'POST' && url.pathname === '/admin/replay') {
      const request = await body(req);
      const source = messages.find((item) => String(item.message_id) === String(request.message_id));
      if (!source) return json(res, 404, { error: 'message_not_found' });
      messages.push({ ...source, seq: ++sequence });
      return json(res, 200, { replayed: source.message_id, cursor: String(sequence) });
    }
    if (req.method === 'POST' && url.pathname === '/admin/fault') {
      const request = await body(req);
      sendFailures = Math.max(0, Number(request.send_failures || 0));
      updateFailures = Math.max(0, Number(request.update_failures || 0));
      return json(res, 200, { send_failures: sendFailures, update_failures: updateFailures });
    }
    if (req.method === 'POST' && url.pathname === '/admin/reset') {
      messages.length = 0; sent.length = 0; sequence = 0; sendFailures = 0; updateFailures = 0;
      return json(res, 200, { reset: true });
    }
    if (req.method === 'GET' && url.pathname === '/admin/sent') return json(res, 200, { sent });
    if (req.method === 'GET' && url.pathname === '/admin/state') {
      return json(res, 200, { sequence, queued_messages: messages.length, sent_messages: sent.length, sendFailures, updateFailures });
    }
    return json(res, 404, { error: 'not_found', path: url.pathname });
  } catch (error) {
    return json(res, 500, { error: String(error?.message || error) });
  }
});

server.listen(port, host, () => {
  console.log(`WEIXIN_SIMULATOR=READY base_url=http://${host}:${port}/ user_id=${userId}`);
});
