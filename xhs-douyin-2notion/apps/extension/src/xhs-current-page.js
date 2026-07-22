const PLATFORM = "xiaohongshu";
const SCHEMA_VERSION = "1.0";
const PLATFORM_CHANGED = "X2N_PLATFORM_CHANGED";
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/u;
const FAILURE_REASONS = Object.freeze(new Set([
  "detail_surface_missing",
  "document_unavailable",
  "dom_unreadable",
  "stable_id_signal_invalid",
  "stable_id_signal_mismatch",
  "unsupported_detail_url",
]));

function exactKeys(value, expected) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

function canonicalPageUrl(contentId) {
  return ["https:", "", "www.xiaohongshu.com", "explore", contentId].join("/");
}

function validCanonicalPageUrl(value, contentId) {
  if (value !== canonicalPageUrl(contentId)) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:"
      && parsed.hostname === "www.xiaohongshu.com"
      && parsed.pathname === `/explore/${contentId}`
      && parsed.search === ""
      && parsed.hash === ""
      && parsed.username === ""
      && parsed.password === ""
      && parsed.port === "";
  } catch {
    return false;
  }
}

/**
 * Runs in Chrome's isolated world through chrome.scripting.executeScript.
 * Keep every helper nested: Chrome serializes this function without module scope.
 */
export function extractXhsCurrentPage() {
  const schemaVersion = "1.0";
  const platform = "xiaohongshu";
  const platformChanged = "X2N_PLATFORM_CHANGED";
  const safeId = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/u;
  const failure = (reason) => ({
    code: platformChanged,
    platform,
    reason,
    schema_version: schemaVersion,
    status: "platform_changed",
  });
  const idFromUrl = (raw, base) => {
    if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) return { state: "invalid" };
    let value;
    try {
      value = new URL(raw, base);
    } catch {
      return { state: "invalid" };
    }
    if (
      value.protocol !== "https:"
      || !new Set(["xiaohongshu.com", "www.xiaohongshu.com"]).has(value.hostname.toLowerCase())
      || value.username
      || value.password
      || value.port
    ) return { state: "invalid" };
    const match = value.pathname.match(/^\/(?:explore|discovery\/item)\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
    return match ? { id: match[1], state: "valid" } : { state: "invalid" };
  };
  const safeTitle = (raw) => {
    if (typeof raw !== "string") return { source: null, status: "missing", value: null };
    const normalized = raw.replace(/\s+/gu, " ").trim();
    if (normalized.length === 0) return { source: null, status: "missing", value: null };
    if (normalized.length > 500 || /[\u0000-\u001F\u007F]/u.test(normalized) || /https?:\/\//iu.test(normalized)) {
      return { source: null, status: "invalid", value: null };
    }
    return { status: "observed", value: normalized };
  };

  try {
    if (!globalThis.document || !globalThis.location) return failure("document_unavailable");
    const current = idFromUrl(globalThis.location.href, globalThis.location.origin);
    if (current.state !== "valid" || !safeId.test(current.id)) return failure("unsupported_detail_url");

    const detailSelectors = [
      '[data-x2n-surface="xhs-note-detail"]',
      "#noteContainer",
      ".note-detail-mask",
      '[class~="note-detail"]',
      "main article[data-note-id]",
      'main [data-note-id][role="article"]',
      "main article",
    ];
    const detailRoot = detailSelectors
      .map((selector) => globalThis.document.querySelector(selector))
      .find((candidate) => candidate && candidate.tagName !== "A");
    if (!detailRoot) return failure("detail_surface_missing");

    const identitySignals = [];
    let strongDetailSurface = detailRoot.matches(
      '[data-x2n-surface="xhs-note-detail"], #noteContainer, .note-detail-mask, [class~="note-detail"]',
    );
    const urlSignals = [
      globalThis.document.querySelector('link[rel~="canonical"]')?.getAttribute("href"),
      globalThis.document.querySelector('meta[property="og:url"]')?.getAttribute("content"),
    ].filter((value) => value !== null && value !== undefined);
    for (const raw of urlSignals) {
      const parsed = idFromUrl(raw, globalThis.location.origin);
      if (parsed.state !== "valid") return failure("stable_id_signal_invalid");
      identitySignals.push(parsed.id);
      strongDetailSurface = true;
    }

    const noteIdNode = detailRoot.matches("[data-note-id]")
      ? detailRoot
      : detailRoot.querySelector("[data-note-id]");
    if (noteIdNode) {
      const candidate = noteIdNode.getAttribute("data-note-id");
      if (typeof candidate !== "string" || !safeId.test(candidate)) return failure("stable_id_signal_invalid");
      identitySignals.push(candidate);
    }
    if (!strongDetailSurface) return failure("detail_surface_missing");
    if (identitySignals.some((candidate) => candidate !== current.id)) {
      return failure("stable_id_signal_mismatch");
    }

    const titleCandidates = [
      [globalThis.document.querySelector('meta[property="og:title"]')?.getAttribute("content"), "open_graph"],
      [detailRoot.querySelector('[data-x2n-field="title"]')?.textContent, "detail_heading"],
      [detailRoot.querySelector("h1")?.textContent, "detail_heading"],
      [detailRoot.querySelector('[role="heading"][aria-level="1"]')?.textContent, "detail_heading"],
    ];
    let title = { source: null, status: "missing", value: null };
    for (const [candidate, source] of titleCandidates) {
      const inspected = safeTitle(candidate);
      if (inspected.status === "missing") continue;
      title = { ...inspected, source: inspected.status === "observed" ? source : null };
      break;
    }

    const declaredType = (detailRoot.getAttribute("data-note-type") ?? "").toLowerCase();
    const openGraphType = (
      globalThis.document.querySelector('meta[property="og:type"]')?.getAttribute("content") ?? ""
    ).toLowerCase();
    const hasVideo = declaredType === "video"
      || openGraphType.includes("video")
      || detailRoot.querySelector("video") !== null;
    const hasImageGallery = declaredType === "image"
      || detailRoot.querySelector(
        '[data-x2n-media="image-gallery"], [aria-label="image gallery"], figure img, [role="list"] img',
      ) !== null;
    let contentType = "unknown";
    let contentTypeSource = null;
    let contentTypeStatus = "unknown";
    if (hasVideo) {
      contentType = "video";
      contentTypeSource = "detail_video_marker";
      contentTypeStatus = "observed";
    } else if (hasImageGallery) {
      contentType = "image_gallery";
      contentTypeSource = "detail_image_marker";
      contentTypeStatus = "observed";
    }

    const pageUrl = ["https:", "", "www.xiaohongshu.com", "explore", current.id].join("/");
    return {
      page_context: {
        content_id: current.id,
        content_type: contentType,
        title: title.value,
      },
      page_url: pageUrl,
      platform,
      provenance: {
        canonical_url: { source: "stable_content_id", status: "derived" },
        content_id: { source: "location_path_and_detail_surface", status: "observed_verified" },
        content_type: { source: contentTypeSource, status: contentTypeStatus },
        title: { source: title.source, status: title.status },
      },
      schema_version: schemaVersion,
      status: "ready",
    };
  } catch {
    return failure("dom_unreadable");
  }
}

