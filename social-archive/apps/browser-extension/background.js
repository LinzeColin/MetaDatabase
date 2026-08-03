/* global SA */
importScripts("shared.js", "content/account-mirror-core.js");

const MENU_SAVE = "social-archive-save-page";
const MENU_SELECTION = "social-archive-save-selection";
const PWA_BRIDGE_URL_PATTERNS = [
  "https://social-archive.linzezhang.com/*",
  "http://127.0.0.1:8765/*",
  "http://localhost:8765/*"
];

async function ensureMenus() {
  await chrome.contextMenus.removeAll();
  chrome.contextMenus.create({ id: MENU_SAVE, title: "保存到我的档案馆", contexts: ["page", "link", "image", "video"] });
  chrome.contextMenus.create({ id: MENU_SELECTION, title: "保存选中文本到我的档案馆", contexts: ["selection"] });
}

async function injectExtractor(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content/extract-core.js", "content/extract.js"] });
}

async function reconnectOpenPwaBridgeTabs() {
  const tabs = await chrome.tabs.query({ url: PWA_BRIDGE_URL_PATTERNS }).catch(() => []);
  const completeTabs = tabs.filter(tab => typeof tab?.id === "number" && tab.status === "complete");
  await Promise.all(completeTabs.map(tab =>
    chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["bridge.js"] }).catch(() => null)
  ));
  return { found: tabs.length, injected: completeTabs.length };
}

async function extractFromTab(tab, mode) {
  await injectExtractor(tab.id);
  const response = await chrome.tabs.sendMessage(tab.id, { type: "SA_EXTRACT", mode });
  if (!response?.ok) throw new Error(response?.error || "页面结构已变化，暂时无法读取");
  return response;
}

function serverDestinations(config) {
  const ids = config.destinationIds || ["social_archive"];
  return config.obsidianLocalEnabled ? ids.filter(id => id !== "obsidian") : ids;
}

function buildCaptureBody(record, tabUrl, config, overrides = {}) {
  const platform = SA.platformFromUrl(record.url || tabUrl);
  return {
    platform: platform.id,
    url: record.url || tabUrl,
    relation_type: overrides.relationType || config.relationType || "saved",
    collection_key: overrides.collectionKey ?? config.collectionKey ?? "",
    title: record.title || null,
    author_name: record.author_name || null,
    text: record.text || null,
    published_at: record.published_at || null,
    media_urls: (record.media_urls || []).filter(url => /^https?:/i.test(url)).slice(0, 100),
    raw_metadata: { ...(record.raw_metadata || {}), capture_source: overrides.source || "toolbar" },
    requested_levels: ["L0", "L1", "L3"],
    destination_ids: overrides.destinationIds || serverDestinations(config)
  };
}

