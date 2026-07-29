const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);
const IDEMPOTENT_METHODS = new Set(["GET", "HEAD", "PUT", "DELETE", "OPTIONS"]);

export async function fetchWithPolicy(fetchImpl, url, init = {}, options = {}) {
  const method = String(init.method || "GET").toUpperCase();
  const timeoutMs = boundedNumber(options.timeoutMs, 15_000, 500, 120_000);
  const attempts = boundedNumber(options.attempts, 1, 1, 3);
  const retryAllowed = options.retry === true || (options.retry !== false && IDEMPOTENT_METHODS.has(method));
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const controller = new AbortController();
    const detach = forwardAbort(init.signal, controller);
    const timer = setTimeout(() => controller.abort(new Error("上游请求超时。")), timeoutMs);
    try {
      const response = await fetchImpl(url, { ...init, signal: controller.signal, redirect: init.redirect || "manual" });
      if (attempt < attempts && retryAllowed && RETRYABLE_STATUS.has(response.status)) {
        await discardBody(response);
        await sleep(retryDelay(response, attempt, options.maxRetryDelayMs));
        continue;
      }
      return response;
    } catch (error) {
      lastError = error;
      const timedOut = controller.signal.aborted && !init.signal?.aborted;
      if (timedOut) lastError = Object.assign(new Error("上游请求超时。"), { code: "UPSTREAM_TIMEOUT" });
      if (attempt >= attempts || !retryAllowed || init.signal?.aborted) throw lastError;
      await sleep(retryDelay(null, attempt, options.maxRetryDelayMs));
    } finally {
      clearTimeout(timer);
      detach();
    }
  }
  throw lastError || new Error("上游请求失败。");
}

function forwardAbort(signal, controller) {
  if (!signal) return () => {};
  if (signal.aborted) controller.abort(signal.reason);
  const listener = () => controller.abort(signal.reason);
  signal.addEventListener("abort", listener, { once: true });
  return () => signal.removeEventListener("abort", listener);
}

function retryDelay(response, attempt, maxRaw = 2_000) {
  const max = boundedNumber(maxRaw, 2_000, 0, 10_000);
  const header = response?.headers?.get?.("retry-after");
  if (header) {
    const seconds = Number(header);
    if (Number.isFinite(seconds)) return Math.min(max, Math.max(0, seconds * 1000));
    const timestamp = Date.parse(header);
    if (Number.isFinite(timestamp)) return Math.min(max, Math.max(0, timestamp - Date.now()));
  }
  return Math.min(max, 150 * (2 ** (attempt - 1)));
}

async function discardBody(response) {
  try { await response.arrayBuffer(); } catch { /* response body can already be unavailable */ }
}

function sleep(ms) { return ms > 0 ? new Promise(resolve => setTimeout(resolve, ms)) : Promise.resolve(); }
function boundedNumber(value, fallback, min, max) {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, Math.floor(parsed))) : fallback;
}
