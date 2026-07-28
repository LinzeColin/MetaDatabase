import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const requiredFiles = [
  "index.html", "public/manifest.webmanifest", "src/ui/account-platform.js", "src/ui/app.js",
  "src/ui/obsidian-import.js", "src/core/constants.js", "src/core/public-pages.js",
  "service/platform/app.mjs", "service/platform/service.mjs", "service/platform/providers.mjs",
  "service/platform/weread.mjs", "README.md", "AGENTS.md", "service/README.md",
  "ops/status/adapter-contract.md", "privacy/index.html", "terms/index.html", "status/index.html",
];
const forbiddenVisiblePhrases = [
  "YOUR NOTES", "STEP 0", "DESIGNED FOR PORTABILITY", "Local server error", "Not found",
  "Export Report", "Static asset binding", "Secret Key", "Canonical Reading Model",
];
const errors = [];
for (const relative of requiredFiles) {
  const file = path.join(root, relative);
  const text = await readFile(file, "utf8");
  if (!/[\u3400-\u9fff]/u.test(text)) errors.push(`${relative} 缺少中文内容。`);
  for (const phrase of forbiddenVisiblePhrases) if (text.includes(phrase)) errors.push(`${relative} 含未本地化短语：${phrase}`);
}
const index = await readFile(path.join(root, "index.html"), "utf8");
if (!/<html\s+lang=["']zh-CN["']/u.test(index)) errors.push("index.html 必须声明 lang=zh-CN。");
if (!index.includes("个人阅读资产中心")) errors.push("index.html 必须声明账户平台主入口。");
const manifest = JSON.parse(await readFile(path.join(root, "public/manifest.webmanifest"), "utf8"));
if (manifest.lang !== "zh-CN") errors.push("manifest.webmanifest 的 lang 必须为 zh-CN。");
if (!String(manifest.name ?? "").includes("阅读")) errors.push("manifest.webmanifest 必须使用中文阅读产品名。");
const constants = await readFile(path.join(root, "src/core/constants.js"), "utf8");
if (!constants.includes('APP_VERSION = "v0.0.0.1.9"')) errors.push("APP_VERSION 必须为 v0.0.0.1.9。");
const accountUi = await readFile(path.join(root, "src/ui/account-platform.js"), "utf8");
for (const required of ["创建账户", "邮箱密码登录", "用 Google 创建", "用 GitHub 创建", "用 Notion 创建", "导入与连接", "阅读画像", "账户与安全"]) {
  if (!accountUi.includes(required)) errors.push(`账户界面缺少中文主流程：${required}`);
}
const allFiles = await walk(root);
const userFacingRoots = ["index.html", "privacy/", "terms/", "status/", "public/", "src/ui/", "src/core/public-pages.js", "README.md", "service/README.md", "ops/status/"];
for (const file of allFiles) {
  const relative = path.relative(root, file).split(path.sep).join("/");
  if (!userFacingRoots.some((prefix) => relative === prefix || relative.startsWith(prefix))) continue;
  if (relative.startsWith("dist/") || !/\.(?:js|html|md|json)$/u.test(relative)) continue;
  const text = await readFile(file, "utf8");
  if (text.includes("WeRead Port") && !["src/core/constants.js", "README.md"].includes(relative)) errors.push(`${relative} 暴露内部英文兼容标识。`);
}
if (errors.length) { console.error("全局中文检查失败："); for (const error of errors) console.error(`- ${error}`); process.exit(1); }
console.log(`全局中文检查通过：${requiredFiles.length} 个关键账户、导入、法律、运维和状态文件。`);
async function walk(directory) { const rows=[]; for (const name of (await readdir(directory)).sort()) { if (["node_modules","dist",".git","__pycache__"].includes(name)) continue; const target=path.join(directory,name); const info=await stat(target); if (info.isDirectory()) rows.push(...await walk(target)); else if (info.isFile()) rows.push(target); } return rows; }
