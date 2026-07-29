'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { DatabaseSync } = require('node:sqlite');
const { UserScopedRepository } = require('../../src/v8-prebuilt/users/scoped-repository');

test('user scoped repository rejects cross-user reads and deletes', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(`CREATE TABLE notes(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,body TEXT NOT NULL);
    INSERT INTO notes VALUES('a','usr_Aaaaaaaaaaaaaaaaaaaaa','A only');
    INSERT INTO notes VALUES('b','usr_Bbbbbbbbbbbbbbbbbbbbb','B only');`);
  const repo = new UserScopedRepository({ db, table: 'notes', readableColumns: ['id','user_id','body'] });
  const a = { userId: 'usr_Aaaaaaaaaaaaaaaaaaaaa' };
  const b = { userId: 'usr_Bbbbbbbbbbbbbbbbbbbbb' };
  assert.equal(repo.getById(a, 'a').body, 'A only');
  assert.equal(repo.getById(a, 'b'), null);
  assert.equal(repo.deleteById(a, 'b'), 0);
  assert.equal(repo.getById(b, 'b').body, 'B only');
  assert.throws(() => repo.getById({ userId: 'attacker' }, 'a'), /USER_CONTEXT_REQUIRED/);
  assert.throws(() => new UserScopedRepository({ db, table: 'notes;DROP TABLE notes' }), /trusted SQL identifier/);
  db.close();
});
