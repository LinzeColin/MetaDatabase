#!/usr/bin/env node
// Runs against the `ws` dependency already used by CyberBoss. It models only the methods required by the MVP contract.
import crypto from 'node:crypto';
import { WebSocketServer } from 'ws';

const host = process.env.SIM_CODEX_HOST || '127.0.0.1';
const port = Number(process.env.SIM_CODEX_PORT || 18765);
const failMode = process.env.SIM_CODEX_FAIL_MODE || '';
const wss = new WebSocketServer({ host, port });

function response(ws, id, result = {}) {
  ws.send(JSON.stringify({ jsonrpc: '2.0', id, result }));
}
function error(ws, id, code, message) {
  ws.send(JSON.stringify({ jsonrpc: '2.0', id, error: { code, message } }));
}
function notification(ws, method, params) {
  ws.send(JSON.stringify({ jsonrpc: '2.0', method, params }));
}

wss.on('connection', (ws) => {
  ws.on('message', (raw) => {
    let msg;
    try { msg = JSON.parse(raw.toString('utf8')); } catch { return; }
    if (msg.id == null) return;
    const method = String(msg.method || '');
    if (method === 'initialize') return response(ws, msg.id, { serverInfo: { name: 'cyberboss-sim', version: '0.0.0.4' } });
    if (method === 'model/list') return response(ws, msg.id, { data: [{ id: 'sim-model', model: 'sim-model', inputModalities: ['text'] }] });
    if (method === 'thread/start') {
      const threadId = `thread-${crypto.randomUUID()}`;
      return response(ws, msg.id, { thread: { id: threadId } });
    }
    if (method === 'thread/resume' || method === 'thread/compact/start') {
      return response(ws, msg.id, { thread: { id: msg.params?.threadId || `thread-${crypto.randomUUID()}` } });
    }
    if (method === 'turn/interrupt') return response(ws, msg.id, {});
    if (method === 'turn/start') {
      const threadId = msg.params?.threadId || `thread-${crypto.randomUUID()}`;
      const turnId = `turn-${crypto.randomUUID()}`;
      response(ws, msg.id, { turn: { id: turnId } });
      notification(ws, 'turn/started', { threadId, turn: { id: turnId }, turnId });
      if (failMode === 'turn_failed') {
        notification(ws, 'turn/failed', { threadId, turnId, turn: { id: turnId, error: { message: 'injected runtime failure' } } });
        return;
      }
      const input = Array.isArray(msg.params?.input) ? msg.params.input : [];
      const text = input.map((x) => x?.text || '').filter(Boolean).join('\n').slice(0, 400);
      notification(ws, 'item/completed', {
        threadId,
        turnId,
        item: { id: `item-${crypto.randomUUID()}`, type: 'agentMessage', text: `SIMULATED_CODEX_RESULT: ${text || 'Completed.'}` },
      });
      notification(ws, 'turn/completed', { threadId, turnId, turn: { id: turnId } });
      return;
    }
    return error(ws, msg.id, -32601, `method not implemented by simulator: ${method}`);
  });
});

console.log(`CODEX_SIMULATOR=READY endpoint=ws://${host}:${port}`);
