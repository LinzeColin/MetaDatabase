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

test("todo uses a browser-valid date pattern and account-scoped IndexedDB persistence", async () => {
  const source = await readFile(todoSource, "utf8");
  const cacheSource = await readFile("app/_components/workbench/local-record-cache.ts", "utf8");

  assert.match(source, /placeholder="YYYY-MM-DD"/);
  assert.match(source, /pattern="\[0-9\]\{4\}-\[0-9\]\{2\}-\[0-9\]\{2\}"/);
  assert.doesNotMatch(source, /placeholder=\{toChineseDate\(""\)\}/);
  assert.match(source, /dueDate: safeString\(dueDate, toChineseDate\(""\)\)/);
  assert.match(source, /createDeviceLocalRecord/);
  assert.match(source, /writeDeviceLocalRecord/);
  assert.match(source, /readDeviceOutbox/);
  assert.match(source, /writeDeviceOutbox/);
  assert.match(source, /scope === "guest"/);
  assert.match(cacheSource, /const OUTBOX_STORE = "outbox"/);
  assert.match(cacheSource, /const DATABASE_VERSION = 2/);
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

test("tenant resource client refreshes an account scope before merging or mutating cross-device history", async () => {
  const source = await readFile(resourceSource, "utf8");

  assert.match(source, /const scopeRefreshRef = useRef<Promise<string \| null> \| null>\(null\);/);
  assert.match(source, /const refreshCurrentScope = useCallback\(async \(\): Promise<string \| null> => \{/);
  assert.match(source, /if \(nextScope === scopeRef\.current\) return nextScope;/);
  assert.match(source, /commitRecords\(\[\]\);/);
  assert.match(source, /local = \(await readDeviceLocalRecords\(nextScope, resource\)\) as T\[\];/);
  assert.match(source, /const responseScope = await refreshCurrentScope\(\);/);
  assert.match(source, /if \(responseScope !== requestScope\) \{/);
  assert.match(source, /const reconciledScope = await refreshCurrentScope\(\);/);
  assert.match(source, /if \(reconciledScope !== requestScope\) \{/);
  assert.match(source, /async \(remote: T\[\], expectedScope: string\): Promise<T\[]>/);
  assert.match(source, /if \(!scope \|\| scope !== expectedScope \|\| scope === "guest" \|\| sensitive\) return remote;/);
  assert.match(source, /const scopeBeforeReplay = await refreshCurrentScope\(\);/);
  assert.match(source, /const scopeAfterReplay = await refreshCurrentScope\(\);/);
  assert.match(source, /const scopeBeforeRequest = await refreshCurrentScope\(\);/);
  assert.match(source, /if \(scopeBeforeRequest !== scope\) \{/);
  assert.match(source, /window\.addEventListener\("focus", refreshWhenVisible\);/);
  assert.match(source, /document\.addEventListener\("visibilitychange", refreshWhenDocumentVisible\);/);
});

test("tenant resource retries only same-account non-sensitive local records after connectivity returns", async () => {
  const source = await readFile(resourceSource, "utf8");
  const cacheSource = await readFile("app/_components/workbench/local-record-cache.ts", "utf8");

  assert.match(source, /appendDeviceOutbox/);
  assert.match(source, /readDeviceOutbox/);
  assert.match(source, /removeDeviceOutboxActions/);
  assert.match(source, /replayOutboxQueue/);
  assert.match(source, /scope === "guest"/);
  assert.match(source, /if \(sensitive\) return false;/);
  assert.match(source, /if \(!scope \|\| scope !== expectedScope \|\| scope === "guest" \|\| sensitive\) return remote;/);
  assert.match(source, /const queuedForReplay = sensitive \? false : await queueDeviceMutation\(deviceOutboxAction\);/);
  assert.match(source, /window\.addEventListener\("online", replayWhenOnline\)/);
  assert.match(source, /已保存在当前设备。连接恢复后会自动同步。/);
  assert.match(source, /完成登录和邮箱验证后会自动同步。/);
  assert.match(cacheSource, /export async function removeDeviceOutboxActions/);
  assert.match(cacheSource, /const existing = await requestValue\(store\.get\(key\)\);/);
});
