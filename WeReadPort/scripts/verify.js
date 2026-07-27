import { access, mkdtemp, readdir, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const tests = (await readdir(path.join(root, "tests"))).filter(name => name.endsWith(".test.mjs")).sort();
if (!tests.length) throw new Error("Verification refused: no *.test.mjs files found.");
const portableDist = await mkdtemp(path.join(os.tmpdir(), "weread-port-verify-"));
try {
  run(process.execPath, ["scripts/check-syntax.js"]);
  run(process.execPath, ["scripts/check-secrets.js"]);
  run(process.execPath, ["scripts/check-zh-cn.js"]);
  run(process.execPath, ["scripts/check-public-pages.js"]);
  run(process.execPath, ["scripts/check-release-metadata.js"]);
  run(process.execPath, ["--test", ...tests.map(name => path.join("tests", name))]);
  run(process.execPath, ["scripts/build-static.js"], { WEREAD_PORT_PORTABLE_DIST: portableDist });
  for (const expected of [
    "index.html",
    "src/ui/app.js",
    "src/ui/export-worker.js",
    "src/core/exporter.js",
    ".openai/hosting.json",
    "build-manifest.json",
    "privacy/index.html",
    "terms/index.html",
    "status/index.html",
  ]) await access(path.join(portableDist, expected));
  console.log("\n全部无依赖验证均已通过：测试集非空、全局中文与静态公开页面检查通过，并完成隔离式便携构建。");
} finally {
  await rm(portableDist, { recursive: true, force: true });
}

function run(command, args, extraEnv = {}) {
  console.log(`\n> ${[command, ...args].join(" ")}`);
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit", env: { ...process.env, ...extraEnv } });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
