'use strict';
const { deepSeekUserId } = require('./deepseek-user-id');

const DEEPSEEK_MODEL = 'deepseek-v4-pro';
const DEEPSEEK_ENDPOINT = 'https://api.deepseek.com/chat/completions';
const DEEPSEEK_REASONING_EFFORT = 'high';

function sanitizeMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) throw Object.assign(new Error('MESSAGES_REQUIRED'), { code: 'MESSAGES_REQUIRED' });
  return messages.map((message) => {
    const role = ['system', 'user', 'assistant'].includes(message?.role) ? message.role : null;
    const content = typeof message?.content === 'string' ? message.content : null;
    if (!role || content === null) throw Object.assign(new Error('MESSAGE_INVALID'), { code: 'MESSAGE_INVALID' });
    // Ordinary-user runtime has no tools. DeepSeek reasoning_content is never persisted,
    // logged, shown to users, or replayed for no-tool conversations.
    return { role, content };
  });
}

function normalizeError(status) {
  if (status === 401 || status === 403) return { code: 'DEEPSEEK_KEY_INVALID', retryable: false };
  if (status === 402) return { code: 'DEEPSEEK_BALANCE_EXHAUSTED', retryable: false };
  if (status === 429) return { code: 'DEEPSEEK_RATE_LIMITED', retryable: true };
  if (status >= 500) return { code: 'DEEPSEEK_UNAVAILABLE', retryable: true };
  return { code: 'DEEPSEEK_REQUEST_REJECTED', retryable: false };
}

class DeepSeekV4ProRuntime {
  constructor({ apiKeyProvider, userIdSecret, fetchImpl = globalThis.fetch, timeoutMs = 300_000 } = {}) {
    if (typeof apiKeyProvider !== 'function' || typeof fetchImpl !== 'function') throw new TypeError('apiKeyProvider and fetchImpl are required');
    if (!Buffer.isBuffer(userIdSecret) || userIdSecret.length < 32) throw new TypeError('userIdSecret must be at least 32 bytes');
    this.apiKeyProvider = apiKeyProvider; this.userIdSecret = userIdSecret; this.fetch = fetchImpl; this.timeoutMs = timeoutMs;
  }

  async send({ messages, userId, signal }) {
    const apiKey = await this.apiKeyProvider();
    if (typeof apiKey !== 'string' || apiKey.trim().length < 8) throw Object.assign(new Error('OWNER_DEEPSEEK_KEY_MISSING'), { code: 'OWNER_DEEPSEEK_KEY_MISSING', retryable: false, preDispatch: true });
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    const abort = () => controller.abort(); if (signal) signal.addEventListener('abort', abort, { once: true });
    try {
      const body = {
        model: DEEPSEEK_MODEL,
        messages: sanitizeMessages(messages),
        thinking: { type: 'enabled' },
        reasoning_effort: DEEPSEEK_REASONING_EFFORT,
        stream: false,
        user_id: deepSeekUserId(userId, this.userIdSecret),
      };
      const response = await this.fetch(DEEPSEEK_ENDPOINT, {
        method: 'POST',
        headers: { authorization: `Bearer ${apiKey.trim()}`, 'content-type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const raw = await response.text(); let parsed = null;
      try { parsed = JSON.parse(raw); } catch {}
      if (!response.ok) {
        const classification = normalizeError(response.status);
        throw Object.assign(new Error(classification.code), { ...classification, status: response.status });
      }
      if (!parsed || parsed.model !== DEEPSEEK_MODEL) throw Object.assign(new Error('DEEPSEEK_MODEL_IDENTITY_MISMATCH'), { code: 'DEEPSEEK_MODEL_IDENTITY_MISMATCH', retryable: false });
      const content = parsed.choices?.[0]?.message?.content;
      if (typeof content !== 'string' || !content.trim()) throw Object.assign(new Error('DEEPSEEK_EMPTY_RESPONSE'), { code: 'DEEPSEEK_EMPTY_RESPONSE', retryable: false });
      return Object.freeze({
        responseId: parsed.id || null,
        model: parsed.model,
        outputText: content,
        usage: parsed.usage || null,
        reasoningContentPersisted: false,
      });
    } catch (error) {
      if (error?.name === 'AbortError') throw Object.assign(new Error('DEEPSEEK_TIMEOUT'), { code: 'DEEPSEEK_TIMEOUT', retryable: true });
      throw error;
    } finally {
      clearTimeout(timer); if (signal) signal.removeEventListener('abort', abort);
    }
  }
}

module.exports = {
  DeepSeekV4ProRuntime,
  DEEPSEEK_MODEL,
  DEEPSEEK_ENDPOINT,
  DEEPSEEK_REASONING_EFFORT,
  sanitizeMessages,
  normalizeError,
};
