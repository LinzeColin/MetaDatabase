// 与原 Cloudflare 版的「对照」守卫：worker_cloud.js 里【每一个路由 / 每一条 cron / 每一个 env 绑定】都必须在这里有对应，
// 日后 worker 加了新路由、新 cron 或新绑定而自托管没跟上，这里会红（而不是等线上某一天才炸）。
// 对照表正文（已模拟 / 未模拟 / 不需要）写在 PR 描述与 dev-notes 里；这个文件是它的机器校验版。
import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync, readFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runJob } from '../app/run_daily.mjs';
import { startServer } from '../app/server.mjs';
import { makePoliteFetch, installPoliteFetch } from '../app/polite_fetch.mjs';
import { workerPath } from '../app/load_worker.mjs';
import { installFetch, tmpDataDir, fastTimers, oaiXml } from './fixtures.mjs';

const here = (p) => new URL(p, import.meta.url);
const workerSrc = readFileSync(workerPath(), 'utf8');
const fetchBody = workerSrc.slice(workerSrc.indexOf('async fetch(request, env)'), workerSrc.indexOf('async scheduled('));

let dataDir, cleanup, srv, base, media, itemId;
before(async () => {
  const t = tmpDataDir(); dataDir = t.dir; cleanup = t.cleanup;
  const restoreT = fastTimers(), net = installFetch({ arxiv: 'ok' });
  const s = await runJob({ job: 'daily', dataDir, backoff: [], sleep: async () => { }, log: () => { }, arxivMinIntervalMs: 0 });
  assert.equal(s.exit_code, 0, JSON.stringify(s));
  net.restore(); restoreT();
  media = mkdtempSync(join(tmpdir(), 'adp-media-'));
  writeFileSync(join(media, 'velorah.mp4'), Buffer.from('0123456789'));
  srv = await startServer({ port: 0, host: '127.0.0.1', dbPath: join(dataDir, 'adp.sqlite'), media, commit: 'parity', arxivMinIntervalMs: 0 });
  base = `http://127.0.0.1:${srv.port}`;
  itemId = (await srv.app.db.prepare('SELECT item_id FROM cn_selections WHERE abstain=0 ORDER BY as_of_date DESC LIMIT 1').first())?.item_id;
  assert.ok(itemId);
});
after(async () => { srv?.server.close(); srv?.app.db.close(); cleanup?.(); if (media) rmSync(media, { recursive: true, force: true }); });

