// Social Archive v0.0.0.7 / T08 — MAIN world ↔ background 的中继
//
// net-observer.js 跑在页面自己的 JS 世界（MAIN world）里，那里**没有** chrome.runtime，
// 所以它只能 window.postMessage。这个文件跑在扩展的隔离世界（ISOLATED world），
// 两边都够得着：收 postMessage，转 chrome.runtime.sendMessage。
//
// 为什么要分成两个文件而不是一个：
//   MAIN world 里的代码和页面共享全局对象——页面能看见它、也能改它。
//   所以那一侧只放"包一层 fetch 把响应抄出来"这一件事，不放任何凭据、
//   不放服务端地址、不放令牌。中继在这一侧，页面碰不到。
(() => {
  "use strict";

  const CHANNEL_KEY = "__socialArchiveNetRelay";
  if (window[CHANNEL_KEY]) return; // 幂等
  window[CHANNEL_KEY] = true;

  window.addEventListener("message", event => {
    // 只收本页面自己发的。event.source !== window 说明是 iframe 或别的窗口发来的，
    // 那不是我们注入的观察器。
    if (event.source !== window) return;
    const data = event.data;
    if (!data || data.__socialArchive !== true) return;

    if (data.type === "SA_RAW_RESPONSE") {
      chrome.runtime.sendMessage({
        type: "SA_NET_CAPTURE",
        url: String(data.url || ""),
        status: Number(data.status || 0),
        body: String(data.body || ""),
        capturedAt: String(data.captured_at || ""),
      }).catch(() => {
        // service worker 睡着时 sendMessage 会拒绝。这里静默——
        // 拦截**绝不允许**影响页面本身，这是 T08 的硬边界之一。
      });
      return;
    }

    if (data.type === "SA_OBSERVER_INSTALLED" || data.type === "SA_OBSERVER_READY") {
      chrome.runtime.sendMessage({
        type: "SA_NET_OBSERVER_STATE",
        state: data.type,
        prefixCount: Number(data.prefixCount || 0),
      }).catch(() => {});
    }
  });

  // 把 background 下发的 URL 前缀转给 MAIN world 的观察器。
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "SA_OBSERVER_CONFIGURE") return undefined;
    window.postMessage({
      __socialArchiveControl: true,
      type: "SA_OBSERVER_CONFIGURE",
      urlPrefixes: Array.isArray(message.urlPrefixes) ? message.urlPrefixes : [],
    }, window.location.origin);
    sendResponse({ ok: true });
    return true;
  });
})();