function safeFileSegment(value, fallback) {
  const text = String(value || fallback || "未命名").normalize("NFKC").replace(/[\\/:*?"<>|\u0000-\u001f]/g, " ").replace(/\s+/g, " ").trim();
  return (text || fallback || "未命名").slice(0, 120);
}

async function exportLocalObsidian(response, record, config) {
  if (!config.obsidianLocalEnabled || !config.destinationIds.includes("obsidian")) return { status: "not_selected" };
  if (!config.obsidianLocalToken) return { status: "needs_user_action", error: "Obsidian 令牌缺失" };
  const markdown = await SA.apiText(`/v1/library/${encodeURIComponent(response.content_id)}/markdown`, { timeoutMs: 15000 });
  const platform = SA.platformFromUrl(record.url || "").id;
  const path = `Social Archive/${safeFileSegment(platform, "web")}/${safeFileSegment(record.title, response.content_id)}-${response.content_id.slice(-8)}.md`;
  const result = await fetch(`${config.obsidianLocalUrl.replace(/\/$/, "")}/vault`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${config.obsidianLocalToken}`,
      "Content-Type": "text/markdown; charset=utf-8",
      "X-Social-Archive-Path": encodeURIComponent(path)
    },
    body: markdown
  });
  if (!result.ok) throw new Error(`Obsidian HTTP ${result.status}`);
  return { status: "done", path };
}

async function captureRecord(record, tabUrl, config, overrides = {}) {
  const body = buildCaptureBody(record, tabUrl, config, overrides);
  const response = await SA.api("/v1/captures", { method: "POST", body: JSON.stringify(body), timeoutMs: 30000 });
  try {
    response.local_obsidian = await exportLocalObsidian(response, record, config);
  } catch (error) {
    response.local_obsidian = { status: "needs_user_action", error: error?.message || "Obsidian 写入失败" };
  }
  return response;
}

async function captureActive(message = {}, sourceTab = null) {
  const tab = sourceTab?.id && sourceTab?.url ? sourceTab : await SA.activeTab();
  const config = await SA.getConfig();
  const extracted = await extractFromTab(tab, message.mode === "list" ? "list" : "page");
  const items = message.mode === "list" ? extracted.items : [extracted.page];
  if (message.mode === "list") {
    for (const item of items) {
      item.raw_metadata = {
        ...(item.raw_metadata || {}),
        scan_completeness: extracted.completeness || "partial",
        scan_context: extracted.scan_context || { mode: "visible_only", no_autoscroll: true }
      };
    }
  }
  if (!items.length) return { ok: false, state: "needs_user_action", error: "当前可见区域没有可读取的内容" };
  let saved = [];
  const failed = [];
  const localDestinationErrors = [];
  if (message.mode === "list") {
    try {
      const batch = await SA.api("/v1/captures/batch", {
        method: "POST",
        body: JSON.stringify({ items: items.map(item => buildCaptureBody(item, tab.url, config, message)) }),
        timeoutMs: 60000
      });
      saved = batch.items || [];
      for (const error of batch.errors || []) failed.push(error.detail || "保存失败");
      if (config.obsidianLocalEnabled && config.destinationIds.includes("obsidian")) {
        for (let index = 0; index < saved.length; index += 1) {
          try { saved[index].local_obsidian = await exportLocalObsidian(saved[index], items[index] || {}, config); }
          catch (error) { localDestinationErrors.push(error?.message || "Obsidian 写入失败"); }
        }
      }
    } catch (error) {
      failed.push(error?.message || "批量保存失败");
    }
  } else {
    try { saved.push(await captureRecord(items[0], tab.url, config, message)); }
    catch (error) { failed.push(error?.message || "保存失败"); }
  }
  if (!saved.length) return { ok: false, state: "needs_user_action", error: failed[0] || "保存失败" };
  await chrome.action.setBadgeBackgroundColor({ color: localDestinationErrors.length ? "#9a6700" : "#1f7a4c" });
  await chrome.action.setBadgeText({ text: String(saved.length) });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2500);
  return {
    ok: true,
    savedCount: saved.length,
    failedCount: failed.length,
    destinationWarningCount: localDestinationErrors.length,
    destinationWarnings: localDestinationErrors,
    jobIds: saved.flatMap(item => item.job_ids || []),
    detailUrls: saved.map(item => item.detail_url)
  };
}

async function injectFabIfAuthorized(tabId, url) {
  if (!/^https?:/i.test(url || "")) return;
  const config = await SA.getConfig();
  if (!config.showFloatingButton) return;
  const platform = SA.platformFromUrl(url);
  if (platform.id === "generic-web") return;
  const state = await SA.permissionState(platform.id);
  if (!state.authorized) return;
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content/fab.js"] }).catch(() => {});
}


const PENDING_CONNECTIONS_KEY = "saPendingAccountConnections";
const SYNC_QUEUE_KEY = "saAccountSyncQueue";
const SYNC_QUEUE_LOCK_KEY = "saAccountSyncQueueLock";
// A live sync refreshes its lock on every batch, so anything older than this
// belongs to a worker MV3 has already terminated.
const SYNC_QUEUE_LOCK_STALE_MS = 3 * 60 * 1000;

async function refreshSyncQueueLock() {
  const stored = await chrome.storage.local.get({ [SYNC_QUEUE_LOCK_KEY]: null });
  const lock = stored[SYNC_QUEUE_LOCK_KEY];
  if (lock) await chrome.storage.local.set({ [SYNC_QUEUE_LOCK_KEY]: { ...lock, heartbeatAt: Date.now() } });
}

// A lock can only be held by the running worker. If this file is evaluating,
// any lock in storage was left by a worker that is already gone.
chrome.storage.local.remove(SYNC_QUEUE_LOCK_KEY).catch(() => {});
const SYNC_QUEUE_LAST_RESULT_KEY = "saAccountSyncQueueLastResult";
const SYNC_CONTROL_KEY = "saSyncRunControls";
const SYNC_QUEUE_ALARM = "sa-account-sync-queue";
const MIRROR_TAB_PREFIX = "saMirrorTab:";
const ACTIVE_SYNC_STATES = new Set(["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"]);

async function getPendingConnections() {
  const stored = await chrome.storage.local.get({ [PENDING_CONNECTIONS_KEY]: {} });
  return stored[PENDING_CONNECTIONS_KEY] || {};
}

async function setPendingConnection(platform, value) {
  const pending = await getPendingConnections();
  if (value) pending[platform] = value;
  else delete pending[platform];
  await chrome.storage.local.set({ [PENDING_CONNECTIONS_KEY]: pending });
}


async function getSyncQueue() {
  const stored = await chrome.storage.local.get({ [SYNC_QUEUE_KEY]: [] });
  return Array.isArray(stored[SYNC_QUEUE_KEY]) ? stored[SYNC_QUEUE_KEY] : [];
}

async function setSyncQueue(items) {
  await chrome.storage.local.set({ [SYNC_QUEUE_KEY]: items });
}

async function getSyncControls() {
  const stored = await chrome.storage.local.get({ [SYNC_CONTROL_KEY]: {} });
  return stored[SYNC_CONTROL_KEY] || {};
}

async function setSyncControl(syncRunId, action = null) {
  if (!syncRunId) return;
  const controls = await getSyncControls();
  if (action) controls[syncRunId] = { action, updatedAt: Date.now() };
  else delete controls[syncRunId];
  await chrome.storage.local.set({ [SYNC_CONTROL_KEY]: controls });
}

async function getSyncControl(syncRunId) {
  if (!syncRunId) return null;
  const controls = await getSyncControls();
  return controls[syncRunId] || null;
}

async function removeQueuedSync({ syncRunId = null, accountId = null } = {}) {
  const queue = await getSyncQueue();
  const kept = queue.filter(item => {
    if (syncRunId && item.syncRunId === syncRunId) return false;
    if (accountId && item.accountId === accountId) return false;
    return true;
  });
  if (kept.length !== queue.length) await setSyncQueue(kept);
  return queue.length - kept.length;
}

async function broadcastMirrorControl(syncRunId, action) {
  const tabs = await chrome.tabs.query({}).catch(() => []);
  await Promise.all(tabs.filter(tab => tab.id).map(tab =>
    chrome.tabs.sendMessage(tab.id, { type: "SA_MIRROR_CONTROL", syncRunId, action }).catch(() => null)
  ));
}

async function stopStateFor(syncRunId) {
  const local = await getSyncControl(syncRunId);
  if (local?.action === "pause" || local?.action === "cancel") return local.action;
  if (!syncRunId) return null;
  const run = await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}`, { timeoutMs: 8000 }).catch(() => null);
  if (run?.status === "paused") return "pause";
  if (run?.status === "cancelled") return "cancel";
  return null;
}

async function controlSyncRun({ syncRunId, accountId = null, action }) {
  const allowed = new Set(["pause", "resume", "cancel", "retry"]);
  if (!syncRunId || !allowed.has(action)) throw new Error("同步控制参数无效");
  const before = await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}`, { timeoutMs: 10000 });
  const effectiveAccountId = accountId || before.source_account_id;
  const result = await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}/control`, {
    method: "POST",
    body: JSON.stringify({ action }),
    timeoutMs: 15000
  });

  if (action === "pause" || action === "cancel") {
    await setSyncControl(syncRunId, action);
    await removeQueuedSync({ syncRunId, accountId: effectiveAccountId });
    await broadcastMirrorControl(syncRunId, action);
  } else {
    await setSyncControl(syncRunId, null);
    await broadcastMirrorControl(syncRunId, "clear");
    await enqueueAccountSync({
      accountId: effectiveAccountId,
      syncRunId,
      triggerType: action === "retry" ? "retry" : "resume"
    });
  }

  const messages = {
    pause: "同步已暂停，已完成内容不会丢失",
    resume: "同步已恢复并重新加入后台队列",
    cancel: "同步已取消，已完成内容仍保留在资料库",
    retry: "同步已重新加入后台队列"
  };
  return { ok: true, ...result, accountId: effectiveAccountId, message: messages[action] };
}

