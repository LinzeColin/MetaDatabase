'use strict';
const test=require('node:test');const assert=require('node:assert/strict');const{reduceOnboarding}=require('../../src/v8-prebuilt/users/onboarding-state');
test('invite and consent complete before any model route',()=>{
  const a=reduceOnboarding('unseen','开始');assert.deepEqual(a,{state:'pending_invite',action:'request_invite',modelCalls:0});
  const b=reduceOnboarding(a.state,'邀请码',{inviteValidated:true});assert.deepEqual(b,{state:'pending_consent',action:'show_consent',modelCalls:0});
  const c=reduceOnboarding(b.state,'同意并开始');assert.deepEqual(c,{state:'active',action:'show_home',modelCalls:0});
  assert.equal(reduceOnboarding('pending_invite','随便聊').modelCalls,0);
});
