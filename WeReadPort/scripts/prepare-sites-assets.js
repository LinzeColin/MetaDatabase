import { access, mkdir, readdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const client = path.join(dist, "client");
const site = path.join(client, "site");
const worker = path.join(dist, "weread_port");
const server = path.join(dist, "server");

await rm(site, { recursive: true, force: true });
await mkdir(site, { recursive: true });
for (const entry of await readdir(client)) {
  if ([".assetsignore", "_headers", "site"].includes(entry)) continue;
  await rename(path.join(client, entry), path.join(site, entry));
}

for (const [from, to] of [["index.html", "home.html"], ["privacy/index.html", "privacy/page.html"], ["terms/index.html", "terms/page.html"], ["status/index.html", "status/page.html"]]) {
  await rename(path.join(site, from), path.join(site, to));
}

for (const required of ["home.html", "admin.html", "assets", "privacy/page.html", "terms/page.html", "status/page.html"]) {
  try { await access(path.join(site, required)); }
  catch { throw new Error(`Sites 静态前缀构建缺少：${required}`); }
}

await rm(server, { recursive: true, force: true });
await rename(worker, server);
await access(path.join(server, "index.js"));
console.log("Sites 静态资源已移动到内部 /site 前缀，Worker 输出已归一到 dist/server。");
