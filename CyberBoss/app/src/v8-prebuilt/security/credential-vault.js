'use strict';
const crypto = require('node:crypto');

function requireKey(value, label) {
  if (!Buffer.isBuffer(value) || value.length !== 32) throw new TypeError(`${label} must be 32 bytes`);
  return value;
}

function deriveWrappingKey(masterKey, userId, keyVersion) {
  requireKey(masterKey, 'masterKey');
  return Buffer.from(crypto.hkdfSync(
    'sha256',
    masterKey,
    Buffer.from(`cyberboss-user-key-wrap:v${keyVersion}`),
    Buffer.from(String(userId)),
    32,
  ));
}

function createWrappedUserKey({ masterKey, userId, keyVersion = 1, randomBytes = crypto.randomBytes }) {
  const userKey = randomBytes(32);
  requireKey(userKey, 'userKey');
  const wrappingKey = deriveWrappingKey(masterKey, userId, keyVersion);
  const iv = randomBytes(12);
  const aad = Buffer.from(`CyberBoss:user-key:${userId}:${keyVersion}`);
  const cipher = crypto.createCipheriv('aes-256-gcm', wrappingKey, iv);
  cipher.setAAD(aad);
  const ciphertext = Buffer.concat([cipher.update(userKey), cipher.final()]);
  return {
    userKey,
    envelope: {
      algorithm: 'AES-256-GCM',
      keyVersion,
      iv: iv.toString('base64url'),
      tag: cipher.getAuthTag().toString('base64url'),
      ciphertext: ciphertext.toString('base64url'),
      aad: aad.toString('base64url'),
    },
  };
}

function unwrapUserKey({ masterKey, userId, envelope }) {
  const expectedAad = Buffer.from(`CyberBoss:user-key:${userId}:${envelope.keyVersion}`);
  const storedAad = Buffer.from(envelope.aad, 'base64url');
  if (storedAad.length !== expectedAad.length || !crypto.timingSafeEqual(storedAad, expectedAad)) {
    throw Object.assign(new Error('USER_KEY_SCOPE_MISMATCH'), { code: 'USER_KEY_SCOPE_MISMATCH' });
  }
  const wrappingKey = deriveWrappingKey(masterKey, userId, envelope.keyVersion);
  const decipher = crypto.createDecipheriv('aes-256-gcm', wrappingKey, Buffer.from(envelope.iv, 'base64url'));
  decipher.setAAD(storedAad);
  decipher.setAuthTag(Buffer.from(envelope.tag, 'base64url'));
  const userKey = Buffer.concat([
    decipher.update(Buffer.from(envelope.ciphertext, 'base64url')),
    decipher.final(),
  ]);
  return requireKey(userKey, 'userKey');
}

function deriveProviderKey(userKey, userId, providerId, keyVersion) {
  requireKey(userKey, 'userKey');
  return Buffer.from(crypto.hkdfSync(
    'sha256',
    userKey,
    Buffer.from(`cyberboss-provider-key:v${keyVersion}`),
    Buffer.from(`${userId}\0${providerId}`),
    32,
  ));
}

function encryptCredential({ userKey, userId, providerId, plaintext, keyVersion = 1, randomBytes = crypto.randomBytes }) {
  if (typeof plaintext !== 'string' || plaintext.length < 8) throw new TypeError('credential is too short');
  const key = deriveProviderKey(userKey, userId, providerId, keyVersion);
  const iv = randomBytes(12);
  const aad = Buffer.from(`CyberBoss:credential:${userId}:${providerId}:${keyVersion}`);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  cipher.setAAD(aad);
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  return {
    algorithm: 'AES-256-GCM',
    keyVersion,
    iv: iv.toString('base64url'),
    tag: cipher.getAuthTag().toString('base64url'),
    ciphertext: ciphertext.toString('base64url'),
    aad: aad.toString('base64url'),
    last4: plaintext.slice(-4),
  };
}

function decryptCredential({ userKey, userId, providerId, record }) {
  const expectedAad = Buffer.from(`CyberBoss:credential:${userId}:${providerId}:${record.keyVersion}`);
  const storedAad = Buffer.from(record.aad, 'base64url');
  if (storedAad.length !== expectedAad.length || !crypto.timingSafeEqual(storedAad, expectedAad)) {
    throw Object.assign(new Error('VAULT_SCOPE_MISMATCH'), { code: 'VAULT_SCOPE_MISMATCH' });
  }
  const key = deriveProviderKey(userKey, userId, providerId, record.keyVersion);
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(record.iv, 'base64url'));
  decipher.setAAD(storedAad);
  decipher.setAuthTag(Buffer.from(record.tag, 'base64url'));
  return Buffer.concat([
    decipher.update(Buffer.from(record.ciphertext, 'base64url')),
    decipher.final(),
  ]).toString('utf8');
}

module.exports = {
  createWrappedUserKey,
  unwrapUserKey,
  deriveProviderKey,
  encryptCredential,
  decryptCredential,
};