async function scheduleSyncQueue(delayInMinutes = 0.5) {
  await chrome.alarms.create(SYNC_QUEUE_ALARM, { delayInMinutes: Math.max(0.5, Number(delayInMinutes || 0.5)) });
}

async function enqueueAccountSync({ accountId, syncRunId = null, tabId = null, profileUrl = "", triggerType = "manual" }) {
  if (!accountId) throw new Error("账号不存在");
  const active = (await listSyncRuns()).find(run => run.source_account_id === accountId && ACTIVE_SYNC_STATES.has(run.status));
  if (active && (!syncRunId || active.id !== syncRunId)) {
    return { ok: true, state: "already_running", accountId, syncRunId: active.id, message: "该账号已经在同步" };
  }
  const queue = await getSyncQueue();
  const existing = queue.find(item => item.accountId === accountId);
  if (existing) {
    existing.syncRunId = existing.syncRunId || syncRunId;
    existing.tabId = existing.tabId || tabId;
    existing.profileUrl = existing.profileUrl || profileUrl;
    existing.triggerType = triggerType || existing.triggerType;
    existing.updatedAt = Date.now();
  } else {
    queue.push({ accountId, syncRunId, tabId, profileUrl, triggerType, enqueuedAt: Date.now(), updatedAt: Date.now() });
  }
  await setSyncQueue(queue);
  await scheduleSyncQueue();
  return { ok: true, state: "queued", accountId, syncRunId, queuedCount: queue.length, message: "同步已加入后台队列" };
}

async function enqueueAllAccounts(triggerType = "manual") {
  const accounts = (await listAccounts()).filter(item => ["connected", "degraded"].includes(item.connection_state));
  const results = [];
  for (const account of accounts) {
    try { results.push(await enqueueAccountSync({ accountId: account.id, triggerType })); }
    catch (error) { results.push({ ok: false, accountId: account.id, error: error?.message || "加入同步队列失败" }); }
  }
  return { ok: results.some(item => item.ok), state: "queued", queuedCount: results.filter(item => item.ok).length, results };
}

async function processSyncQueue() {
  const stored = await chrome.storage.local.get({ [SYNC_QUEUE_LOCK_KEY]: null });
  const lock = stored[SYNC_QUEUE_LOCK_KEY];
  // The lock is released in a finally, but MV3 terminates the service worker at
  // will, and a worker killed mid-sync never runs it. The lock then survived in
  // storage for two hours while every later click returned "busy" and did
  // nothing, with enqueue still reporting ok, so the UI showed no error and the
  // sync counters sat at zero. A lock is only meaningful while the worker that
  // took it is alive, so heartbeatAt has to be recent, not merely startedAt.
  const heldFor = Date.now() - Number(lock?.heartbeatAt || lock?.startedAt || 0);
  if (lock && heldFor < SYNC_QUEUE_LOCK_STALE_MS) {
    await scheduleSyncQueue();
    return { ok: true, state: "busy" };
  }
  if (lock) await chrome.storage.local.remove(SYNC_QUEUE_LOCK_KEY);
  const queue = await getSyncQueue();
  const item = queue.shift();
  if (!item) return { ok: true, state: "empty" };
  await setSyncQueue(queue);
  const queuedControl = await getSyncControl(item.syncRunId);
  if (queuedControl?.action === "pause" || queuedControl?.action === "cancel") {
    if (queue.length) await scheduleSyncQueue();
    return { ok: true, state: queuedControl.action === "pause" ? "paused" : "cancelled", syncRunId: item.syncRunId };
  }
  await chrome.storage.local.set({ [SYNC_QUEUE_LOCK_KEY]: { accountId: item.accountId, startedAt: Date.now(), heartbeatAt: Date.now() } });
  let result;
  try {
    result = await syncAccountById(item.accountId, item);
    await chrome.storage.local.set({ [SYNC_QUEUE_LAST_RESULT_KEY]: { ...result, accountId: item.accountId, finishedAt: Date.now() } });
  } catch (error) {
    result = { ok: false, accountId: item.accountId, error: error?.message || "同步失败", finishedAt: Date.now() };
    await chrome.storage.local.set({ [SYNC_QUEUE_LAST_RESULT_KEY]: result });
  } finally {
    await chrome.storage.local.remove(SYNC_QUEUE_LOCK_KEY);
    if ((await getSyncQueue()).length) await scheduleSyncQueue();
  }
  return result;
}

async function listAccounts() {
  const response = await SA.api("/v1/accounts", { timeoutMs: 10000 });
  return response.items || [];
}

async function listSyncRuns() {
  const response = await SA.api("/v1/sync-runs?limit=200", { timeoutMs: 10000 });
  return response.items || [];
}

function platformSpec(platform) {
  return globalThis.SAMirrorCore?.PLATFORM_SPECS?.[platform] || null;
}

async function waitForTabComplete(tabId, timeoutMs = 45000) {
  const current = await chrome.tabs.get(tabId).catch(() => null);
  if (current?.status === "complete") return current;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("平台页面加载超时"));
    }, timeoutMs);
    function listener(updatedId, changeInfo, tab) {
      if (updatedId !== tabId || changeInfo.status !== "complete") return;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve(tab);
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function ensureAccountMirrorScripts(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content/account-mirror-core.js", "content/account-mirror.js"]
  }).catch(() => {});
}

