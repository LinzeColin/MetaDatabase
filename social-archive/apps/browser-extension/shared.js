(() => {
  "use strict";

  const MANAGED_CONFIG_URL = chrome.runtime.getURL("runtime-config.json");
  const FALLBACK_ENDPOINT = "https://social-archive-api.linzezhang.com";
  const FALLBACK_LIBRARY = "https://social-archive.linzezhang.com";
  const DEFAULT_CONFIG = Object.freeze({
    endpoint: FALLBACK_ENDPOINT,
    libraryUrl: FALLBACK_LIBRARY,
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
      managed: raw.managed !== false
    };
  }

  async function getConfig() {
    const managed = await loadManagedConfig();
    const defaults = {
      ...DEFAULT_CONFIG,
      endpoint: managed.endpoint,
      libraryUrl: managed.libraryUrl
    };
    const stored = await chrome.storage.local.get(defaults);
    return {
      ...defaults,
      ...stored,
      endpoint: normalizeEndpoint(stored.endpoint, managed.endpoint),
      libraryUrl: normalizeEndpoint(stored.libraryUrl, managed.libraryUrl),
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

  /** 把任意失败变成一句能给人看的中文。
   *
   * 规则来自冻结词典（docs/ZERO_BARRIER_UX.md）：
   * 界面上出现的失败不得含英文错误码或堆栈。
   * 服务端的 detail 已经是中文，原样用；缺失或明显不是中文时，按状态码给一句。
   */
  function SA_humanMessage(detail, status) {
    const text = String(detail || "").trim();
    // 至少含一个中文字符才认为它是给人看的
    if (text && /[\u4e00-\u9fff]/.test(text)) return text;
    if (status === 401 || status === 403) return "登录状态已失效，请重新连接。";
    if (status === 404) return "这个功能在当前版本还不可用。";
    if (status === 429) return "请求太频繁，已自动放慢，稍后会继续。";
    if (status >= 500) return "服务器暂时出了点问题。你的数据没有丢，请稍后重试。";
    return "暂时连不上服务器。你的数据没有丢，请重试。";
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
        // 抛给界面的话必须已经是中文（v0.0.0.7 / T14）。
        // 服务端的 detail 本来就是中文；但它缺失时原先兜底成 `HTTP 500`——
        // 英文加状态码，正是冻结词典明令禁止出现在界面上的东西。
        // 在这里兜住，八处 toast(error.message) 就一次都不用改。
        const error = new Error(SA_humanMessage(data.detail, response.status));
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
      // apiText 拿到的 text 可能是一整页 HTML，绝不能直接当提示语。
      if (!response.ok) throw new Error(SA_humanMessage(null, response.status));
      return text;
    } finally {
      clearTimeout(timer);
    }
  }

  function platformFromUrl(value) {
    let host = "";
    try { host = new URL(value).hostname.toLowerCase(); } catch (_) { return PLATFORM_RULES.at(-1); }
    const test = needle => host === needle || host.endsWith(`.${needle}`);
    // **短链域名也要认。**
    //
    // 这些域名本来就写在各平台的权限模式里（我们向用户要过它们的授权），
    // 而认平台时却一个都不判——两张名单对不上，实测有 8 个域名
    // 「要了权限、却认成普通网页」：xhslink.com / v.iesdouyin.com /
    // gifshow.com / kuaishou.cn / b23.tv / redd.it。
    //
    // 其中 xhslink.com 就是小红书的标准分享链接。把一条小红书分享链
    // 记成「普通网页」，等于丢掉平台那一侧的全部处理。
    //
    // （影响有限，因为这些域名多半会跳转到正域名，等用户点保存时地址栏
    //  已经换过来了。但两张名单对不上本身就是个隐患，而且**要了权限
    //  却不用**，对一个把「你的凭据只在你自己机器上」当卖点的产品尤其别扭。）
    if (test("xiaohongshu.com") || test("xhslink.com")) return PLATFORM_RULES.find(x => x.id === "xiaohongshu");
    if (test("douyin.com") || test("iesdouyin.com")) return PLATFORM_RULES.find(x => x.id === "douyin");
    if (test("kuaishou.com") || test("kuaishou.cn") || test("gifshow.com")) return PLATFORM_RULES.find(x => x.id === "kuaishou");
    if (test("bilibili.com") || test("b23.tv")) return PLATFORM_RULES.find(x => x.id === "bilibili");
    if (test("x.com") || test("twitter.com")) return PLATFORM_RULES.find(x => x.id === "x");
    if (test("reddit.com") || test("redd.it")) return PLATFORM_RULES.find(x => x.id === "reddit");
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
