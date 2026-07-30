/* global SA */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  let config = null;
  let bootstrap = null;

  function setServiceState(state, text) {
    const badge = $("serviceState");
    badge.className = `state ${state}`;
    badge.textContent = text || SA.statusCopy(state);
  }

  function message(text, type = "success", target = "serviceMessage") {
    const el = $(target);
    el.textContent = text;
    el.className = `message ${type === "success" ? "" : type}`.trim();
  }

  function obsidianLoopbackUrl(value) {
    const url = new URL(String(value || SA.OBSIDIAN_LOOPBACK_URL).trim());
    if (
      url.protocol !== "http:"
      || url.hostname !== "127.0.0.1"
      || url.port !== "27123"
      || url.username
      || url.password
      || url.pathname !== "/"
      || url.search
      || url.hash
    ) throw new Error("Obsidian 只允许 http://127.0.0.1:27123 的本机桥接地址");
    return SA.OBSIDIAN_LOOPBACK_URL;
  }

  function statusText(value) {
    if (!value) return "尚未检查";
    const state = value.status || value.state || value.action;
    if (["verified", "healthy", "connected", "allow"].includes(state)) return "已连接 / 可用";
    if (["pause", "paused", "degraded", "needs_user_action"].includes(state)) return "需要处理";
    return SA.statusCopy(state);
  }

  function checkMeta(item) {
    const raw = item?.last_checked_at;
    let checked = "尚未检查";
    if (raw) {
      const date = new Date(raw);
      checked = Number.isNaN(date.getTime()) ? String(raw) : date.toLocaleString("zh-CN");
    }
    const latency = Number(item?.latency_ms);
    return `最后检查：${checked}${Number.isFinite(latency) ? ` · ${latency} ms` : " · 延迟未测量"}`;
  }

  async function ensureOriginPermission(endpoint) {
    const originPattern = `${new URL(endpoint).origin}/*`;
    const already = await chrome.permissions.contains({ origins: [originPattern] });
    if (already) return true;
    return chrome.permissions.request({ origins: [originPattern] });
  }

  function renderStorage() {
    const quota = new Map((bootstrap?.storage?.items || []).map(item => [item.store_id, item]));
    const replicas = new Map((bootstrap?.storage?.replicas || []).map(item => [item.store_id, item]));
    $("privateDbState").textContent = bootstrap ? "结构化事实同步可检查" : "等待服务状态";
    $("r2State").textContent = statusText(quota.get("r2") || replicas.get("r2"));
    $("ociState").textContent = statusText(quota.get("oci") || replicas.get("oci"));
    $("githubStorageState").textContent = statusText(quota.get("github_release") || replicas.get("github"));
    const completion = bootstrap?.storage?.completion || {};
    const done = Number(completion.all_three_verified || 0);
    const total = Number(completion.total_artifacts || 0);
    const pending = Number(completion.pending || 0);
    const summary = $("replicationSummary");
    if (!bootstrap) { summary.textContent = "等待三地密文备份状态"; summary.className = "message needs"; }
    else if (total === 0) { summary.textContent = "尚无归档对象；保存后会显示 0/3 → 3/3"; summary.className = "message needs"; }
    else if (pending === 0) { summary.textContent = `归档完成 3/3：${done} 个对象已回读验证`; summary.className = "message"; }
    else { summary.textContent = `未齐三张收据不会显示完成：${done}/${total} 个对象已完成 3/3，${pending} 个仍在备份`; summary.className = "message needs"; }
  }

  async function connectService() {
    const button = $("connectService");
    button.disabled = true;
    button.textContent = "正在连接…";
    try {
      const endpoint = new URL($("endpoint").value.trim() || config.endpoint).toString().replace(/\/$/, "");
      if (!await ensureOriginPermission(endpoint)) throw new Error("未授权访问该私人档案馆地址");
      config = await SA.setConfig({ endpoint, libraryUrl: config.libraryUrl, token: "" });
      const code = $("pairingCode").value.trim().toUpperCase().replace(/\s+/g, "");
      if (code) {
        const paired = await SA.api(config.pairingPath || "/v1/pairing/exchange", {
          method: "POST", body: JSON.stringify({ code, device_name: "Chrome Extension" }), timeoutMs: 12000
        });
        config = await SA.setConfig({ endpoint: paired.endpoint || endpoint, libraryUrl: paired.library_url || paired.endpoint || endpoint, token: paired.token || "" });
        $("pairingCode").value = "";
      }
      bootstrap = await SA.api("/v1/extension/bootstrap", { timeoutMs: 8000 });
      setServiceState("connected", "已连接");
      message("连接成功。以后无需输入地址或配对码，直接点击保存即可。");
      await Promise.all([renderPlatforms(), renderDestinations()]);
      renderStorage();
    } catch (error) {
      setServiceState("error", "连接失败");
      const hint = error?.status === 401 ? "请输入控制台显示的一次性配对码。" : "请确认服务已部署并可访问。";
      message(`无法连接：${error?.message || "未知错误"} ${hint}`, "error");
    } finally {
      button.disabled = false;
      button.textContent = "一键连接";
    }
  }

  async function renderPlatforms() {
    const serverMap = new Map((bootstrap?.connectors || []).map(item => [item.connector_id, item]));
    const aliases = { xiaohongshu: "xhs", douyin: "douk", kuaishou: "ks", bilibili: "bilibili" };
    const cards = [];
    for (const item of SA.PLATFORM_RULES.filter(value => value.id !== "generic_web")) {
      const browser = await SA.permissionState(item.id);
      const server = serverMap.get(item.id) || serverMap.get(aliases[item.id]);
      const serverState = server?.state || "blocked_environment";
      const usable = browser.authorized;
      const reason = server?.last_message_zh || (server?.last_error_code ? `状态代码：${server.last_error_code}` : server?.next_action_zh || "等待服务端检查");
      cards.push(`<article class="setting-card" data-platform="${item.id}">
        <header><h3>${SA.escapeHtml(item.name)}</h3><span class="card-state ${usable ? "connected" : "needs_user_action"}">${usable ? "页面已授权" : "未授权"}</span></header>
        <p>${usable ? "可一键保存当前页" : "授权后显示悬浮保存按钮"} · 服务连接器：${SA.escapeHtml(SA.statusCopy(serverState))}</p>
        <small class="check-meta">${SA.escapeHtml(checkMeta(server))} · ${SA.escapeHtml(reason)}</small>
        <div class="card-actions"><button class="card-button ${usable ? "" : "primary"}" data-action="${usable ? "remove" : "add"}">${usable ? "撤销授权" : "授权平台"}</button></div>
      </article>`);
    }
    $("platformGrid").innerHTML = cards.join("");
    for (const card of $("platformGrid").querySelectorAll("article")) {
      card.querySelector("button").addEventListener("click", async () => {
        const id = card.dataset.platform;
        const action = card.querySelector("button").dataset.action;
        if (action === "add") await SA.requestPlatformPermission(id); else await SA.removePlatformPermission(id);
        await renderPlatforms();
      });
    }
  }

  function renderDestinations() {
    const serverItems = new Map((bootstrap?.destinations || []).map(item => [item.destination_id, item]));
    const ids = ["social_archive", "markdown", "notion", "obsidian", "github", "karakeep", "linkwarden", "archivebox"];
    const validSelected = config.destinationIds.filter(id => {
      if (id === "social_archive") return true;
      if (id === "obsidian" && config.obsidianLocalEnabled) return true;
      return serverItems.get(id)?.state === "connected";
    });
    if (validSelected.length !== config.destinationIds.length) {
      config = { ...config, destinationIds: validSelected };
      SA.setConfig({ destinationIds: validSelected }).catch(() => {});
    }
    $("destinationGrid").innerHTML = ids.map(id => {
      const item = serverItems.get(id) || {};
      const localObsidian = id === "obsidian" && config.obsidianLocalEnabled;
      const state = localObsidian ? "connected" : (item.state || (id === "social_archive" ? "connected" : "needs_user_action"));
      const connected = state === "connected";
      const configured = localObsidian || item.configured === true || id === "social_archive";
      const selected = config.destinationIds.includes(id) && connected;
      const checkboxDisabled = id === "social_archive" || !connected;
      const checked = checkMeta(item);
      const detail = localObsidian
        ? "扩展已主动检查本机插件，可以自动写入。"
        : (item.last_message_zh || item.next_action_zh || "完成连接后即可自动导入。");
      const action = id === "social_archive"
        ? ""
        : `<button class="card-button" data-probe="${id}">${configured ? "检查连接" : "连接设置"}</button>`;
      return `<article class="setting-card" data-destination="${id}">
        <header><h3>${SA.escapeHtml(SA.destinationLabel(id))}</h3><span class="card-state ${SA.escapeHtml(state)}">${SA.escapeHtml(SA.statusCopy(state))}</span></header>
        <p>${SA.escapeHtml(detail)}</p>
        <small class="check-meta">${connected ? "授权有效" : configured ? "配置已保存" : "尚未配置"} · ${SA.escapeHtml(checked)}</small>
        <div class="card-actions"><label class="card-checkbox"><input type="checkbox" ${selected ? "checked" : ""} ${checkboxDisabled ? "disabled" : ""}>自动导入</label>${action}</div>
      </article>`;
    }).join("");
    for (const card of $("destinationGrid").querySelectorAll("article")) {
      const id = card.dataset.destination;
      const checkbox = card.querySelector('input[type="checkbox"]');
      checkbox.addEventListener("change", async () => {
        const next = new Set(config.destinationIds);
        checkbox.checked ? next.add(id) : next.delete(id);
        config = await SA.setConfig({ destinationIds: [...next] });
      });
      card.querySelector("button[data-probe]")?.addEventListener("click", async event => {
        if (id === "obsidian" && config.obsidianLocalEnabled) return connectObsidian();
        event.currentTarget.disabled = true;
        event.currentTarget.textContent = "正在检查…";
        try {
          const result = await SA.api(`/v1/destinations/${encodeURIComponent(id)}/probe`, { method: "POST", timeoutMs: 25000 });
          message(`${SA.destinationLabel(id)}：${result.last_message_zh || result.next_action_zh || SA.statusCopy(result.state)}`, result.state === "connected" ? "success" : "needs");
          await refresh(false);
        } catch (error) {
          message(`${SA.destinationLabel(id)} 检查失败：${error?.message || "未知错误"}`, "error");
          await refresh(false);
        }
      });
    }
  }

  async function probeConfiguredDestinations() {
    const items = bootstrap?.destinations || [];
    const ids = items
      .filter(item => item.destination_id !== "obsidian" || !config.obsidianLocalEnabled)
      .filter(item => item.configured && item.destination_id !== "social_archive")
      .map(item => item.destination_id);
    if (!ids.length) {
      message("尚无需要服务端检查的目的地；请先完成 Notion、Obsidian、GitHub 或可选阅读器设置。", "needs");
      return;
    }
    const button = $("refreshDestinations");
    button.disabled = true;
    button.textContent = "正在检查…";
    try {
      const results = await Promise.all(ids.map(id => SA.api(`/v1/destinations/${encodeURIComponent(id)}/probe`, { method: "POST", timeoutMs: 25000 })));
      const passed = results.filter(item => item.state === "connected").length;
      message(`已检查 ${results.length} 个目的地：${passed} 个连接有效，${results.length - passed} 个需要处理。`, passed === results.length ? "success" : "needs");
      await refresh(false);
    } finally {
      button.disabled = false;
      button.textContent = "检查全部连接";
    }
  }

  async function connectObsidian() {
    const token = $("obsidianToken").value.trim();
    if (!token) return message("请输入 Obsidian 插件设置页显示的令牌。", "needs", "obsidianMessage");
    let url;
    try { url = obsidianLoopbackUrl($("obsidianUrl").value); }
    catch (error) { return message(error?.message || "Obsidian 地址无效", "error", "obsidianMessage"); }
    const origin = `${SA.OBSIDIAN_LOOPBACK_URL}/*`;
    try {
      const alreadyAllowed = await chrome.permissions.contains({ origins: [origin] });
      if (!alreadyAllowed && !(await chrome.permissions.request({ origins: [origin] }))) {
        return message("未获得本机 Obsidian 访问权限。", "error", "obsidianMessage");
      }
      const response = await fetch(`${url}/health`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      config = await SA.setConfig({ obsidianLocalEnabled: true, obsidianLocalUrl: url, obsidianLocalToken: token });
      message("Obsidian 已连接。打开 Obsidian 时，保存会自动写入 Vault。", "success", "obsidianMessage");
      renderDestinations();
    } catch (error) {
      await SA.setConfig({ obsidianLocalEnabled: false });
      message(`无法连接 Obsidian：${error?.message || "未知错误"}`, "error", "obsidianMessage");
    }
  }

  async function refresh(showConnectionMessage = true) {
    try {
      bootstrap = await SA.api("/v1/extension/bootstrap", { timeoutMs: 6000 });
      setServiceState("connected", "已连接");
    } catch (_) {
      bootstrap = null;
      setServiceState("needs_user_action", "待连接");
      if (showConnectionMessage) message("尚未连接私人档案馆；请先完成第一步。", "needs");
    }
    renderStorage();
    await renderPlatforms();
    renderDestinations();
  }

  async function init() {
    config = await SA.getConfig();
    $("endpoint").value = config.endpoint;
    $("showFloatingButton").checked = config.showFloatingButton;
    $("obsidianUrl").value = SA.OBSIDIAN_LOOPBACK_URL;
    $("obsidianToken").value = config.obsidianLocalToken;
    await refresh();
  }

  $("connectService").addEventListener("click", connectService);
  $("connectObsidian").addEventListener("click", connectObsidian);
  $("refreshDestinations").addEventListener("click", probeConfiguredDestinations);
  $("showFloatingButton").addEventListener("change", async event => {
    config = await SA.setConfig({ showFloatingButton: event.target.checked });
    chrome.runtime.sendMessage({ type: "SA_REFRESH_FAB" }).catch(() => {});
  });
  $("openLibrary").addEventListener("click", async () => chrome.tabs.create({ url: (await SA.getConfig()).libraryUrl }));
  $("finish").addEventListener("click", async () => {
    config = await SA.setConfig({ onboardingComplete: true });
    chrome.tabs.create({ url: config.libraryUrl });
  });
  for (const step of document.querySelectorAll(".step")) {
    step.addEventListener("click", () => document.getElementById(step.dataset.target).scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  init().catch(error => message(error?.message || "设置读取失败", "error"));
})();