async function findExistingPlatformTab(platform, preferredTabId = null) {
  const patterns = SA.patternsForPlatform(platform);
  if (!patterns.length) return null;
  const tabs = await chrome.tabs.query({ url: patterns }).catch(() => []);
  const select = globalThis.SAMirrorCore?.preferExistingPlatformTab;
  if (typeof select === "function") return select(tabs, preferredTabId);
  return tabs.find(tab => String(tab?.id) === String(preferredTabId)) || tabs.find(tab => tab?.active) || tabs[0] || null;
}

async function sendSyncBatch(syncRunId, body) {
  // Every batch proves the worker is still alive, which is what keeps a long
  // scan from having its own lock treated as abandoned.
  await refreshSyncQueueLock();
  return SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}/batches`, {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: 90000
  });
}

async function syncChromeBookmarks({ accountId = null, syncRunId = null, triggerType = "manual" } = {}) {
  const hasPermission = await chrome.permissions.contains({ permissions: ["bookmarks"] });
  if (!hasPermission) throw new Error("请先授权读取 Chrome 书签");
  let account = null;
  if (accountId) account = (await listAccounts()).find(item => item.id === accountId) || null;
  if (!account) account = (await listAccounts()).find(item => item.platform === "generic-web" && item.external_account_id === "chrome-bookmarks") || null;
  if (!account) throw new Error("Chrome 书签账号尚未连接");
  if (!syncRunId) {
    const started = await SA.api(`/v1/accounts/${encodeURIComponent(account.id)}/sync`, {
      method: "POST",
      body: JSON.stringify({ mode: account.last_sync_at ? "incremental" : "first_full", relation_types: ["bookmark"], trigger_type: triggerType }),
      timeoutMs: 15000
    });
    syncRunId = started.sync_run_id;
  }
  const tree = await chrome.bookmarks.getTree();
  const config = await SA.getConfig();
  const records = SAMirrorCore.flattenBookmarksTree(tree).map(item => ({
    ...item,
    destination_ids: serverDestinations(config)
  }));
  const chunks = SAMirrorCore.chunk(records, 200);
  for (let index = 0; index < chunks.length; index += 1) {
    const control = await stopStateFor(syncRunId);
    if (control) return { ok: true, accountId: account.id, syncRunId, status: control === "pause" ? "paused" : "cancelled", controlled: true };
    await sendSyncBatch(syncRunId, {
      relation_type: "bookmark",
      scope_type: "collection",
      collection_key: "",
      items: chunks[index],
      completeness: "partial",
      batch_index: index,
      batch_count: chunks.length || 1,
      has_more: index < chunks.length - 1,
      cursor: { source: "chrome.bookmarks", batch_index: index, total_items: records.length }
    });
    await chrome.action.setBadgeBackgroundColor({ color: "#171717" });
    await chrome.action.setBadgeText({ text: `${Math.min(records.length, (index + 1) * 200)}`.slice(-4) });
  }
  const finalControl = await stopStateFor(syncRunId);
  if (finalControl) return { ok: true, accountId: account.id, syncRunId, status: finalControl === "pause" ? "paused" : "cancelled", controlled: true };
  const result = await sendSyncBatch(syncRunId, {
    relation_type: "bookmark",
    scope_type: "relation",
    items: [],
    completeness: "complete",
    batch_index: chunks.length,
    batch_count: chunks.length + 1,
    has_more: false,
    cursor: { source: "chrome.bookmarks", total_items: records.length }
  });
  await chrome.action.setBadgeBackgroundColor({ color: "#1f7a4c" });
  await chrome.action.setBadgeText({ text: "✓" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2500);
  return { ok: true, accountId: account.id, syncRunId, imported: records.length, status: result.status };
}

async function connectChromeBookmarks() {
  const granted = await chrome.permissions.request({ permissions: ["bookmarks"] });
  if (!granted) return { ok: false, state: "unauthorized", error: "你没有授权读取 Chrome 书签" };
  const existing = (await listAccounts()).find(item => item.platform === "generic-web" && item.external_account_id === "chrome-bookmarks");
  if (existing) {
    const queued = await enqueueAccountSync({ accountId: existing.id, triggerType: "manual" });
    return { ...queued, state: "connected", message: "Chrome 书签已连接，首次全量同步已进入后台队列" };
  }
  const start = await SA.api("/v1/accounts/connect/start", {
    method: "POST",
    body: JSON.stringify({
      platform: "generic-web", auth_method: "chrome_bookmarks", display_name: "Chrome 书签",
      external_account_id: "chrome-bookmarks", auto_sync_enabled: true, sync_interval_minutes: 360,
      relation_types: ["bookmark"]
    })
  });
  const completed = await SA.api("/v1/accounts/connect/generic-web/complete", {
    method: "POST",
    body: JSON.stringify({
      connection_ref: start.connection_ref,
      external_account_id: "chrome-bookmarks",
      display_name: "Chrome 书签",
      verified: true,
      metadata: { auth_method: "chrome_bookmarks", permission: "bookmarks", auto_sync_enabled: true, sync_interval_minutes: 360 }
    })
  });
  const queued = await enqueueAccountSync({
    accountId: completed.account_id,
    syncRunId: completed.first_sync?.sync_run_id || null,
    triggerType: "first_connect"
  });
  return { ...queued, state: "connected", message: "Chrome 书签已连接，首次全量同步已进入后台队列" };
}

async function connectBrowserPlatform(platform) {
  const spec = platformSpec(platform);
  if (!spec) throw new Error("当前平台尚未配置账号镜像入口");
  const granted = await SA.requestPlatformPermission(platform);
  if (!granted) return { ok: false, state: "unauthorized", error: `未获得${spec.label}页面读取权限` };
  // Reuse a tab from the same persistent Chrome profile whenever possible.
  // It avoids opening a second login journey and preserves the owner-selected page context.
  const existingTab = await findExistingPlatformTab(platform);
  const start = await SA.api("/v1/accounts/connect/start", {
    method: "POST",
    body: JSON.stringify({
      platform, auth_method: "browser_session", display_name: `${spec.label}账号`,
      auto_sync_enabled: true, sync_interval_minutes: 360, relation_types: spec.relations
    }),
    timeoutMs: 15000
  });
  const tab = existingTab || await chrome.tabs.create({ url: spec.home, active: true });
  await setPendingConnection(platform, {
    connectionRef: start.connection_ref,
    authMethod: "browser_session",
    createdAt: Date.now(),
    tabId: tab.id,
    relations: spec.relations
  });
  if (existingTab?.id) {
    await chrome.tabs.update(existingTab.id, { active: true });
    await ensureAccountMirrorScripts(existingTab.id);
  }
  return {
    ok: true,
    state: "authorizing",
    platform,
    tabId: tab.id,
    message: existingTab
      ? `已复用当前${spec.label}页面，正在确认登录态并启动首次同步。`
      : `已在当前 Chrome profile 中打开${spec.label}，插件会检测现有登录态。`
  };
}

async function connectPlatform(platform) {
  if (platform === "generic-web" || platform === "chrome-bookmarks") return connectChromeBookmarks();
  return connectBrowserPlatform(platform);
}

function describeScanError(error) {
  if (error instanceof Error) return `${error.name}: ${error.message}`.slice(0, 300);
  if (typeof error === "string") return error.slice(0, 300);
  if (error && typeof error.message === "string" && error.message) return error.message.slice(0, 300);
  try {
    return JSON.stringify(error, (_key, value) => (value instanceof Error ? `${value.name}: ${value.message}` : value)).slice(0, 300);
  } catch (_) {
    return String(error).slice(0, 300);
  }
}

function sameOriginUrl(candidate, reference) {
  try {
    const a = new URL(candidate);
    const b = new URL(reference);
    return a.hostname === b.hostname || a.hostname.endsWith(`.${b.hostname}`) || b.hostname.endsWith(`.${a.hostname}`);
  } catch (_) {
    return false;
  }
}

function resolveRelationUrl(platform, relation, profileUrl = "") {
  const spec = platformSpec(platform);
  let url = spec?.relationUrls?.[relation] || spec?.home;
  // Favorites and likes live as tabs on the owner's own profile for
  // Xiaohongshu, Douyin and Kuaishou, but the spec placeholder carries no user
  // id -- https://www.xiaohongshu.com/user/profile is not anybody's profile.
  // Navigating there lands on a page with no relation tabs at all, so the scan
  // reported RELATION_TAB_NOT_FOUND and imported nothing on every run. The
  // connect flow already stored the real profile URL; prefer it.
  if (profileUrl && spec?.relationUrls?.[relation] && sameOriginUrl(profileUrl, url)) url = profileUrl;
  if (platform === "x" && relation === "like" && /https:\/\/x\.com\/[^/]+/i.test(profileUrl)) url = `${profileUrl.replace(/\/$/, "")}/likes`;
  if (platform === "bilibili" && /space\.bilibili\.com\/\d+/i.test(profileUrl)) {
    const base = profileUrl.match(/https:\/\/space\.bilibili\.com\/\d+/i)?.[0];
    if (relation === "favorite") url = `${base}/favlist`;
    if (relation === "like") url = base;
  }
  return url;
}

async function navigateMirrorTab(tabId, url) {
  await chrome.tabs.update(tabId, { url, active: true });
  await waitForTabComplete(tabId);
  await ensureAccountMirrorScripts(tabId);
}

async function sendBrowserScopeBatches({ syncRunId, platform, relation, scopeResult, collectionKey = "", collectionName = "" }) {
  const config = await SA.getConfig();
  const items = (scopeResult.items || []).map(item => ({
    ...item,
    platform,
    relation_type: relation,
    collection_key: collectionKey || item.collection_key || "",
    collection_name: collectionName || item.collection_name || collectionKey || "",
    destination_ids: serverDestinations(config)
  }));
  const chunks = SAMirrorCore.chunk(items, 200);
  for (let index = 0; index < chunks.length; index += 1) {
    await sendSyncBatch(syncRunId, {
      relation_type: relation,
      scope_type: "collection",
      collection_key: collectionKey,
      collection_name: collectionName,
      items: chunks[index],
      completeness: "partial",
      batch_index: index,
      batch_count: chunks.length || 1,
      has_more: index < chunks.length - 1,
      cursor: { ...scopeResult.cursor, batch_index: index, collection_key: collectionKey }
    });
  }
  if (collectionKey) {
    await sendSyncBatch(syncRunId, {
      relation_type: relation,
      scope_type: "collection",
      collection_key: collectionKey,
      collection_name: collectionName,
      items: [],
      completeness: scopeResult.completeness === "complete" ? "complete" : "partial",
      batch_index: chunks.length,
      batch_count: chunks.length + 1,
      has_more: false,
      failure_code: scopeResult.failureCode || null,
      cursor: { ...scopeResult.cursor, collection_key: collectionKey }
    });
  }
  return { imported: items.length, chunks: chunks.length, complete: scopeResult.completeness === "complete" };
}

async function scanBrowserScope({ tabId, platform, relation, syncRunId, url, collectionKey = "", collectionName = "", alreadyLoaded = false }) {
  if (!alreadyLoaded) await navigateMirrorTab(tabId, url);
  const result = await chrome.tabs.sendMessage(tabId, {
    type: "SA_MIRROR_SCAN_RELATION",
    syncRunId,
    relationType: relation,
    collectionKey,
    collectionName,
    maxItems: 100000,
    maxScrolls: 1200,
    stableRoundsRequired: 5
  });
  if (result?.controlled) return { controlled: true, status: result.controlAction === "pause" ? "paused" : "cancelled", relation };
  if (!result?.ok) throw new Error(result?.error || "平台列表读取失败");
  const sent = await sendBrowserScopeBatches({ syncRunId, platform, relation, scopeResult: result, collectionKey, collectionName });
  return { ...result, ...sent, collectionKey, collectionName, url };
}

async function scanOneBrowserRelation({ tabId, platform, relation, syncRunId, profileUrl = "" }) {
  const url = resolveRelationUrl(platform, relation, profileUrl);
  if (!url) {
    return sendSyncBatch(syncRunId, {
      relation_type: relation, scope_type: "relation", items: [], completeness: "failed",
      failure_code: "RELATION_URL_UNAVAILABLE", has_more: false
    });
  }
  await navigateMirrorTab(tabId, url);
  const discoveredCollections = await chrome.tabs.sendMessage(tabId, { type: "SA_MIRROR_DISCOVER_COLLECTIONS" })
    .then(result => result?.ok ? (result.items || []) : [])
    .catch(() => []);

  const scopeResults = [];
  const baseResult = await scanBrowserScope({ tabId, platform, relation, syncRunId, url, alreadyLoaded: true });
  if (baseResult?.controlled) return baseResult;
  scopeResults.push(baseResult);

  const seenUrls = new Set([SAMirrorCore.canonicalUrl(url)]);
  for (const collection of discoveredCollections.slice(0, 100)) {
    const collectionUrl = SAMirrorCore.canonicalUrl(collection.url);
    if (!collectionUrl || seenUrls.has(collectionUrl)) continue;
    seenUrls.add(collectionUrl);
    const control = await stopStateFor(syncRunId);
    if (control) return { controlled: true, status: control === "pause" ? "paused" : "cancelled", relation };
    const collectionResult = await scanBrowserScope({
      tabId,
      platform,
      relation,
      syncRunId,
      url: collectionUrl,
      collectionKey: String(collection.collectionKey || collectionUrl).slice(0, 512),
      collectionName: String(collection.collectionName || "未命名收藏夹").slice(0, 256)
    });
    if (collectionResult?.controlled) return collectionResult;
    scopeResults.push(collectionResult);
  }

  const allComplete = scopeResults.length > 0 && scopeResults.every(item => item.completeness === "complete");
  const imported = scopeResults.reduce((sum, item) => sum + Number(item.imported || 0), 0);
  const failureCodes = scopeResults.map(item => item.failureCode).filter(Boolean);
  return sendSyncBatch(syncRunId, {
    relation_type: relation,
    scope_type: "relation",
    items: [],
    completeness: allComplete ? "complete" : "partial",
    batch_index: scopeResults.length,
    batch_count: scopeResults.length + 1,
    has_more: false,
    failure_code: allComplete ? null : (failureCodes[0] || "RELATION_TERMINAL_NOT_PROVEN"),
    cursor: {
      relation_url: url,
      discovered_collections: Math.max(0, scopeResults.length - 1),
      imported_items: imported,
      scope_completion: scopeResults.map(item => ({
        collection_key: item.collectionKey || "",
        complete: item.completeness === "complete",
        reason: item.completionReason || item.failureCode || null,
        observed_count: item.cursor?.observed_count ?? item.imported ?? 0
      }))
    }
  });
}

async function runBrowserAccountSync({ account, syncRunId = null, tabId = null, profileUrl = "", triggerType = "manual" }) {
  const spec = platformSpec(account.platform);
  if (!spec) throw new Error("该平台暂不支持浏览器账号同步");
  if (!syncRunId) {
    const started = await SA.api(`/v1/accounts/${encodeURIComponent(account.id)}/sync`, {
      method: "POST",
      body: JSON.stringify({ mode: account.last_sync_at ? "incremental" : "first_full", relation_types: spec.relations, trigger_type: triggerType }),
      timeoutMs: 15000
    });
    syncRunId = started.sync_run_id;
  }
  let tab = tabId ? await chrome.tabs.get(tabId).catch(() => null) : null;
  if (!tab) tab = await chrome.tabs.create({ url: spec.home, active: true });
  const results = [];
  for (let index = 0; index < spec.relations.length; index += 1) {
    const relation = spec.relations[index];
    try {
      const relationResult = await scanOneBrowserRelation({ tabId: tab.id, platform: account.platform, relation, syncRunId, profileUrl });
      results.push(relationResult);
      if (relationResult?.controlled) break;
    } catch (error) {
      const control = await stopStateFor(syncRunId);
      if (control) {
        results.push({ controlled: true, status: control === "pause" ? "paused" : "cancelled", relation });
        break;
      }
      results.push(await sendSyncBatch(syncRunId, {
        relation_type: relation,
        scope_type: "relation",
        items: [],
        completeness: "failed",
        failure_code: "BROWSER_SCAN_FAILED",
        // String() on a thrown array or plain object yields "[object Object]"
        // repeated, which is exactly what earlier failures recorded and why
        // they could not be diagnosed at all.
        cursor: { error: describeScanError(error) },
        has_more: false
      }));
    }
    await chrome.action.setBadgeBackgroundColor({ color: "#171717" });
    await chrome.action.setBadgeText({ text: `${index + 1}/${spec.relations.length}` });
  }
  const latest = await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}`, { timeoutMs: 10000 });
  await chrome.action.setBadgeBackgroundColor({ color: latest.status === "completed" ? "#1f7a4c" : "#9a6700" });
  await chrome.action.setBadgeText({ text: latest.status === "completed" ? "✓" : "!" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 3000);
  return { ok: true, syncRunId, status: latest.status, results };
}

