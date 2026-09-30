#!/usr/bin/env node
// arXiv 抓取「有上限的重试 + 指数退避」验证器。
// 抽取【发货中】worker_cloud.js 里的真实代码（ARXIV-RETRY 标记块 + parseOaiArxiv + fetchArxivAll +
// tag/stripTags/decodeEntities + UA/ARXIV_CAP/ARXIV_PAGES 三个常量）实跑，绝不复刻；
// fetch / sleep 用脚本化的假实现注入 —— 不联网、不真等。
// 并带一条【负控】：把 2026-08-12 版（每页 1 次重试、固定 2s）在同一夹具上跑，
// 必须复现「09-29 那天第 1 页连续两次超时 -> arXiv=0」，证明断言承重。
// 跑法：node arxiv-daily-push/tools/verify_arxiv_retry.mjs   （输出 JSON；退出 0 = 全过）
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const WORKER = path.resolve(HERE, '..', 'deploy', 'cloudflare', 'worker_cloud.js');
const src = fs.readFileSync(WORKER, 'utf8');

function between(startMarker, endMarker, label) {
  const a = src.indexOf(startMarker);
  const b = src.indexOf(endMarker, a + 1);
  if (a < 0 || b < 0 || b <= a) throw new Error(`无法在 worker 中定位 ${label}——锚点变了，改验证器别让它空过`);
  return src.slice(a, b);
}
function line(re, label) {
  const m = src.match(re);
  if (!m) throw new Error(`无法在 worker 中定位 ${label}——锚点变了，改验证器别让它空过`);
  return m[0];
}

// —— 抽取线上真实代码 ——
const helpers = between('function stripTags', '// ───────────────────────── Feed 解析', 'stripTags..tag');
const constants = [
  line(/^const UA = .*;$/m, 'UA'),
  line(/^const ARXIV_CAP = \d+;/m, 'ARXIV_CAP'),
  line(/^const ARXIV_PAGES = \d+;/m, 'ARXIV_PAGES'),
].join('\n');
const oaiParser = between('function parseOaiArxiv', '// 2026-08-12 查 33 天运行日志', 'parseOaiArxiv');
const retryBlock = between('const ARXIV_OAI_BASE', '// ───────────────────────── P12 历史回填', 'ARXIV-RETRY..fetchArxivAll');
const factory = new Function(
  constants + '\n' + helpers + '\n' + oaiParser + '\n' + retryBlock +
  '\nreturn { fetchArxivAll, fetchArxivPage, arxivBackoffMs, ARXIV_FETCH_ATTEMPTS, ARXIV_PAGES, ARXIV_BACKOFF_MAX_MS };'
);
const shipped = factory();

// —— 夹具：最小 OAI-PMH 响应 ——
function oai(ids, token) {
  const recs = ids.map(id => `<record><header><identifier>oai:arXiv.org:${id}</identifier></header><metadata><arXiv>` +
    `<id>${id}</id><created>2026-09-28</created><title>T ${id}</title><abstract>A ${id}</abstract>` +
    `<categories>cs.AI</categories><authors><author><keyname>K${id}</keyname></author></authors></arXiv></metadata></record>`).join('');
  return `<OAI-PMH><ListRecords>${recs}${token ? `<resumptionToken>${token}</resumptionToken>` : ''}</ListRecords></OAI-PMH>`;
}
const timeoutErr = () => Object.assign(new Error('timed out'), { name: 'TimeoutError' });
const ok = (text) => ({ ok: true, status: 200, text: async () => text });
const http = (status) => ({ ok: false, status, text: async () => '', body: { cancel: async () => {} } });

