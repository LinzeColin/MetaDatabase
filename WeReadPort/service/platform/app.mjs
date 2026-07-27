import { createHash, timingSafeEqual } from "node:crypto";
import { PlatformError } from "./service.mjs";

const COOKIE_NAME = "wrp_session";
const SECURITY_HEADERS = Object.freeze({
  "Cache-Control": "no-store",
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "Referrer-Policy": "no-referrer",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
});

export function createPlatformApp({ service, config }) {
  const buckets = new Map();
  return async function handle(request) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/healthz") return json({ status: "ok", service: "weread-port-account", version: "v0.0.0.1.8" });
      if (url.pathname === "/readyz") {
        const readiness = await service.readiness();
        return json(readiness, readiness.ready ? 200 : 503);
      }
      requireInternal(request, config.internalProxySecret);
      enforceOrigin(request, config.baseUrl);
      rateLimit(request, buckets);
      const sessionToken = cookieValue(request.headers.get("cookie"), COOKIE_NAME);
      const session = service.authenticate(sessionToken);
      const method = request.method.toUpperCase();
      const path = url.pathname.replace(/^\/v1/, "") || "/";

      if (method === "POST" && path === "/auth/register/password") { const input = await body(request, config.maxJsonBytes); authRateLimit(request, buckets, "register-password", input.email, 5); return authResponse(await service.registerPassword(input, requestContext(request)), config); }
      if (method === "POST" && path === "/auth/login/password") { const input = await body(request, config.maxJsonBytes); authRateLimit(request, buckets, "login-password", input.email, 8); return authResponse(await service.loginPassword(input, requestContext(request)), config); }
      if (method === "POST" && path === "/auth/register/weread") { const input = await body(request, config.maxJsonBytes); authRateLimit(request, buckets, "register-weread", String(input.key || "").slice(-8), 5); return authResponse(await service.registerWeRead(input, requestContext(request)), config); }
      if (method === "POST" && path === "/auth/login/weread") { const input = await body(request, config.maxJsonBytes); authRateLimit(request, buckets, "login-weread", String(input.key || "").slice(-8), 8); return authResponse(await service.loginWeRead(input, requestContext(request)), config); }

      const oauthStart = path.match(/^\/oauth\/(google|github|notion)\/start$/);
      if (method === "GET" && oauthStart) {
        const intent = url.searchParams.get("intent") || "login";
        if (intent !== "login") requireSession(session);
        const result = await service.startOAuth(oauthStart[1], { intent, accountId: session?.accountId || null });
        return json(result);
      }
      const oauthCallback = path.match(/^\/oauth\/(google|github|notion)\/callback$/);
      if (method === "GET" && oauthCallback) {
        const result = await service.completeOAuth(oauthCallback[1], { state: url.searchParams.get("state"), code: url.searchParams.get("code") }, requestContext(request), { expectedAccountId: session?.accountId || null, sessionToken });
        const callbackStatus = result.intent === "reauth" ? "reauthenticated" : "connected";
        const headers = new Headers({ Location: `${config.baseUrl}/?oauth=${encodeURIComponent(result.provider)}&status=${callbackStatus}` });
        if (result.session) headers.append("Set-Cookie", sessionCookie(result.session.token, result.session.expiresAt, config));
        return secure(new Response(null, { status: 303, headers }));
      }

      requireSession(session);
      if (isMutation(method)) {
        service.verifyCsrf(session, request.headers.get("x-csrf-token"));
        if (!["POST /auth/logout", "POST /auth/reauth/password"].includes(`${method} ${path}`)) enforceJson(request);
      }

      if (method === "GET" && path === "/session") { const refreshed = service.refreshSession(sessionToken); if (!refreshed) throw new PlatformError("AUTH_REQUIRED", "请重新登录。", 401); return json({ account: refreshed.account, csrf: refreshed.csrf, expiresAt: refreshed.expiresAt }, 200, { "Set-Cookie": sessionCookie(refreshed.token, refreshed.expiresAt, config) }); }
      if (method === "POST" && path === "/auth/logout") { service.logout(sessionToken); return json({ loggedOut: true }, 200, { "Set-Cookie": clearCookie(config) }); }
      if (method === "POST" && path === "/auth/reauth/password") { const input = await body(request, config.maxJsonBytes); await service.reauthenticatePassword(session.accountId, input.password, sessionToken); return json({ reauthenticated: true }); }
      if (method === "POST" && path === "/auth/reauth/weread") { const input = await body(request, config.maxJsonBytes); await service.reauthenticateWeRead(session.accountId, input.key, sessionToken); return json({ reauthenticated: true }); }
      if (method === "POST" && path === "/auth/link/weread") { service.requireRecentAuth(session); return json({ account: await service.bindWeRead(session.accountId, (await body(request, config.maxJsonBytes)).key) }); }
      if (method === "POST" && path === "/auth/rotate/weread") { service.requireRecentAuth(session); return json({ account: await service.bindWeRead(session.accountId, (await body(request, config.maxJsonBytes)).key) }); }
      if (method === "POST" && path === "/account/password") { const hasPassword = service.publicAccount(session.accountId)?.credentials?.some(item => item.kind === "password"); if (!hasPassword) service.requireRecentAuth(session); const result = await service.configurePassword(session.accountId, await body(request, config.maxJsonBytes), sessionToken); return json(result); }
      if (method === "GET" && path === "/account/sessions") return json({ sessions: service.listSessions(session.accountId, sessionToken) });
      if (method === "POST" && path === "/account/sessions/revoke-others") { service.requireRecentAuth(session); return json(service.revokeOtherSessions(session.accountId, sessionToken)); }
      const sessionMatch = path.match(/^\/account\/sessions\/([A-Za-z0-9_-]+)$/);
      if (method === "DELETE" && sessionMatch) { service.requireRecentAuth(session); const result = service.revokeSession(session.accountId, sessionMatch[1], sessionToken); return json(result, 200, result.currentSession ? { "Set-Cookie": clearCookie(config) } : {}); }

      if (method === "GET" && path === "/profile") return json({ account: service.publicAccount(session.accountId) });
      if (method === "PATCH" && path === "/profile") return json({ account: service.updateProfile(session.accountId, await body(request, config.maxJsonBytes)) });
      if (method === "GET" && path === "/consent") return json({ consent: service.store.getConsent(session.accountId) });
      if (method === "PATCH" && path === "/consent") return json({ consent: service.updateConsent(session.accountId, await body(request, config.maxJsonBytes)) });

      if (method === "GET" && path === "/notes") return json({ notes: service.listNotes(session.accountId, { limit: boundedInt(url.searchParams.get("limit"), 200, 1, 500) }) });
      if (method === "POST" && path === "/notes") { const input = await body(request, config.maxJsonBytes); return json({ note: await service.saveDocument(session.accountId, input, { expectedVersion: input.expectedVersion ?? null }) }, 201); }
      const noteMatch = path.match(/^\/notes\/([A-Za-z0-9_-]+)$/);
      if (method === "GET" && noteMatch) { const note = await service.readNote(session.accountId, noteMatch[1]); if (!note) throw new PlatformError("NOT_FOUND", "笔记不存在。", 404); return json({ note }); }
      if (method === "PUT" && noteMatch) { const input = await body(request, config.maxJsonBytes); return json({ note: await service.saveDocument(session.accountId, { ...input, externalId: input.externalId || noteMatch[1] }, { expectedVersion: input.expectedVersion ?? null }) }); }
      if (method === "DELETE" && noteMatch) return json(await service.deleteNote(session.accountId, noteMatch[1], url.searchParams.get("expectedVersion")));

      if (method === "POST" && path === "/sync/pull") { const input = await body(request, config.maxJsonBytes); return json(await service.syncPull(session.accountId, input.cursor, input.limit)); }
      if (method === "POST" && path === "/sync/push") { const input = await body(request, config.maxJsonBytes); return json(await service.syncPush(session.accountId, input.operations)); }

      const itemsMatch = path.match(/^\/imports\/(google|github|notion)\/items$/);
      if (method === "GET" && itemsMatch) return json(await service.listProviderItems(session.accountId, itemsMatch[1], { container: url.searchParams.get("container") || "", cursor: url.searchParams.get("cursor") || "", limit: boundedInt(url.searchParams.get("limit"), 200, 1, 500) }));
      const importStart = path.match(/^\/imports\/(google|github|notion|obsidian)\/start$/);
      if (method === "POST" && importStart) { const input = await body(request, config.maxImportBytes); const job = service.createImportJob(session.accountId, importStart[1], input.selection, request.headers.get("idempotency-key") || input.idempotencyKey); return json({ job }, 202); }
      const jobMatch = path.match(/^\/imports\/jobs\/([A-Za-z0-9_-]+)$/);
      if (method === "GET" && jobMatch) { const job = service.getImportJob(session.accountId, jobMatch[1]); if (!job) throw new PlatformError("NOT_FOUND", "导入任务不存在。", 404); return json({ job }); }

      if (method === "POST" && path === "/weread/sync") return json(await service.syncWeRead(session.accountId, await body(request, config.maxJsonBytes)));
      if (method === "GET" && path === "/analytics/dashboard") return json({ dashboard: service.analytics(session.accountId) });
      if (method === "GET" && path === "/account/export") { service.requireRecentAuth(session); return json(await service.exportAccount(session.accountId)); }
      if (method === "POST" && path === "/account/delete") { service.requireRecentAuth(session); const result = await service.deleteAccount(session.accountId); return json(result, 200, { "Set-Cookie": clearCookie(config) }); }
      if (method === "GET" && path === "/status/business-lines") { const readiness = await service.readiness(); return json({ version: "v0.0.0.1.8", readiness, lines: businessLines(service.store.counts(), readiness) }); }

      throw new PlatformError("NOT_FOUND", "接口不存在。", 404);
    } catch (error) {
      return errorResponse(error);
    }
  };
}

