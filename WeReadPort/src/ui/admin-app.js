import { AccountApi } from "./account-api.js";

const api = new AccountApi();
const root = document.querySelector("#admin-app");
const state = { account: null, view: "overview", overview: null, mode: "password", busy: false, results: {}, lastReason: "" };

void bootstrap();

async function bootstrap() {
  const session = await api.session().catch(() => null);
  state.account = session?.account || null;
  if (!state.account) return renderLogin();
  await loadOverview();
}

async function loadOverview() {
  try {
    state.overview = await api.adminOverview();
    renderAdmin();
  } catch (error) {
    if (error?.code === "AUTH_REQUIRED") { state.account = null; return renderLogin(); }
    renderAccessBlocked(error);
  }
}

function renderLogin() {
  root.innerHTML = `<main class="admin-login"><section class="admin-login-card" aria-labelledby="admin-login-title"><div class="admin-brand"><span class="admin-brand-mark" aria-hidden="true">阅</span><div><strong>阅迁 Admin</strong><small>受限管理控制台</small></div></div><p class="eyebrow">仅限已配置管理员</p><h1 id="admin-login-title">安全登录管理控制台</h1><p>此页面不会授予普通账户权限。登录后仍会由服务端按不可变账户 ID、专用管理域和近期身份验证进行授权。</p><div class="admin-login-switch" role="tablist"><button data-login-mode="password" class="${state.mode === "password" ? "active" : ""}" type="button" role="tab" aria-selected="${state.mode === "password"}">邮箱和密码</button><button data-login-mode="weread" class="${state.mode === "weread" ? "active" : ""}" type="button" role="tab" aria-selected="${state.mode === "weread"}">微信读书密钥</button></div><form id="admin-login-form">${state.mode === "password" ? `<label for="admin-email">邮箱<input id="admin-email" name="email" type="email" autocomplete="email" required></label><label for="admin-password">密码<input id="admin-password" name="password" type="password" autocomplete="current-password" required></label>` : `<label for="admin-weread-key">微信读书密钥<input id="admin-weread-key" name="key" type="password" autocomplete="off" required placeholder="wrk-…"></label>`}<button class="button primary" type="submit">登录并验证权限</button></form><p class="admin-note">访问日志只记录管理员账户 ID、操作类型、目标对象 ID 和用途说明；不记录密钥、令牌或笔记正文。</p></section></main>`;
  root.querySelectorAll("[data-login-mode]").forEach(button => button.addEventListener("click", () => { state.mode = button.dataset.loginMode; renderLogin(); }));
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
  const message = error?.code === "ADMIN_NOT_CONFIGURED" ? "管理员安全配置尚未完成，服务已拒绝展示数据。" : "当前账户未被配置为管理员，服务端没有返回任何管理数据。";
  root.innerHTML = `<main class="admin-login"><section class="admin-login-card"><p class="eyebrow">访问受限</p><h1>未授予管理权限</h1><p>${escapeHtml(message)}</p><p class="admin-note">请使用已配置的管理员账户登录；普通用户不会因为知道此网址而获得访问权。</p><button id="admin-logout" class="button secondary" type="button">退出当前账户</button></section></main>`;
  root.querySelector("#admin-logout").addEventListener("click", () => runBusy(async () => { await api.logout(); state.account = null; state.overview = null; renderLogin(); }));
}

function renderAdmin() {
  const counts = state.overview?.counts || {};
  root.innerHTML = `<div class="admin-shell"><header class="admin-topbar"><a class="admin-brand" href="/" aria-label="阅迁 Admin 首页"><span class="admin-brand-mark" aria-hidden="true">阅</span><div><strong>阅迁 Admin</strong><small>专用管理域 · 服务端授权</small></div></a><div class="admin-session"><span class="admin-status">管理员已验证</span><code>${escapeHtml(state.account?.id || "")}</code><button class="button ghost" id="admin-logout" type="button">退出</button></div></header><main class="admin-layout"><aside class="admin-sidebar"><nav aria-label="管理功能">${adminNav("overview", "总览")}${adminNav("users", "用户资料")}${adminNav("notes", "笔记")}${adminNav("prompts", "提示词与背景")}${adminNav("audit", "审计日志")}${adminNav("operations", "开发与运维")}</nav></aside><section class="admin-panel" id="admin-content">${renderAdminView(counts)}</section></main></div>`;
  root.querySelectorAll("[data-admin-view]").forEach(button => button.addEventListener("click", () => { state.view = button.dataset.adminView; renderAdmin(); }));
  root.querySelector("#admin-logout").addEventListener("click", () => runBusy(async () => { await api.logout(); state.account = null; state.overview = null; state.results = {}; renderLogin(); }));
  bindAdminView(root.querySelector("#admin-content"));
}

