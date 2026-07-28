"use strict";

// CB-700 / AC-046: each provider reports usage under different field names.
// They are normalised to one shape. When a provider reports nothing usable the
// result is explicitly marked unreported so the caller charges the full
// reservation instead of silently charging zero.

const PROVIDERS = Object.freeze([
  "openai",
  "deepseek",
  "google",
  "anthropic",
  "codex",
]);

class UsageNormalizerError extends Error {
  constructor(code) {
    super(code);
    this.name = "UsageNormalizerError";
    this.code = code;
  }
}

function asNonNegativeInteger(value) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? number : null;
}

function pick(...values) {
  for (const value of values) {
    const parsed = asNonNegativeInteger(value);
    if (parsed !== null) {
      return parsed;
    }
  }
  return null;
}

function normalizeProviderUsage(providerId, usage) {
  if (!PROVIDERS.includes(providerId)) {
    throw new UsageNormalizerError("PROVIDER_NOT_SUPPORTED");
  }
  if (!usage || typeof usage !== "object") {
    return Object.freeze({
      providerId,
      inputTokens: null,
      outputTokens: null,
      totalTokens: null,
      cacheReadTokens: null,
      reasoningTokens: null,
      reported: false,
      source: "reservation_fallback",
    });
  }

  let inputTokens = null;
  let outputTokens = null;
  let totalTokens = null;
  let cacheReadTokens = null;
  let reasoningTokens = null;
  const details = usage.input_tokens_details || {};
  const outputDetails = usage.output_tokens_details || usage.completion_tokens_details || {};

  if (providerId === "openai" || providerId === "codex") {
    inputTokens = pick(usage.input_tokens, usage.prompt_tokens);
    outputTokens = pick(usage.output_tokens, usage.completion_tokens);
    totalTokens = pick(usage.total_tokens);
    cacheReadTokens = pick(details.cached_tokens, usage.prompt_cache_hit_tokens);
    reasoningTokens = pick(outputDetails.reasoning_tokens);
  } else if (providerId === "deepseek") {
    inputTokens = pick(usage.prompt_tokens);
    outputTokens = pick(usage.completion_tokens);
    totalTokens = pick(usage.total_tokens);
    cacheReadTokens = pick(usage.prompt_cache_hit_tokens);
    reasoningTokens = pick(outputDetails.reasoning_tokens);
  } else if (providerId === "google") {
    inputTokens = pick(usage.promptTokenCount);
    outputTokens = pick(usage.candidatesTokenCount);
    totalTokens = pick(usage.totalTokenCount);
    cacheReadTokens = pick(usage.cachedContentTokenCount);
    reasoningTokens = pick(usage.thoughtsTokenCount);
  } else if (providerId === "anthropic") {
    inputTokens = pick(usage.input_tokens);
    outputTokens = pick(usage.output_tokens);
    totalTokens =
      inputTokens !== null && outputTokens !== null ? inputTokens + outputTokens : null;
    cacheReadTokens = pick(usage.cache_read_input_tokens);
  }

  if (totalTokens === null && inputTokens !== null && outputTokens !== null) {
    totalTokens = inputTokens + outputTokens;
  }
  const reported = inputTokens !== null && outputTokens !== null && totalTokens !== null;

  return Object.freeze({
    providerId,
    inputTokens,
    outputTokens,
    totalTokens,
    cacheReadTokens,
    reasoningTokens,
    reported,
    source: reported ? "provider_response" : "reservation_fallback",
  });
}

module.exports = {
  PROVIDERS,
  UsageNormalizerError,
  asNonNegativeInteger,
  normalizeProviderUsage,
};
