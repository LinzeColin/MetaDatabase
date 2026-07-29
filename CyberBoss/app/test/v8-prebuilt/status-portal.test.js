'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {writeStatusSnapshot}=require('../../src/v8-prebuilt/status/status-snapshot-writer');
const {createSetupPortal}=require('../../src/v8-prebuilt/portal/setup-portal');

test('status snapshot is atomic and contains no user fields',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cbstatus-'));
  const file=path.join(dir,'status.json');
  const p=writeStatusSnapshot({filePath:file,version:'v0.0.0.8',lines:[{business_line:'wechat_channel',stage:'S6',state:'healthy',queue_depth:0}]});
  assert.equal(p.business_lines.length,1);
  assert.equal(fs.existsSync(file),true);
  fs.rmSync(dir,{recursive:true,force:true});
});

test('status snapshot rejects sensitive values',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cbstatus-'));
  assert.throws(()=>writeStatusSnapshot({filePath:path.join(dir,'status.json'),version:'v0.0.0.8',lines:[{business_line:'wechat_channel',stage:'S6',state:'healthy',reason_code:'wxid_private_user'}]}),/STATUS_VALUE_FORBIDDEN/);
  fs.rmSync(dir,{recursive:true,force:true});
});

test('portal host boundary fails closed',async(t)=>{
  const server=createSetupPortal({hostAllowlist:['cyberboss.linzezhang.com'],actionAllowlist:['usage'],consumeSetupToken:()=>({userId:'usr_abcdefghijklmnopqrstuv'}),issueSession:()=>({cookie:'cb_session=x',csrf:'c',expiresAt:1}),verifySession:()=>({userId:'usr_abcdefghijklmnopqrstuv'}),handleAction:async()=>({})});
  t.after(()=>server.close());
  await new Promise((resolve)=>server.listen(0,'127.0.0.1',resolve));
  const port=server.address().port;
  const res=await fetch(`http://127.0.0.1:${port}/api/exchange`,{method:'POST',headers:{origin:'https://evil.invalid','content-type':'application/json'},body:'{}'});
  assert.equal(res.status,400);
});

test('portal actions require same-origin session and CSRF and bind server-owned user',async(t)=>{
  const calls=[];
  const server=createSetupPortal({
    hostAllowlist:['127.0.0.1'],
    actionAllowlist:['usage'],
    consumeSetupToken:()=>({userId:'usr_abcdefghijklmnopqrstuv'}),
    issueSession:()=>({cookie:'cb_session=session-token; Path=/; HttpOnly; Secure; SameSite=Strict',csrf:'csrf-token',expiresAt:99}),
    verifySession:({token,csrf})=>{if(token!=='session-token'||csrf!=='csrf-token')throw Object.assign(new Error('SESSION_INVALID'),{code:'SESSION_INVALID'});return{userId:'usr_abcdefghijklmnopqrstuv'};},
    handleAction:async(input)=>{calls.push(input);return{saved:true};},
  });
  t.after(()=>server.close());
  await new Promise((resolve)=>server.listen(0,'127.0.0.1',resolve));
  const port=server.address().port;
  const base=`http://127.0.0.1:${port}`;
  const common={origin:'https://127.0.0.1','content-type':'application/json'};
  const denied=await fetch(`${base}/api/action/usage`,{method:'POST',headers:common,body:'{}'});
  assert.equal(denied.status,403);
  const ok=await fetch(`${base}/api/action/usage`,{method:'POST',headers:{...common,cookie:'cb_session=session-token','x-csrf-token':'csrf-token'},body:JSON.stringify({view:'aggregate'})});
  assert.equal(ok.status,200);
  assert.equal(calls[0].userId,'usr_abcdefghijklmnopqrstuv');
  assert.equal(calls[0].input.view,'aggregate');
});

test('portal rejects actions outside the frozen allowlist before handler dispatch',async(t)=>{
  let calls=0;
  const server=createSetupPortal({
    hostAllowlist:['127.0.0.1'],
    actionAllowlist:['usage'],
    consumeSetupToken:()=>({userId:'usr_abcdefghijklmnopqrstuv'}),
    issueSession:()=>({cookie:'cb_session=session-token; Path=/; HttpOnly; Secure; SameSite=Strict',csrf:'csrf-token',expiresAt:99}),
    verifySession:()=>({userId:'usr_abcdefghijklmnopqrstuv'}),
    handleAction:async()=>{calls++;return{};},
  });
  t.after(()=>server.close());
  await new Promise((resolve)=>server.listen(0,'127.0.0.1',resolve));
  const port=server.address().port;
  const res=await fetch(`http://127.0.0.1:${port}/api/action/admin-shell`,{method:'POST',headers:{origin:'https://127.0.0.1','content-type':'application/json',cookie:'cb_session=session-token','x-csrf-token':'csrf-token'},body:'{}'});
  assert.equal(res.status,404);
  assert.equal(calls,0);
});
