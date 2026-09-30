// 「它真的在跑吗」的只读判定。网页的 /api/selfhost/status、/healthz?strict=1 与每日任务收尾都用这一份。
// 只读库，不写任何东西；不联网。
import { existsSync, readFileSync } from 'node:fs';

export const FRESH_LIMIT_HOURS = Number(process.env.ADP_FRESH_LIMIT_HOURS || 30);
// 判定口径（写进 dev-notes，改这里必须同步改那里）：
//   · 「已完成的运行」= cn_run_log 里 result 为 正常 / 降级 / 弃权 的行（与 /api/runhealth、看门狗同一口径）；
//   · 新鲜 = 最新一条已完成运行的完成时刻距现在 ≤ 30 小时，且那次运行入库的 arXiv 论文数 > 0。
//     每日任务 20:30 UTC 开跑，含最多两次重试的退避窗口约 1 小时内收尾，次日同一时刻也才 24 小时出头，30 小时留了余量。
const COMPLETED = "('正常','降级','弃权')";

function parseJson(s, fallback) { try { return JSON.parse(s); } catch { return fallback; } }

async function metaJson(db, key) {
  const r = await db.prepare('SELECT value FROM cn_meta WHERE key=?').bind(key).first();
  return r ? parseJson(r.value, null) : null;
}

export async function statusReport(db, { commit = 'unknown', now = Date.now(), failuresFile = null } = {}) {
  const count = async (t) => (await db.prepare(`SELECT COUNT(*) n FROM ${t}`).first()).n;
  const run = await db.prepare(
    `SELECT run_id, as_of_date, result, counts_json, at FROM cn_run_log WHERE result IN ${COMPLETED} ORDER BY at DESC LIMIT 1`).first();
  let latest = null, ageHours = null, fresh = false, reason = 'no_completed_run';
  if (run) {
    const c = parseJson(run.counts_json || '{}', {});
    latest = {
      run_id: run.run_id, as_of_date: run.as_of_date, result: run.result, at: run.at,
      arxiv: c.arxiv || 0, biorxiv: c.biorxiv || 0, feeds: c.feeds || 0, candidates: c.candidates || 0,
      degraded: c.degraded || [],
    };
    ageHours = Math.round(((now - Date.parse(run.at)) / 36e5) * 10) / 10;
    if (!(ageHours <= FRESH_LIMIT_HOURS)) reason = `stale:${ageHours}h>${FRESH_LIMIT_HOURS}h`;
    else if (!(latest.arxiv > 0)) reason = 'arxiv_zero';
    else { fresh = true; reason = 'ok'; }
  }
  let lastFailure = null;
  if (failuresFile && existsSync(failuresFile)) {
    try { const lines = readFileSync(failuresFile, 'utf8').trim().split('\n'); lastFailure = lines[lines.length - 1] || null; } catch { /* 读不到不影响判定 */ }
  }
  return {
    service: 'adp', runtime: 'selfhost', commit,
    now: new Date(now).toISOString(),
    db: { items: await count('cn_items'), selections: await count('cn_selections'), reviews: await count('cn_reviews'), events: await count('cn_events') },
    latest_completed_run: latest,
    data_age_hours: ageHours,
    freshness_limit_hours: FRESH_LIMIT_HOURS,
    fresh, fresh_reason: reason,
    last_daily_job: await metaJson(db, 'selfhost_job_daily'),
    last_backfill_job: await metaJson(db, 'selfhost_job_backfill'),
    last_failure: lastFailure,
  };
}
