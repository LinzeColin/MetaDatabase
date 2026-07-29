import {
  APP_NAME,
  APP_VERSION,
  DEFAULT_GATEWAY_TIMEOUT_MS,
  MAX_GATEWAY_REQUEST_BYTES,
  MAX_GATEWAY_RESPONSE_BYTES,
  OFFICIAL_WEREAD_GATEWAY,
  OPERATIONS_STATUS_URL,
  SOURCE_SKILL_VERSION,
} from "../core/constants.js";
import {
  BUSINESS_GOVERNANCE_SCHEMA_VERSION,
  buildBusinessLineStatus,
  summarizeBusinessLines,
  validateBusinessLineGraph,
} from "../core/business-governance.js";
import { parseProxyBody, validateUserKey } from "../core/contract.js";
import { WeReadPortError, toSafeFailure } from "../core/errors.js";
import { combineSignals } from "../core/util.js";

const BUSINESS_GRAPH_ERRORS = Object.freeze(validateBusinessLineGraph());
const RATE_LIMIT_PER_MINUTE = 240;
const rateBuckets = new Map();
const SECURITY_HEADERS = Object.freeze({
  "Content-Security-Policy": "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; connect-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; media-src 'none'; worker-src 'self'; manifest-src 'self'; upgrade-insecure-requests",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
});

/** ChatGPT Sites / Cloudflare Worker 请求入口。@param {Request} request @param {Record<string,any>} env */
export async function handleRequest(request, env = {}) {
  const url = new URL(request.url);
  const rawPath = url.pathname;
  const path = normalizePath(rawPath);
  try {
    if (["/privacy", "/terms", "/status"].includes(rawPath)) {
      return secure(redirectForRequest(request, `${rawPath}/`));
    }
    if (path === "/healthz") return secure(machineHealth(request, url, env));
    if (path === "/readyz") return secure(await machineReadiness(request, url, env));
    if (path === "/api/status") return secure(await publicStatusResponse(request, url, env));
    if (path === "/api/version") {
      return secure(jsonForRequest(request, {
        app: APP_NAME,
        appVersion: APP_VERSION,
        sourceSkillVersion: SOURCE_SKILL_VERSION,
        businessGovernanceSchemaVersion: BUSINESS_GOVERNANCE_SCHEMA_VERSION,
        taskpackVersion: "v0.0.0.1.9",
        releaseCommit: String(env.WRP_RELEASE_COMMIT || ""),
        ovhReleaseId: String(env.WRP_OVH_RELEASE_ID || ""),
        sitesProjectId: String(env.WRP_SITES_PROJECT_ID || ""),
      }));
    }
    if (path.startsWith("/api/platform/")) {
      if (request.method === "OPTIONS") return secure(new Response(null, { status: 204, headers: { Allow: "GET, POST, PUT, PATCH, DELETE, OPTIONS" } }));
      return secure(await proxyAccountPlatform(request, env));
    }
    if (path === "/api/weread/gateway") {
      if (request.method === "OPTIONS") return secure(new Response(null, { status: 204, headers: { Allow: "POST, OPTIONS" } }));
      return secure(await proxyGateway(request, env));
    }
    if (path.startsWith("/api/")) {
      return secure(jsonForRequest(request, { error: { code: "NOT_FOUND", message: "接口不存在。" } }, 404));
    }
    if (!env.ASSETS || typeof env.ASSETS.fetch !== "function") {
      return secure(new Response(request.method === "HEAD" ? null : "静态资源绑定不可用。", { status: 503 }));
    }
    return secure(await fetchAssetWithCanonicalRedirect(staticAssetRequest(request, url), env));
  } catch (error) {
    const safe = toSafeFailure(error);
    const status = error instanceof WeReadPortError && error.status ? error.status : 500;
    return secure(jsonForRequest(request, { error: safe }, status));
  }
}

function machineHealth(request, url, env) {
  assertMachineMethod(request);
  return jsonForRequest(request, {
    ok: true,
    status: "ALIVE",
    app: APP_NAME,
    version: APP_VERSION,
    runtimeMode: runtimeMode(url, env),
    checkedAt: new Date().toISOString(),
  });
}

