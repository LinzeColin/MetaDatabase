'use strict';
const crypto = require('node:crypto');

function deepSeekUserId(userId, secret) {
  if (typeof userId !== 'string' || userId.length < 3) throw new TypeError('userId required');
  if (!Buffer.isBuffer(secret) || secret.length < 32) throw new TypeError('secret must be at least 32 bytes');
  return `cb_${crypto.createHmac('sha256', secret).update('deepseek-user\0').update(userId).digest('base64url').slice(0, 48)}`;
}

module.exports = { deepSeekUserId };
