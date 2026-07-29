'use strict';
const crypto=require('node:crypto');
function requireKey(key){if(!Buffer.isBuffer(key)||key.length!==32)throw new TypeError('masterKey must be 32 bytes');return key;}
function encryptBotAccount({masterKey,userId,accountId,botToken,baseUrl,randomBytes=crypto.randomBytes}){
  requireKey(masterKey); if(!userId||!accountId||!botToken)throw new TypeError('account fields required');
  const iv=randomBytes(12); const aad=Buffer.from(`CyberBoss:weixin-account:${userId}:${accountId}`);
  const cipher=crypto.createCipheriv('aes-256-gcm',masterKey,iv); cipher.setAAD(aad);
  const plaintext=JSON.stringify({botToken,baseUrl}); const ciphertext=Buffer.concat([cipher.update(plaintext,'utf8'),cipher.final()]);
  return JSON.stringify({algorithm:'AES-256-GCM',iv:iv.toString('base64url'),tag:cipher.getAuthTag().toString('base64url'),aad:aad.toString('base64url'),ciphertext:ciphertext.toString('base64url')});
}
function decryptBotAccount({masterKey,userId,accountId,record}){
  requireKey(masterKey); const parsed=typeof record==='string'?JSON.parse(record):record;
  const expected=Buffer.from(`CyberBoss:weixin-account:${userId}:${accountId}`); const aad=Buffer.from(parsed.aad,'base64url');
  if(aad.length!==expected.length||!crypto.timingSafeEqual(aad,expected))throw Object.assign(new Error('WEIXIN_ACCOUNT_SCOPE_MISMATCH'),{code:'WEIXIN_ACCOUNT_SCOPE_MISMATCH'});
  const d=crypto.createDecipheriv('aes-256-gcm',masterKey,Buffer.from(parsed.iv,'base64url'));d.setAAD(aad);d.setAuthTag(Buffer.from(parsed.tag,'base64url'));
  return JSON.parse(Buffer.concat([d.update(Buffer.from(parsed.ciphertext,'base64url')),d.final()]).toString('utf8'));
}
module.exports={encryptBotAccount,decryptBotAccount};
