import { access, mkdir, readdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const client = path.join(root, "dist", "client");
const site = path.join(client, "site");

await rm(site, { recursive: true, force: true });
await mkdir(site, { recursive: true });
for (const entry of await readdir(client)) {
  if ([".assetsignore", "_headers", "site"].includes(entry)) continue;
  await rename(path.join(client, entry), path.join(site, entry));
}

for (const required of ["index.html", "assets", "privacy/index.html", "terms/index.html", "status/index.html"]) {
  try { await access(path.join(site, required)); }
  catch { throw new Error(`Sites 静态前缀构建缺少：${required}`); }
}
console.log("Sites 静态资源已移动到内部 /site 前缀；公开路由将由 Worker 统一加固。");
