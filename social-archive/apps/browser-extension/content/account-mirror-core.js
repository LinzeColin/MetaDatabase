(() => {
  "use strict";

  const PLATFORM_SPECS = Object.freeze({
    xiaohongshu: {
      label: "小红书", relations: ["favorite", "like"],
      home: "https://www.xiaohongshu.com/explore",
      relationUrls: { favorite: "https://www.xiaohongshu.com/user/profile", like: "https://www.xiaohongshu.com/user/profile" },
      contentPatterns: [/\/(?:explore|discovery\/item)\/[a-zA-Z0-9_-]+/],
      collectionText: /收藏夹|合集|专辑/i,
      // Favorites and likes share the profile route. The browser must confirm
      // the selected tab before it can label a page as either relation.
      relationTabMatchers: {
        favorite: [/^收藏$/, /收藏夹/],
        like: [/^赞过$/, /^喜欢$/, /点赞/]
      }
    },
    douyin: {
      label: "抖音", relations: ["favorite", "like"],
      home: "https://www.douyin.com/",
      relationUrls: { favorite: "https://www.douyin.com/user/self?showTab=collection", like: "https://www.douyin.com/user/self?showTab=like" },
      contentPatterns: [/\/video\/\d+/],
      collectionText: /收藏夹|合集|专辑/i
    },
    kuaishou: {
      label: "快手", relations: ["favorite", "like"],
      home: "https://www.kuaishou.com/",
      relationUrls: { favorite: "https://www.kuaishou.com/profile", like: "https://www.kuaishou.com/profile" },
      contentPatterns: [/\/short-video\/[a-zA-Z0-9_-]+/],
      collectionText: /收藏夹|合集|专辑/i
    },
    bilibili: {
      label: "B站", relations: ["favorite", "watch_later", "history", "like"],
      home: "https://www.bilibili.com/",
      relationUrls: {
        favorite: "https://space.bilibili.com/0/favlist",
        watch_later: "https://www.bilibili.com/watchlater/list",
        history: "https://www.bilibili.com/account/history",
        like: "https://space.bilibili.com/0"
      },
      contentPatterns: [/\/video\/(?:BV[a-zA-Z0-9]+|av\d+)/i],
      collectionText: /收藏夹|收藏|稍后再看|合集/i
    },
    x: {
      label: "X", relations: ["bookmark", "like"],
      home: "https://x.com/home",
      relationUrls: { bookmark: "https://x.com/i/bookmarks", like: "https://x.com/home" },
      contentPatterns: [/\/[^/]+\/status\/\d+/],
      collectionText: /folder|bookmark folder|书签文件夹/i
    },
    reddit: {
      label: "Reddit", relations: ["saved", "upvoted"],
      home: "https://www.reddit.com/",
      relationUrls: { saved: "https://www.reddit.com/user/me/saved/", upvoted: "https://www.reddit.com/user/me/upvoted/" },
      contentPatterns: [/\/comments\/[a-z0-9]+/i],
      collectionText: /collection|saved folder/i
    },
    instagram: {
      label: "Instagram", relations: ["saved"],
      home: "https://www.instagram.com/",
      relationUrls: { saved: "https://www.instagram.com/your_activity/saved/" },
      contentPatterns: [/\/(?:p|reel|tv)\/[a-zA-Z0-9_-]+/],
      collectionText: /collection|saved collection|收藏/i
    }
  });

  const END_TEXT = /(?:没有更多|到底了|全部加载|已显示全部|已经到底|暂无更多|no more|you(?:'|’)re all caught up|end of (?:the )?list|nothing else to show)/i;
  const LOGIN_TEXT = /(?:登录|扫码登录|手机号登录|log in|sign in|continue with)/i;
  const TOTAL_TEXT = /(?:共|全部|总计|total)?\s*([\d,.]+)\s*(?:条|个|项|篇|收藏|帖子|笔记|视频|items?|posts?|saved)/i;
  const TRACKING_KEYS = new Set(["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "spm", "share_from_user_hidden", "xsec_source", "xsec_token"]);

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
      const patterns = {
        xiaohongshu: /\/(?:explore|discovery\/item)\/([a-zA-Z0-9_-]+)/,
        douyin: /\/video\/(\d+)/,
        kuaishou: /\/short-video\/([a-zA-Z0-9_-]+)/,
        bilibili: /\/video\/(BV[a-zA-Z0-9]+|av\d+)/i,
        x: /\/[^/]+\/status\/(\d+)/,
        reddit: /\/comments\/([a-z0-9]+)/i,
        instagram: /\/(?:p|reel|tv)\/([a-zA-Z0-9_-]+)/
      };
      return path.match(patterns[platform])?.[1] || url;
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

  function relationTabIsActive(node) {
    const attr = key => String(node?.getAttribute?.(key) || "").toLowerCase();
    if (attr("aria-selected") === "true") return true;
    if (["page", "step", "location", "true"].includes(attr("aria-current"))) return true;
    if (["active", "selected", "current", "true"].includes(attr("data-state"))) return true;
    if (["active", "selected", "current", "true"].includes(attr("data-active"))) return true;
    return /(?:^|\s)(?:active|selected|current)(?:\s|$)/i.test(String(node?.className || ""));
  }

  function ensureRelationScope(platform, relationType, root = document, { allowClick = true } = {}) {
    const spec = PLATFORM_SPECS[platform];
    const matchers = spec?.relationTabMatchers?.[relationType] || [];
    // Platforms with route-specific relations are already scoped by their URL.
    if (!matchers.length) return { confirmed: true, reason: "ROUTE_SCOPED", clicked: false };
    const tabs = [...(root?.querySelectorAll?.("button,a,[role='tab'],[role='button'],[data-e2e*='tab'],[data-testid*='tab'],[class*='tab']") || [])]
      .filter(node => {
        const text = cleanText(node.textContent || node.getAttribute?.("aria-label") || node.title || "", 128);
        return matchers.some(matcher => matcher.test(text));
      });
    const selected = tabs.find(relationTabIsActive);
    if (selected) return { confirmed: true, reason: "TAB_ALREADY_SELECTED", clicked: false };
    const target = tabs[0];
    if (!target) return { confirmed: false, reason: "RELATION_TAB_NOT_FOUND", clicked: false };
    if (!allowClick || typeof target.click !== "function") {
      return { confirmed: false, reason: "RELATION_TAB_SELECTION_UNCONFIRMED", clicked: false };
    }
    target.click();
    if (relationTabIsActive(target)) return { confirmed: true, reason: "TAB_SELECTED", clicked: true };
    return { confirmed: false, reason: "RELATION_TAB_SELECTION_UNCONFIRMED", clicked: true };
  }

  function collectionFromElement(anchor, fallback = "") {
    const card = anchor?.closest?.("article,li,[role='listitem'],[data-e2e*='card'],[class*='card'],[class*='item']");
    const region = card?.closest?.("section,[role='region'],[aria-label]");
    const labelled = region?.querySelector?.("h1,h2,h3,[role='heading'],[aria-label]");
    const breadcrumb = anchor?.closest?.("main,section")?.querySelector?.("nav[aria-label*='breadcrumb'],[class*='breadcrumb']");
    return cleanText(labelled?.textContent || labelled?.getAttribute?.("aria-label") || breadcrumb?.textContent || fallback, 256);
  }

  function discoverCollectionScopes(platform, root = document) {
    const spec = PLATFORM_SPECS[platform];
    if (!spec || !root?.querySelectorAll) return [];
    const current = canonicalUrl(typeof location !== "undefined" ? location.href : "");
    const currentHost = (() => { try { return new URL(current).hostname; } catch (_) { return ""; } })();
    const found = new Map();
    for (const anchor of root.querySelectorAll("a[href]")) {
      const text = cleanText(anchor.textContent || anchor.getAttribute?.("aria-label") || anchor.title || "", 256);
      if (!spec.collectionText?.test(text)) continue;
      const url = canonicalUrl(anchor.href, current || undefined);
      if (!url || url === current) continue;
      let parsed;
      try { parsed = new URL(url); } catch (_) { continue; }
      if (currentHost && parsed.hostname !== currentHost && !parsed.hostname.endsWith(`.${currentHost}`)) continue;
      if (spec.contentPatterns.some(pattern => pattern.test(parsed.pathname))) continue;
      const key = `${platform}:${parsed.pathname}${parsed.search}`.slice(0, 512);
      if (!found.has(key)) found.set(key, { collectionKey: key, collectionName: text || "未命名收藏夹", url });
    }
    return [...found.values()].slice(0, 100);
  }

  function extractCandidates(platform, root = document, options = {}) {
    const spec = PLATFORM_SPECS[platform];
    if (!spec || !root?.querySelectorAll) return [];
    const seen = new Map();
    const currentUrl = canonicalUrl(typeof location !== "undefined" ? location.href : options.pageUrl || "");
    for (const anchor of root.querySelectorAll("a[href]")) {
      const url = canonicalUrl(anchor.href, currentUrl || undefined);
      if (!url) continue;
      let path = "";
      try { path = new URL(url).pathname; } catch (_) { continue; }
      if (!spec.contentPatterns.some(pattern => pattern.test(path))) continue;
      const card = anchor.closest?.("article,li,[role='listitem'],[data-e2e*='card'],[class*='card'],[class*='item']") || anchor;
      const title = cleanText(anchor.getAttribute?.("aria-label") || anchor.title || card.querySelector?.("h1,h2,h3,[title]")?.textContent || anchor.textContent || "", 2048);
      const text = cleanText(card.innerText || card.textContent || title, 20000);
      const author = cleanText(card.querySelector?.("[data-e2e*='author'],[class*='author'],[class*='user'],a[href*='/user/'],a[href*='/profile/']")?.textContent || "", 1024);
      const media = [...(card.querySelectorAll?.("img[src],video[src],source[src]") || [])]
        .map(node => canonicalUrl(node.currentSrc || node.src, currentUrl || undefined)).filter(Boolean).slice(0, 20);
      const collection = cleanText(options.collectionName || collectionFromElement(anchor, options.collectionKey || ""), 256);
      const key = externalId(platform, url);
      if (!seen.has(key)) {
        seen.set(key, {
          platform, url, external_content_id: key,
          title: title || null, author_name: author || null, text: text || null,
          relation_type: options.relationType || relationFromUrl(platform, currentUrl),
          relation_observed_at: new Date().toISOString(),
          collection_key: options.collectionKey || collection,
          collection_name: options.collectionName || collection,
          media_urls: media,
          raw_metadata: {
            capture_source: "browser_account_mirror",
            page_url: currentUrl,
            completion_contract: "explicit_terminal_or_total_match_only"
          },
          requested_levels: ["L0", "L1", "L3"],
          destination_ids: ["social_archive", "markdown"]
        });
      }
    }
    return [...seen.values()];
  }

  function detectLoggedIn(platform, root = document) {
    const loginVisible = [...(root.querySelectorAll?.("button,a,[role='button']") || [])]
      .some(node => LOGIN_TEXT.test(cleanText(node.textContent, 80)) && (!node.getBoundingClientRect || node.getBoundingClientRect().width > 0));
    const excluded = new Set(["home","explore","notifications","messages","search","settings","login","accounts","your_activity"]);
    const profile = [...(root.querySelectorAll?.("a[href]") || [])]
      .map(node => ({ node, href: canonicalUrl(node.href) }))
      .find(item => {
        let path = "";
        try { path = new URL(item.href || (typeof location !== "undefined" ? location.href : "")).pathname; } catch (_) { return false; }
        if (/\/(user|profile|space)\//i.test(path) || /space\.bilibili\.com/i.test(item.href)) return true;
        const segments = path.split("/").filter(Boolean);
        if (["x", "instagram"].includes(platform) && segments.length === 1 && !excluded.has(segments[0].toLowerCase())) return true;
        return platform === "reddit" && /^\/user\/[^/]+/i.test(path);
      });
    const authenticatedSignal = root.querySelector?.([
      "[data-testid='SideNav_AccountSwitcher_Button']", "[data-testid='user-menu-button']",
      "[data-e2e*='avatar']", "[data-e2e*='user']", "button[aria-label*='Profile']",
      "button[aria-label*='个人']", "nav a[href*='/profile/']", "nav a[href*='/user/']", "header [class*='avatar']"
    ].join(","));
    const accountName = cleanText(profile?.node?.textContent || authenticatedSignal?.getAttribute?.("aria-label") || authenticatedSignal?.getAttribute?.("alt") || "", 256);
    return {
      loggedIn: Boolean(profile || authenticatedSignal) && !loginVisible,
      accountName: accountName || `${PLATFORM_SPECS[platform]?.label || platform}账号`,
      externalAccountId: profile?.href || `browser-session:${platform}`,
      profileUrl: profile?.href || "",
      loginHint: loginVisible ? "请先完成平台登录" : "已检测到登录态"
    };
  }

  function isAtBottom(doc = document) {
    const element = doc.scrollingElement || doc.documentElement;
    const height = typeof innerHeight === "number" ? innerHeight : Number(doc.defaultView?.innerHeight || 0);
    return Math.ceil(Number(element?.scrollTop || 0) + height) >= Number(element?.scrollHeight || 0) - 4;
  }

  function explicitEnd(root = document) {
    const candidates = [...(root.querySelectorAll?.("[role='status'],footer,[class*='end'],[class*='empty'],[class*='nomore'],[data-testid*='empty']") || [])];
    return candidates.some(node => END_TEXT.test(cleanText(node.textContent, 240)));
  }

  function totalHint(root = document) {
    const candidates = [...(root.querySelectorAll?.("[aria-label],[role='status'],h1,h2,h3,[class*='count'],[class*='total'],[class*='tab']") || [])];
    for (const node of candidates) {
      const text = cleanText(`${node.getAttribute?.("aria-label") || ""} ${node.textContent || ""}`, 500);
      const match = text.match(TOTAL_TEXT);
      if (!match) continue;
      const value = Number(match[1].replace(/,/g, ""));
      if (Number.isFinite(value) && value >= 0 && value <= 1_000_000) return value;
    }
    return null;
  }

  function completionProof(platform, root = document, discoveredCount = 0) {
    if (!PLATFORM_SPECS[platform]) return { complete: false, reason: "UNKNOWN_PLATFORM", totalHint: null };
    if (explicitEnd(root)) return { complete: true, reason: "EXPLICIT_END_MARKER", totalHint: totalHint(root) };
    const total = totalHint(root);
    if (total !== null && Number(discoveredCount || 0) >= total) return { complete: true, reason: "TRUSTED_TOTAL_MATCH", totalHint: total };
    return { complete: false, reason: "TERMINAL_NOT_PROVEN", totalHint: total };
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

  const api = Object.freeze({
    PLATFORM_SPECS, cleanText, canonicalUrl, externalId, relationFromUrl, collectionFromElement,
    discoverCollectionScopes, extractCandidates, detectLoggedIn, ensureRelationScope, isAtBottom, explicitEnd,
    totalHint, completionProof, flattenBookmarksTree, chunk
  });
  globalThis.SAMirrorCore = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
