// D1 兼容层与 worker 加载（覆盖层）的行为测试。
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { openDatabase } from '../app/d1_sqlite.mjs';
import { applyOverlay, OVERLAY, workerPath, schemaPath, loadWorker } from '../app/load_worker.mjs';

const mem = () => openDatabase(':memory:', schemaPath());

test('schema_cloud.sql 可重复应用（幂等），表齐全', async () => {
  const db = mem();
  db._h.exec(readFileSync(schemaPath(), 'utf8'));
  const names = (await db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cn_%'").all()).results.map((r) => r.name).sort();
  assert.deepEqual(names, ['cn_artifacts', 'cn_events', 'cn_items', 'cn_lessons', 'cn_meta', 'cn_reviews', 'cn_run_log', 'cn_selections', 'cn_sources']);
});

test('整数按 INTEGER 绑定（LIMIT/比较不会变成 REAL）；布尔与 null 对齐 D1；undefined 报错而非静默成 NULL', async () => {
  const db = mem();
  assert.deepEqual(await db.prepare('SELECT typeof(?) t').bind(5).first(), { t: 'integer' });
  assert.deepEqual(await db.prepare('SELECT typeof(?) t').bind(5.5).first(), { t: 'real' });
  assert.deepEqual(await db.prepare('SELECT typeof(?) t').bind(null).first(), { t: 'null' });
  assert.deepEqual(await db.prepare('SELECT ? v').bind(true).first(), { v: 1 });
  assert.throws(() => db.prepare('SELECT ?').bind(undefined), /D1_TYPE_ERROR/);
  assert.throws(() => db.prepare('SELECT ?').bind(NaN), /D1_TYPE_ERROR/);
  await db.prepare('INSERT INTO cn_meta (key,value) VALUES (?,?)').bind('a', '1').run();
  await db.prepare('INSERT INTO cn_meta (key,value) VALUES (?,?)').bind('b', '2').run();
  assert.equal((await db.prepare('SELECT * FROM cn_meta ORDER BY key LIMIT ?').bind(1).all()).results.length, 1);
});

test('带编号占位符 ?1 ?2（worker 的关注/元数据查询在用）与 ON CONFLICT 累加', async () => {
  const db = mem();
  await db.prepare('INSERT INTO cn_meta (key,value) VALUES (?1,?2)').bind('k', '7').run();
  assert.deepEqual(await db.prepare('SELECT value FROM cn_meta WHERE key=?1 AND value<>?2').bind('k', 'x').first(), { value: '7' });
  await db.prepare('INSERT INTO cn_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+?').bind('k', '3', 3).run();
  assert.equal((await db.prepare('SELECT value FROM cn_meta WHERE key=?').bind('k').first()).value, '10');
});

test('first() 无行为 null；run() 带 changes / last_row_id；all() 带 results', async () => {
  const db = mem();
  assert.equal(await db.prepare('SELECT * FROM cn_meta WHERE key=?').bind('nope').first(), null);
  const r = await db.prepare('INSERT INTO cn_events (item_id,kind,grade,at,dedup_key) VALUES (?,?,?,?,?)').bind('i', 'grade', 3, 't', 'k1').run();
  assert.equal(r.success, true); assert.equal(r.meta.changes, 1); assert.equal(r.meta.last_row_id, 1);
  const r2 = await db.prepare('INSERT INTO cn_events (item_id,kind,grade,at,dedup_key) VALUES (?,?,?,?,?)').bind('i', 'grade', 3, 't', 'k2').run();
  assert.equal(r2.meta.last_row_id, 2);
  assert.equal((await db.prepare('SELECT * FROM cn_events').all()).results.length, 2);
});

test('batch 是一个事务：中途失败整批回滚，不留半截数据', async () => {
  const db = mem();
  const ins = (k) => db.prepare('INSERT INTO cn_meta (key,value) VALUES (?,?)').bind(k, 'v');
  await assert.rejects(db.batch([ins('a'), ins('b'), ins('a')]), /UNIQUE/);
  assert.equal((await db.prepare('SELECT COUNT(*) n FROM cn_meta').first()).n, 0);
  const out = await db.batch([ins('a'), db.prepare('SELECT COUNT(*) n FROM cn_meta')]);
  assert.equal(out[1].results[0].n, 1);
  assert.equal((await db.prepare('SELECT COUNT(*) n FROM cn_meta').first()).n, 1);
});

test('唯一索引（dedup_key 部分索引）生效：同日重复评分在库层也挡得住', async () => {
  const db = mem();
  const ev = () => db.prepare('INSERT INTO cn_events (item_id,kind,grade,at,dedup_key) VALUES (?,?,?,?,?)').bind('i', 'grade', 3, 't', 'same');
  await ev().run();
  await assert.rejects(ev().run(), /UNIQUE/);
});

test('覆盖层：每条替换在源码里恰好出现一次，替换后不再有三处 Cloudflare 自述', () => {
  const src = readFileSync(workerPath(), 'utf8');
  for (const o of OVERLAY) assert.equal(src.split(o.from).length - 1, 1, o.name);
  const out = applyOverlay(src);
  for (const o of OVERLAY) { assert.ok(!out.includes(o.from), o.name); assert.ok(out.includes(o.to), o.name); }
  const code = out.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n');   // 文件头注释是历史说明，不会渲染到页面
  assert.ok(!/整套系统(跑在|运行在)\s*Cloudflare/.test(code));
});

test('覆盖层 fail-closed：源码里锚点找不到 / 出现多次时抛错，不会悄悄少替换', () => {
  assert.throws(() => applyOverlay('没有任何锚点'), /found 0/);
  const dup = OVERLAY[0].from + OVERLAY[0].from;
  assert.throws(() => applyOverlay(dup, [OVERLAY[0]]), /found 2/);
});

test('worker_cloud.js 原文件未被改动：加载器只在内存里替换', async () => {
  const before = readFileSync(workerPath(), 'utf8');
  await loadWorker();
  assert.equal(readFileSync(workerPath(), 'utf8'), before);
  assert.ok(before.includes('整套系统运行在 Cloudflare'), '仓库里的 Cloudflare 版源码保持原样，待主线在切换稳定后统一清理');
});

test('新运行路径的源码不引用 Cloudflare 服务（wrangler / D1 绑定 / R2 / workers.dev / api.cloudflare.com）', () => {
  const files = ['d1_sqlite.mjs', 'load_worker.mjs', 'server.mjs', 'run_daily.mjs', 'status.mjs'];
  for (const f of files) {
    const s = readFileSync(new URL(`../app/${f}`, import.meta.url), 'utf8')
      .split('\n').filter((l) => !/^\s*(\/\/|\*)/.test(l)).join('\n');   // 注释里解释「不用什么」不算调用
    assert.ok(!/wrangler|workers\.dev|api\.cloudflare\.com|env\.RAW|r2\.cloudflarestorage|CLOUDFLARE_API/i.test(s.replace(/'整套系统[^']*Cloudflare[^']*'/g, '')), f);
  }
});
