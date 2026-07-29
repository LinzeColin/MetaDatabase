'use strict';
const crypto = require('node:crypto');

function bindReplyRoute({ routeKey, userId, botAccountId, senderId, contextToken }) {
  for (const [name, value] of Object.entries({userId, botAccountId, senderId, contextToken})) {
    if (typeof value !== 'string' || value.length === 0) throw new TypeError(`${name} required`);
  }
  if (!Buffer.isBuffer(routeKey) || routeKey.length < 32) throw new TypeError('routeKey required');
  const destinationHash = crypto.createHmac('sha256', routeKey)
    .update(botAccountId).update('\0').update(senderId).update('\0').update(contextToken).digest('hex');
  return Object.freeze({ userId, botAccountId, senderId, contextToken, destinationHash });
}
function assertReplyRoute({ routeKey, binding, userId, botAccountId, senderId, contextToken }) {
  const candidate = bindReplyRoute({ routeKey, userId, botAccountId, senderId, contextToken });
  const a = Buffer.from(binding.destinationHash, 'hex');
  const b = Buffer.from(candidate.destinationHash, 'hex');
  if (binding.userId !== userId || a.length !== b.length || !crypto.timingSafeEqual(a,b)) {
    throw Object.assign(new Error('REPLY_ROUTE_MISMATCH'), { code:'REPLY_ROUTE_MISMATCH' });
  }
  return true;
}
module.exports = { bindReplyRoute, assertReplyRoute };
