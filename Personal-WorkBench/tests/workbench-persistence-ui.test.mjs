import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const lifecycleSource = "app/_components/workbench/lifestyle-pages-client.tsx";
const resourceSource = "app/_components/workbench/tenant-resource-client.tsx";

test("workbench pages bind every visible lifecycle module to the tenant resource client", async () => {
  const source = await readFile(lifecycleSource, "utf8");

  for (const resource of [
    "habits",
    "habit-checkins",
    "ledger",
    "food",
    "exercise",
    "weights",
    "periods",
    "schedule",
    "anniversaries",
    "diary",
    "savings-goals",
    "savings-transactions",
  ]) {
    assert.match(source, new RegExp(`useTenantResource<[^>]+>\\(\\\"${resource}\\\"`), resource);
  }

  assert.doesNotMatch(source, /已保存到当前会话|登录后可同步到工作台|第 \$\{nextNumber\} 条/);
  assert.match(source, /ResourceStatus/);
  assert.match(source, /DeleteRecordButton/);
});

test("home prioritizes the actionable sign-in prerequisite over a parallel resource failure", async () => {
  const source = await readFile(lifecycleSource, "utf8");

  assert.match(source, /const authRequired = habits\.authRequired \|\| checkins\.authRequired;/);
  assert.match(
    source,
    /const statusError = authRequired\s*\? "请先登录并完成邮箱验证，再保存和查看你的历史记录。"/,
  );
  assert.match(source, /authRequired=\{authRequired\}/);
});

test("tenant resource client uses verified-session endpoints without client tenant fields", async () => {
  const source = await readFile(resourceSource, "utf8");

  assert.match(source, /fetch\(`\/api\/workbench\/\$\{resource\}`/);
  assert.match(source, /credentials: \"same-origin\"/);
  assert.match(source, /idempotency-key/);
  assert.match(source, /encodeURIComponent\(id\)/);
  assert.doesNotMatch(source, /userId\s*:/);
  assert.doesNotMatch(source, /ownerId\s*:/);
  assert.doesNotMatch(source, /tenantId\s*:/);
});
