(() => {
  "use strict";

  const PAGE_SOURCE = "social-archive-web";
  const EXTENSION_SOURCE = "social-archive-extension";
  const allowedOrigins = new Set([
    "https://social-archive.linzezhang.com",
    "http://127.0.0.1:8765",
    "http://localhost:8765"
  ]);
  const BRIDGE_STATE_KEY = "__socialArchiveExtensionBridgeState";
  const bridgeVersion = chrome.runtime.getManifest().version;

  if (!allowedOrigins.has(location.origin)) return;

  function post(type, payload = {}) {
    window.postMessage({ source: EXTENSION_SOURCE, type, ...payload }, location.origin);
  }

  const existing = globalThis[BRIDGE_STATE_KEY];
  if (existing?.version === bridgeVersion && typeof existing.announce === "function") {
    existing.announce();
    return;
  }
  if (typeof existing?.listener === "function") {
    window.removeEventListener("message", existing.listener);
  }

  const onMessage = event => {
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

    if (message.type === "SA_ACCOUNT_CONNECT") {
      chrome.runtime.sendMessage({ type: "SA_ACCOUNT_CONNECT", platform: message.platform })
        .then(result => post("SA_ACCOUNT_CONNECT_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_ACCOUNT_CONNECT_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "无法连接账号" }));
      return;
    }

    if (message.type === "SA_SYNC_ACCOUNT") {
      chrome.runtime.sendMessage({ type: "SA_SYNC_ACCOUNT", accountId: message.accountId })
        .then(result => post("SA_SYNC_ACCOUNT_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_SYNC_ACCOUNT_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "无法启动账号同步" }));
      return;
    }

    if (message.type === "SA_SYNC_ALL_ACCOUNTS") {
      chrome.runtime.sendMessage({ type: "SA_SYNC_ALL_ACCOUNTS" })
        .then(result => post("SA_SYNC_ALL_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_SYNC_ALL_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "无法启动同步" }));
      return;
    }

    if (message.type === "SA_CONTROL_SYNC_RUN") {
      chrome.runtime.sendMessage({
        type: "SA_CONTROL_SYNC_RUN",
        syncRunId: message.syncRunId,
        accountId: message.accountId,
        action: message.action
      })
        .then(result => post("SA_CONTROL_SYNC_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_CONTROL_SYNC_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "无法控制同步任务" }));
      return;
    }

    if (message.type === "SA_OPEN_OPTIONS") {
      chrome.runtime.sendMessage({ type: "SA_OPEN_OPTIONS" })
        .then(result => post("SA_OPTIONS_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_OPTIONS_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "无法打开设置" }));
    }
  };

  const announce = () => post("SA_BRIDGE_READY", { version: bridgeVersion });
  globalThis[BRIDGE_STATE_KEY] = { version: bridgeVersion, listener: onMessage, announce };
  window.addEventListener("message", onMessage);

  announce();
})();
