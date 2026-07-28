"use strict";

// CB-700 / AC-016: Anthropic Messages API with the pinned version header and
// the server-owned model allowlist.

const { normalizeHttpError, providerError } = require("./errors");
const { assertModel, assertPolicy } = require("./policy");

const ANTHROPIC_VERSION = "2023-06-01";

class AnthropicAdapter {
  constructor({ policy, fetchImpl = globalThis.fetch }) {
    this.policy = assertPolicy(policy);
    if (this.policy.providerId !== "anthropic") {
      throw providerError("anthropic", "PROVIDER_NOT_SUPPORTED");
    }
    this.fetch = fetchImpl;
  }

  async sendText({ apiKey, model, messages, maxOutputTokens = 800, signal }) {
    assertModel(this.policy, model);
    const response = await this.fetch(`${this.policy.origin}/v1/messages`, {
      method: "POST",
      signal,
      headers: {
        "content-type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": ANTHROPIC_VERSION,
      },
      body: JSON.stringify({
        model,
        max_tokens: maxOutputTokens,
        messages: messages
          .filter((message) => ["user", "assistant"].includes(message.role))
          .map((message) => ({ role: message.role, content: String(message.content) })),
      }),
    });
    const body = await response.text();
    if (!response.ok) {
      throw Object.assign(
        new Error("provider request failed"),
        normalizeHttpError("anthropic", response.status, body),
      );
    }
    const data = JSON.parse(body);
    const text = (data.content || [])
      .filter((item) => item.type === "text")
      .map((item) => item.text)
      .join("");
    if (!text) {
      throw providerError("anthropic", "PROVIDER_BAD_RESPONSE");
    }
    return Object.freeze({
      provider: "anthropic",
      model,
      text,
      usage: data.usage || null,
    });
  }
}

module.exports = { ANTHROPIC_VERSION, AnthropicAdapter };