export function validateXhsPageFacts(value) {
  if (!exactKeys(value, ["code", "platform", "reason", "schema_version", "status"])
    && !exactKeys(value, ["page_context", "page_url", "platform", "provenance", "schema_version", "status"])) {
    throw new TypeError("XHS page facts contain unknown or missing fields");
  }
  if (value.schema_version !== SCHEMA_VERSION || value.platform !== PLATFORM) {
    throw new TypeError("XHS page facts identity mismatch");
  }
  if (value.status === "platform_changed") {
    if (value.code !== PLATFORM_CHANGED || !FAILURE_REASONS.has(value.reason)) {
      throw new TypeError("XHS platform-changed result is invalid");
    }
    return value;
  }
  if (value.status !== "ready") throw new TypeError("XHS page facts status is invalid");
  if (!exactKeys(value.page_context, ["content_id", "content_type", "title"])) {
    throw new TypeError("XHS page context is invalid");
  }
  const { content_id: contentId, content_type: contentType, title } = value.page_context;
  if (!SAFE_ID.test(contentId) || !new Set(["image_gallery", "unknown", "video"]).has(contentType)) {
    throw new TypeError("XHS page context identity or type is invalid");
  }
  if (title !== null && (typeof title !== "string" || title.length === 0 || title.length > 500 || /https?:\/\//iu.test(title))) {
    throw new TypeError("XHS page title is unsafe");
  }
  if (!validCanonicalPageUrl(value.page_url, contentId)) throw new TypeError("XHS canonical page URL is invalid");
  if (!exactKeys(value.provenance, ["canonical_url", "content_id", "content_type", "title"])) {
    throw new TypeError("XHS provenance is invalid");
  }
  const expectedProvenance = {
    canonical_url: new Set(["derived:stable_content_id"]),
    content_id: new Set(["observed_verified:location_path_and_detail_surface"]),
    content_type: new Set([
      "observed:detail_image_marker",
      "observed:detail_video_marker",
      "unknown:null",
    ]),
    title: new Set(["invalid:null", "missing:null", "observed:detail_heading", "observed:open_graph"]),
  };
  for (const [field, allowed] of Object.entries(expectedProvenance)) {
    const item = value.provenance[field];
    if (!exactKeys(item, ["source", "status"]) || !allowed.has(`${item.status}:${String(item.source)}`)) {
      throw new TypeError(`XHS provenance is invalid: ${field}`);
    }
  }
  if ((title === null) !== new Set(["invalid", "missing"]).has(value.provenance.title.status)) {
    throw new TypeError("XHS title status does not match its value");
  }
  if ((contentType === "unknown") !== (value.provenance.content_type.status === "unknown")) {
    throw new TypeError("XHS content type status does not match its value");
  }
  return value;
}

export function buildXhsCapturePayload(value) {
  const facts = validateXhsPageFacts(value);
  if (facts.status !== "ready") throw new TypeError("Platform-changed facts cannot be captured");
  return {
    auto_scroll: false,
    category_id: null,
    change_account_state: false,
    page_context: { ...facts.page_context },
    page_url: facts.page_url,
    platform: PLATFORM,
    relation: "saved_current",
    user_gesture: true,
  };
}
