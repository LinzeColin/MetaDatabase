const http = require("node:http");

function requestJson(url, options = {}, maxBytes = 2 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const request = http.request(url, { timeout: 1200, ...options }, (response) => {
      if (response.statusCode < 200 || response.statusCode >= 300) {
        response.resume();
        reject(new Error(`Harness UI returned HTTP ${response.statusCode}`));
        return;
      }
      let raw = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        raw += chunk;
        if (raw.length > maxBytes) request.destroy(new Error("Harness UI response is too large"));
      });
      response.on("end", () => {
        if (response.statusCode === 204 || !raw) { resolve(null); return; }
        try { resolve(JSON.parse(raw)); }
        catch (error) { reject(error); }
      });
    });
    request.once("timeout", () => request.destroy(new Error("Harness UI request timed out")));
    request.once("error", reject);
    if (options.body) request.write(options.body);
    request.end();
  });
}

function fetchJson(url, maxBytes) {
  return requestJson(url, { method: "GET", headers: { "Cache-Control": "no-cache" } }, maxBytes);
}

function postJson(url, value) {
  const body = JSON.stringify(value);
  return requestJson(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Content-Length": Buffer.byteLength(body),
    },
    body,
  });
}

function selectHarnessEntry(catalog, state) {
  const entries = Array.isArray(catalog?.entries) ? catalog.entries : [];
  return entries.find((entry) => entry.id === state?.selected) || entries[0] || null;
}

function assertLoopbackBase(raw) {
  const url = new URL(raw || "http://127.0.0.1:3099");
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
    throw new Error("HARNESS_UI_URL must point to a loopback HTTP service");
  }
  return url.origin;
}

function assetWithRevision(raw, generated) {
  if (!raw || raw.includes("?v=") || !generated) return raw || "";
  return `${raw}?v=${encodeURIComponent(generated)}`;
}

function catalogNeedsRefresh(nextState, currentCatalog) {
  if (!currentCatalog || !nextState?.catalogGenerated) return true;
  return nextState.catalogGenerated !== currentCatalog.generated;
}

class HarnessBridge {
  constructor({ baseUrl = process.env.HARNESS_UI_URL, intervalMs = 1000, onChange = null } = {}) {
    this.baseUrl = assertLoopbackBase(baseUrl);
    this.intervalMs = intervalMs;
    this.onChange = onChange;
    this.timer = null;
    this.window = null;
    this.catalog = null;
    this.state = null;
    this.online = false;
    this.error = null;
    this.lastAppliedKey = null;
    this.lastNoticeKey = null;
  }

  snapshot() {
    return {
      catalog: this.catalog || { count: 0, entries: [] },
      state: this.state || {},
      online: this.online,
      error: this.error,
    };
  }

  attach(window) {
    this.window = window;
    this.lastAppliedKey = null;
    this.start();
    this.refresh().catch(() => {});
  }

  detach(window) {
    if (!window || this.window === window) this.window = null;
    this.lastAppliedKey = null;
  }

  start() {
    if (this.timer) return;
    this.refresh().catch(() => {});
    this.timer = setInterval(() => this.refresh().catch(() => {}), this.intervalMs);
    this.timer.unref?.();
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.window = null;
    this.lastAppliedKey = null;
  }

  async patch(values) {
    const state = await postJson(`${this.baseUrl}/api/state`, values);
    const forceCatalog = Boolean(state.catalogGenerated) && state.catalogGenerated !== this.catalog?.generated;
    return this.refresh({ forceCatalog, suppliedState: state });
  }

  async next() {
    const state = await postJson(`${this.baseUrl}/api/next`, {});
    const forceCatalog = Boolean(state.catalogGenerated) && state.catalogGenerated !== this.catalog?.generated;
    return this.refresh({ forceCatalog, suppliedState: state });
  }

  async refreshCatalog() {
    await postJson(`${this.baseUrl}/api/catalog/refresh`, {});
    return this.refresh({ forceCatalog: true });
  }

  async refresh({ forceCatalog = false, suppliedState = null } = {}) {
    try {
      const nextState = suppliedState || await fetchJson(`${this.baseUrl}/state.json`);
      const nextCatalog = forceCatalog || catalogNeedsRefresh(nextState, this.catalog)
        ? await fetchJson(`${this.baseUrl}/catalog.json`)
        : this.catalog;
      this.catalog = nextCatalog;
      this.state = nextState;
      this.online = true;
      this.error = null;
      await this.applyCurrent();
      this.notify();
      return this.snapshot();
    } catch (error) {
      this.online = false;
      this.error = error.message;
      this.notify();
      throw error;
    }
  }

  async applyCurrent() {
    const window = this.window;
    if (!window || window.isDestroyed()) return;
    const entry = selectHarnessEntry(this.catalog, this.state);
    if (!entry) return;
    const key = `${this.catalog?.generated || ""}|${entry.id}|${this.state?.updated || 0}`;
    if (!entry.light || !entry.dark || key === this.lastAppliedKey) return;
    const light = `url(${JSON.stringify(assetWithRevision(entry.light, this.catalog?.generated))})`;
    const dark = `url(${JSON.stringify(assetWithRevision(entry.dark, this.catalog?.generated))})`;
    await window.webContents.executeJavaScript(`(() => {
      document.documentElement.dataset.harnessUi = "active";
      document.documentElement.style.setProperty("--harness-scene", ${JSON.stringify(light)});
      document.documentElement.style.setProperty("--harness-scene-dark", ${JSON.stringify(dark)});
      return true;
    })()`);
    this.lastAppliedKey = key;
  }

  notify() {
    const key = `${this.online}|${this.error || ""}|${this.catalog?.generated || ""}|${this.state?.updated || 0}`;
    if (key === this.lastNoticeKey) return;
    this.lastNoticeKey = key;
    this.onChange?.(this.snapshot());
  }
}

module.exports = {
  HarnessBridge,
  assertLoopbackBase,
  assetWithRevision,
  catalogNeedsRefresh,
  fetchJson,
  postJson,
  selectHarnessEntry,
};
