'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {OPERATOR_COMMANDS,presentUsage,validateOperatorSurface,operatorResult}=require('../../src/v8-prebuilt/ops/novice-presenter');

test('novice usage view explains budget and fuse without technical setup jargon',()=>{
  assert.deepEqual(presentUsage({percent:15}),{level:'healthy',title:'AI 使用正常',body:'本期已使用约 15%，达到上限后会自动停止。',action:'查看详情',usedPercent:15});
  const blocked=presentUsage({percent:100});
  assert.equal(blocked.level,'blocked');
  assert.equal(/API|Token|HTTP|SQLite|熔断器/.test(JSON.stringify(blocked)),false);
  const circuit=presentUsage({percent:20,circuitState:'open'});
  assert.equal(circuit.action,'检查连接');
});

test('operator surface is one command with complete lifecycle actions',()=>{
  assert.equal(validateOperatorSurface(OPERATOR_COMMANDS).ok,true);
  assert.deepEqual(validateOperatorSurface(['install','status']).missing,['doctor','start','stop','restart','backup','restore','rollback']);
  assert.match(operatorResult({command:'install',ok:true}).next,/status/);
  assert.match(operatorResult({command:'restore',ok:false,reasonCode:'MISSING_CREDENTIAL'}).next,/一次性说明/);
});
