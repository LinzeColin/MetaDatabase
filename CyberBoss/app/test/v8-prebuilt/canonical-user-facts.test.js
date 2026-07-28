'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildCanonicalFact, planCanonicalSync } = require('../../src/v8-prebuilt/data/canonical-user-facts');

test('canonical fact is stable, user-scoped and rejects raw conversation fields', () => {
  const input = { userId:'usr_abcdefghijklmnopqrstuv', type:'profile.updated', occurredAt:'2026-07-28T00:00:00Z', payload:{category:'goal',value:'完成项目'}, objectRefs:['r2://a'], sourceEventId:'evt-1' };
  const a=buildCanonicalFact(input); const b=buildCanonicalFact(input);
  assert.equal(a.fact_id,b.fact_id); assert.equal(a.sync_priority,'daily'); assert.equal(a.user_id,input.userId);
  assert.throws(()=>buildCanonicalFact({...input,payload:{raw_message:'not allowed'}}),/CANONICAL_RAW_CONTENT_FORBIDDEN/);
});

test('canonical sync is immediate for critical facts, daily for normal facts and creates no empty commit', () => {
  const base={userId:'usr_abcdefghijklmnopqrstuv',occurredAt:'2026-07-28T00:00:00Z',payload:{},objectRefs:[]};
  const normal=buildCanonicalFact({...base,type:'profile.updated',sourceEventId:'evt-normal'});
  const incident=buildCanonicalFact({...base,type:'incident.opened',sourceEventId:'evt-incident'});
  const notDue=planCanonicalSync([normal,incident],{now:'2026-07-28T12:00:00Z',lastDailySyncAt:'2026-07-28T00:00:00Z'});
  assert.equal(notDue.immediate.length,1); assert.equal(notDue.daily.length,0); assert.equal(notDue.deferred_daily_count,1); assert.equal(notDue.create_commit,true);
  const empty=planCanonicalSync([],{now:'2026-07-28T12:00:00Z',lastDailySyncAt:'2026-07-28T00:00:00Z'});
  assert.equal(empty.create_commit,false);
});
