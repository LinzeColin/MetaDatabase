const PLATFORM = "weibo";
const SCHEMA_VERSION = "1.0";
const PLATFORM_CHANGED = "X2N_PLATFORM_CHANGED";
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/u;
const FAILURE_REASONS = Object.freeze(new Set([
  "content_type_signal_mismatch",
  "detail_surface_ambiguous",
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

function isSyntheticIdentity(contentId) {
  return contentId.startsWith("synthetic-wb-status-");
}

function canonicalPageUrl(contentId) {
  return ["https:", "", "www.weibo.com", "detail", contentId].join("/");
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
    || value.hostname.toLowerCase() !== "www.weibo.com"
    || value.username
    || value.password
    || value.port
  ) return null;
  const detail = value.pathname.match(/^\/detail\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
  return detail ? { contentId: detail[1] } : null;
}

function validCanonicalPageUrl(value, contentId) {
  if (value !== canonicalPageUrl(contentId)) return false;
  const parsed = parseDetailUrl(value);
  if (!parsed || parsed.contentId !== contentId) return false;
  const url = new URL(value);
  return url.search === "" && url.hash === "";
}

/**
 * Runs in Chrome's isolated world through chrome.scripting.executeScript.
 * Helpers are nested because Chrome serializes this function without module scope.
 */
export function extractWeiboCurrentPage() {
  const schemaVersion = "1.0";
  const platform = "weibo";
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
    if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) return null;
    let value;
    try {
      value = new URL(raw, base);
    } catch {
      return null;
    }
    if (
      value.protocol !== "https:"
      || value.hostname.toLowerCase() !== "www.weibo.com"
      || value.username
      || value.password
      || value.port
    ) return null;
    const detail = value.pathname.match(/^\/detail\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
    return detail ? { contentId: detail[1] } : null;
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
    if (!current || !safeId.test(current.contentId) || !current.contentId.startsWith("synthetic-wb-status-")) {
      return failure("unsupported_detail_url");
    }

    const canonicalSignals = [
      globalThis.document.querySelector('link[rel~="canonical"]')?.getAttribute("href"),
      globalThis.document.querySelector('meta[property="og:url"]')?.getAttribute("content"),
    ].filter((value) => value !== null && value !== undefined);
    for (const raw of canonicalSignals) {
      const inspected = inspectUrl(raw, globalThis.location.origin);
      if (!inspected || !safeId.test(inspected.contentId)) return failure("stable_id_signal_invalid");
      if (inspected.contentId !== current.contentId) return failure("stable_id_signal_mismatch");
    }

    const detailSelectors = [
      '[data-x2n-surface="weibo-status-detail"]',
      "main article[data-mid]",
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

    const identityNodes = [
      ...(detailRoot.hasAttribute("data-mid") ? [detailRoot] : []),
      ...detailRoot.querySelectorAll("[data-mid]"),
    ];
    if (identityNodes.length === 0) return failure("stable_id_signal_invalid");
    const identitySignals = identityNodes.map((node) => node.getAttribute("data-mid"));
    if (identitySignals.some((value) => typeof value !== "string" || !safeId.test(value))) {
      return failure("stable_id_signal_invalid");
    }
    if (identitySignals.some((value) => value !== current.contentId)) {
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

    const declaredType = (detailRoot.getAttribute("data-x2n-content-type") ?? "").toLowerCase();
    if (!new Set(["", "image_gallery", "mixed", "text", "unknown", "video"]).has(declaredType)) {
      return failure("content_type_signal_mismatch");
    }
    const typeSignals = new Set();
    if (declaredType === "text" || detailRoot.querySelector('[data-x2n-body="status-text"]') !== null) {
      typeSignals.add("text");
    }
    if (
      declaredType === "image_gallery"
      || detailRoot.querySelector('[data-x2n-media="image-gallery"]') !== null
    ) typeSignals.add("image_gallery");
    if (declaredType === "video" || detailRoot.querySelector('[data-x2n-media="video"]') !== null) {
      typeSignals.add("video");
    }
    const contentType = declaredType === "mixed" || typeSignals.size > 1
      ? "mixed"
      : ([...typeSignals][0] ?? "unknown");
    const sourceByType = {
      image_gallery: "detail_image_marker",
      mixed: "detail_mixed_marker",
      text: "detail_text_marker",
      video: "detail_video_marker",
    };
    const contentTypeSource = sourceByType[contentType] ?? null;
    const contentTypeStatus = contentType === "unknown" ? "unknown" : "observed";

    return {
      page_context: {
        content_id: current.contentId,
        content_type: contentType,
        title: title.value,
      },
      page_url: ["https:", "", "www.weibo.com", "detail", current.contentId].join("/"),
      platform,
      provenance: {
        canonical_url: { source: "stable_mid", status: "derived" },
        content_id: { source: "location_path_and_status_surface", status: "observed_verified" },
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

export function validateWeiboPageFacts(value) {
  if (!exactKeys(value, ["code", "platform", "reason", "schema_version", "status"])
    && !exactKeys(value, ["page_context", "page_url", "platform", "provenance", "schema_version", "status"])) {
    throw new TypeError("Weibo page facts contain unknown or missing fields");
  }
  if (value.schema_version !== SCHEMA_VERSION || value.platform !== PLATFORM) {
    throw new TypeError("Weibo page facts identity mismatch");
  }
  if (value.status === "platform_changed") {
    if (value.code !== PLATFORM_CHANGED || !FAILURE_REASONS.has(value.reason)) {
      throw new TypeError("Weibo platform-changed result is invalid");
    }
    return value;
  }
  if (value.status !== "ready") throw new TypeError("Weibo page facts status is invalid");
  if (!exactKeys(value.page_context, ["content_id", "content_type", "title"])) {
    throw new TypeError("Weibo page context is invalid");
  }
  const { content_id: contentId, content_type: contentType, title } = value.page_context;
  const parsed = parseDetailUrl(value.page_url);
  if (
    !SAFE_ID.test(contentId)
    || !parsed
    || parsed.contentId !== contentId
    || !isSyntheticIdentity(contentId)
    || !new Set(["image_gallery", "mixed", "text", "unknown", "video"]).has(contentType)
  ) throw new TypeError("Weibo page context identity or type is invalid");
  if (title !== null && (
    typeof title !== "string"
    || title.length === 0
    || title.length > 500
    || title !== title.replace(/\s+/gu, " ").trim()
    || /[\u0000-\u001F\u007F]/u.test(title)
    || /https?:\/\//iu.test(title)
  )) throw new TypeError("Weibo page title is unsafe");
  if (!validCanonicalPageUrl(value.page_url, contentId)) {
    throw new TypeError("Weibo canonical page URL is invalid");
  }
  if (!exactKeys(value.provenance, ["canonical_url", "content_id", "content_type", "title"])) {
    throw new TypeError("Weibo provenance is invalid");
  }
  const expectedProvenance = {
    canonical_url: new Set(["derived:stable_mid"]),
    content_id: new Set(["observed_verified:location_path_and_status_surface"]),
    content_type: new Set([
      "observed:detail_image_marker",
      "observed:detail_mixed_marker",
      "observed:detail_text_marker",
      "observed:detail_video_marker",
      "unknown:null",
    ]),
    title: new Set(["invalid:null", "missing:null", "observed:detail_heading", "observed:open_graph"]),
  };
  for (const [field, allowed] of Object.entries(expectedProvenance)) {
    const item = value.provenance[field];
    if (!exactKeys(item, ["source", "status"]) || !allowed.has(`${item.status}:${String(item.source)}`)) {
      throw new TypeError(`Weibo provenance is invalid: ${field}`);
    }
  }
  if ((title === null) !== new Set(["invalid", "missing"]).has(value.provenance.title.status)) {
    throw new TypeError("Weibo title status does not match its value");
  }
  if ((contentType === "unknown") !== (value.provenance.content_type.status === "unknown")) {
    throw new TypeError("Weibo content type status does not match its value");
  }
  return value;
}

export function buildWeiboCapturePayload(value) {
  const facts = validateWeiboPageFacts(value);
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
