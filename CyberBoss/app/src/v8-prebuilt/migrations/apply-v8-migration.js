'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

const USER_SCOPED_TABLES = Object.freeze([
  'inbox', 'jobs', 'events', 'outbox', 'sessions', 'reminders', 'diary',
  'timeline_events', 'checkins', 'system_messages', 'deferred_system_replies',
]);

function quoteIdentifier(value) {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) throw new TypeError('unsafe identifier');
  return `"${value}"`;
}

function tableExists(db, table) {
  return Boolean(db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(table));
}

function columns(db, table) {
  return db.prepare(`PRAGMA table_info(${quoteIdentifier(table)})`).all().map((row) => row.name);
}

function planMigration(db, ownerUserId) {
  if (!/^usr_[A-Za-z0-9_-]{20,}$/.test(ownerUserId)) throw new TypeError('invalid owner user id');
  const steps = [];
  for (const table of USER_SCOPED_TABLES) {
    if (!tableExists(db, table)) continue;
    const cols = columns(db, table);
    if (!cols.includes('user_id')) {
      steps.push({ kind: 'add_column', table, sql: `ALTER TABLE ${quoteIdentifier(table)} ADD COLUMN user_id TEXT` });
      steps.push({ kind: 'backfill', table, sql: `UPDATE ${quoteIdentifier(table)} SET user_id = ? WHERE user_id IS NULL` });
      steps.push({ kind: 'index', table, sql: `CREATE INDEX IF NOT EXISTS ${quoteIdentifier(`idx_${table}_user_id`)} ON ${quoteIdentifier(table)}(user_id)` });
    } else {
      steps.push({ kind: 'backfill', table, sql: `UPDATE ${quoteIdentifier(table)} SET user_id = ? WHERE user_id IS NULL OR user_id = ''` });
    }
    const insertTrigger = quoteIdentifier(`trg_${table}_valid_user_insert`);
    const updateTrigger = quoteIdentifier(`trg_${table}_valid_user_update`);
    const quotedTable = quoteIdentifier(table);
    const guard = `NEW.user_id IS NULL OR NEW.user_id = '' OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)`;
    steps.push({ kind: 'guard_insert', table, sql: `CREATE TRIGGER IF NOT EXISTS ${insertTrigger} BEFORE INSERT ON ${quotedTable} WHEN ${guard} BEGIN SELECT RAISE(ABORT, 'valid user_id required'); END` });
    steps.push({ kind: 'guard_update', table, sql: `CREATE TRIGGER IF NOT EXISTS ${updateTrigger} BEFORE UPDATE OF user_id ON ${quotedTable} WHEN ${guard} BEGIN SELECT RAISE(ABORT, 'valid user_id required'); END` });
  }
  return steps;
}

function applyMigration({ dbPath, ownerUserId, sqlPath, apply = false, now = new Date().toISOString() }) {
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;');
  const schema = fs.readFileSync(sqlPath, 'utf8');
  const plan = planMigration(db, ownerUserId);
  const report = { dbPath: path.resolve(dbPath), apply, ownerUserIdHash: require('node:crypto').createHash('sha256').update(ownerUserId).digest('hex').slice(0, 16), steps: plan.map(({ kind, table }) => ({ kind, table })) };
  if (!apply) {
    db.close();
    return report;
  }
  db.exec('BEGIN IMMEDIATE');
  try {
    db.exec(schema);
    db.prepare(`INSERT INTO users(user_id,role,status,consent_version,consented_at,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET role='owner',updated_at=excluded.updated_at`)
      .run(ownerUserId, 'owner', 'active', 'owner-existing-account-v8', now, now, now);
    db.prepare(`INSERT INTO user_settings(user_id,locale,checkin_enabled,updated_at)
      VALUES(?,?,0,?) ON CONFLICT(user_id) DO NOTHING`).run(ownerUserId, 'zh-CN', now);
    for (const step of plan) {
      if (step.kind === 'backfill') db.prepare(step.sql).run(ownerUserId);
      else db.exec(step.sql);
    }
    const foreignKeyErrors = db.prepare('PRAGMA foreign_key_check').all();
    if (foreignKeyErrors.length) throw Object.assign(new Error('FOREIGN_KEY_CHECK_FAILED'), { code: 'FOREIGN_KEY_CHECK_FAILED', count: foreignKeyErrors.length });
    db.exec('COMMIT');
  } catch (error) {
    try { db.exec('ROLLBACK'); } catch {}
    db.close();
    throw error;
  }
  report.integrity = db.prepare('PRAGMA integrity_check').get().integrity_check;
  if (report.integrity !== 'ok') { db.close(); throw Object.assign(new Error('SQLITE_INTEGRITY_CHECK_FAILED'), { code: 'SQLITE_INTEGRITY_CHECK_FAILED' }); }
  db.close();
  return report;
}

if (require.main === module) {
  const args = process.argv.slice(2);
  const dbIndex = args.indexOf('--db');
  const ownerIndex = args.indexOf('--owner-user-id');
  const sqlIndex = args.indexOf('--sql');
  if (dbIndex < 0 || ownerIndex < 0 || sqlIndex < 0 || !args[dbIndex + 1] || !args[ownerIndex + 1] || !args[sqlIndex + 1]) {
    console.error('用法: node apply-v8-migration.js --db <sqlite> --owner-user-id <usr_...> --sql <exact-target-migration.sql> [--apply]');
    process.exit(2);
  }
  const report = applyMigration({
    dbPath: args[dbIndex + 1],
    ownerUserId: args[ownerIndex + 1],
    sqlPath: path.resolve(args[sqlIndex + 1]),
    apply: args.includes('--apply'),
  });
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

module.exports = { USER_SCOPED_TABLES, planMigration, applyMigration };
