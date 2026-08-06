(() => {
  "use strict";

  const $ = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
  const safeUrl = value => {
    try {
      const url = new URL(String(value || ""));
      return /^https?:$/.test(url.protocol) ? url.toString() : "#";
    } catch (_) { return "#"; }
  };

  const svg = {
    sort: `<svg class="sort-indicator" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 6 8 2l4 4M12 10l-4 4-4-4"/></svg>`,
    chevron: `<svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>`,
    external: `<svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 5h5v5M10 14 19 5M19 13v6H5V5h6"/></svg>`,
    media: `<svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m4 17 5-5 4 4 2-2 5 5"/></svg>`
  };

  const platformMeta = {
    all: { label: "全部", short: "全", cls: "all", server: "" },
    xhs: { label: "小红书", short: "小", cls: "xhs", server: "xiaohongshu" },
    dy: { label: "抖音", short: "抖", cls: "dy", server: "douyin" },
    ks: { label: "快手", short: "快", cls: "ks", server: "kuaishou" },
    bili: { label: "B站", short: "B", cls: "bili", server: "bilibili" },
    x: { label: "X", short: "X", cls: "x", server: "x" },
    reddit: { label: "Reddit", short: "R", cls: "reddit", server: "reddit" },
    ins: { label: "Instagram", short: "In", cls: "ins", server: "instagram" },
    yt: { label: "YouTube", short: "Y", cls: "yt", server: "youtube" },
    web: { label: "Chrome书签/网页", short: "书", cls: "web", server: "generic-web" }
  };
  const platformOrder = ["all", "xhs", "dy", "ks", "bili", "x", "reddit", "ins", "web"];
  const serverToUiPlatform = Object.fromEntries(Object.entries(platformMeta).filter(([key]) => key !== "all").map(([key, value]) => [value.server, key]));

  const relationLabels = {
    // **每个关系值一个独一无二的中文名。**
    // 2026-08-06：`saved` 与 `favorite` 都叫「收藏」、`like` 与 `upvoted` 都叫「点赞」。
    // 在表格那一列里这没关系（用户不在乎内部名），**但关系筛选是照这张表画的**，
    // 于是下拉里会并排出现两个一模一样的「收藏」——生产上两个都有内容
    // （favorite 46 条、saved 5 条），用户没法分辨该点哪一个。
    // 它们本来就是不同平台的不同关系，给不同的名字更准。
    manual_save: "手动保存", bookmark: "书签", saved: "已保存", favorite: "收藏",
    like: "点赞", upvoted: "顶过", watch_later: "稍后再看", history: "观看历史", collection: "收藏夹",
    // **playlist 此前不在这张表里**（2026-08-06）。它是 YouTube 的第二种关系
    // （PLATFORM_RELATIONS["youtube"] = ["watch_later", "playlist"]），而下面那句
    // 取不到标签时会退回原值——用户会在「关系」那一列看到一个英文单词 playlist。
    // YouTube 恰恰是交接里让 Owner 去连的那个平台。
    playlist: "播放列表"
  };
  const relationApiValues = { "收藏": "favorite", "点赞": "like", "书签": "bookmark", "稍后再看": "watch_later" };
  const connectionLabels = {
    connected: "已连接", authorized: "已授权", authorizing: "正在授权", scanning: "同步中", queued: "等待同步",
    discovering: "正在发现", normalizing: "正在整理", artifacting: "正在归档", exporting: "正在导出",
    completed: "同步完成", partial: "部分完成", paused: "已暂停", failed: "需要处理",
    blocked_environment: "需要重新连接", disconnected: "未连接", degraded: "降级可用", cancelled: "已取消"
  };
  // 失败文案词典（v0.0.0.7 / T14）。**逐字**照抄 docs/ZERO_BARRIER_UX.md 的
  // 「错误文案词典（冻结）」，与 src/social_archive/failure_copy.py 是同一份内容的两处实现。
  // 两处会不会漂？有判据盯着：tests/focused/test_failure_copy_matrix.py 里
  // test_pwa_dictionary_matches_the_python_one 逐句比对。
  //
  // 为什么界面必须有这张表：INV-NO-SILENT-ZERO。同步失败时界面只显示
  // 「需要处理」是不够的——用户不知道该去登录、去授权、还是去重试。
  const failureCopy = {
    CREDENTIAL_EXPIRED: { text: "<平台> 的登录状态过期了。[ 重新连接 ]", action: "重新连接" },
    NOT_LOGGED_IN: { text: "没有在浏览器里找到 <平台> 的登录状态。请先在浏览器里登录 <平台>，然后点 [ 重试 ]", action: "重试" },
    REDDIT_NOT_AUTHORIZED: { text: "Reddit 需要单独授权一次。[ 去授权 ]", action: "去授权" },
    TAB_CLOSED: { text: "<平台> 同步中断了，因为标签页被关掉。[ 继续 ]", action: "继续" },
    RATE_LIMITED: { text: "<平台> 请求太频繁，已自动放慢。已经收到的 <N> 条都保住了，稍后会自动继续。", action: null },
    SERVER_UNREACHABLE: { text: "暂时连不上服务器。你的数据没有丢，[ 重试 ]", action: "重试" },
    DISK_QUOTA: { text: "存储空间快满了，已经暂停下载媒体文件，文字和链接还在正常保存。", action: null }
  };
  // 内部失败码比词典细，但界面上只许出现词典里的七句。
  const failureAliases = {
    // **ACQUISITION_PATH_NOT_INSTALLED 从这里删掉了**（2026-08-06）。
    //
    // 服务端早就把它移出别名表了（failure_copy.DELIBERATELY_UNALIASED），
    // 理由写得很清楚：它的含义是「本版本没有实现这条取数路」，
    // 别名成 SERVER_UNREACHABLE 就变成「暂时连不上服务器，[ 重试 ]」——
    // **让人一遍遍重试一件永远不可能成功的事**。
    //
    // 而这一侧没跟着改。**同一个失败码，服务端说「这是产品的问题」，
    // 界面说「暂时连不上，重试」——两张表各修各的，就会这样漂开。**
    // 删掉之后它落到下面 failureSentence 的兜底句：
    // 「这是产品的问题…如果还是这样，请联系我们」——措辞不完美，
    // 但它把人导向对的方向。
    LOGIN_PROOF_UNAVAILABLE: "NOT_LOGGED_IN",
    PERMISSION_DENIED: "NOT_LOGGED_IN",
    UPLOAD_FAILED: "SERVER_UNREACHABLE",
    BROWSER_SCAN_FAILED: "SERVER_UNREACHABLE",
    RELATION_URL_UNAVAILABLE: "SERVER_UNREACHABLE",
    // 原始媒体文件没取到（v0.0.0.7）。内容本身已经保存好了，
    // 少的只是那个视频/图片文件。限流/超时才可以再试。
    MEDIA_TEMPORARILY_UNAVAILABLE: "RATE_LIMITED",
    // 诊断按钮：观察器一条响应都没拦到（v0.0.0.7 / T08）。
    // 滚几屏再点一次就可能好，所以是 retryable 而不是产品缺陷。
    NOTHING_CAPTURED: "RATE_LIMITED",
    MIRROR_TAB_CLOSED: "TAB_CLOSED",
    PLATFORM_SESSION_EXPIRED: "CREDENTIAL_EXPIRED",
    // gallery-dl 退出码 8：撞上验证码/风控。我们不绕，把人引回浏览器自己过。
    // 冻结词典里没有「验证码」这一条，落到最接近的 NOT_LOGGED_IN。
    CHALLENGE_REQUIRED: "NOT_LOGGED_IN",
    BILI_SIDECAR_BLOCKED: "SERVER_UNREACHABLE",
    ITEM_INGEST_FAILED: "SERVER_UNREACHABLE",
    // 「没归类的异常」的稳定兜底码。**不要用 Python 类名当失败码**：
    // 那是无限集合，词典追不上，界面只能说「我们没能记录下原因」。
    DESTINATION_PROBE_FAILED: "SERVER_UNREACHABLE",
    HEALTH_PROBE_FAILED: "SERVER_UNREACHABLE",
    JOB_FAILED: "SERVER_UNREACHABLE",
    CONNECTORERROR: "SERVER_UNREACHABLE",
    // ── 连接器 / OAuth / 各 worker（由 Python 侧同步而来）──
    // 这一批此前整层没进过表：界面会把它们显示成「我们没能记录下原因」，
    // 而原因就写在代码里。scripts/check_every_failure_code_is_explainable.py 扫出来的。
    CLI_WORKER_FAILED: "SERVER_UNREACHABLE",
    CLI_WORKER_COMMAND_FAILED: "SERVER_UNREACHABLE",
    COMMAND_FAILED: "SERVER_UNREACHABLE",
    COMMAND_TIMEOUT: "SERVER_UNREACHABLE",
    BILI_COMMAND_FAILED: "SERVER_UNREACHABLE",
    BILI_RATE_LIMITED: "RATE_LIMITED",
    INSTAGRAM_SESSION_OR_BINARY_MISSING: "NOT_LOGGED_IN",
    INSTAGRAM_SIDECAR_BLOCKED: "SERVER_UNREACHABLE",
    ACCOUNT_REAUTH_REQUIRED: "CREDENTIAL_EXPIRED",
    REDDIT_AUTH_MISSING: "REDDIT_NOT_AUTHORIZED",
    REDDIT_RATE_LIMITED: "RATE_LIMITED",
    INSTAGRAM_SESSION_PERMISSIONS: "NOT_LOGGED_IN",
    X_API_FAILED: "SERVER_UNREACHABLE",
    REDDIT_API_FAILED: "SERVER_UNREACHABLE",
    XHS_WORKER_FAILED: "SERVER_UNREACHABLE",
    WORKER_PROBE_OR_CALL_FAILED: "SERVER_UNREACHABLE",
    INSTALOADER_FAILED: "SERVER_UNREACHABLE",
    BILI_INVALID_RESPONSE: "SERVER_UNREACHABLE",
    OBSIDIAN_LOCAL_BRIDGE_FAILED: "SERVER_UNREACHABLE",
    X_AUTH_MISSING: "CREDENTIAL_EXPIRED",
    X_RATE_LIMITED: "RATE_LIMITED",
    // URL_NOT_SUPPORTED（退出码 32/64）**故意不在这里**：它是我们传错了 URL，
    // 给它任何别名都会变成一句「重试」，而重试一万次也一样。
    // 让它落到 UNEXPLAINED_ZERO 的「这是产品的问题…联系我们」，结论是对的。
    //
    // **INTERCEPT_PREFIX_UNKNOWN 原来就写在这一行**，别名成 SERVER_UNREACHABLE——
    // 紧挨着上面那三行「给它任何别名都会变成一句『重试』，而重试一万次也一样」。
    // 它的含义是「还没有确认这个平台的收藏接口地址」，和 URL_NOT_SUPPORTED
    // 是同一类。**解释就写在上一行，下一行照样踩进去。**
    // 2026-08-06 删掉，让它落到同一个兜底上。
    PLATFORM_PERMISSION_DENIED: "NOT_LOGGED_IN",
    OBSERVER_INSTALL_FAILED: "SERVER_UNREACHABLE",
    // ── B 站收藏夹取数（v0.0.0.7 / G1）。**必须和 failure_copy.py 的 _ALIASES 一字不差。**
    // 这两张表是同一份词典的两个副本，判据
    // test_both_alias_tables_say_exactly_the_same_thing 会逐条比对；
    // 只改一边的话，同一个失败码在插件里有话说、在资料库页面上却变成
    // 「我们没能记录下原因」。
    BILIBILI_NOT_LOGGED_IN: "NOT_LOGGED_IN",
    BILIBILI_FORBIDDEN: "NOT_LOGGED_IN",
    BILIBILI_NO_FOLDERS: "NOT_LOGGED_IN",
    BILIBILI_TAB_UNAVAILABLE: "TAB_CLOSED",
    BILIBILI_TAB_NOT_ON_PLATFORM: "TAB_CLOSED",
    BILIBILI_NETWORK_ERROR: "SERVER_UNREACHABLE",
    BILIBILI_HTTP_ERROR: "SERVER_UNREACHABLE"
  };

  /** 把一个失败码变成给人看的中文句子。认不出来也不能沉默。 */
  function failureSentence(code, platformLabel, count) {
    const key = String(code || "").trim().toUpperCase();
    if (!key) return null;
    const entry = failureCopy[key] || failureCopy[failureAliases[key]];
    if (!entry) {
      // 没见过的失败码**不能**当成没事——那正是 v0.0.0.6 的静默的零。
      return { text: "这次没有取到任何内容，而且我们没能记录下原因。这是产品的问题，请重试一次；如果还是这样，请联系我们。", action: "重试" };
    }
    return {
      text: entry.text.replace(/<平台>/g, platformLabel || "该平台").replace(/<N>/g, String(count || 0)),
      action: entry.action
    };
  }

  const destinationNames = {
    // **同一个东西三个名字**（2026-08-06）：资料库叫它「Social Archive」、
  // 扩展叫「我的档案馆」、设置页叫「主档案」。产品在别处一律叫「档案馆」
  // （全仓 54 处，其中面向用户的「我的档案馆」14 处；「主档案」只有 2 处，
  //   **而且我第一次数错了**：以为两处都在表里，其实一处在表里、一处是
  //   options.html 的正文「主档案与 Markdown 默认开启」。改完表之后拿真 Chrome
  //   打开设置页一读，页面上还留着那个词——**判据比的是三张表，看不见正文**。）
  // 对一个说自己没有技术基础的人，同一样东西三个名字就是三样东西。
  social_archive: "我的档案馆", markdown: "Markdown", notion: "Notion", obsidian: "Obsidian",
    github: "GitHub Private", karakeep: "Karakeep", linkwarden: "Linkwarden", archivebox: "ArchiveBox"
  };
  const destinationMarks = { markdown: "M", notion: "N", obsidian: "O", github: "G" };
  const MAX_SOCIAL_ARCHIVER_BUNDLE_BYTES = 200 * 1024 * 1024;
  const PRODUCT_VERSION = "0.0.0.17";

  const columns = [
    { key: "check", label: "", cls: "col-check sticky-left", required: true, sortable: false },
    { key: "platform", label: "平台", cls: "col-platform sticky-left", required: true, sortable: true, api: "platform" },
    { key: "savedAt", label: "时间", cls: "col-time", required: true, sortable: true, api: "time" },
    { key: "relation", label: "关系", cls: "col-relation", required: false, sortable: true, api: "relation" },
    { key: "topic", label: "主题分类", cls: "col-topic", required: true, sortable: true, api: "topic" },
    { key: "keywords", label: "关键词", cls: "col-keywords", required: true, sortable: true, api: "keywords" },
    { key: "content", label: "内容", cls: "col-content", required: true, sortable: true, api: "content" },
    { key: "author", label: "作者", cls: "col-author", required: false, sortable: true, api: "author" },
    { key: "collection", label: "收藏夹", cls: "col-collection", required: false, sortable: true, api: "collection" },
    { key: "media", label: "媒体", cls: "col-media", required: false, sortable: true, api: "media" },
    { key: "archive", label: "归档状态", cls: "col-archive", required: false, sortable: true, api: "archive" },
    { key: "export", label: "自动导出", cls: "col-export", required: false, sortable: false },
    { key: "url", label: "链接", cls: "col-link", required: true, sortable: true, api: "link" },
    { key: "publishedAt", label: "发布时间", cls: "col-published", required: false, sortable: true, defaultHidden: true, api: "published" },
    { key: "account", label: "来源账号", cls: "col-account", required: false, sortable: true, defaultHidden: true, api: "account" },
    { key: "syncedAt", label: "最近同步", cls: "col-synced", required: false, sortable: true, defaultHidden: true, api: "synced" }
  ];

  const state = {
    rows: [], total: 0, facets: { platforms: [], topics: [] }, platformCounts: {},
    accounts: [], syncRuns: [], destinations: [], serviceReady: false,
    // 登录身份（v0.0.0.7 / T02）。null = 未登录，登录闸会盖住整页。
    user: null,
    // 发起登录必须去的那个域（回调地址登记在它上面）。见 startLogin。
    loginBase: "",
    // 每个平台「现在同步得动吗」，来自服务端。见 renderSyncTable。
    platformSupport: {},
    extension: { detected: false, paired: false, compatible: false, version: "", pairingRequired: false, oneTimeCodeAvailable: false, refreshedAt: null },
    platform: "all", group: true, sortKey: "savedAt", sortDir: "desc", search: "",
    filters: { relation: "all", topic: "all", collection: "all", date: "all", archive: "all" },
    visibleColumns: new Set(columns.filter(column => !column.defaultHidden).map(column => column.key)),
    selected: new Set(), collapsedGroups: new Set(), detailRow: null,
    page: 1, pageSize: 50, loading: false
  };

  const dateFormatter = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  const fullDateFormatter = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });

  /** 见 shared.js 里的同名函数——两侧规则一致：界面上不出现英文错误码。 */
  function humanMessage(detail, status) {
    const text = String(detail || "").trim();
    if (text && /[\u4e00-\u9fff]/.test(text)) return text;
    if (status === 401 || status === 403) return "登录状态已失效，请重新登录。";
    if (status === 404) return "这个功能在当前版本还不可用。";
    if (status === 429) return "请求太频繁，已自动放慢，稍后会继续。";
    if (status >= 500) return "服务器暂时出了点问题。你的数据没有丢，请稍后重试。";
    return "暂时连不上服务器。你的数据没有丢，请重试。";
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeoutMs || 20000);
    try {
      const response = await fetch(path, { ...options, headers, signal: controller.signal, credentials: "same-origin" });
      const text = await response.text();
      let payload = {};
      try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = { detail: text }; }
      if (!response.ok) {
        // 同 shared.js：payload.detail 缺失或不是中文时不能把它原样甩给用户。
        // FastAPI 未处理异常的默认 detail 是英文的 "Internal Server Error"。
        const error = new Error(humanMessage(payload.detail, response.status));
        error.status = response.status;
        throw error;
      }
      return payload;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("请求超时，请稍后重试");
      throw error;
    } finally { clearTimeout(timer); }
  }

  function platformLogo(platform, extra = "") {
    const meta = platformMeta[platform] || platformMeta.web;
    return `<span class="platform-logo ${meta.cls} ${extra}">${escapeHtml(meta.short)}</span>`;
  }
  function formatDate(value, full = false) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return (full ? fullDateFormatter : dateFormatter).format(date).replaceAll("/", "-");
  }
  function relationClass(value) { return value === "收藏" ? "saved" : value === "点赞" ? "liked" : value === "书签" ? "bookmark" : "watch"; }
  function archiveClass(value) { return value === "完整" ? "ok" : value === "处理中" ? "pending" : "issue"; }
  function archiveLabel(value) { return value === "完整" ? "L0/L1/L3 完整" : value === "处理中" ? "媒体处理中" : value === "仅元数据" ? "L0/L1 已保存" : "需要处理"; }
  function normalizeRow(item) {
    const platform = serverToUiPlatform[item.platform] || "web";
    const relations = Array.isArray(item.relations) && item.relations.length ? item.relations : [item.primary_relation].filter(Boolean);
    const relation = relationLabels[item.primary_relation] || relationLabels[relations[0]] || item.primary_relation || "收藏";
    const collections = Array.isArray(item.collections) ? item.collections.filter(Boolean) : [];
    const exportDestinations = Array.isArray(item.export_destinations) ? item.export_destinations : [];
    return {
      id: String(item.id), platform, savedAt: item.relation_time || item.last_observed_at,
      publishedAt: item.published_at, relation, relationRaw: item.primary_relation,
      topic: item.topic || "未分类", keywords: Array.isArray(item.keywords) ? item.keywords : [],
      title: item.title || "无标题内容", content: item.summary || "已保留结构化关系、原始链接和归档信息。",
      author: item.author_name || "未知作者", collection: item.primary_collection || collections.join("、") || "未分组",
      media: Number(item.media_count || item.artifact_count || 0), archive: item.archive_status || "仅元数据",
      export: exportDestinations.map(id => destinationMarks[id]).filter(Boolean), exportDestinations,
      url: safeUrl(item.canonical_url), account: item.account_name || "未标记账号", syncedAt: item.last_synced_at || item.last_observed_at,
      raw: item
    };
  }

  function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span class="dot"></span><span>${escapeHtml(message)}</span>`;
    $("toastStack").appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(8px)";
      setTimeout(() => toast.remove(), 220);
    }, 3000);
  }

  function setServiceBadge(stateName, text) {
    const badge = $("serviceBadge");
    badge.className = `service-badge ${stateName}`;
    badge.textContent = text;
  }

  async function loadHealth() {
    try {
      const health = await api("/health", { timeoutMs: 5000 });
      state.serviceReady = health.status === "ok";
      setServiceBadge("connected", `私人档案馆已连接 · v${health.version || PRODUCT_VERSION}`);
      // 存储吃紧时要**主动**说，别等用户发现媒体没下下来才去猜。
      //
      // 冻结词典里本来就有 DISK_QUOTA 那一句（「存储空间快满了，已经暂停
      // 下载媒体文件，文字和链接还在正常保存。」），而 /v1/storage/status
      // **此前没有任何界面在调**——服务端算得出来，用户看不到。
      // 这是「建好了没接上」的第 6 次，由 scripts/find_endpoints_no_client_calls.py 扫出来。
      //
      // 只在真的吃紧时改徽标：不吃紧就不打扰。接口自带 message_zh，
      // 我们不另造句子（造句子等于绕过冻结词典）。
      try {
        const storage = await api("/v1/storage/status", { timeoutMs: 5000 });
        if (storage && storage.l3_allowed === false && storage.message_zh) {
          setServiceBadge("degraded", storage.message_zh);
        }
      } catch (_) {
        // 存储状态取不到不该把「档案馆已连接」这条也弄没了——它是附加信息。
      }
    } catch (error) {
      state.serviceReady = false;
      setServiceBadge("error", "私人档案馆暂时不可用");
      throw error;
    }
  }

  function buildLibraryQuery() {
    const params = new URLSearchParams();
    if (state.search.trim()) params.set("q", state.search.trim());
    if (state.platform !== "all") params.set("platform", platformMeta[state.platform].server);
    if (state.filters.relation !== "all") params.set("relation", relationApiValues[state.filters.relation] || state.filters.relation);
    if (state.filters.topic !== "all") params.set("topic", state.filters.topic);
    // 收藏夹用**库里存的那个 key**（B 站是媒体 id），不是显示名——
    // 拿显示名去筛什么都筛不出来。
    if (state.filters.collection !== "all") params.set("collection", state.filters.collection);
    if (state.filters.archive !== "all") {
      const archive = { "完整": "完整", "处理中": "处理中", "需处理": "仅元数据" }[state.filters.archive];
      if (archive) params.set("archive", archive);
    }
    if (state.filters.date !== "all") {
      const date = new Date(Date.now() - Number(state.filters.date) * 86400000);
      params.set("after", date.toISOString());
    }
    const column = columns.find(item => item.key === state.sortKey);
    params.set("sort_by", column?.api || "time");
    params.set("sort_dir", state.sortDir);
    params.set("limit", String(state.pageSize));
    params.set("offset", String((state.page - 1) * state.pageSize));
    return params;
  }

  async function loadLibrary({ resetPage = false } = {}) {
    if (resetPage) state.page = 1;
    state.loading = true;
    document.querySelector(".table-card")?.classList.add("loading");
    updateEmptyState("loading");
    try {
      const result = await api(`/v1/library?${buildLibraryQuery().toString()}`);
      state.rows = (result.items || []).map(normalizeRow);
      state.total = Number(result.total || 0);
      state.facets = result.facets || { platforms: [], topics: [] };
      if (state.platform === "all") {
        state.platformCounts = Object.fromEntries((state.facets.platforms || []).map(item => [item.platform, Number(item.count || 0)]));
      }
      const maxPage = Math.max(1, Math.ceil(state.total / state.pageSize));
      if (state.page > maxPage) { state.page = maxPage; return loadLibrary(); }
      renderPlatformTabs();
      renderTopicOptions();
      renderCollectionOptions();
      renderRelationOptions();
      renderTable();
      renderPagination();
      updateEmptyState(state.total ? "ready" : "empty");
    } catch (error) {
      state.rows = [];
      state.total = 0;
      renderTable();
      renderPagination();
      updateEmptyState("error", error.message);
      showToast(`资料库读取失败：${error.message}`, "error");
    } finally {
      state.loading = false;
      document.querySelector(".table-card")?.classList.remove("loading");
    }
  }

  async function loadAccountsAndDestinations() {
    const [accountsResult, runsResult, destinationsResult] = await Promise.all([
      api("/v1/accounts"), api("/v1/sync-runs?limit=200"), api("/v1/destinations")
    ]);
    state.accounts = accountsResult.items || [];
    // 能不能同步由**服务端**说了算，界面照着画（见 account_sync.SYNCABLE_NOW）。
    // 两个前端各维护一份「哪些平台能同步」必然漂开，那是又一处「看着接上了」。
    state.platformSupport = Object.fromEntries(
      (accountsResult.supported_platforms || []).map(item => [item.platform, item]));
    state.syncRuns = runsResult.items || [];
    state.destinations = destinationsResult.items || [];
    renderSyncSummary();
    renderSyncTable();
    renderNextStep();
    renderDestinationsModal();
  }

  /** 下一步：**永远只显示一件事**（v0.0.0.7 / INV-ZERO-BARRIER）。
   *
   * Owner 的原话：「我都不知道应该怎么操作」。首页此前把状态、账号表、
   * 导出、设置一起摊开，没有任何东西说"现在该干嘛"。
   *
   * 规则：按顺序找到**第一个**没做完的事，只显示它；全做完就什么也不显示。
   * 不排优先级、不并列、不给第二个选项——多给一个选择就是多一次犹豫。
   */
  function renderNextStep() {
    const box = $("nextStep");
    const steps = [
      {
        need: () => !state.extension.detected,
        title: "第 1 步：安装浏览器插件",
        why: "收藏内容要从你自己的浏览器里读，所以需要这个插件。装好后页面会自动认出来并带你回来。",
        action: "去安装",
        run: () => { location.href = "/extension-install"; },
      },
      {
        need: () => state.extension.detected && !state.extension.compatible,
        title: "第 1 步：更新浏览器插件",
        why: `装着的是 v${state.extension.version || "未知"}，需要 v${PRODUCT_VERSION}。`,
        action: "去更新",
        run: () => { location.href = "/extension-install"; },
      },
      {
        need: () => state.extension.detected && state.extension.compatible && !state.extension.paired,
        title: "第 2 步：连接插件",
        why: "点一下就好，你不需要输入任何字符。",
        action: "连接",
        run: async () => { if (await connectExtension()) { showToast("插件已连接。"); await refreshEverything(); } },
      },
      {
        need: () => !state.accounts.some(item =>
          ["connected", "degraded"].includes(item.connection_state)
          && state.platformSupport[item.platform]?.sync_supported !== false),
        title: "第 3 步：连接一个能同步的来源",
        // **这句话原来是硬编码的**：「本版本能自动同步的是 Chrome 书签，
        // 以及连接后的 X / Instagram。小红书、抖音、B站、快手暂时还不能自动读取。」
        //
        // 2026-08-05 实测：X 与 Instagram **都同步不了**（X 被零费用门关着，
        // Instagram 的授权那一步没有 Owner 点得到的界面），两个都已经在
        // NOT_SYNCABLE_YET 里。**这句文案比能力声明晚了整整一轮。**
        //
        // 这是同一种病的第五处，也是**第一处靠搜索找出来的**（前四处
        // 要么是 Owner 撞出来的，要么是我给别的事取证时顺手撞见的）。
        // 搜的是「乐观措辞 + 中文」的用户可见串，47 处里就这一处在撒谎。
        //
        // 现在从 state.platformSupport 现算，永远不会再漂。
        why: (() => {
          const names = Object.entries(state.platformSupport || {})
            .filter(([, support]) => support?.sync_supported !== false)
            .map(([id]) => platformMeta[serverToUiPlatform[id]]?.label || id);
          return names.length
            ? `本版本能自动同步的是：${names.join("、")}。其余平台可以用插件一条条保存。`
            : "本版本还没有能自动同步的平台。可以用插件把看到的内容一条条保存进来。";
        })(),
        action: "去连接",
        run: () => openSyncModal(),
      },
      {
        need: () => !state.syncRuns.some(run => ["completed", "partial"].includes(run.status)),
        title: "第 4 步：同步一次",
        why: "把已连接来源里的收藏拉进档案馆。之后它会按周期自己跑。",
        action: "立即同步全部",
        run: () => syncAllAccounts(),
      },
    ];
    const step = steps.find(item => {
      try { return item.need(); } catch (_) { return false; }
    });
    if (!step) { box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    $("nextStepTitle").textContent = step.title;
    $("nextStepWhy").textContent = step.why;
    const button = $("nextStepAction");
    button.textContent = step.action;
    button.onclick = () => { Promise.resolve(step.run()).catch(error => showToast(error.message, "error")); };
  }

  async function refreshEverything() {
    await Promise.allSettled([loadAccountsAndDestinations(), refreshExtensionStatus()]);
    renderNextStep();
  }

  function renderSyncSummary() {
    const connected = state.accounts.filter(item => ["connected", "degraded"].includes(item.connection_state)).length;
    const active = state.syncRuns.filter(item => ["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(item.status));
    const failures = state.syncRuns.filter(item => ["failed", "blocked_environment"].includes(item.status));
    // **「已连接」不等于「同步得动」。**
    //
    // Owner 有三个已连接账号（小红书/抖音/B站），顶部却写着「3 个账号已连接」，
    // 读起来像一切正常——而那三个在本版本一条都同步不了。他的原话是
    // 「不知道应该怎么操作」。这里必须把这个差别说出来，而不是让人点了才发现。
    const syncable = state.accounts.filter(item =>
      ["connected", "degraded"].includes(item.connection_state)
      && state.platformSupport[item.platform]?.sync_supported !== false).length;
    const stuck = connected - syncable;
    $("connectedAccountCount").textContent = stuck > 0
      ? `${connected} 个账号已连接，其中 ${stuck} 个本版本还不能自动同步`
      : `${connected} 个账号已连接`;
    if (stuck > 0 && !syncable) {
      // 一个都同步不动时，顶部只说一件事：**现在真正能做的那一件**。
      $("syncSummaryText").textContent =
        " · 现在可以：在浏览器里打开任意一条内容，点插件的「保存到我的档案馆」；"
        + "或连接 Chrome 书签一次性导入。";
      document.querySelector(".sync-strip")?.classList.add("needs");
      return;
    }
    if (!state.accounts.length) {
      $("syncSummaryText").textContent = " · 连接一次账号后自动全量导入收藏、点赞和书签";
      document.querySelector(".sync-strip")?.classList.add("needs");
      return;
    }
    document.querySelector(".sync-strip")?.classList.toggle("needs", Boolean(failures.length));
    document.querySelector(".sync-strip")?.classList.remove("error");
    if (active.length) {
      const imported = active.reduce((sum, run) => sum + Number(run.imported_count || 0), 0);
      const discovered = active.reduce((sum, run) => sum + Number(run.discovered_count || 0), 0);
      $("syncSummaryText").textContent = ` · ${active.length} 个同步任务正在运行 · 已导入 ${imported}/${discovered || "…"} 条`;
    } else if (failures.length) {
      // 不只说"有几个失败了"，把**为什么**说出来（T14 / INV-NO-SILENT-ZERO）。
      const worst = failures.find(run => run.last_error_code) || failures[0];
      const label = platformMeta[serverToUiPlatform[worst?.platform]]?.label || "";
      const sentence = failureSentence(worst?.last_error_code, label, worst?.imported_count);
      $("syncSummaryText").textContent = sentence
        ? ` · ${sentence.text}${failures.length > 1 ? `（另有 ${failures.length - 1} 个账号也需要处理，其他不受影响）` : ""}`
        : ` · ${failures.length} 个账号需要重新连接，其他账号不受影响`;
    } else {
      const lastSync = state.accounts.map(item => item.last_sync_at).filter(Boolean).sort().at(-1);
      $("syncSummaryText").textContent = lastSync ? ` · 最近同步 ${formatDate(lastSync, true)}` : " · 首次同步尚未开始";
    }
  }

  function renderPlatformTabs() {
    const countFor = key => {
      if (key === "all") return Object.values(state.platformCounts).reduce((sum, value) => sum + Number(value || 0), 0) || state.total;
      return Number(state.platformCounts[platformMeta[key].server] || 0);
    };
    $("platformTabs").innerHTML = platformOrder.map(key => {
      const meta = platformMeta[key];
      return `<button class="platform-tab ${state.platform === key ? "active" : ""}" data-platform="${key}">${platformLogo(key)}<span>${escapeHtml(meta.label)}</span><span class="count">${countFor(key).toLocaleString("zh-CN")}</span></button>`;
    }).join("");
    document.querySelectorAll(".platform-tab").forEach(button => button.addEventListener("click", () => {
      state.platform = button.dataset.platform;
      state.group = state.platform === "all";
      $("groupBtn").classList.toggle("active", state.group);
      $("groupBtn").setAttribute("aria-pressed", String(state.group));
      state.selected.clear();
      loadLibrary({ resetPage: true });
    }));
  }

  /** 关系筛选照真实数据重建（v0.0.0.7 / T15）。
   *
   * **此前它是写死的四个，而且没有任何代码去重建它。**
   * 2026-08-06 对着生产量：书签 0 条、稍后再看 1 条，
   * 而最大的那一组「观看历史」71 条（193 条里的 37%）**根本不在名单上**——
   * Owner 没法筛出自己最大的那一堆。主题那个筛选早就照 facet 重建了，
   * 这个一直没跟上。
   */
  function renderRelationOptions() {
    const select = $("relationFilter");
    if (!select) return;
    const current = state.filters.relation;
    const relations = (state.facets.relations || []).map(item => item.relation).filter(Boolean);
    if (!relations.length) return;           // 还没读到数据时别把它清空
    select.innerHTML = `<option value="all">全部关系</option>${relations.map(value =>
      `<option value="${escapeHtml(value)}">${escapeHtml(relationLabels[value] || value)}</option>`).join("")}`;
    select.value = relations.includes(current) ? current : "all";
    if (select.value !== current) state.filters.relation = "all";
  }

  /** 收藏夹筛选（v0.0.0.10）。**整栏由真实数据重建，没有收藏夹就整个藏起来。**
   *
   * 藏起来是有意的：绝大多数平台本来就没有收藏夹的概念，永远显示一个
   * 只有「全部收藏夹」一项的下拉框，是在界面上摆一个点了没用的东西。
   *
   * value 用 key（库里存的媒体 id），显示用 label（「学习」）——
   * 两者混淆的话，他点了一个看得懂的名字，却筛不出任何东西。
   */
  function renderCollectionOptions() {
    const select = $("collectionFilter");
    const field = $("collectionField");
    if (!select || !field) return;
    const collections = (state.facets.collections || []).filter(item => item.key);
    field.hidden = collections.length === 0;
    if (!collections.length) {
      state.filters.collection = "all";
      return;
    }
    const current = state.filters.collection;
    select.innerHTML = `<option value="all">全部收藏夹</option>${collections.map(item =>
      `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label || item.key)}（${Number(item.count || 0)}）</option>`).join("")}`;
    select.value = collections.some(item => item.key === current) ? current : "all";
    if (select.value !== current) state.filters.collection = "all";
  }

  function renderTopicOptions() {
    const select = $("topicFilter");
    const current = state.filters.topic;
    const topics = (state.facets.topics || []).map(item => item.topic).filter(Boolean);
    select.innerHTML = `<option value="all">全部主题</option>${topics.map(topic => `<option value="${escapeHtml(topic)}">${escapeHtml(topic)}</option>`).join("")}`;
    select.value = topics.includes(current) ? current : "all";
    if (select.value !== current) state.filters.topic = "all";
  }

  function renderHead() {
    $("tableHead").innerHTML = columns.filter(column => state.visibleColumns.has(column.key)).map(column => {
      if (column.key === "check") return `<th class="${column.cls}"><input id="selectAll" type="checkbox" aria-label="选择当前页全部内容"></th>`;
      return `<th class="${column.cls} ${column.sortable ? "sortable" : ""} ${state.sortKey === column.key ? "sorted" : ""}" ${column.sortable ? `data-sort="${column.key}"` : ""}><span class="th-content">${escapeHtml(column.label)}${column.sortable ? svg.sort : ""}</span></th>`;
    }).join("");
    document.querySelectorAll("th[data-sort]").forEach(header => header.addEventListener("click", () => {
      const key = header.dataset.sort;
      if (state.sortKey === key) state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      else {
        state.sortKey = key;
        state.sortDir = ["savedAt", "publishedAt", "syncedAt", "media"].includes(key) ? "desc" : "asc";
      }
      updateSortLabel();
      loadLibrary({ resetPage: true });
    }));
    $("selectAll")?.addEventListener("change", event => {
      state.rows.forEach(row => event.target.checked ? state.selected.add(row.id) : state.selected.delete(row.id));
      renderTable();
    });
  }

  function cellHtml(row, key) {
    const meta = platformMeta[row.platform] || platformMeta.web;
    switch (key) {
      case "check": return `<td class="col-check sticky-left"><input class="row-check" data-id="${escapeHtml(row.id)}" type="checkbox" aria-label="选择 ${escapeHtml(row.title)}" ${state.selected.has(row.id) ? "checked" : ""}></td>`;
      case "platform": return `<td class="col-platform sticky-left"><div class="platform-cell">${platformLogo(row.platform)}<span>${escapeHtml(meta.label)}</span></div></td>`;
      case "savedAt": return `<td class="col-time"><div class="time-cell">${escapeHtml(formatDate(row.savedAt))}<small>${escapeHtml(row.relation)}时间</small></div></td>`;
      case "relation": return `<td class="col-relation"><span class="relation-badge ${relationClass(row.relation)}">${escapeHtml(row.relation)}</span></td>`;
      case "topic": return `<td class="col-topic"><span class="topic-badge">${escapeHtml(row.topic)}</span></td>`;
      case "keywords": return `<td class="col-keywords"><div class="keyword-list">${row.keywords.length ? row.keywords.map(keyword => `<span class="keyword">${escapeHtml(keyword)}</span>`).join("") : '<span class="keyword">未标记</span>'}</div></td>`;
      case "content": return `<td class="col-content"><div class="content-cell"><div class="content-title" title="${escapeHtml(row.title)}">${escapeHtml(row.title)}</div><div class="content-summary">${escapeHtml(row.content)}</div></div></td>`;
      case "author": return `<td class="col-author"><div class="author-cell"><span class="avatar">${escapeHtml(row.author.slice(0, 1).toUpperCase())}</span><span title="${escapeHtml(row.author)}">${escapeHtml(row.author)}</span></div></td>`;
      case "collection": return `<td class="col-collection"><div class="collection-cell" title="${escapeHtml(row.collection)}">${escapeHtml(row.collection)}</div></td>`;
      case "media": return `<td class="col-media"><div class="media-cell">${svg.media}<span>${row.media}</span></div></td>`;
      case "archive": return `<td class="col-archive"><span class="status-pill ${archiveClass(row.archive)}">${escapeHtml(archiveLabel(row.archive))}</span></td>`;
      case "export": return `<td class="col-export"><div class="export-dots">${["M", "N", "O", "G"].map(mark => `<span class="export-dot ${row.export.includes(mark) ? "done" : ""}" title="${({ M: "Markdown", N: "Notion", O: "Obsidian", G: "GitHub" })[mark]}">${mark}</span>`).join("")}</div></td>`;
      case "url": {
        const host = row.url === "#" ? "不可用" : new URL(row.url).hostname.replace("www.", "").split(".")[0];
        return `<td class="col-link"><a class="link-btn" href="${escapeHtml(row.url)}" target="_blank" rel="noopener" data-stop-row>${escapeHtml(host)} ${svg.external}</a></td>`;
      }
      case "publishedAt": return `<td class="col-published"><div class="time-cell">${escapeHtml(formatDate(row.publishedAt))}<small>发布时间</small></div></td>`;
      case "account": return `<td class="col-account">${escapeHtml(row.account)}</td>`;
      case "syncedAt": return `<td class="col-synced"><div class="time-cell">${escapeHtml(formatDate(row.syncedAt))}<small>最近同步</small></div></td>`;
      default: return "";
    }
  }

  function rowHtml(row, activeColumns) {
    return `<tr class="data-row ${state.selected.has(row.id) ? "selected" : ""}" tabindex="0" data-row-id="${escapeHtml(row.id)}">${activeColumns.map(column => cellHtml(row, column.key)).join("")}</tr>`;
  }

  function renderTable() {
    renderHead();
    $("visibleCount").textContent = String(state.rows.length);
    $("totalCount").textContent = state.total.toLocaleString("zh-CN");
    const activeColumns = columns.filter(column => state.visibleColumns.has(column.key));
    let html = "";
    if (state.group && state.platform === "all") {
      platformOrder.filter(key => key !== "all").forEach(platform => {
        const groupRows = state.rows.filter(row => row.platform === platform);
        if (!groupRows.length) return;
        const collapsed = state.collapsedGroups.has(platform);
        const account = state.accounts.find(item => serverToUiPlatform[item.platform] === platform);
        const accountStatus = account ? connectionLabels[account.connection_state] || account.connection_state : "未连接账号";
        html += `<tr class="group-row"><td colspan="${activeColumns.length}"><div class="group-line">${platformLogo(platform)}<span>${escapeHtml(platformMeta[platform].label)}</span><span class="group-count">本页 ${groupRows.length} 条 · 平台共 ${Number(state.platformCounts[platformMeta[platform].server] || groupRows.length).toLocaleString("zh-CN")} 条</span><span class="group-spacer"></span><span class="group-sync"><span class="pulse" style="width:6px;height:6px;box-shadow:none"></span>${escapeHtml(accountStatus)}</span><button class="group-collapse ${collapsed ? "collapsed" : ""}" data-collapse="${platform}" aria-label="折叠 ${escapeHtml(platformMeta[platform].label)}">${svg.chevron}</button></div></td></tr>`;
        if (!collapsed) groupRows.forEach(row => { html += rowHtml(row, activeColumns); });
      });
    } else {
      state.rows.forEach(row => { html += rowHtml(row, activeColumns); });
    }
    $("tableBody").innerHTML = html;
    bindRows();
    updateBulkBar();
    const selectAll = $("selectAll");
    if (selectAll) selectAll.checked = Boolean(state.rows.length && state.rows.every(row => state.selected.has(row.id)));
  }

  function bindRows() {
    document.querySelectorAll(".group-collapse").forEach(button => button.addEventListener("click", event => {
      event.stopPropagation();
      const platform = button.dataset.collapse;
      state.collapsedGroups.has(platform) ? state.collapsedGroups.delete(platform) : state.collapsedGroups.add(platform);
      renderTable();
    }));
    document.querySelectorAll(".row-check").forEach(checkbox => {
      checkbox.addEventListener("click", event => event.stopPropagation());
      checkbox.addEventListener("change", () => {
        checkbox.checked ? state.selected.add(checkbox.dataset.id) : state.selected.delete(checkbox.dataset.id);
        renderTable();
      });
    });
    document.querySelectorAll("[data-stop-row]").forEach(link => link.addEventListener("click", event => event.stopPropagation()));
    document.querySelectorAll(".data-row").forEach(row => {
      const open = () => openDetail(row.dataset.rowId);
      row.addEventListener("click", open);
      row.addEventListener("keydown", event => {
        if (["Enter", " "].includes(event.key)) { event.preventDefault(); open(); }
      });
    });
  }

  function updateEmptyState(mode, detail = "") {
    const empty = $("emptyState");
    const title = $("emptyTitle");
    const copy = $("emptyCopy");
    const button = $("emptyConnectAccount");
    if (mode === "ready") { empty.classList.remove("show"); return; }
    empty.classList.add("show");
    if (mode === "loading") {
      title.textContent = "正在读取资料库";
      copy.textContent = "正在加载最新同步结果。";
      button.hidden = true;
    } else if (mode === "error") {
      title.textContent = "暂时无法读取资料库";
      copy.textContent = detail || "请稍后重试。";
      button.hidden = false;
      button.textContent = "重新加载";
      button.dataset.action = "retry";
    } else if (!state.accounts.length) {
      title.textContent = "连接账号后，收藏内容会自动出现在这里";
      copy.textContent = "无需逐条打开帖子。连接一次账号即可开始首次全量同步。";
      button.hidden = false;
      button.textContent = "连接第一个账号";
      button.dataset.action = "connect";
    } else {
      title.textContent = state.search || Object.values(state.filters).some(value => value !== "all") ? "没有符合条件的内容" : "账号已经连接，正在等待首次同步结果";
      copy.textContent = state.search || Object.values(state.filters).some(value => value !== "all") ? "清除搜索或筛选条件后再试。" : "打开账号同步中心查看进度或立即同步。";
      button.hidden = false;
      button.textContent = "查看账号同步";
      button.dataset.action = "sync";
    }
  }

  function renderPagination() {
    const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    $("pageInfo").textContent = `第 ${state.page} / ${pages} 页`;
    $("prevPage").disabled = state.page <= 1;
    $("nextPage").disabled = state.page >= pages;
    $("pageSizeCopy").textContent = `每页 ${state.pageSize} 条`;
  }

  function updateBulkBar() {
    $("bulkCount").textContent = String(state.selected.size);
    $("bulkBar").classList.toggle("open", state.selected.size > 0);
  }

  function updateSortLabel() {
    const column = columns.find(item => item.key === state.sortKey);
    $("sortBtnLabel").textContent = `${column?.label || "排序"} · ${state.sortDir === "desc" ? "降序" : "升序"}`;
    renderSortPopover();
  }

  async function openDetail(id) {
    const row = state.rows.find(item => item.id === id);
    if (!row) return;
    state.detailRow = row;
    $("drawerPlatformLogo").innerHTML = platformLogo(row.platform);
    $("drawerHeaderTitle").textContent = row.title;
    $("drawerHeaderMeta").textContent = `${platformMeta[row.platform].label} · ${row.relation} · ${formatDate(row.savedAt, true)}`;
    $("drawerOpenLink").href = row.url;
    renderDetailContent(row);
    $("drawerBackdrop").classList.add("open");
    $("detailDrawer").classList.add("open");
    $("closeDrawer").focus();
    try {
      const detail = await api(`/v1/library/${encodeURIComponent(id)}`);
      row.detail = detail;
      renderDetailContent(row);
    } catch (_) { /* The table row is already sufficient for a useful detail view. */ }
  }

  function renderDetailContent(row) {
    const artifacts = row.detail?.artifacts || [];
    const receipts = row.detail?.destination_receipts || [];
    $("drawerContent").innerHTML = `
      <h2 class="drawer-title">${escapeHtml(row.title)}</h2>
      <div class="drawer-badges"><span class="relation-badge ${relationClass(row.relation)}">${escapeHtml(row.relation)}</span><span class="topic-badge">${escapeHtml(row.topic)}</span>${row.keywords.map(keyword => `<span class="keyword">${escapeHtml(keyword)}</span>`).join("")}</div>
      <div class="drawer-section"><h3>内容</h3><div class="drawer-text">${escapeHtml(row.content)}</div></div>
      <div class="drawer-section"><h3>关键信息</h3><div class="meta-grid">
        <div class="meta-item"><span>平台</span><strong>${escapeHtml(platformMeta[row.platform].label)}</strong></div>
        <div class="meta-item"><span>来源账号</span><strong>${escapeHtml(row.account)}</strong></div>
        <div class="meta-item"><span>${escapeHtml(row.relation)}时间</span><strong>${escapeHtml(formatDate(row.savedAt, true))}</strong></div>
        <div class="meta-item"><span>发布时间</span><strong>${escapeHtml(formatDate(row.publishedAt, true))}</strong></div>
        <div class="meta-item"><span>作者</span><strong>${escapeHtml(row.author)}</strong></div>
        <div class="meta-item"><span>收藏夹</span><strong>${escapeHtml(row.collection)}</strong></div>
        <div class="meta-item"><span>归档状态</span><strong>${escapeHtml(archiveLabel(row.archive))}</strong></div>
        <div class="meta-item"><span>最近同步</span><strong>${escapeHtml(formatDate(row.syncedAt, true))}</strong></div>
      </div></div>
      <div class="drawer-section"><h3>归档文件 · ${artifacts.length || row.media} 项</h3><div class="media-grid">${(artifacts.length || row.media) ? Array.from({ length: Math.min(artifacts.length || row.media, 3) }, (_, index) => `<div class="media-thumb" data-label="${escapeHtml(artifacts[index]?.artifact_type || (index === 0 ? "封面" : `媒体 ${index + 1}`))}"></div>`).join("") : '<div style="color:var(--text-3)">该条内容当前只有结构化信息与原始链接。</div>'}</div></div>
      <div class="drawer-section"><h3>自动导出</h3><div class="export-dots">${["M", "N", "O", "G"].map(mark => `<span class="export-dot ${row.export.includes(mark) ? "done" : ""}">${mark}</span>`).join("")}<span style="margin-left:6px;color:var(--text-3);font-size:12px">${receipts.length ? `${receipts.length} 个真实回执` : "尚无已完成回执"}</span></div>${renderReceiptList(receipts)}</div>`;
    document.querySelectorAll("[data-retry-receipt]").forEach(button => button.addEventListener("click", () => retryReceipt(button.dataset.retryReceipt, button)));
  }

  /** 失败的目的地回执要能**在界面上**重试（v0.0.0.7 / T14）。
   *
   * 此前这里只显示一个数字「N 个真实回执」——失败了也只是让这个数变大，
   * 既说不出是哪个目的地失败、也没有任何补救动作。而服务端的
   * `POST /v1/destinations/receipts/{id}/retry` 一直开着，**全仓唯一的
   * 调用方是验收脚本 browser_acceptance.py**：能被测试驱动，用户点不到。
   *
   * 冻结词典里那句「[ 重试 ]」指的就是这类动作。文案许诺了一个动作，
   * 界面上却没有对应的按钮，这条承诺就是假的。
   */
  function renderReceiptList(receipts) {
    if (!receipts.length) return "";
    const rows = receipts.map(receipt => {
      const status = String(receipt.status || "");
      const name = destinationNames[receipt.destination_id] || receipt.destination_id;
      const label = { done: "已写入", noop: "无需写入", failed: "写入失败" }[status] || status;
      // 只有失败的才给重试。服务端对非 failed 的回执返回 409，
      // 在界面上就该是"根本没有这颗按钮"，而不是点了才被拒绝。
      const button = status === "failed"
        ? `<button class="btn small" data-retry-receipt="${escapeHtml(receipt.id)}">重试</button>`
        : "";
      return `<div class="receipt-row"><span>${escapeHtml(name)}</span>`
        + `<span class="muted">${escapeHtml(label)}${receipt.message_zh ? ` · ${escapeHtml(receipt.message_zh)}` : ""}</span>`
        + `${button}</div>`;
    });
    return `<div class="receipt-list">${rows.join("")}</div>`;
  }

  async function retryReceipt(receiptId, button) {
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "正在重试…";
    try {
      const result = await api(`/v1/destinations/receipts/${encodeURIComponent(receiptId)}/retry`, { method: "POST" });
      showToast(result?.message_zh || "已重新排队，稍后会自动完成。");
      await loadLibrary();
    } catch (error) {
      showToast(error.message || "重试失败，请稍后再试。", "error");
      button.disabled = false;
      button.textContent = original;
    }
  }

  function closeDetail() {
    $("drawerBackdrop").classList.remove("open");
    $("detailDrawer").classList.remove("open");
    state.detailRow = null;
  }

  function renderColumnsPopover() {
    const popover = $("columnsPopover");
    popover.innerHTML = `<div class="popover-title"><span>显示列</span><span class="popover-subtitle">必需列不可隐藏</span></div>${columns.filter(column => column.key !== "check").map(column => `<div class="popover-option ${column.required ? "required" : ""}"><input id="col-${column.key}" type="checkbox" ${state.visibleColumns.has(column.key) ? "checked" : ""} ${column.required ? "disabled" : ""}><label for="col-${column.key}">${escapeHtml(column.label)}</label></div>`).join("")}<div class="popover-divider"></div><button class="btn small" style="width:100%" id="resetColumns">恢复默认列</button>`;
    popover.querySelectorAll("input:not(:disabled)").forEach(input => input.addEventListener("change", () => {
      const key = input.id.replace("col-", "");
      input.checked ? state.visibleColumns.add(key) : state.visibleColumns.delete(key);
      persistUi();
      renderTable();
    }));
    $("resetColumns").addEventListener("click", () => {
      state.visibleColumns = new Set(columns.filter(column => !column.defaultHidden).map(column => column.key));
      persistUi();
      renderColumnsPopover();
      renderTable();
    });
  }

  function renderSortPopover() {
    const popover = $("sortPopover");
    popover.innerHTML = `<div class="popover-title"><span>自定义排序</span><span class="popover-subtitle">按任意列值</span></div><div class="sort-grid"><select id="sortField">${columns.filter(column => column.sortable).map(column => `<option value="${column.key}" ${state.sortKey === column.key ? "selected" : ""}>${escapeHtml(column.label)}</option>`).join("")}</select><select id="sortDirection"><option value="desc" ${state.sortDir === "desc" ? "selected" : ""}>降序</option><option value="asc" ${state.sortDir === "asc" ? "selected" : ""}>升序</option></select></div><div style="padding:7px 8px;color:var(--text-3);font-size:11px">也可直接点击表头切换排序。默认：时间从新到旧。</div>`;
    $("sortField").addEventListener("change", event => { state.sortKey = event.target.value; updateSortLabel(); loadLibrary({ resetPage: true }); });
    $("sortDirection").addEventListener("change", event => { state.sortDir = event.target.value; updateSortLabel(); loadLibrary({ resetPage: true }); });
  }

  function positionPopover(popover, anchor) {
    const rect = anchor.getBoundingClientRect();
    const width = popover.offsetWidth || 290;
    popover.style.left = `${Math.min(window.innerWidth - width - 12, Math.max(12, rect.right - width))}px`;
    let top = rect.bottom + 8;
    if (top + popover.offsetHeight > window.innerHeight - 12) top = Math.max(12, rect.top - popover.offsetHeight - 8);
    popover.style.top = `${top}px`;
  }

  function togglePopover(id, anchor) {
    ["columnsPopover", "sortPopover"].forEach(other => { if (other !== id) $(other).classList.remove("open"); });
    const popover = $(id);
    popover.classList.toggle("open");
    if (popover.classList.contains("open")) positionPopover(popover, anchor);
  }

  function latestRunFor(accountId) {
    return state.syncRuns.filter(run => run.source_account_id === accountId).sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")))[0] || null;
  }

  function renderSyncTable() {
    if (!$("syncTableBody")) return;
    const rows = [];
    for (const key of platformOrder.filter(item => item !== "all")) {
      const server = platformMeta[key].server;
      const accounts = state.accounts.filter(account => account.platform === server);
      if (!accounts.length) {
        // **同步不了的平台，连了也没用。**
        //
        // 原来这里对所有平台一律画「连接账号」，旁边写「连接后自动首次全量同步」
        // —— 而小红书/抖音/快手/B站 连上之后一条也同步不了。
        // 这是和「立即同步」那颗按钮同一种假话，换了个位置。
        const support = state.platformSupport[server];
        if (support?.sync_supported === false) {
          // **「同步不了」不等于「连了没用」。**
          //
          // 上一版这里一律不画「连接账号」，理由写的是「同步不了的平台，
          // 连了也没用」。那句话**对国内四家是真的**——它们的 CookI 一步
          // 都不离开浏览器，服务端根本不接收；**对 X / Instagram 是假的**：
          // 托管的登录状态会被取原文件那条路用到。
          //
          // 把 x/instagram 移出「能同步」之后，这段代码顺手连它们的连接入口
          // 也一起关掉了——一次改动，两个后果，而第二个我没看见。
          const canConnect = support.connect_supported !== false;
          const connectCell = canConnect
            ? `<button class="btn small" data-connect-platform="${server}">连接账号</button>`
            : "—";
          const extra = canConnect
            ? `<br><span class="muted">连接之后，保存单条内容时服务器会用你的登录状态去尝试下载原文件。</span>`
            : "";
          rows.push(`<tr><td><div class="platform-cell">${platformLogo(key)}<div><div>${escapeHtml(platformMeta[key].label)}</div><span class="muted">本版本暂不支持自动同步</span></div></div></td>`
            + `<td><div class="connection-status"><span class="dot" style="background:var(--text-3)"></span>未连接</div></td><td>—</td>`
            + `<td><span class="muted" style="line-height:1.5">${escapeHtml(support.not_syncable_reason || "")}${extra}</span></td><td>—</td><td>${connectCell}</td></tr>`);
          continue;
        }
        rows.push(`<tr><td><div class="platform-cell">${platformLogo(key)}<div><div>${escapeHtml(platformMeta[key].label)}</div><span class="muted">尚未连接</span></div></div></td><td><div class="connection-status"><span class="dot" style="background:var(--text-3)"></span>未连接</div></td><td>—</td><td><span class="muted">连接后自动首次全量同步</span></td><td>—</td><td><button class="btn small" data-connect-platform="${server}">连接账号</button></td></tr>`);
        continue;
      }
      for (const account of accounts) {
        const run = latestRunFor(account.id);
        const discovered = Number(run?.discovered_count || 0);
        const imported = Number(run?.imported_count || 0);
        const progress = discovered ? Math.min(100, Math.round(imported / discovered * 100)) : (run?.status === "completed" ? 100 : 0);
        const status = run?.status || account.connection_state;
        const stateClass = ["connected", "completed"].includes(status) ? "connected" : ["failed", "blocked_environment"].includes(status) ? "error" : "scanning";
        let action = "";
        if (run && ["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(status)) {
          action = `<button class="btn small" data-control-run="${escapeHtml(run.id)}" data-account-id="${escapeHtml(account.id)}" data-control-action="pause">暂停</button><button class="btn small subtle-danger" data-control-run="${escapeHtml(run.id)}" data-account-id="${escapeHtml(account.id)}" data-control-action="cancel">取消</button>`;
        } else if (run && status === "paused") {
          action = `<button class="btn small" data-control-run="${escapeHtml(run.id)}" data-account-id="${escapeHtml(account.id)}" data-control-action="resume">继续</button><button class="btn small subtle-danger" data-control-run="${escapeHtml(run.id)}" data-account-id="${escapeHtml(account.id)}" data-control-action="cancel">取消</button>`;
        } else if (run && ["partial", "failed"].includes(status)) {
          action = `<button class="btn small" data-control-run="${escapeHtml(run.id)}" data-account-id="${escapeHtml(account.id)}" data-control-action="retry">重试</button>`;
        } else if (status === "blocked_environment") {
          action = `<button class="btn small" data-connect-platform="${server}">重新连接</button>`;
        } else if (state.platformSupport[account.platform]?.sync_supported === false) {
          // **不给一个点下去必然失败的按钮。**
          //
          // 小红书/抖音/快手/B站 走浏览器拦截路，而那条路的取数缝隙目前是
          // 显式 stub。此前界面照样画「立即同步」，点下去拿到
          // ACQUISITION_PATH_NOT_INSTALLED，而那个码被别名成 SERVER_UNREACHABLE，
          // 于是用户看到「暂时连不上服务器，[ 重试 ]」——**一遍遍重试一件
          // 永远不可能成功的事**。Owner 的原话是「不知道应该怎么操作」。
          //
          // 现在：不画那颗按钮，把「为什么」和「现在能做什么」直接写出来。
          action = `<span class="muted" style="max-width:280px;display:inline-block;line-height:1.5">`
            + `${escapeHtml(state.platformSupport[account.platform]?.not_syncable_reason || "本版本还不能自动同步这个平台。")}</span>`;
        } else {
          action = `<button class="btn small" data-sync-account="${escapeHtml(account.id)}">立即同步</button>`;
        }
        // 断开（v0.0.0.7 / INV-REVERSIBLE）。只在没有正在跑的任务时给——
        // 跑到一半时该点的是上面的「取消」，两颗按钮意思不同，别摆在一起让人选。
        if (account.connection_state !== "disconnected"
            && !["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting", "paused"].includes(status)) {
          action += `<button class="btn small subtle-danger" data-disconnect-account="${escapeHtml(account.id)}">断开</button>`;
        }
        rows.push(`<tr><td><div class="platform-cell">${platformLogo(key)}<div><div>${escapeHtml(account.display_name || account.external_account_id || platformMeta[key].label)}</div><span class="muted">${escapeHtml(platformMeta[key].label)}</span></div></div></td><td><div class="connection-status ${stateClass}"><span class="dot"></span>${escapeHtml(connectionLabels[status] || status || "未知")}</div></td><td><strong style="color:var(--text)">${Number(account.content_count || 0).toLocaleString("zh-CN")}</strong> 条</td><td><div class="sync-progress"><div style="font-size:11px;color:var(--text-3)">${run ? `${imported}/${discovered || "…"} · ${connectionLabels[run.status] || run.status}` : "首次同步尚未开始"}</div>${run && (run.last_error_code || run.outcome === "stalled") ? `<div class="muted" style="font-size:11px;margin-top:2px" data-failure-reason>${escapeHtml(run.outcome === "stalled" ? (run.message_zh || "") : (failureSentence(run.last_error_code, platformMeta[key].label, run.imported_count)?.text || ""))}</div>` : ""}<div class="progress-track"><div class="progress-bar" style="width:${progress}%"></div></div></div></td><td>${escapeHtml(formatDate(account.last_sync_at, true))}</td><td><div class="sync-action-stack">${action}</div></td></tr>`);
      }
    }
    $("syncTableBody").innerHTML = rows.join("");
    document.querySelectorAll("[data-connect-platform]").forEach(button => button.addEventListener("click", () => connectAccount(button.dataset.connectPlatform, button)));
    document.querySelectorAll("[data-sync-account]").forEach(button => button.addEventListener("click", () => syncAccount(button.dataset.syncAccount, button)));
    document.querySelectorAll("[data-disconnect-account]").forEach(button => button.addEventListener("click", () => disconnectAccount(button.dataset.disconnectAccount, button)));
    document.querySelectorAll("[data-control-run]").forEach(button => button.addEventListener("click", () => controlSyncRun(
      button.dataset.controlRun,
      button.dataset.accountId,
      button.dataset.controlAction,
      button
    )));
  }

  function openSyncModal() { renderSyncTable(); $("syncModalBackdrop").classList.add("open"); }
  function closeModal(id) { $(id)?.classList.remove("open"); }

  function openImportModal() {
    $("importForm")?.reset();
    if ($("importError")) $("importError").textContent = "";
    openModal("importModalBackdrop");
  }

  function safeArchiveFilename(file) {
    const candidate = String(file?.name || "social-archiver-export.zip");
    const normalized = candidate.replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 180);
    return normalized || "social-archiver-export.zip";
  }

  async function importSocialArchiver(event) {
    event.preventDefault();
    const file = $("archiveFile")?.files?.[0];
    const error = $("importError");
    const submit = $("importSubmit");
    if (error) error.textContent = "";
    if (!file) {
      if (error) error.textContent = "请选择一个 ZIP 导出包。";
      return;
    }
    if (!file.name.toLowerCase().endsWith(".zip") || file.size <= 0) {
      if (error) error.textContent = "请选择非空的 ZIP 导出包。";
      return;
    }
    if (file.size > MAX_SOCIAL_ARCHIVER_BUNDLE_BYTES) {
      if (error) error.textContent = "导入包超过 200 MiB，请拆分后重试。";
      return;
    }
    const original = submit?.textContent || "开始导入";
    if (submit) { submit.disabled = true; submit.textContent = "正在导入…"; }
    try {
      const result = await api("/v1/import/social-archiver", {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Archive-Filename": safeArchiveFilename(file)
        },
        body: file,
        timeoutMs: 120000
      });
      const imported = Number(result.imported ?? result.accepted ?? 0);
      closeModal("importModalBackdrop");
      $("importForm")?.reset();
      showToast(imported ? `已导入 ${imported} 条内容；重复项会自动复用。` : "导入已完成，但没有可识别的新内容。", imported ? "success" : "needs");
      await loadLibrary({ resetPage: true });
    } catch (requestError) {
      if (error) error.textContent = requestError.message || "导入失败，请检查 ZIP 内容后重试。";
    } finally {
      if (submit) { submit.disabled = false; submit.textContent = original; }
    }
  }

  function postToExtension(type, payload = {}, timeoutMs = 2500) {
    const requestId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        window.removeEventListener("message", onMessage);
        reject(new Error("没有检测到 Social Archive 浏览器插件"));
      }, timeoutMs);
      function onMessage(event) {
        const data = event.data || {};
        if (event.source !== window || data.source !== "social-archive-extension" || data.requestId !== requestId) return;
        clearTimeout(timer);
        window.removeEventListener("message", onMessage);
        if (data.ok === false) reject(new Error(data.error || data.message || "插件操作失败"));
        else resolve(data);
      }
      window.addEventListener("message", onMessage);
      window.postMessage({ source: "social-archive-web", type, requestId, ...payload }, location.origin);
    });
  }

  function extensionStatus(payload = {}) {
    const version = String(payload.version || "");
    return {
      detected: payload.detected === true,
      paired: payload.paired === true,
      compatible: version === PRODUCT_VERSION,
      version,
      refreshedAt: Date.now()
    };
  }

  async function refreshExtensionStatus() {
    try {
      state.extension = extensionStatus(await postToExtension("SA_PING", {}, 1500));
    } catch (_) {
      state.extension = { detected: false, paired: false, compatible: false, version: "", refreshedAt: Date.now() };
    }
    return state.extension;
  }

  /** 替扩展取一个长期可撤销令牌，并交给它（v0.0.0.7 / T03）。
   *
   * 这个页面是**已登录**的，会话 cookie 就在同源请求里；用它换令牌，
   * 再通过 bridge 直接递给扩展。用户点一下按钮，不接触令牌文本，
   * 一个字符都不用输入——这是 INV-ZERO-BARRIER 要的形态。
   *
   * 取代的旧流程：服务端生成一次性码 → 用户去别处找到它 → 手抄进设置页 →
   * 十分钟过期就重来。实际使用中连续失败三次。
   */
  async function connectExtension() {
    let token = "";
    try {
      // 同源、带会话 cookie。api() 里 credentials 就是 same-origin。
      token = String((await api("/v1/auth/extension-token", { method: "POST" })).token || "");
    } catch (error) {
      showToast(
        error?.status === 401
          ? "请先登录你的档案馆，再连接插件。"
          : "暂时取不到插件访问凭据，请稍后再试。",
        "needs"
      );
      return false;
    }
    if (!token) {
      showToast("暂时取不到插件访问凭据，请稍后再试。", "needs");
      return false;
    }
    try {
      // 不下发 endpoint：扩展用它自己的托管配置（runtime-config.json）连 API 域，
      // 页面这边只负责把凭据递过去。页面替扩展决定服务地址会绕过托管配置。
      await postToExtension("SA_ADOPT_TOKEN", { token, libraryUrl: location.origin }, 12000);
    } catch (error) {
      showToast(error?.message || "插件连接失败，请重试。", "needs");
      return false;
    }
    await refreshExtensionStatus();
    return state.extension.paired === true;
  }

  async function ensureExtensionReady() {
    const extension = await refreshExtensionStatus();
    // **不要把页面跳走。**
    //
    // 原来这两处直接 location.href = "/extension-install"：用户点的按钮写着
    // 「立即同步全部」，页面却跳到一个安装说明页。Owner 的原话：
    // 「点击同步全部账号后就会跳转到莫名其妙的页面…怎么实际功能和显示文字还不一样」。
    //
    // 那条 toast 也白搭 —— 页面当场就跳走了，没人来得及读。
    // 改成先问一句：跳不跳由用户决定，而且他知道为什么要跳。
    if (!extension.detected) {
      if (confirm("还没有检测到 Social Archive 浏览器插件。\n\n同步收藏需要它来读取你自己浏览器里的登录状态。\n\n要现在打开安装说明吗？")) {
        location.href = "/extension-install";
      }
      return false;
    }
    if (!extension.compatible) {
      if (confirm(`检测到的插件是 v${extension.version || "未知"}，需要 v${PRODUCT_VERSION}。\n\n要现在打开更新说明吗？`)) {
        location.href = "/extension-install";
      }
      return false;
    }
    if (!extension.paired) {
      // 不再把用户丢去设置页手抄一串码——就地替它取凭据接上。
      const connected = await connectExtension();
      if (!connected) return false;
      showToast("插件已连接。", "ok");
    }
    return true;
  }

  window.addEventListener("message", event => {
    const data = event.data || {};
    if (event.source !== window || data.source !== "social-archive-extension" || data.type !== "SA_BRIDGE_READY") return;
    refreshExtensionStatus().catch(() => {});
  });

  async function connectAccount(platform, button) {
    const meta = Object.values(platformMeta).find(item => item.server === platform) || platformMeta.web;
    if (button) { button.disabled = true; button.textContent = "正在打开…"; }
    try {
      if (!await ensureExtensionReady()) return;
      const result = await postToExtension("SA_ACCOUNT_CONNECT", { platform });
      showToast(result.message || `${meta.label} 授权流程已打开`);
      setTimeout(() => loadAccountsAndDestinations().catch(() => {}), 1200);
    } catch (error) {
      showToast(`${meta.label}：${error.message}`, "error");
    } finally {
      if (button) { button.disabled = false; button.textContent = "连接账号"; }
    }
  }

  /** 断开账号（v0.0.0.7 / INV-REVERSIBLE）。
   *
   * 连接是一次点击，此前断开做不到——而连上之后每 6 小时自己跑一次。
   *
   * 这里直接调接口而不像扩展那样走 background：网页这一侧没有本地同步队列，
   * 要清的那份队列在扩展里，由扩展自己那颗按钮负责。两边都能断，
   * 各自清各自那一半。
   */
  async function disconnectAccount(accountId, button) {
    const account = state.accounts.find(item => item.id === accountId);
    if (!account) return;
    const label = account.display_name || platformMeta[serverToUiPlatform[account.platform]]?.label || "这个账号";
    const kept = Number(account.content_count || 0).toLocaleString("zh-CN");
    if (!confirm(`断开 ${label} 之后不会再自动同步。\n\n已经存下的 ${kept} 条内容都会留着，随时可以重新连接。\n\n确定断开吗？`)) return;
    if (button) { button.disabled = true; button.textContent = "正在断开…"; }
    try {
      const result = await api(`/v1/accounts/${encodeURIComponent(accountId)}`, { method: "DELETE" });
      showToast(result?.message_zh || "已断开连接。");
      await loadAccountsAndDestinations();
      renderSyncTable();
    } catch (error) {
      showToast(`${label}：${error.message}`, "error");
    } finally {
      if (button) { button.disabled = false; button.textContent = "断开"; }
    }
  }

  async function syncAccount(accountId, button) {
    const account = state.accounts.find(item => item.id === accountId);
    if (!account) return;
    const active = latestRunFor(accountId);
    if (active && ["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(active.status)) {
      showToast(`${account.display_name || platformMeta[serverToUiPlatform[account.platform]]?.label || "账号"} 正在同步：已导入 ${active.imported_count || 0}/${active.discovered_count || "…"} 条`);
      return;
    }
    if (button) { button.disabled = true; button.textContent = "正在启动…"; }
    try {
      if (!await ensureExtensionReady()) return;
      const result = await postToExtension("SA_SYNC_ACCOUNT", { accountId });
      showToast(result.message || "同步已加入后台队列；已完成内容会立即出现在资料库。");
      setTimeout(() => loadAccountsAndDestinations().catch(() => {}), 800);
    } catch (error) {
      showToast(`无法开始同步：${error.message}。请确认 Social Archive 插件已安装并连接。`, "error");
    } finally { if (button) { button.disabled = false; button.textContent = "立即同步"; } }
  }

  async function controlSyncRun(syncRunId, accountId, action, button) {
    const labels = { pause: "暂停", resume: "继续", cancel: "取消", retry: "重试" };
    if (action === "cancel" && !window.confirm("取消本次同步？已经导入的内容会保留，未完成内容可以之后重新同步。")) return;
    const original = button?.textContent || labels[action] || "处理";
    if (button) { button.disabled = true; button.textContent = "处理中…"; }
    try {
      const result = await postToExtension("SA_CONTROL_SYNC_RUN", { syncRunId, accountId, action });
      showToast(result.message || `同步已${labels[action] || "更新"}`);
      await loadAccountsAndDestinations();
      renderSyncTable();
    } catch (error) {
      showToast(`无法${labels[action] || "处理"}同步：${error.message}`, "error");
    } finally {
      if (button) { button.disabled = false; button.textContent = original; }
    }
  }

  async function syncAllAccounts() {
    const connected = state.accounts.filter(item => ["connected", "degraded"].includes(item.connection_state));
    // **只数真的同步得动的。** 原来这里把所有已连接账号都算进去，于是
    // 点「立即同步全部」会提示「已将 3 个账号加入队列」，然后什么也不发生——
    // 因为那三个平台的取数路在本版本是 stub。名实不符正出在这里。
    const accounts = connected.filter(item =>
      state.platformSupport[item.platform]?.sync_supported !== false);
    if (!connected.length) { openSyncModal(); showToast("请先连接至少一个平台账号", "needs"); return; }
    if (!accounts.length) {
      showToast("已连接的账号在本版本都还不能自动同步。现在可以在浏览器里打开任意一条内容，点插件的「保存到我的档案馆」。", "needs");
      openSyncModal();
      return;
    }
    try {
      if (!await ensureExtensionReady()) return;
      const result = await postToExtension("SA_SYNC_ALL_ACCOUNTS");
      showToast(result.message || `已将 ${Number(result.queuedCount || accounts.length)} 个账号加入后台同步队列`
        + (connected.length > accounts.length ? `（另有 ${connected.length - accounts.length} 个本版本还不能自动同步）` : ""));
      setTimeout(() => loadAccountsAndDestinations().catch(() => {}), 800);
    } catch (error) {
      showToast(`无法启动同步：${error.message}。请确认 Social Archive 插件已安装并连接。`, "error");
    }
  }

  function renderDestinationsModal() {
    const body = $("destinationsModalBody");
    if (!body) return;
    body.innerHTML = `<div class="destination-live-grid">${state.destinations.map(item => {
      const stateName = item.state || "needs_user_action";
      return `<article class="destination-live-card"><header><strong>${escapeHtml(destinationNames[item.destination_id] || item.destination_id)}</strong><span class="state-label ${escapeHtml(stateName)}">${escapeHtml(connectionLabels[stateName] || stateName)}</span></header><p>${escapeHtml(item.last_message_zh || item.next_action_zh || "完成一次真实写入后才会显示已连接。")}</p><p class="muted">${escapeHtml(item.coverage_zh || "")}</p><p class="muted privacy-note">${escapeHtml(item.privacy_note_zh || "")}</p><footer><small>${item.last_checked_at ? `最近检查 ${escapeHtml(formatDate(item.last_checked_at, true))}` : "尚未实测"}</small>${!["social_archive", "markdown"].includes(item.destination_id) ? `<button class="btn small" data-probe-destination="${escapeHtml(item.destination_id)}">检查连接</button>` : ""}${backfillButton(item)}</footer></article>`;
    }).join("")}</div>`;
    document.querySelectorAll("[data-probe-destination]").forEach(button => button.addEventListener("click", () => probeDestination(button.dataset.probeDestination, button)));
    document.querySelectorAll("[data-backfill-destination]").forEach(button => button.addEventListener("click", () => backfillDestination(button.dataset.backfillDestination, Number(button.dataset.backfillMissing || 0), button)));
  }

  /** 少送了就给个补的按钮。**没少送就不要出现**——按钮本身就是一句话。
   *
   * 2026-08-05 实测：Owner 连上 GitHub 与 Obsidian 之后，两边各只有
   * 1 / 193 条。不是坏了——投递只在**新内容进来时**发生，他后来才连上。
   * 而在他那一侧，「我连上了，我的档案应该都在那儿」是最自然的期待。
   * 在这个按钮之前，补上去的唯一办法是逐条点 192 次，或者让开发者
   * 登进服务器敲命令——两条都不该是他要走的路。
   */
  function backfillButton(item) {
    const total = Number(item.content_total || 0);
    const done = Number(item.exported_count || 0);
    const missing = total - done;
    if (!(missing > 0) || item.state !== "connected") return "";
    return `<button class="btn small" data-backfill-destination="${escapeHtml(item.destination_id)}" data-backfill-missing="${missing}">把没送过去的 ${missing} 条补上</button>`;
  }

  async function backfillDestination(destinationId, missing, button) {
    const name = destinationNames[destinationId] || destinationId;
    // **往外部账号批量写，先问一句。** 192 条不是一次点击该有的默默后果。
    if (!window.confirm(`要把 ${missing} 条补送到「${name}」吗？\n\n它们会一条条送过去，可能要几分钟。`)) return;
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "正在排队…";
    try {
      const result = await api(`/v1/destinations/${encodeURIComponent(destinationId)}/backfill`, { method: "POST" });
      showToast(result.message_zh || `已排队 ${result.enqueued} 条。`, "ok");
    } catch (error) {
      showToast(error?.message || "补投没能开始", "error");
    } finally {
      button.disabled = false;
      button.textContent = original;
      // 与「检查连接」用同一个刷新入口——**别自己造第二个**，
      // 两个刷新路径最后总会有一个忘了更新某处。
      await loadAccountsAndDestinations().catch(() => {});
    }
  }

  async function probeDestination(id, button) {
    button.disabled = true; button.textContent = "检查中…";
    try {
      const result = await api(`/v1/destinations/${encodeURIComponent(id)}/probe`, { method: "POST", timeoutMs: 25000 });
      showToast(result.message_zh || `${destinationNames[id] || id} 已连接`);
    } catch (error) {
      showToast(`${destinationNames[id] || id}：${error.message}`, "error");
    } finally {
      button.disabled = false; button.textContent = "检查连接";
      await loadAccountsAndDestinations().catch(() => {});
    }
  }

  function renderSettingsModal() {
    const saved = loadUiSettings();
    $("settingsModalBody").innerHTML = `<div class="settings-grid">
      <article class="settings-card"><label><input id="settingGroup" type="checkbox" ${state.group ? "checked" : ""}><span><strong>按平台分组</strong><span>全部视图以平台为主体分类。</span></span></label></article>
      <article class="settings-card"><label><input id="settingCompact" type="checkbox" ${document.body.classList.contains("compact") ? "checked" : ""}><span><strong>紧凑表格</strong><span>同屏显示更多收藏内容。</span></span></label></article>
      <article class="settings-card"><label><input id="settingDark" type="checkbox" ${document.documentElement.dataset.theme === "dark" ? "checked" : ""}><span><strong>深色主题</strong><span>只影响当前浏览器，不改变归档数据。</span></span></label></article>
      <article class="settings-card"><label><input type="checkbox" checked disabled><span><strong>默认 L0＋L1＋L3</strong><span>L2 页面快照默认关闭，不阻塞主流程。</span></span></label></article>
    </div>
    <div class="settings-grid" style="margin-top:10px">
      <article class="settings-card"><div><strong>当前登录</strong><div class="muted" style="margin-top:4px">${escapeHtml(state.user?.display_name || "未知")}</div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn small" id="settingLogout">退出登录</button>
          <button class="btn small subtle-danger" id="settingRevokeExtension">断开浏览器插件</button>
        </div>
        <div class="muted" style="margin-top:8px">退出登录不会删除任何已归档内容。断开插件后，插件上行会立刻失效，重新登录页面即可再次接上。</div>
      </div></article>
    </div>`;
    $("settingGroup").addEventListener("change", event => { state.group = event.target.checked; $("groupBtn").classList.toggle("active", state.group); persistUi(); renderTable(); });
    $("settingCompact").addEventListener("change", event => { document.body.classList.toggle("compact", event.target.checked); $("densityBtn").classList.toggle("active", event.target.checked); persistUi(); });
    $("settingDark").addEventListener("change", event => { document.documentElement.dataset.theme = event.target.checked ? "dark" : "light"; persistUi(); });
    $("settingLogout").addEventListener("click", logout);
    // 断开插件（DELETE /v1/auth/extension-token）。此前这条路由**没有任何调用方**：
    // 令牌发得出去、收不回来。INV-REVERSIBLE 同一条。
    $("settingRevokeExtension").addEventListener("click", async event => {
      const button = event.currentTarget;
      if (!confirm("断开后浏览器插件会立刻失去访问权限（上行返回 401）。\n\n已归档的内容一条都不会删。重新打开本页面即可再次接上。\n\n确定断开吗？")) return;
      button.disabled = true;
      const original = button.textContent;
      button.textContent = "正在断开…";
      try {
        await api("/v1/auth/extension-token", { method: "DELETE", timeoutMs: 8000 });
        showToast("已断开浏览器插件。");
        await refreshExtensionStatus();
      } catch (error) {
        showToast(error.message || "断开失败，请稍后再试。", "error");
      } finally {
        button.disabled = false;
        button.textContent = original;
      }
    });
  }

  function openModal(id) { $(id)?.classList.add("open"); }

  function renderClassificationModal() {
    $("classificationModalBody").innerHTML = `<form id="classificationForm" class="form-grid"><label>主题分类<input id="classificationTopic" required maxlength="256" placeholder="例如：AI与技术"></label><label>关键词<input id="classificationKeywords" maxlength="500" placeholder="用逗号分隔，例如：Agent, 自动化, 工作流"></label><div id="classificationError" class="inline-error"></div><div class="form-actions"><button type="button" class="btn" data-close-modal="classificationModalBackdrop">取消</button><button class="btn primary" type="submit">保存到 ${state.selected.size} 条内容</button></div></form>`;
    $("classificationForm").addEventListener("submit", async event => {
      event.preventDefault();
      const topic = $("classificationTopic").value.trim();
      const keywords = $("classificationKeywords").value.split(/[，,]/).map(item => item.trim()).filter(Boolean);
      try {
        await api("/v1/library/classify", { method: "POST", body: JSON.stringify({ content_ids: [...state.selected], topic, keywords }) });
        closeModal("classificationModalBackdrop");
        state.selected.clear();
        showToast("主题分类和关键词已更新");
        await loadLibrary();
      } catch (error) { $("classificationError").textContent = error.message; }
    });
  }

  async function bulkExport() {
    const ids = [...state.selected];
    if (!ids.length) return;
    const destinations = state.destinations.filter(item => item.state === "connected" && item.destination_id !== "social_archive").map(item => item.destination_id);
    if (!destinations.includes("markdown")) destinations.unshift("markdown");
    let accepted = 0;
    for (const id of ids) {
      try { await api(`/v1/library/${encodeURIComponent(id)}/export`, { method: "POST", body: JSON.stringify({ destination_ids: destinations }) }); accepted += 1; }
      catch (_) { /* Each row remains independently retryable. */ }
    }
    showToast(`已将 ${accepted}/${ids.length} 条内容加入自动导出队列`, accepted === ids.length ? "success" : "needs");
    state.selected.clear();
    renderTable();
  }

  function renderSyncConnectPicker() {
    const cards = platformOrder.filter(key => key !== "all").map(key => `<article class="account-connect-card"><span>${platformLogo(key)}</span><div class="grow"><strong>${escapeHtml(platformMeta[key].label)}</strong><small>授权一次后自动全量导入，再持续增量同步</small></div><button class="btn small" data-picker-platform="${platformMeta[key].server}">连接</button></article>`).join("");
    const body = $("syncTableBody").closest(".modal-body");
    const existing = body.querySelector(".account-connect-grid");
    if (existing) existing.remove();
    const grid = document.createElement("div");
    grid.className = "account-connect-grid";
    grid.innerHTML = cards;
    body.prepend(grid);
    grid.querySelectorAll("[data-picker-platform]").forEach(button => button.addEventListener("click", () => connectAccount(button.dataset.pickerPlatform, button)));
  }

  function persistUi() {
    localStorage.setItem("social-archive-ui-v006", JSON.stringify({
      visibleColumns: [...state.visibleColumns], group: state.group,
      compact: document.body.classList.contains("compact"), theme: document.documentElement.dataset.theme || "light"
    }));
  }

  function loadUiSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem("social-archive-ui-v006") || "{}");
      if (Array.isArray(saved.visibleColumns)) {
        const required = columns.filter(column => column.required).map(column => column.key);
        state.visibleColumns = new Set([...required, ...saved.visibleColumns.filter(key => columns.some(column => column.key === key))]);
      }
      if (typeof saved.group === "boolean") state.group = saved.group;
      document.body.classList.toggle("compact", Boolean(saved.compact));
      document.documentElement.dataset.theme = saved.theme === "dark" ? "dark" : "light";
      return saved;
    } catch (_) { return {}; }
  }

  function bind() {
    $("globalSearch").addEventListener("input", debounce(event => { state.search = event.target.value; loadLibrary({ resetPage: true }); }, 280));
    $("filterBtn").addEventListener("click", () => {
      const panel = $("filterPanel");
      panel.classList.toggle("open");
      const open = panel.classList.contains("open");
      $("filterBtn").classList.toggle("active", open);
      $("filterBtn").setAttribute("aria-expanded", String(open));
    });
    [["relationFilter", "relation"], ["topicFilter", "topic"], ["collectionFilter", "collection"], ["dateFilter", "date"], ["archiveFilter", "archive"]].forEach(([id, key]) => $(id).addEventListener("change", event => { state.filters[key] = event.target.value; loadLibrary({ resetPage: true }); }));
    $("groupBtn").addEventListener("click", () => {
      if (state.platform !== "all") state.platform = "all";
      state.group = !state.group;
      $("groupBtn").classList.toggle("active", state.group);
      $("groupBtn").setAttribute("aria-pressed", String(state.group));
      persistUi();
      loadLibrary({ resetPage: true });
    });
    $("densityBtn").addEventListener("click", () => {
      document.body.classList.toggle("compact");
      const compact = document.body.classList.contains("compact");
      $("densityBtn").classList.toggle("active", compact);
      $("densityBtn").setAttribute("aria-pressed", String(compact));
      persistUi();
    });
    $("themeToggle").addEventListener("click", () => {
      document.documentElement.dataset.theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      persistUi();
    });
    $("columnsBtn").addEventListener("click", event => { renderColumnsPopover(); togglePopover("columnsPopover", event.currentTarget); });
    $("sortBtn").addEventListener("click", event => { renderSortPopover(); togglePopover("sortPopover", event.currentTarget); });
    $("prevPage").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; loadLibrary(); } });
    $("nextPage").addEventListener("click", () => { if (state.page < Math.ceil(state.total / state.pageSize)) { state.page += 1; loadLibrary(); } });
    $("closeDrawer").addEventListener("click", closeDetail);
    $("drawerBackdrop").addEventListener("click", closeDetail);
    $("copyLinkBtn").addEventListener("click", async () => {
      if (!state.detailRow) return;
      try { await navigator.clipboard.writeText(state.detailRow.url); showToast("原始链接已复制"); }
      catch (_) { showToast("浏览器未允许复制，请使用“打开原文”", "needs"); }
    });
    document.querySelectorAll("[data-open-sync]").forEach(button => button.addEventListener("click", openSyncModal));
    $("openImport").addEventListener("click", openImportModal);
    $("importForm").addEventListener("submit", importSocialArchiver);
    $("closeSyncModal").addEventListener("click", () => closeModal("syncModalBackdrop"));
    $("syncModalBackdrop").addEventListener("click", event => { if (event.target === event.currentTarget) closeModal("syncModalBackdrop"); });
    $("syncAllBtn").addEventListener("click", syncAllAccounts);
    $("modalSyncAll").addEventListener("click", syncAllAccounts);
    $("connectNewAccount").addEventListener("click", renderSyncConnectPicker);
    $("bulkClear").addEventListener("click", () => { state.selected.clear(); renderTable(); });
    $("bulkExport").addEventListener("click", bulkExport);
    $("bulkCategory").addEventListener("click", () => { renderClassificationModal(); openModal("classificationModalBackdrop"); });
    $("emptyConnectAccount").addEventListener("click", event => {
      const action = event.currentTarget.dataset.action;
      if (action === "retry") loadLibrary();
      else openSyncModal();
    });
    document.querySelectorAll("[data-nav]").forEach(button => button.addEventListener("click", () => {
      const nav = button.dataset.nav;
      document.querySelectorAll("[data-nav]").forEach(item => item.classList.toggle("active", item === button || (nav === "library" && item.dataset.nav === "library")));
      if (nav === "library") { closeModal("destinationsModalBackdrop"); closeModal("settingsModalBackdrop"); window.scrollTo({ top: 0, behavior: "smooth" }); }
      if (nav === "exports") { renderDestinationsModal(); openModal("destinationsModalBackdrop"); }
      if (nav === "settings") { renderSettingsModal(); openModal("settingsModalBackdrop"); }
    }));
    document.querySelectorAll("[data-close-modal]").forEach(button => button.addEventListener("click", () => closeModal(button.dataset.closeModal)));
    ["destinationsModalBackdrop", "settingsModalBackdrop", "classificationModalBackdrop", "importModalBackdrop"].forEach(id => $(id)?.addEventListener("click", event => { if (event.target === event.currentTarget) closeModal(id); }));
    document.addEventListener("click", event => {
      if (!event.target.closest(".popover") && !event.target.closest("#columnsBtn") && !event.target.closest("#sortBtn")) document.querySelectorAll(".popover").forEach(popover => popover.classList.remove("open"));
      const close = event.target.closest("[data-close-modal]");
      if (close) closeModal(close.dataset.closeModal);
    });
    document.addEventListener("keydown", event => {
      if (event.key === "/" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) { event.preventDefault(); $("globalSearch").focus(); }
      if (event.key === "Escape") { closeDetail(); ["syncModalBackdrop", "destinationsModalBackdrop", "settingsModalBackdrop", "classificationModalBackdrop", "importModalBackdrop"].forEach(closeModal); document.querySelectorAll(".popover").forEach(popover => popover.classList.remove("open")); }
    });
  }

  function debounce(fn, delay) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
  }

  /** 登录闸（v0.0.0.7 / T02）。
   *
   * ## 为什么这段是后补的
   *
   * `auth.py` 提供了 7 条登录路由，而全仓客户端**只调用其中一条**
   * （POST /v1/auth/extension-token）。`/v1/auth/{provider}/start` 零调用——
   * 也就是说产品里**根本没有登录按钮**。
   *
   * Owner 打开页面、点了、告诉我「我点击也登陆了」，而服务端
   * oauth_identity 与 session 都是 0。不是他操作错了，是没有东西可点。
   *
   * 这一条一直没被发现，是因为「接口没人调」那道门只扫 api.py，
   * 从没看过 auth.py（本轮第六次射程写错）。
   *
   * ## 契约
   *
   *   GET  /v1/auth/me                 401 = 未登录
   *   GET  /v1/auth/providers          → [{name, configured}]，没配好的不显示
   *   GET  /v1/auth/{name}/start       → {authorize_url}，**要自己跳过去**
   *   POST /v1/auth/logout
   *
   * 没配好的 provider 不画按钮——比画一个点了就报 503 的按钮好。
   */
  async function requireLogin() {
    const gate = $("loginGate");
    try {
      const me = await api("/v1/auth/me", { timeoutMs: 8000 });
      state.user = me;
      gate.classList.add("hidden");
      return true;
    } catch (error) {
      if (error.status && error.status !== 401 && error.status !== 403) throw error;
    }
    state.user = null;
    gate.classList.remove("hidden");
    const buttons = $("loginButtons");
    const note = $("loginNote");
    try {
      const { providers = [], login_base: loginBase = "" } = await api("/v1/auth/providers", { timeoutMs: 8000 });
      state.loginBase = String(loginBase || "").replace(/\/$/, "");
      const usable = providers.filter(item => item.configured);
      if (!usable.length) {
        buttons.innerHTML = "";
        note.textContent = "登录还没有配置好（缺少 Google / GitHub 的应用凭据），请联系管理员。";
        return false;
      }
      const label = { google: "用 Google 登录", github: "用 GitHub 登录" };
      buttons.innerHTML = usable
        .map(item => `<button class="btn primary login-btn" data-login-provider="${escapeHtml(item.name)}">${escapeHtml(label[item.name] || item.name)}</button>`)
        .join("");
      note.textContent = "登录后浏览器插件会自动接上，你不需要输入任何字符。";
      document.querySelectorAll("[data-login-provider]").forEach(button =>
        button.addEventListener("click", () => startLogin(button.dataset.loginProvider, button)));
    } catch (error) {
      buttons.innerHTML = "";
      note.textContent = `连不上档案馆服务：${error.message}`;
    }
    return false;
  }

  /** 发起登录。
   *
   * **必须是顶层跳转，而且必须跳到 login_base 那个域。**
   *
   * state cookie 是 host-only 的：在哪个域调 /start 就种在哪个域，
   * 而回调地址固定是 login_base（登记在 Google/GitHub 应用里的那个）。
   * 两者不同域时，回调收不到 state → 400「登录链接已失效」。
   * 实测：Owner 在资料库域点了好几次，callback 全是 400、session 始终 0。
   *
   * 用 fetch 也不行：跨域 fetch 种不上 SameSite=lax 的 cookie，
   * 要种得上就得放宽到 SameSite=None + CORS 允许凭据——
   * 那是把登录 cookie 放宽给整个站点，不值得。顶层导航天然满足 lax。
   */
  function startLogin(provider, button) {
    button.disabled = true;
    button.textContent = "正在跳转…";
    const base = state.loginBase || "";
    location.href = `${base}/v1/auth/${encodeURIComponent(provider)}/start?redirect=1`;
  }

  async function logout() {
    try { await api("/v1/auth/logout", { method: "POST", timeoutMs: 8000 }); } catch (_) { /* 已经登出也算登出 */ }
    location.reload();
  }

  async function init() {
    // **先过登录闸。** 没登录时后面每一个接口都会 401，
    // 那样用户看到的是一堆「服务连接异常」，而真正的原因是没登录。
    if (!await requireLogin()) return;
    loadUiSettings();
    bind();
    updateSortLabel();
    $("groupBtn").classList.toggle("active", state.group);
    $("densityBtn").classList.toggle("active", document.body.classList.contains("compact"));
    renderPlatformTabs();
    renderTable();
    renderPagination();
    const results = await Promise.allSettled([loadHealth(), loadAccountsAndDestinations(), refreshExtensionStatus()]);
    if (results.some(result => result.status === "rejected")) {
      document.querySelector(".sync-strip")?.classList.add("error");
      $("connectedAccountCount").textContent = "服务连接异常";
      $("syncSummaryText").textContent = " · 请刷新页面或检查登录状态";
    }
    await loadLibrary();
    renderNextStep();
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/assets/sw.js?v=007-r2").catch(() => {});
  }

  document.addEventListener("DOMContentLoaded", () => init().catch(error => {
    setServiceBadge("error", "初始化失败");
    updateEmptyState("error", error.message);
  }));
})();
