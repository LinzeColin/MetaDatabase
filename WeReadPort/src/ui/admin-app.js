import { AccountApi } from "./account-api.js";

const api = new AccountApi();
const root = document.querySelector("#admin-app");
const DIRECT_LIST_LIMIT = 5_000;
const state = {
  account: null,
  view: "overview",
  overview: null,
  mode: "weread",
  busy: false,
  results: {},
  failures: {},
};

void bootstrap();

async function bootstrap() {
  const session = await api.session().catch(() => null);
  state.account = session?.account || null;
  if (!state.account) return handoffOrLogin();
  await loadOverview();
}

function handoffOrLogin() {
  const current = new URL(window.location.href);
  if (current.searchParams.get("handoff") === "1") return renderLogin();
  if (!current.hostname.toLowerCase().startsWith("admin.")) return renderLogin();
  const publicHandoff = new URL(current.href);
  publicHandoff.hostname = current.hostname.slice("admin.".length);
  publicHandoff.pathname = "/api/platform/v1/session/handoff";
  publicHandoff.search = "";
  publicHandoff.hash = "";
  window.location.replace(publicHandoff.toString());
}

async function loadOverview() {
  try {
    state.overview = await api.adminOverview();
    const names = ["users", "notes", "prompts", "skills", "security", "audit", "operations"];
    const settled = await Promise.allSettled([
      api.adminAccounts({ limit: DIRECT_LIST_LIMIT }),
      api.adminNotes({ limit: DIRECT_LIST_LIMIT }),
      api.adminPrompts({ limit: DIRECT_LIST_LIMIT }),
      api.adminBookSkills({ limit: DIRECT_LIST_LIMIT }),
      api.adminSecurity({ limit: DIRECT_LIST_LIMIT }),
      api.adminAudit({ limit: DIRECT_LIST_LIMIT }),
      api.readiness(),
    ]);
    state.results = {};
    state.failures = {};
    settled.forEach((item, index) => {
      if (item.status === "fulfilled") state.results[names[index]] = item.value;
      else state.failures[names[index]] = item.reason;
    });
    renderAdmin();
  } catch (error) {
    if (error?.code === "AUTH_REQUIRED") {
      state.account = null;
      return handoffOrLogin();
    }
    renderAccessBlocked(error);
  }
}

function renderLogin() {
  const passwordMode = state.mode === "password";
  const fields = passwordMode
    ? '<label for="admin-email">邮箱<input id="admin-email" name="email" type="email" autocomplete="email" required></label><label for="admin-password">密码<input id="admin-password" name="password" type="password" autocomplete="current-password" required></label>'
    : '<label for="admin-weread-key">微信读书密钥<input id="admin-weread-key" name="key" type="password" autocomplete="off" required placeholder="wrk-…"></label>';
  root.innerHTML = [
    '<main class="admin-login"><section class="admin-login-card" aria-labelledby="admin-login-title">',
    '<div class="admin-brand"><span class="admin-brand-mark" aria-hidden="true">阅</span><div><strong>阅迁 Admin</strong><small>专用管理控制台</small></div></div>',
    '<p class="eyebrow">仅限已配置管理员</p><h1 id="admin-login-title">登录后直接查看管理数据</h1>',
    '<p>主站已经登录时会自动带入当前会话；无需再次输入密钥。服务端仍只接受专用管理域和不可变账户白名单。</p>',
    '<div class="admin-login-switch" role="tablist">',
    '<button data-login-mode="password" class="' + (passwordMode ? "active" : "") + '" type="button" role="tab" aria-selected="' + passwordMode + '">邮箱和密码</button>',
    '<button data-login-mode="weread" class="' + (!passwordMode ? "active" : "") + '" type="button" role="tab" aria-selected="' + (!passwordMode) + '">微信读书密钥</button></div>',
    '<form id="admin-login-form">' + fields + '<button class="button primary" type="submit">登录并直接展示数据</button></form>',
    '<p class="admin-note">当前测试管理员账户使用微信读书密钥登录；系统不会显示或修改密钥、令牌、会话 Cookie。</p>',
    '</section></main>',
  ].join("");
  root.querySelectorAll("[data-login-mode]").forEach(button => button.addEventListener("click", () => {
    state.mode = button.dataset.loginMode;
    renderLogin();
  }));
  root.querySelector("#admin-login-form").addEventListener("submit", async event => {
    event.preventDefault();
    await runBusy(async () => {
      const input = Object.fromEntries(new FormData(event.currentTarget));
      const result = state.mode === "password" ? await api.loginPassword(input) : await api.loginWeRead(input);
      state.account = result.account;
      await loadOverview();
    });
  });
}

