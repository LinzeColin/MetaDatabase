// 网页：用真实流水线（假网络）造出一份库，再起真的 HTTP 服务逐页请求，断言页面必现内容。
// 功能清单 = worker_cloud.js 的路由表（见 dev-notes/2026-09-30-ADP自托管.md「现有功能清单」）。
import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runJob } from '../app/run_daily.mjs';
import { startServer } from '../app/server.mjs';
import { installFetch, tmpDataDir, fastTimers } from './fixtures.mjs';

let dataDir, cleanup, srv, base, itemId, media;

before(async () => {
  const t = tmpDataDir(); dataDir = t.dir; cleanup = t.cleanup;
  const restoreT = fastTimers(), net = installFetch({ arxiv: 'ok' });
  const s = await runJob({ job: 'daily', dataDir, backoff: [], sleep: async () => { }, log: () => { } });
  assert.equal(s.exit_code, 0, JSON.stringify(s));
  net.restore(); restoreT();
  media = mkdtempSync(join(tmpdir(), 'adp-media-'));
  writeFileSync(join(media, 'velorah.mp4'), Buffer.from('0123456789abcdefghij'));
  srv = await startServer({ port: 0, host: '127.0.0.1', dbPath: join(dataDir, 'adp.sqlite'), media, commit: 'deadbeefcafe' });
  base = `http://127.0.0.1:${srv.port}`;
  const st = await (await fetch(`${base}/api/selfhost/status`)).json();
  itemId = (await srv.app.db.prepare('SELECT item_id FROM cn_selections WHERE abstain=0 ORDER BY as_of_date DESC LIMIT 1').first())?.item_id;
  assert.ok(itemId, '流水线应已选出今日条目：' + JSON.stringify(st.latest_completed_run));
});
after(async () => { srv?.server.close(); srv?.app.db.close(); cleanup?.(); if (media) rmSync(media, { recursive: true, force: true }); });

const get = async (p, init) => { const r = await fetch(base + p, { redirect: 'manual', ...init }); return { r, body: await r.text() }; };

const NAV = [['/', '今天'], ['/review', '复习'], ['/radar', '前沿雷达'], ['/watchlist', '关注'], ['/library', '知识库'], ['/system', '系统']];

test('主要页面都 200、带统一外壳（标题、导航、页脚）且不再自称跑在 Cloudflare', async () => {
  for (const p of ['/', '/review', '/radar', '/watchlist', '/library', '/system', '/history', '/search?q=fixture', '/board/board1']) {
    const { r, body } = await get(p);
    assert.equal(r.status, 200, `${p} → ${r.status}`);
    assert.match(r.headers.get('content-type'), /text\/html/);
    assert.match(body, /ADP 前沿学习/, p);
    for (const [h, n] of NAV) assert.ok(body.includes(`<a href="${h}"`) && body.includes(`>${n}</a>`), `${p} 缺导航「${n}」`);
    assert.ok(!/跑在 Cloudflare|运行在 Cloudflare|Workers \+ D1/.test(body), `${p} 仍有 Cloudflare 自述`);
    assert.match(r.headers.get('content-security-policy') || '', /default-src 'self'/);
  }
});

test('今天页：有今日精选条目与讲义入口；页脚写明自托管', async () => {
  const { body } = await get('/');
  assert.match(body, /Fixture paper \d+ on sparse attention/);
  assert.match(body, /整套系统自托管在自己的服务器上/);
  assert.match(body, /往期精选/);
});

test('系统页：近 14 天运行表里有今天这一行，并带 arXiv 入库数（看门狗靠这个格式）', async () => {
  const { body } = await get('/system');
  assert.match(body, /系统与来源/);
  assert.match(body, /整套系统自托管（Node \+ SQLite/);
  assert.match(body, /arXiv \d+ · bio \d+ · 板块流 \d+ · 候选 \d+/);
  assert.match(body, /立即运行一次每日流水线/);
});

test('雷达页按板块列出来源；板块页可翻页；条目详情页可打开', async () => {
  const radar = (await get('/radar')).body;
  assert.match(radar, /arXiv 全站/);
  assert.match(radar, /板块一/);
  const board = await get('/board/board1');
  assert.match(board.body, /Fixture paper/);
  const item = await get(`/item/${encodeURIComponent(itemId)}`);
  assert.equal(item.r.status, 200); assert.match(item.body, /Fixture paper/);
  assert.equal((await get('/item/does-not-exist')).r.status, 404);
  assert.equal((await get('/no-such-page')).r.status, 404);
});

test('搜索页按关键字命中；知识库页可打开', async () => {
  const s = await get('/search?q=sparse+attention');
  assert.equal(s.r.status, 200); assert.match(s.body, /Fixture paper/);
  assert.equal((await get('/library')).r.status, 200);
});

