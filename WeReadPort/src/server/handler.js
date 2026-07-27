import {
  APP_NAME,
  APP_VERSION,
  DEFAULT_GATEWAY_TIMEOUT_MS,
  MAX_GATEWAY_REQUEST_BYTES,
  MAX_GATEWAY_RESPONSE_BYTES,
  OFFICIAL_WEREAD_GATEWAY,
  SOURCE_SKILL_VERSION,
} from "../core/constants.js";
import { parseProxyBody, validateUserKey } from "../core/contract.js";
import { WeReadPortError, toSafeFailure } from "../core/errors.js";
import { combineSignals } from "../core/util.js";

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
  try {
    if (url.pathname === "/healthz" || url.pathname === "/readyz") {
      return secure(json({ ok: true, app: APP_NAME, version: APP_VERSION }));
    }
    if (url.pathname === "/api/version") {
      return secure(json({ app: APP_NAME, appVersion: APP_VERSION, sourceSkillVersion: SOURCE_SKILL_VERSION }));
    }
    if (url.pathname === "/api/weread/gateway") {
      if (request.method === "OPTIONS") return secure(new Response(null, { status: 204, headers: { Allow: "POST, OPTIONS" } }));
      return secure(await proxyGateway(request, env));
    }
    if (url.pathname.startsWith("/api/")) {
      return secure(json({ error: { code: "NOT_FOUND", message: "接口不存在。" } }, 404));
    }
    if (!env.ASSETS || typeof env.ASSETS.fetch !== "function") {
      return secure(new Response("静态资源绑定不可用。", { status: 503 }));
    }
    return secure(await env.ASSETS.fetch(request));
  } catch (error) {
    const safe = toSafeFailure(error);
    const status = error instanceof WeReadPortError && error.status ? error.status : 500;
    return secure(json({ error: safe }, status));
  }
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

/** @param {Response} response */
function secure(response) {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) headers.set(name, value);
  if (!headers.has("Cache-Control")) headers.set("Cache-Control", "no-cache");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}