async function machineReadiness(request, url, env) {
  assertMachineMethod(request);
  const assets = await inspectAssets(request, env);
  const accountService = await inspectAccountService(request, env);
  const governanceReady = BUSINESS_GRAPH_ERRORS.length === 0;
  const ready = assets.ready && accountService.ready && governanceReady;
  return jsonForRequest(request, {
    ok: ready,
    status: ready ? "READY" : "NOT_READY",
    app: APP_NAME,
    version: APP_VERSION,
    runtimeMode: runtimeMode(url, env),
    checkedAt: new Date().toISOString(),
    checks: {
      staticAssets: assets,
      accountPlatformService: accountService,
      gatewayProxyContract: { ready: true, detail: "代理地址、接口白名单、参数白名单和上游技能版本已加载；未使用用户密钥探测上游。" },
      businessGovernanceContract: {
        ready: governanceReady,
        schemaVersion: BUSINESS_GOVERNANCE_SCHEMA_VERSION,
        detail: governanceReady ? "业务线标识唯一、依赖存在且依赖图无环。" : "业务治理合同无效。",
        errorCodes: BUSINESS_GRAPH_ERRORS,
      },
    },
  }, ready ? 200 : 503);
}

async function publicStatusResponse(request, url, env) {
  assertMachineMethod(request);
  const assets = await inspectAssets(request, env);
  const accountService = await inspectAccountService(request, env);
  const mode = runtimeMode(url, env);
  const checkedAt = new Date().toISOString();
  const businessLines = buildBusinessLineStatus({ assetsReady: assets.ready, accountServiceReady: accountService.ready, checkedAt });
  const governanceReady = BUSINESS_GRAPH_ERRORS.length === 0;
  const operational = assets.ready && accountService.ready && governanceReady;
  return jsonForRequest(request, {
    ok: operational,
    status: operational ? "OPERATIONAL" : "DEGRADED",
    statusLabel: operational ? "运行正常" : "部分降级",
    app: APP_NAME,
    appVersion: APP_VERSION,
    sourceSkillVersion: SOURCE_SKILL_VERSION,
    runtimeMode: mode,
    runtimeLabel: runtimeLabel(mode),
    checkedAt,
    components: {
      publicApplication: {
        status: assets.ready ? "AVAILABLE" : "UNAVAILABLE",
        label: assets.ready ? "公开应用可用" : "静态资源不可用",
        detail: assets.detail,
      },
      accountPlatform: {
        status: accountService.ready ? "AVAILABLE" : "UNAVAILABLE",
        label: accountService.ready ? "账户、同步与云端存储服务可用" : "账户平台服务不可用",
        detail: accountService.detail,
      },
      localImportAndExport: {
        status: assets.ready ? "AVAILABLE" : "UNAVAILABLE",
        label: assets.ready ? "本地上传与导出内核可加载" : "无法加载浏览器应用",
        detail: "ZIP、JSON、Markdown 和 TXT 在当前浏览器中处理；不会通过状态检查读取用户文件。",
      },
      wereadGatewayProxy: {
        status: "AVAILABLE",
        label: "微信读书代理合同已加载",
        detail: "这里只验证本站代理合同，不使用任何用户密钥调用腾讯上游。真实连接结果取决于用户权限与上游可用性。",
      },
      operationsOverview: {
        status: "EXTERNAL",
        label: "供应商与基础设施状态",
        detail: "外部状态入口独立运行，不接收用户密钥或笔记。",
        url: OPERATIONS_STATUS_URL,
      },
    },
    businessGovernance: {
      schemaVersion: BUSINESS_GOVERNANCE_SCHEMA_VERSION,
      graphStatus: governanceReady ? "VALID" : "INVALID",
      graphErrors: BUSINESS_GRAPH_ERRORS,
      summary: summarizeBusinessLines(businessLines),
      lines: businessLines,
    },
    dataBoundary: {
      serverSideUserNotePersistence: true,
      serverSideUserKeyPersistence: "账户级加密凭据；不明文存储",
      accountScopedEncryption: true,
      multiTenantIsolation: true,
      statusContainsUserContent: false,
      businessGovernanceContainsUserContent: false,
    },
  });
}


