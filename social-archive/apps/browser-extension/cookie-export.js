// Social Archive v0.0.0.7 / T06 — 平台会话导出（仅西方三源）
//
// 采自任务包 03_PREBUILT/extension/cookie-export.js。**格式部分逐字保留**，
// 那是已实测过的部分（gallery-dl 1.32.9 与 yt-dlp 2026.7.4 都能完整读取）。
// 有两处按 CONFLICT_ORDER 做了改动，记在这里而不是悄悄改掉：
//
//   C-T06-01 模块形态：预制件用 ES `export`，而本扩展的 service worker 走
//     `importScripts`（MV3 里那要求 manifest 声明 "type":"module"，会牵动
//     整个后台脚本的加载方式）。改成与 shared.js / extension-utils.js 一致的
//     IIFE + globalThis，逻辑一行未动。
//
//   C-T06-02 上传端点：预制件写的是 `POST /v1/sources/{platform}/credential`
//     且 body 为 {kind, payload}；T05 已经落地的是
//     `PUT /v1/credentials/{platform}`、body 为 {cookies_txt}，并配套了
//     `DELETE /v1/credentials/{platform}` 做一键撤销。两者只是命名不同，
//     语义完全一致。选择保留 T05 的形状，因为撤销那一半已经按它建好并测过；
//     若改回预制件的路径，撤销端点会变成孤立的另一套命名。
//     预制件里被实测过的是**Cookie 格式**，不是端点路径。
//
// 硬边界（违反即架构违规）：
//   1. 只允许 ALLOWED_PLATFORMS 里的平台。国内平台的 Cookie 永远不出浏览器。
//   2. 只在用户点「连接」时读取，读完立即上传并丢弃，绝不写 chrome.storage。
//   3. 绝不打印、绝不 console.log 任何 cookie 的 value。
//
// 格式说明（这一段决定成败，不要改）：
//   Netscape cookies.txt 是 7 列 TAB 分隔：
//     domain <TAB> includeSubdomains <TAB> path <TAB> secure <TAB> expiry <TAB> name <TAB> value
//   · 首行必须是 "# Netscape HTTP Cookie File"，yt-dlp 会校验它
//   · includeSubdomains 取 TRUE 当且仅当 cookie 不是 hostOnly
//   · 会话 cookie（没有 expirationDate）expiry 写 0
//   · 【关键】httpOnly 的 cookie 按普通行写，不要加 curl 风格的 "#HttpOnly_" 前缀。
//     加了前缀的行以 # 开头，标准 MozillaCookieJar 会当注释丢掉，
//     而登录态几乎全在 httpOnly cookie 里 —— 那样会得到一个"格式正确但登录不上"的文件。
(() => {
  "use strict";

  const ALLOWED_PLATFORMS = Object.freeze({
    x: { domains: ["x.com", "twitter.com"] },
    instagram: { domains: ["instagram.com"] },
    youtube: { domains: ["youtube.com", "google.com"] },
  });

  // 这几个平台的 Cookie 永远不允许离开浏览器。
  const FORBIDDEN_PLATFORMS = new Set(["xiaohongshu", "douyin", "bilibili", "kuaishou"]);

  class CookieExportError extends Error {
    constructor(code, message) {
      super(message);
      this.code = code;
    }
  }

  function netscapeLine(cookie) {
    const includeSubdomains = cookie.hostOnly ? "FALSE" : "TRUE";
    const secure = cookie.secure ? "TRUE" : "FALSE";
    const expiry = cookie.expirationDate ? Math.floor(cookie.expirationDate) : 0;
    return [
      cookie.domain,
      includeSubdomains,
      cookie.path || "/",
      secure,
      String(expiry),
      cookie.name,
      cookie.value,
    ].join("\t");
  }

  /**
   * 读取某平台的会话并序列化。
   * @returns {Promise<{text: string, count: number, domains: string[]}>}
   * @throws {CookieExportError} NOT_LOGGED_IN | PLATFORM_FORBIDDEN | PERMISSION_DENIED
   */
  async function exportPlatformSession(platform) {
    if (FORBIDDEN_PLATFORMS.has(platform)) {
      throw new CookieExportError(
        "PLATFORM_FORBIDDEN",
        `${platform} 的登录状态不会离开你的浏览器，这个平台走浏览器内同步。`,
      );
    }
    const spec = ALLOWED_PLATFORMS[platform];
    if (!spec) {
      throw new CookieExportError("PLATFORM_UNKNOWN", `未知平台 ${platform}`);
    }

    const collected = [];
    const seen = new Set();
    for (const domain of spec.domains) {
      let cookies;
      try {
        cookies = await chrome.cookies.getAll({ domain });
      } catch (error) {
        // 权限没给到时 chrome 会抛，这里必须给出可读原因而不是空数组，
        // 否则上层会把"没权限"误判成"没登录"。
        throw new CookieExportError(
          "PERMISSION_DENIED",
          `浏览器没有授予读取 ${domain} 的权限。`,
        );
      }
      for (const cookie of cookies) {
        // 同一个 name 可能在多个 domain/path 下出现，按三元组去重而不是按 name。
        const key = `${cookie.domain}|${cookie.path}|${cookie.name}`;
        if (seen.has(key)) continue;
        seen.add(key);
        collected.push(cookie);
      }
    }

    if (collected.length === 0) {
      throw new CookieExportError(
        "NOT_LOGGED_IN",
        `没有在浏览器里找到 ${platform} 的登录状态。`,
      );
    }

    const text =
      "# Netscape HTTP Cookie File\n" +
      "# 由 Social Archive 生成，仅用于读取你自己的收藏。\n" +
      collected.map(netscapeLine).join("\n") +
      "\n";

    // 只回报条数和域名，永远不回报值。
    return { text, count: collected.length, domains: spec.domains };
  }

  /**
   * 读取并上传，然后立刻丢弃明文。
   * 调用方拿不到 text，避免它被顺手存进 storage 或打进日志。
   */
  async function connectPlatformSession(platform, { endpoint, token }) {
    const { text, count } = await exportPlatformSession(platform);
    let response;
    try {
      // 见 C-T06-02：端点用 T05 已落地的形状。
      response = await fetch(`${endpoint}/v1/credentials/${encodeURIComponent(platform)}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ cookies_txt: text }),
      });
    } finally {
      // 尽早断开引用。JS 里没法强制擦内存，但不留长生命周期引用是我们能做到的。
      // 注意这里没有任何 console 输出 —— 有意为之。
    }
    if (!response.ok) {
      // 400 是产品明确拒绝（例如国内平台），要把服务端那句中文透出来；
      // 其余状态统一说"连不上"，不把服务端细节泄给界面。
      let detail = "";
      if (response.status === 400) {
        detail = await response.json().then(body => String(body?.detail || "")).catch(() => "");
      }
      throw new CookieExportError(
        "UPLOAD_FAILED",
        detail || `暂时连不上服务器（${response.status}）。你的数据没有丢。`,
      );
    }
    return { count };
  }

  const api = Object.freeze({
    ALLOWED_PLATFORMS, FORBIDDEN_PLATFORMS, CookieExportError,
    netscapeLine, exportPlatformSession, connectPlatformSession,
  });
  globalThis.SACookieExport = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
