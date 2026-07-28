'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {DatabaseSync}=require('node:sqlite');
const {WeixinAccountSupervisor,extractMessages,extractCursor}=require('../../src/v8-prebuilt/weixin/account-supervisor');
const {SqliteIngressStore}=require('../../src/v8-prebuilt/weixin/sqlite-ingress-store');
const {SharedBotAccountStore}=require('../../src/v8-prebuilt/weixin/shared-bot-account-store');
const {SqliteUserRepository}=require('../../src/v8-prebuilt/users/user-repository');

function setup(){
  const db=new DatabaseSync(':memory:');
  db.exec(fs.readFileSync(path.join(__dirname,'../../migrations/multiuser_foundation.sql.template'),'utf8'));
  db.exec(fs.readFileSync(path.join(__dirname,'../../migrations/public_scan_entry.sql.template'),'utf8'));
  db.prepare(`INSERT INTO users(user_id,role,status,created_at,updated_at) VALUES(?,?,?,?,?)`).run('owner','owner','active','2026-07-28T00:00:00Z','2026-07-28T00:00:00Z');
  return db;
}
function activate(db,master){
  const store=new SharedBotAccountStore({db,masterKey:master,ownerUserId:'owner',clock:()=>1});
  store.activate({accountId:'shared-bot',botToken:'synthetic-bot-token',baseUrl:'https://ilink.invalid/',weixinUserId:'owner-wx'});
  return store;
}

test('extracts supported update shapes and cursor',()=>{assert.equal(extractMessages({message_list:[{x:1}]}).length,1);assert.equal(extractCursor({get_updates_buf:'c'},'x'),'c');});

test('supervisor persists before cursor and processes deterministic start',async()=>{
  const db=setup(),master=Buffer.alloc(32,1),payload=Buffer.alloc(32,2);activate(db,master);
  const ingress=new SqliteIngressStore({db,clock:()=>1});let handled=0;
  const users=new SqliteUserRepository({db,identityKey:Buffer.alloc(32,5),clock:()=> '2026-07-28T00:00:00Z'});
  const s=new WeixinAccountSupervisor({db,masterKey:master,payloadKey:payload,ingress,userRepository:users,firstReply:{handle:()=>{handled+=1;return{action:'first_reply_queued'};}},clientFactory:()=>({getUpdates:async()=>({get_updates_buf:'c1',message_list:[{message_id:'m1',from_user_id:'sender-1',context_token:'ct',item_list:[{text_item:{text:'开始'}}]}]})})});
  const result=await s.tick();assert.equal(result.poll[0].inserted,1);assert.equal(handled,1);assert.equal(ingress.cursor('shared-bot').cursor,'c1');assert.equal(db.prepare(`SELECT state FROM weixin_inbox_v8`).get().state,'processed');db.close();
});

test('auth failure marks the one shared bot reauth_required',async()=>{
  const db=setup(),master=Buffer.alloc(32,1),payload=Buffer.alloc(32,2);activate(db,master);
  const s=new WeixinAccountSupervisor({db,masterKey:master,payloadKey:payload,ingress:new SqliteIngressStore({db}),clientFactory:()=>({getUpdates:async()=>{throw Object.assign(new Error('x'),{code:'ILINK_HTTP_401'});}})});
  assert.equal((await s.tick()).poll[0].status,'failed');assert.equal(db.prepare(`SELECT status FROM weixin_accounts WHERE singleton_key='shared'`).get().status,'reauth_required');db.close();
});

test('one shared bot separates two senders by server-owned user identity',async()=>{
  const db=setup(),master=Buffer.alloc(32,1),payload=Buffer.alloc(32,2);activate(db,master);
  const users=new SqliteUserRepository({db,identityKey:Buffer.alloc(32,5),clock:()=> '2026-07-28T00:00:00Z'});
  const ingress=new SqliteIngressStore({db,clock:()=>1});
  const s=new WeixinAccountSupervisor({db,masterKey:master,payloadKey:payload,ingress,userRepository:users,clientFactory:()=>({getUpdates:async()=>({get_updates_buf:'c1',message_list:[{message_id:'m1',from_user_id:'sender-1'},{message_id:'m2',from_user_id:'sender-2'}]})})});
  const result=await s.pollAccount(s.activeAccounts()[0]);assert.equal(result.inserted,2);
  const rows=db.prepare(`SELECT DISTINCT user_id AS userId FROM weixin_inbox_v8 ORDER BY user_id`).all();assert.equal(rows.length,2);assert.notEqual(rows[0].userId,rows[1].userId);assert.equal(db.prepare(`SELECT COUNT(*) AS n FROM weixin_accounts`).get().n,1);db.close();
});