function redirectForRequest(request, pathname) {
  if (!['GET', 'HEAD'].includes(request.method)) {
    throw new WeReadPortError("METHOD", "只允许 GET 或 HEAD。", { status: 405 });
  }
  const target = new URL(pathname, request.url);
  return new Response(null, { status: 308, headers: { Location: target.toString(), "Cache-Control": "no-cache" } });
}

function assertMachineMethod(request) {
  if (!["GET", "HEAD"].includes(request.method)) {
    throw new WeReadPortError("METHOD", "只允许 GET 或 HEAD。", { status: 405 });
  }
}

async function inspectAssets(request, env) {
  if (!env.ASSETS || typeof env.ASSETS.fetch !== "function") {
    return { ready: false, detail: "静态资源绑定不可用。" };
  }
  const probeUrl = new URL("/site/home.html", request.url);
  let response;
  try {
    response = await fetchAssetWithCanonicalRedirect(new Request(probeUrl, { method: "GET", headers: { Accept: "text/html" } }), env);
    const contentType = response.headers.get("content-type") ?? "";
    const ready = response.ok && contentType.toLowerCase().includes("text/html");
    await response.body?.cancel().catch(() => {});
    return {
      ready,
      detail: ready ? "主页静态资源已通过同源探测。" : `主页静态资源探测失败（HTTP ${response.status}）。`,
    };
  } catch {
    return { ready: false, detail: "主页静态资源探测发生异常。" };
  }
}


async function inspectAccountService(request, env) {
  const raw = String(env.WEREAD_ACCOUNT_SERVICE_URL || "").trim();
  const internalSecret = String(env.WRP_INTERNAL_PROXY_SECRET || "");
  const expected = {
    taskpackVersion: "v0.0.0.1.9",
    releaseCommit: String(env.WRP_RELEASE_COMMIT || ""),
    ovhReleaseId: String(env.WRP_OVH_RELEASE_ID || ""),
    sitesProjectId: String(env.WRP_SITES_PROJECT_ID || ""),
  };
  if (!raw || !internalSecret) return { ready: false, detail: "账户平台地址或内部代理密钥未配置。", releaseIdentity: expected };
  if (!expected.releaseCommit || !expected.ovhReleaseId || !expected.sitesProjectId) return { ready: false, detail: "部署身份未绑定 commit、OVH release 或 Sites project。", releaseIdentity: expected };
  let base;
  try { base = new URL(raw); } catch { return { ready: false, detail: "账户平台服务地址无效。", releaseIdentity: expected }; }
  if (base.protocol !== "https:" && !["127.0.0.1", "localhost"].includes(base.hostname)) return { ready: false, detail: "账户平台服务必须使用 HTTPS。", releaseIdentity: expected };
  try {
    const probe = new URL("/internal/readyz", base);
    const fetchImpl = typeof env.ACCOUNT_SERVICE_FETCH === "function" ? env.ACCOUNT_SERVICE_FETCH : fetch;
    const response = await fetchImpl(probe, {
      method: "GET", redirect: "manual",
      headers: { Accept: "application/json", "User-Agent": "WeReadPort-Readiness/0.0.0.1.9", "x-wrp-internal-secret": internalSecret },
    });
    const payload = await response.json().catch(() => ({}));
    const actual = payload?.releaseIdentity || {};
    const identityMatches = Object.entries(expected).every(([key, value]) => actual[key] === value);
    const ready = response.ok && payload?.ready === true && identityMatches;
    return {
      ready,
      detail: ready ? "账户平台通过内部密钥、依赖与部署身份探测。" : `账户平台就绪或部署身份不匹配（HTTP ${response.status}）。`,
      releaseIdentity: actual,
      expectedReleaseIdentity: expected,
    };
  } catch { return { ready: false, detail: "账户平台服务就绪探测发生异常。", releaseIdentity: expected }; }
}

