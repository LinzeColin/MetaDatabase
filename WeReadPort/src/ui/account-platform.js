import { AccountApi } from "./account-api.js";
import { readObsidianSelection } from "./obsidian-import.js";

const api = new AccountApi();
const AUTO_SYNC_STALE_SECONDS = 60;
const state = { account: null, view: "overview", busy: false, wereadSyncing: false, notes: [], dashboard: null, providerItems: {}, toastTimer: null, serviceReady: null, serviceDetail: "", autoSyncAccountId: "" };

export async function renderAccountPlatform(root) {
  const oauthReturned = consumeOAuthLoginReturn();
  root.innerHTML = shell();
  bindGlobal(root);
  setBusy(true, "正在安全检查登录状态…");
  try {
    const readiness = await api.readiness();
    state.serviceReady = readiness.ok && readiness.payload?.status === "READY";
    state.serviceDetail = state.serviceReady ? "账户服务可用" : (readiness.payload?.checks?.accountPlatformService?.detail || "账户服务尚未就绪");
    if (state.serviceReady) {
      const session = await api.session();
      state.account = session?.account || null;
    }
  } catch (error) {
    state.serviceReady = false;
    state.serviceDetail = error?.message || "无法连接账户服务";
  }
  setBusy(false);
  await renderCurrent(root);
  if (state.account) void syncWeReadAfterLogin(root, { force: oauthReturned });
}

function shell() {
  return `
    <a class="skip-link" href="#platform-main">跳到主要内容</a>
    <header class="account-topbar">
      <a class="account-brand" href="/" aria-label="阅迁账户平台首页"><span aria-hidden="true">阅</span><div><strong>阅迁</strong><small>阅读资产中心</small></div></a>
      <nav aria-label="公开导航"><a href="/migrate/">匿名迁移工具</a><a href="/privacy/">隐私</a><a href="/terms/">条款</a><a href="/status/">系统状态</a></nav>
      <div id="account-header-actions"></div>
    </header>
    <div id="global-progress" class="global-progress hidden" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span><span>正在处理…</span></div>
    <main id="platform-main" tabindex="-1"></main>
    <div id="toast" class="toast hidden" role="status" aria-live="polite"></div>
  `;
}

async function renderCurrent(root) {
  const main = root.querySelector("#platform-main");
  const actions = root.querySelector("#account-header-actions");
  if (!state.account) {
    actions.innerHTML = `<span class="trust-pill ${state.serviceReady === false ? "danger" : ""}"><span aria-hidden="true">●</span>${state.serviceReady === false ? "账户服务不可用" : "账户数据加密存储"}</span>`;
    if (state.serviceReady === false) {
      main.innerHTML = serviceUnavailableView();
      main.querySelector("#retry-service")?.addEventListener("click", () => renderAccountPlatform(root));
      return;
    }
    main.innerHTML = authView();
    bindAuth(main);
    return;
  }
  actions.innerHTML = `<button class="account-menu-button" id="header-profile" type="button" aria-label="打开账户设置"><span aria-hidden="true">${escapeHtml(initials(state.account.displayName))}</span><strong>${escapeHtml(state.account.displayName)}</strong></button>`;
  main.innerHTML = appView();
  bindApp(main);
  if (state.view === "overview") await loadOverview(main);
  if (state.view === "notes") await loadNotes(main);
  if (state.view === "analytics") await loadAnalytics(main);
  if (state.view === "imports") renderImportHub(main);
  if (state.view === "account") await renderAccount(main);
}

function serviceUnavailableView() {
  return `<section class="service-blocker" aria-labelledby="service-blocker-title"><div class="service-blocker-icon" aria-hidden="true">!</div><p class="eyebrow">登录暂时不可用</p><h1 id="service-blocker-title">账户服务尚未完成安全连接。</h1><p>${escapeHtml(state.serviceDetail || "系统没有通过登录、存储与部署身份就绪检查。")}</p><div class="button-row"><button class="button primary" id="retry-service" type="button">重新检查</button><a class="button secondary" href="/status/">查看系统状态</a><a class="button ghost" href="/migrate/">先用匿名迁移工具</a></div><p class="form-help">系统会在账户后端、加密存储和部署版本全部一致后自动开放注册登录，不会展示无法工作的假入口。</p></section>`;
}

function authView() {
  return `
    <section class="auth-hero" aria-labelledby="auth-title">
      <div class="auth-intro">
        <p class="eyebrow">你的阅读记录，不再困在一个应用里</p>
        <h1 id="auth-title">一个账户，统一保存、同步和理解你的全部阅读笔记。</h1>
        <p>注册后可以绑定微信读书密钥，连接 Notion、Obsidian、GitHub 与 Google Drive。所有笔记、画像和导入记录都只属于你的账户，并可在不同设备继续使用。</p>
        <ol class="beginner-path" aria-label="新手使用步骤">
          <li><span>1</span><div><strong>选择一种登录方式</strong><small>微信读书密钥、邮箱密码或常用平台</small></div></li>
          <li><span>2</span><div><strong>点一下连接数据</strong><small>系统会解释每一步，不需要懂技术术语</small></div></li>
          <li><span>3</span><div><strong>查看笔记与画像</strong><small>跨设备同步、热度趋势和可解释推荐</small></div></li>
        </ol>
        <div class="security-proof"><strong>默认安全边界</strong><ul><li>账户之间严格隔离</li><li>密钥与笔记加密存储</li><li>不会因相同邮箱自动合并账户</li><li>可导出或永久删除全部数据</li></ul></div>
      </div>
      <div class="auth-card" aria-label="注册或登录">
        <div class="auth-mode" role="tablist" aria-label="账户操作">
          <button class="auth-mode-tab active" type="button" role="tab" aria-selected="true" data-mode="register">创建账户</button>
          <button class="auth-mode-tab" type="button" role="tab" aria-selected="false" data-mode="login">登录</button>
        </div>
        <section class="key-first" aria-labelledby="key-auth-title">
          <div class="recommended-label">推荐 · 已有微信读书密钥</div>
          <h2 id="key-auth-title">用密钥快速开始</h2>
          <p>密钥用于验证并连接你的微信读书，账户本身使用独立 ID；以后换密钥也不会丢失笔记。</p>
          <form id="key-auth-form">
            <label for="account-weread-key">微信读书密钥</label>
            <div class="secret-input"><input id="account-weread-key" name="key" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="以 wrk- 开头" required><button class="reveal-secret" type="button" aria-label="显示密钥" aria-pressed="false">显示</button></div>
            <label class="register-only" for="key-display-name">你的昵称</label>
            <input class="register-only" id="key-display-name" name="displayName" autocomplete="name" placeholder="例如：Linz">
            <button class="button primary full" type="submit"><span class="mode-register">验证密钥并创建账户</span><span class="mode-login hidden">用密钥登录</span></button>
          </form>
        </section>
        <div class="auth-divider"><span>也可以使用</span></div>
        <div class="oauth-grid" aria-label="第三方账户">
          <button type="button" class="oauth-button" data-provider="google"><span class="provider-mark">G</span><span class="mode-register">用 Google 创建</span><span class="mode-login hidden">用 Google 登录</span></button>
          <button type="button" class="oauth-button" data-provider="github"><span class="provider-mark">GH</span><span class="mode-register">用 GitHub 创建</span><span class="mode-login hidden">用 GitHub 登录</span></button>
          <button type="button" class="oauth-button" data-provider="notion"><span class="provider-mark">N</span><span class="mode-register">用 Notion 创建</span><span class="mode-login hidden">用 Notion 登录</span></button>
        </div>
        <details class="email-auth">
          <summary>使用邮箱和密码</summary>
          <form id="password-auth-form">
            <label for="account-email">邮箱</label><input id="account-email" name="email" type="email" autocomplete="email" required placeholder="name@example.com">
            <label for="account-password">密码</label><input id="account-password" name="password" type="password" autocomplete="new-password" minlength="12" required placeholder="至少 12 位，包含字母和数字">
            <label class="register-only" for="password-display-name">你的昵称</label><input class="register-only" id="password-display-name" name="displayName" autocomplete="name" placeholder="例如：Linz">
            <p class="form-help register-only">密码不会明文保存；注册后仍可绑定微信读书和其他平台。</p>
            <button class="button secondary full" type="submit"><span class="mode-register">创建邮箱账户</span><span class="mode-login hidden">邮箱密码登录</span></button>
          </form>
        </details>
        <p class="legal-agreement">继续即表示你已阅读并同意<a href="/terms/">使用条款</a>与<a href="/privacy/">隐私政策</a>。</p>
      </div>
    </section>`;
}

