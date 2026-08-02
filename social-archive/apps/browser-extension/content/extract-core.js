(() => {
  "use strict";
  if (globalThis.SocialArchiveExtractorCore) return;

  const MAX_TEXT = 120000;
  const MAX_MEDIA = 100;
  const LIST_LIMIT = 100;

  function cleanText(value, max = MAX_TEXT) {
    return String(value || "")
      .replace(/\u0000/g, "")
      .replace(/[\t\r ]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim()
      .slice(0, max);
  }

  function absoluteUrl(value, base = location.href) {
    try {
      const url = new URL(String(value || ""), base);
      return /^https?:$/.test(url.protocol) ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function visible(element) {
    if (!(element instanceof Element)) return false;
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return box.width > 18 && box.height > 12 && box.bottom > 0 && box.top < innerHeight
      && style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity || 1) > 0;
  }

  function meta(...names) {
    for (const name of names) {
      const nodes = document.querySelectorAll("meta[name],meta[property]");
      for (const node of nodes) {
        if ((node.getAttribute("name") === name || node.getAttribute("property") === name) && node.content) {
          return cleanText(node.content, 4096);
        }
      }
    }
    return null;
  }

  function firstNode(selectors, root = document) {
    for (const selector of selectors) {
      try {
        const node = root.querySelector(selector);
        if (node) return node;
      } catch (_) { /* ignore stale selectors */ }
    }
    return null;
  }

  function firstText(selectors, root = document, max = MAX_TEXT) {
    for (const selector of selectors) {
      try {
        for (const node of root.querySelectorAll(selector)) {
          const value = cleanText(node.innerText || node.textContent, max);
          if (value) return value;
        }
      } catch (_) { /* ignore stale selectors */ }
    }
    return null;
  }

  function attr(selectors, name, root = document) {
    const node = firstNode(selectors, root);
    return node ? cleanText(node.getAttribute(name), 4096) || null : null;
  }

  function detectPlatform(hostname = location.hostname) {
    const host = String(hostname || "").toLowerCase().replace(/^www\./, "");
    const test = domain => host === domain || host.endsWith(`.${domain}`);
    if (test("xiaohongshu.com") || test("xhslink.com")) return "xiaohongshu";
    if (test("douyin.com") || test("iesdouyin.com")) return "douyin";
    if (test("tiktok.com")) return "tiktok";
    if (test("kuaishou.com") || test("gifshow.com")) return "kuaishou";
    if (test("bilibili.com") || test("b23.tv")) return "bilibili";
    if (test("x.com") || test("twitter.com")) return "x";
    if (test("reddit.com") || test("redd.it")) return "reddit";
    if (test("instagram.com")) return "instagram";
    return "generic-web";
  }

  function jsonLdObjects() {
    const result = [];
    for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const parsed = JSON.parse(node.textContent || "null");
        const values = Array.isArray(parsed) ? parsed : [parsed];
        for (const value of values) {
          if (value && typeof value === "object") result.push(value);
          if (value?.["@graph"] && Array.isArray(value["@graph"])) result.push(...value["@graph"].filter(x => x && typeof x === "object"));
        }
      } catch (_) { /* malformed publisher data is non-fatal */ }
    }
    return result.slice(0, 50);
  }

  function structuredValue(keys) {
    for (const object of jsonLdObjects()) {
      for (const key of keys) {
        const value = object[key];
        if (typeof value === "string" && cleanText(value)) return cleanText(value, 4096);
        if (value && typeof value === "object" && typeof value.name === "string") return cleanText(value.name, 4096);
      }
    }
    return null;
  }

  function mediaFrom(root = document) {
    const values = [];
    const selectors = [
      "img[src]", "img[srcset]", "video[src]", "video source[src]", "audio[src]", "source[src]",
      'meta[property="og:image"]', 'meta[property="og:video"]', 'meta[property="og:audio"]'
    ];
    for (const selector of selectors) {
      for (const node of root.querySelectorAll(selector)) {
        if (node instanceof Element && !node.matches("meta") && !visible(node)) continue;
        const candidates = [node.currentSrc, node.src, node.content, node.getAttribute("src")];
        if (node.getAttribute?.("srcset")) {
          candidates.push(...node.getAttribute("srcset").split(",").map(part => part.trim().split(/\s+/)[0]));
        }
        for (const candidate of candidates) {
          const url = absoluteUrl(candidate);
          if (url) values.push(url);
        }
      }
    }
    return [...new Set(values)].slice(0, MAX_MEDIA);
  }

  function canonicalUrl() {
    return absoluteUrl(document.querySelector('link[rel="canonical"]')?.href)
      || absoluteUrl(meta("og:url", "twitter:url"))
      || location.href;
  }

  function timeValue(root = document) {
    const node = firstNode(["time[datetime]", "[data-time][datetime]", "[datetime]"], root);
    return cleanText(node?.getAttribute("datetime"), 128)
      || meta("article:published_time", "date", "datePublished")
      || structuredValue(["datePublished", "uploadDate"]);
  }

  function genericPage() {
    return {
      url: canonicalUrl(),
      title: cleanText(meta("og:title", "twitter:title") || structuredValue(["headline", "name"]) || document.title, 2048),
      author_name: cleanText(meta("author", "article:author") || structuredValue(["author", "creator"]), 1024) || null,
      text: cleanText(
        firstText(["article", "main article", "[role='article']", "main"], document)
        || meta("description", "og:description", "twitter:description")
        || document.body?.innerText
      ),
      published_at: timeValue(),
      media_urls: mediaFrom(document),
      raw_metadata: {}
    };
  }

  function xPage() {
    const tweet = firstNode(['article[data-testid="tweet"]', '[data-testid="tweet"]']) || document;
    return {
      ...genericPage(),
      url: absoluteUrl(firstNode(['a[href*="/status/"]'], tweet)?.href) || canonicalUrl(),
      title: firstText(['[data-testid="tweetText"]'], tweet, 600) || cleanText(document.title, 2048),
      author_name: firstText(['[data-testid="User-Name"] a[role="link"] span', '[data-testid="User-Name"] span'], tweet, 1024),
      text: firstText(['[data-testid="tweetText"]', '[lang]'], tweet) || genericPage().text,
      published_at: timeValue(tweet),
      media_urls: mediaFrom(tweet),
      raw_metadata: { extraction_rule: "x_tweet" }
    };
  }

  function redditPage() {
    const post = firstNode(["shreddit-post", 'article[data-testid="post-container"]', "main article"]) || document;
    const permalink = post.getAttribute?.("permalink") || attr(['a[data-testid="post-title"]', 'a[href*="/comments/"]'], "href", post);
    return {
      ...genericPage(),
      url: absoluteUrl(permalink) || canonicalUrl(),
      title: firstText(['[slot="title"]', '[data-testid="post-title"]', "h1"], post, 2048) || genericPage().title,
      author_name: cleanText(post.getAttribute?.("author"), 1024) || firstText(['a[href*="/user/"]', 'a[href*="/u/"]'], post, 1024),
      text: firstText(['[slot="text-body"]', '[data-testid="post-content"]', '.md', '[data-click-id="text"]'], post) || genericPage().text,
      published_at: cleanText(post.getAttribute?.("created-timestamp"), 128) || timeValue(post),
      media_urls: mediaFrom(post),
      raw_metadata: { extraction_rule: "reddit_post" }
    };
  }

  function instagramPage() {
    const post = firstNode(["main article", "article"]) || document;
    const caption = firstText(['h1', 'ul li span', '[role="button"] span'], post);
    return {
      ...genericPage(),
      title: cleanText(meta("og:title") || caption || document.title, 2048),
      author_name: firstText(['header a[href^="/"]', 'a[href^="/"][role="link"]'], post, 1024),
      text: caption || cleanText(meta("og:description") || genericPage().text),
      published_at: timeValue(post),
      media_urls: mediaFrom(post),
      raw_metadata: { extraction_rule: "instagram_post" }
    };
  }

  function xhsPage() {
    const root = firstNode(["#noteContainer", ".note-container", '[class*="note-detail"]', "main"]) || document;
    return {
      ...genericPage(),
      title: firstText(["#detail-title", ".title", '[class*="title"] h1', "h1"], root, 2048) || genericPage().title,
      author_name: firstText(['.author-wrapper [class*="name"]', '[class*="author"] [class*="name"]', 'a[href*="/user/profile/"]'], root, 1024),
      text: firstText(["#detail-desc", ".desc", '[class*="note-content"]', '[class*="desc"]'], root) || genericPage().text,
      published_at: timeValue(root),
      media_urls: mediaFrom(root),
      raw_metadata: { extraction_rule: "xiaohongshu_note" }
    };
  }

  function douyinPage(platform) {
    const root = firstNode(['[data-e2e="browse-video-desc"]', '[data-e2e="video-desc"]', '[class*="video-info"]', "main"]) || document;
    return {
      ...genericPage(),
      title: firstText(['[data-e2e="browse-video-desc"]', '[data-e2e="video-desc"]', "h1", '[class*="title"]'], root, 2048) || genericPage().title,
      author_name: firstText(['[data-e2e="browser-nickname"]', '[data-e2e="video-author-uniqueid"]', 'a[href*="/user/"]', '[class*="author"]'], document, 1024),
      text: firstText(['[data-e2e="browse-video-desc"]', '[data-e2e="video-desc"]', '[class*="desc"]'], document) || genericPage().text,
      published_at: timeValue(document),
      media_urls: mediaFrom(document),
      raw_metadata: { extraction_rule: `${platform}_video` }
    };
  }

  function kuaishouPage() {
    const root = firstNode(['[class*="video-info"]', '[class*="photo-info"]', "main"]) || document;
    return {
      ...genericPage(),
      title: firstText(["h1", '[class*="title"]', '[class*="caption"]'], root, 2048) || genericPage().title,
      author_name: firstText(['a[href*="/profile/"]', '[class*="author"]', '[class*="user-name"]'], root, 1024),
      text: firstText(['[class*="caption"]', '[class*="desc"]', '[class*="content"]'], root) || genericPage().text,
      published_at: timeValue(root),
      media_urls: mediaFrom(root),
      raw_metadata: { extraction_rule: "kuaishou_video" }
    };
  }

  function bilibiliPage() {
    const root = firstNode(["#app", "main"]) || document;
    return {
      ...genericPage(),
      title: firstText(["h1.video-title", ".video-title", "h1"], root, 2048) || genericPage().title,
      author_name: firstText([".up-name", ".staff-name", 'a[href*="space.bilibili.com"]'], root, 1024),
      text: firstText([".desc-info-text", ".video-desc-container", '[class*="desc"]'], root) || genericPage().text,
      published_at: timeValue(root),
      media_urls: mediaFrom(root),
      raw_metadata: { extraction_rule: "bilibili_video" }
    };
  }

  function normalizeRecord(record, platform, source) {
    const url = absoluteUrl(record?.url) || canonicalUrl();
    return {
      url,
      title: cleanText(record?.title || document.title, 2048),
      author_name: cleanText(record?.author_name, 1024) || null,
      text: cleanText(record?.text) || null,
      published_at: cleanText(record?.published_at, 128) || null,
      media_urls: [...new Set((record?.media_urls || []).map(value => absoluteUrl(value)).filter(Boolean))].slice(0, MAX_MEDIA),
      raw_metadata: {
        ...(record?.raw_metadata || {}),
        platform,
        source,
        captured_at: new Date().toISOString(),
        page_language: document.documentElement.lang || null,
        viewport: { width: innerWidth, height: innerHeight }
      }
    };
  }

  function extractPage(platformOverride = null) {
    const platform = platformOverride || detectPlatform();
    const record = ({
      x: xPage,
      reddit: redditPage,
      instagram: instagramPage,
      xiaohongshu: xhsPage,
      douyin: () => douyinPage("douyin"),
      tiktok: () => douyinPage("tiktok"),
      kuaishou: kuaishouPage,
      bilibili: bilibiliPage,
      "generic-web": genericPage
    }[platform] || genericPage)();
    return normalizeRecord(record, platform, "browser_extension_current_page");
  }

  const LIST_SELECTORS = Object.freeze({
    x: ['article[data-testid="tweet"]'],
    reddit: ["shreddit-post", 'article[data-testid="post-container"]'],
    instagram: ['main a[href*="/p/"]', 'main a[href*="/reel/"]'],
    xiaohongshu: ['a[href*="/explore/"]', 'a[href*="/discovery/item/"]'],
    douyin: ['a[href*="/video/"]', 'a[href*="/note/"]'],
    tiktok: ['a[href*="/video/"]'],
    kuaishou: ['a[href*="/short-video/"]', 'a[href*="/photo/"]'],
    bilibili: ['a[href*="/video/"]'],
    "generic-web": ["article a[href]", "main a[href]", "[role='main'] a[href]", "a[href]"]
  });

  function recordFromListNode(node, platform) {
    const anchor = node.matches?.("a[href]") ? node : firstNode(["a[href]"], node);
    const url = absoluteUrl(anchor?.href || node.getAttribute?.("permalink"));
    if (!url) return null;
    const title = cleanText(
      firstText(['[data-testid="tweetText"]', '[slot="title"]', "h1", "h2", "h3", '[class*="title"]', '[class*="desc"]'], node, 700)
      || anchor?.getAttribute?.("aria-label")
      || anchor?.title
      || anchor?.innerText,
      700
    );
    if (!title || title.length < 2) return null;
    const author = cleanText(firstText(['[data-testid="User-Name"]', 'a[href*="/user/"]', 'a[href*="/profile/"]', '[class*="author"]'], node, 1024), 1024) || null;
    const text = cleanText(firstText(['[data-testid="tweetText"]', '[slot="text-body"]', '[class*="desc"]', "p"], node, 10000), 10000) || null;
    return normalizeRecord({
      url,
      title,
      author_name: author,
      text,
      published_at: timeValue(node),
      media_urls: mediaFrom(node),
      raw_metadata: { extraction_rule: `${platform}_visible_list_card` }
    }, platform, "browser_extension_visible_list");
  }

  function extractVisibleList(platformOverride = null) {
    const platform = platformOverride || detectPlatform();
    const selectors = LIST_SELECTORS[platform] || LIST_SELECTORS["generic-web"];
    const seen = new Set();
    const items = [];
    let matchedNodes = 0;
    for (const selector of selectors) {
      let nodes = [];
      try { nodes = [...document.querySelectorAll(selector)]; } catch (_) { continue; }
      for (const node of nodes) {
        if (!visible(node)) continue;
        matchedNodes += 1;
        const record = recordFromListNode(node, platform);
        if (!record || seen.has(record.url)) continue;
        seen.add(record.url);
        record.raw_metadata.scan_completeness = "partial";
        record.raw_metadata.no_autoscroll = true;
        items.push(record);
        if (items.length >= LIST_LIMIT) break;
      }
      if (items.length >= LIST_LIMIT || items.length >= 12) break;
    }
    return {
      platform,
      items,
      completeness: "partial",
      scan_context: {
        mode: "visible_only",
        no_autoscroll: true,
        matched_nodes: matchedNodes,
        unique_items: items.length,
        viewport: { width: innerWidth, height: innerHeight },
        captured_at: new Date().toISOString()
      }
    };
  }

  globalThis.SocialArchiveExtractorCore = Object.freeze({
    cleanText, absoluteUrl, detectPlatform, extractPage, extractVisibleList
  });
})();