async function proxyAccountPlatform(request, env) {
  assertSameOrigin(request, { allowOAuthCallbackNavigation: true });
  enforceRateLimit(request);
  const rawBase = String(env.WEREAD_ACCOUNT_SERVICE_URL || "").trim();
  const internalSecret = String(env.WRP_INTERNAL_PROXY_SECRET || "");
  if (!rawBase || !internalSecret) throw new WeReadPortError("NOT_READY", "账户平台服务尚未配置。", { status: 503 });
  let base;
  try { base = new URL(rawBase); } catch { throw new WeReadPortError("NOT_READY", "账户平台服务配置无效。", { status: 503 }); }
  if (base.protocol !== "https:" && !["127.0.0.1", "localhost"].includes(base.hostname)) throw new WeReadPortError("NOT_READY", "账户平台服务必须使用 HTTPS。", { status: 503 });
  const incoming = new URL(request.url);
  const target = new URL(incoming.pathname.replace(/^\/api\/platform/, "") || "/", base);
  target.search = incoming.search;
  const headers = new Headers();
  for (const name of ["accept", "content-type", "cookie", "idempotency-key", "origin", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest", "user-agent", "x-csrf-token"]) {
    const value = request.headers.get(name); if (value) headers.set(name, value);
  }
  headers.set("x-wrp-internal-secret", internalSecret);
  const ip = request.headers.get("cf-connecting-ip"); if (ip) headers.set("x-forwarded-for", ip);
  const fetchImpl = typeof env.ACCOUNT_SERVICE_FETCH === "function" ? env.ACCOUNT_SERVICE_FETCH : fetch;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 35_000);
  try {
    const response = await fetchImpl(target, { method: request.method, headers, body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body, redirect: "manual", signal: combineSignals(request.signal, controller.signal) });
    const outputHeaders = new Headers();
    for (const name of ["content-type", "cache-control", "set-cookie", "location", "retry-after"]) {
      const value = response.headers.get(name); if (value) outputHeaders.set(name, value);
    }
    if (outputHeaders.has("location")) {
      const location = new URL(outputHeaders.get("location"), incoming.origin);
      if (location.origin !== incoming.origin) throw new WeReadPortError("UPSTREAM_REDIRECT", "账户服务返回了非同源重定向。", { status: 502 });
      outputHeaders.set("location", location.toString());
    }
    return new Response(response.body, { status: response.status, headers: outputHeaders });
  } catch (error) {
    if (controller.signal.aborted) throw new WeReadPortError("TIMEOUT", "账户平台服务响应超时。", { status: 504, retryable: true });
    if (error instanceof WeReadPortError) throw error;
    throw new WeReadPortError("NETWORK", "无法连接账户平台服务。", { status: 502, retryable: true });
  } finally { clearTimeout(timer); }
}

