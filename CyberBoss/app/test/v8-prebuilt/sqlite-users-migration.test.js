'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { applyMigration } = require('../../src/v8-prebuilt/migrations/apply-v8-migration');
const { SqliteUserRepository } = require('../../src/v8-prebuilt/users/user-repository');
const { SqliteInviteCodeStore } = require('../../src/v8-prebuilt/users/invite-code-store');
const { RegistrationService } = require('../../src/v8-prebuilt/users/registration-service');

function temp() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cbv8-'));
  return { dir, dbPath: path.join(dir, 'db.sqlite') };
}

test('migration is additive, guards future user scope and keeps reports pseudonymous', () => {
  const t = temp();
  let db = new DatabaseSync(t.dbPath);
  db.exec("CREATE TABLE jobs(id TEXT PRIMARY KEY,status TEXT); INSERT INTO jobs VALUES('j1','queued');");
  db.close();

  const owner = 'usr_ownerabcdefghijklmnopq';
  const schema = path.join(__dirname, '../../migrations/multiuser_foundation.sql.template');
  const dry = applyMigration({ dbPath: t.dbPath, ownerUserId: owner, sqlPath: schema, apply: false });
  assert.ok(dry.steps.some((x) => x.table === 'jobs'));
  assert.equal('ownerUserId' in dry, false);
  assert.match(dry.ownerUserIdHash, /^[a-f0-9]{16}$/);

  const report = applyMigration({ dbPath: t.dbPath, ownerUserId: owner, sqlPath: schema, apply: true, now: '2026-01-01T00:00:00Z' });
  assert.equal(report.integrity, 'ok');
  db = new DatabaseSync(t.dbPath);
  assert.equal(db.prepare("SELECT user_id FROM jobs WHERE id='j1'").get().user_id, owner);
  assert.throws(() => db.prepare('INSERT INTO jobs(id,status) VALUES(?,?)').run('j-null', 'queued'), /valid user_id required/);
  assert.throws(() => db.prepare('INSERT INTO jobs(id,status,user_id) VALUES(?,?,?)').run('j-unknown', 'queued', 'usr_unknownabcdefghijklmn'), /valid user_id required/);
  assert.throws(() => db.prepare('UPDATE jobs SET user_id=NULL WHERE id=?').run('j1'), /valid user_id required/);

  const users = new SqliteUserRepository({ db, identityKey: Buffer.alloc(32, 4), clock: () => '2026-01-01T00:00:00Z' });
  const invites = new SqliteInviteCodeStore({ db, secret: Buffer.alloc(32, 7), clock: () => 1000 });
  invites.create({ code: 'ABCD-EFGH-1234' });
  const reg = new RegistrationService({ userRepository: users, inviteStore: invites, registrationMode: 'invite' });
  const principal = { botAccountId: 'bot', senderId: 'sender' };
  assert.equal(reg.start({ principal }).action, 'request_invite_code');
  const started = reg.start({ principal, inviteCode: 'ABCD-EFGH-1234' });
  assert.equal(started.user.status, 'pending_consent');
  const active = reg.consent({ principal, accepted: true });
  assert.equal(active.user.status, 'active');
  assert.equal(users.resolveByPrincipal({ botAccountId: 'bot', senderId: 'other' }), null);
  db.prepare('INSERT INTO jobs(id,status,user_id) VALUES(?,?,?)').run('j-valid', 'queued', active.user.userId);
  assert.equal(db.prepare('SELECT user_id FROM jobs WHERE id=?').get('j-valid').user_id, active.user.userId);
  db.close();
  fs.rmSync(t.dir, { recursive: true, force: true });
});

test('migration creates crypto-shreddable user key table and allows revoked channel rebinding', () => {
  const t = temp();
  const db = new DatabaseSync(t.dbPath);
  const owner = 'usr_ownerabcdefghijklmnopq';
  const schema = path.join(__dirname, '../../migrations/multiuser_foundation.sql.template');
  db.close();
  applyMigration({ dbPath: t.dbPath, ownerUserId: owner, sqlPath: schema, apply: true, now: '2026-01-01T00:00:00Z' });
  const live = new DatabaseSync(t.dbPath);
  assert.equal(live.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='user_data_keys'").get().name, 'user_data_keys');
  live.prepare('INSERT INTO user_channels(channel,bot_account_ref,principal_hash,user_id,created_at,revoked_at) VALUES(?,?,?,?,?,?)').run('weixin', 'bot-a', 'p1', owner, '2026-01-01', '2026-01-02');
  live.prepare('INSERT INTO user_channels(channel,bot_account_ref,principal_hash,user_id,created_at,revoked_at) VALUES(?,?,?,?,?,NULL)').run('weixin', 'bot-b', 'p2', owner, '2026-01-03');
  assert.equal(live.prepare('SELECT COUNT(*) AS n FROM user_channels WHERE user_id=?').get(owner).n, 2);
  live.close();
  fs.rmSync(t.dir, { recursive: true, force: true });
});

test('sqlite invite codes require keyed hashing and are not stored as reusable plaintext hashes',()=>{
  const t=temp();
  const db=new DatabaseSync(t.dbPath);
  const schema=path.join(__dirname,'../../migrations/multiuser_foundation.sql.template');
  db.exec(fs.readFileSync(schema,'utf8'));
  assert.throws(()=>new SqliteInviteCodeStore({db}),/invite secret/);
  const secret=Buffer.alloc(32,9);
  const store=new SqliteInviteCodeStore({db,secret,clock:()=>1});
  store.create({code:'WXYZ-1234-ABCD'});
  const row=db.prepare('SELECT code_hash FROM invite_codes').get();
  const unkeyed=require('node:crypto').createHash('sha256').update('WXYZ1234ABCD').digest('hex');
  assert.notEqual(row.code_hash,unkeyed);
  assert.equal(row.code_hash.includes('WXYZ'),false);
  db.close();fs.rmSync(t.dir,{recursive:true,force:true});
});
