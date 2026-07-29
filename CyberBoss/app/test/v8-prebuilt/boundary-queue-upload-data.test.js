'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { assertOwnerCapability, requireSameUser } = require('../../src/v8-prebuilt/security/request-boundary');
const { FairUserQueue } = require('../../src/v8-prebuilt/runtime/fair-user-queue');
const { validateArchiveManifest } = require('../../src/v8-prebuilt/imports/upload-policy');
const { stableHash } = require('../../src/v8-prebuilt/imports/normalize');
const { MemoryImportLedger } = require('../../src/v8-prebuilt/imports/import-ledger');
const { userObjectKey } = require('../../src/v8-prebuilt/data/object-key');
const { buildDeletionPlan, validateDeletionReceipts } = require('../../src/v8-prebuilt/privacy/deletion-plan');

test('ordinary user cannot cross scope or trigger owner capabilities', () => {
  const user = { userId: 'usr_A', role: 'user' };
  assert.throws(() => assertOwnerCapability(user, 'codex.turn'), /OWNER_ONLY_CAPABILITY/);
  assert.throws(() => requireSameUser(user, { userId: 'usr_B' }), /USER_SCOPE_VIOLATION/);
  assert.equal(requireSameUser(user, { userId: 'usr_A', value: 1 }).value, 1);
});

test('fair queue keeps one active per user and rotates users', () => {
  const queue = new FairUserQueue({ perUserLimit: 1, totalLimit: 2 });
  queue.enqueue({ id: 'a1', userId: 'A' });
  queue.enqueue({ id: 'a2', userId: 'A' });
  queue.enqueue({ id: 'b1', userId: 'B' });
  const first = queue.claimNext();
  const second = queue.claimNext();
  assert.deepEqual(new Set([first.userId, second.userId]), new Set(['A', 'B']));
  assert.equal(queue.claimNext(), null);
  queue.complete(first);
  assert.equal(queue.claimNext().id, 'a2');
});

test('upload manifest rejects traversal, bombs and executable formats', () => {
  assert.throws(() => validateArchiveManifest({ archiveBytes: 10, files: [{ path: '../x.json', uncompressedBytes: 1 }] }), /ARCHIVE_PATH_FORBIDDEN/);
  assert.throws(() => validateArchiveManifest({ archiveBytes: 10, files: [{ path: 'x.exe', uncompressedBytes: 1 }] }), /ARCHIVE_FILE_TYPE_FORBIDDEN/);
  assert.throws(() => validateArchiveManifest({ archiveBytes: 10, files: [{ path: 'x.json', uncompressedBytes: 2_000_000_000 }] }), /ARCHIVE_FILE_TOO_LARGE/);
  assert.equal(validateArchiveManifest({ archiveBytes: 10, files: [{ path: 'export/conversations.json', uncompressedBytes: 100 }] }).files.length, 1);
});

test('import ledger is user scoped and idempotent', () => {
  const ledger = new MemoryImportLedger();
  const sourceHash = stableHash({ content: 'same' });
  const first = ledger.begin({ userId: 'A', source: 'chatgpt', sourceHash });
  const repeat = ledger.begin({ userId: 'A', source: 'chatgpt', sourceHash });
  const other = ledger.begin({ userId: 'B', source: 'chatgpt', sourceHash });
  assert.equal(repeat.id, first.id);
  assert.equal(repeat.duplicate, true);
  assert.notEqual(other.id, first.id);
});

test('object keys cannot escape user prefix', () => {
  const key = userObjectKey({ userId: 'usr_ABC', category: 'imports', objectId: 'obj_123' });
  assert.match(key, /^cyberboss\/users\/usr_ABC\/imports\/obj_123\//);
  assert.throws(() => userObjectKey({ userId: '../other', category: 'imports', objectId: 'x' }), /unsafe object segment/);
});

test('deletion plan is ordered and requires every receipt', () => {
  const plan = buildDeletionPlan({ userId: 'usr_A', requestId: 'del_1' });
  const receipts = plan.map((step) => ({ id: step.id, userId: step.userId, status: 'succeeded' }));
  assert.equal(validateDeletionReceipts(plan, receipts), true);
  assert.equal(validateDeletionReceipts(plan, receipts.slice(1)), false);
});
