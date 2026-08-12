#!/usr/bin/env node
// weread-port 唯一认可的生产部署入口：`npm run deploy:cloudflare`
//
// 不要直接跑 `npx wrangler deploy`。生产的 8 个 plain_text 变量在版本控制之外，
// 裸跑会把它们全部清掉 —— 站点当场变成「账户服务尚未完成安全连接」。
// 2026-08-12 真发生过一次，靠 `wrangler rollback` 恢复，中断约 3 分钟。
//
// 本脚本做四件事：
//   1. 部署前从**当前线上版本**取回变量，缺一个就拒绝部署（fail closed）
//   2. 构建，然后带着这些变量 deploy
//   3. 部署后回读：新版本的 bindings 齐不齐、运行时 /api/version 认不认这些值
//   4. 任一条不过 -> 自动 rollback 回上一版，并以非零退出
//
// 变量值全程不落日志：所有输出都过 redact()。

import { execFile } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import {
  REQUIRED_VARS, assertCarryableVars, checkRuntimeIdentity, collectPlainTextVars,
  diffDeployedVars, pickCurrentDeployment, redact,
} from "../src/ops/cloudflare-deploy-contract.js";

const run = promisify(execFile);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SCRIPT_NAME = "weread-port";
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID || "a8e86fa4be62ee3f9b5873b2aa934256";
const API_BASE = process.env.WRP_CF_API_BASE || "https://api.cloudflare.com/client/v4";
const SITE = process.env.WRP_DEPLOY_SITE || "https://weread.linzezhang.com";
const EVIDENCE_DIR = process.env.WRP_DEPLOY_EVIDENCE_DIR
  || path.join(process.env.HOME || ".", "Documents/Codex/GithubProject/_protected/WeReadPort_deploys");
const VERIFY_TRIES = 10;
const VERIFY_SLEEP_MS = 3000;
// next-env 之类的生成物这里没有；脏树一律拒绝，别给「顺手带上没提交的改动」留口子。

// say/fail 必须先于任何可能失败的语句定义：否则第一个 fail() 会撞上 liveVars 的
// TDZ，用户拿到的是一段堆栈而不是「缺 CLOUDFLARE_API_TOKEN」。（第一版就是这样，跑反例才发现。）
let liveVars = new Map();   // 供 redact 用；随取随更新
const say = message => console.log(redact(message, liveVars));
function fail(message) { console.error(redact(`[deploy] ${message}`, liveVars)); process.exit(1); }

const token = (process.env.CLOUDFLARE_API_TOKEN || "").trim();
if (!token) fail("缺少 CLOUDFLARE_API_TOKEN。凭据在 _protected/ops_vault 的 cloudflare_workers_deploy_token。");

async function cf(pathname) {
  const response = await fetch(`${API_BASE}${pathname}`, { headers: { Authorization: `Bearer ${token}` } });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.success) {
    const detail = payload?.errors?.map(e => e.message).join("；") || `HTTP ${response.status}`;
    throw new Error(`Cloudflare API 失败（${pathname}）：${detail}`);
  }
  return payload.result;
}

async function currentVersion() {
  const deployments = await cf(`/accounts/${ACCOUNT_ID}/workers/scripts/${SCRIPT_NAME}/deployments`);
  return pickCurrentDeployment(deployments?.deployments || []);
}

async function versionBindings(versionId) {
  const version = await cf(`/accounts/${ACCOUNT_ID}/workers/scripts/${SCRIPT_NAME}/versions/${versionId}`);
  return collectPlainTextVars(version?.resources?.bindings || version?.bindings || []);
}

