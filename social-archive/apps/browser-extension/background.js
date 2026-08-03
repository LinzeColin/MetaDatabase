/* global SA */
importScripts("shared.js", "content/platform-catalog.js", "content/extension-utils.js", "cookie-export.js");

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
const SYNC_QUEUE_LAST_RESULT_KEY = "saAccountSyncQueueLastResult";
const SYNC_CONTROL_KEY = "saSyncRunControls";
const SYNC_QUEUE_ALARM = "sa-account-sync-queue";
// T08：MAIN world 观察器抄回来的原始响应，先缓冲在 service worker 里。
// 上限存在的理由：一次大翻页可能抄回几十兆，撑爆 worker 会把整条同步弄挂。
const NET_CAPTURE_LIMIT = 200;
const netCaptureBuffer = [];
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

// v0.0.0.7 / T03：原先这里向所有标签页广播 SA_MIRROR_CONTROL，
// 让 DOM 抓取的 content script 中途停下。抓取器已删，广播没有接收方——
// 留着它会让"暂停已下发"看着成立而实际什么都没发生。
// 暂停/取消并没有因此失效：stopStateFor 从本地 storage 与服务端 sync-run
// 两处读控制态，编排层每一轮都查，这才是真正生效的那条路。
// T08 引入 MAIN-world 拦截时会带来它自己的控制通道，届时再建。

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
  } else {
    await setSyncControl(syncRunId, null);
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
  if (lock && Date.now() - Number(lock.startedAt || 0) < 2 * 60 * 60 * 1000) {
    await scheduleSyncQueue();
    return { ok: true, state: "busy" };
  }
  const queue = await getSyncQueue();
  const item = queue.shift();
  if (!item) return { ok: true, state: "empty" };
  await setSyncQueue(queue);
  const queuedControl = await getSyncControl(item.syncRunId);
  if (queuedControl?.action === "pause" || queuedControl?.action === "cancel") {
    if (queue.length) await scheduleSyncQueue();
    return { ok: true, state: queuedControl.action === "pause" ? "paused" : "cancelled", syncRunId: item.syncRunId };
  }
  await chrome.storage.local.set({ [SYNC_QUEUE_LOCK_KEY]: { accountId: item.accountId, startedAt: Date.now() } });
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
  return globalThis.SAPlatformCatalog?.platformCatalogEntry?.(platform) || null;
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

async function findExistingPlatformTab(platform, preferredTabId = null) {
  const patterns = SA.patternsForPlatform(platform);
  if (!patterns.length) return null;
  const tabs = await chrome.tabs.query({ url: patterns }).catch(() => []);
  const select = globalThis.SAExtensionUtils?.preferExistingPlatformTab;
  if (typeof select === "function") return select(tabs, preferredTabId);
  return tabs.find(tab => String(tab?.id) === String(preferredTabId)) || tabs.find(tab => tab?.active) || tabs[0] || null;
}

async function sendSyncBatch(syncRunId, body) {
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
  const records = SAExtensionUtils.flattenBookmarksTree(tree).map(item => ({
    ...item,
    destination_ids: serverDestinations(config)
  }));
  const chunks = SAExtensionUtils.chunk(records, 200);
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

function resolveRelationUrl(platform, relation, profileUrl = "") {
  const spec = platformSpec(platform);
  let url = spec?.relationUrls?.[relation] || spec?.home;
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
}

async function sendBrowserScopeBatches({ syncRunId, platform, relation, scopeResult, collectionKey = "", collectionName = "" }) {
  const config = await SA.getConfig();
  const items = (scopeResult.items || []).map(item => ({
    ...item,
    platform,
    relation_type: relation,
    collection_key: collectionKey || item.collection_key || "",
    // 同上：collection_name 只能在批次级别出现（下面 sendSyncBatch 已经带了）。
    // 放到条目上会被 CaptureRequest 的 extra="forbid" 整批打回 422。
    destination_ids: serverDestinations(config)
  }));
  const chunks = SAExtensionUtils.chunk(items, 200);
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

/** 取数缝隙 —— **T08 只需要换掉这一个函数体**。
 *
 * v0.0.0.6 这里向 content script 发 `SA_MIRROR_SCAN_RELATION`，由 DOM 抓取器
 * 滚页面、抠选择器、凑出列表。那条路已被 CONFLICT_ORDER 实测证伪并随 T03 删除。
 * 替代品（在 Owner 浏览器里拦平台自己的 API 响应）属于 T08。
 *
 * **它现在抛错，而不是返回空列表——这是刻意的。** 返回 `{ ok: true, items: [] }`
 * 会一路走完 sendBrowserScopeBatches，在服务端留下一条 completeness=complete、
 * item_count=0 的扫描回执，也就是 INV-NO-SILENT-ZERO 明令禁止的那种"静默的零"：
 * 界面显示同步成功、库里一条没有、没有任何地方说得出为什么。
 * v0.0.0.6 生产上"永远是 0"就是这么来的（见 evidence/T00/CURRENT_TRUTH.json）。
 *
 * 抛出的错由 runBrowserAccountSync 的 catch 接住，写成
 * completeness=failed + failure_code=ACQUISITION_PATH_NOT_INSTALLED，
 * 用户看到的是"这条没成，原因是什么"，而不是"这条空"。
 */
async function acquireRelationItems() {
  const error = new Error("本版本尚未接入平台列表读取通道，请等待版本更新后重试。");
  error.failureCode = "ACQUISITION_PATH_NOT_INSTALLED";
  throw error;
}

async function scanBrowserScope({ tabId, platform, relation, syncRunId, url, collectionKey = "", collectionName = "", alreadyLoaded = false }) {
  if (!alreadyLoaded) await navigateMirrorTab(tabId, url);
  // 取数与传输是两件事，缝在这一行上：上面换实现，下面这两句不动。
  const result = await acquireRelationItems({ tabId, platform, relation, syncRunId, collectionKey, collectionName });
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
  // v0.0.0.7 / T03：收藏夹枚举原先由 DOM 抓取器扫页面里的链接文字猜出来
  // （靠一张"看着像收藏夹"的中文文案正则表）。
  // 抓取器已删。T08 从平台自己的 API 响应里拿收藏夹清单——那是权威来源，
  // 不是从界面文案反推。在那之前这里为空，且下面的取数缝隙会明确报错，
  // 不会出现"收藏夹 0 个但同步成功"。
  const discoveredCollections = [];

  const scopeResults = [];
  const baseResult = await scanBrowserScope({ tabId, platform, relation, syncRunId, url, alreadyLoaded: true });
  if (baseResult?.controlled) return baseResult;
  scopeResults.push(baseResult);

  const seenUrls = new Set([SAExtensionUtils.canonicalUrl(url)]);
  for (const collection of discoveredCollections.slice(0, 100)) {
    const collectionUrl = SAExtensionUtils.canonicalUrl(collection.url);
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
        // 带了具体原因就报具体原因。一律报 BROWSER_SCAN_FAILED 会把
        // "本版本没接取数通道"和"这次扫描炸了"混成同一条，
        // 用户和 T14 的文案矩阵都分不出该怎么办。
        failure_code: error?.failureCode || "BROWSER_SCAN_FAILED",
        cursor: { error: String(error?.message || error).slice(0, 300) },
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
  // v0.0.0.7 / T03：登录态确认原先靠扫页面上有没有"登录"按钮、有没有头像元素。
  // 那是 DOM 抓取，已删。
  //
  // 这里**不能退回"猜它已登录"**：猜错的后果是拿一个未登录的会话去发起首次全量同步，
  // 平台返回空列表，系统记一条"同步完成、0 条"——又是 INV-NO-SILENT-ZERO 那个洞。
  // T08 的拦截路会用"是否收到过带身份的 API 响应"来确认，那是可证的信号。
  return {
    ok: false,
    state: "authorizing",
    failureCode: "LOGIN_PROOF_UNAVAILABLE",
    error: "本版本无法确认这个页面的登录态，账号暂不能连接；请等待版本更新后重试。"
  };
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
      // 就绪与否只有一个判据：拿现有令牌真的调一次受保护接口。
      // 旧实现先问服务端「还要不要配对」，那条路已随 T03 删除；
      // 而且它把"服务说不用配对"当成"我连得上"——两回事，中间隔着令牌有没有效。
      let paired = false;
      try {
        if (config.token) {
          await SA.api("/v1/extension/bootstrap", { timeoutMs: 5000 });
          paired = true;
        }
      } catch (_) {
        paired = false;
      }
      return {
        detected: true,
        paired,
        configured: Boolean(config.endpoint),
        endpoint: config.endpoint,
        libraryUrl: config.libraryUrl,
        serviceReady: paired,
        version: chrome.runtime.getManifest().version
      };
    }
    if (message?.type === "SA_WEB_BRIDGE_CONFIGURE") {
      const current = await SA.getConfig();
      const endpoint = String(message.endpoint || current.endpoint || "").replace(/\/$/, "");
      const libraryUrl = String(message.libraryUrl || current.libraryUrl || endpoint).replace(/\/$/, "");
      if (!/^https?:\/\//i.test(endpoint) || !/^https?:\/\//i.test(libraryUrl)) throw new Error("服务地址无效");
      const next = await SA.setConfig({ endpoint, libraryUrl, onboardingComplete: true });
      return { ok: true, paired: Boolean(next.token), endpoint: next.endpoint, libraryUrl: next.libraryUrl };
    }
    // 取代旧的一次性码流程（v0.0.0.7 / T03）。
    //
    // 旧流程：服务端生成一串码 → 用户从终端/邮件里找到它 → 手抄进扩展设置页 →
    // 十分钟内没抄完就重来。实际使用中连续失败三次，且"手抄一串字符"本身
    // 就是 INV-ZERO-BARRIER 明令禁止的门槛。
    //
    // 新流程：**已登录的档案馆页面**用自己的会话 cookie 调
    // POST /v1/auth/extension-token 换一个长期可撤销令牌，通过 bridge 直接交给扩展。
    // 用户点一下"连接插件"，不接触令牌文本，一个字符都不用输入。
    //
    // 令牌明文只在页面到扩展这一跳里出现，服务端只存哈希；
    // 撤销后扩展上行立刻 401（T03 的 Oracle）。
    if (message?.type === "SA_WEB_BRIDGE_ADOPT_TOKEN") {
      const current = await SA.getConfig();
      // 服务地址取扩展自己的托管配置，不接受页面下发——页面能改端点就等于
      // 任何拿到桥的页面都能把上行改到别处去。
      const endpoint = String(current.endpoint || "").replace(/\/$/, "");
      const token = String(message.token || "").trim();
      if (!/^https?:\/\//i.test(endpoint)) throw new Error("服务地址无效");
      if (!token) throw new Error("没有收到访问凭据，请在档案馆页面重新点击连接插件。");
      const next = await SA.setConfig({
        endpoint,
        libraryUrl: String(message.libraryUrl || current.libraryUrl || "").replace(/\/$/, "") || current.libraryUrl,
        token,
        onboardingComplete: true
      });
      // 存下就算数是不够的——立刻用它调一次受保护接口，确认它真的能用。
      // 否则"已连接"会在第一次同步时才被证伪。
      try {
        await SA.api("/v1/extension/bootstrap", { timeoutMs: 8000 });
      } catch (error) {
        await SA.setConfig({ token: "" });
        throw new Error("凭据未能通过验证，请在档案馆页面重新点击连接插件。");
      }
      return { ok: true, paired: true, endpoint: next.endpoint, libraryUrl: next.libraryUrl };
    }
    // 国内三源：装 MAIN world 观察器（v0.0.0.7 / T08）。
    //
    // 硬边界：只包 fetch / XHR 抄一份响应，绝不合成请求、绝不改请求或响应、
    // 绝不读 Cookie。签名（小红书 x-s/x-t、抖音 a_bogus）全由页面自己完成。
    // 国内平台的 Cookie 一步都不出浏览器（INV-DOMESTIC-COOKIE-STAYS）。
    if (message?.type === "SA_INSTALL_NET_OBSERVER") {
      const platform = String(message.platform || "").trim().toLowerCase();
      const tabId = Number(message.tabId);
      const prefixes = globalThis.SAPlatformCatalog?.interceptPrefixes?.(platform);
      // prefixes 为 null = 还没有实测过的前缀。**必须在这里显式失败**：
      // 装一个前缀为空的观察器等于永远拦不到，而且页面一切正常、界面显示已连接——
      // 正是 INV-NO-SILENT-ZERO 要防的那种零。
      if (!Array.isArray(prefixes) || prefixes.length === 0) {
        return {
          ok: false, state: "needs_user_action", platform,
          failureCode: "INTERCEPT_PREFIX_UNKNOWN",
          error: `还没有确认 ${globalThis.SAPlatformCatalog?.platformLabel?.(platform) || platform} 的收藏接口地址，这个平台暂时不能同步。`,
        };
      }
      if (!Number.isInteger(tabId)) return { ok: false, error: "没有可用的平台页面。" };
      try {
        // MAIN world 先装观察器，再在隔离世界装中继——顺序反了会漏掉
        // 观察器安装瞬间发出的那条 SA_OBSERVER_INSTALLED。
        await chrome.scripting.executeScript({
          target: { tabId }, world: "MAIN", files: ["net-observer.js"],
        });
        await chrome.scripting.executeScript({
          target: { tabId }, files: ["content/net-relay.js"],
        });
        await chrome.tabs.sendMessage(tabId, {
          type: "SA_OBSERVER_CONFIGURE", urlPrefixes: prefixes,
        });
        return { ok: true, state: "observing", platform, prefixCount: prefixes.length };
      } catch (error) {
        return { ok: false, state: "failed", failureCode: "OBSERVER_INSTALL_FAILED",
                 error: error?.message || "无法在该页面上启动同步。" };
      }
    }
    // 观察器抄回来的原始响应。**服务端负责解析**——这里只搬运，不 JSON.parse：
    // 解析失败会吞掉本来能救的数据（预制件的原话）。
    if (message?.type === "SA_NET_CAPTURE") {
      const body = String(message.body || "");
      if (!body) return { ok: false, ignored: true };
      netCaptureBuffer.push({
        url: String(message.url || ""), status: Number(message.status || 0),
        body, capturedAt: String(message.capturedAt || ""),
      });
      // 只留最近若干条，避免 service worker 内存被一次大翻页撑爆。
      if (netCaptureBuffer.length > NET_CAPTURE_LIMIT) netCaptureBuffer.shift();
      return { ok: true, buffered: netCaptureBuffer.length };
    }
    if (message?.type === "SA_GET_NET_CAPTURES") {
      // 只回形态与条数，不回响应体——响应体里可能有平台返回的个人信息，
      // 让它在消息里到处传是没必要的暴露面。
      return { ok: true, count: netCaptureBuffer.length,
               urls: netCaptureBuffer.map(item => item.url),
               totalBytes: netCaptureBuffer.reduce((sum, item) => sum + item.body.length, 0) };
    }
    // 西方三源的会话导出（v0.0.0.7 / T06）。
    //
    // cookies 是**可选权限**：装插件时不申请，只在用户点「连接 X」这一刻才要。
    // 用户拒绝授权时说清楚是没授权，不要退回"没登录"——那两件事的下一步不一样。
    if (message?.type === "SA_CONNECT_PLATFORM_SESSION") {
      const platform = String(message.platform || "").trim().toLowerCase();
      const spec = globalThis.SACookieExport?.ALLOWED_PLATFORMS?.[platform];
      if (!spec) {
        return { ok: false, state: "needs_user_action", error: "这个平台不通过浏览器会话连接。" };
      }
      const origins = spec.domains.flatMap(domain => [`https://*.${domain}/*`, `https://${domain}/*`]);
      const granted = await chrome.permissions.request({ permissions: ["cookies"], origins })
        .catch(() => false);
      if (!granted) {
        return { ok: false, state: "unauthorized", error: "没有获得读取该平台登录状态的授权。" };
      }
      const config = await SA.getConfig();
      try {
        const { count } = await globalThis.SACookieExport.connectPlatformSession(platform, {
          endpoint: config.endpoint, token: config.token,
        });
        // 只回条数。**任何时候都不回、也不记 cookie 的名或值。**
        return { ok: true, state: "connected", platform, count,
                 message_zh: `已连接，登录状态已加密保存（${count} 条）。随时可以一键撤销。` };
      } catch (error) {
        const code = error?.code || "UPLOAD_FAILED";
        return { ok: false, state: code === "NOT_LOGGED_IN" ? "needs_user_action" : "failed",
                 failureCode: code, error: error?.message || "连接失败" };
      }
    }
    if (message?.type === "SA_REVOKE_PLATFORM_SESSION") {
      const platform = String(message.platform || "").trim().toLowerCase();
      const config = await SA.getConfig();
      const response = await fetch(`${config.endpoint}/v1/credentials/${encodeURIComponent(platform)}`, {
        method: "DELETE", headers: { Authorization: `Bearer ${config.token}` },
      }).catch(() => null);
      if (!response?.ok) return { ok: false, error: "撤销失败，请稍后重试。" };
      // 顺手把浏览器这边的权限也还回去——库里删了但权限还留着，
      // 用户看到的仍是"这个插件能读我的 Cookie"。
      const spec = globalThis.SACookieExport?.ALLOWED_PLATFORMS?.[platform];
      if (spec) {
        await chrome.permissions.remove({
          origins: spec.domains.flatMap(d => [`https://*.${d}/*`, `https://${d}/*`]),
        }).catch(() => null);
      }
      return { ok: true, state: "disconnected", message_zh: "已撤销，服务器上的登录信息已删除。" };
    }
    if (message?.type === "SA_OPEN_OPTIONS") {
      await chrome.runtime.openOptionsPage();
      return { ok: true };
    }
    return { ok: false, error: "未知操作" };
  })().then(sendResponse).catch(error => sendResponse({ ok: false, state: "needs_user_action", error: error?.message || "操作失败" }));
  return true;
});
