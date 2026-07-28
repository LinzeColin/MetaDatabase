"use strict";

// CB-700 / AC-014: DeepSeek speaks the OpenAI chat-completions protocol, so the
// same adapter shape is reused — but the origin and model allowlist stay pinned
// to DeepSeek's own server-owned policy.

const { normalizeHttpError, providerError } = require("./errors");
const { assertModel, assertPolicy } = require("./policy");

class DeepSeekAdapter {
  constructor({ policy, fetchImpl = globalThis.fetch }) {
    this.policy = assertPolicy(policy);
    if (this.policy.providerId !== "deepseek") {
      throw providerError("deepseek", "PROVIDER_NOT_SUPPORTED");
    }
    this.fetch = fetchImpl;
  }

  async sendText({ apiKey, model, messages, maxOutputTokens = 800, signal }) {
    assertModel(this.policy, model);
    const response = await this.fetch(`${this.policy.origin}/chat/completions`, {
      method: "POST",
      signal,
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: messages.map((message) => ({
          role: message.role,
          content: String(message.content),
        })),
        max_tokens: maxOutputTokens,
        stream: false,
      }),
    });
    const body = await response.text();
    if (!response.ok) {
      throw Object.assign(
        new Error("provider request failed"),
        normalizeHttpError("deepseek", response.status, body),
      );
    }
    const data = JSON.parse(body);
    const text = data && data.choices && data.choices[0] && data.choices[0].message
      ? data.choices[0].message.content
      : null;
    if (typeof text !== "string" || !text) {
      throw providerError("deepseek", "PROVIDER_BAD_RESPONSE");
    }
    return Object.freeze({ provider: "deepseek", model, text, usage: data.usage || null });
  }
}

module.exports = { DeepSeekAdapter };