function adminNav(view, label) { return `<button class="admin-nav-button ${state.view === view ? "active" : ""}" data-admin-view="${view}" type="button">${label}</button>`; }
function renderAdminView(counts) {
  if (state.view === "users") return queryView("用户资料", "读取账户资料前，请填写明确用途。不会返回密码摘要、密钥、令牌或会话 Cookie。", "admin-users-form", "搜索账户 ID、昵称或邮箱", renderUsers(state.results.users));
  if (state.view === "notes") return queryView("笔记", "先读取索引；点击单条正文前会再次记录用途和目标笔记。", "admin-notes-form", "可选：只看某个账户 ID", renderNotes(state.results.notes));
  if (state.view === "prompts") return queryView("提示词与背景", "读取的是用户主动保存的 AI 偏好；内容加密保存，管理员读取会进入审计日志。", "admin-prompts-form", "可选：此处无需搜索", renderPrompts(state.results.prompts), true);
  if (state.view === "audit") return queryView("审计日志", "审计日志不包含笔记正文、密钥或令牌。", "admin-audit-form", "可选：此处无需搜索", renderAudit(state.results.audit), true);
  if (state.view === "operations") return renderOperations();
  return `<p class="eyebrow">受限总览</p><h1>管理员控制台</h1><p>数据展示受专用域、服务端账户白名单、近期身份验证、用途说明和独立审计共同约束。</p><div class="admin-note">用户侧没有管理员导航或管理数据接口；此页面也不会显示任何密钥、令牌、会话 Cookie 或对象存储路径。</div><section class="admin-metric-grid"><article><span>账户</span><strong>${formatCount(counts.accounts)}</strong></article><article><span>笔记索引</span><strong>${formatCount(counts.notes)}</strong></article><article><span>AI 偏好</span><strong>${formatCount(counts.aiPreferences)}</strong></article><article><span>待处理导入</span><strong>${formatCount(counts.pendingImports)}</strong></article></section>`;
}
function queryView(title, description, formId, placeholder, result, compact = false) { return `<p class="eyebrow">受限读取</p><h1>${title}</h1><p>${description}</p><form class="admin-query-form ${compact ? "compact" : ""}" id="${formId}"><label>查看用途<input name="reason" minlength="4" required placeholder="例如：处理用户工单 #1234"></label><p class="admin-note">用途说明不要填写笔记正文、密钥、令牌或其他敏感内容。</p>${compact ? "" : `<label>${title === "用户资料" ? "筛选" : "账户 ID"}<input name="query" placeholder="${escapeAttr(placeholder)}"></label>`}<button class="button primary" type="submit">读取并审计</button></form>${result || `<div class="admin-empty">填写用途后读取受限数据。</div>`}`; }

