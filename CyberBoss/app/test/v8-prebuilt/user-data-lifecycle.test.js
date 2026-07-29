'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const { buildUserExportManifest, executeDeletion }=require('../../src/v8-prebuilt/privacy/user-data-lifecycle');
const { ORDER }=require('../../src/v8-prebuilt/privacy/deletion-plan');

const userId='usr_AAAAAAAAAAAAAAAAAAAA';

test('export manifest is deterministic and contains references rather than raw content',()=>{
  const a=buildUserExportManifest({userId,generatedAt:'2026-07-28T00:00:00Z',factRefs:['f2','f1','f1'],objectRefs:['o1']});
  const b=buildUserExportManifest({userId,generatedAt:'2026-07-28T00:00:00Z',factRefs:['f1','f2'],objectRefs:['o1']});
  assert.equal(a.manifestSha256,b.manifestSha256);assert.deepEqual(a.factRefs,['f1','f2']);assert.equal(Object.hasOwn(a,'rawChat'),false);
});

test('deletion executes every ordered action once and resumes from receipts',async()=>{
  const map=new Map();const calls=[];
  const receiptStore={async get({idempotencyKey}){return map.get(idempotencyKey)||null;},async put({idempotencyKey,receipt}){map.set(idempotencyKey,receipt);}};
  const handlers=Object.fromEntries(ORDER.map((action)=>[action,async({userId:id})=>{calls.push(action);assert.equal(id,userId);return {ok:true};}]));
  const first=await executeDeletion({userId,requestId:'delete-request-0001',receiptStore,handlers});
  const second=await executeDeletion({userId,requestId:'delete-request-0001',receiptStore,handlers});
  assert.equal(first.ok,true);assert.equal(second.ok,true);assert.equal(calls.length,ORDER.length);
});

test('deletion fails closed when a required handler is absent',async()=>{
  const receiptStore={get:async()=>null,put:async()=>{}};
  await assert.rejects(()=>executeDeletion({userId,requestId:'delete-request-0002',receiptStore,handlers:{}}),/DELETION_HANDLER_MISSING/);
});