function runtimeMode(url, env) {
  const configured = String(env.DEPLOYMENT_ENV ?? "").trim().toLowerCase();
  if (["production", "preview", "local"].includes(configured)) return configured;
  if (["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) return "local";
  if (url.hostname.endsWith(".chatgpt.site")) return "production";
  return "preview";
}

function runtimeLabel(mode) {
  return ({ production: "线上生产环境", preview: "预览或自定义环境", local: "本地预览环境" })[mode] ?? "未知环境";
}

function normalizePath(value) {
  if (value === "/") return value;
  return value.replace(/\/+$/u, "") || "/";
}

/** Keep public routes out of the direct static-asset namespace so Sites always
 * reaches this Worker before a document is returned. */
function staticAssetRequest(request, url) {
  const target = new URL(url);
  target.pathname = staticAssetPath(url.pathname);
  return new Request(target.toString(), request);
}

async function fetchAssetWithCanonicalRedirect(request, env) {
  let response = await env.ASSETS.fetch(request);
  const location = response.headers.get("location");
  if (response.status < 300 || response.status >= 400 || !location) return response;
  let canonical;
  try { canonical = new URL(location, request.url); } catch { return response; }
  const source = new URL(request.url);
  if (canonical.origin !== source.origin || !canonical.pathname.startsWith("/site/")) return response;
  response = await env.ASSETS.fetch(new Request(canonical.toString(), request));
  return response;
}

function staticAssetPath(pathname) {
  if (pathname === "/") return "/site/home.html";
  if (["/privacy/", "/terms/", "/status/"].includes(pathname)) return `/site${pathname}page.html`;
  if (pathname.startsWith("/assets/") || /\.[A-Za-z0-9]{1,16}$/u.test(pathname)) return `/site${pathname}`;
  return "/site/home.html";
}

/** @param {Request} request @param {Record<string,any>} env */
async function proxyGateway(request, env) {
  if (request.method !== "POST") {
    throw new WeReadPortError("METHOD", "只允许 POST。", { status: 405 });
  }
  assertSameOrigin(request);
  enforceRateLimit(request);
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    throw new WeReadPortError("INVALID_REQUEST", "Content-Type 必须是 application/json。", { status: 415 });
  }
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > MAX_GATEWAY_REQUEST_BYTES) {
    throw new WeReadPortError("INVALID_REQUEST", "请求超过安全上限。", { status: 413 });
  }
  const requestBytes = await readLimitedBody(request, MAX_GATEWAY_REQUEST_BYTES, "请求超过安全上限。");
  let input;
  try {
    input = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(requestBytes));
  } catch (error) {
    throw new WeReadPortError("INVALID_REQUEST", "请求体不是有效 JSON。", { status: 400, cause: error });
  }
  const body = parseProxyBody(input);
  const key = validateUserKey(extractBearer(request.headers.get("authorization")));
  const upstreamFetch = typeof env.UPSTREAM_FETCH === "function" ? env.UPSTREAM_FETCH : fetch;
  const configuredTimeout = Number(env.UPSTREAM_TIMEOUT_MS);
  const timeoutMs = Number.isFinite(configuredTimeout) ? Math.max(1, Math.min(DEFAULT_GATEWAY_TIMEOUT_MS, Math.floor(configuredTimeout))) : DEFAULT_GATEWAY_TIMEOUT_MS;
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(new Error("上游请求超时")), timeoutMs);
  let upstream;
  try {
    upstream = await upstreamFetch(OFFICIAL_WEREAD_GATEWAY, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
      redirect: "manual",
      cache: "no-store",
      signal: combineSignals(request.signal, timeoutController.signal),
    });
  } catch (error) {
    if (timeoutController.signal.aborted && !request.signal.aborted) {
      throw new WeReadPortError("TIMEOUT", "微信读书官方接口响应超时。", { status: 504, retryable: true, cause: error });
    }
    throw new WeReadPortError("NETWORK", "无法连接微信读书官方接口。", { status: 502, retryable: true, cause: error });
  } finally {
    clearTimeout(timer);
  }
  const responseBytes = await readLimitedResponse(upstream, MAX_GATEWAY_RESPONSE_BYTES);
  // Parse once at the trust boundary so non-JSON upstream content cannot be relayed as an opaque success.
  try {
    JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(responseBytes));
  } catch (error) {
    throw new WeReadPortError("SCHEMA", "微信读书官方接口返回了无法解析的 JSON。", { status: 502, cause: error });
  }
  return new Response(responseBytes, {
    status: upstream.status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-WeRead-Source-Skill-Version": SOURCE_SKILL_VERSION,
    },
  });
}

/** @param {Request} request @param {{allowOAuthCallbackNavigation?: boolean}} [options] */
function assertSameOrigin(request, { allowOAuthCallbackNavigation = false } = {}) {
  const url = new URL(request.url);
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (origin && origin !== url.origin) {
    throw new WeReadPortError("FORBIDDEN", "拒绝跨站请求。", { status: 403 });
  }
  const oauthCallbackNavigation = allowOAuthCallbackNavigation && isOAuthCallbackNavigation(request, url, origin, fetchSite);
  if (fetchSite && !["same-origin", "same-site", "none"].includes(fetchSite) && !oauthCallbackNavigation) {
    throw new WeReadPortError("FORBIDDEN", "拒绝跨站请求。", { status: 403 });
  }
}