async function completePendingBrowserConnection(message, senderTab) {
  const platform = message.platform;
  const pending = (await getPendingConnections())[platform];
  if (!pending || !message.loggedIn) return { ok: false, ignored: true };
  if (Date.now() - Number(pending.createdAt || 0) > 30 * 60 * 1000) {
    await setPendingConnection(platform, null);
    return { ok: false, state: "expired", error: "连接流程已过期，请重新点击连接账号" };
  }
  const completed = await SA.api(`/v1/accounts/connect/${encodeURIComponent(platform)}/complete`, {
    method: "POST",
    body: JSON.stringify({
      connection_ref: pending.connectionRef,
      external_account_id: message.externalAccountId || `browser-session:${platform}`,
      display_name: message.accountName || `${platformSpec(platform)?.label || platform}账号`,
      verified: true,
      metadata: {
        auth_method: "browser_session",
        auto_sync_enabled: true,
        sync_interval_minutes: 360,
        verification_source: "browser_content_script",
        profile_url: message.profileUrl || ""
      }
    }),
    timeoutMs: 15000
  });
  await setPendingConnection(platform, null);
  await enqueueAccountSync({
    accountId: completed.account_id,
    syncRunId: completed.first_sync?.sync_run_id || null,
    tabId: senderTab?.id || pending.tabId || null,
    profileUrl: message.profileUrl || "",
    triggerType: "first_connect"
  });
  return { ok: true, state: "connected", accountId: completed.account_id, message: "账号已连接，首次全量同步已进入后台队列" };
}

