// 每日任务：arXiv 失败重试 / 失败留痕 / 不静默成功。跑的是真的 worker_cloud.js + 真 SQLite，只有网络是假的。
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { runJob } from '../app/run_daily.mjs';
import { openDatabase } from '../app/d1_sqlite.mjs';
import { schemaPath } from '../app/load_worker.mjs';
import { statusReport } from '../app/status.mjs';
import { installFetch, tmpDataDir, fastTimers } from './fixtures.mjs';

const silent = () => { const recs = []; const f = (r) => recs.push(r); f.recs = recs; return f; };

async function rows(dir) {
  const db = openDatabase(join(dir, 'adp.sqlite'), schemaPath());
  const { results } = await db.prepare('SELECT run_id, result, counts_json, note FROM cn_run_log ORDER BY at, run_id').all();
  return { db, results };
}

test('arXiv 第一次就成功：只尝试 1 次，退出码 0，留备份与任务记录', async () => {
  const t = tmpDataDir(), restoreT = fastTimers(), net = installFetch({ arxiv: 'ok' });
  try {
    const sleeps = [];
    const s = await runJob({ job: 'daily', dataDir: t.dir, backoff: [600, 1200], sleep: async (x) => sleeps.push(x), log: silent() });
    assert.equal(s.exit_code, 0); assert.equal(s.status, 'ok'); assert.equal(s.attempts, 1);
    assert.deepEqual(sleeps, []);
    assert.ok(s.arxiv > 0, 'arXiv 入库条数应 > 0');
    assert.match(s.backup, /backups\/adp-\d{4}-\d{2}-\d{2}\.sqlite$/); assert.ok(existsSync(s.backup));
    const { db, results } = await rows(t.dir);
    assert.equal(results.length, 1); assert.ok(['正常', '降级'].includes(results[0].result));
    const meta = await db.prepare("SELECT value FROM cn_meta WHERE key='selfhost_job_daily'").first();
    assert.equal(JSON.parse(meta.value).status, 'ok');
    const st = await statusReport(db, { commit: 't' });
    assert.equal(st.fresh, true); assert.equal(st.fresh_reason, 'ok');
    db.close();
  } finally { net.restore(); restoreT(); t.cleanup(); }
});

test('arXiv 前一轮全部 503、下一轮恢复：退避后重试成功，失败那行改标「降级·已重试」且保留', async () => {
  const t = tmpDataDir(), restoreT = fastTimers();
  // 第 1 轮 = worker 内部 3 次尝试（arXiv 调用 1..3）全 503；第 4 次起恢复
  const net = installFetch({ arxiv: (n) => (n <= 3 ? 'fail503' : 'ok') });
  try {
    const sleeps = [];
    const log = silent();
    const s = await runJob({ job: 'daily', dataDir: t.dir, backoff: [600, 1200], sleep: async (x) => sleeps.push(x), log });
    assert.equal(s.status, 'ok'); assert.equal(s.exit_code, 0); assert.equal(s.attempts, 2);
    assert.deepEqual(sleeps, [600], '只在第 1 次失败后退避一次，且用第一档退避');
    assert.equal(net.calls.arxiv, 4, '3 次页内尝试 + 重试轮成功的 1 次');
    const { db, results } = await rows(t.dir);
    assert.equal(results.length, 2, '两次尝试各留一行，不覆盖');
    assert.equal(results[0].result, '降级·已重试');
    assert.match(results[0].note, /arxiv:http503/);
    assert.ok(['正常', '降级'].includes(results[1].result));
    assert.ok(!JSON.parse(results[1].counts_json).degraded.some((d) => d.startsWith('arxiv:')));
    assert.equal(log.recs.filter((r) => r.event === 'attempt').length, 2);
    assert.ok(log.recs.some((r) => r.event === 'retry_wait' && r.wait_seconds === 600));
    db.close();
  } finally { net.restore(); restoreT(); t.cleanup(); }
});