/** OAuth 提供方只能经跨站顶层导航回调；状态码与 PKCE 仍由账户服务验证。 */
function isOAuthCallbackNavigation(request, url, origin, fetchSite) {
  return request.method === "GET"
    && origin === null
    && fetchSite === "cross-site"
    && request.headers.get("sec-fetch-mode") === "navigate"
    && request.headers.get("sec-fetch-dest") === "document"
    && /^\/api\/platform\/v1\/oauth\/(google|github|notion)\/callback$/.test(url.pathname);
}

/** Best-effort per-isolate abuse control; upstream/user-key limits remain authoritative. @param {Request} request */
function enforceRateLimit(request) {
  const nowMinute = Math.floor(Date.now() / 60_000);
  // Trust only the platform-provided Cloudflare address. A client-controlled
  // X-Forwarded-For header must not create unbounded buckets.
  const identity = request.headers.get("cf-connecting-ip") || "unknown";
  const bucketKey = `${identity}:${nowMinute}`;
  if (!rateBuckets.has(bucketKey)) {
    for (const key of rateBuckets.keys()) {
      if (!key.endsWith(`:${nowMinute}`)) rateBuckets.delete(key);
    }
    // Bound isolate memory even under a distributed address-flood attempt.
    if (rateBuckets.size >= 2_000) {
      throw new WeReadPortError("RATE_LIMIT", "请求过于频繁，请稍后重试。", { status: 429, retryable: true });
    }
  }
  const count = (rateBuckets.get(bucketKey) ?? 0) + 1;
  rateBuckets.set(bucketKey, count);
  if (count > RATE_LIMIT_PER_MINUTE) {
    throw new WeReadPortError("RATE_LIMIT", "请求过于频繁，请稍后重试。", { status: 429, retryable: true });
  }
}

/** @param {string|null} value */
function extractBearer(value) {
  const match = typeof value === "string" ? value.match(/^Bearer\s+(.+)$/i) : null;
  if (!match) throw new WeReadPortError("AUTH", "缺少微信读书密钥。", { status: 401 });
  return match[1];
}

/** @param {Request} request @param {number} maxBytes @param {string} message */
async function readLimitedBody(request, maxBytes, message) {
  if (!request.body) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (!value) continue;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel();
      throw new WeReadPortError("INVALID_REQUEST", message, { status: 413 });
    }
    chunks.push(value);
  }
  return concatBytes(chunks, total);
}

/** @param {Response} response @param {number} maxBytes */
async function readLimitedResponse(response, maxBytes) {
  const declared = Number(response.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > maxBytes) {
    throw new WeReadPortError("TOO_LARGE", "微信读书官方接口响应超过安全上限。", { status: 502 });
  }
  if (!response.body) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > maxBytes) throw new WeReadPortError("TOO_LARGE", "微信读书官方接口响应超过安全上限。", { status: 502 });
    return bytes;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (!value) continue;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel();
      throw new WeReadPortError("TOO_LARGE", "微信读书官方接口响应超过安全上限。", { status: 502 });
    }
    chunks.push(value);
  }
  return concatBytes(chunks, total);
}

/** @param {Uint8Array[]} chunks @param {number} total */
function concatBytes(chunks, total) {
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

/** @param {unknown} value @param {number} [status] */
function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function jsonForRequest(request, value, status = 200) {
  const response = json(value, status);
  if (request.method !== "HEAD") return response;
  return new Response(null, { status, headers: response.headers });
}

/** @param {Response} response */
function secure(response) {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) headers.set(name, value);
  if (!headers.has("Cache-Control")) headers.set("Cache-Control", "no-cache");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}
