import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const lifecycleSource = "app/_components/workbench/lifestyle-pages-client.tsx";
const resourceSource = "app/_components/workbench/tenant-resource-client.tsx";
const todoSource = "app/_components/workbench/todo-page-client.tsx";

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

test("home preserves an on-device save acknowledgement while still offering the sign-in next step", async () => {
  const source = await readFile(lifecycleSource, "utf8");

  assert.match(source, /const authRequired = habits\.authRequired \|\| checkins\.authRequired;/);
  assert.match(source, /const statusError = habits\.error \|\| checkins\.error;/);
  assert.match(source, /authRequired=\{authRequired\}/);
  assert.match(source, /loginSuggested=\{loginSuggested\}/);
});

test("network-level resource uncertainty still offers a truthful sign-in next step", async () => {
  const source = await readFile(resourceSource, "utf8");

  assert.match(source, /const \[loginSuggested, setLoginSuggested\] = useState\(false\);/);
  assert.match(source, /暂时无法读取你的历史记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。/);
  assert.match(source, /暂时无法保存这条记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。/);
  assert.match(source, /暂时无法删除这条记录。请先登录并完成邮箱验证；若已登录，请检查网络后重试。/);
  assert.match(source, /authRequired \|\| loginSuggested \? <a className="data-link" href="\/auth\/sign-in">去登录<\/a> : null/);
});

test("habit controls distinguish an on-device check-in from a cloud-synced check-in", async () => {
  const source = await readFile(lifecycleSource, "utf8");

  assert.match(source, /setFeedback\(`正在处理\$\{card\.label\}打卡…`\);/);
  assert.match(source, /未完成\$\{card\.label\}打卡：请先登录并完成邮箱验证，或检查网络后重试。/);
  assert.match(source, /未能取消\$\{card\.label\}打卡，请检查后重试。/);
  assert.match(source, /已完成\$\{card\.label\}打卡，历史记录已同步。/);
  assert.match(source, /已完成\$\{card\.label\}打卡，记录已保存在当前设备。/);
  assert.match(source, /saveFeedback\(/);
});

test("period record control immediately acknowledges pending and failed saves", async () => {
  const source = await readFile(lifecycleSource, "utf8");

  assert.match(source, /setFeedback\("正在保存经期记录…"\);/);
  assert.match(source, /setFeedback\("未能保存经期记录，请查看上方状态提示后重试。"\);/);
  assert.match(source, /saveFeedback\(saved, "经期记录已保存，历史记录已更新。", "经期记录已保存在当前设备。"\)/);
  assert.doesNotMatch(source, /if \(periods\.authRequired\)/);
  assert.doesNotMatch(source, /if \(periods\.consentRequired\)/);
});

test("todo date placeholder is stable across server and browser rendering", async () => {
  const source = await readFile(todoSource, "utf8");

  assert.match(source, /placeholder="YYYY-MM-DD"/);
  assert.doesNotMatch(source, /placeholder=\{toChineseDate\(""\)\}/);
  assert.match(source, /dueDate: safeString\(dueDate, toChineseDate\(""\)\)/);
});

test("built-in habit requests use a stable ASCII idempotency key", async () => {
  const source = await readFile(lifecycleSource, "utf8");

  assert.match(source, /function builtinHabitIdempotencyKey\(index: number\): string/);
  assert.match(source, /builtin-habit-\$\{String\(index \+ 1\)\.padStart\(2, "0"\)\}-v1/);
  assert.match(source, /builtinHabitIdempotencyKey\(index\)/);
  assert.doesNotMatch(source, /builtin-habit-\$\{card\.label\}/);
});

test("tenant resource client uses verified-session endpoints without client tenant fields", async () => {
  const source = await readFile(resourceSource, "utf8");

  assert.match(source, /fetch\(`\/api\/mydairy\/\$\{resource\}`/);
  assert.doesNotMatch(source, /\/api\/workbench\//);
  assert.match(source, /credentials: \"same-origin\"/);
  assert.match(source, /request_id/);
  assert.doesNotMatch(source, /idempotency-key/);
  assert.match(source, /encodeURIComponent\(id\)/);
  assert.doesNotMatch(source, /userId\s*:/);
  assert.doesNotMatch(source, /ownerId\s*:/);
  assert.doesNotMatch(source, /tenantId\s*:/);
});

test("tenant resource client writes an opaque device-local fallback before a cloud mutation", async () => {
  const source = await readFile(resourceSource, "utf8");
  const cacheSource = await readFile("app/_components/workbench/local-record-cache.ts", "utf8");

  assert.match(source, /resolveBrowserRecordScope/);
  assert.match(source, /writeDeviceLocalRecord/);
  assert.match(source, /sensitive && cloudAvailabilityRef\.current !== "available"/);
  assert.match(source, /removeDeviceLocalRecord/);
  assert.match(cacheSource, /account:\$\{suffix\}/);
  assert.match(cacheSource, /Guest records[\s\S]*never auto-synced/);
  assert.match(cacheSource, /tenantFieldNames/);
});
