// 每日任务入口（由 systemd timer 经 adp-daily-run.sh 在一次性容器里调用）：
//   node run_daily.mjs daily      抓取 → 选择 → 讲义 → 建卡 → run_log（原 cron 30 20 * * *）
//   node run_daily.mjs backfill   arXiv 历史回填一页（原 cron 30 8 / 30 2）
//
// 在 worker_cloud.js 已有的「每页最多 3 次尝试、退避 2s→4s」之上再加一层任务级重试：
//   arXiv 整体没抓到（degraded 里出现 arxiv:*，含 arxiv:parsed0 / TimeoutError:truncated / httpNNN）或整次运行「失败」，
//   就按 ADP_RETRY_BACKOFF_SECONDS（默认 600,1200）退避后再跑；总尝试次数 = 退避个数 + 1，有上限，不会无限重试。
//   worker 的 runDaily 当天只要有一行「正常/降级/弃权」就幂等跳过，所以重试前要把上一轮那行改标成「降级·已重试」
//   （行保留，可查；/system 页同日多行取最新，/api/runhealth 与看门狗只认正常/降级/弃权）。
//
// 不静默成功：
//   退出码 0 = 已完成且 arXiv 有数据；1 = 运行失败；2 = 重试用尽 arXiv 仍没抓到；3 = 抓取成功但库备份失败。
//   非 0 → systemd 判 unit 失败 → OnFailure 落一行失败记录（见 adp-failure@.service）。
//   每次尝试与最终结论都写 ${ADP_DATA_DIR}/logs/jobs.jsonl 与 cn_meta(selfhost_job_<job>)，/api/selfhost/status 会读出来。
import { appendFileSync, mkdirSync, readdirSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { loadWorker, schemaPath } from './load_worker.mjs';
import { openDatabase } from './d1_sqlite.mjs';

const CRON = { daily: '30 20 * * *', backfill: '30 8 * * *' };
const ATTEMPT_TIMEOUT_MS = Number(process.env.ADP_ATTEMPT_TIMEOUT_SECONDS || 1200) * 1000;
const KEEP_BACKUPS = Number(process.env.ADP_KEEP_BACKUPS || 7);

const utcDay = () => new Date().toISOString().slice(0, 10);
const parseBackoff = (s) => String(s ?? '600,1200').split(',').map((x) => x.trim()).filter(Boolean).map(Number).filter((n) => Number.isFinite(n) && n >= 0);
export const arxivFailed = (counts) => (counts?.degraded || []).some((d) => /^arxiv:/.test(String(d)));

function makeLogger(dataDir) {
  const dir = join(dataDir, 'logs');
  mkdirSync(dir, { recursive: true });
  const file = join(dir, 'jobs.jsonl');
  return (rec) => {
    const line = JSON.stringify({ at: new Date().toISOString(), ...rec });
    console.log(line);
    try { appendFileSync(file, line + '\n'); } catch (e) { console.error('写 jobs.jsonl 失败：' + e.message); }
  };
}

async function setMeta(db, key, obj) {
  await db.prepare('INSERT INTO cn_meta (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').bind(key, JSON.stringify(obj)).run();
}

// 把今天「已完成但 arXiv 抓取失败」的行改标成「降级·已重试」，让 runDaily 不再幂等跳过。返回改了几行。
export async function reopenArxivFailedToday(db, attemptNo) {
  const { results } = await db.prepare("SELECT run_id, counts_json, note FROM cn_run_log WHERE as_of_date=? AND result IN ('正常','降级','弃权')").bind(utcDay()).all();
  let n = 0;
  for (const r of results || []) {
    let c = {}; try { c = JSON.parse(r.counts_json || '{}'); } catch { /* 坏 JSON 当作没有 */ }
    if (!arxivFailed(c)) continue;
    const note = `${r.note ? r.note + '；' : ''}arXiv 抓取失败（${(c.degraded || []).filter((d) => /^arxiv:/.test(d)).join(',')}），自托管任务已重试（第 ${attemptNo} 次尝试之后）`;
    // run_id 只精确到分钟（worker 里 slice(0,15)）：同一分钟内再跑一次会撞主键，「占位」被 DO NOTHING 吞掉、
    // 收尾 UPDATE 反而覆盖掉这一行。所以改标的同时给它换个唯一 run_id，把失败记录固定下来。
    const keepId = `${r.run_id}~r${attemptNo}-${Math.floor(Date.now() / 1000)}`;
    await db.prepare("UPDATE cn_run_log SET result='降级·已重试', note=?, run_id=? WHERE run_id=?").bind(note.slice(0, 500), keepId, r.run_id).run();
    n++;
  }
  return n;
}

function withTimeout(p, ms, what) {
  let t;
  return Promise.race([p, new Promise((_, rej) => { t = setTimeout(() => rej(Object.assign(new Error(`${what} 超过 ${ms / 1000}s`), { name: 'AttemptTimeout' })), ms); })]).finally(() => clearTimeout(t));
}

async function scheduledOnce(worker, env, cron) {
  const pending = [];
  await worker.scheduled({ cron }, env, { waitUntil: (p) => pending.push(Promise.resolve(p)) });
  const settled = await Promise.all(pending);
  return settled[0];
}

export function backupDatabase(db, dataDir, keep = KEEP_BACKUPS) {
  const dir = join(dataDir, 'backups');
  mkdirSync(dir, { recursive: true });
  const target = join(dir, `adp-${utcDay()}.sqlite`);
  if (existsSync(target)) rmSync(target);
  db._h.exec(`VACUUM INTO '${target.replace(/'/g, "''")}'`);
  const all = readdirSync(dir).filter((f) => /^adp-\d{4}-\d{2}-\d{2}\.sqlite$/.test(f)).sort();
  for (const f of all.slice(0, Math.max(0, all.length - keep))) rmSync(join(dir, f));
  return target;
}

export async function runJob({ job = 'daily', dataDir = process.env.ADP_DATA_DIR || '/data', dbPath, backoff = parseBackoff(process.env.ADP_RETRY_BACKOFF_SECONDS), sleep = (s) => new Promise((r) => setTimeout(r, s * 1000)), log, doBackup = true } = {}) {
  if (!CRON[job]) throw new Error(`未知任务 ${job}`);
  log ||= makeLogger(dataDir);
  const { worker } = await loadWorker();
  const db = openDatabase(dbPath || join(dataDir, 'adp.sqlite'), schemaPath());
  const env = { DB: db };
  const maxAttempts = job === 'daily' ? backoff.length + 1 : 1;
  const t0 = Date.now();
  let last = null, status = 'failed', exitCode = 1, attempt = 0;

  for (attempt = 1; attempt <= maxAttempts; attempt++) {
    if (job === 'daily') {
      const reopened = await reopenArxivFailedToday(db, attempt - 1);
      if (reopened) log({ job, event: 'reopened_failed_run', rows: reopened, attempt });
    }
    let res, timedOut = false;
    try { res = await withTimeout(scheduledOnce(worker, env, CRON[job]), ATTEMPT_TIMEOUT_MS, `第 ${attempt} 次尝试`); }
    catch (e) { timedOut = e.name === 'AttemptTimeout'; res = { result: '失败', counts: { degraded: [] }, note: `${e.name}: ${String(e.message || e).slice(0, 200)}` }; }
    last = res || { result: '未知', counts: { degraded: [] } };
    const counts = last.counts || {};
    log({ job, event: 'attempt', attempt, of: maxAttempts, result: last.result, run_id: last.runId, arxiv: counts.arxiv ?? null, degraded: counts.degraded || [], note: last.note || null });

    if (job === 'backfill') {
      // 回填本身永不抛（runBackfill 内部降级）；有 degraded 只记录，不算任务失败——游标不动，下个时段重试同一窗口。
      status = 'ok'; exitCode = 0; break;
    }
    // 超时后那次运行可能还在后台写库：不再叠第二次，直接判失败收尾（进程退出时连同它一起结束）。
    if (timedOut) { status = 'failed'; exitCode = 1; break; }
    if (last.result === '失败') { status = 'failed'; exitCode = 1; }
    else if (arxivFailed(counts)) { status = 'arxiv_failed'; exitCode = 2; }
    else { status = 'ok'; exitCode = 0; break; }
    if (attempt < maxAttempts) {
      const wait = backoff[attempt - 1];
      log({ job, event: 'retry_wait', attempt, wait_seconds: wait, because: status });
      await sleep(wait);
    }
  }

  let backup = null;
  if (job === 'daily' && doBackup && status !== 'failed') {
    try { backup = backupDatabase(db, dataDir); log({ job, event: 'backup_ok', file: backup }); }
    catch (e) { backup = 'failed: ' + String(e.message || e).slice(0, 200); log({ job, event: 'backup_failed', error: backup }); if (exitCode === 0) { status = 'backup_failed'; exitCode = 3; } }
  }
  const counts = last?.counts || {};
  const summary = {
    job, status, exit_code: exitCode, attempts: Math.min(attempt, maxAttempts), max_attempts: maxAttempts,
    result: last?.result ?? null, run_id: last?.runId ?? null, arxiv: counts.arxiv ?? null, degraded: counts.degraded || [],
    note: last?.note ?? null, backup, seconds: Math.round((Date.now() - t0) / 1000),
  };
  await setMeta(db, `selfhost_job_${job}`, { at: new Date().toISOString(), ...summary });
  log({ event: 'job_done', ...summary });
  db.close();
  return summary;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const job = process.argv[2] || 'daily';
  try {
    const s = await runJob({ job });
    process.exit(s.exit_code);
  } catch (e) {
    console.error(JSON.stringify({ event: 'job_crashed', job, error: String(e.stack || e) }));
    process.exit(1);
  }
}
