'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {
  createWrappedUserKey,
  unwrapUserKey,
  encryptCredential,
  decryptCredential,
} = require('../../src/v8-prebuilt/security/credential-vault');

test('wrapped user key isolates user and enables credential round-trip', () => {
  const master = Buffer.alloc(32, 9);
  const userId = 'usr_abcdefghijklmnopqrstuv';
  const { userKey, envelope } = createWrappedUserKey({ masterKey: master, userId });
  const recoveredUserKey = unwrapUserKey({ masterKey: master, userId, envelope });
  assert.deepEqual(recoveredUserKey, userKey);
  const secret = 'synthetic-secret-value-1234';
  const record = encryptCredential({ userKey: recoveredUserKey, userId, providerId: 'weixin-ilink', plaintext: secret });
  assert.equal(decryptCredential({ userKey: recoveredUserKey, userId, providerId: 'weixin-ilink', record }), secret);
  assert.equal(JSON.stringify({ envelope, record }).includes(secret), false);
  assert.equal(Object.hasOwn(record, 'plaintextHash'), false);
});

test('wrapped user key and provider credential are scope bound', () => {
  const master = Buffer.alloc(32, 4);
  const userId = 'usr_abcdefghijklmnopqrstuv';
  const { userKey, envelope } = createWrappedUserKey({ masterKey: master, userId });
  assert.throws(() => unwrapUserKey({ masterKey: master, userId: 'usr_otherabcdefghijklmnop', envelope }), /USER_KEY_SCOPE_MISMATCH/);
  const record = encryptCredential({ userKey, userId, providerId: 'weixin-ilink', plaintext: 'synthetic-secret-value-1234' });
  assert.throws(() => decryptCredential({ userKey, userId, providerId: 'user-export-object', record }), /VAULT_SCOPE_MISMATCH/);
});

test('crypto-shred contract requires the wrapped user key record', () => {
  const master = Buffer.alloc(32, 7);
  const userId = 'usr_abcdefghijklmnopqrstuv';
  const { userKey } = createWrappedUserKey({ masterKey: master, userId });
  const record = encryptCredential({ userKey, userId, providerId: 'weixin-ilink', plaintext: 'synthetic-secret-value-1234' });
  const wrappedKeyRecord = null;
  assert.equal(wrappedKeyRecord, null);
  assert.throws(() => decryptCredential({ userKey: wrappedKeyRecord, userId, providerId: 'weixin-ilink', record }), /userKey must be 32 bytes/);
});