function bindAdminView(content) {
  content.querySelector("#admin-users-form")?.addEventListener("submit", event => { event.preventDefault(); const form = Object.fromEntries(new FormData(event.currentTarget)); loadRestricted("users", form.reason, () => api.adminAccounts({ reason: form.reason, query: form.query })); });
  content.querySelector("#admin-notes-form")?.addEventListener("submit", event => { event.preventDefault(); const form = Object.fromEntries(new FormData(event.currentTarget)); loadRestricted("notes", form.reason, () => api.adminNotes({ reason: form.reason, accountId: form.query })); });
  content.querySelector("#admin-prompts-form")?.addEventListener("submit", event => { event.preventDefault(); const form = Object.fromEntries(new FormData(event.currentTarget)); loadRestricted("prompts", form.reason, () => api.adminPrompts({ reason: form.reason })); });
  content.querySelector("#admin-audit-form")?.addEventListener("submit", event => { event.preventDefault(); const form = Object.fromEntries(new FormData(event.currentTarget)); loadRestricted("audit", form.reason, () => api.adminAudit({ reason: form.reason })); });
  content.querySelectorAll("[data-admin-note]").forEach(button => button.addEventListener("click", () => { const reason = state.lastReason; if (!reason) return openNotice("请先用用途说明读取笔记索引。"); loadRestricted("note", reason, () => api.adminNote(button.dataset.adminNote, reason), { modal: true }); }));
  content.querySelector("#admin-refresh-ops")?.addEventListener("click", () => refreshOperations());
}

async function loadRestricted(kind, reason, callback, { modal = false } = {}) {
  state.lastReason = String(reason || "");
  await runBusy(async () => {
    const result = await callback();
    if (modal) return showNoteModal(result.note);
    state.results[kind] = result;
    renderAdmin();
  });
}

function renderUsers(result) { const rows = result?.accounts || []; if (!rows.length) return ""; return `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>账户</th><th>邮箱</th><th>笔记</th><th>AI 偏好</th><th>更新时间</th></tr></thead><tbody>${rows.map(item => `<tr><td><strong>${escapeHtml(item.displayName)}</strong><br><code>${escapeHtml(item.id)}</code></td><td>${escapeHtml(item.email || "—")}</td><td>${formatCount(item.noteCount)}</td><td>${item.hasAiPreferences ? "已保存" : "未保存"}</td><td>${escapeHtml(formatDateTime(item.updatedAt))}</td></tr>`).join("")}</tbody></table></div>`; }
function renderNotes(result) { const rows = result?.notes || []; if (!rows.length) return ""; return `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>账户</th><th>笔记</th><th>书籍 / 作者</th><th>时间</th><th>正文</th></tr></thead><tbody>${rows.map(item => `<tr><td><strong>${escapeHtml(item.accountDisplayName)}</strong><br><code>${escapeHtml(item.accountId)}</code></td><td>${escapeHtml(item.title)}</td><td>${escapeHtml([item.bookTitle ? `《${item.bookTitle}》` : "", item.author || ""].filter(Boolean).join(" · ") || "—")}</td><td>${escapeHtml(formatDateTime(item.eventAt || item.updatedAt))}</td><td><button class="button ghost" data-admin-note="${escapeAttr(item.id)}" type="button">读取正文</button></td></tr>`).join("")}</tbody></table></div>`; }
function renderPrompts(result) { const rows = result?.preferences || []; if (!rows.length) return ""; return `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>账户</th><th>平台 / 风格</th><th>个人补充信息</th><th>自定义提示词</th><th>更新时间</th></tr></thead><tbody>${rows.map(item => `<tr><td><strong>${escapeHtml(item.accountDisplayName)}</strong><br><code>${escapeHtml(item.accountId)}</code></td><td>${escapeHtml(`${item.preferences.providerId} / ${item.preferences.styleId}`)}</td><td>${escapeHtml(item.preferences.personalContext || "—")}</td><td>${escapeHtml(item.preferences.customPrompt || "—")}</td><td>${escapeHtml(formatDateTime(item.updatedAt))}</td></tr>`).join("")}</tbody></table></div>`; }
function renderAudit(result) { const rows = result?.events || []; if (!rows.length) return ""; return `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>时间</th><th>操作</th><th>管理员</th><th>目标</th><th>用途</th></tr></thead><tbody>${rows.map(item => `<tr><td>${escapeHtml(formatDateTime(item.createdAt))}</td><td>${escapeHtml(item.action)}</td><td><code>${escapeHtml(item.actorAccountId)}</code></td><td><code>${escapeHtml(item.targetNoteId || item.targetAccountId || "—")}</code></td><td>${escapeHtml(item.reason)}</td></tr>`).join("")}</tbody></table></div>`; }
function renderOperations() { const readiness = state.results.operations; return `<p class="eyebrow">开发与运维</p><h1>运行状态</h1><p>仅显示公开就绪状态和运行边界；不会展示环境变量、密钥、令牌、IP、R2 对象路径或系统服务配置。</p><div class="admin-note">实际发布验收以 Worker 与 OVH 的健康、就绪和部署身份探针为准，不能以本页面渲染作为成功依据。</div><button id="admin-refresh-ops" class="button primary" type="button">刷新运行状态</button>${readiness ? `<pre>${escapeHtml(JSON.stringify(readiness, null, 2))}</pre>` : ""}`; }
async function refreshOperations() { await runBusy(async () => { state.results.operations = await api.readiness(); renderAdmin(); }); }

