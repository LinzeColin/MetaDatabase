import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handleRequest } from "../src/server/handler.js";
import {
  LEGAL_EFFECTIVE_DATE,
  legalContentHtml,
  legalMainHtml,
  statusMainHtml,
} from "../src/core/public-pages.js";
import { APP_VERSION, SOURCE_SKILL_VERSION } from "../src/core/constants.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const assetEnv = {
  ASSETS: {
    fetch: async request => {
      const url = new URL(request.url);
      if (url.pathname === "/index.html") {
        return new Response("<!doctype html><html lang=\"zh-CN\"><title>微信读书笔记迁移</title></html>", {
          status: 200,
          headers: { "Content-Type": "text/html; charset=utf-8" },
        });
      }
      return new Response("未找到", { status: 404, headers: { "Content-Type": "text/plain; charset=utf-8" } });
    },
  },
};

test("隐私政策覆盖生产所需的处理、保存、第三方、权利与安全边界", () => {
  const html = legalContentHtml("privacy");
  for (const phrase of [
    "适用范围与维护者",
    "我们处理哪些数据",
    "处理目的与处理位置",
    "保存、清除与备份边界",
    "访问统计、日志与第三方",
    "你的选择与责任",
    "安全、儿童与政策变更",
    LEGAL_EFFECTIVE_DATE,
  ]) assert.ok(html.includes(phrase), `隐私政策缺少：${phrase}`);
  assert.ok(!/wrk-[A-Za-z0-9_-]{8,}/u.test(html));
  assert.ok(legalMainHtml("privacy").includes("报告安全问题时请勿公开粘贴密钥或笔记"));
});

test("使用条款覆盖允许、禁止、内容责任、可用性与变更边界", () => {
  const html = legalContentHtml("terms");
  for (const phrase of [
    "服务目的与适用范围",
    "允许用途",
    "禁止用途",
    "密钥、文件与内容责任",
    "可用性、上游变化与安全停止",
    "责任限制与变更",
  ]) assert.ok(html.includes(phrase), `使用条款缺少：${phrase}`);
  assert.ok(html.includes("7×24 是架构、监控、自愈、备份和恢复目标"));
});

test("系统状态静态正文在 JavaScript 不可用时仍可阅读", () => {
  const html = statusMainHtml();
  for (const phrase of ["系统状态", "/healthz", "/readyz", "/api/status", "不使用你的微信读书密钥进行探测", "端到端白箱治理矩阵", "依赖与耦合"]) {
    assert.ok(html.includes(phrase), `系统状态静态页缺少：${phrase}`);
  }
});


test("公开页面无尾斜杠入口安全重定向到规范地址", async () => {
  for (const route of ["privacy", "terms", "status"]) {
    const response = await handleRequest(new Request(`https://example.test/${route}`), assetEnv);
    assert.equal(response.status, 308);
    assert.equal(response.headers.get("location"), `https://example.test/${route}/`);
  }
});

test("法律页面自动链接不会把中文标点吞入 href", () => {
  const html = legalContentHtml("privacy") + legalContentHtml("terms");
  assert.ok(!/href="[^"]+[，。；：！？、）》】」』]"/u.test(html));
  assert.ok(!html.includes('issues。本工具'));
  assert.ok(html.includes('href="https://github.com/LinzeColin/MetaDatabase/issues"'));
});

test("存活与就绪采用不同 Oracle，缺少资源绑定时不会伪装就绪", async () => {
  const health = await handleRequest(new Request("https://example.test/healthz"));
  assert.equal(health.status, 200);
  assert.equal((await health.json()).status, "ALIVE");

  const ready = await handleRequest(new Request("https://example.test/readyz"));
  assert.equal(ready.status, 503);
  const payload = await ready.json();
  assert.equal(payload.status, "NOT_READY");
  assert.equal(payload.checks.staticAssets.ready, false);
});

test("静态资源真实可读时就绪与公开状态才报告可用", async () => {
  const ready = await handleRequest(new Request("https://weread-port.linzezhang35.chatgpt.site/readyz"), assetEnv);
  assert.equal(ready.status, 200);
  const readyPayload = await ready.json();
  assert.equal(readyPayload.status, "READY");
  assert.equal(readyPayload.runtimeMode, "production");

  const status = await handleRequest(new Request("https://weread-port.linzezhang35.chatgpt.site/api/status"), assetEnv);
  assert.equal(status.status, 200);
  const payload = await status.json();
  assert.equal(payload.status, "OPERATIONAL");
  assert.equal(payload.appVersion, APP_VERSION);
  assert.equal(payload.sourceSkillVersion, SOURCE_SKILL_VERSION);
  assert.equal(payload.components.publicApplication.status, "AVAILABLE");
  assert.equal(payload.dataBoundary.serverSideUserNotePersistence, false);
  assert.equal(payload.businessGovernance.graphStatus, "VALID");
  assert.equal(payload.businessGovernance.lines.length, 7);
});

test("公开状态响应不暴露环境 Secret、用户数据或部署内部标识", async () => {
  const response = await handleRequest(new Request("https://example.test/api/status"), {
    ...assetEnv,
    DEPLOYMENT_ENV: "preview",
    PRIVATE_DATABASE_TOKEN: "should-never-appear",
    R2_SECRET: "should-never-appear",
    USER_NOTE: "私人笔记正文",
  });
  const text = await response.text();
  for (const forbidden of ["should-never-appear", "私人笔记正文", "PRIVATE_DATABASE_TOKEN", "R2_SECRET", "project_id"]) {
    assert.ok(!text.includes(forbidden), `状态响应泄露：${forbidden}`);
  }
});

test("机器端点只允许 GET/HEAD，HEAD 不返回正文", async () => {
  const head = await handleRequest(new Request("https://example.test/readyz", { method: "HEAD" }), assetEnv);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), "");
  const post = await handleRequest(new Request("https://example.test/api/status", { method: "POST" }), assetEnv);
  assert.equal(post.status, 405);
});

test("隐私、条款和状态源文件是预渲染页面而不是同一空壳副本", async () => {
  const pages = {
    privacy: await readFile(path.join(root, "privacy/index.html"), "utf8"),
    terms: await readFile(path.join(root, "terms/index.html"), "utf8"),
    status: await readFile(path.join(root, "status/index.html"), "utf8"),
  };
  assert.ok(pages.privacy.includes("我们处理哪些数据"));
  assert.ok(pages.terms.includes("禁止用途"));
  assert.ok(pages.status.includes("公开运行状态"));
  assert.notEqual(pages.privacy, pages.terms);
  assert.notEqual(pages.terms, pages.status);
});

test("包版本、应用版本和任务包版本保持一致映射", async () => {
  const packageJson = JSON.parse(await readFile(path.join(root, "package.json"), "utf8"));
  assert.equal(packageJson.version, "0.0.7");
  assert.equal(packageJson.taskpackVersion, APP_VERSION);
  assert.equal(packageJson.releaseStage, "stage2-formal-development-taskpack-delivery");
});