function renderAccessBlocked(error) {
  const message = error?.code === "ADMIN_NOT_CONFIGURED"
    ? "管理员安全配置尚未完成，服务已拒绝展示数据。"
    : "当前账户未被配置为管理员，服务端没有返回任何管理数据。";
  root.innerHTML = '<main class="admin-login"><section class="admin-login-card"><p class="eyebrow">访问受限</p><h1>未授予管理权限</h1><p>'
    + escapeHtml(message)
    + '</p><p class="admin-note">普通用户不会因为知道此网址而获得访问权。</p><button id="admin-logout" class="button secondary" type="button">退出当前账户</button></section></main>';
  root.querySelector("#admin-logout").addEventListener("click", () => runBusy(async () => {
    await api.logout();
    state.account = null;
    state.overview = null;
    state.results = {};
    renderLogin();
  }));
}

function renderAdmin() {
  const counts = state.overview?.counts || {};
  root.innerHTML = [
    '<div class="admin-shell"><header class="admin-topbar">',
    '<a class="admin-brand" href="/" aria-label="阅迁 Admin 首页"><span class="admin-brand-mark" aria-hidden="true">阅</span><div><strong>阅迁 Admin</strong><small>专用管理域 · 直接访问</small></div></a>',
    '<div class="admin-session"><span class="admin-status">管理员已登录</span><code>' + escapeHtml(state.account?.id || "") + '</code><button class="button ghost" id="admin-refresh" type="button">刷新数据</button><button class="button ghost" id="admin-logout" type="button">退出</button></div>',
    '</header><main class="admin-layout"><aside class="admin-sidebar"><nav aria-label="管理功能">',
    adminNav("overview", "总览"),
    adminNav("users", "用户资料"),
    adminNav("notes", "笔记"),
    adminNav("prompts", "提示词与背景"),
    adminNav("skills", "Book-to-Skill"),
    adminNav("security", "登录与安全"),
    adminNav("audit", "平台操作记录"),
    adminNav("operations", "开发与运维"),
    '</nav></aside><section class="admin-panel" id="admin-content">' + renderAdminView(counts) + '</section></main></div>',
  ].join("");
  root.querySelectorAll("[data-admin-view]").forEach(button => button.addEventListener("click", () => {
    state.view = button.dataset.adminView;
    renderAdmin();
  }));
  root.querySelector("#admin-refresh").addEventListener("click", () => runBusy(loadOverview));
  root.querySelector("#admin-logout").addEventListener("click", () => runBusy(async () => {
    await api.logout();
    state.account = null;
    state.overview = null;
    state.results = {};
    renderLogin();
  }));
  bindAdminView(root.querySelector("#admin-content"));
}

function adminNav(view, label) {
  return '<button class="admin-nav-button ' + (state.view === view ? "active" : "") + '" data-admin-view="' + view + '" type="button">' + label + '</button>';
}

function renderAdminView(counts) {
  if (state.view === "users") return directView("用户资料", "账户资料已在登录后自动加载，无需填写用途或再次验证。", renderUsers(state.results.users), state.failures.users);
  if (state.view === "notes") return directView("笔记", "笔记索引已自动加载；点击任意一条即可展开正文，无需再次登录。", renderNotes(state.results.notes), state.failures.notes);
  if (state.view === "prompts") return directView("提示词与背景", "用户保存的 AI 平台、提问风格、个人补充信息和自定义提示词已直接展示。", renderPrompts(state.results.prompts), state.failures.prompts);
  if (state.view === "skills") return directView("Book-to-Skill", "已保存的单书 Skill 索引已自动加载；点击后可直接查看其 Markdown 正文。", renderBookSkills(state.results.skills), state.failures.skills);
  if (state.view === "security") return directView("登录与安全", "展示必要的登录、会话、凭据生命周期与已同意行为元数据；不会显示密钥、令牌、Cookie、完整 IP 或完整 User-Agent。", renderSecurity(state.results.security), state.failures.security);
  if (state.view === "audit") return directView("平台操作记录", "系统自动保留管理操作记录；展示不再要求填写用途。", renderAudit(state.results.audit), state.failures.audit);
  if (state.view === "operations") return directView("开发与运维", "运行状态已自动加载，不显示环境变量、密钥、令牌、IP 或对象存储路径。", renderOperations(), state.failures.operations);
  return [
    '<p class="eyebrow">管理总览</p><h1>管理员控制台</h1>',
    '<p>进入专用管理域后，账户资料、笔记、提示词、平台操作记录和运行状态会直接加载。</p>',
    '<div class="admin-note">用户侧没有管理员导航或管理数据接口；此页面也不会显示密钥、令牌、会话 Cookie 或对象存储路径。</div>',
    '<section class="admin-metric-grid">',
    '<article><span>账户</span><strong>' + formatCount(counts.accounts) + '</strong></article>',
    '<article><span>笔记索引</span><strong>' + formatCount(counts.notes) + '</strong></article>',
    '<article><span>Book-to-Skill</span><strong>' + formatCount(counts.bookSkills) + '</strong></article>',
    '<article><span>AI 偏好</span><strong>' + formatCount(counts.aiPreferences) + '</strong></article>',
    '<article><span>待处理导入</span><strong>' + formatCount(counts.pendingImports) + '</strong></article>',
    '</section>',
  ].join("");
}

