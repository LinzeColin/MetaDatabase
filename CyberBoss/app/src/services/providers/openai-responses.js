"use strict";

// CB-700 / AC-013: OpenAI over the Responses API at the fixed official origin.

const { normalizeHttpError, providerError } = require("./errors");
const { assertModel, assertPolicy } = require("./policy");

const ROLES = Object.freeze(["user", "assistant", "system", "developer"]);

class OpenAIResponsesAdapter {
  constructor({ policy, fetchImpl = globalThis.fetch }) {
    this.policy = assertPolicy(policy);
    if (this.policy.providerId !== "openai") {
      throw providerError("openai", "PROVIDER_NOT_SUPPORTED");
    }
    this.fetch = fetchImpl;
  }

  async sendText({ apiKey, model, messages, maxOutputTokens = 800, signal }) {
    assertModel(this.policy, model);
    const input = messages
      .filter((message) => ROLES.includes(message.role))
      .map((message) => ({ role: message.role, content: String(message.content) }));
    const response = await this.fetch(`${this.policy.origin}/v1/responses`, {
      method: "POST",
      signal,
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${apiKey}`,
      },
      // store:false keeps the user's prompt out of provider-side retention.
      body: JSON.stringify({ model, input, max_output_tokens: maxOutputTokens, store: false }),
    });
    const body = await response.text();
    if (!response.ok) {
      throw Object.assign(
        new Error("provider request failed"),
        normalizeHttpError("openai", response.status, body),
      );
    }
    const data = JSON.parse(body);
    const text =
      typeof data.output_text === "string"
        ? data.output_text
        : (data.output || [])
            .flatMap((item) => item.content || [])
            .filter((item) => item.type === "output_text")
            .map((item) => item.text)
            .join("");
    if (!text) {
      throw providerError("openai", "PROVIDER_BAD_RESPONSE");
    }
    return Object.freeze({ provider: "openai", model, text, usage: data.usage || null });
  }
}

module.exports = { OpenAIResponsesAdapter };
