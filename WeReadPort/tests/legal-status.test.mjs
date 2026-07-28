import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handleRequest } from "../src/server/handler.js";
import { LEGAL_EFFECTIVE_DATE, legalContentHtml, legalMainHtml, statusMainHtml } from "../src/core/public-pages.js";
import { APP_VERSION, SOURCE_SKILL_VERSION } from "../src/core/constants.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const healthyEnv = {
  ASSETS: {
    fetch: async request => {
      const url = new URL(request.url);
      if (url.pathname === "/site/home") return new Response("<!doctype html><html lang=\"zh-CN\"><title>阅迁</title></html>", { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } });
      return new Response("未找到", { status: 404, headers: { "Content-Type": "text/plain; charset=utf-8" } });
    },
  },
  WEREAD_ACCOUNT_SERVICE_URL: "https://account.example.test",
  WRP_INTERNAL_PROXY_SECRET: "test-internal-proxy-secret-not-for-production",
  WRP_TASKPACK_VERSION: "v0.0.0.1.9",
  WRP_RELEASE_COMMIT: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  WRP_OVH_RELEASE_ID: "ovh-release-test",
  WRP_SITES_PROJECT_ID: "sites-project-test",
  ACCOUNT_SERVICE_FETCH: async () => new Response(JSON.stringify({
    status: "ready", ready: true,
    releaseIdentity: {
      taskpackVersion: "v0.0.0.1.9",
      releaseCommit: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      ovhReleaseId: "ovh-release-test",
      sitesProjectId: "sites-project-test",
    },
  }), { status: 200, headers: { "Content-Type": "application/json" } }),
};

test("隐私政策覆盖账户、凭据、长期存储、隔离、第三方、权利和删除边界", () => {
  const html = legalContentHtml("privacy");
  for (const phrase of ["适用范围与产品主体", "我们处理的数据", "用途与法律边界", "存储、位置与保留", "安全与多用户隔离", "第三方平台与一键导入", "你的选择与权利", "儿童、事件与变更"]) assert.ok(html.includes(phrase), phrase);
  for (const phrase of ["不可变 account_id", "不会因为邮箱相同自动合并账户", "永久删除账户", "运行期模型 Token 依赖为零"]) assert.ok(html.includes(phrase), phrase);
  assert.ok(!/wrk-[A-Za-z0-9_-]{8,}/u.test(html));
  const page = legalMainHtml("privacy");
  assert.ok(page.includes("请勿公开粘贴密钥"));
  assert.ok(page.includes(LEGAL_EFFECTIVE_DATE));
});

test("使用条款覆盖账户、允许、禁止、导入同步、可用性和终止边界", () => {
  const html = legalContentHtml("terms");
  for (const phrase of ["服务范围", "账户与安全责任", "允许用途", "禁止用途", "导入、同步与数据责任", "上游、可用性与变更", "责任边界与终止"]) assert.ok(html.includes(phrase), phrase);
  assert.ok(html.includes("7×24 是架构、监控、自愈、备份和恢复目标"));
  assert.ok(html.includes("不会自动合并"));
});

test("系统状态静态正文在 JavaScript 不可用时仍可阅读且不使用用户凭据探测", () => {
  const html = statusMainHtml();
  for (const phrase of ["系统状态", "/healthz", "/readyz", "/api/status", "不使用任何用户密钥", "端到端白箱治理矩阵", "依赖与耦合"]) assert.ok(html.includes(phrase), phrase);
});

test("公开页面无尾斜杠入口安全重定向到规范地址", async () => {
  for (const route of ["privacy", "terms", "status"]) {
    const response = await handleRequest(new Request(`https://example.test/${route}`), healthyEnv);
    assert.equal(response.status, 308);
    assert.equal(response.headers.get("location"), `https://example.test/${route}/`);
  }
});

test("公开静态入口由 Worker 映射到内部资产前缀并统一附加安全头", async () => {
  const requested = [];
  const env = {
    ...healthyEnv,
    ASSETS: {
      fetch: async request => {
        requested.push(new URL(request.url).pathname);
        return new Response("<!doctype html><html lang=\"zh-CN\"></html>", { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } });
      },
    },
  };
  for (const [path, expected] of [["/", "/site/home"], ["/privacy/", "/site/privacy/page"], ["/assets/app.js", "/site/assets/app.js"]]) {
    const response = await handleRequest(new Request(`https://example.test${path}`), env);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("content-security-policy"), "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; connect-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; media-src 'none'; worker-src 'self'; manifest-src 'self'; upgrade-insecure-requests");
    assert.equal(response.headers.get("referrer-policy"), "no-referrer");
    assert.equal(response.headers.get("x-content-type-options"), "nosniff");
    assert.equal(requested.at(-1), expected);
  }
});

