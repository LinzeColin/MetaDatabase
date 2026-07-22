const PLATFORM = "douyin";
const SCHEMA_VERSION = "1.0";
const PLATFORM_CHANGED = "X2N_PLATFORM_CHANGED";
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/u;
const FAILURE_REASONS = Object.freeze(new Set([
  "content_type_signal_ambiguous",
  "content_type_signal_mismatch",
  "detail_surface_ambiguous",
  "detail_surface_missing",
  "document_unavailable",
  "dom_unreadable",
  "short_link_canonical_invalid",
  "short_link_canonical_missing",
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

function canonicalPageUrl(contentKind, contentId) {
  return ["https:", "", "www.douyin.com", contentKind, contentId].join("/");
}

function parseDetailUrl(raw, base) {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) return null;
  let value;
  try {
    value = new URL(raw, base);
  } catch {
    return null;
  }
  if (
    value.protocol !== "https:"
    || value.hostname.toLowerCase() !== "www.douyin.com"
    || value.username
    || value.password
    || value.port
  ) return null;
  const match = value.pathname.match(/^\/(video|note)\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
  return match ? { contentId: match[2], contentKind: match[1] } : null;
}

function validCanonicalPageUrl(value, contentId) {
  const parsed = parseDetailUrl(value);
  if (!parsed || parsed.contentId !== contentId || value !== canonicalPageUrl(parsed.contentKind, contentId)) return false;
  const url = new URL(value);
  return url.search === "" && url.hash === "";
}

/**
 * Runs in Chrome's isolated world through chrome.scripting.executeScript.
 * Every helper is nested because Chrome serializes the function without module scope.
 */
export function extractDouyinCurrentPage() {
  const schemaVersion = "1.0";
  const platform = "douyin";
  const platformChanged = "X2N_PLATFORM_CHANGED";
  const safeId = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/u;
  const failure = (reason) => ({
    code: platformChanged,
    platform,
    reason,
    schema_version: schemaVersion,
    status: "platform_changed",
  });
  const inspectUrl = (raw, base) => {
    if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) return { state: "invalid" };
    let value;
    try {
      value = new URL(raw, base);
    } catch {
      return { state: "invalid" };
    }
    if (value.protocol !== "https:" || value.username || value.password || value.port) return { state: "invalid" };
    const host = value.hostname.toLowerCase();
    if (host === "v.douyin.com") {
      const shortMatch = value.pathname.match(/^\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
      return shortMatch ? { shortCode: shortMatch[1], state: "short" } : { state: "invalid" };
    }
    if (host !== "www.douyin.com") return { state: "invalid" };
    const match = value.pathname.match(/^\/(video|note)\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
    return match
      ? { contentId: match[2], contentKind: match[1], state: "detail" }
      : { state: "invalid" };
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
    const current = inspectUrl(globalThis.location.href, globalThis.location.origin);
    if (!new Set(["detail", "short"]).has(current.state)) return failure("unsupported_detail_url");
    if (current.state === "short" && !current.shortCode.startsWith("synthetic-")) {
      return failure("unsupported_detail_url");
    }

    const canonicalSignals = [
      globalThis.document.querySelector('link[rel~="canonical"]')?.getAttribute("href"),
      globalThis.document.querySelector('meta[property="og:url"]')?.getAttribute("content"),
    ].filter((value) => value !== null && value !== undefined);
    const parsedCanonical = [];
    for (const raw of canonicalSignals) {
      const inspected = inspectUrl(raw, globalThis.location.origin);
      if (inspected.state !== "detail") {
        return failure(current.state === "short" ? "short_link_canonical_invalid" : "stable_id_signal_invalid");
      }
      parsedCanonical.push(inspected);
    }
    if (current.state === "short" && parsedCanonical.length === 0) return failure("short_link_canonical_missing");
    const identity = current.state === "detail" ? current : parsedCanonical[0];
    if (
      !identity
      || !safeId.test(identity.contentId)
      || !identity.contentId.startsWith("synthetic-")
    ) return failure("stable_id_signal_invalid");
    if (parsedCanonical.some(
      (candidate) => candidate.contentId !== identity.contentId || candidate.contentKind !== identity.contentKind,
    )) return failure("stable_id_signal_mismatch");

    const detailSelectors = [
      '[data-x2n-surface="douyin-detail"]',
      'main [data-e2e="video-detail"]',
      'main article[data-aweme-id]',
      '#douyin-right-container [data-aweme-id]',
    ];
    const detailRoots = [];
    for (const selector of detailSelectors) {
      for (const candidate of globalThis.document.querySelectorAll(selector)) {
        if (candidate.tagName !== "A" && !detailRoots.includes(candidate)) detailRoots.push(candidate);
      }
    }
    if (detailRoots.length === 0) return failure("detail_surface_missing");
    if (detailRoots.length !== 1) return failure("detail_surface_ambiguous");
    const [detailRoot] = detailRoots;

    const awemeNodes = [
      ...(detailRoot.matches("[data-aweme-id]") ? [detailRoot] : []),
      ...detailRoot.querySelectorAll("[data-aweme-id]"),
    ];
    if (awemeNodes.length === 0) return failure("stable_id_signal_invalid");
    const awemeIds = awemeNodes.map((node) => node.getAttribute("data-aweme-id"));
    if (awemeIds.some((value) => typeof value !== "string" || !safeId.test(value))) {
      return failure("stable_id_signal_invalid");
    }
    if (awemeIds.some((value) => value !== identity.contentId)) return failure("stable_id_signal_mismatch");

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

    const declaredType = (
      detailRoot.getAttribute("data-aweme-type")
      ?? detailRoot.getAttribute("data-note-type")
      ?? ""
    ).toLowerCase();
    const openGraphType = (
      globalThis.document.querySelector('meta[property="og:type"]')?.getAttribute("content") ?? ""
    ).toLowerCase();
    const hasVideo = declaredType === "video"
      || openGraphType.includes("video")
      || detailRoot.querySelector("video") !== null;
    const hasGallery = new Set(["gallery", "image", "image_gallery", "note"]).has(declaredType)
      || detailRoot.querySelector(
        '[data-x2n-media="image-gallery"], [aria-label="image gallery"], [role="list"] img',
      ) !== null;
    if (hasVideo && hasGallery) return failure("content_type_signal_ambiguous");
    if ((identity.contentKind === "video" && hasGallery) || (identity.contentKind === "note" && hasVideo)) {
      return failure("content_type_signal_mismatch");
    }
    let contentType = "unknown";
    let contentTypeSource = null;
    let contentTypeStatus = "unknown";
    if (hasVideo) {
      contentType = "video";
      contentTypeSource = "detail_video_marker";
      contentTypeStatus = "observed";
    } else if (hasGallery) {
      contentType = "image_gallery";
      contentTypeSource = "detail_image_marker";
      contentTypeStatus = "observed";
    }

    const pageUrl = ["https:", "", "www.douyin.com", identity.contentKind, identity.contentId].join("/");
    return {
      page_context: {
        content_id: identity.contentId,
        content_type: contentType,
        title: title.value,
      },
      page_url: pageUrl,
      platform,
      provenance: {
        canonical_url: { source: "stable_content_id_and_kind", status: "derived" },
        content_id: {
          source: current.state === "short"
            ? "short_link_canonical_and_detail_surface"
            : "location_path_and_detail_surface",
          status: "observed_verified",
        },
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

export function validateDouyinPageFacts(value) {
  if (!exactKeys(value, ["code", "platform", "reason", "schema_version", "status"])
    && !exactKeys(value, ["page_context", "page_url", "platform", "provenance", "schema_version", "status"])) {
    throw new TypeError("Douyin page facts contain unknown or missing fields");
  }
  if (value.schema_version !== SCHEMA_VERSION || value.platform !== PLATFORM) {
    throw new TypeError("Douyin page facts identity mismatch");
  }
  if (value.status === "platform_changed") {
    if (value.code !== PLATFORM_CHANGED || !FAILURE_REASONS.has(value.reason)) {
      throw new TypeError("Douyin platform-changed result is invalid");
    }
    return value;
  }
  if (value.status !== "ready") throw new TypeError("Douyin page facts status is invalid");
  if (!exactKeys(value.page_context, ["content_id", "content_type", "title"])) {
    throw new TypeError("Douyin page context is invalid");
  }
  const { content_id: contentId, content_type: contentType, title } = value.page_context;
  if (
    !SAFE_ID.test(contentId)
    || !contentId.startsWith("synthetic-")
    || !new Set(["image_gallery", "unknown", "video"]).has(contentType)
  ) {
    throw new TypeError("Douyin page context identity or type is invalid");
  }
  if (title !== null && (
    typeof title !== "string"
    || title.length === 0
    || title.length > 500
    || title !== title.replace(/\s+/gu, " ").trim()
    || /[\u0000-\u001F\u007F]/u.test(title)
    || /https?:\/\//iu.test(title)
  )) {
    throw new TypeError("Douyin page title is unsafe");
  }
  if (!validCanonicalPageUrl(value.page_url, contentId)) throw new TypeError("Douyin canonical page URL is invalid");
  if (!exactKeys(value.provenance, ["canonical_url", "content_id", "content_type", "title"])) {
    throw new TypeError("Douyin provenance is invalid");
  }
  const expectedProvenance = {
    canonical_url: new Set(["derived:stable_content_id_and_kind"]),
    content_id: new Set([
      "observed_verified:location_path_and_detail_surface",
      "observed_verified:short_link_canonical_and_detail_surface",
    ]),
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
      throw new TypeError(`Douyin provenance is invalid: ${field}`);
    }
  }
  if ((title === null) !== new Set(["invalid", "missing"]).has(value.provenance.title.status)) {
    throw new TypeError("Douyin title status does not match its value");
  }
  if ((contentType === "unknown") !== (value.provenance.content_type.status === "unknown")) {
    throw new TypeError("Douyin content type status does not match its value");
  }
  return value;
}

export function buildDouyinCapturePayload(value) {
  const facts = validateDouyinPageFacts(value);
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
