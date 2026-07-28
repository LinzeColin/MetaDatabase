'use strict';
const { assertNoSensitiveValues } = require('./business-matrix');

function ratio(numerator, denominator) {
  if (!Number.isFinite(denominator) || denominator <= 0) return null;
  return Math.round((Number(numerator || 0) / denominator) * 1000) / 10;
}

function buildModelUsageSummary({ usageRow = {}, circuitRow = {}, globalDailyLimit, generatedAt = new Date().toISOString() }) {
  const provider = {
    provider: 'deepseek',
    model: 'deepseek-v4-pro',
    reasoning_effort: 'high',
    calls_today: Number(usageRow.calls || 0),
    prompt_tokens_today: Number(usageRow.promptTokens || 0),
    cache_hit_tokens_today: Number(usageRow.cacheHitTokens || 0),
    cache_miss_tokens_today: Number(usageRow.cacheMissTokens || 0),
    completion_tokens_today: Number(usageRow.completionTokens || 0),
    reasoning_tokens_today: Number(usageRow.reasoningTokens || 0),
    total_tokens_today: Number(usageRow.totalTokens || 0),
    fallback_usage_records_today: Number(usageRow.fallbackCharges || 0),
    global_budget_used_percent: ratio(usageRow.totalTokens, globalDailyLimit),
    circuit_state: circuitRow.state || 'closed',
    half_open_probe_in_flight: Boolean(circuitRow.probeInFlight),
  };
  const payload = { schema_version: 2, generated_at: generatedAt, provider };
  assertNoSensitiveValues(payload);
  return payload;
}

module.exports = { buildModelUsageSummary };
