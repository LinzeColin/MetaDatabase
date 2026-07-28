"use strict";

// CB-700: the single outbound path for ordinary-user model calls. Every
// adapter is constructed from a server-owned policy at startup, so there is no
// runtime opportunity to introduce a new origin.

const { AnthropicAdapter } = require("./anthropic");
const { DeepSeekAdapter } = require("./deepseek");
const { GeminiAdapter } = require("./gemini");
const { OpenAIResponsesAdapter } = require("./openai-responses");
const { ProviderPolicyError, selectServerPolicy } = require("./policy");

// Frozen official origins. A policy naming a different origin is a
// configuration error, not a user choice.
const OFFICIAL_ORIGINS = Object.freeze({
  openai: "https://api.openai.com",
  deepseek: "https://api.deepseek.com",
  google: "https://generativelanguage.googleapis.com",
  anthropic: "https://api.anthropic.com",
});

class ProviderRouter {
  constructor({ policies, fetchImpl = globalThis.fetch }) {
    if (!policies) {
      throw new ProviderPolicyError("PROVIDER_POLICIES_REQUIRED");
    }
    const build = (providerId, Adapter) => {
      const policy = selectServerPolicy(policies, providerId);
      if (policy.origin !== OFFICIAL_ORIGINS[providerId]) {
        throw new ProviderPolicyError("PROVIDER_ORIGIN_NOT_OFFICIAL");
      }
      return new Adapter({ policy, fetchImpl });
    };
    this.adapters = new Map([
      ["openai", build("openai", OpenAIResponsesAdapter)],
      ["deepseek", build("deepseek", DeepSeekAdapter)],
      ["google", build("google", GeminiAdapter)],
      ["anthropic", build("anthropic", AnthropicAdapter)],
    ]);
  }

  get(providerId) {
    const adapter = this.adapters.get(providerId);
    if (!adapter) {
      throw new ProviderPolicyError("PROVIDER_NOT_SUPPORTED");
    }
    return adapter;
  }

  allowedModels(providerId) {
    return this.get(providerId).policy.models;
  }

  // Only these five fields cross into an adapter; a caller cannot add a base
  // URL, a header or a retention flag.
  sendText({ providerId, apiKey, model, messages, maxOutputTokens, signal }) {
    return this.get(providerId).sendText({
      apiKey,
      model,
      messages,
      maxOutputTokens,
      signal,
    });
  }
}

module.exports = { OFFICIAL_ORIGINS, ProviderRouter };
