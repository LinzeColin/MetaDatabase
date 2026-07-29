'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const {InviteService,MemoryInviteStore}=require('../../src/v8-prebuilt/users/invite-service');
const {bindReplyRoute,assertReplyRoute}=require('../../src/v8-prebuilt/channel/reply-route-binding');
const {buildCheckin}=require('../../src/v8-prebuilt/checkin/deterministic-checkin');
const {evaluateQuota}=require('../../src/v8-prebuilt/runtime/quota-policy');
const {buildSecureSetupLink,tokenAppearsInRequestTarget}=require('../../src/v8-prebuilt/security/secure-setup-link');

test('invite is hashed, bounded, one-use and revocable',()=>{
  let now=1000; const store=new MemoryInviteStore(); const svc=new InviteService({store,secret:crypto.randomBytes(32),clock:()=>now});
  const invite=svc.issue({createdByUserId:'usr_owner_12345678901234567890',ttlMs:100,maxUses:1});
  assert.equal([...store.rows.values()][0].codeHash.includes(invite.code),false);
  assert.equal(svc.consume({code:invite.code,userId:'usr_user_123456789012345678901'}).uses,1);
  assert.throws(()=>svc.consume({code:invite.code,userId:'usr_other_12345678901234567890'}),/INVITE_INVALID/);
  const second=svc.issue({createdByUserId:'usr_owner_12345678901234567890',ttlMs:100,maxUses:1});
  assert.equal(svc.revoke(second.code),true);
  assert.throws(()=>svc.consume({code:second.code,userId:'usr_other_12345678901234567890'}),/INVITE_INVALID/);
});

test('reply route cannot cross users or destinations',()=>{
  const key=crypto.randomBytes(32);
  const a=bindReplyRoute({routeKey:key,userId:'usr_A_12345678901234567890',botAccountId:'bot1',senderId:'senderA',contextToken:'contextA'});
  assert.equal(assertReplyRoute({routeKey:key,binding:a,userId:a.userId,botAccountId:'bot1',senderId:'senderA',contextToken:'contextA'}),true);
  assert.throws(()=>assertReplyRoute({routeKey:key,binding:a,userId:'usr_B_12345678901234567890',botAccountId:'bot1',senderId:'senderB',contextToken:'contextB'}),/REPLY_ROUTE_MISMATCH/);
});

test('checkin is deterministic, opt-out and quiet-hours safe',()=>{
  assert.deepEqual(buildCheckin({userId:'u',scheduledAt:'2026-01-01T12:00:00Z',enabled:false}),{action:'skip_disabled',modelCalls:0});
  assert.equal(buildCheckin({userId:'u',scheduledAt:'2026-01-01T23:00:00Z',quietStartHour:22,quietEndHour:8}).action,'skip_quiet_hours');
  const row=buildCheckin({userId:'u',scheduledAt:'2026-01-01T12:00:00Z',sequence:2});
  assert.equal(row.action,'send_template'); assert.equal(row.modelCalls,0);
});

test('quota failures are isolated and model-free',()=>{
  assert.equal(evaluateQuota({kind:'ai',userActive:1}).code,'USER_QUEUE_FULL');
  assert.equal(evaluateQuota({kind:'ai',globalProviderActive:2}).code,'GLOBAL_PROVIDER_BUSY');
  assert.equal(evaluateQuota({kind:'import',globalImportActive:1}).code,'IMPORT_BUSY');
  assert.equal(evaluateQuota({kind:'ai',text:'a'.repeat(32769)}).modelCalls,0);
});

test('setup token stays out of HTTP request target',()=>{
  const token='opaque_token_12345678901234567890';
  const link=buildSecureSetupLink({origin:'https://cyberboss.linzezhang.com',token,purpose:'provider_setup'});
  assert.equal(tokenAppearsInRequestTarget(link,token),false);
  assert.ok(new URL(link).hash.includes('opaque_token'));
});
