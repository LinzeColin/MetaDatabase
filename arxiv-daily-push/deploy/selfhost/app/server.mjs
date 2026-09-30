// ADP 自托管网页服务：把 worker_cloud.js 的 fetch 处理器挂到 Node http 上，数据库是本地 SQLite。
// 只监听容器内端口，对外只经 Traefik；不联网调用任何 Cloudflare 服务。
//
// 在 worker 之前多出来的四个路由（worker 本身没有，属于自托管运维面）：
//   /healthz               进程 + 库能读；响应体固定（不含时间），供拉取式部署做「直连 vs 经 Traefik 逐字节一致」回测
//   /healthz?strict=1      同上，且数据必须新鲜（见 status.mjs），否则 503 —— 给外部监控用，部署器不用它
//   /version.txt           构建时写入的提交号
//   /api/selfhost/status   只读 JSON：最新一次运行、数据新鲜度、最近一次每日任务记录
//   /media/*               首屏视频（Cloudflare 上原本由静态资产层提供），支持 Range
import http from 'node:http';
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { loadWorker, mediaDir, schemaPath } from './load_worker.mjs';
import { openDatabase } from './d1_sqlite.mjs';
import { statusReport } from './status.mjs';

const MAX_BODY = 1024 * 1024;

function readCommit() {
  for (const p of [process.env.ADP_VERSION_FILE, '/app/version.txt'].filter(Boolean)) {
    try { return readFileSync(p, 'utf8').trim() || 'unknown'; } catch { /* 下一个 */ }
  }
  return process.env.SOURCE_COMMIT || 'unknown';
}

const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' };

export async function createApp({ dbPath, media = mediaDir(), commit = readCommit(), failuresFile = null } = {}) {
  const { worker } = await loadWorker();
  const db = openDatabase(dbPath, schemaPath());
  const env = { DB: db };
  const ctx = { waitUntil(p) { Promise.resolve(p).catch(() => { }); }, passThroughOnException() { } };
  let runLock = Promise.resolve();   // 手动「立即运行」串行化：一次只跑一个，避免并发抓取叠在一起

  async function handle(request) {
    const url = new URL(request.url);
    const p = url.pathname;
    if (p === '/healthz' && request.method === 'GET') {
      try { await db.prepare('SELECT 1 AS ok').first(); }
      catch (e) { return new Response(JSON.stringify({ status: 'error', error: String(e.message || e).slice(0, 200) }), { status: 503, headers: JSON_HEADERS }); }
      if (url.searchParams.get('strict') === '1') {
        const s = await statusReport(db, { commit, failuresFile });
        if (!s.fresh) return new Response(JSON.stringify({ status: 'stale', reason: s.fresh_reason, commit }), { status: 503, headers: JSON_HEADERS });
      }
      return new Response(JSON.stringify({ status: 'ok', service: 'adp', commit }), { status: 200, headers: JSON_HEADERS });
    }
    if (p === '/version.txt') return new Response(commit + '\n', { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' } });
    if (p === '/api/selfhost/status') return new Response(JSON.stringify(await statusReport(db, { commit, failuresFile }), null, 1), { headers: JSON_HEADERS });
    if (p.startsWith('/media/')) return serveMedia(request, p.slice('/media/'.length), media);
    if (p === '/api/run' && request.method === 'POST') {
      const prev = runLock;
      let release; runLock = new Promise((r) => { release = r; });
      await prev;
      try { return await worker.fetch(request, env, ctx); } finally { release(); }
    }
    return worker.fetch(request, env, ctx);
  }
  return { handle, db, env };
}

function serveMedia(request, name, dir) {
  if (!/^[A-Za-z0-9._-]+\.mp4$/.test(name)) return new Response('not found', { status: 404 });
  const full = resolve(join(dir, name));
  if (!full.startsWith(resolve(dir) + sep) || !existsSync(full)) return new Response('not found', { status: 404 });
  const size = statSync(full).size;
  const headers = { 'content-type': 'video/mp4', 'accept-ranges': 'bytes', 'cache-control': 'public, max-age=86400' };
  const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.get('range') || '');
  let start = 0, end = size - 1, status = 200;
  if (range && (range[1] || range[2])) {
    if (range[1] === '') { start = Math.max(0, size - Number(range[2])); }
    else { start = Number(range[1]); if (range[2]) end = Math.min(end, Number(range[2])); }
    if (start > end || start >= size) return new Response(null, { status: 416, headers: { 'content-range': `bytes */${size}` } });
    status = 206; headers['content-range'] = `bytes ${start}-${end}/${size}`;
  }
  headers['content-length'] = String(end - start + 1);
  if (request.method === 'HEAD') return new Response(null, { status, headers });
  return new Response(createReadStream(full, { start, end }), { status, headers });
}

async function toRequest(req) {
  const proto = String(req.headers['x-forwarded-proto'] || 'http').split(',')[0].trim();
  const host = String(req.headers['x-forwarded-host'] || req.headers.host || 'localhost').split(',')[0].trim();
  const headers = new Headers();
  for (const [k, v] of Object.entries(req.headers)) if (v !== undefined) headers.set(k, Array.isArray(v) ? v.join(', ') : v);
  let body;
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    const chunks = []; let n = 0;
    for await (const c of req) { n += c.length; if (n > MAX_BODY) throw Object.assign(new Error('body too large'), { status: 413 }); chunks.push(c); }
    body = Buffer.concat(chunks);
  }
  return new Request(`${proto}://${host}${req.url}`, { method: req.method, headers, body });
}

export async function startServer({ port = Number(process.env.PORT || 8080), host = '0.0.0.0', dbPath = process.env.ADP_DB || join(process.env.ADP_DATA_DIR || '/data', 'adp.sqlite'), ...rest } = {}) {
  const dataDir = process.env.ADP_DATA_DIR || '/data';
  const app = await createApp({ dbPath, failuresFile: join(dataDir, 'logs', 'failures.log'), ...rest });
  const server = http.createServer(async (req, res) => {
    try {
      const r = await app.handle(await toRequest(req));
      const h = {}; r.headers.forEach((v, k) => { h[k] = v; });
      res.writeHead(r.status, h);
      if (req.method === 'HEAD' || !r.body) { res.end(); return; }
      res.end(Buffer.from(await r.arrayBuffer()));
    } catch (e) {
      const status = e.status || 500;
      if (!res.headersSent) res.writeHead(status, JSON_HEADERS);
      res.end(JSON.stringify({ error: String(e.message || e).slice(0, 200) }));
    }
  });
  server.keepAliveTimeout = 65000;
  await new Promise((ok) => server.listen(port, host, ok));
  const shutdown = () => { server.close(() => { try { app.db.close(); } catch { /* 已关 */ } process.exit(0); }); setTimeout(() => process.exit(0), 5000).unref(); };
  return { server, app, shutdown, port: server.address().port };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const s = await startServer();
  process.on('SIGTERM', s.shutdown); process.on('SIGINT', s.shutdown);
  console.log(JSON.stringify({ event: 'listening', port: s.port, at: new Date().toISOString() }));
}
