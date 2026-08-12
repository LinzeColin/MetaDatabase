import test from "node:test";
import assert from "node:assert/strict";
import {
  PRESERVED_SECRETS, REQUIRED_VARS, assertCarryableVars, checkRuntimeIdentity,
  collectPlainTextVars, diffDeployedVars, pickCurrentDeployment, redact,
} from "../src/ops/cloudflare-deploy-contract.js";

// 2026-08-12 事故的真实形状：能用的那一版有 8 个 plain_text + 1 个 secret，
// 裸跑 wrangler deploy 之后只剩 assets + secret。
const HEALTHY_BINDINGS = [
  { type: "service", name: "ASSETS" },
  { type: "plain_text", name: "DEPLOYMENT_ENV", text: "production" },
  { type: "plain_text", name: "WEREAD_ACCOUNT_SERVICE_URL", text: "https://weread-api.example.com" },
  { type: "plain_text", name: "WRP_ACCOUNT_PROXY_TIMEOUT_MS", text: "12000" },
  { type: "plain_text", name: "WRP_EDGE_DEPLOYMENT_ID", text: "cf-edge-v1" },
  { type: "plain_text", name: "WRP_OVH_RELEASE_ID", text: "ovh-v1" },
  { type: "plain_text", name: "WRP_PUBLIC_HOST", text: "weread.example.com" },
  { type: "plain_text", name: "WRP_RELEASE_COMMIT", text: "a".repeat(40) },
  { type: "plain_text", name: "WRP_TASKPACK_VERSION", text: "v0.0.0.1.9" },
  { type: "secret_text", name: "WRP_INTERNAL_PROXY_SECRET" },
];
const WIPED_BINDINGS = [
  { type: "assets", name: "ASSETS" },
  { type: "secret_text", name: "WRP_INTERNAL_PROXY_SECRET" },
];

test("正例：线上齐全时给出可带走的 8 个变量", () => {
  const carry = assertCarryableVars(collectPlainTextVars(HEALTHY_BINDINGS));
  assert.deepEqual(carry.map(([name]) => name), [...REQUIRED_VARS]);
  assert.equal(carry.length, 8);
});

test("反例：线上被清空时拒绝部署，而不是发一个残缺版本上去", () => {
  assert.throws(
    () => assertCarryableVars(collectPlainTextVars(WIPED_BINDINGS)),
    /线上缺少变量.*不部署/s,
  );
});

test("反例：少任意一个变量都要拦下（逐个试，不是只试一个）", () => {
  for (const dropped of REQUIRED_VARS) {
    const bindings = HEALTHY_BINDINGS.filter(b => b.name !== dropped);
    assert.throws(
      () => assertCarryableVars(collectPlainTextVars(bindings)),
      new RegExp(dropped),
      `${dropped} 缺失时没有被拦下`,
    );
  }
});

test("反例：变量存在但为空串也要拦下（空值等于没有）", () => {
  const bindings = HEALTHY_BINDINGS.map(b =>
    b.name === "WEREAD_ACCOUNT_SERVICE_URL" ? { ...b, text: "   " } : b);
  assert.throws(() => assertCarryableVars(collectPlainTextVars(bindings)), /线上变量为空/);
});

test("反例：secret 被降级成 plain_text 要拦下", () => {
  const bindings = [...HEALTHY_BINDINGS,
    { type: "plain_text", name: PRESERVED_SECRETS[0], text: "不该出现在这里" }];
  assert.throws(() => assertCarryableVars(collectPlainTextVars(bindings)), /应当是 secret/);
});

test("部署后：变量原样带上时无差异；丢失或被改都要报出来", () => {
  const carry = assertCarryableVars(collectPlainTextVars(HEALTHY_BINDINGS));
  assert.deepEqual(diffDeployedVars(carry, collectPlainTextVars(HEALTHY_BINDINGS)), []);
  assert.deepEqual(diffDeployedVars(carry, collectPlainTextVars(WIPED_BINDINGS)),
    REQUIRED_VARS.map(name => `${name} 丢失`));
  const tampered = HEALTHY_BINDINGS.map(b =>
    b.name === "WRP_PUBLIC_HOST" ? { ...b, text: "别的域名" } : b);
  assert.deepEqual(diffDeployedVars(carry, collectPlainTextVars(tampered)),
    ["WRP_PUBLIC_HOST 与部署前不一致"]);
});

