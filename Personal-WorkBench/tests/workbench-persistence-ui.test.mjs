import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const lifecycleSource = "app/_components/workbench/lifestyle-pages-client.tsx";
const pageSource = "app/page.tsx";
const resourceSource = "app/_components/workbench/tenant-resource-client.tsx";
const todoSource = "app/_components/workbench/todo-page-client.tsx";
const accountSource = "app/account/page.tsx";
const legacyImportPanelSource = "app/account/legacy-import-panel.tsx";
const visitorTimeSource = "app/_components/workbench/visitor-time-client.tsx";

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

test("normal home reports authentication state and visitor-local time without changing the frozen reference view", async () => {
  const [source, page, visitorTime] = await Promise.all([
    readFile(lifecycleSource, "utf8"),
    readFile(pageSource, "utf8"),
    readFile(visitorTimeSource, "utf8"),
  ]);

  assert.match(source, /const visitorTime = useVisitorTime\(reference\);/);
  assert.match(source, /const accountActionRequired = authRequired \|\| loginSuggested;/);
  assert.doesNotMatch(source, /if \(accountActionRequired\) \{[\s\S]*?再开始\$\{card\.label\}打卡。[\s\S]*?return;/);
  assert.match(source, /accountActionRequired \? "本机打卡" : "点击打卡"/);
  assert.match(source, /useTenantResource<OverviewTodoRecord>\("todos", \{ enabled: !reference \}\)/);
  assert.match(source, /useTenantResource<LedgerRecord>\("ledger", \{ enabled: !reference, sensitive: true \}\)/);
  assert.match(source, /function overviewValue\(/);
  assert.match(source, /return "未登录";/);
  assert.match(source, /return "不确定";/);
  assert.doesNotMatch(source, /<div className="home-time">11:27<\/div>/);
  assert.match(visitorTime, /window\.setInterval\(refresh, refreshIntervalMs\)/);
  assert.match(visitorTime, /formatVisitorTime\(\)/);
  assert.match(page, /<VisitorDate fixtureDate=\{fixture\.date\} fixtureWeekday=\{fixture\.weekday\} reference=\{reference\} \/>/);
});

test("history empty states never replace an unreadable history with a false zero-record claim", async () => {
  const [lifecycle, todo] = await Promise.all([
    readFile(lifecycleSource, "utf8"),
    readFile(todoSource, "utf8"),
  ]);

  assert.match(lifecycle, /function canShowEmptyHistory\(/);
  assert.match(lifecycle, /canShowEmptyHistory\(ledger, reference\)/);
  assert.match(lifecycle, /canShowEmptyHistory\(activeResource, reference\)/);
  assert.match(lifecycle, /canShowEmptyHistory\(periods, reference\)/);
  assert.match(lifecycle, /canShowEmptyHistory\(current, reference\)/);
  assert.match(todo, /!todos\.loading && !todos\.error && todos\.records\.length === 0/);
});

test("account distinguishes signed-out visitors from signed-in unverified accounts", async () => {
  const account = await readFile(accountSource, "utf8");

  assert.match(account, /fetch\("\/api\/auth\/get-session\?disableCookieCache=true", \{ credentials: "same-origin" \}\)/);
  assert.match(account, /if \(!nextSession\?\.user\) \{\s+setMessage\("请先登录后再管理账户。"\);/);
  assert.match(account, /if \(!nextSession\.user\.emailVerified\) \{\s+setMessage\("请先完成邮箱验证。"\);/);
});

test("account exposes an explicit preview-before-apply legacy migration without changing source browser data", async () => {
  const [account, panel] = await Promise.all([
    readFile(accountSource, "utf8"),
    readFile(legacyImportPanelSource, "utf8"),
  ]);

  assert.match(account, /import \{ LegacyImportPanel \} from "\.\/legacy-import-panel"/);
  assert.match(account, /<LegacyImportPanel \/>/);
  assert.match(panel, /\/api\/mydairy\/legacy-import\/preview/);
  assert.match(panel, /\/api\/mydairy\/legacy-import\/apply\?request_id=/);
  assert.match(panel, /accept="application\/json,\.json"/);
  assert.match(panel, /预览完成：共/);
  assert.match(panel, /确认导入到我的历史/);
  assert.match(panel, /不会删除原文件或原浏览器数据/);
  assert.doesNotMatch(panel, /deleteDatabase|indexedDB\.deleteDatabase|localStorage\.removeItem/);
});

test("network-level resource uncertainty gives Google users a truthful sign-in next step", async () => {
  const source = await readFile(resourceSource, "utf8");

  assert.match(source, /const \[loginSuggested, setLoginSuggested\] = useState\(false\);/);
  assert.match(source, /暂时无法读取你的历史记录。请先确认已登录；使用 Google 登录无需额外验证邮箱。若已登录，请检查网络后重试。/);
  assert.match(source, /暂时无法保存这条记录。请先确认已登录；使用 Google 登录无需额外验证邮箱。若已登录，请检查网络后重试。/);
  assert.match(source, /暂时无法删除这条记录。请先确认已登录；使用 Google 登录无需额外验证邮箱。若已登录，请检查网络后重试。/);
  assert.match(source, /authRequired \|\| loginSuggested \? <a className="data-link" href="\/auth\/sign-in">去登录<\/a> : null/);
  assert.match(source, /consentRequired \? <a className="data-link" href="\/account" onClick=\{continueAfterConsent\}>开启敏感跨设备保存<\/a> : null/);
});

test("persistence UI distinguishes an explicit sensitive-consent denial from an account-verification denial", async () => {
  const source = await readFile(resourceSource, "utf8");

  assert.match(source, /type ApiFailureCode = "EMAIL_VERIFICATION_REQUIRED" \| "SENSITIVE_CLOUD_CONSENT_REQUIRED";/);
  assert.match(source, /code === "SENSITIVE_CLOUD_CONSENT_REQUIRED"/);
  assert.match(source, /code === "EMAIL_VERIFICATION_REQUIRED"/);
  assert.match(source, /function cloudAvailabilityFor\(status: number, code: ApiFailureCode \| null\)/);
  assert.match(source, /if \(code === "SENSITIVE_CLOUD_CONSENT_REQUIRED"\) return "consent_required";/);
  assert.match(source, /if \(code === "EMAIL_VERIFICATION_REQUIRED"\) return "verification_required";/);
  assert.match(source, /若刚使用 Google 登录，请退出后重新登录；邮箱账号请完成验证邮件。/);
  assert.match(source, /完成登录后会自动同步；使用 Google 登录无需额外验证邮箱。/);
});

test("habit controls distinguish an on-device check-in from a cloud-synced check-in", async () => {
  const source = await readFile(lifecycleSource, "utf8");

  assert.match(source, /setFeedback\(`正在处理\$\{card\.label\}打卡…`\);/);
  assert.match(source, /未完成\$\{card\.label\}打卡：请先登录；使用 Google 登录无需额外验证邮箱，或检查网络后重试。/);
  assert.match(source, /未能取消\$\{card\.label\}打卡，请检查后重试。/);
  assert.match(source, /已完成\$\{card\.label\}打卡，历史记录已同步。/);
  assert.match(source, /已完成\$\{card\.label\}打卡，记录已保存在当前设备。/);
  assert.match(source, /saveFeedback\(/);
});

test("first-paint write controls wait for resource initialization instead of losing a click", async () => {
  const [lifecycle, todo] = await Promise.all([
    readFile(lifecycleSource, "utf8"),
    readFile(todoSource, "utf8"),
  ]);

  assert.match(lifecycle, /disabled=\{habits\.loading \|\| checkins\.loading \|\| habits\.saving \|\| checkins\.saving\}/);
  assert.match(lifecycle, /disabled=\{ledger\.loading \|\| ledger\.saving\}/);
  assert.match(lifecycle, /disabled=\{foodRecords\.loading \|\| foodRecords\.saving\}/);
  assert.match(lifecycle, /disabled=\{exerciseRecords\.loading \|\| exerciseRecords\.saving\}/);
  assert.match(lifecycle, /disabled=\{weightRecords\.loading \|\| weightRecords\.saving\}/);
  assert.match(lifecycle, /disabled=\{periods\.loading \|\| periods\.saving\}/);
  assert.match(lifecycle, /disabled=\{reference \|\| current\.loading \|\| current\.saving\}/);
  assert.match(lifecycle, /disabled=\{reference \|\| savingsTransactions\.loading \|\| savingsTransactions\.saving\}/);
  assert.match(todo, /disabled=\{todos\.loading \|\| todos\.saving\}/);
});

test("normal menu routes keep every user-audited lifecycle control bound to a state change or record write", async () => {
  const [source, page] = await Promise.all([
    readFile(lifecycleSource, "utf8"),
    readFile(pageSource, "utf8"),
  ]);

  assert.match(page, /const reference = typeof params\.reference === "string" && referenceRoutes\.has\(params\.reference\);/);
  assert.match(page, /const requestedRoute = reference \? params\.reference! : params\.view;/);
  for (const label of ["早起", "阅读", "运动", "喝水", "早睡"]) {
    assert.match(page, new RegExp(`label: "${label}"`), label);
  }

  assert.match(source, /onClick=\{\(\) => void toggleHabit\(card, index\)\}/);
  assert.match(source, /const saved = await checkins\.create\(\{ habitId: habit\.id, localDate: today \}\);/);
  assert.match(source, /const recentCheckins = useMemo/);
  assert.match(source, /function removeCheckin\(checkin: HabitCheckin\)/);
  assert.match(source, /已删除\$\{label\}的打卡记录。/);
  assert.match(source, /最近打卡/);
  assert.match(source, /<DeleteRecordButton disabled=\{checkins\.saving\} onDelete=\{\(\) => void removeCheckin\(checkin\)\} \/>/);

  assert.match(source, /onClick=\{\(\) => chooseType\("expense"\)\}/);
  assert.match(source, /onClick=\{\(\) => chooseType\("income"\)\}/);
  assert.match(source, /onClick=\{\(\) => void addRecord\(\)\}/);
  assert.match(source, /const saved = editingId \? await ledger\.update\(editingId, payload\) : await ledger\.create\(payload\);/);
  assert.match(source, /function startEditing\(record: LedgerRecord\)/);
  assert.match(source, /<EditRecordButton disabled=\{ledger\.saving\} onEdit=\{\(\) => startEditing\(record\)\} \/>/);

  for (const resourceModule of ["exercise", "weight", "food"]) {
    assert.match(source, new RegExp(`onClick=\\{\\(\\) => selectModule\\("${resourceModule}"\\)\\}`), resourceModule);
  }
  assert.match(source, /onClick=\{openPhotoPicker\}/);
  assert.match(source, /photoInputRef\.current\?\.click\(\);/);
  assert.match(source, /onClick=\{\(\) => void addFoodRecord\(\)\}/);
  assert.match(source, /const saved = foodEditing \? await foodRecords\.update\(foodEditing\.id, payload\) : await foodRecords\.create\(payload\);/);
  assert.match(source, /function startEditingFood\(record: FoodRecord\)/);
  assert.match(source, /onClick=\{\(\) => void addExerciseRecord\(\)\}/);
  assert.match(source, /\? await exerciseRecords\.update\(exerciseEditing\.id, payload\)\s+: await exerciseRecords\.create\(payload\);/);
  assert.match(source, /function startEditingExercise\(record: ExerciseRecord\)/);
  assert.match(source, /onClick=\{\(\) => void addWeightRecord\(\)\}/);
  assert.match(source, /const saved = weightEditing \? await weightRecords\.update\(weightEditing\.id, payload\) : await weightRecords\.create\(payload\);/);
  assert.match(source, /function startEditingWeight\(record: WeightRecord\)/);

  assert.match(source, /onClick=\{\(\) => void addPeriodRecord\(\)\}/);
  assert.match(source, /const saved = editingId \? await periods\.update\(editingId, payload\) : await periods\.create\(payload\);/);
  assert.match(source, /<EditRecordButton disabled=\{periods\.saving\} onEdit=\{\(\) => startEditing\(record\)\} \/>/);

  assert.match(source, /onClick=\{\(\) => void action\(\)\}/);
  assert.match(source, /const action = route === "schedule"/);
  assert.match(source, /const saved = editingRecordId \? await schedule\.update\(editingRecordId, payload\) : await schedule\.create\(payload\);/);
  assert.match(source, /const saved = editingRecordId \? await anniversaries\.update\(editingRecordId, payload\) : await anniversaries\.create\(payload\);/);
  assert.match(source, /const saved = editingRecordId \? await diary\.update\(editingRecordId, payload\) : await diary\.create\(payload\);/);
  assert.match(source, /const saved = editingRecordId \? await savingsGoals\.update\(editingRecordId, payload\) : await savingsGoals\.create\(payload\);/);
  assert.match(source, /function startEditingPrimary\(record: TenantRecord\)/);
  assert.match(source, /onClick=\{\(\) => void submitSavingsTransaction\(\)\}/);
  assert.match(source, /\? await savingsTransactions\.update\(editingRecordId, payload\)\s+: await savingsTransactions\.create\(payload\);/);
  assert.match(source, /function startEditingTransaction\(record: SavingsTransactionRecord\)/);
});

test("period record control immediately acknowledges pending and failed saves", async () => {
  const source = await readFile(lifecycleSource, "utf8");

  assert.match(source, /setFeedback\("正在保存经期记录…"\);/);
  assert.match(source, /setFeedback\("未能保存经期记录，请查看上方状态提示后重试。"\);/);
  assert.match(source, /经期记录已保存，历史记录已更新。/);
  assert.match(source, /经期记录已修改，历史记录已更新。/);
  assert.doesNotMatch(source, /if \(periods\.authRequired\)/);
  assert.doesNotMatch(source, /if \(periods\.consentRequired\)/);
});

test("todo uses a browser-valid date pattern and the shared account-scoped persistence client", async () => {
  const source = await readFile(todoSource, "utf8");
  const cacheSource = await readFile("app/_components/workbench/local-record-cache.ts", "utf8");

  assert.match(source, /placeholder="YYYY-MM-DD"/);
  assert.match(source, /pattern="\[0-9\]\{4\}-\[0-9\]\{2\}-\[0-9\]\{2\}"/);
  assert.match(source, /useTenantResource<TodoRecord>\("todos"\)/);
  assert.match(source, /await todos\.update\(editingId, payload\)/);
  assert.match(source, /async function toggleTodo\(todo: TodoRecord\)/);
  assert.match(source, /await todos\.destroy\(todo\.id\)/);
  assert.match(source, /isDeviceLocalRecord/);
  assert.match(source, /ResourceStatus/);
  assert.match(cacheSource, /const OUTBOX_STORE = "outbox"/);
  assert.match(cacheSource, /const DATABASE_VERSION = 3/);
  assert.match(cacheSource, /const RECORD_ALIAS_STORE = "record-aliases"/);
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

  assert.match(source, /await firstScopeReady\.promise/);
  assert.match(source, /initialization\.finally\(firstScopeReady\.resolve\)/);
  assert.match(source, /resolveBrowserRecordScope/);
  assert.match(source, /writeDeviceLocalRecord/);
  assert.match(source, /sensitive && cloudAvailabilityRef\.current !== "available"/);
  assert.match(source, /removeDeviceLocalRecord/);
  assert.match(cacheSource, /account:\$\{suffix\}/);
  assert.match(cacheSource, /Guest records[\s\S]*never auto-synced/);
  assert.match(cacheSource, /tenantFieldNames/);
});

test("tenant resource client updates only the current account's local row or verified cloud row", async () => {
  const source = await readFile(resourceSource, "utf8");

  assert.match(source, /update: \(id: string, payload: Record<string, unknown>, idempotencyKey\?: string\) => Promise<T \| null>;/);
  assert.match(source, /const local = localRecordsRef\.current\.find\(\(record\) => record\.id === id\);/);
  assert.match(source, /if \(local && isDeviceLocalRecord\(local\)\)/);
  assert.match(source, /await writeDeviceLocalRecord\(scope, resource, updatedLocal\);/);
  assert.match(source, /method: "PATCH"/);
  assert.match(source, /`\/api\/mydairy\/\$\{resource\}\/\$\{encodeURIComponent\(id\)\}`/);
  assert.match(source, /A missing consent never sends a PATCH body to the server/);
});

test("sensitive record saves preflight the read-only consent state before falling back to this device", async () => {
  const source = await readFile(resourceSource, "utf8");
  const createStart = source.indexOf("const create = useCallback");
  const preflight = source.indexOf('if (sensitive && cloudAvailabilityRef.current === "unknown")', createStart);
  const localWrite = source.indexOf("await writeDeviceLocalRecord", createStart);

  assert.ok(createStart >= 0);
  assert.ok(preflight > createStart);
  assert.ok(localWrite > preflight);
  assert.match(source.slice(preflight, localWrite), /await reload\(\);/);
  assert.match(source.slice(preflight, localWrite), /const preflightScope = await refreshCurrentScope\(\);/);
  assert.match(source, /server still rejects any non-consented cloud path before body parsing/);
});

test("tenant resource client refreshes an account scope before merging or mutating cross-device history", async () => {
  const source = await readFile(resourceSource, "utf8");

  assert.match(source, /const scopeRefreshRef = useRef<Promise<string \| null> \| null>\(null\);/);
  assert.match(source, /const refreshCurrentScope = useCallback\(async \(forceSessionRefresh = false\): Promise<string \| null> => \{/);
  assert.match(source, /if \(forceSessionRefresh\) invalidateBrowserRecordScope\(\);/);
  assert.match(source, /if \(nextScope === scopeRef\.current\) return nextScope;/);
  assert.match(source, /commitRecords\(\[\]\);/);
  assert.match(source, /local = \(await readDeviceLocalRecords\(nextScope, resource\)\) as T\[\];/);
  assert.match(source, /const responseScope = await refreshCurrentScope\(\);/);
  assert.match(source, /if \(responseScope !== requestScope\) \{/);
  assert.match(source, /const reconciledScope = await refreshCurrentScope\(\);/);
  assert.match(source, /if \(reconciledScope !== requestScope\) \{/);
  assert.match(source, /async \(remote: T\[\], expectedScope: string\): Promise<T\[]>/);
  assert.match(source, /scope === "guest" \|\| \(sensitive && cloudAvailabilityRef\.current !== "available"\)/);
  assert.match(source, /const scopeBeforeReplay = await refreshCurrentScope\(\);/);
  assert.match(source, /const scopeAfterReplay = await refreshCurrentScope\(\);/);
  assert.match(source, /const scopeBeforeRequest = await refreshCurrentScope\(\);/);
  assert.match(source, /if \(scopeBeforeRequest !== scope\) \{/);
  assert.match(source, /window\.addEventListener\("focus", refreshWhenVisible\);/);
  assert.match(source, /const refreshWhenVisible = \(\) => void reload\(true\);/);
  assert.match(source, /window\.addEventListener\("pageshow", refreshWhenPageShows\);/);
  assert.match(source, /const refreshWhenPageShows = \(\) => void reload\(true\);/);
  assert.match(source, /document\.visibilityState === "visible"\) void reload\(true\);/);
  assert.match(source, /document\.addEventListener\("visibilitychange", refreshWhenDocumentVisible\);/);
});

test("tenant resource replays only same-account local records, and sensitive records only after a current consented read", async () => {
  const [source, cacheSource, account] = await Promise.all([
    readFile(resourceSource, "utf8"),
    readFile("app/_components/workbench/local-record-cache.ts", "utf8"),
    readFile(accountSource, "utf8"),
  ]);

  assert.match(source, /appendDeviceOutbox/);
  assert.match(source, /Before account-scoped IndexedDB existed/);
  assert.match(source, /if \(scope === "guest"\)/);
  assert.match(source, /const legacyActions = readOutbox\(storage\) as DeviceOutboxAction\[\];/);
  assert.match(source, /deriveDeviceOutboxParentReferences/);
  assert.match(source, /resolveDeviceOutboxAction/);
  assert.match(source, /rememberDeviceOutboxRecordAlias/);
  assert.match(source, /readDeviceOutbox/);
  assert.match(source, /removeDeviceOutboxActions/);
  assert.match(source, /replayOutboxQueue/);
  assert.match(source, /scope === "guest"/);
  assert.match(source, /if \(sensitive\) return false;/);
  assert.match(source, /requiresSensitiveConsent: true as const/);
  assert.match(source, /cloudAvailabilityRef\.current !== "available"/);
  assert.match(source, /createDeviceLocalRecoveryOutboxAction/);
  assert.match(source, /Before consent-pending replay existed/);
  assert.match(source, /allActions = await appendDeviceOutbox\(scope, recoveryAction\);/);
  assert.match(source, /const queuedForReplay = await queueDeviceMutation\(deviceOutboxAction\);/);
  assert.match(source, /mydairy:privacy-consent-accepted/);
  assert.match(source, /accountReturnPathFromLocation/);
  assert.match(source, /return_to=/);
  assert.match(source, /window\.addEventListener\("online", replayWhenOnline\)/);
  assert.match(source, /开启敏感跨设备保存后会自动同步这条记录。/);
  assert.match(source, /使用 Google 登录无需额外验证邮箱。/);
  assert.match(cacheSource, /export async function removeDeviceOutboxActions/);
  assert.match(cacheSource, /export async function resolveDeviceOutboxAction/);
  assert.match(cacheSource, /export async function rememberDeviceOutboxRecordAlias/);
  assert.match(cacheSource, /export function createDeviceLocalRecoveryOutboxAction/);
  assert.match(cacheSource, /export function deviceLocalRecordRequestPayload/);
  assert.match(cacheSource, /DEVICE_OUTBOX_FALLBACK_PREFIX/);
  assert.match(cacheSource, /const existing = await requestValue\(store\.get\(key\)\);/);
  assert.match(account, /window\.dispatchEvent\(new Event\("mydairy:privacy-consent-accepted"\)\);/);
  assert.match(account, /safeAccountReturnPath/);
  assert.match(account, /正在返回原页面同步你的历史记录…/);
  assert.match(account, /window\.location\.assign\(returnTo\)/);
  assert.match(account, /本设备当前账号暂存的敏感记录会自动同步。/);
});

test("dependent local mutations resolve a same-account parent alias before an immediate cloud request", async () => {
  const source = await readFile(resourceSource, "utf8");
  const cacheSource = await readFile("app/_components/workbench/local-record-cache.ts", "utf8");
  const deriveStart = cacheSource.indexOf("export function deriveDeviceOutboxParentReferences");
  const deriveEnd = cacheSource.indexOf("async function readDeviceRecordAlias", deriveStart);
  const createStart = source.indexOf("const create = useCallback");
  const resolveStart = source.indexOf("const resolvedAction = await resolveDeviceOutboxAction(scope, deviceOutboxAction);", createStart);
  const fetchStart = source.indexOf("const response = await fetch", resolveStart);

  assert.ok(deriveStart >= 0);
  assert.ok(deriveEnd > deriveStart);
  assert.match(cacheSource.slice(deriveStart, deriveEnd), /localRecordId\.startsWith\("local_"\)/);
  assert.match(cacheSource.slice(deriveStart, deriveEnd), /return \[reference\];/);
  assert.match(source, /const parentReferences = deriveDeviceOutboxParentReferences\(resource, payload\);/);
  assert.ok(resolveStart > createStart);
  assert.ok(fetchStart > resolveStart);
  assert.match(source.slice(resolveStart, fetchStart), /if \(!resolvedAction\)[\s\S]*queueDeviceMutation\(deviceOutboxAction\)/);
  assert.match(source.slice(fetchStart, fetchStart + 500), /body: JSON\.stringify\(resolvedAction\.payload\)/);
  assert.match(source, /正在等待关联记录同步，完成后会自动同步。/);
});

test("todo replay is isolated by the shared resource client", async () => {
  const [todo, resource] = await Promise.all([
    readFile(todoSource, "utf8"),
    readFile(resourceSource, "utf8"),
  ]);

  assert.match(todo, /useTenantResource<TodoRecord>\("todos"\)/);
  assert.match(resource, /function actionTargetsResource\(action: DeviceOutboxAction, resource: string\)/);
  assert.match(resource, /\.filter\(\(action\) => actionTargetsResource\(action, resource\)\)/);
  assert.match(resource, /removeDeviceOutboxActions\(scope, acknowledged\)/);
  assert.doesNotMatch(todo, /writeDeviceOutbox\(scope, replayResult\.remaining\)/);
});