function appView() {
  return `
    <div class="account-layout">
      <aside class="account-sidebar" aria-label="账户功能">
        <div class="sidebar-account"><span>${escapeHtml(initials(state.account.displayName))}</span><div><strong>${escapeHtml(state.account.displayName)}</strong><small>阅读资产账户</small></div></div>
        <nav>
          ${navButton("overview", "首页", "⌂")}${navButton("imports", "导入与连接", "↗")}${navButton("notes", "我的笔记", "▤")}${navButton("analytics", "阅读画像", "◫")}${navButton("account", "账户与安全", "⚙")}
        </nav>
        <div class="sidebar-foot"><a href="/status/">系统状态</a><a href="/migrate/">匿名迁移工具</a><button id="logout-button" type="button">退出登录</button></div>
      </aside>
      <section class="account-content" id="account-content">${viewSkeleton()}</section>
    </div>`;
}
function navButton(view, label, icon) { return `<button class="sidebar-nav ${state.view === view ? "active" : ""}" data-view="${view}" type="button"><span aria-hidden="true">${icon}</span>${label}</button>`; }
function viewSkeleton() { return `<div class="content-loading" role="status"><span class="spinner"></span><p>正在读取你的账户数据…</p></div>`; }

function bindGlobal(root) {
  root.querySelector("#account-header-actions").addEventListener("click", event => { if (event.target.closest("#header-profile")) { state.view = "account"; renderCurrent(root); } });
}
function bindAuth(main) {
  let mode = "register";
  const setMode = next => {
    mode = next;
    main.querySelectorAll("[data-mode]").forEach(button => { const active = button.dataset.mode === mode; button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active)); });
    main.querySelectorAll(".mode-register").forEach(node => node.classList.toggle("hidden", mode !== "register"));
    main.querySelectorAll(".mode-login").forEach(node => node.classList.toggle("hidden", mode !== "login"));
    main.querySelectorAll(".register-only").forEach(node => node.classList.toggle("hidden", mode !== "register"));
    const password = main.querySelector("#account-password"); password.autocomplete = mode === "register" ? "new-password" : "current-password";
  };
  main.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => setMode(button.dataset.mode)));
  main.querySelector(".reveal-secret").addEventListener("click", event => { const input = main.querySelector("#account-weread-key"); const showing = input.type === "text"; input.type = showing ? "password" : "text"; event.currentTarget.textContent = showing ? "显示" : "隐藏"; event.currentTarget.setAttribute("aria-pressed", String(!showing)); });
  main.querySelector("#key-auth-form").addEventListener("submit", async event => {
    event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await action(mode === "register" ? "正在验证密钥并创建账户…" : "正在安全登录…", async () => {
      const result = mode === "register" ? await api.registerWeRead(data) : await api.loginWeRead(data);
      state.account = result.account; state.view = "overview"; state.notes = []; state.dashboard = null; await renderCurrent(document);
      return result;
    });
    if (result) void syncWeReadAfterLogin(document, { force: true });
  });
  main.querySelector("#password-auth-form").addEventListener("submit", async event => {
    event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await action(mode === "register" ? "正在创建加密账户…" : "正在安全登录…", async () => {
      const result = mode === "register" ? await api.registerPassword(data) : await api.loginPassword(data);
      state.account = result.account; state.view = "overview"; await renderCurrent(document);
      return result;
    });
    if (result) void syncWeReadAfterLogin(document, { force: true });
  });
  main.querySelectorAll("[data-provider]").forEach(button => button.addEventListener("click", () => action(`正在前往 ${providerLabel(button.dataset.provider)} 授权…`, () => api.oauth(button.dataset.provider, "login"))));
}
function bindApp(main) {
  main.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", async () => { state.view = button.dataset.view; await renderCurrent(document); }));
  main.querySelector("#logout-button").addEventListener("click", () => action("正在安全退出…", async () => { await api.logout(); state.account = null; state.view = "overview"; state.notes = []; state.dashboard = null; state.autoSyncAccountId = ""; await renderCurrent(document); }));
}

