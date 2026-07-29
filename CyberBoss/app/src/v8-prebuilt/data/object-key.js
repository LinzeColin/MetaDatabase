'use strict';
const crypto = require('node:crypto');

function safeSegment(value) {
  const text = String(value || '');
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(text)) throw new TypeError('unsafe object segment');
  return text;
}

function userObjectKey({ userId, category, objectId, version = 1 }) {
  const uid = safeSegment(userId);
  const kind = safeSegment(category);
  const oid = safeSegment(objectId);
  if (!Number.isInteger(version) || version < 1) throw new TypeError('invalid version');
  const digest = crypto.createHash('sha256').update(`${uid}\0${kind}\0${oid}\0${version}`).digest('hex');
  return `cyberboss/users/${uid}/${kind}/${oid}/v${version}-${digest.slice(0, 16)}.bin`;
}

module.exports = { safeSegment, userObjectKey };
