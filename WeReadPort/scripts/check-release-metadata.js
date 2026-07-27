import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { APP_VERSION } from "../src/core/constants.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const pkg = await readJson("package.json");
assert.equal(pkg.version, "0.0.7", "package.json 版本必须是 0.0.7");
assert.equal(pkg.taskpackVersion, APP_VERSION, "任务包版本与运行时版本不一致");
assert.equal(pkg.releaseStage, "stage2-formal-development-taskpack-delivery");
assert.equal(pkg.devDependencies["@cloudflare/vite-plugin"], "1.47.0");
assert.equal(pkg.devDependencies["@openai/sites-vite-plugin"], "0.1.0");
assert.equal(pkg.devDependencies.vite, "8.1.5");
assert.equal(pkg.devDependencies.wrangler, "4.114.0");

if (await exists("package-lock.json")) {
  const lock = await readJson("package-lock.json");
  assert.equal(lock.name, pkg.name);
  assert.equal(lock.version, pkg.version);
  assert.equal(lock.lockfileVersion, 3);
  assert.equal(lock.packages?.[""]?.version, pkg.version);
  assert.deepEqual(lock.packages?.[""]?.devDependencies, pkg.devDependencies);
}

const sbomPath = await firstExisting(["sbom.cdx.json", "SBOM.cdx.json", "artifacts/sbom.cdx.json"]);
if (sbomPath) {
  const sbom = await readJson(sbomPath);
  const component = sbom.metadata?.component;
  assert.equal(component?.name, pkg.name);
  assert.equal(component?.version, pkg.version);
  if (component?.purl) assert.ok(component.purl.includes(`@${pkg.version}`));
}

const hosting = await readJson(".openai/hosting.json");
for (const forbidden of ["secret", "token", "password", "cookie", "authorization"]) {
  assert.equal(Object.keys(hosting).some(key => key.toLowerCase().includes(forbidden)), false, `hosting.json 禁止字段：${forbidden}`);
}
assert.equal(hosting.d1 ?? null, null, "P0 不应启用 D1");
assert.equal(hosting.r2 ?? null, null, "P0 产品面不应启用 R2");
console.log("发布元数据检查通过：版本、依赖、可选锁文件/SBOM 与 Sites 配置一致。");

async function readJson(relative) {
  return JSON.parse(await readFile(path.join(root, relative), "utf8"));
}
async function exists(relative) {
  try { await access(path.join(root, relative)); return true; } catch { return false; }
}
async function firstExisting(candidates) {
  for (const candidate of candidates) if (await exists(candidate)) return candidate;
  return null;
}