async function loadOverview(main) {
  const content = main.querySelector("#account-content");
  let notes = [], dashboard = null;
  try { [notes, dashboard] = await Promise.all([api.notes(), api.analytics()]); } catch (error) { toast(error.message, "error"); }
  state.notes = notes?.notes || []; state.dashboard = dashboard?.dashboard || null;
  const providers = new Set((state.account.connections || []).map(item => item.provider));
  const hasWeRead = (state.account.credentials || []).some(item => item.provider === "weread");
  const next = !hasWeRead ? "绑定微信读书" : providers.size < 1 ? "连接第一个云端来源" : state.notes.length === 0 ? "导入第一批笔记" : "查看阅读画像";
  content.innerHTML = `
    <header class="content-heading"><div><p class="eyebrow">账户首页</p><h1>早上好，${escapeHtml(state.account.displayName)}</h1><p>你的笔记、连接与画像已经绑定到同一账户，可在不同设备继续。</p></div><button class="button primary" id="primary-next" type="button">${next}</button></header>
    <section class="onboarding-card" aria-labelledby="onboarding-title"><div><span class="step-label">新手路线</span><h2 id="onboarding-title">三步完成你的阅读资产中心</h2><p>不需要理解 API、仓库或 Vault。按顺序点按钮即可。</p></div><ol class="onboarding-steps">
      ${onboardingStep(1, hasWeRead, "连接微信读书", hasWeRead ? "已绑定，可随时同步" : "粘贴密钥，系统自动验证")}
      ${onboardingStep(2, providers.size > 0, "连接其他笔记来源", providers.size ? `已连接 ${providers.size} 个平台` : "Notion、Google、GitHub 或 Obsidian")}
      ${onboardingStep(3, state.notes.length > 0, "查看统一笔记和画像", state.notes.length ? `账户中已有 ${state.notes.length} 条笔记` : "导入后自动生成趋势与推荐")}
    </ol></section>
    <section class="metric-grid" aria-label="账户概览">
      ${metric("笔记总数", state.notes.length, "所有来源统一保存")}${metric("已连接来源", providers.size + (hasWeRead ? 1 : 0), "可随时新增或解绑")}${metric("近 90 天活跃", state.dashboard?.summary?.activeDays90 ?? 0, "只在你同意后统计")}${metric("潜在推荐", state.dashboard?.recommendations?.length ?? 0, "每条都有推荐理由")}
    </section>
    ${homeReadingProfile(state.dashboard, state.account, hasWeRead)}
    <section class="quick-grid"><article><div><span class="source-logo weread">微</span><div><h2>微信读书同步</h2><p>${hasWeRead ? "首次完整整理；之后只检查真实变化的书籍与笔记。" : "先绑定本人密钥；密钥不是账户主键，可安全轮换。"}</p></div></div><button id="quick-weread" class="button ${hasWeRead ? "secondary" : "primary"}" type="button">${hasWeRead ? "立即同步" : "绑定密钥"}</button></article>
      <article><div><span class="source-logo cloud">云</span><div><h2>一键导入</h2><p>Notion、Obsidian、GitHub、Google Drive 都会用中文一步一步引导。</p></div></div><button id="quick-import" class="button secondary" type="button">选择来源</button></article>
      <article><div><span class="source-logo chart">析</span><div><h2>阅读画像</h2><p>热度、趋势、主题偏好和潜在推荐，不使用模型 Token。</p></div></div><button id="quick-analytics" class="button secondary" type="button">查看画像</button></article></section>
    ${state.notes.length ? `<section class="recent-section"><div class="section-title"><h2>最近更新</h2><button data-go="notes" type="button">查看全部</button></div>${noteList(state.notes.slice(0, 5), false)}</section>` : emptyState("还没有笔记", "先连接一个来源，系统会把不同平台的笔记整理到同一个账户。", "去导入", "imports")}`;
  content.querySelector("#primary-next").addEventListener("click", () => { state.view = next === "查看阅读画像" ? "analytics" : "imports"; renderCurrent(document); });
  content.querySelector("#quick-import").addEventListener("click", () => { state.view = "imports"; renderCurrent(document); });
  content.querySelector("#quick-analytics").addEventListener("click", () => { state.view = "analytics"; renderCurrent(document); });
  content.querySelector("#quick-weread").addEventListener("click", () => hasWeRead ? runWeReadSync(content) : openWeReadDialog(content));
  content.querySelectorAll("[data-download-weread]").forEach(button => button.addEventListener("click", () => runSensitiveAction("weread-export")));
  content.querySelectorAll("[data-go-analytics]").forEach(button => button.addEventListener("click", () => { state.view = "analytics"; renderCurrent(document); }));
  content.querySelectorAll("[data-go]").forEach(button => button.addEventListener("click", () => { state.view = button.dataset.go; renderCurrent(document); }));
}
function onboardingStep(number, done, title, detail) { return `<li class="${done ? "done" : ""}"><span>${done ? "✓" : number}</span><div><strong>${title}</strong><small>${detail}</small></div></li>`; }
function metric(label, value, detail) { return `<article class="metric-card"><p>${label}</p><strong>${escapeHtml(String(value))}</strong><small>${detail}</small></article>`; }
function homeReadingProfile(dashboard, account, hasWeRead) {
  if (!dashboard) return "";
  const categories = (dashboard.categoryDistribution || []).slice(0, 3);
  const recommendations = (dashboard.recommendations || []).slice(0, 3);
  const coverage = account?.weread?.summary?.coverage;
  const coverageText = !hasWeRead ? "绑定微信读书后会显示官方数据核对结果。" : coverage ? (coverage.verified ? `已核对 ${coverage.accountedDocuments || 0} 条可导入内容；源端报告 ${coverage.sourceReportedNotes || 0} 条。` : `当前尚有 ${coverage.unresolvedDocuments || 0} 条待确认；可从“导入与连接”发起完整核对。`) : "尚未完成首次数据核对。";
  return `<section class="home-profile-card" aria-labelledby="home-profile-title"><div class="section-title"><div><p class="eyebrow">阅读画像</p><h2 id="home-profile-title">你的阅读偏好，已经整合到首页</h2><p>${escapeHtml(coverageText)}</p></div><button class="button secondary" data-go-analytics type="button">查看完整画像</button></div><div class="home-profile-grid"><div><span>近 90 天活跃</span><strong>${escapeHtml(String(dashboard.summary?.activeDays90 ?? 0))} 天</strong></div><div><span>已汇总来源</span><strong>${escapeHtml(String(dashboard.summary?.sourceCount ?? 0))} 个</strong></div><div><span>估算字数</span><strong>${escapeHtml(numberFormat(dashboard.summary?.estimatedWords || 0))}</strong></div></div>${categories.length ? `<div class="profile-topics"><strong>高频主题</strong><div>${categories.map(item => `<span>${escapeHtml(item.label)} · ${escapeHtml(String(item.value))}</span>`).join("")}</div></div>` : ""}${recommendations.length ? `<div class="home-recommendations"><strong>潜在下一步</strong><div>${recommendations.map(item => `<article><div><small>${escapeHtml(sourceName(item.source))}</small><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.reason)}</p></div>${recommendationLink(item)}</article>`).join("")}</div></div>` : ""}${hasWeRead ? `<div class="home-profile-actions"><button class="button ghost" data-download-weread type="button">下载微信读书数据（JSON）</button></div>` : ""}</section>`;
}

function renderImportHub(main) {
  const content = main.querySelector("#account-content");
  const connections = state.account.connections || [];
  const connected = new Set(connections.filter(item => item.importReady !== false).map(item => item.provider));
  const hasWeRead = (state.account.credentials || []).some(item => item.provider === "weread");
  content.innerHTML = `
    <header class="content-heading"><div><p class="eyebrow">导入与连接</p><h1>选择你现在使用的应用</h1><p>每个入口都只要求你做一件事；系统自动处理格式、分页和重复内容。</p></div></header>
    <div class="beginner-notice"><strong>不知道怎么选？</strong><p>你在哪里写笔记，就点哪个图标。Obsidian 选本机文件夹；其他平台会打开官方授权页面。</p></div>
    <section class="source-card-grid" aria-label="可导入来源">
      ${sourceCard("weread", "微信读书", "微", hasWeRead, hasWeRead ? "首次完整整理；之后只同步真实变化的书籍、划线和想法" : "粘贴本人密钥并绑定账户", hasWeRead ? "立即同步" : "绑定并同步")}
      ${sourceCard("notion", "Notion", "N", connected.has("notion"), "授权后选择页面；系统自动展开页面内容", connected.has("notion") ? "选择页面" : "一键连接")}
      ${sourceCard("obsidian", "Obsidian", "O", true, "直接选择 Vault 文件夹或导出的 ZIP，无需安装插件", "选择文件夹")}
      ${sourceCard("github", "GitHub", "GH", connected.has("github"), "先授权读取仓库，再勾选 Markdown、TXT 或 JSON；平台只执行读取", connected.has("github") ? "选择仓库" : "授权读取")}
      ${sourceCard("google", "Google Drive", "G", connected.has("google"), "Google 登录不自动读取网盘；点击后单独授权只读范围", connected.has("google") ? "选择文件" : "授权只读")}
    </section>
    ${hasWeRead ? wereadDataControls(state.account) : ""}
    <section id="import-workspace" class="import-workspace hidden" aria-live="polite"></section>
    <input id="obsidian-folder" type="file" webkitdirectory directory multiple hidden>
    <input id="obsidian-files" type="file" accept=".zip,.md,.markdown,.txt" multiple hidden>`;
  content.querySelectorAll("[data-source]").forEach(button => button.addEventListener("click", async () => {
    const provider = button.dataset.source;
    if (provider === "weread") { if (hasWeRead) await runWeReadSync(content); else openWeReadDialog(content); return; }
    if (provider === "obsidian") { openObsidianChooser(content); return; }
    if (!connected.has(provider)) { await action(`正在前往 ${providerLabel(provider)} 官方授权读取…`, () => api.oauth(provider, "import")); return; }
    await openProviderPicker(content, provider);
  }));
  content.querySelector("#weread-full-sync")?.addEventListener("click", () => runWeReadSync(content, { forceFull: true, preserveView: true }));
  content.querySelector("#weread-download")?.addEventListener("click", () => runSensitiveAction("weread-export"));
}
function sourceCard(id, name, mark, connected, description, actionLabel) { return `<article class="source-card"><div class="source-card-head"><span class="source-logo ${id}">${mark}</span><span class="connection-state ${connected ? "connected" : ""}">${connected ? "已连接" : "未连接"}</span></div><h2>${name}</h2><p>${description}</p><button class="button ${connected ? "secondary" : "primary"} full" data-source="${id}" type="button">${actionLabel}</button></article>`; }
function wereadDataControls(account) {
  const coverage = account?.weread?.summary?.coverage;
  const verified = Boolean(coverage?.verified);
  const sourceNotes = Number(coverage?.sourceReportedNotes || 0);
  const accounted = Number(coverage?.accountedDocuments || 0);
  const unresolved = Number(coverage?.unresolvedDocuments || 0);
  const summary = !coverage ? "尚未完成首次完整核对；首次同步会读取当前可访问的书籍、划线和想法。" : verified ? `核对通过：源端报告 ${sourceNotes} 条，已确认 ${accounted} 条可导入内容。书签只有官方计数时不会被伪装成正文。` : `尚未完成完整确认：当前已核对 ${accounted} 条，仍有 ${unresolved} 条待确认。完整核对不会删除你现有笔记。`;
  return `<section class="weread-data-controls"><div><p class="eyebrow">微信读书数据</p><h2>${verified ? "数据覆盖已核验" : "先核对，再判断是否完整"}</h2><p>${escapeHtml(summary)}</p></div><div class="button-row"><button id="weread-full-sync" class="button secondary" type="button">完整核对全部数据</button><button id="weread-download" class="button primary" type="button">下载已同步数据（JSON）</button></div></section>`;
}

