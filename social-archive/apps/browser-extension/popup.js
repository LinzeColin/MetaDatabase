/* global SA */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const platformShort = { xiaohongshu: "小", douyin: "抖", kuaishou: "快", bilibili: "B", x: "X", reddit: "R", instagram: "In", "generic-web": "网" };
  const platformName = { xiaohongshu: "小红书", douyin: "抖音", kuaishou: "快手", bilibili: "B站", x: "X", reddit: "Reddit", instagram: "Instagram", "generic-web": "Chrome 书签" };
  const statusName = { connected: "已连接", degraded: "降级可用", completed: "同步完成", partial: "部分完成", queued: "等待同步", discovering: "正在发现", scanning: "同步中", normalizing: "正在整理", artifacting: "正在归档", exporting: "正在导出", failed: "需要处理", blocked_environment: "重新连接", paused: "已暂停" };

  let config = null;
  let tab = null;
  let platform = null;
  let accounts = [];
  let runs = [];
  let bootstrap = null;

  function showStatus(text, type = "success") {
    const element = $("status");
    element.textContent = text;
    element.className = `status ${type === "success" ? "" : type}`.trim();
  }
  function setBusy(value) {
    $("primarySync").disabled = value;
    $("manageAccounts").disabled = value;
    $("savePage").disabled = value;
  }
  function latestRun(accountId) {
    return runs.filter(run => run.source_account_id === accountId).sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")))[0] || null;
  }
  function formatTime(value) {
    if (!value) return "尚未同步";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "尚未同步";
    return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date).replaceAll("/", "-");
  }

  async function renderAuthorization() {
    const permission = await SA.permissionState(platform.id);
    if (permission.authorized) {
      $("authorization").innerHTML = '<span class="auth-pill connected">当前站点已授权</span>';
      return;
    }
    $("authorization").innerHTML = '<button id="authorizeSite" class="authorize-button">授权当前站点</button>';
    $("authorizeSite").addEventListener("click", async () => {
      const granted = await SA.requestPlatformPermission(platform.id);
      if (!granted) return showStatus("未获得站点授权。账号批量同步不会因此被标记成功。", "needs");
      await renderAuthorization();
      showStatus("当前站点已授权。单条保存现在可用。");
    });
  }

  function renderSummary(serviceConnected) {
    const connected = accounts.filter(account => ["connected", "degraded"].includes(account.connection_state)).length;
    const active = runs.filter(run => ["queued", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(run.status));
    const total = accounts.reduce((sum, account) => sum + Number(account.content_count || 0), 0);
    $("serviceState").className = `service-pill ${serviceConnected ? "connected" : "error"}`;
    $("serviceState").textContent = serviceConnected ? "已连接" : "待连接";
    if (!serviceConnected) {
      $("summaryTitle").textContent = "私人档案馆尚未连接";
      $("summaryCopy").textContent = "打开设置完成一次配对。";
      $("primarySyncLabel").textContent = "连接私人档案馆";
      $("primarySyncHint").textContent = "完成后才能同步账号收藏";
      return;
    }
    if (!connected) {
      $("summaryTitle").textContent = "还没有连接平台账号";
      $("summaryCopy").textContent = "连接一次账号后自动全量导入，不需要逐条点击。";
      $("primarySyncLabel").textContent = "连接第一个账号";
      $("primarySyncHint").textContent = "支持 8 个平台与 Chrome 书签";
      return;
    }
    $("summaryTitle").textContent = `${connected} 个账号 · ${total.toLocaleString("zh-CN")} 条内容`;
    if (active.length) {
      const imported = active.reduce((sum, run) => sum + Number(run.imported_count || 0), 0);
      const discovered = active.reduce((sum, run) => sum + Number(run.discovered_count || 0), 0);
      $("summaryCopy").textContent = `${active.length} 个同步任务正在运行 · ${imported}/${discovered || "…"} 条`;
      $("primarySyncLabel").textContent = "查看同步进度";
      $("primarySyncHint").textContent = "已完成内容会立即出现在资料库";
    } else {
      $("summaryCopy").textContent = "首次全量后只同步新增收藏、点赞和书签。";
      $("primarySyncLabel").textContent = "立即同步全部账号";
      $("primarySyncHint").textContent = "无需逐条打开帖子";
    }
  }

  function renderAccounts() {
    if (!accounts.length) {
      $("accountList").innerHTML = '<div class="empty-accounts">没有已连接账号。点击上方“连接与管理账号”开始。</div>';
      return;
    }
    $("accountList").innerHTML = accounts.slice(0, 5).map(account => {
      const run = latestRun(account.id);
      const current = run?.status || account.connection_state || "connected";
      const imported = Number(run?.imported_count || 0);
      const discovered = Number(run?.discovered_count || 0);
      const detail = ["queued", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(current)
        ? `同步 ${imported}/${discovered || "…"}`
        : `${Number(account.content_count || 0).toLocaleString("zh-CN")} 条 · ${formatTime(account.last_sync_at)}`;
      return `<article class="account-row"><span class="platform-dot">${SA.escapeHtml(platformShort[account.platform] || "网")}</span><span class="account-copy"><strong>${SA.escapeHtml(account.display_name || account.external_account_id || platformName[account.platform] || account.platform)}</strong><small>${SA.escapeHtml(detail)}</small></span><span class="state-label ${SA.escapeHtml(current)}">${SA.escapeHtml(statusName[current] || current)}</span></article>`;
    }).join("");
  }

  function renderDestinations() {
    const items = bootstrap?.destinations || [];
    const map = new Map(items.map(item => [item.destination_id, item]));
    const ids = ["markdown", "notion", "obsidian", "github"];
    $("destinationChips").innerHTML = ids.map(id => {
      const item = map.get(id) || {};
      const state = id === "markdown" ? "connected" : (item.state || "needs_user_action");
      return `<span class="destination-chip ${SA.escapeHtml(state)}"><span class="destination-dot"></span>${SA.escapeHtml(SA.destinationLabel(id))} · ${SA.escapeHtml(SA.statusCopy(state))}</span>`;
    }).join("");
  }

  async function refresh() {
    let serviceConnected = true;
    try {
      const [accountData, runData, bootstrapData] = await Promise.all([
        SA.api("/v1/accounts", { timeoutMs: 7000 }),
        SA.api("/v1/sync-runs?limit=100", { timeoutMs: 7000 }),
        SA.api("/v1/extension/bootstrap", { timeoutMs: 7000 })
      ]);
      accounts = accountData.items || [];
      runs = runData.items || [];
      bootstrap = bootstrapData;
      const pending = runs.filter(run => ["queued", "discovering", "scanning", "normalizing", "artifacting", "exporting", "failed", "blocked_environment"].includes(run.status)).length;
      $("taskCount").textContent = String(pending);
      $("taskCount").classList.toggle("hidden", pending === 0);
    } catch (_) {
      serviceConnected = false;
      accounts = [];
      runs = [];
      bootstrap = null;
    }
    renderSummary(serviceConnected);
    renderAccounts();
    renderDestinations();
    return serviceConnected;
  }

  async function syncAll() {
    const serviceConnected = await refresh();
    if (!serviceConnected) {
      await chrome.runtime.openOptionsPage();
      return;
    }
    const connected = accounts.filter(account => ["connected", "degraded"].includes(account.connection_state));
    if (!connected.length) {
      await chrome.runtime.sendMessage({ type: "SA_OPEN_ACCOUNT_CENTER" });
      window.close();
      return;
    }
    const active = runs.some(run => ["queued", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(run.status));
    if (active) {
      await chrome.runtime.sendMessage({ type: "SA_OPEN_TASK_CENTER" });
      window.close();
      return;
    }
    setBusy(true);
    try {
      const result = await chrome.runtime.sendMessage({ type: "SA_SYNC_ALL_ACCOUNTS" });
      if (!result?.ok) throw new Error(result?.error || "没有可同步的已连接账号");
      showStatus(result.message || `已将 ${Number(result.queuedCount || connected.length)} 个账号加入后台同步队列。`, "success");
      await refresh();
    } catch (error) {
      showStatus(`无法启动同步：${error?.message || "未知错误"}`, "error");
    } finally { setBusy(false); }
  }

  async function runCapture() {
    setBusy(true);
    showStatus("正在保存当前页面；这是账号批量同步之外的备用入口。", "needs");
    try {
      config = await SA.setConfig({ relationType: $("relationType").value, collectionKey: $("collectionKey").value.trim() });
      const response = await chrome.runtime.sendMessage({
        type: "SA_CAPTURE_ACTIVE", mode: "page", source: "popup_fallback_current_page",
        relationType: config.relationType, collectionKey: config.collectionKey, destinationIds: config.destinationIds
      });
      if (!response?.ok) throw new Error(response?.error || "保存失败");
      showStatus(`当前页面已保存。${response.destinationWarningCount ? "部分导出需要处理。" : "后台将继续归档和导出。"}`, response.destinationWarningCount ? "needs" : "success");
      await refresh();
    } catch (error) { showStatus(`保存失败：${error?.message || "未知错误"}`, "error"); }
    finally { setBusy(false); }
  }

  async function initCurrentPage() {
    try {
      tab = await SA.activeTab();
      platform = SA.platformFromUrl(tab.url);
      $("platformBadge").textContent = platform.name;
      $("pageTitle").textContent = tab.title || "当前页面";
      config = await SA.getConfig();
      $("relationType").value = config.relationType;
      $("collectionKey").value = config.collectionKey;
      await renderAuthorization();
    } catch (error) {
      $("pageTitle").textContent = "当前页面不可读取";
      $("savePage").disabled = true;
    }
  }

  $("primarySync").addEventListener("click", syncAll);
  $("manageAccounts").addEventListener("click", () => chrome.runtime.sendMessage({ type: "SA_OPEN_ACCOUNT_CENTER" }).then(() => window.close()));
  $("refresh").addEventListener("click", refresh);
  $("settings").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("manageDestinations").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("savePage").addEventListener("click", runCapture);
  $("taskCenter").addEventListener("click", () => chrome.runtime.sendMessage({ type: "SA_OPEN_TASK_CENTER" }).then(() => window.close()));
  $("openLibrary").addEventListener("click", async () => chrome.tabs.create({ url: (await SA.getConfig()).libraryUrl }));

  Promise.all([refresh(), initCurrentPage()]).catch(error => showStatus(error?.message || "插件初始化失败", "error"));
})();