test("运行时回读：值真的到了 worker 里才算过", () => {
  const carry = assertCarryableVars(collectPlainTextVars(HEALTHY_BINDINGS));
  const good = { releaseCommit: "a".repeat(40), ovhReleaseId: "ovh-v1", edgeDeploymentId: "cf-edge-v1", taskpackVersion: "v0.0.0.1.9" };
  assert.deepEqual(checkRuntimeIdentity(good, carry), []);
  assert.deepEqual(checkRuntimeIdentity({ ...good, releaseCommit: "" }, carry),
    ["运行时 releaseCommit 为空（WRP_RELEASE_COMMIT 没到 worker 里）"]);
  assert.deepEqual(checkRuntimeIdentity({ ...good, ovhReleaseId: "别的" }, carry),
    ["运行时 ovhReleaseId 与送入的 WRP_OVH_RELEASE_ID 不一致"]);
  assert.equal(checkRuntimeIdentity({}, carry).length, 4, "整个响应为空时四项都要报");
});

test("运行时回读不看上游账户服务健不健康（它实测会偶发 NOT_READY）", () => {
  const carry = assertCarryableVars(collectPlainTextVars(HEALTHY_BINDINGS));
  const payload = { releaseCommit: "a".repeat(40), ovhReleaseId: "ovh-v1", edgeDeploymentId: "cf-edge-v1", taskpackVersion: "v0.0.0.1.9", accountPlatformService: { ready: false } };
  assert.deepEqual(checkRuntimeIdentity(payload, carry), [],
    "上游 NOT_READY 不该被算成部署失败，否则上游一抖就回滚好的部署");
});

test("变量值一律不许进日志", () => {
  const vars = collectPlainTextVars(HEALTHY_BINDINGS);
  const line = "deploy 输出里混进了 https://weread-api.example.com 和 weread.example.com";
  const safe = redact(line, vars);
  assert.ok(!safe.includes("https://weread-api.example.com"), "URL 没被遮掉");
  assert.ok(!safe.includes("weread.example.com"), "host 没被遮掉");
  assert.match(safe, /<WEREAD_ACCOUNT_SERVICE_URL>/);
});

// 真实 /deployments 返回的顺序：**降序**（最新在前），而 `wrangler deployments list`
// 打印出来是升序。第一版按 wrangler 的顺序写成 .at(-1)，读到 2026-08-02 最早那一版，
// 于是对着好好的线上报「缺 8 个变量」拒绝部署。
const REAL_DEPLOYMENTS_DESC = [
  { created_on: "2026-08-12T03:15:34.610766Z", versions: [{ version_id: "8238e5af-newest" }] },
  { created_on: "2026-08-12T03:12:51.360145Z", versions: [{ version_id: "c7b6d8e9-rollback" }] },
  { created_on: "2026-08-02T11:36:00.363113Z", versions: [{ version_id: "977cf154-oldest" }] },
];

test("挑当前线上版本：降序 payload 要拿到最新那一版", () => {
  assert.equal(pickCurrentDeployment(REAL_DEPLOYMENTS_DESC), "8238e5af-newest");
});

test("挑当前线上版本：升序 payload 也要拿到同一版（不依赖任何一端的顺序约定）", () => {
  assert.equal(pickCurrentDeployment([...REAL_DEPLOYMENTS_DESC].reverse()), "8238e5af-newest");
});

test("挑当前线上版本：拿不到就抛，不许静默用一个错的版本继续", () => {
  assert.throws(() => pickCurrentDeployment([]), /取不到当前线上版本/);
  assert.throws(() => pickCurrentDeployment([{ created_on: "2026-08-12T00:00:00Z" }]), /取不到当前线上版本/);
});