function openWeReadDialog(content) {
  const workspace = content.querySelector("#import-workspace") || content;
  workspace.classList.remove("hidden");
  workspace.innerHTML = `<div class="guided-panel"><div class="guide-number">1</div><div><h2>绑定你的微信读书密钥</h2><p>复制以 <code>wrk-</code> 开头的本人密钥并粘贴。系统验证成功后会加密保存到你的账户；密钥可随时轮换，不会成为数据库主键。</p><form id="bind-weread"><label for="bind-weread-key">微信读书密钥</label><input id="bind-weread-key" name="key" type="password" autocomplete="off" required placeholder="wrk-…"><button class="button primary" type="submit">验证、绑定并开始同步</button></form><p class="form-help">不要使用他人的密钥。系统不会把密钥写入日志、状态页或导出文件。</p></div></div>`;
  workspace.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "center" });
  workspace.querySelector("#bind-weread").addEventListener("submit", async event => {
    event.preventDefault();
    const key = new FormData(event.currentTarget).get("key");
    const result = await action("正在验证并绑定微信读书…", async () => {
      const response = await api.bindWeRead(key);
      state.account = response.account;
      return response;
    });
    if (result) {
      toast("微信读书已绑定，正在后台同步数据。", "success");
      void runWeReadSync(content, { automatic: true });
    }
  });
}
function consumeOAuthLoginReturn() {
  const url = new URL(location.href);
  const returned = Boolean(url.searchParams.get("oauth")) && url.searchParams.get("status") === "connected";
  if (returned) {
    url.searchParams.delete("oauth");
    url.searchParams.delete("status");
    history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }
  return returned;
}
function hasWeReadCredential(account = state.account) { return Boolean(account?.credentials?.some(item => item.provider === "weread")); }
async function syncWeReadAfterLogin(root, { force = false } = {}) {
  const account = state.account;
  if (!hasWeReadCredential(account) || state.autoSyncAccountId === account.id) return;
  const lastSyncAt = Number(account.weread?.lastSyncAt || 0);
  if (!force && lastSyncAt > 0 && Date.now() / 1000 - lastSyncAt < AUTO_SYNC_STALE_SECONDS) return;
  state.autoSyncAccountId = account.id;
  await runWeReadSync(root.querySelector("#account-content"), { automatic: true });
}
async function runWeReadSync(content, { automatic = false, forceFull = false, preserveView = false } = {}) {
  if (state.wereadSyncing) { toast("微信读书正在同步，请稍候。", "info"); return undefined; }
  const complete = async () => {
    const result = await api.wereadSync(forceFull ? "full" : "auto");
    const summary = result.summary || {};
    const scope = summary.syncMode === "incremental"
      ? `快速核对 ${summary.notebookBooks || 0} 本书，跳过 ${summary.skippedUnchangedBooks || 0} 本无变化书籍`
      : `完整整理 ${summary.notebookBooks || 0} 本书`;
    const coverage = summary.coverage || result.coverage || {};
    const verification = coverage.verified ? "覆盖已核验" : coverage.unresolvedDocuments ? `仍有 ${coverage.unresolvedDocuments} 条待确认` : "覆盖待完整核对";
    toast(`同步完成：${scope}；${summary.updatedDocuments ?? summary.importedDocuments ?? 0} 条更新，${summary.unchangedDocuments || 0} 条已是最新；${verification}。`, result.failures?.length || !coverage.verified && summary.syncMode === "full" ? "warning" : "success");
    const profile = await api.profile();
    state.account = profile.account;
    if (automatic) {
      if (["overview", "notes"].includes(state.view)) await renderCurrent(document);
    } else {
      if (!preserveView) state.view = "notes";
      await renderCurrent(document);
    }
    return result;
  };
  if (!automatic) return action("正在同步微信读书最新变化…", complete);
  state.wereadSyncing = true;
  toast(forceFull ? "正在后台完整核对微信读书数据…" : "已登录，正在后台检查微信读书最新变化…", "info");
  try { return await complete(); }
  catch (error) {
    toast(error?.message || "微信读书同步失败，请稍后重试。", "error");
    console.error(JSON.stringify({ event: "weread_background_sync_failed", code: String(error?.code || "REQUEST_FAILED") }));
    return undefined;
  } finally { state.wereadSyncing = false; }
}
function openObsidianChooser(content) {
  const workspace = content.querySelector("#import-workspace");
  workspace.classList.remove("hidden");
  workspace.innerHTML = `<div class="guided-panel"><div class="guide-number">1</div><div><h2>选择 Obsidian 笔记</h2><p><strong>最简单：</strong>点“选择 Vault 文件夹”，在电脑里找到平时打开的 Obsidian 文件夹并确认。系统只读取 Markdown/TXT 文本，不上传图片或插件配置。</p><div class="button-row"><button id="choose-vault" class="button primary" type="button">选择 Vault 文件夹</button><button id="choose-obsidian-files" class="button secondary" type="button">我只有 ZIP 或 Markdown</button></div><div id="obsidian-selection" class="selection-status hidden"></div></div></div>`;
  const folder = content.querySelector("#obsidian-folder"), files = content.querySelector("#obsidian-files");
  workspace.querySelector("#choose-vault").addEventListener("click", () => folder.click());
  workspace.querySelector("#choose-obsidian-files").addEventListener("click", () => files.click());
  const onSelect = async input => { await action("正在本地整理 Obsidian 文件…", async () => { const selection = await readObsidianSelection(input.files); workspace.querySelector("#obsidian-selection").classList.remove("hidden"); workspace.querySelector("#obsidian-selection").innerHTML = `<strong>已找到 ${selection.totalFiles} 条文本笔记</strong><p>来源：${escapeHtml(selection.sourceLabel)}。确认后进入账户级加密导入队列。</p><button id="confirm-obsidian" class="button primary" type="button">确认导入</button>`; workspace.querySelector("#confirm-obsidian").addEventListener("click", () => startJob("obsidian", selection)); }); };
  folder.onchange = () => onSelect(folder); files.onchange = () => onSelect(files);
  workspace.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "center" });
}
async function openProviderPicker(content, provider, container = "") {
  const workspace = content.querySelector("#import-workspace"); workspace.classList.remove("hidden"); workspace.innerHTML = `<div class="content-loading"><span class="spinner"></span><p>正在读取 ${providerLabel(provider)} 可选内容…</p></div>`;
  await action(null, async () => {
    const result = await api.providerItems(provider, container ? { container } : {});
    if (result.kind === "containers") {
      workspace.innerHTML = picker(provider, result.items, "先选择一个仓库", true);
      bindPicker(workspace, provider, true);
    } else {
      workspace.innerHTML = picker(provider, result.items, `选择要从 ${providerLabel(provider)} 导入的内容`, false);
      bindPicker(workspace, provider, false, container);
    }
    workspace.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" });
  });
}
function picker(provider, items, title, containers) { return `<div class="picker-panel"><div class="section-title"><div><p class="eyebrow">${containers ? "第 1 步" : "最后一步"}</p><h2>${title}</h2><p>${containers ? "只会显示你已授权访问的仓库。" : "默认不全选，先检查名称，再确认导入。"}</p></div></div>${items.length ? `<div class="picker-list">${items.map(item => `<label class="picker-item"><input type="${containers ? "radio" : "checkbox"}" name="picker" value="${escapeAttr(item.id)}"><span><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.detail || "")}</small></span></label>`).join("")}</div><button id="picker-confirm" class="button primary" type="button">${containers ? "查看这个仓库" : "导入所选内容"}</button>` : `<div class="empty-inline"><strong>没有找到可导入内容</strong><p>检查平台授权范围，或返回选择其他来源。</p></div>`}</div>`; }
function bindPicker(workspace, provider, containers, container = "") { const button = workspace.querySelector("#picker-confirm"); if (!button) return; button.addEventListener("click", async () => { const selected = [...workspace.querySelectorAll("input[name=picker]:checked")].map(input => input.value); if (!selected.length) { toast("请先选择至少一项。", "warning"); return; } if (containers) { await openProviderPicker(document.querySelector("#account-content"), provider, selected[0]); return; } const labels = new Map([...workspace.querySelectorAll(".picker-item")].map(label => [label.querySelector("input").value, label.querySelector("strong").textContent])); await startJob(provider, { container, items: selected.map(id => ({ id, label: labels.get(id), ...(provider === "google" ? { mimeType: inferGoogleType(id, workspace) } : {}) })) }); }); }
function inferGoogleType(id, workspace) { const input = [...workspace.querySelectorAll("input")].find(item => item.value === id); return input?.closest("label")?.querySelector("small")?.textContent === "Google 文档" ? "application/vnd.google-apps.document" : "text/plain"; }
async function startJob(provider, selection) { await action("正在建立安全导入任务…", async () => { const result = await api.startImport(provider, selection); toast("导入任务已建立，系统正在后台处理。", "success"); await waitForJob(result.job.id); state.view = "notes"; await renderCurrent(document); }); }
async function waitForJob(id) { for (let attempt = 0; attempt < 40; attempt += 1) { const result = await api.importJob(id); if (result.job.state === "COMPLETE") { toast(`导入完成：${result.job.progress.saved || 0} 条笔记。`, "success"); return result.job; } if (result.job.state === "FAILED") throw new Error("导入失败，请检查授权或文件后重试。"); await delay(500); } throw new Error("导入仍在处理，可稍后在笔记页刷新查看。"); }

