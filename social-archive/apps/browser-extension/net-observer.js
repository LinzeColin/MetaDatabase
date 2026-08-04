// Social Archive v0.0.0.7 — MAIN world 响应拦截器（国内三源专用）
//
// 这个文件取代 v0.0.0.6 的 DOM 选择器抓取器。
//
// 它做什么：
//   在平台页面自己的 JS 世界里，把 window.fetch 与 XMLHttpRequest 包一层，
//   当页面自己去请求它自己的收藏列表接口时，把响应体原样抄一份出来。
//
// 它不做什么（硬边界）：
//   · 不合成请求。签名（小红书 x-s/x-t、抖音 a_bogus）由页面自己完成，我们碰都不碰。
//   · 不修改请求或响应。页面拿到的东西和我们不存在时一模一样。
//   · 不读取 Cookie。一个字节都不读。
//   · 不解析。解析在服务端用上游的字段约定做，这里只负责搬运。
//
// 为什么这样比 DOM 抓取强：
//   DOM 抓取依赖类名和结构，平台改一次版就全线崩，而且只能拿到页面渲染出来的那部分。
//   拦截拿到的是 API 原始 JSON —— 字段全、翻页游标现成、平台改版只要接口没动就不受影响。
//
// 注入方式（由 background 调用）：
//   chrome.scripting.executeScript({ target:{tabId}, world:"MAIN", files:["net-observer.js"] })
//   world:"MAIN" 自 Chrome 95 起支持；本扩展 minimum_chrome_version 已是 116。

(() => {
  "use strict";

  const CHANNEL = "__socialArchiveNetObserver";
  if (window[CHANNEL]) return; // 幂等：重复注入不重复包装
  window[CHANNEL] = { version: "0.0.0.7", matched: 0 };

  // 只对白名单前缀生效。由 background 在注入前通过 <script> data 属性或后续消息下发，
  // 这里给出默认值，实际以 configure 消息为准。
  // 注意：这些前缀必须来自真实抓包，不要凭印象写。首次运行时把命中的完整 URL
  // 记进 evidence，供 Build Agent 校正。
  let urlPrefixes = [];

  const post = (payload) => {
    // postMessage 是 MAIN world 与 content script 之间唯一的合法通道。
    window.postMessage({ __socialArchive: true, ...payload }, window.location.origin);
  };

  /** 把 fetch / XHR 拿到的地址补全成绝对地址再比对。
   *
   * **这一步原先没有，导致同源相对地址一律匹配不上。**
   * 实测（2026-08-04，真实 Chrome + 本地探针页）：页面每 1.2 秒
   * `fetch("/fav-list?page=N")` 一次，观察器自报 installed/ready 都为 true，
   * 而抓到的条数是 **0** —— 因为比对的是原始参数 `/fav-list?page=N`，
   * 里面根本不含域名。
   *
   * 而**同源相对地址正是各平台调自己接口的常规写法**，也就是说这条拦截路
   * 在真实平台上很可能一条都抓不到，且表现为「装好了、就绪了、什么也没有」。
   * 静态审查看不出这种问题：每一行单看都是对的。
   */
  const absolute = (url) => {
    if (!url) return url;
    try { return new URL(String(url), window.location.href).href; }
    catch (_) { return String(url); }
  };

  const shouldCapture = (url) => {
    if (!url || urlPrefixes.length === 0) return false;
    const full = absolute(url);
    return urlPrefixes.some((prefix) => full.includes(prefix) || String(url).includes(prefix));
  };

  const emit = (url, status, bodyText) => {
    window[CHANNEL].matched += 1;
    post({
      type: "SA_RAW_RESPONSE",
      url,
      status,
      // 原样字符串。服务端负责判断是不是 JSON、怎么解析。
      // 这里绝不 JSON.parse —— 解析失败会吞掉本来能救的数据。
      body: bodyText,
      captured_at: new Date().toISOString(),
    });
  };

  // ---- fetch ----
  const nativeFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await nativeFetch.apply(this, args);
    try {
      // 记录时也用绝对地址：报给开发者的那份清单要能直接看出是哪个接口。
      const url = absolute(typeof args[0] === "string" ? args[0] : args[0]?.url);
      if (shouldCapture(url)) {
        // clone() 是关键：直接读 response.body 会把流消费掉，页面就拿不到数据了。
        response
          .clone()
          .text()
          .then((text) => emit(url, response.status, text))
          .catch(() => {
            /* 读取失败不能影响页面，静默放过 */
          });
      }
    } catch (_) {
      /* 拦截逻辑任何异常都不允许影响页面本身 */
    }
    return response;
  };

  // ---- XMLHttpRequest ----
  const nativeOpen = XMLHttpRequest.prototype.open;
  const nativeSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__saUrl = absolute(url);
    return nativeOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener("load", () => {
      try {
        if (shouldCapture(this.__saUrl)) {
          // responseType 为 "" 或 "text" 时 responseText 可读；其他类型跳过而不是报错。
          const text =
            this.responseType === "" || this.responseType === "text"
              ? this.responseText
              : null;
          if (text) emit(this.__saUrl, this.status, text);
        }
      } catch (_) {
        /* 同上 */
      }
    });
    return nativeSend.apply(this, args);
  };

  // ---- 配置下发 ----
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data;
    if (!data || data.__socialArchiveControl !== true) return;
    if (data.type === "SA_OBSERVER_CONFIGURE" && Array.isArray(data.urlPrefixes)) {
      urlPrefixes = data.urlPrefixes;
      post({ type: "SA_OBSERVER_READY", prefixCount: urlPrefixes.length });
    }
  });

  post({ type: "SA_OBSERVER_INSTALLED" });
})();