test("法律页面链接不会吞入中文标点且安全入口明确", () => {
  const html = legalMainHtml("privacy") + legalMainHtml("terms");
  assert.ok(!/href="[^"]+[，。；：！？、）》】」』]"/u.test(html));
  assert.ok(html.includes('href="https://github.com/LinzeColin/MetaDatabase/issues"'));
});

test("存活与就绪采用不同 Oracle，缺少绑定时不伪装就绪", async () => {
  const health = await handleRequest(new Request("https://example.test/healthz"));
  assert.equal(health.status, 200);
  assert.equal((await health.json()).status, "ALIVE");
  const ready = await handleRequest(new Request("https://example.test/readyz"));
  assert.equal(ready.status, 503);
  const payload = await ready.json();
  assert.equal(payload.status, "NOT_READY");
  assert.equal(payload.checks.staticAssets.ready, false);
  assert.equal(payload.checks.accountPlatformService.ready, false);
});

test("静态资源和账户服务同时可用时才报告生产就绪", async () => {
  const ready = await handleRequest(new Request("https://weread-port.linzezhang35.chatgpt.site/readyz"), healthyEnv);
  assert.equal(ready.status, 200);
  const readyPayload = await ready.json();
  assert.equal(readyPayload.status, "READY");
  assert.equal(readyPayload.runtimeMode, "production");

  const status = await handleRequest(new Request("https://weread-port.linzezhang35.chatgpt.site/api/status"), healthyEnv);
  assert.equal(status.status, 200);
  const payload = await status.json();
  assert.equal(payload.status, "OPERATIONAL");
  assert.equal(payload.appVersion, APP_VERSION);
  assert.equal(payload.sourceSkillVersion, SOURCE_SKILL_VERSION);
  assert.equal(payload.components.publicApplication.status, "AVAILABLE");
  assert.equal(payload.components.accountPlatform.status, "AVAILABLE");
  assert.equal(payload.dataBoundary.serverSideUserNotePersistence, true);
  assert.equal(payload.dataBoundary.accountScopedEncryption, true);
  assert.equal(payload.businessGovernance.graphStatus, "VALID");
  assert.equal(payload.businessGovernance.lines.length, 11);
});

test("公开状态响应不暴露 Secret、用户数据或部署内部标识", async () => {
  const response = await handleRequest(new Request("https://example.test/api/status"), { ...healthyEnv, PRIVATE_DATABASE_TOKEN: "never", R2_SECRET: "never-r2", USER_NOTE: "私人笔记正文" });
  const text = await response.text();
  for (const forbidden of ["never-r2", "私人笔记正文", "PRIVATE_DATABASE_TOKEN", "R2_SECRET", "project_id"]) assert.ok(!text.includes(forbidden));
});

test("机器端点只允许 GET/HEAD，HEAD 不返回正文", async () => {
  const head = await handleRequest(new Request("https://example.test/readyz", { method: "HEAD" }), healthyEnv);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), "");
  const post = await handleRequest(new Request("https://example.test/api/status", { method: "POST" }), healthyEnv);
  assert.equal(post.status, 405);
});

test("隐私、条款和状态源文件是预渲染页面而非同一空壳", async () => {
  const pages = {
    privacy: await readFile(path.join(root, "privacy/index.html"), "utf8"),
    terms: await readFile(path.join(root, "terms/index.html"), "utf8"),
    status: await readFile(path.join(root, "status/index.html"), "utf8"),
  };
  assert.ok(pages.privacy.includes("我们处理的数据"));
  assert.ok(pages.terms.includes("禁止用途"));
  assert.ok(pages.status.includes("公开运行状态"));
  assert.notEqual(pages.privacy, pages.terms);
  assert.notEqual(pages.terms, pages.status);
});

test("包版本、应用版本和任务包版本保持一致映射", async () => {
  const packageJson = JSON.parse(await readFile(path.join(root, "package.json"), "utf8"));
  assert.equal(packageJson.version, "0.0.9");
  assert.equal(packageJson.taskpackVersion, APP_VERSION);
  assert.equal(packageJson.releaseStage, "stage2-formal-development-taskpack-delivery");
});
