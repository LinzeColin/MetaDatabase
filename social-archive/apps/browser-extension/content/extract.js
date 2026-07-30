(() => {
  "use strict";
  if (globalThis.__socialArchiveExtractorInstalled) return;
  globalThis.__socialArchiveExtractorInstalled = true;

  const visible = (element) => {
    if (!(element instanceof Element)) return false;
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return box.width > 20 && box.height > 20 && box.bottom > 0 && box.top < innerHeight && style.visibility !== "hidden" && style.display !== "none";
  };

  const meta = (...names) => {
    for (const name of names) {
      const element = document.querySelector(`meta[name="${CSS.escape(name)}"],meta[property="${CSS.escape(name)}"]`);
      if (element?.content) return element.content.trim();
    }
    return null;
  };

  const cleanText = (value, max = 120000) => String(value || "").replace(/\u0000/g, "").trim().slice(0, max);

  function pageRecord() {
    const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href;
    const images = [...document.querySelectorAll("img[src]")]
      .filter(visible)
      .map(item => item.currentSrc || item.src)
      .filter(url => /^https?:/i.test(url));
    const videos = [...document.querySelectorAll("video[src],video source[src]")]
      .filter(visible)
      .map(item => item.currentSrc || item.src)
      .filter(url => /^https?:/i.test(url));
    return {
      url: canonical,
      title: cleanText(meta("og:title", "twitter:title") || document.title, 2048),
      author_name: cleanText(meta("author", "article:author"), 1024) || null,
      text: cleanText(meta("description", "og:description", "twitter:description") || document.querySelector("article")?.innerText || document.body?.innerText),
      published_at: meta("article:published_time", "date", "datePublished"),
      media_urls: [...new Set([...videos, ...images])].slice(0, 30),
      raw_metadata: {
        captured_at: new Date().toISOString(),
        page_language: document.documentElement.lang || null,
        source: "browser_extension_user_action",
        viewport: { width: innerWidth, height: innerHeight }
      }
    };
  }

  function candidateLinks() {
    const selectors = [
      "article a[href]",
      "main a[href]",
      "[role='main'] a[href]",
      "[data-testid] a[href]",
      "a[href]"
    ];
    const found = [];
    const seen = new Set();
    for (const selector of selectors) {
      for (const link of document.querySelectorAll(selector)) {
        if (!visible(link)) continue;
        let url;
        try { url = new URL(link.href, location.href); } catch (_) { continue; }
        if (!/^https?:$/.test(url.protocol) || seen.has(url.href)) continue;
        const title = cleanText(link.innerText || link.getAttribute("aria-label") || link.title, 500);
        if (!title || title.length < 2) continue;
        seen.add(url.href);
        found.push({
          url: url.href,
          title,
          author_name: null,
          text: null,
          media_urls: [],
          raw_metadata: { source: "visible_list_item", captured_at: new Date().toISOString() }
        });
        if (found.length >= 80) return found;
      }
      if (found.length >= 12) break;
    }
    return found;
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "SA_EXTRACT") return undefined;
    try {
      const page = pageRecord();
      const items = message.mode === "list" ? candidateLinks() : [page];
      sendResponse({ ok: true, page, items, completeness: message.mode === "list" ? "partial" : "complete" });
    } catch (error) {
      sendResponse({ ok: false, error: error?.message || "页面读取失败" });
    }
    return true;
  });
})();
