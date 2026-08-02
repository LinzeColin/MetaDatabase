(() => {
  "use strict";
  if (globalThis.__socialArchiveExtractorInstalled) return;
  globalThis.__socialArchiveExtractorInstalled = true;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "SA_EXTRACT") return undefined;
    try {
      const core = globalThis.SocialArchiveExtractorCore;
      if (!core) throw new Error("页面读取器未加载，请重新点击一次");
      const page = core.extractPage();
      if (message.mode === "list") {
        const result = core.extractVisibleList();
        sendResponse({ ok: true, page, items: result.items, completeness: result.completeness, scan_context: result.scan_context });
      } else {
        sendResponse({ ok: true, page, items: [page], completeness: "complete", scan_context: { mode: "current_page" } });
      }
    } catch (error) {
      sendResponse({ ok: false, error: error?.message || "页面读取失败" });
    }
    return true;
  });
})();