function directView(title, description, content, failure) {
  const body = failure ? renderLoadFailure(failure) : content || '<div class="admin-empty">当前没有可展示的数据。</div>';
  return '<p class="eyebrow">直接展示</p><h1>' + escapeHtml(title) + '</h1><p>' + escapeHtml(description) + '</p>' + body;
}

function renderLoadFailure(error) {
  return '<div class="admin-empty">此分组暂时未能加载：' + escapeHtml(error?.message || "请求失败，请刷新后重试。") + '</div>';
}

function bindAdminView(content) {
  content.querySelectorAll("[data-admin-note]").forEach(button => button.addEventListener("click", () => {
    void runBusy(async () => {
      const result = await api.adminNote(button.dataset.adminNote);
      showNoteModal(result.note);
    });
  }));
  content.querySelectorAll("[data-admin-book-skill]").forEach(button => button.addEventListener("click", () => {
    void runBusy(async () => {
      const result = await api.adminBookSkill(button.dataset.adminBookSkill);
      showBookSkillModal(result);
    });
  }));
}

function renderUsers(result) {
  const rows = result?.accounts || [];
  if (!rows.length) return "";
  return '<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>账户</th><th>邮箱</th><th>笔记</th><th>AI 偏好</th><th>更新时间</th></tr></thead><tbody>'
    + rows.map(item => '<tr><td><strong>' + escapeHtml(item.displayName) + '</strong><br><code>' + escapeHtml(item.id) + '</code></td><td>' + escapeHtml(item.email || "—") + '</td><td>' + formatCount(item.noteCount) + '</td><td>' + (item.hasAiPreferences ? "已保存" : "未保存") + '</td><td>' + escapeHtml(formatDateTime(item.updatedAt)) + '</td></tr>').join("")
    + '</tbody></table></div>';
}

function renderNotes(result) {
  const rows = result?.notes || [];
  if (!rows.length) return "";
  return '<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>账户</th><th>笔记</th><th>书籍 / 作者</th><th>时间</th><th>正文</th></tr></thead><tbody>'
    + rows.map(item => '<tr><td><strong>' + escapeHtml(item.accountDisplayName) + '</strong><br><code>' + escapeHtml(item.accountId) + '</code></td><td>' + escapeHtml(item.title) + '</td><td>' + escapeHtml([item.bookTitle ? "《" + item.bookTitle + "》" : "", item.author || ""].filter(Boolean).join(" · ") || "—") + '</td><td>' + escapeHtml(formatDateTime(item.eventAt || item.updatedAt)) + '</td><td><button class="button ghost" data-admin-note="' + escapeAttr(item.id) + '" type="button">展开正文</button></td></tr>').join("")
    + '</tbody></table></div>';
}

function renderPrompts(result) {
  const rows = result?.preferences || [];
  if (!rows.length) return "";
  return '<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>账户</th><th>平台 / 风格</th><th>个人补充信息</th><th>自定义提示词</th><th>更新时间</th></tr></thead><tbody>'
    + rows.map(item => '<tr><td><strong>' + escapeHtml(item.accountDisplayName) + '</strong><br><code>' + escapeHtml(item.accountId) + '</code></td><td>' + escapeHtml(item.preferences.providerId + " / " + item.preferences.styleId) + '</td><td>' + escapeHtml(item.preferences.personalContext || "—") + '</td><td>' + escapeHtml(item.preferences.customPrompt || "—") + '</td><td>' + escapeHtml(formatDateTime(item.updatedAt)) + '</td></tr>').join("")
    + '</tbody></table></div>';
}

