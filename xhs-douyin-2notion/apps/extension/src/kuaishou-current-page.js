const PLATFORM = "kuaishou";
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
  return contentId.startsWith("synthetic-ks-video-");
}

function canonicalPageUrl(contentId) {
  return ["https:", "", "www.kuaishou.com", "short-video", contentId].join("/");
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
    || value.hostname.toLowerCase() !== "www.kuaishou.com"
    || value.username
    || value.password
    || value.port
  ) return null;
  const detail = value.pathname.match(/^\/short-video\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
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
 * Every helper is nested because Chrome serializes the function without module scope.
 */
export function extractKuaishouCurrentPage() {
  const schemaVersion = "1.0";
  const platform = "kuaishou";
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
      || value.hostname.toLowerCase() !== "www.kuaishou.com"
      || value.username
      || value.password
      || value.port
    ) return null;
    const detail = value.pathname.match(/^\/short-video\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
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
    if (!current || !safeId.test(current.contentId) || !current.contentId.startsWith("synthetic-ks-video-")) {
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
      '[data-x2n-surface="kuaishou-video-detail"]',
      "main [data-photo-id]",
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
      ...(detailRoot.hasAttribute("data-photo-id") ? [detailRoot] : []),
      ...detailRoot.querySelectorAll("[data-photo-id]"),
    ];
    if (identityNodes.length === 0) return failure("stable_id_signal_invalid");
    const identitySignals = identityNodes.map((node) => node.getAttribute("data-photo-id"));
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
    if (
      !new Set(["", "unknown", "video"]).has(declaredType)
      || detailRoot.querySelector('[data-x2n-media="image-gallery"]') !== null
      || detailRoot.querySelector('[data-x2n-body="article-text"]') !== null
    ) return failure("content_type_signal_mismatch");
    const contentType = declaredType === "video" || detailRoot.querySelector('[data-x2n-media="video"]') !== null
      ? "video"
      : "unknown";
    const contentTypeSource = contentType === "video" ? "detail_video_marker" : null;
    const contentTypeStatus = contentType === "video" ? "observed" : "unknown";

    return {
      page_context: {
        content_id: current.contentId,
        content_type: contentType,
        title: title.value,
      },
      page_url: ["https:", "", "www.kuaishou.com", "short-video", current.contentId].join("/"),
      platform,
      provenance: {
        canonical_url: { source: "stable_photo_id", status: "derived" },
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

export function validateKuaishouPageFacts(value) {
  if (!exactKeys(value, ["code", "platform", "reason", "schema_version", "status"])
    && !exactKeys(value, ["page_context", "page_url", "platform", "provenance", "schema_version", "status"])) {
    throw new TypeError("Kuaishou page facts contain unknown or missing fields");
  }
  if (value.schema_version !== SCHEMA_VERSION || value.platform !== PLATFORM) {
    throw new TypeError("Kuaishou page facts identity mismatch");
  }
  if (value.status === "platform_changed") {
    if (value.code !== PLATFORM_CHANGED || !FAILURE_REASONS.has(value.reason)) {
      throw new TypeError("Kuaishou platform-changed result is invalid");
    }
    return value;
  }
  if (value.status !== "ready") throw new TypeError("Kuaishou page facts status is invalid");
  if (!exactKeys(value.page_context, ["content_id", "content_type", "title"])) {
    throw new TypeError("Kuaishou page context is invalid");
  }
  const { content_id: contentId, content_type: contentType, title } = value.page_context;
  const parsed = parseDetailUrl(value.page_url);
  if (
    !SAFE_ID.test(contentId)
    || !parsed
    || parsed.contentId !== contentId
    || !isSyntheticIdentity(contentId)
    || !new Set(["unknown", "video"]).has(contentType)
  ) throw new TypeError("Kuaishou page context identity or type is invalid");
  if (title !== null && (
    typeof title !== "string"
    || title.length === 0
    || title.length > 500
    || title !== title.replace(/\s+/gu, " ").trim()
    || /[\u0000-\u001F\u007F]/u.test(title)
    || /https?:\/\//iu.test(title)
  )) throw new TypeError("Kuaishou page title is unsafe");
  if (!validCanonicalPageUrl(value.page_url, contentId)) {
    throw new TypeError("Kuaishou canonical page URL is invalid");
  }
  if (!exactKeys(value.provenance, ["canonical_url", "content_id", "content_type", "title"])) {
    throw new TypeError("Kuaishou provenance is invalid");
  }
  const expectedProvenance = {
    canonical_url: new Set(["derived:stable_photo_id"]),
    content_id: new Set(["observed_verified:location_path_and_detail_surface"]),
    content_type: new Set(["observed:detail_video_marker", "unknown:null"]),
    title: new Set(["invalid:null", "missing:null", "observed:detail_heading", "observed:open_graph"]),
  };
  for (const [field, allowed] of Object.entries(expectedProvenance)) {
    const item = value.provenance[field];
    if (!exactKeys(item, ["source", "status"]) || !allowed.has(`${item.status}:${String(item.source)}`)) {
      throw new TypeError(`Kuaishou provenance is invalid: ${field}`);
    }
  }
  if ((title === null) !== new Set(["invalid", "missing"]).has(value.provenance.title.status)) {
    throw new TypeError("Kuaishou title status does not match its value");
  }
  if ((contentType === "unknown") !== (value.provenance.content_type.status === "unknown")) {
    throw new TypeError("Kuaishou content type status does not match its value");
  }
  return value;
}

export function buildKuaishouCapturePayload(value) {
  const facts = validateKuaishouPageFacts(value);
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
