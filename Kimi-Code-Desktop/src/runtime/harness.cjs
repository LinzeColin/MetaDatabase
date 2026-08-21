const http = require("node:http");

function fetchJson(url, maxBytes = 2 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: 1200 }, (response) => {
      if (response.statusCode !== 200) {
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
        try { resolve(JSON.parse(raw)); }
        catch (error) { reject(error); }
      });
    });
    request.once("timeout", () => request.destroy(new Error("Harness UI request timed out")));
    request.once("error", reject);
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

class HarnessBridge {
  constructor({ baseUrl = process.env.HARNESS_UI_URL, intervalMs = 15000 } = {}) {
    this.baseUrl = assertLoopbackBase(baseUrl);
    this.intervalMs = intervalMs;
    this.timer = null;
    this.window = null;
    this.lastKey = null;
  }

  attach(window) {
    this.stop();
    this.window = window;
    this.start();
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
    this.lastKey = null;
  }

  async refresh() {
    if (!this.window || this.window.isDestroyed()) return;
    const [catalog, state] = await Promise.all([
      fetchJson(`${this.baseUrl}/catalog.json`),
      fetchJson(`${this.baseUrl}/state.json`),
    ]);
    const entry = selectHarnessEntry(catalog, state);
    if (!entry) return;
    const key = `${entry.id}|${state.updated || 0}`;
    if (!entry.light || !entry.dark || key === this.lastKey) return;
    this.lastKey = key;
    const light = `url(${JSON.stringify(entry.light)})`;
    const dark = `url(${JSON.stringify(entry.dark)})`;
    await this.window.webContents.executeJavaScript(`(() => {
      document.documentElement.dataset.harnessUi = "active";
      document.documentElement.style.setProperty("--harness-scene", ${JSON.stringify(light)});
      document.documentElement.style.setProperty("--harness-scene-dark", ${JSON.stringify(dark)});
      return true;
    })()`);
  }
}

module.exports = { HarnessBridge, assertLoopbackBase, fetchJson, selectHarnessEntry };