// 脚本化 fetch：steps 依次是 'timeout' | 'neterr' | number(HTTP 状态) | {ok:text} | {bodyfail:true}
function scripted(steps) {
  const calls = [];
  const sleeps = [];
  let i = 0;
  const deps = {
    fetch: async (u) => {
      calls.push(u);
      const step = steps[Math.min(i++, steps.length - 1)];   // 走完后重复最后一步（模拟「持续故障」）
      if (step === 'timeout') throw timeoutErr();
      if (step === 'neterr') throw Object.assign(new Error('net'), { name: 'TypeError' });
      if (typeof step === 'number') return http(step);
      if (step.bodyfail) return { ok: true, status: 200, text: async () => { throw timeoutErr(); } };
      return ok(step.ok);
    },
    sleep: async (ms) => { sleeps.push(ms); },
  };
  return { deps, calls, sleeps };
}

const results = {};
const failures = [];
function check(name, cond, detail) {
  results[name] = { pass: !!cond, ...(cond ? {} : { detail }) };
  if (!cond) failures.push(name);
}
const A = shipped.ARXIV_FETCH_ATTEMPTS;
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// 1 一次成功：不重试、不睡
{
  const s = scripted([{ ok: oai(['2609.00001', '2609.00002']) }]);
  const items = await shipped.fetchArxivAll('2026-09-29', s.deps);
  check('first_try_success_no_retry', items.length === 2 && s.calls.length === 1 && s.sleeps.length === 0 && items.truncatedReason === null,
    { items: items.length, calls: s.calls.length, sleeps: s.sleeps, reason: items.truncatedReason });
}
// 2 09-29 的形状：第 1 页连续超时两次，第 3 次成功 —— 现在要救回来，退避 2s、4s
{
  const s = scripted(['timeout', 'timeout', { ok: oai(['2609.00003']) }]);
  const items = await shipped.fetchArxivAll('2026-09-29', s.deps);
  check('two_timeouts_then_success_recovers', items.length === 1 && s.calls.length === 3 && eq(s.sleeps, [2000, 4000]) && items.truncatedReason === null,
    { items: items.length, calls: s.calls.length, sleeps: s.sleeps, reason: items.truncatedReason });
}
// 3 持续超时：恰好 A 次尝试就停（有上限），最后一次之后不再睡；带 truncatedReason 返回（看门狗仍能看到 arXiv=0）
{
  const s = scripted(['timeout']);
  const items = await shipped.fetchArxivAll('2026-09-29', s.deps);
  check('persistent_timeout_is_bounded', items.length === 0 && s.calls.length === A && s.sleeps.length === A - 1 && items.truncatedReason === 'arxiv:TimeoutError',
    { items: items.length, calls: s.calls.length, sleeps: s.sleeps, reason: items.truncatedReason });
}
// 4 503 / 429 会重试；持续 503 用尽后原因是 arxiv:http503
{
  const s1 = scripted([503, { ok: oai(['2609.00004']) }]);
  const a = await shipped.fetchArxivAll('2026-09-29', s1.deps);
  const s2 = scripted([503]);
  const b = await shipped.fetchArxivAll('2026-09-29', s2.deps);
  const s3 = scripted([429, 429, { ok: oai(['2609.00005']) }]);
  const c = await shipped.fetchArxivAll('2026-09-29', s3.deps);
  check('http_503_429_retried', a.length === 1 && s1.calls.length === 2 && b.length === 0 && s2.calls.length === A && b.truncatedReason === 'arxiv:http503' && c.length === 1 && s3.calls.length === 3,
    { a: a.length, aCalls: s1.calls.length, b: b.length, bCalls: s2.calls.length, bReason: b.truncatedReason, c: c.length, cCalls: s3.calls.length });
}
// 5 非 429 的 4xx 不重试
{
  const s = scripted([404]);
  const items = await shipped.fetchArxivAll('2026-09-29', s.deps);
  check('http_404_not_retried', items.length === 0 && s.calls.length === 1 && s.sleeps.length === 0 && items.truncatedReason === 'arxiv:http404',
    { calls: s.calls.length, sleeps: s.sleeps, reason: items.truncatedReason });
}
// 6 读 body 中断也重试（以前 resp.text() 抛出来会把整批丢掉）
{
  const s = scripted([{ bodyfail: true }, { ok: oai(['2609.00006']) }]);
  const items = await shipped.fetchArxivAll('2026-09-29', s.deps);
  check('body_read_failure_retried', items.length === 1 && s.calls.length === 2 && eq(s.sleeps, [2000]), { items: items.length, calls: s.calls.length, sleeps: s.sleeps });
}
// 7 第 2 页用尽重试：第 1 页的结果保留（不丢），总子请求 = 1 + A，且不超过 ARXIV_PAGES * A
{
  const s = scripted([{ ok: oai(['2609.00007', '2609.00008'], 'TOKEN123') }, 'timeout']);
  const items = await shipped.fetchArxivAll('2026-09-29', s.deps);
  check('page2_exhausted_keeps_page1', items.length === 2 && s.calls.length === 1 + A && s.calls.length <= shipped.ARXIV_PAGES * A && items.truncatedReason === 'arxiv:TimeoutError',
    { items: items.length, calls: s.calls.length, reason: items.truncatedReason });
  check('page2_uses_resumption_token', s.calls[1].includes('resumptionToken=TOKEN123'), { second: s.calls[1] });
}
// 8 任何故障形状下子请求总数不超过 ARXIV_PAGES * ARXIV_FETCH_ATTEMPTS
{
  const shapes = [['timeout'], ['neterr'], [500], [502], [429], [{ bodyfail: true }],
    [{ ok: oai(['2609.00009'], 'T') }, 503], [{ ok: oai(['2609.00010'], 'T') }, 'neterr']];
  const worst = Math.max(...await Promise.all(shapes.map(async (steps) => {
    const s = scripted(steps);
    await shipped.fetchArxivAll('2026-09-29', s.deps);
    return s.calls.length;
  })));
  check('call_budget_is_capped', worst <= shipped.ARXIV_PAGES * A, { worst, cap: shipped.ARXIV_PAGES * A });
}
// 9 退避是指数、单调、封顶
{
  const seq = [0, 1, 2, 3, 4, 5].map(shipped.arxivBackoffMs);
  const mono = seq.every((v, k) => k === 0 || v >= seq[k - 1]);
  check('backoff_exponential_and_capped', seq[0] === 2000 && seq[1] === 4000 && mono && Math.max(...seq) === shipped.ARXIV_BACKOFF_MAX_MS, { seq });
}