async function verifyPendingPlatform(platform) {
  const pending = (await getPendingConnections())[platform];
  if (!pending) return { ok: false, state: "not_pending", error: "没有等待确认的连接流程，请重新点击连接账号" };
  const preferred = await findExistingPlatformTab(platform, pending.tabId);
  if (!preferred?.id) {
    return { ok: false, state: "authorizing", error: "未找到可复用的平台页面；插件不会打开新的登录页。" };
  }
  await chrome.tabs.update(preferred.id, { active: true });
  await ensureAccountMirrorScripts(preferred.id);
  const state = await chrome.tabs.sendMessage(preferred.id, { type: "SA_MIRROR_DISCOVER_ACCOUNT" }).catch(() => null);
  if (!state?.loggedIn) return { ok: false, state: "authorizing", error: "当前页面的登录态尚未确认；插件不会重新打开登录页。" };
  return completePendingBrowserConnection({ type: "SA_PLATFORM_PAGE_READY", platform, ...state }, preferred);
}

async function syncAccountById(accountId, options = {}) {
  const account = (await listAccounts()).find(item => item.id === accountId);
  if (!account) throw new Error("账号不存在");
  if (account.platform === "generic-web" && account.external_account_id === "chrome-bookmarks") {
    return syncChromeBookmarks({
      accountId,
      syncRunId: options.syncRunId || null,
      triggerType: options.triggerType || "manual"
    });
  }
  return runBrowserAccountSync({
    account,
    syncRunId: options.syncRunId || null,
    tabId: options.tabId || null,
    profileUrl: options.profileUrl || "",
    triggerType: options.triggerType || "manual"
  });
}

