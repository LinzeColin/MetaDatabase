// 给定一个 SQLite 文件，用自托管应用（不开端口）逐页渲染一遍，输出 JSON。被 tests/test_selfhost_migration.py 用来证明：
// 迁移导入后的库，网页服务能直接读、页面能渲染、今日精选能找到。用法：node smoke_render.mjs <db>
import { createApp } from '../app/server.mjs';

const app = await createApp({ dbPath: process.argv[2], media: '/nonexistent', commit: 'smoke' });
const out = { pages: {}, status: null };
const sel = await app.db.prepare('SELECT item_id FROM cn_selections WHERE abstain=0 ORDER BY as_of_date DESC LIMIT 1').first();
const paths = ['/', '/review', '/radar', '/library', '/watchlist', '/system', '/history', '/board/board1', '/healthz'];
if (sel) paths.push('/item/' + encodeURIComponent(sel.item_id));
for (const p of paths) {
  const r = await app.handle(new Request('http://x.test' + p));
  const body = await r.text();
  out.pages[p] = { status: r.status, bytes: body.length, has_title: /ADP 前沿学习/.test(body) || p === '/healthz', body_head: body.slice(0, 0) };
}
const home = await (await app.handle(new Request('http://x.test/'))).text();
out.home_mentions_selected_item = sel ? home.includes('Fixture paper') : null;
out.status = await (await app.handle(new Request('http://x.test/api/selfhost/status'))).json();
console.log(JSON.stringify(out));
app.db.close();