// —— 负控：2026-08-12 版（每页 1 次重试、固定 2s）在「连续两次超时」这一夹具上必然得 0 篇 ——
async function preFixFetchArxivAll(deps) {
  const items = []; let truncated = null;
  const RETRIES = 1;
  let resp = null;
  for (let attempt = 0; attempt <= RETRIES; attempt++) {
    try { resp = await deps.fetch('x'); break; } catch (e) {
      if (attempt === RETRIES) { truncated = 'arxiv:' + (e && e.name || 'FetchError'); break; }
      await deps.sleep(2000);
    }
  }
  // resp 在本夹具下恒为 null（两次都超时）：旧版此时直接放弃，得 0 篇。
  items.truncatedReason = truncated;
  return items;
}
{
  const s = scripted(['timeout', 'timeout', { ok: oai(['2609.00003']) }]);
  const old = await preFixFetchArxivAll(s.deps);
  check('negative_control_prefix_loses_the_day', old.length === 0 && old.truncatedReason === 'arxiv:TimeoutError' && s.calls.length === 2,
    { items: old.length, calls: s.calls.length, reason: old.truncatedReason });
}

const report = { verifier: 'verify_arxiv_retry', attempts_per_page: A, pages: shipped.ARXIV_PAGES, scenarios: results, failed: failures };
process.stdout.write(JSON.stringify(report, null, 2) + '\n');
process.exit(failures.length ? 1 : 0);