function renderBookSkills(result) {
  const rows = result?.bookSkills || [];
  if (!rows.length) return "";
  return '<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>账户</th><th>书籍 / 作者</th><th>来源笔记</th><th>版本</th><th>更新时间</th><th>正文</th></tr></thead><tbody>'
    + rows.map(item => '<tr><td><strong>' + escapeHtml(item.accountDisplayName) + '</strong><br><code>' + escapeHtml(item.accountId) + '</code></td><td>' + escapeHtml([item.bookTitle ? "《" + item.bookTitle + "》" : "", item.author || ""].filter(Boolean).join(" · ") || "—") + '</td><td>' + formatCount(item.noteCount) + '</td><td>v' + escapeHtml(String(item.version || 1)) + '</td><td>' + escapeHtml(formatDateTime(item.updatedAt)) + '</td><td><button class="button ghost" data-admin-book-skill="' + escapeAttr(item.id) + '" type="button">查看 Markdown</button></td></tr>').join("")
    + '</tbody></table></div>';
}

function renderSecurity(result) {
  const securityEvents = result?.securityEvents || [];
  const sessions = result?.sessions || [];
  const credentials = result?.credentials || [];
  const behaviorEvents = result?.behaviorEvents || [];
  if (!securityEvents.length && !sessions.length && !credentials.length && !behaviorEvents.length) return "";
  return '<div class="admin-security-groups">'
    + securityTable("登录与安全事件", ["时间", "账户", "事件", "方式", "结果", "会话", "设备指纹", "网络指纹"], securityEvents.map(item => ['<td>' + escapeHtml(formatDateTime(item.createdAt)) + '</td>', '<td><strong>' + escapeHtml(item.accountDisplayName || "—") + '</strong><br><code>' + escapeHtml(item.accountId || "—") + '</code></td>', '<td>' + escapeHtml(item.eventType) + '</td>', '<td>' + escapeHtml(item.method) + '</td>', '<td>' + escapeHtml(item.outcome) + '</td>', '<td><code>' + escapeHtml(item.sessionId || "—") + '</code></td>', '<td><code>' + escapeHtml(item.userAgentFingerprint || "—") + '</code></td>', '<td><code>' + escapeHtml(item.ipFingerprint || "—") + '</code></td>']))
    + securityTable("当前会话元数据", ["账户", "创建", "最近活动", "到期", "设备指纹", "网络指纹"], sessions.map(item => ['<td><strong>' + escapeHtml(item.accountDisplayName || "—") + '</strong><br><code>' + escapeHtml(item.accountId || "—") + '</code></td>', '<td>' + escapeHtml(formatDateTime(item.createdAt)) + '</td>', '<td>' + escapeHtml(formatDateTime(item.lastSeenAt)) + '</td>', '<td>' + escapeHtml(formatDateTime(item.expiresAt)) + '</td>', '<td><code>' + escapeHtml(item.userAgentFingerprint || "—") + '</code></td>', '<td><code>' + escapeHtml(item.ipFingerprint || "—") + '</code></td>']))
    + securityTable("凭据生命周期", ["账户", "类型", "平台", "安全标签", "创建", "更新"], credentials.map(item => ['<td><strong>' + escapeHtml(item.accountDisplayName || "—") + '</strong><br><code>' + escapeHtml(item.accountId || "—") + '</code></td>', '<td>' + escapeHtml(item.kind) + '</td>', '<td>' + escapeHtml(item.provider) + '</td>', '<td>' + escapeHtml(item.label) + '</td>', '<td>' + escapeHtml(formatDateTime(item.createdAt)) + '</td>', '<td>' + escapeHtml(formatDateTime(item.updatedAt)) + '</td>']))
    + securityTable("已同意行为事件", ["时间", "账户", "事件", "脱敏元数据"], behaviorEvents.map(item => ['<td>' + escapeHtml(formatDateTime(item.occurredAt)) + '</td>', '<td><strong>' + escapeHtml(item.accountDisplayName || "—") + '</strong><br><code>' + escapeHtml(item.accountId || "—") + '</code></td>', '<td>' + escapeHtml(item.eventType) + '</td>', '<td><code>' + escapeHtml(JSON.stringify(item.value || {})) + '</code></td>']))
    + '</div>';
}

