(() => {
  "use strict";

  const MANAGED_CONFIG_URL = chrome.runtime.getURL("runtime-config.json");
  const FALLBACK_ENDPOINT = "https://social-archive-api.linzezhang.com";
  // 资料库回落地址用**接口那个域名**：同一份前端，而且没有 Cloudflare Access
  // 挡着。指向被挡的那个域名时，扩展会一直把人往一堵进不去的墙上送。（2026-08-17）
  const FALLBACK_LIBRARY = "https://social-archive-api.linzezhang.com";
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
    // **youtube 在服务端凭据表、Cookie 导出白名单、manifest 权限里一直都有，
    // 唯独这里没有——于是权限要了、存得下、导得出，而用户点不到。**
    // 2026-08-05 由 Owner 裁定接上。google.com 也要，因为 YouTube 的登录态
    // 有一部分挂在 Google 账号域上（cookie-export 的 ALLOWED_PLATFORMS 里
    // 早就把这两个域写在一起了）。
    { id: "youtube", name: "YouTube", patterns: ["https://*.youtube.com/*", "https://youtube.com/*", "https://*.google.com/*"] },
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
    if (test("youtube.com") || test("youtu.be")) return PLATFORM_RULES.find(x => x.id === "youtube");
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

  /** 要一次权限，**先问有没有**——任何权限，不只是主机权限（2026-08-10）。
   *
   * ## 为什么补这一个
   *
   * `requestPlatformPermission` 2026-08-06 已经按「先 contains 再 request」
   * 改过，但它只管**主机权限**：`patternsForPlatform` 为空就直接 return true。
   * 于是 background 里另外两处一直是裸的 `chrome.permissions.request`：
   *
   *     connectChromeBookmarks          bookmarks（Chrome 书签）
   *     connectPlatformSessionByCookies cookies（登录状态托管）
   *
   * 而 MV3 的 service worker 里**永远没有用户手势**，`request` 在那儿
   * 一定抛 "This function must be called during a user gesture"——
   * **即使这个权限刚刚在面板里被授予过**。这不是推断：
   * `evidence/G3/SHIPPED_PACKAGE.json` 的
   * `permission_request_from_service_worker` 三项全是这句话。
   *
   * 后果是具体的：他在资料库面板上点「连接账号」→ 面板在页面里把
   * bookmarks 要到手（那一步是对的）→ 消息发给 background →
   * `connectChromeBookmarks` 第一行就抛，面板把那句**英文**原样显示给他。
   * 这正是 8/4 那次停摆的同一个形状，只是换了个平台。
   *
   * 2026-08-07 那次修复把授权挪进了页面，注释里写的理由是
   * 「background 那边的 requestPlatformPermission 会先 contains 再 request」——
   * 那句话只对三条路里的一条成立，而它恰好写在处理另外两条的函数上。
   */
  async function ensurePermission(request) {
    const wanted = request || {};
    if (!wanted.permissions?.length && !wanted.origins?.length) return true;
    if (await chrome.permissions.contains(wanted).catch(() => false)) return true;
    // 到这儿才是真没授予。在 service worker 里 request 仍旧会抛，
    // **而抛出来那句英文和「连接账号」看不出关系**，所以在这里收成 false，
    // 由调用方说一句他能照着做的中文。
    return chrome.permissions.request(wanted).catch(() => false);
  }

  async function requestPlatformPermission(platformId) {
    const origins = patternsForPlatform(platformId);
    if (!origins.length) return true;
    // **已经有了就别再问。**
    //
    // `chrome.permissions.request` 要求「在一次用户手势期间调用」，
    // 没有手势就直接抛 "This function must be called during a user gesture"
    // —— **即使这个权限早就授予过**。
    //
    // 后果不是测试跑不了，是**定时自动同步每次都会炸**：
    // 自动同步由 chrome.alarms 触发（默认 360 分钟一次），那条路上没有任何
    // 用户手势，而它一路会走到取数前的这一句。用户当初点「连接账号」时
    // 明明给过权限，之后每一次自动同步却都失败——而且失败原因是一句
    // 讲手势的英文，和「同步」这件事看不出关系。
    //
    // 2026-08-06 由 G3 的端到端演练撞出来（它在 service worker 里跑整条链，
    // 同样没有手势——**和定时同步是同一个形状**）。
    // **2026-08-10：交给 ensurePermission，它会把异常收住。**
    //
    // 这个帮手原来自己做 contains-then-request，最后那一句 request **仍然会抛**。
    // 三个调用方里只有两个接了 `.catch(() => false)`：
    //
    //     background.js:314   installNetObserverForTab   .catch  ✓
    //     background.js:1383  bilibili 注入前             .catch  ✓
    //     background.js:997   **connectBrowserPlatform**  没有    ✗
    //
    // 而漏掉的那一条正是 bilibili / 小红书 / 抖音 / 快手 / Reddit / Instagram
    // **重新连接**走的路。授权真没拿到时，他看到的会是
    // "This function must be called during a user gesture"，而不是
    // 「未获得B站页面读取权限」。**在一处接住，好过在三处各接一次。**
    return ensurePermission({ origins });
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
    ensurePermission, requestPlatformPermission, removePlatformPermission, destinationLabel, jobLabel,
    normalizeJobState, statusCopy, escapeHtml
  });
})();