function authResponse(result, config) {
  return json({ account: result.account, csrf: result.session.csrf, expiresAt: result.session.expiresAt }, 200, { "Set-Cookie": sessionCookie(result.session.token, result.session.expiresAt, config) });
}
function requireInternal(request, expected) { const actual = request.headers.get("x-wrp-internal-secret") || ""; if (!secureEqual(actual, expected)) throw new PlatformError("INTERNAL_AUTH", "服务身份验证失败。", 401); }
function requireSession(session) { if (!session) throw new PlatformError("AUTH_REQUIRED", "请先登录。", 401); }
function enforceOrigin(request, baseUrl) { const origin = request.headers.get("origin"); if (origin && origin !== new URL(baseUrl).origin) throw new PlatformError("ORIGIN", "拒绝跨站请求。", 403); const site = request.headers.get("sec-fetch-site"); if (site && !["same-origin", "same-site", "none"].includes(site)) throw new PlatformError("ORIGIN", "拒绝跨站请求。", 403); }
function enforceJson(request) { if (!String(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) throw new PlatformError("CONTENT_TYPE", "Content-Type 必须是 application/json。", 415); }
function isMutation(method) { return ["POST", "PUT", "PATCH", "DELETE"].includes(method); }
function requestContext(request) { return { userAgent: request.headers.get("user-agent") || "", ipPrefix: request.headers.get("x-forwarded-for")?.split(",")[0]?.trim().replace(/(\d+\.\d+\.\d+)\.\d+/, "$1.0") || "" }; }

async function body(request, maxBytes) {
  enforceJson(request);
  const length = Number(request.headers.get("content-length") || 0);
  if (length > maxBytes) throw new PlatformError("TOO_LARGE", "请求超过安全上限。", 413);
  const bytes = Buffer.from(await request.arrayBuffer());
  if (bytes.length > maxBytes) throw new PlatformError("TOO_LARGE", "请求超过安全上限。", 413);
  try { return JSON.parse(bytes.toString("utf8") || "{}"); } catch { throw new PlatformError("INVALID_JSON", "请求不是有效 JSON。", 400); }
}
function json(payload, status = 200, extraHeaders = {}) { return secure(new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...extraHeaders } })); }
function secure(response) { const headers = new Headers(response.headers); for (const [key, value] of Object.entries(SECURITY_HEADERS)) if (!headers.has(key)) headers.set(key, value); return new Response(response.body, { status: response.status, statusText: response.statusText, headers }); }
function errorResponse(error) { const known = error instanceof PlatformError; const status = known ? error.status : 500; const payload = { error: { code: known ? error.code : "INTERNAL", message: known ? error.message : "服务暂时不可用，请稍后重试。" } }; return json(payload, status); }
function cookieValue(header, name) { for (const item of String(header || "").split(";")) { const [key, ...rest] = item.trim().split("="); if (key === name) return rest.join("="); } return ""; }
function sessionCookie(token, expiresAt, config) { const secureFlag = config.production ? "; Secure" : ""; return `${COOKIE_NAME}=${token}; Path=/; HttpOnly; SameSite=Lax${secureFlag}; Expires=${new Date(expiresAt * 1000).toUTCString()}`; }
function clearCookie(config) { const secureFlag = config.production ? "; Secure" : ""; return `${COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax${secureFlag}; Max-Age=0`; }
function boundedInt(value, fallback, min, max) { const parsed = Number(value ?? fallback); return Number.isInteger(parsed) ? Math.min(Math.max(parsed, min), max) : fallback; }
function rateLimit(request, buckets) { boundedRateLimit(request, buckets, "global", "", 300, 60_000); }
function authRateLimit(request, buckets, scope, subject, limit) { boundedRateLimit(request, buckets, scope, subject, limit, 15 * 60_000); }
function boundedRateLimit(request, buckets, scope, subject, limit, windowMs) {
  const remote = request.headers.get("cf-connecting-ip") || request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
  const slot = Math.floor(Date.now() / windowMs);
  const identity = createHash("sha256").update(`${remote}|${String(subject || "").trim().toLowerCase()}`).digest("hex").slice(0, 24);
  const bucketKey = `${scope}:${identity}:${slot}`;
  const next = (buckets.get(bucketKey) || 0) + 1; buckets.set(bucketKey, next);
  if (next > limit) throw new PlatformError("RATE_LIMIT", "尝试次数过多，请稍后再试。", 429);
  if (buckets.size > 5000) for (const item of buckets.keys()) if (!item.endsWith(`:${slot}`)) buckets.delete(item);
}
function secureEqual(left, right) {
  const a = Buffer.from(String(left || "")); const b = Buffer.from(String(right || ""));
  return a.length > 0 && a.length === b.length && timingSafeEqual(a, b);
}
function businessLines(counts, readiness) {
  const deps = readiness?.dependencies || {};
  const providerReady = Object.values(deps.providers || {}).every(item => item.configured);
  const storageState = deps.database?.ok && deps.objectStore?.ok ? "READY" : "BLOCKED";
  const importState = !deps.importWorker?.ok ? "BLOCKED" : counts.stalledImports ? "DEGRADED" : counts.pendingImports ? "RUNNING" : "READY";
  return [
    line("public-trust", "公开信任面", "READY", "隐私、条款、状态与机器端点"),
    line("identity-access", "账户与多平台身份", providerReady ? "READY" : "BLOCKED", "密码、微信读书密钥、Google、GitHub、Notion"),
    line("account-storage", "账户数据隔离与加密", storageState, `${counts.accounts} 个账户，${counts.notes} 条加密笔记索引`),
    line("cross-device-sync", "跨设备云同步", deps.database?.ok ? "READY" : "BLOCKED", "游标、幂等与乐观冲突"),
    line("provider-imports", "四平台一键导入", importState, `${counts.pendingImports} 个处理中，${counts.stalledImports} 个租约超时`),
    line("weread-wide-sync", "微信读书广范围同步", "NOT_VERIFIED", "能力发现、全游标、书架、批注、书评、进度、统计、推荐"),
    line("analytics-recommendations", "画像、热度与推荐", "READY", "明确同意、确定性聚合、无模型 Token"),
    line("legacy-migration", "匿名迁移兼容入口", "READY", "/migrate 兼容旧导出"),
    line("release-supply-chain", "发布与供应链", "NOT_VERIFIED", "等待同一 commit 的 CI 与部署证据"),
    line("operations-recovery", "运维、自愈与恢复", readiness?.ready ? (counts.pendingOutbox ? "DEGRADED" : "READY") : "BLOCKED", `${counts.pendingOutbox} 个待同步事实`),
    line("facts-backup", "结构化事实与异地冷备", "EXTERNAL", "Private-Database、R2 与 OCI 外部证据"),
  ];
}
function line(id, name, state, detail) { return { id, name, stage: "v0.0.0.1.8", state, detail }; }
