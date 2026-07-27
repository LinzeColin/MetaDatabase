import { DEFAULT_GATEWAY_ATTEMPTS, DEFAULT_GATEWAY_TIMEOUT_MS, MAX_GATEWAY_RESPONSE_BYTES, OFFICIAL_WEREAD_GATEWAY } from "./constants.js";
import { buildGatewayBody, validateUserKey } from "./contract.js";
import { UpgradeRequiredError, WeReadPortError } from "./errors.js";
import { abortableDelay, asObject, combineSignals, isPlainObject } from "./util.js";

/**
 * @param {{endpoint?:string,fetchImpl?:typeof fetch,timeoutMs?:number,maxAttempts?:number,maxResponseBytes?:number,mode?:"proxy"|"direct",delay?:(ms:number,signal?:AbortSignal)=>Promise<void>,random?:()=>number}} [options]
 */
export function createGatewayClient(options = {}) {
  const mode = options.mode ?? "proxy";
  const endpoint = options.endpoint ?? (mode === "proxy" ? "/api/weread/gateway" : OFFICIAL_WEREAD_GATEWAY);
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_GATEWAY_TIMEOUT_MS;
  const maxAttempts = Math.max(1, options.maxAttempts ?? DEFAULT_GATEWAY_ATTEMPTS);
  const maxBytes = options.maxResponseBytes ?? MAX_GATEWAY_RESPONSE_BYTES;
  const delay = options.delay ?? abortableDelay;
  const random = options.random ?? Math.random;

  /** @template T @param {string} apiName @param {Record<string,unknown>} parameters @param {{key:string,signal?:AbortSignal,attempts?:number}} callOptions @returns {Promise<T>} */
  async function call(apiName, parameters, callOptions) {
    const key = validateUserKey(callOptions.key);
    const request = buildGatewayBody(apiName, parameters);
    const attempts = Math.max(1, callOptions.attempts ?? maxAttempts);
    /** @type {unknown} */ let lastError;
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      if (callOptions.signal?.aborted) throw new WeReadPortError("CANCELLED", "操作已取消。", { cause: callOptions.signal.reason });
      const timeout = new AbortController();
      const timer = setTimeout(() => timeout.abort(new Error("微信读书接口请求超时")), timeoutMs);
      const signal = combineSignals(callOptions.signal, timeout.signal);
      try {
        const response = await fetchImpl(endpoint, {
          method: "POST",
          headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(request), signal, cache: "no-store", credentials: mode === "proxy" ? "same-origin" : "omit", redirect: "error",
        });
        const bytes = await readResponseBytes(response, maxBytes);
        let parsed;
        try { parsed = JSON.parse(new TextDecoder().decode(bytes)); }
        catch (error) { throw new WeReadPortError("SCHEMA", "微信读书接口返回了无法解析的 JSON。", { cause: error }); }
        if (!response.ok) throw classifyHttp(response.status, parsed);
        inspectBusinessResponse(parsed);
        return /** @type {T} */ (parsed);
      } catch (error) {
        lastError = normalizeFetchError(error, callOptions.signal, timeout.signal);
        if (!isRetryable(lastError) || attempt >= attempts) throw lastError;
        const base = Math.min(1_000, 120 * 2 ** (attempt - 1));
        await delay(base + Math.floor(random() * 40), callOptions.signal);
      } finally { clearTimeout(timer); }
    }
    throw normalizeFetchError(lastError, callOptions.signal, undefined);
  }
  return Object.freeze({ call, endpoint, mode });
}

/** Accept collector-style call input. @param {ReturnType<typeof createGatewayClient>} client */
export function createCollectorCaller(client) {
  return ({ key, apiName, params = {}, signal }) => client.call(apiName, params, { key, signal });
}

/** @param {unknown} value */
export function inspectBusinessResponse(value) {
  const object = asObject(value, "微信读书接口响应");
  const upgrade = isPlainObject(object.upgrade_info) ? object.upgrade_info : isPlainObject(object.data) && isPlainObject(object.data.upgrade_info) ? object.data.upgrade_info : undefined;
  if (upgrade) throw new UpgradeRequiredError(/** @type {Record<string,unknown>} */ (upgrade));
  const errcode = typeof object.errcode === "number" ? object.errcode : undefined;
  if (errcode !== undefined && errcode !== 0) {
    const message = typeof object.errmsg === "string" && object.errmsg.length <= 200 ? object.errmsg : "微信读书官方接口返回业务错误。";
    const code = new Set([-2012, -2001, 401, 403]).has(errcode) ? "AUTH" : new Set([-429, 429]).has(errcode) ? "RATE_LIMIT" : "UPSTREAM";
    throw new WeReadPortError(code, message, { errcode, retryable: code === "RATE_LIMIT" });
  }
}

/** @param {number} status @param {unknown} parsed */
function classifyHttp(status, parsed) {
  const object = isPlainObject(parsed) ? parsed : {};
  const upstreamMessage = typeof object.error === "string" && object.error.length <= 200 ? object.error : undefined;
  if (status === 401 || status === 403) return new WeReadPortError("AUTH", upstreamMessage ?? "微信读书密钥被拒绝。", { status });
  if (status === 429) return new WeReadPortError("RATE_LIMIT", upstreamMessage ?? "微信读书官方接口触发限流。", { status, retryable: true });
  return new WeReadPortError("UPSTREAM", upstreamMessage ?? `微信读书官方接口返回 HTTP ${status}。`, { status, retryable: [408, 425, 500, 502, 503, 504].includes(status) });
}
/** @param {unknown} error @param {AbortSignal|undefined} external @param {AbortSignal|undefined} timeout */
function normalizeFetchError(error, external, timeout) { if (error instanceof WeReadPortError || error instanceof UpgradeRequiredError) return error; if (external?.aborted) return new WeReadPortError("CANCELLED", "操作已取消。", { cause: external.reason }); if (timeout?.aborted) return new WeReadPortError("TIMEOUT", "微信读书官方接口请求超时。", { retryable: true, cause: error }); return new WeReadPortError("NETWORK", "无法连接微信读书官方接口。", { retryable: true, cause: error }); }
/** @param {unknown} error */
function isRetryable(error) { return error instanceof WeReadPortError && error.retryable; }
/** @param {Response} response @param {number} maxBytes */
async function readResponseBytes(response, maxBytes) { const declared = Number(response.headers.get("content-length") ?? "0"); if (Number.isFinite(declared) && declared > maxBytes) throw new WeReadPortError("TOO_LARGE", "微信读书官方接口响应超过安全上限。"); if (!response.body) { const bytes = new Uint8Array(await response.arrayBuffer()); if (bytes.byteLength > maxBytes) throw new WeReadPortError("TOO_LARGE", "微信读书官方接口响应超过安全上限。"); return bytes; } const reader = response.body.getReader(), chunks = []; let total = 0; while (true) { const { done, value } = await reader.read(); if (done) break; if (value) { total += value.byteLength; if (total > maxBytes) { await reader.cancel(); throw new WeReadPortError("TOO_LARGE", "微信读书官方接口响应超过安全上限。"); } chunks.push(value); } } const out = new Uint8Array(total); let offset = 0; for (const chunk of chunks) { out.set(chunk, offset); offset += chunk.byteLength; } return out; }
