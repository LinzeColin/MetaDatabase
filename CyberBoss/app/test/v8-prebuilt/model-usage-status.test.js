'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {buildModelUsageSummary}=require('../../src/v8-prebuilt/status/model-usage-summary');
test('DeepSeek-only usage summary is aggregate and privacy safe',()=>{
  const summary=buildModelUsageSummary({usageRow:{calls:3,promptTokens:100,cacheHitTokens:40,cacheMissTokens:60,completionTokens:50,reasoningTokens:20,totalTokens:150,fallbackCharges:1},circuitRow:{state:'closed',probeInFlight:false},globalDailyLimit:1000,generatedAt:'2026-07-28T00:00:00Z'});
  assert.equal(summary.provider.provider,'deepseek');assert.equal(summary.provider.model,'deepseek-v4-pro');assert.equal(summary.provider.global_budget_used_percent,15);assert.equal(JSON.stringify(summary).includes('openai'),false);
});
