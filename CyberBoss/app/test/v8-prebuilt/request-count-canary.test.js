'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const { evaluateRequestCountCanary }=require('../../src/v8-prebuilt/release/request-count-canary');

test('canary promotes by request count without real-time waiting',()=>{
  assert.equal(evaluateRequestCountCanary({totalRequests:10,errorCount:0,p95Ms:1000}).decision,'continue_by_request_count');
  const pass=evaluateRequestCountCanary({totalRequests:20,errorCount:0,p95Ms:1000});
  assert.equal(pass.decision,'promote');assert.equal(pass.modelCalls,0);
});

test('privacy or duplicate side effect causes immediate rollback',()=>{
  assert.equal(evaluateRequestCountCanary({totalRequests:1,errorCount:0,p95Ms:1,privacyViolations:1}).reasonCode,'PRIVACY_VIOLATION');
  assert.equal(evaluateRequestCountCanary({totalRequests:1,errorCount:0,p95Ms:1,duplicateSideEffects:1}).reasonCode,'DUPLICATE_SIDE_EFFECT');
});