async function loadNotes(main) {
  const content = main.querySelector("#account-content");
  let result; try { result = await api.notes(); } catch (error) { toast(error.message, "error"); result = { notes: [] }; }
  state.notes = result.notes || [];
  content.innerHTML = `<header class="content-heading"><div><p class="eyebrow">我的笔记</p><h1>所有来源，统一保存在你的账户</h1><p>每条笔记都有来源、版本与更新时间；跨设备修改使用乐观冲突保护。</p></div><button class="button primary" id="add-note" type="button">新建笔记</button></header><div class="note-toolbar"><label for="note-search">搜索笔记</label><input id="note-search" type="search" placeholder="输入标题或来源"><span>${state.notes.length} 条</span></div><div id="notes-list">${state.notes.length ? noteList(state.notes, true) : emptyStateMarkup("还没有笔记", "从微信读书、Notion、Obsidian、GitHub 或 Google Drive 导入，或手动新建。", "去导入", "imports")}</div>`;
  content.querySelector("#add-note").addEventListener("click", () => noteEditor(content));
  content.querySelector("#note-search").addEventListener("input", event => { const q = event.target.value.trim().toLowerCase(); const filtered = state.notes.filter(note => `${note.title} ${note.source} ${note.category}`.toLowerCase().includes(q)); content.querySelector("#notes-list").innerHTML = filtered.length ? noteList(filtered, true) : `<div class="empty-inline"><strong>没有匹配笔记</strong><p>换一个关键词试试。</p></div>`; bindNoteRows(content); });
  bindNoteRows(content);
  content.querySelectorAll("[data-go]").forEach(button => button.addEventListener("click", () => { state.view = button.dataset.go; renderCurrent(document); }));
}
function noteList(notes, interactive) { return `<div class="note-list">${notes.map(note => `<article class="note-row" ${interactive ? `data-note="${escapeAttr(note.id)}" tabindex="0"` : ""}><span class="note-source">${sourceName(note.source)}</span><div><h3>${escapeHtml(note.title)}</h3><p>${escapeHtml(note.category || "未分类")} · ${noteTimeLabel(note)} · 版本 ${note.version}</p></div><span class="note-arrow" aria-hidden="true">›</span></article>`).join("")}</div>`; }
function bindNoteRows(content) { content.querySelectorAll("[data-note]").forEach(row => { const open = () => openNote(content, row.dataset.note); row.addEventListener("click", open); row.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); open(); } }); }); }
async function openNote(content, id) { await action("正在解密笔记…", async () => { const result = await api.note(id); noteEditor(content, result.note); }); }
function noteEditor(content, note = null) {
  const host = document.createElement("div"); host.className = "modal-backdrop"; host.innerHTML = `<section class="modal" role="dialog" aria-modal="true" aria-labelledby="note-editor-title"><div class="modal-head"><div><p class="eyebrow">${note ? "编辑笔记" : "新建笔记"}</p><h2 id="note-editor-title">${note ? escapeHtml(note.title) : "记录新的阅读想法"}</h2></div><button class="modal-close" type="button" aria-label="关闭">×</button></div><form id="note-editor"><label for="note-title">标题</label><input id="note-title" name="title" required maxlength="180" value="${escapeAttr(note?.title || "")}"><label for="note-category">分类</label><input id="note-category" name="category" maxlength="80" value="${escapeAttr(note?.category || "手动笔记")}"><label for="note-content">正文</label><textarea id="note-content" name="content" required rows="14">${escapeHtml(note?.content || "")}</textarea><div class="modal-actions">${note ? `<button class="button danger" id="delete-note" type="button">删除</button>` : ""}<button class="button secondary modal-close-action" type="button">取消</button><button class="button primary" type="submit">加密保存</button></div></form></section>`; document.body.append(host); const close = () => host.remove(); host.querySelectorAll(".modal-close,.modal-close-action").forEach(button => button.addEventListener("click", close)); host.addEventListener("click", event => { if (event.target === host) close(); }); host.querySelector("#note-editor").addEventListener("submit", async event => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget)); await action("正在加密保存…", async () => { await api.saveNote({ ...data, source: note?.source || "manual", externalId: note?.externalId || crypto.randomUUID(), expectedVersion: note?.version ?? null }); close(); toast("笔记已保存并加入跨设备同步。", "success"); await loadNotes(document.querySelector("#platform-main")); }); }); const del = host.querySelector("#delete-note"); if (del) del.addEventListener("click", () => action("正在删除…", async () => { await api.deleteNote(note.id, note.version); close(); toast("笔记已删除。", "success"); await loadNotes(document.querySelector("#platform-main")); })); host.querySelector("input")?.focus();
}

