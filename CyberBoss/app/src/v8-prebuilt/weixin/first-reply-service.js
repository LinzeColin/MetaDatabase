'use strict';
function normalizeText(message){const items=Array.isArray(message?.item_list)?message.item_list:[];return items.map(x=>x?.text_item?.text||x?.voice_item?.text||'').join('\n').trim();}
class FirstReplyService{
 constructor({registrationService,replyOutbox,encrypt,routeBinder,clock=()=>Date.now()}){Object.assign(this,{registrationService,replyOutbox,encrypt,routeBinder,clock});}
 stage({userId,accountId,message,text,suffix}){const contextToken=String(message.context_token||'');const toUserId=String(message.from_user_id||'');const route=this.routeBinder({userId,accountId,toUserId,contextToken});const body={toUserId,contextToken,text};const idempotencyKey=`${suffix}:${accountId}:${message.message_id||message.msg_id||toUserId}`;this.replyOutbox.stage({userId,accountId,destinationHash:route.destinationHash,idempotencyKey,bodyCiphertext:this.encrypt({scope:`outbox:${accountId}:${idempotencyKey}`,value:body})});return{action:`${suffix}_queued`,userId,modelCalls:0};}
 handle({accountId,message,principal}){const text=normalizeText(message);if(text!=='开始')return{action:'continue_runtime',modelCalls:0};const reg=this.registrationService.activateFromStart({principal});const user=reg.user;if(reg.action==='capacity_full'){return this.stage({userId:user.userId,accountId,message,text:'CyberBoss 当前只开放 5 个普通用户名额，名额已满。',suffix:'capacity-full'});}return this.stage({userId:user.userId,accountId,message,text:'欢迎使用 CyberBoss。你的账户已开通，直接告诉我现在要做什么；发送“帮助”可以查看最简单的用法。',suffix:'first-reply'});}
}
module.exports={FirstReplyService,normalizeText};
