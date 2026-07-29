'use strict';
const crypto = require('node:crypto');

function assertString(name, value) {
  if (typeof value !== 'string' || value.length === 0) throw new TypeError(`${name} is required`);
}

function derivePrincipalHash({ identityKey, channel = 'weixin', botAccountId, senderId }) {
  if (!Buffer.isBuffer(identityKey) || identityKey.length < 32) throw new TypeError('identityKey must be a Buffer of at least 32 bytes');
  assertString('channel', channel); assertString('botAccountId', botAccountId); assertString('senderId', senderId);
  return crypto.createHmac('sha256', identityKey).update(channel).update('\0').update(botAccountId).update('\0').update(senderId).digest();
}

function deriveUserId(input) {
  const digest = derivePrincipalHash(input);
  return `usr_${digest.toString('base64url').slice(0, 26)}`;
}

function principalHashHex(input) { return derivePrincipalHash(input).toString('hex'); }

module.exports = { deriveUserId, principalHashHex };