test('arXiv 一直失败：重试次数有上限，退出码 2，失败留在库与 cn_meta 里，数据不算新鲜', async () => {
  const t = tmpDataDir(), restoreT = fastTimers(), net = installFetch({ arxiv: 'timeout' });
  try {
    const sleeps = [];
    const s = await runJob({ job: 'daily', dataDir: t.dir, backoff: [600, 1200], sleep: async (x) => sleeps.push(x) });   // 用默认 logger：写 jobs.jsonl
    assert.equal(s.status, 'arxiv_failed'); assert.equal(s.exit_code, 2);
    assert.equal(s.attempts, 3); assert.deepEqual(sleeps, [600, 1200], '退避逐档拉长，共两次等待');
    assert.ok(net.calls.arxiv <= 3 * 3, `arXiv 调用总量有硬上限（每轮 ≤3 次页内尝试）：${net.calls.arxiv}`);
    assert.ok(s.degraded.some((d) => d.startsWith('arxiv:TimeoutError')), JSON.stringify(s.degraded));
    const { db, results } = await rows(t.dir);
    assert.equal(results.length, 3);
    assert.deepEqual(results.map((r) => r.result).slice(0, 2), ['降级·已重试', '降级·已重试']);
    assert.equal(results[2].result, '降级', '最后一行如实是降级，不会被伪装成正常');
    const meta = JSON.parse((await db.prepare("SELECT value FROM cn_meta WHERE key='selfhost_job_daily'").first()).value);
    assert.equal(meta.status, 'arxiv_failed'); assert.equal(meta.exit_code, 2);
    const st = await statusReport(db, { commit: 't' });
    assert.equal(st.fresh, false); assert.equal(st.fresh_reason, 'arxiv_zero');
    const jl = readFileSync(join(t.dir, 'logs', 'jobs.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
    assert.equal(jl.filter((r) => r.event === 'attempt').length, 3);
    assert.equal(jl.at(-1).event, 'job_done'); assert.equal(jl.at(-1).status, 'arxiv_failed');
    db.close();
  } finally { net.restore(); restoreT(); t.cleanup(); }
});

test('上一次把失败留在了当天：再触发一次会重开那一行重新抓取，而不是被「当日已成功」幂等跳过', async () => {
  const t = tmpDataDir(), restoreT = fastTimers();
  let net = installFetch({ arxiv: 'fail503' });
  try {
    const first = await runJob({ job: 'daily', dataDir: t.dir, backoff: [0], sleep: async () => { }, log: silent() });
    assert.equal(first.exit_code, 2);
    net.restore(); net = installFetch({ arxiv: 'ok' });
    const second = await runJob({ job: 'daily', dataDir: t.dir, backoff: [0], sleep: async () => { }, log: silent() });
    assert.equal(second.exit_code, 0, JSON.stringify(second)); assert.equal(second.attempts, 1);
    assert.ok(net.calls.arxiv >= 1, '必须真的去抓了 arXiv');
    const { db, results } = await rows(t.dir);
    assert.ok(results.some((r) => r.result === '降级·已重试'));
    assert.ok(['正常', '降级'].includes(results.at(-1).result));
    db.close();
  } finally { net.restore(); restoreT(); t.cleanup(); }
});

test('当天已成功：再触发是幂等跳过，不重复抓取，退出码 0', async () => {
  const t = tmpDataDir(), restoreT = fastTimers(), net = installFetch({ arxiv: 'ok' });
  try {
    await runJob({ job: 'daily', dataDir: t.dir, backoff: [0], sleep: async () => { }, log: silent() });
    const before = net.calls.arxiv;
    const again = await runJob({ job: 'daily', dataDir: t.dir, backoff: [0], sleep: async () => { }, log: silent() });
    assert.equal(again.exit_code, 0); assert.equal(again.result, '未运行');
    assert.equal(net.calls.arxiv, before, '第二次不应再碰 arXiv');
  } finally { net.restore(); restoreT(); t.cleanup(); }
});

test('退避配置决定尝试上限：只配一档 = 最多 2 次', async () => {
  const t = tmpDataDir(), restoreT = fastTimers(), net = installFetch({ arxiv: 'fail503' });
  try {
    const s = await runJob({ job: 'daily', dataDir: t.dir, backoff: [5], sleep: async () => { }, log: silent() });
    assert.equal(s.attempts, 2); assert.equal(s.max_attempts, 2); assert.equal(s.exit_code, 2);
  } finally { net.restore(); restoreT(); t.cleanup(); }
});

test('历史回填任务：单次尝试、不因 OAI 繁忙而判任务失败（游标不动，下个时段重试）', async () => {
  const t = tmpDataDir(), restoreT = fastTimers(), net = installFetch({ arxiv: 'fail503' });
  try {
    const s = await runJob({ job: 'backfill', dataDir: t.dir, sleep: async () => { }, log: silent() });
    assert.equal(s.attempts, 1); assert.equal(s.exit_code, 0);
    const db = openDatabase(join(t.dir, 'adp.sqlite'), schemaPath());
    const cur = await db.prepare("SELECT value FROM cn_meta WHERE key='backfill_from'").first();
    assert.equal(cur, null, '503 时游标必须不推进');
    const last = JSON.parse((await db.prepare("SELECT value FROM cn_meta WHERE key='backfill_last'").first()).value);
    assert.ok(last.degraded.includes('backfill:oai503'));
    db.close();
  } finally { net.restore(); restoreT(); t.cleanup(); }
});

test('负控：把重试关掉（退避为空）时，一次 503 整轮就记降级——证明上面的重试真的在起作用', async () => {
  const t = tmpDataDir(), restoreT = fastTimers(), net = installFetch({ arxiv: (n) => (n <= 3 ? 'fail503' : 'ok') });
  try {
    const s = await runJob({ job: 'daily', dataDir: t.dir, backoff: [], sleep: async () => { }, log: silent() });
    assert.equal(s.exit_code, 2); assert.equal(s.attempts, 1);
  } finally { net.restore(); restoreT(); t.cleanup(); }
});
