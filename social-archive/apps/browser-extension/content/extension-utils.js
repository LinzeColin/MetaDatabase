/**
 * 扩展通用工具 —— URL 规范化、ID 提取、Chrome 书签展平、分块、标签页挑选。
 *
 * ## 它为什么单独存在
 *
 * 这些函数原先住在 `content/account-mirror-core.js`（「账号镜像核心」）里，
 * 和 DOM 抓取器混在一个文件。名字听着像抓取的一部分，其实**一个都不是**：
 *
 *   · `flattenBookmarksTree` 读的是 `chrome.bookmarks.getTree()`，
 *      不碰任何页面 DOM——它是 T04 走通脊柱的第一个数据源
 *   · `canonicalUrl` / `externalId` / `relationFromUrl` 是 URL→语义的纯函数，
 *      无论内容是抓来的、拦截来的、还是服务端 gallery-dl 取来的，都要用它们去重
 *   · `chunk` / `preferExistingPlatformTab` 与内容来源完全无关
 *
 * 按 T03 的字面「删掉 account-mirror-core.js」会把这些一并删掉，
 * 于是 T04 的书签来源和 T08 的去重都得重造。所以先把它们搬出来，再删抓取器。
 *
 * ## 与 `content/extract-core.js` 的重名
 *
 * `extract-core.js` 里另有一个 `cleanText` 和一个 `canonicalUrl`，**不是重复**：
 * 那两个服务于「抓当前这一页的正文」，`canonicalUrl` 在那边是无参的
 * （取 `location.href` 的规范形式）。这里的 `canonicalUrl(value, base)` 收任意
 * URL 并剥掉追踪参数。两者语义不同，各自留在各自的文件里。
 */
(() => {
  "use strict";

  // 剥掉这些查询参数后，同一条内容在不同分享链路下会收敛成同一个 URL。
  // 少剥一个，去重就会漏；`xsec_token` 是小红书分享链接里每次都变的那个。
  const TRACKING_KEYS = new Set([
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "share_from_user_hidden", "xsec_source", "xsec_token"
  ]);

  // 各平台内容 ID 在 URL 路径里的位置。这是 URL 结构，不是 DOM 结构——
  // 页面改版不影响它，换成 API 拦截也照样要用它算 external_content_id。
  const CONTENT_ID_PATTERNS = Object.freeze({
    xiaohongshu: /\/(?:explore|discovery\/item)\/([a-zA-Z0-9_-]+)/,
    douyin: /\/(?:video|note)\/(\d+)/,
    kuaishou: /\/(?:short-video|photo)\/([a-zA-Z0-9_-]+)/,
    bilibili: /\/video\/(BV[a-zA-Z0-9]+|av\d+)/i,
    x: /\/[^/]+\/status\/(\d+)/,
    reddit: /\/comments\/([a-z0-9]+)/i,
    instagram: /\/(?:p|reel|tv)\/([a-zA-Z0-9_-]+)/
  });

  function cleanText(value, max = 4000) {
    return String(value || "").replace(/\s+/g, " ").trim().slice(0, max);
  }

  function safeIso(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number <= 0) return null;
    const date = new Date(number);
    return Number.isNaN(date.getTime()) ? null : date.toISOString();
  }

  function canonicalUrl(value, base) {
    try {
      const effectiveBase = base || (typeof location !== "undefined" ? location.href : undefined);
      const url = new URL(String(value || ""), effectiveBase);
      if (!/^https?:$/.test(url.protocol)) return "";
      url.hash = "";
      for (const key of [...url.searchParams.keys()]) {
        if (TRACKING_KEYS.has(key) || key.startsWith("utm_")) url.searchParams.delete(key);
      }
      return url.toString();
    } catch (_) { return ""; }
  }

  function externalId(platform, url) {
    try {
      const path = new URL(url).pathname;
      // 认不出来就退回整个 URL——宁可去重粒度粗一点，也不要返回空串，
      // 空串会让不同内容撞成同一个 key，是"静默丢数据"。
      return path.match(CONTENT_ID_PATTERNS[platform])?.[1] || url;
    } catch (_) { return url; }
  }

  function relationFromUrl(platform, value) {
    const url = String(value || "").toLowerCase();
    if (platform === "x") return url.includes("bookmark") ? "bookmark" : "like";
    if (platform === "reddit") return url.includes("upvoted") ? "upvoted" : "saved";
    if (platform === "bilibili") {
      if (url.includes("watchlater")) return "watch_later";
      if (url.includes("history")) return "history";
      if (url.includes("fav")) return "favorite";
      return "like";
    }
    if (platform === "instagram") return "saved";
    return url.includes("like") || url.includes("liked") ? "like" : "favorite";
  }

  function flattenBookmarksTree(nodes) {
    const records = [];
    function walk(node, folders) {
      const title = cleanText(node?.title || "", 256);
      if (node?.url) {
        const url = canonicalUrl(node.url);
        if (url) records.push({
          platform: "generic-web", url, external_content_id: `chrome-bookmark:${node.id}`,
          relation_type: "bookmark", collection_key: folders.filter(Boolean).join(" / ").slice(0, 512),
          collection_name: folders.filter(Boolean).join(" / ").slice(0, 512), title: title || url, text: title || null,
          relation_observed_at: safeIso(node.dateAdded) || new Date().toISOString(), media_urls: [],
          raw_metadata: { capture_source: "chrome_bookmarks", chrome_bookmark_id: String(node.id || ""), parent_id: String(node.parentId || ""), folder_path: folders.filter(Boolean) },
          requested_levels: ["L0", "L1", "L3"], destination_ids: ["social_archive", "markdown"]
        });
        return;
      }
      const next = title ? [...folders, title] : folders;
      for (const child of node?.children || []) walk(child, next);
    }
    for (const node of nodes || []) walk(node, []);
    return records;
  }

  function chunk(items, size = 200) {
    const output = [];
    for (let index = 0; index < items.length; index += size) output.push(items.slice(index, index + size));
    return output;
  }

  function preferExistingPlatformTab(tabs, preferredTabId = null) {
    const candidates = (Array.isArray(tabs) ? tabs : []).filter(tab => Number.isInteger(tab?.id));
    const preferred = candidates.find(tab => String(tab.id) === String(preferredTabId));
    return preferred || candidates.find(tab => tab.active === true) || candidates[0] || null;
  }

  const api = Object.freeze({
    TRACKING_KEYS, CONTENT_ID_PATTERNS,
    cleanText, safeIso, canonicalUrl, externalId, relationFromUrl,
    flattenBookmarksTree, chunk, preferExistingPlatformTab
  });
  globalThis.SAExtensionUtils = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