async function syncAllAccounts(triggerType = "manual") {
  return enqueueAllAccounts(triggerType);
}

async function openAccountCenter() {
  await chrome.tabs.create({ url: chrome.runtime.getURL("options.html#platforms") });
  return { ok: true };
}

async function scheduleBookmarkRefresh() {
  const hasPermission = await chrome.permissions.contains({ permissions: ["bookmarks"] });
  if (!hasPermission) return;
  await chrome.alarms.create("sa-bookmarks-refresh", { delayInMinutes: 0.2 });
}

chrome.runtime.onInstalled.addListener(async details => {
  const config = await SA.setConfig({});
  await ensureMenus();
  await chrome.alarms.create("sa-account-sync", { periodInMinutes: 360 });
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false }).catch(() => {});
  if (details.reason === "install" || details.reason === "update") {
    await reconnectOpenPwaBridgeTabs();
  }
  if (details.reason === "install" && !config.onboardingComplete) {
    await chrome.tabs.create({ url: chrome.runtime.getURL("options.html?onboarding=1") });
  }
});

chrome.runtime.onStartup.addListener(() => {
  ensureMenus().catch(() => {});
  chrome.alarms.create("sa-account-sync", { periodInMinutes: 360 }).catch(() => {});
  getSyncQueue().then(queue => queue.length ? scheduleSyncQueue() : null).catch(() => {});
});
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") injectFabIfAuthorized(tabId, tab.url).catch(() => {});
});
chrome.permissions.onAdded.addListener(async () => {
  try { const tab = await SA.activeTab(); await injectFabIfAuthorized(tab.id, tab.url); } catch (_) {}
});


chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "sa-bookmarks-refresh") {
    listAccounts().then(accounts => {
      const account = accounts.find(item => item.platform === "generic-web" && item.external_account_id === "chrome-bookmarks");
      return account ? enqueueAccountSync({ accountId: account.id, triggerType: "bookmark_change" }) : null;
    }).catch(() => {});
  }
  if (alarm.name === "sa-account-sync") enqueueAllAccounts("scheduled").catch(() => {});
  if (alarm.name === SYNC_QUEUE_ALARM) processSyncQueue().catch(() => {});
});

if (chrome.bookmarks) {
  chrome.bookmarks.onCreated.addListener(() => scheduleBookmarkRefresh().catch(() => {}));
  chrome.bookmarks.onChanged.addListener(() => scheduleBookmarkRefresh().catch(() => {}));
  chrome.bookmarks.onMoved.addListener(() => scheduleBookmarkRefresh().catch(() => {}));
  chrome.bookmarks.onRemoved.addListener(() => scheduleBookmarkRefresh().catch(() => {}));
}

