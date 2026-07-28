'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {
  ALLOWED_ACTIONS,
  ACTION_TIMEOUT_MS,
  validateActionConfig,
  validateRootControlledFile,
  loadActionConfig,
  runOperatorAction,
}=require('../../src/v8-prebuilt/ops/operator-dispatcher');

function config(){return Object.fromEntries(ALLOWED_ACTIONS.map((action)=>[action,[`/opt/cyberboss/${action}.sh`]]));}

test('operator dispatcher exposes the complete frozen lifecycle, bounded timeout and never uses a shell',()=>{
  const calls=[];
  const result=runOperatorAction({action:'backup',config:config(),environment:{NODE_OPTIONS:'--require /tmp/evil.js',CYBERBOSS_RELEASE_ID:'release-safe'},runner:(exe,args,options)=>{calls.push({exe,args,options});return {status:0};}});
  assert.equal(result.ok,true);assert.equal(calls.length,1);assert.equal(calls[0].options.shell,false);assert.equal(calls[0].exe,'/opt/cyberboss/backup.sh');
  assert.equal(calls[0].options.timeout,ACTION_TIMEOUT_MS.backup);assert.equal(calls[0].options.killSignal,'SIGTERM');
  assert.equal(calls[0].options.env.NODE_OPTIONS,undefined);assert.equal(calls[0].options.env.CYBERBOSS_RELEASE_ID,'release-safe');
});

test('operator dispatcher rejects unknown actions, relative executables and config expansion',()=>{
  assert.throws(()=>runOperatorAction({action:'shell',config:config()}),/OPERATOR_ACTION_NOT_ALLOWED/);
  const relative=config();relative.start=['systemctl','start','cyberboss'];
  assert.throws(()=>validateActionConfig(relative),/absolute executable/);
  const unknown={...config(),exec:['/bin/true']};
  assert.throws(()=>validateActionConfig(unknown),/OPERATOR_CONFIG_ACTION_NOT_ALLOWED/);
});

test('root-controlled config rejects symlink, wrong owner expectation and group/world writable mode',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cyberboss-operator-'));
  const executable=path.join(dir,'doctor.sh');
  const cfg=path.join(dir,'operator-actions.json');
  fs.writeFileSync(executable,'#!/bin/sh\nexit 0\n',{mode:0o700});
  const value=Object.fromEntries(ALLOWED_ACTIONS.map((action)=>[action,[executable]]));
  fs.writeFileSync(cfg,JSON.stringify(value),{mode:0o600});
  const uid=process.getuid();
  assert.equal(loadActionConfig(cfg,{expectedUid:uid,verifyExecutables:true}).doctor[0],executable);
  assert.throws(()=>loadActionConfig(cfg,{expectedUid:uid+1,verifyExecutables:false}),/OPERATOR_FILE_OWNER_INVALID/);
  fs.chmodSync(cfg,0o622);
  assert.throws(()=>loadActionConfig(cfg,{expectedUid:uid,verifyExecutables:false}),/OPERATOR_FILE_WRITABLE_BY_NON_OWNER/);
  fs.chmodSync(cfg,0o600);
  const link=path.join(dir,'config-link.json');fs.symlinkSync(cfg,link);
  assert.throws(()=>loadActionConfig(link,{expectedUid:uid,verifyExecutables:false}),/OPERATOR_SYMLINK_NOT_ALLOWED/);
  fs.rmSync(dir,{recursive:true,force:true});
});

test('executable verification rejects non-owner writable programs',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cyberboss-executable-'));
  const executable=path.join(dir,'run.sh');fs.writeFileSync(executable,'#!/bin/sh\nexit 0\n',{mode:0o700});fs.chmodSync(executable,0o722);
  assert.throws(()=>validateRootControlledFile(executable,{expectedUid:process.getuid(),allowSymlink:true}),/OPERATOR_FILE_WRITABLE_BY_NON_OWNER/);
  fs.rmSync(dir,{recursive:true,force:true});
});

test('operator failures and timeouts return one novice recovery action without retry loop',()=>{
  const failure=runOperatorAction({action:'start',config:config(),runner:()=>({status:7})});
  assert.equal(failure.ok,false);assert.equal(failure.code,7);assert.match(failure.next,/doctor/);
  const timeout=runOperatorAction({action:'backup',config:config(),runner:()=>({status:null,error:{code:'ETIMEDOUT'}})});
  assert.equal(timeout.ok,false);assert.equal(timeout.code,124);assert.match(timeout.title,/安全停止/);
});
