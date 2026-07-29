'use strict';
const crypto=require('node:crypto');
function canonical(value){if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));return value;}
function stableHash(value){return crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');}
function normalizeConversation({source,sourceConversationId,title,messages,compatibility='stable'}){const clean=(messages||[]).map((m,i)=>({role:['user','assistant','system'].includes(m.role)?m.role:'unknown',text:String(m.text||'').trim(),createdAt:m.createdAt||null,sourceMessageId:m.sourceMessageId||`${sourceConversationId||'conv'}:${i}`})).filter(m=>m.text);const out={source,sourceConversationId:String(sourceConversationId||stableHash(clean).slice(0,20)),title:String(title||'未命名对话'),compatibility,messages:clean};return{...out,sourceHash:stableHash(out)};}
module.exports={canonical,stableHash,normalizeConversation};