chrome.commands.onCommand.addListener(async command => {
  try {
    if (command === "save-current-page") {
      await captureActive({ mode: "page", source: "keyboard_shortcut" });
      return;
    }
    if (command === "open-task-center") {
      const tab = await SA.activeTab().catch(() => null);
      if (tab?.windowId) await chrome.sidePanel.open({ windowId: tab.windowId });
    }
  } catch (_) {
    await chrome.action.setBadgeBackgroundColor({ color: "#b42318" });
    await chrome.action.setBadgeText({ text: "!" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2200);
  }
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id || !tab.url) return;
  try {
    if (info.menuItemId === MENU_SELECTION && info.selectionText) {
      const config = await SA.getConfig();
      await captureRecord({ url: tab.url, title: tab.title, text: info.selectionText, media_urls: [], raw_metadata: { source: "selection" } }, tab.url, config, { source: "context_selection" });
    } else if (info.menuItemId === MENU_SAVE) {
      await captureActive({ mode: "page", source: "context_menu" }, tab);
    }
    await chrome.action.setBadgeBackgroundColor({ color: "#1f7a4c" });
    await chrome.action.setBadgeText({ text: "✓" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2200);
  } catch (_) {
    await chrome.action.setBadgeBackgroundColor({ color: "#b42318" });
    await chrome.action.setBadgeText({ text: "!" });
  }
});

chrome.runtime.onConnect.addListener(port => {
  if (port.name !== "sa-account-mirror-scan") return;
  port.onMessage.addListener(() => {});
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message?.type === "SA_ACCOUNT_CONNECT") return connectPlatform(String(message.platform || ""));
    if (message?.type === "SA_VERIFY_PLATFORM_SESSION") return verifyPendingPlatform(String(message.platform || ""));
    if (message?.type === "SA_GET_PENDING_CONNECTIONS") return { ok: true, items: await getPendingConnections() };
    if (message?.type === "SA_OPEN_ACCOUNT_CENTER") return openAccountCenter();
    if (message?.type === "SA_SYNC_ACCOUNT") return enqueueAccountSync({ accountId: String(message.accountId || ""), triggerType: "manual" });
    if (message?.type === "SA_SYNC_ALL_ACCOUNTS") return syncAllAccounts("manual");
    if (message?.type === "SA_CONTROL_SYNC_RUN") return controlSyncRun({
      syncRunId: String(message.syncRunId || ""),
      accountId: message.accountId ? String(message.accountId) : null,
      action: String(message.action || "")
    });
    if (message?.type === "SA_GET_SYNC_CONTROL_STATE") {
      const control = await getSyncControl(String(message.syncRunId || ""));
      return { ok: true, action: control?.action || null };
    }
    if (message?.type === "SA_PLATFORM_PAGE_READY") return completePendingBrowserConnection(message, sender?.tab);
    if (message?.type === "SA_CAPTURE_ACTIVE") return captureActive(message, sender?.tab);
    if (message?.type === "SA_OPEN_TASK_CENTER") {
      const tab = await SA.activeTab().catch(() => null);
      if (tab?.windowId) await chrome.sidePanel.open({ windowId: tab.windowId });
      return { ok: true };
    }
    if (message?.type === "SA_REFRESH_FAB") {
      const tab = await SA.activeTab();
      await injectFabIfAuthorized(tab.id, tab.url);
      return { ok: true };
    }
    if (message?.type === "SA_WEB_BRIDGE_STATUS") {
      const config = await SA.getConfig();
      let serviceReady = false;
      let paired = false;
      let pairingRequired = false;
      let oneTimeCodeAvailable = false;
      try {
        const pairing = await fetch(`${config.endpoint}/v1/pairing/status`, { cache: "no-store" }).then(response => response.ok ? response.json() : null);
        pairingRequired = pairing?.pairing_required === true;
        oneTimeCodeAvailable = pairing?.one_time_code_available === true;
        if (pairing && pairing.pairing_required === false) {
          serviceReady = Boolean(pairing.service_ready);
          paired = serviceReady;
        } else if (config.token) {
          await SA.api("/v1/extension/bootstrap", { timeoutMs: 5000 });
          serviceReady = true;
          paired = true;
        }
      } catch (_) {
        serviceReady = false;
      }
      return {
        detected: true,
        paired,
        configured: Boolean(config.endpoint),
        endpoint: config.endpoint,
        libraryUrl: config.libraryUrl,
        serviceReady,
        pairingRequired,
        oneTimeCodeAvailable,
        version: chrome.runtime.getManifest().version
      };
    }
    if (message?.type === "SA_WEB_BRIDGE_CONFIGURE") {
      const current = await SA.getConfig();
      const endpoint = String(message.endpoint || current.endpoint || "").replace(/\/$/, "");
      const libraryUrl = String(message.libraryUrl || current.libraryUrl || endpoint).replace(/\/$/, "");
      if (!/^https?:\/\//i.test(endpoint) || !/^https?:\/\//i.test(libraryUrl)) throw new Error("服务地址无效");
      const response = await fetch(`${endpoint}/v1/pairing/status`, { cache: "no-store" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.pairing_required !== false || !payload.service_ready) {
        throw new Error(payload.detail || "当前服务仍要求安全配对");
      }
      const next = await SA.setConfig({ endpoint, libraryUrl, token: "", onboardingComplete: true });
      return { ok: true, paired: true, endpoint: next.endpoint, libraryUrl: next.libraryUrl };
    }
    if (message?.type === "SA_WEB_BRIDGE_PAIR") {
      const current = await SA.getConfig();
      const endpoint = String(message.endpoint || current.endpoint || "").replace(/\/$/, "");
      if (!/^https?:\/\//i.test(endpoint)) throw new Error("服务地址无效");
      const response = await fetch(`${endpoint}${current.pairingPath || "/v1/pairing/exchange"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: String(message.code || ""), device_name: "Social Archive Chrome" })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `配对失败（${response.status}）`);
      const next = await SA.setConfig({
        endpoint: payload.endpoint || endpoint,
        libraryUrl: payload.library_url || current.libraryUrl,
        token: payload.token || "",
        onboardingComplete: true
      });
      return { ok: true, paired: Boolean(next.token), endpoint: next.endpoint, libraryUrl: next.libraryUrl };
    }
    if (message?.type === "SA_OPEN_OPTIONS") {
      await chrome.runtime.openOptionsPage();
      return { ok: true };
    }
    return { ok: false, error: "未知操作" };
  })().then(sendResponse).catch(error => sendResponse({ ok: false, state: "needs_user_action", error: error?.message || "操作失败" }));
  return true;
});
