'use strict';
const {normalizeConversation}=require('./normalize');
function textFromContent(c){if(typeof c==='string')return c;if(Array.isArray(c))return c.map(x=>typeof x==='string'?x:(x?.text||'')).filter(Boolean).join('\n');return c?.text||'';}
function parseClaude(input){const root=typeof input==='string'?JSON.parse(input):input;const rows=Array.isArray(root)?root:(root.conversations||[]);if(!Array.isArray(rows))throw new TypeError('Claude export conversations not found');return rows.map((conv,idx)=>{const list=conv.chat_messages||conv.messages||[];const messages=list.map((m,i)=>({role:m.sender==='assistant'||m.role==='assistant'?'assistant':'user',text:textFromContent(m.content||m.text),createdAt:m.created_at||m.createdAt||null,sourceMessageId:m.uuid||m.id||`${idx}:${i}`}));return normalizeConversation({source:'claude',sourceConversationId:conv.uuid||conv.id||`claude:${idx}`,title:conv.name||conv.title,messages});});}
module.exports={parseClaude};
