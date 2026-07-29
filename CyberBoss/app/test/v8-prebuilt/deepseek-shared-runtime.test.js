'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { DatabaseSync } = require('node:sqlite');
const { FiveSeatRegistry } = require('../../src/v8-prebuilt/runtime/five-seat-registry');
const { GlobalDailyTokenLedger, GLOBAL_DAILY_TOKEN_CAP } = require('../../src/v8-prebuilt/runtime/global-daily-token-ledger');
const { conservativeDeepSeekReservation, MODEL_CONTEXT_TOKENS, MODEL_MAX_OUTPUT_TOKENS } = require('../../src/v8-prebuilt/runtime/deepseek-token-reservation');
const { normalizeDeepSeekUsage } = require('../../src/v8-prebuilt/runtime/deepseek-usage');
const { SqliteDeepSeekCircuitBreaker } = require('../../src/v8-prebuilt/runtime/sqlite-deepseek-circuit-breaker');
const { DeepSeekV4ProRuntime, DEEPSEEK_MODEL, DEEPSEEK_ENDPOINT } = require('../../src/v8-prebuilt/runtime/deepseek-v4-pro-runtime');
const { SharedDeepSeekController } = require('../../src/v8-prebuilt/runtime/shared-deepseek-controller');
const { projectSharedDeepSeekStatus } = require('../../src/v8-prebuilt/runtime/shared-deepseek-status');

test('five ordinary seats are atomic and owner is exempt', () => {
  const seats = new FiveSeatRegistry({ db: new DatabaseSync(':memory:') });
  assert.equal(seats.claim({ userId: 'owner', role: 'owner' }).seatNumber, null);
  for (let index = 1; index <= 5; index += 1) assert.equal(seats.claim({ userId: `user-${index}` }).accepted, true);
  const sixth = seats.claim({ userId: 'user-6' });
  assert.equal(sixth.accepted, false); assert.equal(sixth.code, 'USER_CAPACITY_FULL'); assert.equal(sixth.providerCalls, 0);
  assert.deepEqual(seats.snapshot(), { activeOrdinarySeats: 5, seatLimit: 5, remainingSeats: 0 });
});

test('only the UTC daily global 1B token cap is enforced', () => {
  let now = Date.parse('2026-07-28T12:00:00Z');
  const ledger = new GlobalDailyTokenLedger({ db: new DatabaseSync(':memory:'), clock: () => now });
  const first = ledger.reserve({ requestId: 'request-a', userId: 'user-a', estimatedTotalTokens: GLOBAL_DAILY_TOKEN_CAP - 1 });
  assert.equal(first.accepted, true);
  const second = ledger.reserve({ requestId: 'request-b', userId: 'user-b', estimatedTotalTokens: 2 });
  assert.equal(second.accepted, false); assert.equal(second.code, 'GLOBAL_DAILY_TOKEN_CAP'); assert.equal(second.providerCalls, 0);
  ledger.settle({ reservationId: first.reservationId, usage: { prompt_tokens: GLOBAL_DAILY_TOKEN_CAP - 1, prompt_cache_hit_tokens: 0, prompt_cache_miss_tokens: GLOBAL_DAILY_TOKEN_CAP - 1, completion_tokens: 0, total_tokens: GLOBAL_DAILY_TOKEN_CAP - 1 } });
  now = Date.parse('2026-07-29T00:00:00Z');
  assert.equal(ledger.status(now).remainingTokens, GLOBAL_DAILY_TOKEN_CAP);
  assert.equal(Object.hasOwn(ledger.status(now), 'monthlyUsedTokens'), false);
});

test('request id is idempotent and identity-bound', () => {
  const ledger = new GlobalDailyTokenLedger({ db: new DatabaseSync(':memory:') });
  const first = ledger.reserve({ requestId: 'same', userId: 'user-a', estimatedTotalTokens: 100 });
  assert.equal(ledger.reserve({ requestId: 'same', userId: 'user-a', estimatedTotalTokens: 100 }).existing, true);
  assert.equal(ledger.reserve({ requestId: 'same', userId: 'user-b', estimatedTotalTokens: 100 }).code, 'REQUEST_IDENTITY_CONFLICT');
  ledger.settle({ reservationId: first.reservationId, usage: { prompt_tokens: 7, prompt_cache_hit_tokens: 2, prompt_cache_miss_tokens: 5, completion_tokens: 3, total_tokens: 10, completion_tokens_details: { reasoning_tokens: 2 } } });
  assert.equal(ledger.reserve({ requestId: 'same', userId: 'user-a', estimatedTotalTokens: 1 }).code, 'REQUEST_ALREADY_ACCOUNTED');
});

test('DeepSeek usage includes cache, output and reasoning tokens with CNY cost', () => {
  const usage = normalizeDeepSeekUsage({ prompt_tokens: 100, prompt_cache_hit_tokens: 40, prompt_cache_miss_tokens: 60, completion_tokens: 20, total_tokens: 120, completion_tokens_details: { reasoning_tokens: 10 } });
  assert.deepEqual({ prompt: usage.promptTokens, hit: usage.cacheHitTokens, miss: usage.cacheMissTokens, completion: usage.completionTokens, reasoning: usage.reasoningTokens, total: usage.totalTokens }, { prompt: 100, hit: 40, miss: 60, completion: 20, reasoning: 10, total: 120 });
  assert.equal(usage.estimatedCostNanoCny, 40 * 25 + 60 * 3000 + 20 * 6000);
});

