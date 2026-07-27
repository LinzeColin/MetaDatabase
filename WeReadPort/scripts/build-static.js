import { cp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { APP_NAME } from "../src/core/constants.js";
import { legalMainHtml, legalTitle, standaloneDocument, statusMainHtml } from "../src/core/public-pages.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.resolve(process.env.WEREAD_PORT_PORTABLE_DIST || path.join(root, "dist"));
if (dist === root || !dist) throw new Error("便携构建输出必须使用独立目录。");
await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await cp(path.join(root, "index.html"), path.join(dist, "index.html"));
await cp(path.join(root, "public"), dist, { recursive: true });
await mkdir(path.join(dist, "src"), { recursive: true });
await cp(path.join(root, "src", "core"), path.join(dist, "src", "core"), { recursive: true });
await cp(path.join(root, "src", "ui"), path.join(dist, "src", "ui"), { recursive: true });
await mkdir(path.join(dist, ".openai"), { recursive: true });
await cp(path.join(root, ".openai", "hosting.json"), path.join(dist, ".openai", "hosting.json"));

for (const kind of ["privacy", "terms"]) {
  const target = path.join(dist, kind);
  await mkdir(target, { recursive: true });
  await writeFile(path.join(target, "index.html"), standaloneDocument({
    title: `${legalTitle(kind)}｜${APP_NAME}`,
    description: kind === "privacy" ? "了解微信读书笔记迁移如何处理、传输、清除与保护数据。" : "了解微信读书笔记迁移的允许用途、禁止用途、服务边界和责任。",
    body: legalMainHtml(kind),
  }), "utf8");
}

const statusTarget = path.join(dist, "status");
await mkdir(statusTarget, { recursive: true });
await writeFile(path.join(statusTarget, "index.html"), standaloneDocument({
  title: `系统状态｜${APP_NAME}`,
  description: "查看微信读书笔记迁移的公开应用、静态资源、微信读书代理合同与运维入口状态。",
  body: statusMainHtml(),
}), "utf8");

const files = await walk(dist);
await writeFile(path.join(dist, "build-manifest.json"), `${JSON.stringify({
  generatedBy: "scripts/build-static.js",
  routes: ["/", "/privacy/", "/terms/", "/status/"],
  files: files.sort(),
}, null, 2)}\n`);
console.log(`已在 ${dist} 构建 ${files.length + 1} 个便携文件，并预渲染隐私、条款与系统状态页面。`);

async function walk(dir, prefix = "") {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const rel = path.posix.join(prefix, entry.name);
    if (entry.isDirectory()) out.push(...await walk(path.join(dir, entry.name), rel));
    else out.push(rel);
  }
  return out;
}
