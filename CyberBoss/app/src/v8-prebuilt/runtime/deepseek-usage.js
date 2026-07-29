'use strict';

const PRICE_NANOCNY_PER_TOKEN = Object.freeze({ cacheHit: 25, cacheMiss: 3_000, output: 6_000 });

function nonNegativeInteger(value) { return Number.isSafeInteger(value) && value >= 0 ? value : 0; }

function normalizeDeepSeekUsage(usage) {
  if (!usage || !Number.isSafeInteger(usage.total_tokens) || usage.total_tokens < 0) return null;
  const promptTokens = nonNegativeInteger(usage.prompt_tokens);
  const cacheHitTokens = Math.min(promptTokens, nonNegativeInteger(usage.prompt_cache_hit_tokens));
  const cacheMissTokens = Math.min(promptTokens - cacheHitTokens, nonNegativeInteger(usage.prompt_cache_miss_tokens) || Math.max(0, promptTokens - cacheHitTokens));
  const completionTokens = nonNegativeInteger(usage.completion_tokens);
  const reasoningTokens = Math.min(completionTokens, nonNegativeInteger(usage.completion_tokens_details?.reasoning_tokens));
  const totalTokens = nonNegativeInteger(usage.total_tokens);
  const estimatedCostNanoCny = cacheHitTokens * PRICE_NANOCNY_PER_TOKEN.cacheHit
    + cacheMissTokens * PRICE_NANOCNY_PER_TOKEN.cacheMiss
    + completionTokens * PRICE_NANOCNY_PER_TOKEN.output;
  return Object.freeze({
    promptTokens,
    cacheHitTokens,
    cacheMissTokens,
    completionTokens,
    reasoningTokens,
    totalTokens,
    estimatedCostNanoCny,
    estimatedCostCny: estimatedCostNanoCny / 1_000_000_000,
  });
}

module.exports = { normalizeDeepSeekUsage, PRICE_NANOCNY_PER_TOKEN };
