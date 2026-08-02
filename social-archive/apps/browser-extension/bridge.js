(() => {
  "use strict";

  const PAGE_SOURCE = "social-archive-web";
  const EXTENSION_SOURCE = "social-archive-extension";
  const allowedOrigins = new Set([
    "https://social-archive.linzezhang.com",
    "http://127.0.0.1:8765",
    "http://localhost:8765",
    "http://127.0.0.1:18765",
    "http://localhost:18765"
  ]);

  if (!allowedOrigins.has(location.origin)) return;

  function post(type, payload = {}) {
    window.postMessage({ source: EXTENSION_SOURCE, type, ...payload }, location.origin);
  }

  window.addEventListener("message", event => {
    if (event.source !== window || event.origin !== location.origin) return;
    const message = event.data || {};
    if (message.source !== PAGE_SOURCE) return;

    if (message.type === "SA_PING") {
      chrome.runtime.sendMessage({ type: "SA_WEB_BRIDGE_STATUS" })
        .then(result => post("SA_PONG", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_PONG", { requestId: message.requestId, detected: true, paired: false, error: error?.message || "插件状态读取失败" }));
      return;
    }

    if (message.type === "SA_CONFIGURE") {
      chrome.runtime.sendMessage({ type: "SA_WEB_BRIDGE_CONFIGURE", endpoint: message.endpoint, libraryUrl: message.libraryUrl })
        .then(result => post("SA_PAIR_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_PAIR_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "连接失败" }));
      return;
    }

    if (message.type === "SA_PAIR") {
      chrome.runtime.sendMessage({ type: "SA_WEB_BRIDGE_PAIR", code: message.code, endpoint: message.endpoint })
        .then(result => post("SA_PAIR_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_PAIR_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "配对失败" }));
      return;
    }

    if (message.type === "SA_OPEN_OPTIONS") {
      chrome.runtime.sendMessage({ type: "SA_OPEN_OPTIONS" })
        .then(result => post("SA_OPTIONS_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_OPTIONS_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "无法打开设置" }));
    }
  });

  post("SA_BRIDGE_READY", { version: chrome.runtime.getManifest().version });
})();
