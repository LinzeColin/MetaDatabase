'use strict';
const {ILinkMessageClient}=require('./ilink-message-client');
const {decryptBotAccount}=require('../public-entry/account-token-crypto');
const {decryptJson}=require('./payload-crypto');

function extractMessages(update){
  const candidates=[update?.messages,update?.message_list,update?.msg_list,update?.updates];
  const list=candidates.find(Array.isArray)||[];
  return list.filter(x=>x&&typeof x==='object');
}
function extractCursor(update,current=''){
  return String(update?.get_updates_buf??update?.sync_buf??update?.next_cursor??current??'');
}
class WeixinAccountSupervisor{
  constructor({db,masterKey,payloadKey,ingress,firstReply,userRepository,onMessage=async()=>({action:'ignored'}),clientFactory,clock=()=>Date.now()}){
    if(!db?.prepare)throw new TypeError('db required');
    if(!Buffer.isBuffer(masterKey)||masterKey.length!==32)throw new TypeError('masterKey must be 32 bytes');
    if(!Buffer.isBuffer(payloadKey)||payloadKey.length!==32)throw new TypeError('payloadKey must be 32 bytes');
    Object.assign(this,{db,masterKey,payloadKey,ingress,firstReply,userRepository,onMessage,clock});
    this.clientFactory=clientFactory||((account)=>new ILinkMessageClient({baseUrl:account.baseUrl,token:account.botToken}));
  }
  activeAccounts(){
    const rows=this.db.prepare(`SELECT account_id AS accountId,owner_user_id AS ownerUserId,token_ciphertext AS tokenCiphertext FROM weixin_accounts WHERE singleton_key='shared' AND status='active'`).all();if(rows.length>1)throw Object.assign(new Error('MULTIPLE_SHARED_BOTS_FORBIDDEN'),{code:'MULTIPLE_SHARED_BOTS_FORBIDDEN'});return rows;
  }
  account(row){
    const x=decryptBotAccount({masterKey:this.masterKey,userId:row.ownerUserId,accountId:row.accountId,record:row.tokenCiphertext});
    return{accountId:row.accountId,ownerUserId:row.ownerUserId,baseUrl:x.baseUrl,botToken:x.botToken};
  }
  async pollAccount(row){
    const account=this.account(row),current=this.ingress.cursor(account.accountId),client=this.clientFactory(account);
    try{
      const update=await client.getUpdates(current.cursor);
      const messages=extractMessages(update),next=extractCursor(update,current.cursor);
      const userByMessage=new Map();for(const message of messages){const senderId=String(message?.from_user_id||'').trim();let userId=account.ownerUserId;if(senderId&&this.userRepository){const principal={channel:'weixin',botAccountId:account.accountId,senderId};userId=(this.userRepository.resolveByPrincipal(principal)||this.userRepository.ensurePending({principal})).userId;}userByMessage.set(message,userId);}const persisted=this.ingress.persistBatchBeforeCursor({accountId:account.accountId,userId:account.ownerUserId,resolveUserId:(message)=>userByMessage.get(message)||account.ownerUserId,cursorBefore:current.cursor,cursorAfter:next,messages,encrypt:({scope,value})=>require('./payload-crypto').encryptJson({key:this.payloadKey,scope,value})});
      return{accountId:account.accountId,status:'ok',received:messages.length,inserted:persisted.inserted,cursor:persisted.cursor};
    }catch(error){
      const code=error?.code||'WEIXIN_POLL_FAILED';
      if(['ILINK_HTTP_401','ILINK_HTTP_403','ILINK_PROVIDER_REJECTED'].includes(code)){
        this.db.prepare(`UPDATE weixin_accounts SET status='reauth_required',updated_at=? WHERE account_id=?`).run(this.clock(),account.accountId);
      }
      return{accountId:account.accountId,status:'failed',code};
    }
  }
  async processOne(){
    const row=this.ingress.claimNext();if(!row)return{status:'idle'};
    try{
      const message=decryptJson({key:this.payloadKey,scope:`inbox:${row.accountId}:${row.providerMessageId}`,record:row.payloadCiphertext});
      const principal={channel:'weixin',botAccountId:row.accountId,senderId:String(message.from_user_id||'')};
      let result=this.firstReply?.handle({accountId:row.accountId,message,principal});
      if(!result||result.action==='continue_runtime')result=await this.onMessage({userId:row.userId,accountId:row.accountId,message,principal});
      this.ingress.finish(row.inboxId,{ok:true});return{status:'processed',inboxId:row.inboxId,result};
    }catch(error){this.ingress.finish(row.inboxId,{ok:false,errorCode:error?.code||'MESSAGE_PROCESS_FAILED'});return{status:'failed',inboxId:row.inboxId,code:error?.code||'MESSAGE_PROCESS_FAILED'};}
  }
  async tick(){
    const poll=[];for(const row of this.activeAccounts())poll.push(await this.pollAccount(row));
    const processed=[];for(let i=0;i<100;i+=1){const result=await this.processOne();if(result.status==='idle')break;processed.push(result);}
    return{poll,processed};
  }
}
module.exports={WeixinAccountSupervisor,extractMessages,extractCursor};
