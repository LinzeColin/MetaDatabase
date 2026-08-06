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

    // v0.0.0.7 / T03 收尾：这里原先转发 SA_CONFIGURE → SA_WEB_BRIDGE_CONFIGURE，
    // 让页面下发 endpoint 与 libraryUrl 写进扩展配置。**已整条删除。**
    //
    // 删的理由不是"没人用"，是它和二十行之后那条规则直接冲突：
    // SA_WEB_BRIDGE_ADOPT_TOKEN 明写「服务地址取扩展自己的托管配置，不接受页面
    // 下发——页面能改端点就等于任何拿到桥的页面都能把上行改到别处去」。
    // 而这条转发做的正是那件事。桥注入在档案馆页面上，同源的任何脚本都能发它。
    //
    // 没人发它只说明**今天**没被用到，不等于用不了。端点由 setConfig 托管，
    // 采纳令牌那条路（SA_ADOPT_TOKEN）已经覆盖了真实的连接流程。
    // v0.0.0.7 / T03：原先这里转发用户手抄的一次性码（SA_PAIR）。
    // 现在转发的是**已登录页面替扩展取到的长期令牌**——页面用自己的会话
    // 调 /v1/auth/extension-token 换来，用户一个字符都不输入。
    if (message.type === "SA_ADOPT_TOKEN") {
      chrome.runtime.sendMessage({
        type: "SA_WEB_BRIDGE_ADOPT_TOKEN",
        token: message.token,
        endpoint: message.endpoint,
        libraryUrl: message.libraryUrl
      })
        .then(result => post("SA_ADOPT_TOKEN_RESULT", { requestId: message.requestId, ...(result || {}) }))
        .catch(error => post("SA_ADOPT_TOKEN_RESULT", { requestId: message.requestId, ok: false, message: error?.message || "连接失败" }));
      return;
    }

    if (message.type === "SA_ACCOUNT_CONNECT") {
      // **这条路拿不到权限，所以它不做连接，只把人送到做得到的地方。**
      //
      // 连接账号要先拿到平台权限（主机 / bookmarks / cookies），而
      // `chrome.permissions.request` 有两条硬要求：要有用户手势，
      // 而且**内容脚本里根本没有 permissions API**。这里是档案馆网页上的
      // 内容脚本，两条都不满足——转发给 background 也没用，
      // 手势不会跨过 sendMessage 那道边界（实测三种权限全抛
      // "This function must be called during a user gesture"）。
      //
      // 所以这颗按钮原来是**结构上不可能成功**的。改成打开插件的账号页：
      // 那是一个扩展页面，点击手势和 permissions API 都在那儿。
      chrome.runtime.sendMessage({ type: "SA_OPEN_ACCOUNT_CENTER" })
        .then(() => post("SA_ACCOUNT_CONNECT_RESULT", { requestId: message.requestId, ok: true,
          message: "已打开插件的账号页——请在那一页点「连接账号」，浏览器会弹出授权框。" }))
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
