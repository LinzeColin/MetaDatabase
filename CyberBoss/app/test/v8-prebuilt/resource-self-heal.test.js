'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const { evaluateResourceGate }=require('../../src/v8-prebuilt/operations/resource-gate');
const { decideSelfHeal }=require('../../src/v8-prebuilt/operations/self-heal-policy');

const healthy={freeMemoryBytes:2_000_000_000,freeDiskBytes:20_000_000_000,freeInodes:50_000,queueDepth:2,loadRatio:0.5};

test('resource gate fails closed on missing or unsafe measurements without model calls',()=>{
  assert.deepEqual(evaluateResourceGate({}),{state:'reject',reasonCode:'RESOURCE_MEASUREMENT_UNAVAILABLE',missing:['freeMemoryBytes','freeDiskBytes','freeInodes','queueDepth','loadRatio'],modelCalls:0});
  const low=evaluateResourceGate({...healthy,freeMemoryBytes:1});
  assert.equal(low.state,'reject');assert.equal(low.modelCalls,0);
  assert.equal(evaluateResourceGate(healthy).state,'allow');
});

test('self-heal is bounded and stops restart loops',()=>{
  const now=1_000_000;
  assert.equal(decideSelfHeal({reasonCode:'READYZ_FAILED',healthy:false,nowMs:now,restartTimestamps:[]}).action,'restart_process_family');
  assert.equal(decideSelfHeal({reasonCode:'READYZ_FAILED',healthy:false,nowMs:now,restartTimestamps:[now-1,now-2,now-3]}).action,'stop_restart_loop_and_alert');
  assert.equal(decideSelfHeal({reasonCode:'SECURITY_BOUNDARY_FAILED',healthy:false,nowMs:now,restartTimestamps:[]}).action,'isolate_and_alert');
});