async function assertCleanTree() {
  const { stdout } = await run("git", ["status", "--porcelain", "--", root], { cwd: root });
  if (stdout.trim()) fail(`工作树不干净，拒绝部署：\n${stdout.trim()}`);
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function fetchJson(url) {
  const response = await fetch(url, { headers: { "cache-control": "no-cache" } });
  if (!response.ok) throw new Error(`${url} 回 HTTP ${response.status}`);
  return response.json();
}

// ── 1. 部署前 ───────────────────────────────────────────────────────────────
// 抛出一律落成一行 [deploy] …：拒绝部署时该给的是「为什么不部署」，不是一段堆栈。
let previousVersionId, carry;
try {
  await assertCleanTree();
  previousVersionId = await currentVersion();
  liveVars = await versionBindings(previousVersionId);
  carry = assertCarryableVars(liveVars);
} catch (error) {
  fail(`${error.message}${previousVersionId ? `（读的是线上版本 ${previousVersionId.slice(0, 8)}）` : ""}`);
}
say(`[deploy] 当前线上版本 ${previousVersionId.slice(0, 8)}，取回 ${carry.length} 个变量：${REQUIRED_VARS.join("、")}`);

// ── 2. 构建并部署 ───────────────────────────────────────────────────────────
say("[deploy] 构建");
await run("npm", ["run", "build"], { cwd: root, maxBuffer: 32 * 1024 * 1024 });

say("[deploy] wrangler deploy（带回全部变量；secret 由 Cloudflare 自动保留）");
const deployArgs = ["wrangler", "deploy"];
for (const [name, value] of carry) deployArgs.push("--var", `${name}:${value}`);
try {
  const { stdout } = await run("npx", deployArgs, { cwd: root, maxBuffer: 32 * 1024 * 1024 });
  say(stdout.split("\n").filter(line => /Uploaded|Current Version/.test(line)).join("\n"));
} catch (error) {
  fail(`wrangler deploy 失败：${error.stderr || error.message}`);
}

const deployedVersionId = await currentVersion();
if (deployedVersionId === previousVersionId) fail("部署后版本 id 没变，wrangler 可能没真发出去。");

// ── 3. 部署后回读（有上限的重试；上游抖动不算失败）─────────────────────────
async function verifyOnce() {
  const problems = diffDeployedVars(carry, await versionBindings(deployedVersionId));
  try {
    problems.push(...checkRuntimeIdentity(await fetchJson(`${SITE}/api/version`), carry));
  } catch (error) {
    problems.push(`回读 /api/version 失败：${error.message}`);
  }
  try {
    const health = await fetchJson(`${SITE}/healthz`);
    if (health?.ok !== true) problems.push(`/healthz 不 ok：${health?.status ?? "无 status"}`);
  } catch (error) {
    problems.push(`回读 /healthz 失败：${error.message}`);
  }
  return problems;
}

let problems = [];
for (let attempt = 1; attempt <= VERIFY_TRIES; attempt++) {
  problems = await verifyOnce();
  if (!problems.length) { say(`[deploy] 第 ${attempt}/${VERIFY_TRIES} 次回读通过`); break; }
  if (attempt === VERIFY_TRIES) break;
  say(`[deploy] 第 ${attempt}/${VERIFY_TRIES} 次回读未过（${problems.join("；")}），${VERIFY_SLEEP_MS / 1000}s 后重试`);
  await sleep(VERIFY_SLEEP_MS);
}

// ── 4. 不过就回滚 ───────────────────────────────────────────────────────────
if (problems.length) {
  say(`[deploy] 回读失败，自动回滚到 ${previousVersionId.slice(0, 8)}：${problems.join("；")}`);
  try {
    await run("npx", ["wrangler", "rollback", "--version-id", previousVersionId,
      "--message", "自动回滚：部署后回读未通过", "-y"], { cwd: root, maxBuffer: 8 * 1024 * 1024 });
    fail("已回滚到上一版。站点应已恢复，请查上面的失败原因。");
  } catch (error) {
    fail(`回滚也失败了，站点可能仍处于坏状态，立刻人工介入：${error.stderr || error.message}`);
  }
}

// 上游账户服务单独看：它偶发 NOT_READY（实测约 1/13），只报告，不作为部署成败。
let accountService = "未探测";
try {
  const ready = await fetchJson(`${SITE}/readyz`);
  const check = ready?.checks?.accountPlatformService;
  accountService = check?.ready === true ? "READY" : `NOT_READY（${check?.detail ?? "无 detail"}）—— 上游状态，与本次部署无关`;
} catch (error) {
  accountService = `探测失败：${error.message}`;
}
say(`[deploy] 上游账户服务：${accountService}`);

// 证据留档（写不进去不算部署失败）
try {
  const { stdout: head } = await run("git", ["rev-parse", "HEAD"], { cwd: root });
  await mkdir(EVIDENCE_DIR, { recursive: true });
  const record = {
    script: SCRIPT_NAME, site: SITE, commit: head.trim(),
    previous_version_id: previousVersionId, deployed_version_id: deployedVersionId,
    carried_vars: REQUIRED_VARS, account_service: accountService, verified: true,
  };
  const file = path.join(EVIDENCE_DIR, `${deployedVersionId}.json`);
  await writeFile(file, `${JSON.stringify(record, null, 2)}\n`, "utf8");
  say(`[deploy] 记录：${file}`);
} catch (error) {
  say(`[deploy] 证据没写成（不影响部署）：${error.message}`);
}

say(`[deploy] 完成：${deployedVersionId.slice(0, 8)} 已上线，${REQUIRED_VARS.length} 个变量齐全并已回读确认。`);
