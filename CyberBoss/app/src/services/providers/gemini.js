"use strict";

// CB-700 / AC-015: Google Gemini via generateContent with the x-goog-api-key
// header. The key never travels in the query string, where it would land in
// proxy and server access logs.

const { normalizeHttpError, providerError } = require("./errors");
const { assertModel, assertPolicy } = require("./policy");

class GeminiAdapter {
  constructor({ policy, fetchImpl = globalThis.fetch }) {
    this.policy = assertPolicy(policy);
    if (this.policy.providerId !== "google") {
      throw providerError("google", "PROVIDER_NOT_SUPPORTED");
    }
    this.fetch = fetchImpl;
  }

  async sendText({ apiKey, model, messages, maxOutputTokens = 800, signal }) {
    assertModel(this.policy, model);
    const contents = messages
      .filter((message) => ["user", "assistant"].includes(message.role))
      .map((message) => ({
        role: message.role === "assistant" ? "model" : "user",
        parts: [{ text: String(message.content) }],
      }));
    const url = `${this.policy.origin}/v1beta/models/${encodeURIComponent(model)}:generateContent`;
    const response = await this.fetch(url, {
      method: "POST",
      signal,
      headers: { "content-type": "application/json", "x-goog-api-key": apiKey },
      body: JSON.stringify({ contents, generationConfig: { maxOutputTokens } }),
    });
    const body = await response.text();
    if (!response.ok) {
      throw Object.assign(
        new Error("provider request failed"),
        normalizeHttpError("google", response.status, body),
      );
    }
    const data = JSON.parse(body);
    const parts =
      data.candidates && data.candidates[0] && data.candidates[0].content
        ? data.candidates[0].content.parts || []
        : [];
    const text = parts.map((part) => part.text || "").join("");
    if (!text) {
      throw providerError("google", "PROVIDER_BAD_RESPONSE");
    }
    return Object.freeze({
      provider: "google",
      model,
      text,
      usage: data.usageMetadata || null,
    });
  }
}

module.exports = { GeminiAdapter };