async function loadAnalytics(main) {
  const content = main.querySelector("#account-content"); let result; try { result = await api.analytics(); } catch (error) { toast(error.message, "error"); result = { dashboard: null }; } const d = result.dashboard; state.dashboard = d;
  if (!d) { content.innerHTML = emptyStateMarkup("暂时无法生成画像", "请稍后重试。", "返回首页", "overview"); return; }
  content.innerHTML = `<header class="content-heading"><div><p class="eyebrow">阅读画像</p><h1>你的阅读热度、主题与潜在下一步</h1><p>所有统计都在你的账户范围内确定性计算；不会把笔记正文发送给模型。</p></div><button class="button secondary" id="analytics-settings" type="button">隐私设置</button></header>
    <section class="consent-banner ${d.consent?.behaviorAnalytics ? "enabled" : ""}"><div><strong>${d.consent?.behaviorAnalytics ? "行为分析已开启" : "行为分析默认关闭"}</strong><p>${d.consent?.behaviorAnalytics ? "你可以随时关闭，关闭后非必要行为事件会被删除。" : "当前热度主要来自笔记更新时间；开启后可记录阅读时段等非正文事件。"}</p></div><button id="toggle-analytics" class="button ${d.consent?.behaviorAnalytics ? "ghost" : "primary"}" type="button">${d.consent?.behaviorAnalytics ? "关闭" : "开启"}</button></section>
    <section class="metric-grid">${metric("笔记", d.summary.noteCount, "账户内加密正文")}${metric("来源", d.summary.sourceCount, "已汇总来源")}${metric("估算字数", numberFormat(d.summary.estimatedWords), "仅用于个人统计")}${metric("活跃天数", d.summary.activeDays90, "最近 90 天")}</section>
    <section class="analytics-grid"><article class="chart-card"><div class="section-title"><div><h2>12 周笔记趋势</h2><p>每周新增或更新的笔记数量</p></div></div>${barChart(d.weeklyTrend || [])}</article><article class="chart-card"><div class="section-title"><div><h2>来源分布</h2><p>你的笔记主要来自哪里</p></div></div>${distribution(d.sourceDistribution || [])}</article></section>
    <section class="heatmap-card"><div class="section-title"><div><h2>近 90 天阅读热度</h2><p>颜色越深表示当天记录或阅读活动越多</p></div><span class="heat-legend">少 <i></i><i></i><i></i><i></i> 多</span></div>${heatmap(d.readingHeatmap || [])}</section>
    <section class="recommend-card"><div class="section-title"><div><h2>潜在推荐</h2><p>每条都显示来源和理由；微信读书官方推荐会直达真实书籍详情页。</p></div></div>${d.recommendations?.length ? `<div class="recommend-list">${d.recommendations.map(item => `<article><span>${escapeHtml(sourceName(item.source))}</span><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.reason)}</p></div>${recommendationLink(item)}</article>`).join("")}</div>` : `<div class="empty-inline"><strong>还没有足够数据</strong><p>导入第一批笔记并开启推荐个性化后，这里会出现可解释建议。</p></div>`}</section>`;
  content.querySelector("#analytics-settings").addEventListener("click", () => { state.view = "account"; renderCurrent(document); });
  content.querySelector("#toggle-analytics").addEventListener("click", () => action("正在更新隐私选择…", async () => { const consent = state.account.consent || {}; await api.updateConsent({ behaviorAnalytics: !d.consent.behaviorAnalytics, recommendationPersonalization: consent.recommendationPersonalization || false }); const profile = await api.profile(); state.account = profile.account; await loadAnalytics(document.querySelector("#platform-main")); }));
}
function barChart(items) { const max = Math.max(1, ...items.map(item => Number(item.value || 0))); return `<div class="bar-chart" role="img" aria-label="最近十二周笔记趋势">${items.map(item => `<div><span style="height:${Math.max(4, Number(item.value || 0) / max * 100)}%" title="${item.week}：${item.value}"></span><small>${item.week.slice(5)}</small></div>`).join("")}</div>`; }
function distribution(items) { const total = Math.max(1, items.reduce((sum, item) => sum + Number(item.value || 0), 0)); return `<div class="distribution-list">${items.slice(0, 8).map(item => `<div><span>${escapeHtml(sourceName(item.label))}</span><div><i style="width:${Number(item.value || 0) / total * 100}%"></i></div><strong>${item.value}</strong></div>`).join("") || `<p>暂无数据</p>`}</div>`; }
function heatmap(items) { return `<div class="heatmap" role="img" aria-label="近九十天阅读热度">${items.map(item => `<span class="level-${item.level}" title="${item.date}：${item.value}" aria-label="${item.date}，热度 ${item.value}"></span>`).join("")}</div>`; }
function recommendationLink(item) {
  const link = officialRecommendationLink(item);
  return link ? `<a href="${escapeAttr(link)}" rel="noopener noreferrer" target="_blank">${item.source === "weread-official" ? "在微信读书打开" : "查看"}</a>` : "";
}
function officialRecommendationLink(item) {
  const raw = String(item?.deepLink || "");
  try {
    const url = new URL(raw);
    if (url.protocol === "https:" && url.hostname === "weread.qq.com" && url.pathname.startsWith("/web/")) return url.toString();
  } catch { /* 继续从官方推荐 ID 补全链接 */ }
  if (item?.source !== "weread-official") return "";
  const bookId = String(item?.id || "").replace(/^weread:/u, "").trim();
  return /^[A-Za-z0-9_-]{6,256}$/.test(bookId) ? `https://weread.qq.com/web/bookDetail/${encodeURIComponent(bookId)}` : "";
}

