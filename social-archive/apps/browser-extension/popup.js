/* global SA */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const ACTION_LABEL_LIST = "读取当前列表";
  let tab = null;
  let platform = null;
  let config = null;
  let destinations = [];

  function showStatus(text, type = "success") {
    const element = $("status");
    element.textContent = text;
    element.className = `status ${type === "success" ? "" : type}`.trim();
  }

  function setBusy(value) {
    $("savePage").disabled = value;
    $("scanList").disabled = value;
  }

  async function renderAuthorization() {
    const state = await SA.permissionState(platform.id);
    if (state.authorized) {
      $("authorization").innerHTML = '<span class="auth-pill connected">已授权</span>';
      return;
    }
    $("authorization").innerHTML = '<button id="authorizeSite" class="authorize-button">授权当前平台</button>';
    $("authorizeSite").addEventListener("click", async () => {
      const granted = await SA.requestPlatformPermission(platform.id);
      if (!granted) return showStatus("未获得站点授权。仍可点击“保存到我的档案馆”，但不会显示悬浮按钮。", "needs");
      await chrome.runtime.sendMessage({ type: "SA_REFRESH_FAB" });
      await renderAuthorization();
      showStatus("已授权。此平台页面将显示“保存到我的档案馆”悬浮按钮。");
    });
  }

  async function authorizedSourceCount() {
    const platforms = SA.PLATFORM_RULES.filter(item => item.id !== "generic_web");
    const states = await Promise.all(platforms.map(item => SA.permissionState(item.id).catch(() => ({ authorized: false }))));
    return { authorized: states.filter(item => item.authorized).length, total: platforms.length };
  }

  async function renderConnectionSummary(pending = 0, serviceConnected = true) {
    const sources = await authorizedSourceCount();
    const connectedDestinations = destinations.filter(item => item.state === "connected" && item.destination_id !== "social_archive").length;
    const fixedDestinations = 1; // 只有私人档案馆在首次配对后固定可用；其他目的地需主动检查。
    const totalDestinations = 5;
    const connected = Math.min(totalDestinations, fixedDestinations + connectedDestinations);
    const prefix = serviceConnected ? "服务已连接" : "服务待连接";
    $("connectionSummary").textContent = `${prefix} · 已授权来源 ${sources.authorized}/${sources.total} · 已连接目的地 ${connected}/${totalDestinations} · 待处理 ${pending}`;
    $("connectionSummary").classList.toggle("needs", !serviceConnected);
  }

  function renderDestinations() {
    const stateById = new Map(destinations.map(item => [item.destination_id, item]));
    const ids = ["social_archive", "markdown", "notion", "obsidian", "github"];
    $("destinationChips").innerHTML = ids.map(id => {
      const item = stateById.get(id) || {};
      const state = id === "social_archive" ? "connected" : (item.state || "needs_user_action");
      const connected = state === "connected";
      const selected = config.destinationIds.includes(id);
      const label = `${SA.destinationLabel(id)} · ${SA.statusCopy(state)}`;
      return `<button class="destination-chip ${selected ? "selected" : ""} ${connected ? "" : "disconnected"}" data-id="${id}" data-connected="${connected}" title="${SA.escapeHtml(item.last_message_zh || item.next_action_zh || label)}"><span class="destination-dot ${SA.escapeHtml(state)}"></span>${SA.escapeHtml(label)}</button>`;
    }).join("");
    for (const button of $("destinationChips").querySelectorAll("button")) {
      button.addEventListener("click", async () => {
        const id = button.dataset.id;
        if (button.dataset.connected !== "true") {
          showStatus(`${SA.destinationLabel(id)} 尚未连接。已为你打开连接设置。`, "needs");
          setTimeout(() => chrome.runtime.openOptionsPage(), 450);
          return;
        }
        const next = new Set(config.destinationIds);
        if (id === "social_archive") return showStatus("我的档案馆是必选目的地，不能关闭。", "needs");
        next.has(id) ? next.delete(id) : next.add(id);
        config = await SA.setConfig({ destinationIds: [...next] });
        renderDestinations();
      });
    }
  }

  async function refreshServer() {
    let pending = 0;
    let serviceConnected = true;
    try {
      const bootstrap = await SA.api("/v1/extension/bootstrap", { timeoutMs: 5000 });
      destinations = bootstrap.destinations || [];
      const pendingJobs = (bootstrap.jobs || []).filter(job => !["succeeded", "done", "dead"].includes(job.status)).length;
      const failedExports = Number(bootstrap.summary?.failed_exports || 0);
      pending = pendingJobs + failedExports;
      $("taskCount").textContent = String(pending);
      $("taskCount").classList.toggle("hidden", pending === 0);
    } catch (_) {
      destinations = [];
      serviceConnected = false;
      showStatus("尚未连接 Social Archive。先打开设置完成一键配对。", "needs");
    }
    renderDestinations();
    await renderConnectionSummary(pending, serviceConnected);
  }

  async function runCapture(mode) {
    setBusy(true);
    showStatus(mode === "list" ? `正在${ACTION_LABEL_LIST}，不会自动滚动…` : "正在保存并自动导出…", "needs");
    try {
      config = await SA.setConfig({
        relationType: $("relationType").value,
        collectionKey: $("collectionKey").value.trim()
      });
      const response = await chrome.runtime.sendMessage({
        type: "SA_CAPTURE_ACTIVE",
        mode,
        source: mode === "list" ? "popup_visible_list" : "popup_current_page",
        relationType: config.relationType,
        collectionKey: config.collectionKey,
        destinationIds: config.destinationIds
      });
      if (!response?.ok) throw new Error(response?.error || "操作失败");
      const sourceSuffix = response.failedCount ? `，另有 ${response.failedCount} 条来源失败` : "";
      const destinationSuffix = response.destinationWarningCount ? `；${response.destinationWarningCount} 个目的地需要检查` : "";
      showStatus(`已保存 ${response.savedCount} 条。下载、自动导出与三地备份已进入任务中心${sourceSuffix}${destinationSuffix}。`, response.destinationWarningCount ? "needs" : "success");
      await refreshServer();
    } catch (error) {
      showStatus(`保存失败：${error?.message || "未知错误"}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function init() {
    config = await SA.getConfig();
    tab = await SA.activeTab();
    platform = SA.platformFromUrl(tab.url);
    $("platformBadge").textContent = platform.name;
    $("pageTitle").textContent = tab.title || "当前页面";
    $("relationType").value = config.relationType;
    $("collectionKey").value = config.collectionKey;
    await renderAuthorization();
    await refreshServer();
  }

  $("savePage").addEventListener("click", () => runCapture("page"));
  $("scanList").addEventListener("click", () => runCapture("list"));
  $("settings").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("manageDestinations").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("taskCenter").addEventListener("click", () => chrome.runtime.sendMessage({ type: "SA_OPEN_TASK_CENTER" }).then(() => window.close()));
  $("openLibrary").addEventListener("click", async () => {
    const current = await SA.getConfig();
    chrome.tabs.create({ url: current.libraryUrl });
  });

  init().catch(error => showStatus(error?.message || "无法读取当前页面", "error"));
})();
