'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { SetupTokenService, MemorySetupTokenStore } = require('../../src/v8-prebuilt/security/setup-token-service');
const { SessionTokenService, MemorySessionStore } = require('../../src/v8-prebuilt/security/session-token-service');

test('setup token enforces purpose, one-time use and expiry', () => {
  let now = 1000;
  const service = new SetupTokenService({ store: new MemorySetupTokenStore(), clock: () => now, ttlMs: 100 });
  const first = service.issue({ userId: 'usr_abcdefghijklmnopqrstuv', purpose: 'provider' });
  assert.throws(() => service.consume({ token: first.token, purpose: 'import' }), /LINK_INVALID/);
  assert.equal(service.consume({ token: first.token, purpose: 'provider' }).userId, 'usr_abcdefghijklmnopqrstuv');
  assert.throws(() => service.consume({ token: first.token, purpose: 'provider' }), /LINK_INVALID/);
  const expired = service.issue({ userId: 'usr_abcdefghijklmnopqrstuv', purpose: 'import' });
  now = 2000;
  assert.throws(() => service.consume({ token: expired.token, purpose: 'import' }), /LINK_EXPIRED/);
});

test('session validates CSRF and global revocation', () => {
  const store = new MemorySessionStore();
  const service = new SessionTokenService({ store, clock: () => 1000 });
  const issued = service.issue({ userId: 'usr_abcdefghijklmnopqrstuv' });
  assert.equal(issued.expiresAt, 1000 + 7 * 24 * 60 * 60 * 1000);
  assert.equal(service.verify({ token: issued.token, csrf: issued.csrf }).userId, 'usr_abcdefghijklmnopqrstuv');
  assert.match(issued.cookie, /HttpOnly; Secure; SameSite=Strict/);
  service.revokeAll('usr_abcdefghijklmnopqrstuv');
  assert.throws(() => service.verify({ token: issued.token, csrf: issued.csrf }), /SESSION_INVALID/);
});