async function renderAccount(main) {
  const content = main.querySelector("#account-content");
  const credentials = state.account.credentials || [];
  const connections = state.account.connections || [];
  const consent = state.account.consent || {};
  const hasPassword = credentials.some(item => item.kind === "password");
  let sessions = [];
  try { sessions = (await api.sessions()).sessions || []; }
  catch { sessions = []; }
  content.innerHTML = `<header class="content-heading"><div><p class="eyebrow">账户与安全</p><h1>管理你的身份、设备、连接和数据选择</h1><p>账户 ID 不随密钥或登录方式变化；新增登录方式不会自动合并其他账户。</p></div></header>
    <section class="settings-card"><h2>个人资料</h2><form id="profile-form"><label for="profile-name">显示昵称</label><div class="inline-form"><input id="profile-name" name="displayName" maxlength="80" value="${escapeAttr(state.account.displayName)}"><button class="button secondary" type="submit">保存</button></div></form><dl class="account-meta"><div><dt>账户 ID</dt><dd><code>${escapeHtml(state.account.id)}</code></dd></div><div><dt>界面语言</dt><dd>简体中文</dd></div><div><dt>创建时间</dt><dd>${formatDate(state.account.createdAt)}</dd></div></dl></section>
    <section class="settings-card"><div class="section-title"><div><h2>登录方式</h2><p>密钥是微信读书连接凭据，账户主体是不可变账户 ID；至少保留一种可用登录方式。</p></div></div><div class="credential-list">${credentials.map(item => `<article><span class="source-logo ${item.provider}">${providerMark(item.provider)}</span><div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(providerLabel(item.provider))} · ${formatDate(item.updatedAt)}</small></div><span class="connection-state connected">已绑定</span></article>`).join("")}</div><div class="button-row"><button id="configure-password" class="button secondary" type="button">${hasPassword ? "修改邮箱和密码" : "设置邮箱和密码"}</button><button id="bind-weread-account" class="button secondary" type="button">${credentials.some(item => item.provider === "weread") ? "轮换微信读书密钥" : "绑定微信读书密钥"}</button>${["google", "github", "notion"].filter(provider => !credentials.some(item => item.provider === provider)).map(provider => `<button class="button ghost link-provider" data-provider="${provider}" type="button">绑定 ${providerLabel(provider)}</button>`).join("")}</div><p class="form-help">不会因为 Google、GitHub、Notion 或邮箱相同而静默合并账户；绑定始终需要在当前已登录账户内明确操作。</p></section>
    <section class="settings-card"><div class="section-title"><div><h2>已登录设备</h2><p>查看当前与其他设备会话。撤销后对应设备必须重新登录。</p></div><button id="revoke-other-sessions" class="button ghost" type="button" ${sessions.length <= 1 ? "disabled" : ""}>退出其他设备</button></div><div class="credential-list session-list">${sessions.length ? sessions.map(item => `<article><span class="source-logo">${item.current ? "本" : "端"}</span><div><strong>${item.current ? "当前设备" : "已登录设备"}</strong><small>最近活动 ${formatDateTime(item.lastSeenAt)} · 到期 ${formatDateTime(item.expiresAt)}${item.ipHint ? ` · 网络 ${escapeHtml(item.ipHint)}` : ""}</small></div>${item.current ? `<span class="connection-state connected">当前</span>` : `<button class="button ghost revoke-session" data-session-id="${escapeAttr(item.id)}" type="button">退出</button>`}</article>`).join("") : `<div class="empty-inline"><strong>暂时无法读取设备列表</strong><p>刷新页面后重试；这不会影响当前登录。</p></div>`}</div></section>
    <section class="settings-card"><h2>云端连接</h2><p>连接令牌按账户密钥加密；导入只使用只读或最小必要权限。</p><div class="credential-list">${connections.length ? connections.map(item => `<article><span class="source-logo ${item.provider}">${providerMark(item.provider)}</span><div><strong>${providerLabel(item.provider)}</strong><small>${escapeHtml(item.metadata?.emailHint || item.metadata?.workspaceName || "已授权")}</small></div><span class="connection-state connected">已连接</span></article>`).join("") : `<div class="empty-inline"><strong>尚未连接云端来源</strong><p>到“导入与连接”选择常用应用。</p></div>`}</div></section>
    <section class="settings-card"><h2>画像与行为分析</h2><div class="toggle-row"><div><strong>行为分析</strong><p>只记录阅读时段等结构化事件，不记录笔记正文。</p></div><button id="behavior-toggle" class="switch ${consent.behaviorAnalytics ? "on" : ""}" type="button" role="switch" aria-checked="${Boolean(consent.behaviorAnalytics)}"><span></span></button></div><div class="toggle-row"><div><strong>个性化推荐</strong><p>使用账户内主题和官方推荐生成可解释建议，不调用模型。</p></div><button id="recommend-toggle" class="switch ${consent.recommendationPersonalization ? "on" : ""}" type="button" role="switch" aria-checked="${Boolean(consent.recommendationPersonalization)}"><span></span></button></div></section>
    <section class="settings-card danger-zone"><h2>导出与删除</h2><p>敏感操作需要近期重新验证。可单独下载微信读书已同步笔记，也可导出完整账户资料；永久删除会清除对象存储与账户索引。</p><div class="button-row"><button id="export-weread" class="button primary" type="button">下载微信读书数据（JSON）</button><button id="export-account" class="button secondary" type="button">导出我的全部数据</button><button id="delete-account" class="button danger" type="button">永久删除账户</button></div></section>`;
  content.querySelector("#profile-form").addEventListener("submit", async event => { event.preventDefault(); await action("正在保存资料…", async () => { const result = await api.updateProfile(Object.fromEntries(new FormData(event.currentTarget))); state.account = result.account; toast("个人资料已保存。", "success"); await renderCurrent(document); }); });
  content.querySelector("#configure-password").addEventListener("click", () => passwordDialog(hasPassword));
  content.querySelector("#bind-weread-account").addEventListener("click", () => accountSecurityDialog(credentials.some(item => item.provider === "weread") ? "rotate" : "bind"));
  content.querySelectorAll(".link-provider").forEach(button => button.addEventListener("click", () => api.oauth(button.dataset.provider, "link")));
  content.querySelectorAll(".revoke-session").forEach(button => button.addEventListener("click", () => guardedSensitive("正在退出该设备…", "session", async () => { await api.revokeSession(button.dataset.sessionId); toast("该设备已退出登录。", "success"); await renderCurrent(document); })));
  content.querySelector("#revoke-other-sessions").addEventListener("click", () => guardedSensitive("正在退出其他设备…", "session", async () => { if (!confirm("确定让其他所有设备退出登录吗？")) return; const result = await api.revokeOtherSessions(); toast(`已退出 ${result.revoked || 0} 个其他设备。`, "success"); await renderCurrent(document); }));
  content.querySelector("#behavior-toggle").addEventListener("click", () => updateConsents(!consent.behaviorAnalytics, consent.recommendationPersonalization));
  content.querySelector("#recommend-toggle").addEventListener("click", () => updateConsents(consent.behaviorAnalytics, !consent.recommendationPersonalization));
  content.querySelector("#export-weread").addEventListener("click", () => runSensitiveAction("weread-export"));
  content.querySelector("#export-account").addEventListener("click", () => runSensitiveAction("export"));
  content.querySelector("#delete-account").addEventListener("click", () => runSensitiveAction("delete"));
}

function passwordDialog(hasPassword) {
  const host = modal(`<p class="eyebrow">账户安全</p><h2>${hasPassword ? "修改邮箱和密码" : "为密钥账户设置邮箱和密码"}</h2><p>${hasPassword ? "修改成功后，其他设备会自动退出。" : "设置后仍可继续用微信读书密钥登录，也可在任何设备使用邮箱密码。"}</p><form id="password-config-form"><label for="password-config-email">邮箱</label><input id="password-config-email" name="email" type="email" autocomplete="email" required value="${escapeAttr(state.account.email || "")}" placeholder="name@example.com">${hasPassword ? `<label for="password-config-current">当前密码</label><input id="password-config-current" name="currentPassword" type="password" autocomplete="current-password" required>` : ""}<label for="password-config-new">新密码</label><input id="password-config-new" name="newPassword" type="password" autocomplete="new-password" minlength="12" required placeholder="至少 12 位，包含字母和数字"><label for="password-config-confirm">再次输入新密码</label><input id="password-config-confirm" name="confirmPassword" type="password" autocomplete="new-password" minlength="12" required><button class="button primary full" type="submit">${hasPassword ? "保存并退出其他设备" : "设置邮箱密码"}</button></form>`);
  host.querySelector("form").addEventListener("submit", async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    if (data.newPassword !== data.confirmPassword) { toast("两次输入的新密码不一致。", "warning"); return; }
    await guardedSensitive("正在安全更新密码…", "password", async () => {
      const result = await api.configurePassword({ email: data.email, currentPassword: data.currentPassword || "", newPassword: data.newPassword });
      state.account = result.account;
      host.remove();
      toast(hasPassword ? "密码已更新，其他设备已退出。" : "邮箱密码已设置。", "success");
      await renderCurrent(document);
    });
  });
}

