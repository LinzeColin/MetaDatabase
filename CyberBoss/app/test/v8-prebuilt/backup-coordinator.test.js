'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const { BackupCoordinator }=require('../../src/v8-prebuilt/backup/backup-coordinator');

function client(){ const map=new Map(); return { map, async putObject({key,body}){map.set(key,Buffer.from(body));return {etag:`etag-${map.size}`};},async getObject({key}){if(!map.has(key))throw new Error('missing');return map.get(key);} }; }
function coordinator(){
  const r2=client(),oci=client();let restored=null;
  const c=new BackupCoordinator({
    snapshotRuntimeDb:async()=>Buffer.from('sqlite-snapshot'),
    encryptSnapshot:async(value)=>Buffer.concat([Buffer.from('enc:'),value]),
    decryptSnapshot:async(value)=>value.subarray(4),
    r2,oci,
    validateSnapshot:async(value)=>{if(value.toString()!=='sqlite-snapshot')throw new Error('invalid snapshot');},
    restoreRuntimeDb:async(value)=>{restored=value.toString();return {integrity:'ok'};},
  });
  return {c,r2,oci,getRestored:()=>restored};
}

test('one encrypted backup is written to R2 and OCI and restores from either source',async()=>{
  const {c,r2,oci,getRestored}=coordinator();
  const receipt=await c.create({backupId:'backup_00000001',releaseId:'release_0000001',createdAt:'2026-07-28T00:00:00Z'});
  assert.equal(r2.map.size,1);assert.equal(oci.map.size,1);assert.match(receipt.sha256,/^[a-f0-9]{64}$/);
  assert.equal((await c.restore({receipt,source:'r2'})).ok,true);
  assert.equal((await c.restore({receipt,source:'oci'})).ok,true);
  assert.equal(getRestored(),'sqlite-snapshot');
});

test('corrupted backup fails before restore',async()=>{
  const {c,r2}=coordinator();
  const receipt=await c.create({backupId:'backup_00000002',releaseId:'release_0000001',createdAt:'2026-07-28T00:00:00Z'});
  r2.map.set(receipt.key,Buffer.from('corrupt'));
  await assert.rejects(()=>c.restore({receipt,source:'r2'}),/BACKUP_INTEGRITY_FAILED/);
});
