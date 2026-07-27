import test from "node:test";
import assert from "node:assert/strict";
import {
  BUSINESS_GOVERNANCE_SCHEMA_VERSION,
  BUSINESS_LINE_STATE,
  buildBusinessLineStatus,
  businessLineDefinitions,
  summarizeBusinessLines,
  validateBusinessLineGraph,
} from "../src/core/business-governance.js";
import { businessGovernanceStaticHtml, statusMainHtml } from "../src/core/public-pages.js";
import { handleRequest } from "../src/server/handler.js";

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
      return new Response("未找到", { status: 404 });
    },
  },
};

test("业务线合同具有唯一标识、已登记依赖和无环 DAG", () => {
  const lines = businessLineDefinitions();
  assert.equal(lines.length, 7);
  assert.deepEqual(validateBusinessLineGraph(lines), []);
  assert.equal(new Set(lines.map(line => line.id)).size, lines.length);
  assert.ok(lines.some(line => line.dependsOnAny.length > 0), "至少一条链路应表达输入替代关系");
});

test("运行时只把已取得 Oracle 的业务线标记为就绪", () => {
  const lines = buildBusinessLineStatus({ assetsReady: true, checkedAt: "2026-07-27T00:00:00Z" });
  const byId = new Map(lines.map(line => [line.id, line]));
  assert.equal(byId.get("public-trust").state, BUSINESS_LINE_STATE.READY);
  assert.equal(byId.get("local-import").state, BUSINESS_LINE_STATE.READY);
  assert.equal(byId.get("weread-direct-export").state, BUSINESS_LINE_STATE.NOT_VERIFIED);
  assert.equal(byId.get("release-supply-chain").state, BUSINESS_LINE_STATE.NOT_VERIFIED);
  assert.equal(byId.get("operations-recovery").state, BUSINESS_LINE_STATE.EXTERNAL);
  const summary = summarizeBusinessLines(lines);
  assert.equal(summary.total, 7);
  assert.deepEqual(summary.blocking, []);
  assert.deepEqual(summary.notVerified.sort(), ["release-supply-chain", "weread-direct-export"]);
});

test("静态资源故障时受影响纵向链路 fail-closed", () => {
  const lines = buildBusinessLineStatus({ assetsReady: false, checkedAt: "2026-07-27T00:00:00Z" });
  const blocked = lines.filter(line => line.state === BUSINESS_LINE_STATE.BLOCKED).map(line => line.id);
  assert.deepEqual(blocked.sort(), ["chatgpt-handoff", "local-import", "normalize-export", "public-trust", "weread-direct-export"].sort());
  assert.ok(lines.every(line => line.reasonCode && line.recoveryAction));
});

test("无 JavaScript 状态页仍包含完整业务基线矩阵", () => {
  const html = statusMainHtml();
  const table = businessGovernanceStaticHtml();
  for (const phrase of ["业务基线纵向切片", "端到端白箱治理矩阵", "依赖与耦合", "验收 Oracle", "恢复或下一步"]) {
    assert.ok(html.includes(phrase), `缺少静态状态内容：${phrase}`);
  }
  for (const line of businessLineDefinitions()) {
    assert.ok(table.includes(`data-business-line=\"${line.id}\"`));
    assert.ok(table.includes(line.name));
  }
});

test("/readyz 与 /api/status 公开业务合同使用同一 schema 并保持脱敏", async () => {
  const ready = await handleRequest(new Request("https://example.test/readyz"), assetEnv);
  assert.equal(ready.status, 200);
  const readyPayload = await ready.json();
  assert.equal(readyPayload.checks.businessGovernanceContract.ready, true);
  assert.equal(readyPayload.checks.businessGovernanceContract.schemaVersion, BUSINESS_GOVERNANCE_SCHEMA_VERSION);

  const response = await handleRequest(new Request("https://example.test/api/status"), {
    ...assetEnv,
    USER_KEY: "do-not-expose",
    USER_NOTE: "不应公开的笔记",
    INTERNAL_PROJECT_ID: "private-project-id",
  });
  assert.equal(response.status, 200);
  const text = await response.text();
  const payload = JSON.parse(text);
  assert.equal(payload.businessGovernance.schemaVersion, BUSINESS_GOVERNANCE_SCHEMA_VERSION);
  assert.equal(payload.businessGovernance.graphStatus, "VALID");
  assert.equal(payload.businessGovernance.lines.length, 7);
  assert.equal(payload.dataBoundary.businessGovernanceContainsUserContent, false);
  for (const forbidden of ["do-not-expose", "不应公开的笔记", "private-project-id", "USER_KEY", "USER_NOTE"]) {
    assert.ok(!text.includes(forbidden), `业务状态泄露：${forbidden}`);
  }
});

test("版本接口公开治理 schema 但不公开运行内部标识", async () => {
  const response = await handleRequest(new Request("https://example.test/api/version"), assetEnv);
  const payload = await response.json();
  assert.equal(payload.businessGovernanceSchemaVersion, BUSINESS_GOVERNANCE_SCHEMA_VERSION);
  assert.deepEqual(Object.keys(payload).sort(), ["app", "appVersion", "businessGovernanceSchemaVersion", "sourceSkillVersion"].sort());
});