async function guardedSensitive(label, actionName, callback) {
  await action(label, async () => {
    try { return await callback(); }
    catch (error) {
      if (error?.code !== "RECENT_AUTH_REQUIRED") throw error;
      openRecentAuthDialog(actionName, callback);
      return undefined;
    }
  });
}
async function updateConsents(behaviorAnalytics, recommendationPersonalization) { await action("正在更新隐私选择…", async () => { const result = await api.updateConsent({ behaviorAnalytics, recommendationPersonalization }); state.account.consent = result.consent; toast("隐私选择已更新。", "success"); await renderCurrent(document); }); }
function accountSecurityDialog(mode) { const host = modal(`<p class="eyebrow">账户安全</p><h2>${mode === "rotate" ? "轮换微信读书密钥" : "绑定微信读书密钥"}</h2><p>输入新密钥后系统会验证并替换加密凭据，账户 ID 和历史笔记不会改变。</p><form id="security-key-form"><label for="security-key">新密钥</label><input id="security-key" name="key" type="password" autocomplete="off" required placeholder="wrk-…"><button class="button primary full" type="submit">验证并保存</button></form>`); host.querySelector("form").addEventListener("submit", async event => { event.preventDefault(); await action("正在验证新密钥…", async () => { const key = new FormData(event.currentTarget).get("key"); const result = mode === "rotate" ? await api.rotateWeRead(key) : await api.bindWeRead(key); state.account = result.account; host.remove(); toast("微信读书密钥已安全更新。", "success"); await renderCurrent(document); }); }); }
async function runSensitiveAction(actionName) {
  await action(actionName === "delete" ? "正在确认账户状态…" : "正在准备导出…", async () => {
    try { await completeSensitiveAction(actionName); }
    catch (error) {
      if (error?.code !== "RECENT_AUTH_REQUIRED") throw error;
      openRecentAuthDialog(actionName, () => completeSensitiveAction(actionName));
    }
  });
}
async function completeSensitiveAction(actionName) {
  if (actionName === "weread-export") {
    const data = await api.exportWeRead();
    downloadJson(data, `weread-port-wechat-reading-${new Date().toISOString().slice(0, 10)}.json`);
    toast("微信读书已同步数据已下载。", "success");
    return;
  }
  if (actionName === "export") {
    const data = await api.exportAccount();
    downloadJson(data, `weread-port-account-${new Date().toISOString().slice(0, 10)}.json`);
    toast("账户数据已导出。", "success");
    return;
  }
  if (!confirm("此操作不可撤销。确定永久删除账户及所有笔记吗？")) return;
  await api.deleteAccount();
  state.account = null;
  await renderCurrent(document);
}
function openRecentAuthDialog(actionName, continuation = () => completeSensitiveAction(actionName)) {
  const credentials = state.account?.credentials || [];
  const hasPassword = credentials.some(item => item.kind === "password");
  const hasWeRead = credentials.some(item => item.provider === "weread");
  const oauthProviders = credentials.filter(item => item.kind === "oauth").map(item => item.provider);
  const forms = [
    hasPassword ? `<form class="reauth-option" data-method="password"><h3>用账户密码验证</h3><label for="reauth-password">账户密码</label><input id="reauth-password" name="secret" type="password" autocomplete="current-password" required><button class="button primary full" type="submit">验证并继续</button></form>` : "",
    hasWeRead ? `<form class="reauth-option" data-method="weread"><h3>用微信读书密钥验证</h3><label for="reauth-weread">微信读书密钥</label><input id="reauth-weread" name="secret" type="password" autocomplete="off" required placeholder="wrk-…"><button class="button primary full" type="submit">验证并继续</button></form>` : "",
    oauthProviders.length ? `<div class="reauth-option"><h3>用已绑定平台验证</h3><p>跳转官方授权页确认身份后自动返回，不会按邮箱合并账户。</p><div class="button-row">${oauthProviders.map(provider => `<button class="button secondary oauth-reauth" data-provider="${provider}" type="button">用 ${providerLabel(provider)} 验证</button>`).join("")}</div></div>` : "",
  ].join("");
  const title = ({ delete: "删除前再次确认身份", export: "导出前再次确认身份", "weread-export": "下载微信读书数据前再次确认身份", password: "设置密码前再次确认身份", session: "管理设备前再次确认身份" })[actionName] || "再次确认身份";
  const host = modal(`<p class="eyebrow">账户安全</p><h2>${title}</h2><p>选择你已经绑定的任一登录方式。验证只更新当前会话，不会创建或合并账户。</p><div class="reauth-grid">${forms}</div>`);
  host.querySelectorAll("form[data-method]").forEach(form => form.addEventListener("submit", async event => {
    event.preventDefault();
    await action("正在验证身份…", async () => {
      const secret = new FormData(event.currentTarget).get("secret");
      if (event.currentTarget.dataset.method === "password") await api.reauthPassword(secret);
      else await api.reauthWeRead(secret);
      host.remove();
      await continuation();
    });
  }));
  host.querySelectorAll(".oauth-reauth").forEach(button => button.addEventListener("click", () => api.oauth(button.dataset.provider, "reauth")));
}

function emptyState(title, detail, actionLabel, view) { return `<section class="empty-state"><div aria-hidden="true">□</div><h2>${title}</h2><p>${detail}</p><button class="button primary" data-go="${view}" type="button">${actionLabel}</button></section>`; }
function emptyStateMarkup(title, detail, actionLabel, view) { return `<section class="empty-state"><div aria-hidden="true">□</div><h2>${title}</h2><p>${detail}</p><button class="button primary" data-go="${view}" type="button">${actionLabel}</button></section>`; }
function modal(inner) { const host = document.createElement("div"); host.className = "modal-backdrop"; host.innerHTML = `<section class="modal compact" role="dialog" aria-modal="true"><button class="modal-close" type="button" aria-label="关闭">×</button>${inner}</section>`; document.body.append(host); host.querySelector(".modal-close").addEventListener("click", () => host.remove()); host.addEventListener("click", event => { if (event.target === host) host.remove(); }); host.querySelector("input")?.focus(); return host; }

async function action(label, callback) {
  if (state.busy) return undefined;
  setBusy(true, label || "正在处理…");
  try { return await callback(); }
  catch (error) {
    toast(error?.message || "操作失败，请重试。", "error");
    console.error(JSON.stringify({ event: "ui_action_failed", code: String(error?.code || "REQUEST_FAILED") }));
    return undefined;
  } finally { setBusy(false); }
}
function setBusy(value, label = "正在处理…") { state.busy = value; const node = document.querySelector("#global-progress"); if (!node) return; node.classList.toggle("hidden", !value); node.querySelector("span:last-child").textContent = label; document.querySelectorAll("button").forEach(button => { if (button.closest("#global-progress")) return; button.disabled = value; }); }
function toast(message, type = "info") { const node = document.querySelector("#toast"); if (!node) return; node.textContent = message; node.className = `toast ${type}`; clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => node.classList.add("hidden"), 5000); }
function providerLabel(provider) { return ({ google: "Google", github: "GitHub", notion: "Notion", obsidian: "Obsidian", weread: "微信读书", email: "邮箱密码" })[provider] || provider; }
function providerMark(provider) { return ({ google: "G", github: "GH", notion: "N", obsidian: "O", weread: "微", email: "@" })[provider] || "•"; }
function sourceName(source) { return ({ weread: "微信读书", notion: "Notion", obsidian: "Obsidian", github: "GitHub", google: "Google Drive", manual: "手动笔记", "weread-official": "微信读书官方", "account-pattern": "账户画像", onboarding: "新手建议" })[source] || source || "未知来源"; }
function initials(value) { return String(value || "阅").trim().slice(0, 2).toUpperCase(); }
function formatDate(value) { const timestamp = Number(value || 0) < 1e12 ? Number(value || 0) * 1000 : Number(value || 0); if (!timestamp) return "未知时间"; return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(timestamp); }
function formatDateTime(value) { const timestamp = Number(value || 0) < 1e12 ? Number(value || 0) * 1000 : Number(value || 0); if (!timestamp) return "未知时间"; return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(timestamp); }
function noteTimeLabel(note) { return note.eventAt ? `真实事件时间 ${formatDate(note.eventAt)}` : `更新时间 ${formatDate(note.updatedAt)}`; }
function numberFormat(value) { return new Intl.NumberFormat("zh-CN", { notation: Number(value) > 9999 ? "compact" : "standard" }).format(Number(value || 0)); }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, "&#96;"); }
function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function reduceMotion() { return matchMedia("(prefers-reduced-motion: reduce)").matches; }
function downloadJson(data, name) { const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