test('写操作：学习入队 → 主动回忆评分进 FSRS → 同日重复评分幂等；关注增删', async () => {
  const study = await fetch(`${base}/api/study/${encodeURIComponent(itemId)}`, { method: 'POST' });
  assert.equal(study.status, 200);
  const g1 = await (await fetch(`${base}/api/grade/${encodeURIComponent(itemId)}/3`, { method: 'POST' })).json();
  assert.equal(g1.duplicate, false); assert.ok(g1.due_at && g1.interval >= 1, JSON.stringify(g1));
  assert.ok(g1.id > 0, 'last_row_id 应被传回');
  const g2 = await (await fetch(`${base}/api/grade/${encodeURIComponent(itemId)}/4`, { method: 'POST' })).json();
  assert.equal(g2.duplicate, true);
  assert.equal((await fetch(`${base}/api/grade/${encodeURIComponent(itemId)}/9`, { method: 'POST' })).status, 422);
  const add = await fetch(`${base}/api/watch/add`, { method: 'POST', redirect: 'manual', body: new URLSearchParams({ facet: 'keyword', value: 'sparse' }) });
  assert.equal(add.status, 303);
  assert.ok(new URL(add.headers.get('location')).pathname === '/watchlist');
  const w = await get('/watchlist'); assert.match(w.body, /sparse/);
});

test('经 Traefik（X-Forwarded-Proto: https）时重定向必须是 https 地址', async () => {
  const add = await fetch(`${base}/api/watch/add`, { method: 'POST', redirect: 'manual', headers: { 'x-forwarded-proto': 'https', 'x-forwarded-host': 'adp.example.test' }, body: new URLSearchParams({ facet: 'keyword', value: 'retrieval' }) });
  assert.equal(add.headers.get('location'), 'https://adp.example.test/watchlist');
});

test('只读端点：build.json、runhealth、backfill、robots 与自托管运维面', async () => {
  assert.match((await (await fetch(`${base}/build.json`)).json()).build_id, /^[0-9a-f]{12}$/);
  const rh = await (await fetch(`${base}/api/runhealth`)).json();
  assert.ok(rh.latest.arxiv > 0 && rh.latest.as_of_date);
  assert.equal((await fetch(`${base}/api/backfill`)).status, 200);
  assert.equal((await fetch(`${base}/robots.txt`)).status, 200);
  const h = await get('/healthz');
  assert.equal(h.r.status, 200); assert.equal(h.body, '{"status":"ok","service":"adp","commit":"deadbeefcafe"}');
  assert.equal((await get('/healthz')).body, h.body, '健康检查响应体必须逐字节稳定（拉取式部署要比对）');
  assert.equal((await get('/version.txt')).body.trim(), 'deadbeefcafe');
  const st = await (await fetch(`${base}/api/selfhost/status`)).json();
  assert.equal(st.runtime, 'selfhost'); assert.equal(st.fresh, true); assert.ok(st.db.items > 0);
  assert.equal(st.last_daily_job.status, 'ok');
  assert.equal((await get('/healthz?strict=1')).r.status, 200);
});

test('数据变旧后 /healthz?strict=1 变 503，普通 /healthz 仍 200', async () => {
  await srv.app.db.prepare("UPDATE cn_run_log SET at='2020-01-01T00:00:00.000Z'").run();
  assert.equal((await get('/healthz?strict=1')).r.status, 503);
  assert.equal((await get('/healthz')).r.status, 200);
  const st = await (await fetch(`${base}/api/selfhost/status`)).json();
  assert.equal(st.fresh, false); assert.match(st.fresh_reason, /^stale:/);
});

test('首屏视频：200 / Range 206 / 越界 416 / 路径穿越 404', async () => {
  const full = await get('/media/velorah.mp4');
  assert.equal(full.r.status, 200); assert.equal(full.r.headers.get('content-type'), 'video/mp4'); assert.equal(full.body, '0123456789abcdefghij');
  const part = await get('/media/velorah.mp4', { headers: { range: 'bytes=2-5' } });
  assert.equal(part.r.status, 206); assert.equal(part.body, '2345'); assert.equal(part.r.headers.get('content-range'), 'bytes 2-5/20');
  assert.equal((await get('/media/velorah.mp4', { headers: { range: 'bytes=99-' } })).r.status, 416);
  assert.equal((await get('/media/..%2Fadp.sqlite')).r.status, 404);
  assert.equal((await get('/media/nothere.mp4')).r.status, 404);
});

test('没有 R2 绑定：/api/raw-selftest 明确 503，而不是假装成功（自托管不带对象存储）', async () => {
  const r = await fetch(`${base}/api/raw-selftest`, { method: 'POST' });
  assert.equal(r.status, 503);
});
