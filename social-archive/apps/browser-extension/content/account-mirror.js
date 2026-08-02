/* global SAMirrorCore */
(() => {
  "use strict";
  if (globalThis.__socialArchiveAccountMirrorLoaded) return;
  globalThis.__socialArchiveAccountMirrorLoaded = true;

  function platformFromLocation() {
    const host = location.hostname.toLowerCase();
    if (host.endsWith("xiaohongshu.com")) return "xiaohongshu";
    if (host.endsWith("douyin.com")) return "douyin";
    if (host.endsWith("kuaishou.com")) return "kuaishou";
    if (host.endsWith("bilibili.com")) return "bilibili";
    if (host === "x.com" || host.endsWith(".x.com") || host.endsWith("twitter.com")) return "x";
    if (host.endsWith("reddit.com")) return "reddit";
    if (host.endsWith("instagram.com")) return "instagram";
    return "generic-web";
  }

  const scanControls = new Map();

  async function readScanControl(syncRunId) {
    if (!syncRunId) return null;
    const local = scanControls.get(syncRunId);
    if (local === "pause" || local === "cancel") return local;
    const remote = await chrome.runtime.sendMessage({ type: "SA_GET_SYNC_CONTROL_STATE", syncRunId }).catch(() => null);
    if (remote?.action === "pause" || remote?.action === "cancel") {
      scanControls.set(syncRunId, remote.action);
      return remote.action;
    }
    return null;
  }

  function controlledResult(platform, relationType, action) {
    return {
      ok: false, controlled: true, controlAction: action, platform, relationType,
      items: [], completeness: "partial", endConfirmed: false,
      completionReason: "USER_CONTROLLED", failureCode: action === "pause" ? "USER_PAUSED" : "USER_CANCELLED"
    };
  }

  function openScanHeartbeat(platform, relationType) {
    const port = chrome.runtime.connect({ name: "sa-account-mirror-scan" });
    const send = phase => { try { port.postMessage({ type: "SA_SCAN_HEARTBEAT", platform, relationType, phase, at: Date.now() }); } catch (_) {} };
    send("started");
    const timer = setInterval(() => send("running"), 20000);
    return () => { clearInterval(timer); send("finished"); try { port.disconnect(); } catch (_) {} };
  }

  async function scanRelation({
    syncRunId = "", relationType, collectionKey = "", collectionName = "",
    maxItems = 100000, maxScrolls = 1200, stableRoundsRequired = 5
  }) {
    const platform = platformFromLocation();
    const closeHeartbeat = openScanHeartbeat(platform, relationType);
    try {
      const discovered = new Map();
      let stableRounds = 0;
      let previousHeight = -1;
      let previousCount = -1;
      let stableExhausted = false;
      let proof = { complete: false, reason: "TERMINAL_NOT_PROVEN", totalHint: null };

      const collect = () => {
        for (const item of SAMirrorCore.extractCandidates(platform, document, { relationType, collectionKey, collectionName })) {
          item.relation_type = relationType || SAMirrorCore.relationFromUrl(platform, location.href);
          item.collection_key = collectionKey || item.collection_key || "";
          item.collection_name = collectionName || item.collection_name || item.collection_key || "";
          discovered.set(`${item.external_content_id || item.url}:${item.collection_key}`, item);
        }
      };

      for (let round = 0; round < maxScrolls && discovered.size < maxItems; round += 1) {
        if (round === 0 || round % 4 === 0) {
          const control = await readScanControl(syncRunId);
          if (control) return controlledResult(platform, relationType, control);
        }
        collect();
        proof = SAMirrorCore.completionProof(platform, document, discovered.size);
        if (proof.complete) break;

        const scrolling = document.scrollingElement || document.documentElement;
        const currentHeight = Number(scrolling.scrollHeight || 0);
        const atBottom = SAMirrorCore.isAtBottom(document);
        if (currentHeight === previousHeight && discovered.size === previousCount && atBottom) stableRounds += 1;
        else stableRounds = 0;
        previousHeight = currentHeight;
        previousCount = discovered.size;
        if (atBottom && stableRounds >= stableRoundsRequired) {
          // Stable height alone is not enough to declare a complete account scan.
          // Stop to avoid an endless loop, but return PARTIAL unless a terminal/total proof exists.
          stableExhausted = true;
          break;
        }
        scrolling.scrollTo({ top: scrolling.scrollHeight, behavior: "auto" });
        await new Promise(resolve => setTimeout(resolve, Math.min(1600, 450 + round * 4)));
        const afterWaitControl = await readScanControl(syncRunId);
        if (afterWaitControl) return controlledResult(platform, relationType, afterWaitControl);
      }

      const finalControl = await readScanControl(syncRunId);
      if (finalControl) return controlledResult(platform, relationType, finalControl);
      collect();
      proof = SAMirrorCore.completionProof(platform, document, discovered.size);
      const complete = Boolean(proof.complete);
      return {
        ok: true,
        platform,
        relationType: relationType || SAMirrorCore.relationFromUrl(platform, location.href),
        collectionKey,
        collectionName,
        items: [...discovered.values()],
        completeness: complete ? "complete" : "partial",
        endConfirmed: complete,
        completionReason: proof.reason,
        totalHint: proof.totalHint,
        cursor: {
          page_url: SAMirrorCore.canonicalUrl(location.href),
          scroll_height: Number((document.scrollingElement || document.documentElement).scrollHeight || 0),
          observed_count: discovered.size,
          total_hint: proof.totalHint,
          completion_reason: proof.reason,
          stable_exhausted: stableExhausted
        },
        failureCode: complete ? null : (stableExhausted ? "STABLE_END_WITHOUT_PROOF" : "TERMINAL_NOT_PROVEN")
      };
    } finally {
      closeHeartbeat();
    }
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    (async () => {
      if (message?.type === "SA_MIRROR_DISCOVER_ACCOUNT") {
        const platform = platformFromLocation();
        return { ok: true, platform, ...SAMirrorCore.detectLoggedIn(platform) };
      }
      if (message?.type === "SA_MIRROR_DISCOVER_COLLECTIONS") {
        const platform = platformFromLocation();
        return { ok: true, platform, items: SAMirrorCore.discoverCollectionScopes(platform, document) };
      }
      if (message?.type === "SA_MIRROR_CONTROL") {
        const syncRunId = String(message.syncRunId || "");
        if (message.action === "clear") scanControls.delete(syncRunId);
        else if (["pause", "cancel"].includes(message.action)) scanControls.set(syncRunId, message.action);
        return { ok: true, action: message.action };
      }
      if (message?.type === "SA_MIRROR_SCAN_RELATION") return scanRelation(message);
      return { ok: false, error: "未知账号同步操作" };
    })().then(sendResponse).catch(error => sendResponse({ ok: false, error: error?.message || "账号读取失败" }));
    return true;
  });

  const platform = platformFromLocation();
  if (platform !== "generic-web") {
    const state = SAMirrorCore.detectLoggedIn(platform);
    chrome.runtime.sendMessage({ type: "SA_PLATFORM_PAGE_READY", platform, ...state, pageUrl: location.href }).catch(() => {});
  }
})();