function securityTable(title, headings, rows) {
  if (!rows.length) return '<section class="admin-security-group"><h2>' + escapeHtml(title) + '</h2><div class="admin-empty">当前没有可展示的数据。</div></section>';
  return '<section class="admin-security-group"><h2>' + escapeHtml(title) + '</h2><div class="admin-table-wrap"><table class="admin-table"><thead><tr>' + headings.map(label => '<th>' + escapeHtml(label) + '</th>').join("") + '</tr></thead><tbody>' + rows.map(cells => '<tr>' + cells.join("") + '</tr>').join("") + '</tbody></table></div></section>';
}

function renderAudit(result) {
  const rows = result?.events || [];
  if (!rows.length) return "";
  return '<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>时间</th><th>操作</th><th>管理员</th><th>目标</th><th>系统标记</th></tr></thead><tbody>'
    + rows.map(item => '<tr><td>' + escapeHtml(formatDateTime(item.createdAt)) + '</td><td>' + escapeHtml(item.action) + '</td><td><code>' + escapeHtml(item.actorAccountId) + '</code></td><td><code>' + escapeHtml(item.targetNoteId || item.targetAccountId || "—") + '</code></td><td>' + escapeHtml(item.reason) + '</td></tr>').join("")
    + '</tbody></table></div>';
}

function renderOperations() {
  const readiness = state.results.operations;
  if (!readiness) return "";
  return '<pre>' + escapeHtml(JSON.stringify(readiness, null, 2)) + '</pre>';
}

function showNoteModal(note) {
  const host = document.createElement("div");
  host.className = "admin-modal-backdrop";
  host.innerHTML = '<section class="admin-modal" role="dialog" aria-modal="true" aria-labelledby="admin-note-title"><p class="eyebrow">笔记正文</p><h2 id="admin-note-title">'
    + escapeHtml(note.title)
    + '</h2><p>'
    + escapeHtml([note.accountDisplayName, note.accountEmail, note.bookTitle ? "《" + note.bookTitle + "》" : "", note.author].filter(Boolean).join(" · "))
    + '</p><pre>'
    + escapeHtml(note.content || "")
    + '</pre><div class="modal-actions"><button class="button primary" type="button">关闭</button></div></section>';
  document.body.append(host);
  host.querySelector("button").addEventListener("click", () => host.remove());
  host.addEventListener("click", event => {
    if (event.target === host) host.remove();
  });
}

function showBookSkillModal(result) {
  const skill = result?.bookSkill || {};
  const host = document.createElement("div");
  host.className = "admin-modal-backdrop";
  host.innerHTML = '<section class="admin-modal" role="dialog" aria-modal="true" aria-labelledby="admin-book-skill-title"><p class="eyebrow">Book-to-Skill Markdown</p><h2 id="admin-book-skill-title">'
    + escapeHtml(skill.bookTitle ? "《" + skill.bookTitle + "》" : "Book-to-Skill")
    + '</h2><p>'
    + escapeHtml([skill.accountDisplayName, skill.accountEmail, skill.author, skill.noteCount ? skill.noteCount + " 条笔记" : ""].filter(Boolean).join(" · "))
    + '</p><pre>'
    + escapeHtml(result?.artifact?.markdown || "")
    + '</pre><div class="modal-actions"><button class="button primary" type="button">关闭</button></div></section>';
  document.body.append(host);
  host.querySelector("button").addEventListener("click", () => host.remove());
  host.addEventListener("click", event => {
    if (event.target === host) host.remove();
  });
}

function openNotice(message) {
  const host = document.createElement("div");
  host.className = "admin-modal-backdrop";
  host.innerHTML = '<section class="admin-modal" role="dialog" aria-modal="true"><h2>请求未完成</h2><p>' + escapeHtml(message) + '</p><div class="modal-actions"><button class="button primary" type="button">关闭</button></div></section>';
  document.body.append(host);
  host.querySelector("button").addEventListener("click", () => host.remove());
}

async function runBusy(callback) {
  if (state.busy) return;
  state.busy = true;
  try {
    await callback();
  } catch (error) {
    openNotice(error?.message || "请求失败，请稍后重试。");
  } finally {
    state.busy = false;
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function formatCount(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function formatDateTime(value) {
  const seconds = Number(value || 0);
  if (!seconds) return "—";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(seconds < 1e12 ? seconds * 1000 : seconds);
}