test('reservation uses official context and output ceilings without per-user quota', () => {
  assert.equal(MODEL_CONTEXT_TOKENS, 1_000_000); assert.equal(MODEL_MAX_OUTPUT_TOKENS, 384_000);
  const reserved = conservativeDeepSeekReservation([{ role: 'user', content: 'hello' }]);
  assert.ok(reserved >= 384_000); assert.ok(reserved <= 1_000_000);
});

test('DeepSeek V4 Pro request is fixed to official endpoint, thinking high and no unsupported knobs', async () => {
  let observed;
  const runtime = new DeepSeekV4ProRuntime({
    apiKeyProvider: async () => 'owner-deepseek-project-key',
    userIdSecret: Buffer.alloc(32, 7),
    fetchImpl: async (url, options) => {
      observed = { url, headers: options.headers, body: JSON.parse(options.body) };
      return new Response(JSON.stringify({ id: 'chat-1', model: 'deepseek-v4-pro', choices: [{ message: { role: 'assistant', content: '完成', reasoning_content: 'private chain' } }], usage: { prompt_tokens: 5, prompt_cache_hit_tokens: 1, prompt_cache_miss_tokens: 4, completion_tokens: 3, total_tokens: 8, completion_tokens_details: { reasoning_tokens: 2 } } }), { status: 200 });
    },
  });
  const result = await runtime.send({ userId: 'usr-secret-user', messages: [{ role: 'user', content: '你好', reasoning_content: 'must-strip' }] });
  assert.equal(observed.url, DEEPSEEK_ENDPOINT); assert.equal(observed.body.model, DEEPSEEK_MODEL);
  assert.deepEqual(observed.body.thinking, { type: 'enabled' }); assert.equal(observed.body.reasoning_effort, 'high');
  for (const key of ['temperature', 'top_p', 'presence_penalty', 'frequency_penalty', 'tool_choice', 'tools']) assert.equal(Object.hasOwn(observed.body, key), false);
  assert.equal(JSON.stringify(observed.body).includes('usr-secret-user'), false);
  assert.equal(JSON.stringify(observed.body).includes('reasoning_content'), false);
  assert.equal(result.outputText, '完成'); assert.equal(result.reasoningContentPersisted, false);
  assert.equal(Object.hasOwn(result, 'reasoningContent'), false);
});

test('controller rejects sixth seat and global cap before provider call', async () => {
  const db = new DatabaseSync(':memory:'); const seats = new FiveSeatRegistry({ db });
  for (let index = 1; index <= 5; index += 1) seats.claim({ userId: `user-${index}` });
  let calls = 0;
  const controller = new SharedDeepSeekController({
    seats,
    ledger: new GlobalDailyTokenLedger({ db }),
    runtime: { async send() { calls += 1; return { outputText: 'ok', usage: { prompt_tokens: 1, prompt_cache_hit_tokens: 0, prompt_cache_miss_tokens: 1, completion_tokens: 1, total_tokens: 2 } }; } },
    circuit: new SqliteDeepSeekCircuitBreaker({ db }),
    estimateTokens: () => 2,
  });
  const result = await controller.execute({ userId: 'user-6', requestId: 'denied', messages: [{ role: 'user', content: 'x' }] });
  assert.equal(result.code, 'USER_CAPACITY_FULL'); assert.equal(result.providerCalls, 0); assert.equal(calls, 0);
});

test('DeepSeek technical circuit persists and is not a user quota', () => {
  let now = 0; const db = new DatabaseSync(':memory:');
  const first = new SqliteDeepSeekCircuitBreaker({ db, failureThreshold: 2, cooldownMs: 100, probeLeaseMs: 50, clock: () => now });
  first.failure({ retryable: true, code: 'DEEPSEEK_UNAVAILABLE' }); first.failure({ retryable: true, code: 'DEEPSEEK_UNAVAILABLE' });
  assert.equal(first.before().code, 'DEEPSEEK_CIRCUIT_OPEN');
  const restart = new SqliteDeepSeekCircuitBreaker({ db, failureThreshold: 2, cooldownMs: 100, probeLeaseMs: 50, clock: () => now });
  now = 100; assert.equal(restart.before().allowed, true); assert.equal(restart.before().code, 'DEEPSEEK_CIRCUIT_PROBE_BUSY');
  now = 150; assert.equal(restart.before().allowed, true); restart.success(); assert.equal(restart.snapshot().state, 'closed');
});

test('status is aggregate and contains no user identity', () => {
  const db = new DatabaseSync(':memory:'); const seats = new FiveSeatRegistry({ db }); seats.claim({ userId: 'private-user' });
  const ledger = new GlobalDailyTokenLedger({ db }); const reservation = ledger.reserve({ requestId: 'status-request', userId: 'private-user', estimatedTotalTokens: 20 });
  ledger.settle({ reservationId: reservation.reservationId, usage: { prompt_tokens: 8, prompt_cache_hit_tokens: 2, prompt_cache_miss_tokens: 6, completion_tokens: 2, total_tokens: 10, completion_tokens_details: { reasoning_tokens: 1 } } });
  const status = projectSharedDeepSeekStatus({ seats, ledger, circuit: new SqliteDeepSeekCircuitBreaker({ db }) });
  assert.equal(status.model, 'deepseek-v4-pro'); assert.equal(status.seatLimit, 5); assert.equal(status.capTokens, 1_000_000_000);
  assert.equal(JSON.stringify(status).includes('private-user'), false); assert.ok(status.estimatedCostCny > 0);
});
