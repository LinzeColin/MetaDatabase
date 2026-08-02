(() => {
  "use strict";

  const MANAGED_CONFIG_URL = chrome.runtime.getURL("runtime-config.json");
  const FALLBACK_ENDPOINT = "https://social-archive-api.linzezhang.com";
  const FALLBACK_LIBRARY = "https://social-archive.linzezhang.com";
  const DEFAULT_CONFIG = Object.freeze({
    endpoint: FALLBACK_ENDPOINT,
    libraryUrl: FALLBACK_LIBRARY,
    pairingPath: "/v1/pairing/exchange",
    token: "",
    destinationIds: ["social_archive", "markdown"],
    relationType: "saved",
    collectionKey: "",
    showFloatingButton: true,
    onboardingComplete: false,
    obsidianLocalEnabled: false,
    obsidianLocalUrl: "http://127.0.0.1:27123",
    obsidianLocalToken: ""
  });

  const PLATFORM_RULES = Object.freeze([
    { id: "xiaohongshu", name: "小红书", patterns: ["https://*.xiaohongshu.com/*", "https://xhslink.com/*", "https://*.xhslink.com/*"] },
    { id: "douyin", name: "抖音", patterns: ["https://*.douyin.com/*", "https://v.iesdouyin.com/*"] },
    { id: "kuaishou", name: "快手", patterns: ["https://*.kuaishou.com/*", "https://*.gifshow.com/*", "https://kuaishou.cn/*", "https://*.kuaishou.cn/*"] },
    { id: "bilibili", name: "哔哩哔哩", patterns: ["https://*.bilibili.com/*", "https://b23.tv/*"] },
    { id: "x", name: "X", patterns: ["https://x.com/*", "https://*.x.com/*", "https://twitter.com/*"] },
    { id: "reddit", name: "Reddit", patterns: ["https://*.reddit.com/*", "https://redd.it/*"] },
    { id: "instagram", name: "Instagram", patterns: ["https://*.instagram.com/*"] },
    { id: "generic-web", name: "普通网页", patterns: [] }
  ]);

  const DESTINATION_NAMES = Object.freeze({
    social_archive: "我的档案馆",
    markdown: "Markdown",
    notion: "Notion",
    obsidian: "Obsidian",
    github: "GitHub 私有库",
    karakeep: "Karakeep 阅读器",
    linkwarden: "Linkwarden 阅读器",
    archivebox: "ArchiveBox 归档队列"
  });

  const JOB_LABELS = Object.freeze({
    download_l3: "保存原文件",
    export_destination: "导出副本",
    replicate_object: "三地备份",
    sync_private_database: "同步事实",
    connector_run: "读取平台"
  });

  let managedConfigPromise = null;

  function normalizeEndpoint(value, fallback = FALLBACK_ENDPOINT) {
    try {
      const url = new URL(String(value || fallback).trim());
      if (!/^https?:$/.test(url.protocol)) return fallback;
      url.hash = "";
      url.search = "";
      return url.toString().replace(/\/$/, "");
    } catch (_) {
      return fallback;
    }
  }

  async function loadManagedConfig() {
    if (!managedConfigPromise) {
      managedConfigPromise = fetch(MANAGED_CONFIG_URL, { cache: "no-store" })
        .then(response => response.ok ? response.json() : {})
        .catch(() => ({}));
    }
    const raw = await managedConfigPromise;
    return {
      endpoint: normalizeEndpoint(raw.endpoint, FALLBACK_ENDPOINT),
      libraryUrl: normalizeEndpoint(raw.library_url, FALLBACK_LIBRARY),
      pairingPath: String(raw.pairing_path || "/v1/pairing/exchange"),
      managed: raw.managed !== false
    };
  }

  async function getConfig() {
    const managed = await loadManagedConfig();
    const defaults = {
      ...DEFAULT_CONFIG,
      endpoint: managed.endpoint,
      libraryUrl: managed.libraryUrl,
      pairingPath: managed.pairingPath
    };
    const stored = await chrome.storage.local.get(defaults);
    return {
      ...defaults,
      ...stored,
      endpoint: normalizeEndpoint(stored.endpoint, managed.endpoint),
      libraryUrl: normalizeEndpoint(stored.libraryUrl, managed.libraryUrl),
      pairingPath: String(stored.pairingPath || managed.pairingPath),
      destinationIds: Array.isArray(stored.destinationIds) && stored.destinationIds.length
        ? [...new Set(stored.destinationIds.map(String))]
        : [...DEFAULT_CONFIG.destinationIds]
    };
  }

  async function setConfig(patch) {
    const current = await getConfig();
    const next = { ...current, ...patch };
    next.endpoint = normalizeEndpoint(next.endpoint, current.endpoint);
    next.libraryUrl = normalizeEndpoint(next.libraryUrl, current.libraryUrl || FALLBACK_LIBRARY);
    next.destinationIds = [...new Set((next.destinationIds || []).map(String))];
    if (!next.destinationIds.includes("social_archive")) next.destinationIds.unshift("social_archive");
    await chrome.storage.local.set(next);
    return next;
  }

  async function api(path, options = {}) {
    const config = await getConfig();
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (config.token) headers.set("Authorization", `Bearer ${config.token}`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeoutMs || 15000);
    try {
      const response = await fetch(`${config.endpoint}${path}`, { ...options, headers, signal: controller.signal });
      const text = await response.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { detail: text }; }
      if (!response.ok) {
        const error = new Error(data.detail || `HTTP ${response.status}`);
        error.status = response.status;
        error.payload = data;
        throw error;
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  async function apiText(path, options = {}) {
    const config = await getConfig();
    const headers = new Headers(options.headers || {});
    if (config.token) headers.set("Authorization", `Bearer ${config.token}`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeoutMs || 15000);
    try {
      const response = await fetch(`${config.endpoint}${path}`, { ...options, headers, signal: controller.signal });
      const text = await response.text();
      if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
      return text;
    } finally {
      clearTimeout(timer);
    }
  }

  function platformFromUrl(value) {
    let host = "";
    try { host = new URL(value).hostname.toLowerCase(); } catch (_) { return PLATFORM_RULES.at(-1); }
    const test = needle => host === needle || host.endsWith(`.${needle}`);
    if (test("xiaohongshu.com")) return PLATFORM_RULES.find(x => x.id === "xiaohongshu");
    if (test("douyin.com")) return PLATFORM_RULES.find(x => x.id === "douyin");
    if (test("kuaishou.com")) return PLATFORM_RULES.find(x => x.id === "kuaishou");
    if (test("bilibili.com")) return PLATFORM_RULES.find(x => x.id === "bilibili");
    if (test("x.com") || test("twitter.com")) return PLATFORM_RULES.find(x => x.id === "x");
    if (test("reddit.com")) return PLATFORM_RULES.find(x => x.id === "reddit");
    if (test("instagram.com")) return PLATFORM_RULES.find(x => x.id === "instagram");
    return PLATFORM_RULES.at(-1);
  }

  function patternsForPlatform(platformId) {
    return PLATFORM_RULES.find(item => item.id === platformId)?.patterns || [];
  }

  async function permissionState(platformId) {
    const origins = patternsForPlatform(platformId);
    if (!origins.length) return { authorized: true, origins: [] };
    const authorized = await chrome.permissions.contains({ origins });
    return { authorized, origins };
  }

  async function requestPlatformPermission(platformId) {
    const origins = patternsForPlatform(platformId);
    if (!origins.length) return true;
    return chrome.permissions.request({ origins });
  }

  async function removePlatformPermission(platformId) {
    const origins = patternsForPlatform(platformId);
    if (!origins.length) return false;
    return chrome.permissions.remove({ origins });
  }

  async function activeTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !/^https?:/i.test(tab.url || "")) throw new Error("请先打开一个可保存的网页");
    return tab;
  }

  function destinationLabel(id) { return DESTINATION_NAMES[id] || id; }
  function jobLabel(type) { return JOB_LABELS[type] || type || "归档任务"; }

  function normalizeJobState(job) {
    if (["succeeded", "done", "noop"].includes(job.status)) return "success";
    if (["dead", "failed", "retry"].includes(job.status)) return "needs_user_action";
    return job.status || "queued";
  }

  function statusCopy(state) {
    return ({
      queued: "等待处理", running: "正在处理", success: "已完成", done: "已完成", noop: "无需重复写入", failed: "失败",
      needs_user_action: "需要你处理", connected: "已连接", checking: "检查中", not_checked: "尚未检查",
      degraded: "需要检查", expired: "授权已失效", blocked_policy: "当前不可用",
      blocked_environment: "等待环境连接", disabled: "未启用", healthy: "可用",
      authorized: "已授权", unauthorized: "未授权", unsupported: "暂不支持"
    })[state] || state || "未知";
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    })[char]);
  }

  globalThis.SA = Object.freeze({
    DEFAULT_CONFIG, PLATFORM_RULES, DESTINATION_NAMES, loadManagedConfig, getConfig, setConfig,
    api, apiText, activeTab, platformFromUrl, patternsForPlatform, permissionState,
    requestPlatformPermission, removePlatformPermission, destinationLabel, jobLabel,
    normalizeJobState, statusCopy, escapeHtml
  });
})();
