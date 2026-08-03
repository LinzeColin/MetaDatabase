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
    web: { label: "Chrome书签/网页", short: "书", cls: "web", server: "generic-web" }
  };
  const platformOrder = ["all", "xhs", "dy", "ks", "bili", "x", "reddit", "ins", "web"];
  const serverToUiPlatform = Object.fromEntries(Object.entries(platformMeta).filter(([key]) => key !== "all").map(([key, value]) => [value.server, key]));

  const relationLabels = {
    manual_save: "手动保存", bookmark: "书签", saved: "收藏", favorite: "收藏",
    like: "点赞", upvoted: "点赞", watch_later: "稍后再看", history: "观看历史", collection: "收藏夹"
  };
  const relationApiValues = { "收藏": "favorite", "点赞": "like", "书签": "bookmark", "稍后再看": "watch_later" };
  const connectionLabels = {
    connected: "已连接", authorized: "已授权", authorizing: "正在授权", scanning: "同步中", queued: "等待同步",
    discovering: "正在发现", normalizing: "正在整理", artifacting: "正在归档", exporting: "正在导出",
    completed: "同步完成", partial: "部分完成", paused: "已暂停", failed: "需要处理",
    blocked_environment: "需要重新连接", disconnected: "未连接", degraded: "降级可用", cancelled: "已取消"
  };
  const destinationNames = {
    social_archive: "Social Archive", markdown: "Markdown", notion: "Notion", obsidian: "Obsidian",
    github: "GitHub Private", karakeep: "Karakeep", linkwarden: "Linkwarden", archivebox: "ArchiveBox"
  };
  const destinationMarks = { markdown: "M", notion: "N", obsidian: "O", github: "G" };
  const MAX_SOCIAL_ARCHIVER_BUNDLE_BYTES = 200 * 1024 * 1024;
  const PRODUCT_VERSION = "0.0.0.6";

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
    extension: { detected: false, paired: false, compatible: false, version: "", refreshedAt: null },
    platform: "all", group: true, sortKey: "savedAt", sortDir: "desc", search: "",
    filters: { relation: "all", topic: "all", date: "all", archive: "all" },
    visibleColumns: new Set(columns.filter(column => !column.defaultHidden).map(column => column.key)),
    selected: new Set(), collapsedGroups: new Set(), detailRow: null,
    page: 1, pageSize: 50, loading: false
  };

  const dateFormatter = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  const fullDateFormatter = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });

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
        const error = new Error(payload.detail || `请求失败（${response.status}）`);
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
      setServiceBadge("connected", `私人档案馆已连接 · v${health.version || "0.0.0.6"}`);
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
    state.syncRuns = runsResult.items || [];
    state.destinations = destinationsResult.items || [];
    renderSyncSummary();
    renderSyncTable();
    renderDestinationsModal();
  }

  function renderSyncSummary() {
    const connected = state.accounts.filter(item => ["connected", "degraded"].includes(item.connection_state)).length;
    const active = state.syncRuns.filter(item => ["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(item.status));
    const failures = state.syncRuns.filter(item => ["failed", "blocked_environment"].includes(item.status));
    $("connectedAccountCount").textContent = `${connected} 个账号已连接`;
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
      $("syncSummaryText").textContent = ` · ${failures.length} 个账号需要重新连接，其他账号不受影响`;
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
      <div class="drawer-section"><h3>自动导出</h3><div class="export-dots">${["M", "N", "O", "G"].map(mark => `<span class="export-dot ${row.export.includes(mark) ? "done" : ""}">${mark}</span>`).join("")}<span style="margin-left:6px;color:var(--text-3);font-size:12px">${receipts.length ? `${receipts.length} 个真实回执` : "尚无已完成回执"}</span></div></div>`;
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
        } else {
          action = `<button class="btn small" data-sync-account="${escapeHtml(account.id)}">立即同步</button>`;
        }
        rows.push(`<tr><td><div class="platform-cell">${platformLogo(key)}<div><div>${escapeHtml(account.display_name || account.external_account_id || platformMeta[key].label)}</div><span class="muted">${escapeHtml(platformMeta[key].label)}</span></div></div></td><td><div class="connection-status ${stateClass}"><span class="dot"></span>${escapeHtml(connectionLabels[status] || status || "未知")}</div></td><td><strong style="color:var(--text)">${Number(account.content_count || 0).toLocaleString("zh-CN")}</strong> 条</td><td><div class="sync-progress"><div style="font-size:11px;color:var(--text-3)">${run ? `${imported}/${discovered || "…"} · ${connectionLabels[run.status] || run.status}` : "首次同步尚未开始"}</div><div class="progress-track"><div class="progress-bar" style="width:${progress}%"></div></div></div></td><td>${escapeHtml(formatDate(account.last_sync_at, true))}</td><td><div class="sync-action-stack">${action}</div></td></tr>`);
      }
    }
    $("syncTableBody").innerHTML = rows.join("");
    document.querySelectorAll("[data-connect-platform]").forEach(button => button.addEventListener("click", () => connectAccount(button.dataset.connectPlatform, button)));
    document.querySelectorAll("[data-sync-account]").forEach(button => button.addEventListener("click", () => syncAccount(button.dataset.syncAccount, button)));
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

  async function ensureExtensionReady() {
    const extension = await refreshExtensionStatus();
    if (!extension.detected) {
      showToast("未检测到 Social Archive 浏览器插件，正在打开安装说明。", "needs");
      location.href = "/extension-install";
      return false;
    }
    if (!extension.compatible) {
      showToast(`检测到插件 v${extension.version || "未知"}，请更新至 v${PRODUCT_VERSION}。`, "needs");
      location.href = "/extension-install";
      return false;
    }
    if (!extension.paired) {
      await postToExtension("SA_OPEN_OPTIONS").catch(() => {});
      showToast("插件已检测到，请在打开的设置页完成一次性配对。", "needs");
      return false;
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

  async function syncAccount(accountId, button) {
    const account = state.accounts.find(item => item.id === accountId);
    if (!account) return;
    const active = latestRunFor(accountId);
    if (active && ["queued", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(active.status)) {
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
    const accounts = state.accounts.filter(item => ["connected", "degraded"].includes(item.connection_state));
    if (!accounts.length) { openSyncModal(); showToast("请先连接至少一个平台账号", "needs"); return; }
    try {
      if (!await ensureExtensionReady()) return;
      const result = await postToExtension("SA_SYNC_ALL_ACCOUNTS");
      showToast(result.message || `已将 ${Number(result.queuedCount || accounts.length)} 个账号加入后台同步队列`);
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
      return `<article class="destination-live-card"><header><strong>${escapeHtml(destinationNames[item.destination_id] || item.destination_id)}</strong><span class="state-label ${escapeHtml(stateName)}">${escapeHtml(connectionLabels[stateName] || stateName)}</span></header><p>${escapeHtml(item.last_message_zh || item.next_action_zh || "完成一次真实写入后才会显示已连接。")}</p><footer><small>${item.last_checked_at ? `最近检查 ${escapeHtml(formatDate(item.last_checked_at, true))}` : "尚未实测"}</small>${!["social_archive", "markdown"].includes(item.destination_id) ? `<button class="btn small" data-probe-destination="${escapeHtml(item.destination_id)}">检查连接</button>` : ""}</footer></article>`;
    }).join("")}</div>`;
    document.querySelectorAll("[data-probe-destination]").forEach(button => button.addEventListener("click", () => probeDestination(button.dataset.probeDestination, button)));
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
    </div>`;
    $("settingGroup").addEventListener("change", event => { state.group = event.target.checked; $("groupBtn").classList.toggle("active", state.group); persistUi(); renderTable(); });
    $("settingCompact").addEventListener("change", event => { document.body.classList.toggle("compact", event.target.checked); $("densityBtn").classList.toggle("active", event.target.checked); persistUi(); });
    $("settingDark").addEventListener("change", event => { document.documentElement.dataset.theme = event.target.checked ? "dark" : "light"; persistUi(); });
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
    [["relationFilter", "relation"], ["topicFilter", "topic"], ["dateFilter", "date"], ["archiveFilter", "archive"]].forEach(([id, key]) => $(id).addEventListener("change", event => { state.filters[key] = event.target.value; loadLibrary({ resetPage: true }); }));
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

  async function init() {
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
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/assets/sw.js?v=006-r1").catch(() => {});
  }

  document.addEventListener("DOMContentLoaded", () => init().catch(error => {
    setServiceBadge("error", "初始化失败");
    updateEmptyState("error", error.message);
  }));
})();
