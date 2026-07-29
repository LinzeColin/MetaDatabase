'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'); const os = require('node:os'); const path = require('node:path');
const { loadRuntimeTextSecret } = require('../../src/v8-prebuilt/security/runtime-text-secret');

test('DeepSeek key loads from env or systemd credential without normalizing into code', () => {
  assert.equal(loadRuntimeTextSecret({ env: { DEEPSEEK_API_KEY: 'deepseek-key-123' }, envName: 'DEEPSEEK_API_KEY', credentialName: 'deepseek-api-key' }), 'deepseek-key-123');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cb-secret-'));
  fs.writeFileSync(path.join(dir, 'deepseek-api-key'), 'file-key-456\n');
  assert.equal(loadRuntimeTextSecret({ env: { CREDENTIALS_DIRECTORY: dir }, envName: 'DEEPSEEK_API_KEY', credentialName: 'deepseek-api-key' }), 'file-key-456');
});
