import { access, mkdtemp, readdir, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const tests = await testFiles(path.join(root, "tests"));
if (!tests.length) throw new Error("验证拒绝：没有找到测试文件。");
const portableDist = await mkdtemp(path.join(os.tmpdir(), "weread-port-verify-"));
try {
  run(process.execPath, ["scripts/check-syntax.js"]);
  run(process.execPath, ["scripts/check-secrets.js"]);
  run(process.execPath, ["scripts/check-zh-cn.js"]);
  run(process.execPath, ["scripts/check-public-pages.js"]);
  run(process.execPath, ["scripts/check-release-metadata.js"]);
  run(process.execPath, ["--test", ...tests.map(file => path.relative(root, file))]);
  run("python3", ["-m", "compileall", "-q", "ops", "service"]);
  run("python3", ["-m", "unittest", "discover", "-s", "ops/tests", "-p", "test_*.py"]);
  run("python3", ["-m", "unittest", "discover", "-s", "service/tests", "-p", "test_*.py"]);
  run(process.execPath, ["scripts/build-static.js"], { WEREAD_PORT_PORTABLE_DIST: portableDist });
  for (const expected of ["index.html", "src/ui/account-platform.js", "src/ui/app.js", "src/ui/export-worker.js", "src/core/exporter.js", ".openai/hosting.json", "build-manifest.json", "privacy/index.html", "terms/index.html", "status/index.html"]) await access(path.join(portableDist, expected));
  console.log("\n全部冻结验证通过：账户平台、四平台导入、跨租户隔离、同步、画像、微信读书广范围合同、全局中文、运维恢复和便携构建均已即时验证。");
} finally { await rm(portableDist, { recursive: true, force: true }); }
function run(command, args, extraEnv = {}) { console.log(`\n> ${[command, ...args].join(" ")}`); const result=spawnSync(command,args,{cwd:root,stdio:"inherit",env:{...process.env,...extraEnv}}); if(result.status!==0) process.exit(result.status??1); }
async function testFiles(directory) { const out=[]; for (const entry of await readdir(directory,{withFileTypes:true})) { const full=path.join(directory,entry.name); if(entry.isDirectory()) out.push(...await testFiles(full)); else if(entry.isFile() && entry.name.endsWith(".test.mjs")) out.push(full); } return out.sort(); }
