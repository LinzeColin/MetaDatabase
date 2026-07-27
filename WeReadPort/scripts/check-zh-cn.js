import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const requiredFiles = [
  "index.html",
  "public/manifest.webmanifest",
  "src/ui/app.js",
  "src/ui/export-worker.js",
  "src/core/constants.js",
  "src/core/public-pages.js",
  "src/core/exporter.js",
  "src/core/local-import.js",
  "src/core/chatgpt-bridge.js",
  "src/core/offline-search.js",
  "src/core/render.js",
  "scripts/export-cli.js",
  "README.md",
  "AGENTS.md",
  "ops/status/adapter-contract.md",
  "privacy/index.html",
  "terms/index.html",
  "status/index.html",
];

const forbiddenVisiblePhrases = [
  "YOUR NOTES",
  "STEP 0",
  "Markdown Profile",
  "Portable CommonMark",
  "GitHub Flavored Markdown",
  "Obsidian Vault",
  "Notion Import ZIP",
  "DESIGNED FOR PORTABILITY",
  "Local server error",
  "Not found",
  "Export Report",
  "Static asset binding",
  "API Key",
  "Secret Key",
  "Canonical Reading Model",
];

const allowEnglishOnlyFiles = new Set([
  "src/core/model.js", // 仅包含内部类型说明。
  "tests/export-zip.test.mjs", // 测试名称和机器字段不属于产品界面。
  "tests/localization.test.mjs", // 负向断言包含旧名称。
  "scripts/check-zh-cn.js", // 扫描规则自身列出禁用短语。
]);

const errors = [];
for (const relative of requiredFiles) {
  const file = path.join(root, relative);
  const text = await readFile(file, "utf8");
  if (!/[\u3400-\u9fff]/u.test(text)) errors.push(`${relative} 缺少中文内容。`);
  for (const phrase of forbiddenVisiblePhrases) {
    if (text.includes(phrase)) errors.push(`${relative} 含未本地化短语：${phrase}`);
  }
}

const index = await readFile(path.join(root, "index.html"), "utf8");
if (!/<html\s+lang=["']zh-CN["']/u.test(index)) errors.push("index.html 必须声明 lang=zh-CN。");
if (!index.includes("微信读书笔记迁移")) errors.push("index.html 必须显示中文产品名“微信读书笔记迁移”。");

const manifest = JSON.parse(await readFile(path.join(root, "public/manifest.webmanifest"), "utf8"));
if (manifest.lang !== "zh-CN") errors.push("manifest.webmanifest 的 lang 必须为 zh-CN。");
if (!String(manifest.name ?? "").includes("微信读书笔记迁移")) errors.push("manifest.webmanifest 必须使用中文产品名。");

const constants = await readFile(path.join(root, "src/core/constants.js"), "utf8");
if (!constants.includes('APP_NAME = "微信读书笔记迁移"')) errors.push("APP_NAME 必须为中文产品名。");
if (!constants.includes('APP_VERSION = "v0.0.0.1.7"')) errors.push("APP_VERSION 必须为 v0.0.0.1.7。");

// “WeRead Port”仅允许作为向后兼容的内部稳定标识，不得进入页面、文案或导出显示名。
const allFiles = await walk(root);
for (const file of allFiles) {
  const relative = path.relative(root, file).split(path.sep).join("/");
  if (relative.startsWith("dist/") || relative.includes("node_modules/") || allowEnglishOnlyFiles.has(relative)) continue;
  if (!/\.(?:js|mjs|html|md|json|py|service|timer|example)$/u.test(relative)) continue;
  const text = await readFile(file, "utf8");
  if (text.includes("WeRead Port") && relative !== "src/core/constants.js") {
    errors.push(`${relative} 暴露旧英文产品名 WeRead Port。`);
  }
}

if (errors.length) {
  console.error("全局中文检查失败：");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}
console.log(`全局中文检查通过：${requiredFiles.length} 个关键产品文件，产品名、语言声明和禁用短语均符合要求。`);

async function walk(directory) {
  const rows = [];
  for (const name of (await readdir(directory)).sort()) {
    if (["node_modules", "dist", ".git", "__pycache__"].includes(name)) continue;
    const target = path.join(directory, name);
    const info = await stat(target);
    if (info.isDirectory()) rows.push(...await walk(target));
    else if (info.isFile()) rows.push(target);
  }
  return rows;
}