const enc = encodeURIComponent;
const form = (o) => ({ method: 'POST', redirect: 'manual', body: new URLSearchParams(o) });
// worker fetch 处理器里出现的每个路由字面量 → 一次真实请求与期望状态码。键必须与源码里的字面量完全一致。
const ROUTES = () => ({
  '/favicon.ico': { req: ['/favicon.ico'], status: 200 },
  '/robots.txt': { req: ['/robots.txt'], status: 200 },
  '/build.json': { req: ['/build.json'], status: 200 },
  '/api/backfill': { req: ['/api/backfill'], status: 200 },
  '/api/runhealth': { req: ['/api/runhealth'], status: 200 },
  '/api/a0-canary': { req: ['/api/a0-canary'], status: 200, stubNet: true },
  '/api/watch/add': { req: ['/api/watch/add', form({ facet: 'keyword', value: 'parity' })], status: 303 },
  '/api/watch/ack/': { req: ['/api/watch/ack/' + enc('w:parity'), { method: 'POST', redirect: 'manual' }], status: 404 },   // 不存在的关注 → 404 JSON（存在的见写操作测试）
  '/api/watch/del/': { req: ['/api/watch/del/' + enc('w:parity'), { method: 'POST', redirect: 'manual' }], status: 303 },
  '/api/grade/': { req: [`/api/grade/${enc(itemId)}/3`, { method: 'POST' }], status: 200 },
  '/api/study/': { req: [`/api/study/${enc(itemId)}`, { method: 'POST' }], status: 200 },
  '/api/raw-selftest': { req: ['/api/raw-selftest', { method: 'POST' }], status: 410 },
  '/api/run': { req: ['/api/run', { method: 'POST' }], status: 429 },   // 夹具里刚跑完一轮 → 冷却期内拒绝（放行见下方冷却测试）
  '/api/rum': { req: ['/api/rum', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{"metric":"LCP","value":1200,"theme":"warm","route":"today","device":"desktop","network":"4g"}' }], status: 202 },
  '/': { req: ['/'], status: 200 }, '/today': { req: ['/today'], status: 200 },
  '/review': { req: ['/review'], status: 200 }, '/queue': { req: ['/queue'], status: 200 },
  '/radar': { req: ['/radar'], status: 200 }, '/system': { req: ['/system'], status: 200 },
  '/watchlist': { req: ['/watchlist'], status: 200 }, '/library': { req: ['/library'], status: 200 },
  '/history': { req: ['/history'], status: 200 }, '/search': { req: ['/search?q=fixture'], status: 200 },
  '/board/': { req: ['/board/board1'], status: 200 },
  '/item/': { req: [`/item/${enc(itemId)}`], status: 200 },
});

test('路由对照：worker fetch 处理器里的每个路由字面量都在对照表里，且在自托管上真实请求得到预期状态码', async () => {
  const literals = new Set([
    ...[...fetchBody.matchAll(/\bp === '([^']+)'/g)].map((m) => m[1]),
    ...[...fetchBody.matchAll(/\bp\.startsWith\('([^']+)'\)/g)].map((m) => m[1]),
  ]);
  const table = ROUTES();
  assert.ok(literals.size >= 25, `路由字面量提取失败？只找到 ${literals.size} 个`);
  const missing = [...literals].filter((l) => !(l in table));
  assert.deepEqual(missing, [], `worker 新增了路由，自托管对照表没有跟上：${missing.join(', ')}`);
  for (const [lit, { req, status, stubNet }] of Object.entries(table)) {
    assert.ok(literals.has(lit), `对照表里的 ${lit} 已不在 worker 源码里（过期条目）`);
    const net = stubNet ? installFetch({ arxiv: 'ok' }) : null;
    try {
      const r = await fetch(base + req[0], { redirect: 'manual', ...(req[1] || {}) });
      await r.text();
      assert.equal(r.status, status, `${req[1]?.method || 'GET'} ${req[0]} → ${r.status}`);
    } finally { net?.restore(); }
  }
});

test('手动运行冷却：最近已完成的运行在冷却期内回 429 和人话说明；冷却设为 0 则照常运行', async () => {
  const r = await fetch(base + '/api/run', { method: 'POST' });
  const j = await r.json();
  assert.equal(r.status, 429);
  assert.equal(j.error, 'cooldown');
  assert.match(j.message, /小时内不重复抓取/);
  process.env.ADP_MANUAL_RUN_COOLDOWN_HOURS = '0';
  const net = installFetch({ arxiv: 'ok' });
  try {
    const ok = await fetch(base + '/api/run', { method: 'POST' });
    await ok.text();
    assert.equal(ok.status, 200);
  } finally { net.restore(); delete process.env.ADP_MANUAL_RUN_COOLDOWN_HOURS; }
});

test('写操作回路：关注新增 → 已读 → 删除；评分后 /review 出现该条', async () => {
  const add = await fetch(base + '/api/watch/add', form({ facet: 'keyword', value: 'parity-x' }));
  assert.equal(add.status, 303); assert.match(add.headers.get('location'), /\/watchlist$/);
  const page = await (await fetch(base + '/watchlist')).text();
  const ack = /\/api\/watch\/ack\/([^"'\s)]+)/.exec(page)?.[1];
  assert.ok(ack, '关注页应列出刚加的关注');
  assert.equal((await fetch(`${base}/api/watch/ack/${ack}`, { method: 'POST', redirect: 'manual' })).status, 303);
  assert.equal((await fetch(`${base}/api/watch/del/${ack}`, { method: 'POST', redirect: 'manual' })).status, 303);
  assert.ok(!(await (await fetch(base + '/watchlist')).text()).includes(ack), '删除后关注页不应再有它');
  assert.equal((await fetch(`${base}/api/grade/${enc(itemId)}/3`, { method: 'POST' })).status, 200);
  assert.ok((await (await fetch(base + '/review')).text()).length > 1000);
});

test('POST 的坏输入回 JSON 错误而不是 HTML 页：评分等级越界 422、关注 facet 不合法 422、RUM 坏指标 422、未知 API 404', async () => {
  const cases = [
    [`/api/grade/${enc(itemId)}/9`, { method: 'POST' }, 422],
    ['/api/watch/add', form({ facet: 'nope', value: 'x' }), 422],
    ['/api/rum', { method: 'POST', body: '{"metric":"X","value":1}' }, 422],
    ['/api/nonexistent', { method: 'POST' }, 404],
  ];
  for (const [p, init, status] of cases) {
    const r = await fetch(base + p, { redirect: 'manual', ...init });
    assert.equal(r.status, status, p);
    assert.match(r.headers.get('content-type'), /application\/json/, p);
    await r.text();
  }
});

test('cron 对照：wrangler 的每条 cron 都有 systemd 定时器对应，worker 里的回填 cron 与 run_daily.mjs 一致', () => {
  const wr = readFileSync(here('../../cloudflare/wrangler_cloud.jsonc'), 'utf8');
  const crons = /"crons":\s*\[([^\]]*)\]/.exec(wr)[1].match(/"([^"]+)"/g).map((s) => s.replace(/"/g, ''));
  assert.equal(crons.length, 3);
  const timers = readFileSync(here('../adp-daily.timer'), 'utf8') + readFileSync(here('../adp-backfill.timer'), 'utf8');
  for (const c of crons) {
    const [m, h] = c.split(' ');
    const cal = `OnCalendar=*-*-* ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00 UTC`;
    assert.ok(timers.includes(cal), `cron「${c}」在 systemd 定时器里找不到 ${cal}`);
  }
  const workerCrons = [...workerSrc.slice(workerSrc.indexOf('async scheduled(')).matchAll(/event\.cron === '([^']+)'/g)].map((m) => m[1]);
  assert.deepEqual([...workerCrons].sort(), ['30 2 * * *', '30 8 * * *']);
  for (const c of workerCrons) assert.ok(crons.includes(c), `worker 用到的 cron ${c} 不在 wrangler 里`);
  const rd = readFileSync(here('../app/run_daily.mjs'), 'utf8');
  assert.match(rd, /daily: '30 20 \* \* \*'/); assert.match(rd, /backfill: '30 8 \* \* \*'/);
  assert.ok(crons.includes('30 20 * * *'));
});

test('env 对照：worker 只用到 DB（已由 SQLite 模拟）与 RAW（R2，自托管明确停用）；没有 KV / 变量 / 密钥 / Cache API', () => {
  const names = new Set([...workerSrc.matchAll(/\benv\.([A-Za-z_]+)/g)].map((m) => m[1]));
  assert.deepEqual([...names].sort(), ['DB', 'RAW'], '出现了新的 env 绑定：自托管必须模拟或明确停用');
  assert.ok(!/\bcaches\b|\benv\[|\bKV\b|\.waitUntil\(.*fetch/.test(fetchBody), 'fetch 路径里出现了 Cache API / KV');
  assert.ok(/env && env\.RAW && sourceId/.test(workerSrc), '抓取旁路写 R2 必须由 env.RAW 守卫（自托管没有 RAW）');
  assert.equal(srv.app.env.RAW, undefined);
  assert.deepEqual(Object.keys(srv.app.env), ['DB']);
});

test('邮件不需要：自托管运行面（代码、镜像、systemd、配置）与 worker 里没有任何邮件发送能力', () => {
  const dir = here('../');
  const files = [
    ...readdirSync(new URL('../app/', import.meta.url)).filter((f) => f.endsWith('.mjs')).map((f) => `app/${f}`),
    'Dockerfile', 'adp.env', 'install.sh', 'adp-daily-run.sh', ...readdirSync(dir).filter((f) => /\.(service|timer)$/.test(f)),
  ];
  const bad = /smtp|nodemailer|sendmail|sendgrid|mailgun|ADP_SMTP|resend\.com/i;
  for (const f of files) assert.ok(!bad.test(readFileSync(new URL('../' + f, import.meta.url), 'utf8')), `${f} 含邮件相关字样`);
  assert.ok(!bad.test(workerSrc), 'worker_cloud.js 含邮件发送相关字样（只允许 OpenAlex 的 mailto 礼貌标识）');
});

test('「今天」页：刚由 cron 选出的精选不能被误标成「今天还没选出来」（as_of_date 是 UTC 日，本地日是 UTC+8）', async () => {
  const localDay = (ms) => new Date(ms + 8 * 3600e3).toISOString().slice(0, 10);
  const yesterday = localDay(Date.now() - 864e5);
  // 复现 cron 形态：as_of_date 比「此刻的本地日」早一天，但这次选择是刚刚才产生的
  await srv.app.db.prepare('UPDATE cn_selections SET as_of_date=?, run_at=?').bind(yesterday, new Date().toISOString()).run();
  assert.ok(!(await (await fetch(base + '/')).text()).includes('还没选出来'), '新鲜的精选被误标成过期');
  // 负控：真的是三天前的选择，必须仍然明说「不是今天的」
  await srv.app.db.prepare('UPDATE cn_selections SET run_at=?').bind(new Date(Date.now() - 3 * 864e5).toISOString()).run();
  assert.match(await (await fetch(base + '/')).text(), /今天（\d{4}-\d{2}-\d{2}）还没选出来/);
});

// ───────── arXiv 限速（≥3 秒） ─────────
test('限速：同一 arXiv 主机的请求起点至少间隔 minIntervalMs；并发发起也排队；其它主机不受影响', async () => {
  const GAP = 40; const starts = [];   // 用真实时钟与真实 setTimeout（间隔缩小到 40ms）；3000ms 是同一段代码的默认值
  const inner = async (u) => { starts.push([Date.now(), new URL(u).hostname]); return new Response('ok'); };
  const f = makePoliteFetch(inner, { minIntervalMs: GAP });
  await f('https://export.arxiv.org/a');
  await f('https://oaipmh.arxiv.org/b');                       // 不同子域也算同一个 arXiv
  await Promise.all([f('https://arxiv.org/c'), f('https://export.arxiv.org/d'), f('https://arxiv.org/e')]);   // 并发：仍然各隔一个间隔
  let slept = 0;   // 非 arXiv 主机：不应调用 sleep（用计数判定，不靠墙钟，负载再高也不抖）
  const g = makePoliteFetch(inner, { minIntervalMs: GAP, sleep: async () => { slept++; } });
  await g('https://feeds.example.test/rss'); await g('https://feeds.example.test/rss2'); await g('https://api.biorxiv.org/x');
  assert.equal(slept, 0, '非 arXiv 主机不应被限速');
  const arxiv = starts.filter(([, h]) => /arxiv\.org$/.test(h)).map(([t]) => t);
  assert.equal(arxiv.length, 5);
  for (let i = 1; i < arxiv.length; i++) assert.ok(arxiv[i] - arxiv[i - 1] >= GAP, `第 ${i} 次与上一次只隔 ${arxiv[i] - arxiv[i - 1]}ms`);
});

test('限速：minIntervalMs=0 关闭；installPoliteFetch 幂等（不套两层）并能还原', async () => {
  const orig = globalThis.fetch;
  try {
    assert.equal(installPoliteFetch({ minIntervalMs: 0 })(), undefined); assert.equal(globalThis.fetch, orig);
    const r1 = installPoliteFetch({ minIntervalMs: 10 }); const w = globalThis.fetch;
    assert.notEqual(w, orig); assert.equal(w.isPolite, true);
    const r2 = installPoliteFetch({ minIntervalMs: 10 }); assert.equal(globalThis.fetch, w, '重复安装不能再套一层');
    r2(); assert.equal(globalThis.fetch, w); r1(); assert.equal(globalThis.fetch, orig);
  } finally { globalThis.fetch = orig; }
});

test('限速接入每日任务：真实 runJob 的 arXiv 翻页请求之间有间隔（间隔由 arxivMinIntervalMs 控制）', async () => {
  const t = tmpDataDir(); const stamps = [];
  const orig = globalThis.fetch;
  globalThis.fetch = async (input) => {
    const url = String(input?.url || input);
    if (/arxiv\.org/.test(url)) {
      stamps.push(Date.now());
      return new Response(oaiXml(5, { token: stamps.length === 1 ? 'tok1' : null }), { status: 200 });
    }
    if (/biorxiv/.test(url)) return new Response('{"collection":[]}');
    return new Response('<rss version="2.0"><channel><title>t</title></channel></rss>');
  };
  try {
    const s = await runJob({ job: 'daily', dataDir: t.dir, backoff: [], sleep: async () => { }, log: () => { }, doBackup: false, arxivMinIntervalMs: 50 });
    assert.equal(s.exit_code, 0, JSON.stringify(s));
    assert.ok(stamps.length >= 2, `应至少翻 2 页，实际 ${stamps.length}`);
    assert.ok(stamps[1] - stamps[0] >= 50, `两页之间只隔 ${stamps[1] - stamps[0]}ms`);
    assert.equal(globalThis.fetch.isPolite, undefined, 'runJob 结束后必须还原 fetch');
  } finally { globalThis.fetch = orig; t.cleanup(); }
});
