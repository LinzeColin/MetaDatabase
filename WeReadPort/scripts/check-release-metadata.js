import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { APP_VERSION } from "../src/core/constants.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const pkg = await readJson("package.json");
assert.equal(pkg.version, "0.0.9", "package.json 版本必须是 0.0.9");
assert.equal(pkg.taskpackVersion, "v0.0.0.1.9");
assert.equal(APP_VERSION, pkg.taskpackVersion, "任务包版本与运行时版本不一致");
assert.equal(pkg.releaseStage, "stage2-formal-development-taskpack-delivery");
for (const [name, expected] of Object.entries({
  "@cloudflare/vite-plugin": "1.47.0",
  vite: "8.1.5",
  wrangler: "4.114.0",
})) assert.equal(pkg.devDependencies[name], expected, `${name} 必须锁定到 ${expected}`);

assert.equal(await exists("package-lock.json"), true, "正式开发任务包必须包含 package-lock.json");
const lock = await readJson("package-lock.json");
assert.equal(lock.name, pkg.name);
assert.equal(lock.version, pkg.version);
assert.equal(lock.lockfileVersion, 3);
assert.equal(lock.packages?.[""]?.version, pkg.version);
assert.deepEqual(lock.packages?.[""]?.devDependencies, pkg.devDependencies);

const sbomPath = await firstExisting(["sbom.cdx.json", "SBOM.cdx.json", "artifacts/sbom.cdx.json"]);
assert.ok(sbomPath, "正式开发任务包必须包含 CycloneDX SBOM");
const sbom = await readJson(sbomPath);
assert.equal(sbom.metadata?.component?.name, pkg.name);
assert.equal(sbom.metadata?.component?.version, pkg.version);
assert.equal(JSON.stringify(sbom).includes("@openai/sites-vite-plugin"), false, "SBOM 不得残留 ChatGPT Sites 构建依赖。");
assert.equal(JSON.stringify(sbom).includes("chatgpt.site"), false, "SBOM 不得残留 ChatGPT Sites 域名。");

assert.equal(await exists(".openai/hosting.json"), false, "生产入口不得保留 ChatGPT Sites 配置。");
const wrangler = await readJson("wrangler.jsonc");
assert.equal(wrangler.workers_dev, false, "不得暴露 workers.dev 默认入口。");
assert.equal(wrangler.assets?.binding, "ASSETS", "Cloudflare 静态资源绑定必须存在。");
assert.equal(wrangler.assets?.directory, "./dist/client", "Cloudflare 静态资源必须来自标准 Vite 构建输出。");
assert.equal(JSON.stringify(pkg).includes("@openai/sites-vite-plugin"), false, "不得保留 ChatGPT Sites 构建依赖。");

for (const required of [
  "service/platform/app.mjs", "service/platform/service.mjs", "service/platform/store.mjs",
  "service/platform/object-store.mjs", "service/platform/providers.mjs", "service/platform/weread.mjs",
  "service/schema.sql", "service/install_platform.py", "service/systemd/weread-port-platform.service",
  "src/ui/account-platform.js", "src/ui/account-api.js", "src/ui/obsidian-import.js",
]) assert.equal(await exists(required), true, `缺少当前版本必要文件：${required}`);

console.log("发布元数据检查通过：v0.0.0.1.9、锁文件、SBOM、Cloudflare/OVH 分层与账户平台制品一致。");

async function readJson(relative) { return JSON.parse(await readFile(path.join(root, relative), "utf8")); }
async function exists(relative) { try { await access(path.join(root, relative)); return true; } catch { return false; } }
async function firstExisting(candidates) { for (const candidate of candidates) if (await exists(candidate)) return candidate; return null; }