function showNoteModal(note) { const host = document.createElement("div"); host.className = "admin-modal-backdrop"; host.innerHTML = `<section class="admin-modal" role="dialog" aria-modal="true" aria-labelledby="admin-note-title"><p class="eyebrow">已审计的单条读取</p><h2 id="admin-note-title">${escapeHtml(note.title)}</h2><p>${escapeHtml([note.accountDisplayName, note.accountEmail, note.bookTitle ? `《${note.bookTitle}》` : "", note.author].filter(Boolean).join(" · "))}</p><pre>${escapeHtml(note.content || "")}</pre><div class="modal-actions"><button class="button primary" type="button">关闭</button></div></section>`; document.body.append(host); host.querySelector("button").addEventListener("click", () => host.remove()); host.addEventListener("click", event => { if (event.target === host) host.remove(); }); }
function openNotice(message) { const host = document.createElement("div"); host.className = "admin-modal-backdrop"; host.innerHTML = `<section class="admin-modal" role="dialog" aria-modal="true"><h2>需要用途说明</h2><p>${escapeHtml(message)}</p><div class="modal-actions"><button class="button primary" type="button">关闭</button></div></section>`; document.body.append(host); host.querySelector("button").addEventListener("click", () => host.remove()); }

async function runBusy(callback) { if (state.busy) return; state.busy = true; try { await callback(); } catch (error) { if (error?.code === "RECENT_AUTH_REQUIRED") return openReauth(() => callback()); openNotice(error?.message || "请求失败，请稍后重试。"); } finally { state.busy = false; } }
function openReauth(continuation) { const methods = state.account?.credentials || []; const hasPassword = methods.some(item => item.kind === "password"); const hasWeRead = methods.some(item => item.provider === "weread"); const host = document.createElement("div"); host.className = "admin-modal-backdrop"; host.innerHTML = `<section class="admin-modal" role="dialog" aria-modal="true"><p class="eyebrow">近期身份验证</p><h2>重新验证后继续</h2><p>管理读取需要近期身份验证，不会因为已登录就长期保持高权限。</p><div class="admin-login-switch">${hasPassword ? `<button data-reauth="password" class="active" type="button">账户密码</button>` : ""}${hasWeRead ? `<button data-reauth="weread" type="button">微信读书密钥</button>` : ""}</div><form id="admin-reauth-form"><label for="admin-reauth-secret">验证信息<input id="admin-reauth-secret" name="secret" type="password" autocomplete="off" required></label><button class="button primary" type="submit">验证并继续</button></form></section>`; document.body.append(host); let method = hasPassword ? "password" : "weread"; host.querySelectorAll("[data-reauth]").forEach(button => button.addEventListener("click", () => { method = button.dataset.reauth; host.querySelectorAll("[data-reauth]").forEach(item => item.classList.toggle("active", item === button)); })); host.querySelector("form").addEventListener("submit", async event => { event.preventDefault(); const secret = new FormData(event.currentTarget).get("secret"); try { if (method === "password") await api.reauthPassword(secret); else await api.reauthWeRead(secret); host.remove(); await runBusy(continuation); } catch (error) { openNotice(error?.message || "验证失败。"); } }); }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, "&#96;"); }
function formatCount(value) { return new Intl.NumberFormat("zh-CN").format(Number(value || 0)); }
function formatDateTime(value) { const seconds = Number(value || 0); if (!seconds) return "—"; return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(seconds < 1e12 ? seconds * 1000 : seconds); }
