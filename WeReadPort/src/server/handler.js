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
      }));
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
    return secure(await env.ASSETS.fetch(request));
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
  const governanceReady = BUSINESS_GRAPH_ERRORS.length === 0;
  const ready = assets.ready && governanceReady;
  return jsonForRequest(request, {
    ok: ready,
    status: ready ? "READY" : "NOT_READY",
    app: APP_NAME,
    version: APP_VERSION,
    runtimeMode: runtimeMode(url, env),
    checkedAt: new Date().toISOString(),
    checks: {
      staticAssets: assets,
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
  const mode = runtimeMode(url, env);
  const checkedAt = new Date().toISOString();
  const businessLines = buildBusinessLineStatus({ assetsReady: assets.ready, checkedAt });
  const governanceReady = BUSINESS_GRAPH_ERRORS.length === 0;
  const operational = assets.ready && governanceReady;
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
      serverSideUserNotePersistence: false,
      serverSideUserKeyPersistence: false,
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
  const probeUrl = new URL("/index.html", request.url);
  let response;
  try {
    response = await env.ASSETS.fetch(new Request(probeUrl, { method: "GET", headers: { Accept: "text/html" } }));
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

/** @param {Request} request */
function assertSameOrigin(request) {
  const url = new URL(request.url);
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (origin && origin !== url.origin) {
    throw new WeReadPortError("FORBIDDEN", "拒绝跨站请求。", { status: 403 });
  }
  if (fetchSite && !["same-origin", "same-site", "none"].includes(fetchSite)) {
    throw new WeReadPortError("FORBIDDEN", "拒绝跨站请求。", { status: 403 });
  }
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
