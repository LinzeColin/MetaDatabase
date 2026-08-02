/* global SA */
importScripts("shared.js");

const MENU_SAVE = "social-archive-save-page";
const MENU_SELECTION = "social-archive-save-selection";

async function ensureMenus() {
  await chrome.contextMenus.removeAll();
  chrome.contextMenus.create({ id: MENU_SAVE, title: "保存到我的档案馆", contexts: ["page", "link", "image", "video"] });
  chrome.contextMenus.create({ id: MENU_SELECTION, title: "保存选中文本到我的档案馆", contexts: ["selection"] });
}

async function injectExtractor(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content/extract-core.js", "content/extract.js"] });
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

function isSafeLocalObsidianPath(value) {
  const text = String(value || "");
  const parts = text.split("/");
  return text.length <= 2048
    && parts.length >= 3
    && parts[0] === "Social Archive"
    && parts.every(part => part && part !== "." && part !== ".." && !/[\\\u0000-\u001f]/.test(part))
    && parts.at(-1).toLowerCase().endsWith(".md");
}

function localObsidianPath(response, record, remotePath) {
  if (isSafeLocalObsidianPath(remotePath)) return String(remotePath);
  const platform = SA.platformFromUrl(record?.url || "").id;
  return `Social Archive/${safeFileSegment(platform, "web")}/${safeFileSegment(record?.title, response.content_id)}-${response.content_id.slice(-8)}.md`;
}

async function exportLocalObsidian(response, record, config, remotePath = null) {
  if (!config.obsidianLocalEnabled || !config.destinationIds.includes("obsidian")) return { status: "not_selected" };
  const path = localObsidianPath(response, record, remotePath);
  if (!config.obsidianLocalToken) return { status: "failed", path, error: "Obsidian 令牌缺失" };
  try {
    const markdown = await SA.apiText(`/v1/library/${encodeURIComponent(response.content_id)}/markdown`, { timeoutMs: 15000 });
    const result = await fetch(`${SA.OBSIDIAN_LOOPBACK_URL}/vault`, {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${config.obsidianLocalToken}`,
        "Content-Type": "text/markdown; charset=utf-8",
        "X-Social-Archive-Path": encodeURIComponent(path)
      },
      body: markdown
    });
    if (!result.ok) throw new Error(`Obsidian HTTP ${result.status}`);
    let payload = {};
    try { payload = await result.json(); } catch (_) { throw new Error("Obsidian 返回了无效回执"); }
    if (!["done", "noop"].includes(payload.status)) throw new Error("Obsidian 返回了未知完成状态");
    const confirmedPath = isSafeLocalObsidianPath(payload.path) ? payload.path : path;
    return { status: payload.status, path: confirmedPath };
  } catch (error) {
    return { status: "failed", path, error: error?.message || "Obsidian 写入失败" };
  }
}

async function recordLocalObsidianReceipt(response, local) {
  if (!["done", "noop", "failed"].includes(local.status)) return null;
  return SA.api("/v1/destinations/obsidian-local/receipts", {
    method: "POST",
    body: JSON.stringify({ content_id: response.content_id, status: local.status, remote_path: local.path || null }),
    timeoutMs: 15000
  });
}

async function attachLocalObsidianReceipt(response, record, config, remotePath = null) {
  const local = await exportLocalObsidian(response, record, config, remotePath);
  response.local_obsidian = local;
  if (local.status === "not_selected") return local;
  try {
    response.local_obsidian_receipt = await recordLocalObsidianReceipt(response, local);
  } catch (error) {
    local.receipt_error = error?.message || "Obsidian 回执未写入任务中心";
  }
  return local;
}

async function captureRecord(record, tabUrl, config, overrides = {}) {
  const body = buildCaptureBody(record, tabUrl, config, overrides);
  const response = await SA.api("/v1/captures", { method: "POST", body: JSON.stringify(body), timeoutMs: 30000 });
  await attachLocalObsidianReceipt(response, record, config);
  return response;
}

async function captureActive(message = {}, sourceTab = null) {
  const tab = sourceTab?.id && sourceTab?.url ? sourceTab : await SA.activeTab();
  const config = await SA.getConfig();
  const extracted = await extractFromTab(tab, message.mode === "list" ? "list" : "page");
  const items = message.mode === "list" ? extracted.items : [extracted.page];
  if (!items.length) return { ok: false, state: "needs_user_action", error: "当前可见区域没有可读取的内容" };
  let saved = [];
  const failed = [];
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
          await attachLocalObsidianReceipt(saved[index], items[index] || {}, config);
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
  const skippedDestinationIds = [...new Set(saved.flatMap(item => item.skipped_destination_ids || []))];
  const localDestinationErrors = saved
    .map(item => item.local_obsidian)
    .filter(item => item?.status === "failed")
    .map(item => item.receipt_error || item.error || "Obsidian 本机桥接失败");
  const destinationWarnings = [...new Set([
    ...localDestinationErrors,
    ...skippedDestinationIds.map(id => `${SA.destinationLabel(id)} 尚未完成主动连接检查，未自动导出`)
  ])];
  await chrome.action.setBadgeBackgroundColor({ color: destinationWarnings.length ? "#9a6700" : "#1f7a4c" });
  await chrome.action.setBadgeText({ text: String(saved.length) });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2500);
  return {
    ok: true,
    savedCount: saved.length,
    failedCount: failed.length,
    destinationWarningCount: destinationWarnings.length,
    destinationWarnings,
    skippedDestinationIds,
    jobIds: saved.flatMap(item => item.job_ids || []),
    detailUrls: saved.map(item => item.detail_url)
  };
}

async function retryLocalObsidian(contentId, remotePath) {
  const config = await SA.getConfig();
  if (!config.obsidianLocalEnabled || !config.destinationIds.includes("obsidian")) {
    return { ok: false, state: "needs_user_action", error: "请先在设置中连接并启用 Obsidian 本机桥接" };
  }
  const response = { content_id: contentId };
  const local = await attachLocalObsidianReceipt(response, {}, config, remotePath);
  if (local.status === "done" || local.status === "noop") return { ok: true, status: local.status };
  return { ok: false, state: "needs_user_action", error: local.receipt_error || local.error || "Obsidian 本机桥接重试失败" };
}

async function injectFabIfAuthorized(tabId, url) {
  if (!/^https?:/i.test(url || "")) return;
  const config = await SA.getConfig();
  if (!config.showFloatingButton) return;
  const platform = SA.platformFromUrl(url);
  if (platform.id === "generic_web") return;
  const state = await SA.permissionState(platform.id);
  if (!state.authorized) return;
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content/fab.js"] }).catch(() => {});
}

chrome.runtime.onInstalled.addListener(async details => {
  const config = await SA.setConfig({});
  await ensureMenus();
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false }).catch(() => {});
  if (details.reason === "install" && !config.onboardingComplete) {
    await chrome.tabs.create({ url: chrome.runtime.getURL("options.html?onboarding=1") });
  }
});

chrome.runtime.onStartup.addListener(() => ensureMenus().catch(() => {}));
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") injectFabIfAuthorized(tabId, tab.url).catch(() => {});
});
chrome.permissions.onAdded.addListener(async () => {
  try { const tab = await SA.activeTab(); await injectFabIfAuthorized(tab.id, tab.url); } catch (_) {}
});

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
    let hasDestinationWarning = false;
    if (info.menuItemId === MENU_SELECTION && info.selectionText) {
      const config = await SA.getConfig();
      const saved = await captureRecord({ url: tab.url, title: tab.title, text: info.selectionText, media_urls: [], raw_metadata: { source: "selection" } }, tab.url, config, { source: "context_selection" });
      hasDestinationWarning = Boolean((saved.skipped_destination_ids || []).length || saved.local_obsidian?.status === "failed");
    } else if (info.menuItemId === MENU_SAVE) {
      const saved = await captureActive({ mode: "page", source: "context_menu" });
      hasDestinationWarning = Boolean(saved.destinationWarningCount);
    }
    await chrome.action.setBadgeBackgroundColor({ color: hasDestinationWarning ? "#9a6700" : "#1f7a4c" });
    await chrome.action.setBadgeText({ text: hasDestinationWarning ? "!" : "✓" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2200);
  } catch (_) {
    await chrome.action.setBadgeBackgroundColor({ color: "#b42318" });
    await chrome.action.setBadgeText({ text: "!" });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message?.type === "SA_CAPTURE_ACTIVE") return captureActive(message, sender?.tab);
    if (message?.type === "SA_RETRY_LOCAL_OBSIDIAN") return retryLocalObsidian(message.contentId, message.remotePath);
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
      try {
        const pairing = await fetch(`${config.endpoint}/v1/pairing/status`, { cache: "no-store" })
          .then(response => response.ok ? response.json() : null);
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
