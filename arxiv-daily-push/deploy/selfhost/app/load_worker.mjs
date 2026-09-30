// 把 deploy/cloudflare/worker_cloud.js 加载成一个普通 ES 模块（export default { fetch, scheduled }）。
//
// 为什么不复制一份：worker_cloud.js 是页面、选择、讲义、FSRS、抓取的唯一实现，且有一批 tools/verify_*.mjs
// 直接从它里面抽代码做验证。自托管与它共用同一份源码，就不会出现「两份实现慢慢分叉」。
//
// 唯一的改动是下面 OVERLAY：页面上三处「整套系统跑在 Cloudflare」的自述在自托管后就是假话，必须改掉。
// 每条替换都要求在源码里【恰好出现一次】——源码将来改了措辞，这里直接抛错（fail closed），
// 而不是悄悄少替换一处，让页面继续谎称跑在 Cloudflare。
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

export const OVERLAY = [
  {
    name: 'meta-description',
    from: '整套系统跑在 Cloudflare。',
    to: '整套系统自托管在自己的服务器上。',
  },
  {
    name: 'footer-receipt',
    from: '整套系统运行在 Cloudflare（抓取·选择·讲义·回忆·排程都在云端）；每日 cron 自动更新，不依赖任何本机。',
    to: '整套系统自托管在自己的服务器上（抓取·选择·讲义·回忆·排程都在服务器）；每日定时任务自动更新，不依赖任何本机。',
  },
  {
    name: 'system-page-intro',
    from: '整套系统跑在 Cloudflare（Workers + D1 + 每日 cron），不依赖任何本机。',
    to: '整套系统自托管（Node + SQLite + systemd 每日定时任务），不依赖任何本机。',
  },
];

function count(haystack, needle) {
  let n = 0;
  for (let i = haystack.indexOf(needle); i !== -1; i = haystack.indexOf(needle, i + needle.length)) n++;
  return n;
}

export function applyOverlay(source, overlay = OVERLAY) {
  let out = source;
  for (const o of overlay) {
    const n = count(out, o.from);
    if (n !== 1) throw new Error(`selfhost overlay "${o.name}" expected exactly 1 match in worker_cloud.js, found ${n}`);
    out = out.replace(o.from, () => o.to);
  }
  return out;
}

// 镜像里 worker 在 /app/vendor/，仓库里在 ../../cloudflare/。
export function findFile(envName, candidates) {
  const fromEnv = process.env[envName];
  if (fromEnv) { if (!existsSync(fromEnv)) throw new Error(`${envName}=${fromEnv} 不存在`); return fromEnv; }
  for (const c of candidates) if (existsSync(c)) return c;
  throw new Error(`找不到 ${envName}（试过 ${candidates.join(', ')}）`);
}
export const workerPath = () => findFile('ADP_WORKER_PATH', [resolve(HERE, 'vendor/worker_cloud.js'), resolve(HERE, '../../cloudflare/worker_cloud.js')]);
export const schemaPath = () => findFile('ADP_SCHEMA_PATH', [resolve(HERE, 'schema_cloud.sql'), resolve(HERE, '../../cloudflare/schema_cloud.sql')]);
export const mediaDir = () => findFile('ADP_MEDIA_DIR', [resolve(HERE, 'media'), resolve(HERE, '../../cloudflare/assets/media')]);

let cached = null;
export async function loadWorker() {
  if (cached) return cached;
  const src = applyOverlay(readFileSync(workerPath(), 'utf8'));
  const url = 'data:text/javascript;base64,' + Buffer.from(src, 'utf8').toString('base64');
  const mod = await import(url);
  if (typeof mod.default?.fetch !== 'function' || typeof mod.default?.scheduled !== 'function') {
    throw new Error('worker_cloud.js 没有导出 { fetch, scheduled }');
  }
  cached = { worker: mod.default, sourceSha256: createHash('sha256').update(src).digest('hex') };
  return cached;
}
