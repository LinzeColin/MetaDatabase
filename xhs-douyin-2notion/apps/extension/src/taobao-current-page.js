const PLATFORM = "taobao";
const SCHEMA_VERSION = "1.0";
const PLATFORM_CHANGED = "X2N_PLATFORM_CHANGED";
const SAFE_ITEM_ID = /^[1-9][0-9]{5,20}$/u;
const SYNTHETIC_ITEM_ID = /^9900000000000[0-9]{6}$/u;
const FAILURE_REASONS = Object.freeze(new Set([
  "content_type_signal_mismatch",
  "detail_surface_ambiguous",
  "detail_surface_missing",
  "document_unavailable",
  "dom_unreadable",
  "stable_id_signal_invalid",
  "stable_id_signal_mismatch",
  "unsupported_item_url",
]));

function exactKeys(value, expected) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

function canonicalPageUrl() {
  return ["https:", "", "item.taobao.com", "item.htm"].join("/");
}

function parseItemUrl(raw, base, allowSyntheticControl = false) {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) return null;
  let value;
  try {
    value = new URL(raw, base);
  } catch {
    return null;
  }
  if (
    value.protocol !== "https:"
    || value.hostname.toLowerCase() !== "item.taobao.com"
    || value.username
    || value.password
    || value.port
    || value.hash
    || !/^\/item\.htm\/?$/u.test(value.pathname)
  ) return null;
  const keys = [...value.searchParams.keys()].sort();
  const expectedKeys = allowSyntheticControl ? ["id", "x2n_fixture"] : ["id"];
  if (JSON.stringify(keys) !== JSON.stringify(expectedKeys)) return null;
  if (value.searchParams.getAll("id").length !== 1) return null;
  if (allowSyntheticControl) {
    if (value.searchParams.getAll("x2n_fixture").length !== 1) return null;
    if (value.searchParams.get("x2n_fixture") !== "1") return null;
  }
  const contentId = value.searchParams.get("id") ?? "";
  return SAFE_ITEM_ID.test(contentId) ? { contentId } : null;
}

function validCanonicalPageUrl(value) {
  if (value !== canonicalPageUrl()) return false;
  const parsed = new URL(value);
  return parsed.protocol === "https:"
    && parsed.hostname === "item.taobao.com"
    && parsed.pathname === "/item.htm"
    && parsed.search === ""
    && parsed.hash === "";
}

/**
 * Runs in Chrome's isolated world through chrome.scripting.executeScript.
 * Helpers are nested because Chrome serializes this function without module scope.
 */
export function extractTaobaoCurrentPage() {
  const schemaVersion = "1.0";
  const platform = "taobao";
  const platformChanged = "X2N_PLATFORM_CHANGED";
  const safeItemId = /^[1-9][0-9]{5,20}$/u;
  const syntheticItemId = /^9900000000000[0-9]{6}$/u;
  const failure = (reason) => ({
    code: platformChanged,
    platform,
    reason,
    schema_version: schemaVersion,
    status: "platform_changed",
  });
  const inspectUrl = (raw, base, allowSyntheticControl = false) => {
    if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) return null;
    let value;
    try {
      value = new URL(raw, base);
    } catch {
      return null;
    }
    if (
      value.protocol !== "https:"
      || value.hostname.toLowerCase() !== "item.taobao.com"
      || value.username
      || value.password
      || value.port
      || value.hash
      || !/^\/item\.htm\/?$/u.test(value.pathname)
    ) return null;
    const keys = [...value.searchParams.keys()].sort();
    const expectedKeys = allowSyntheticControl ? ["id", "x2n_fixture"] : ["id"];
    if (JSON.stringify(keys) !== JSON.stringify(expectedKeys)) return null;
    if (value.searchParams.getAll("id").length !== 1) return null;
    if (allowSyntheticControl) {
      if (value.searchParams.getAll("x2n_fixture").length !== 1) return null;
      if (value.searchParams.get("x2n_fixture") !== "1") return null;
    }
    const contentId = value.searchParams.get("id") ?? "";
    return safeItemId.test(contentId) ? { contentId } : null;
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
    const current = inspectUrl(globalThis.location.href, globalThis.location.origin, true);
    if (!current || !syntheticItemId.test(current.contentId)) return failure("unsupported_item_url");

    const canonicalSignals = [
      globalThis.document.querySelector('link[rel~="canonical"]')?.getAttribute("href"),
      globalThis.document.querySelector('meta[property="og:url"]')?.getAttribute("content"),
    ].filter((value) => value !== null && value !== undefined);
    for (const raw of canonicalSignals) {
      const inspected = inspectUrl(raw, globalThis.location.origin);
      if (!inspected || !safeItemId.test(inspected.contentId)) return failure("stable_id_signal_invalid");
      if (inspected.contentId !== current.contentId) return failure("stable_id_signal_mismatch");
    }

    const detailSelectors = [
      '[data-x2n-surface="taobao-item-detail"]',
      'main [data-x2n-kind="item"][data-num-iid]',
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
      ...(detailRoot.hasAttribute("data-num-iid") ? [detailRoot] : []),
      ...detailRoot.querySelectorAll("[data-num-iid]"),
    ];
    if (identityNodes.length === 0) return failure("stable_id_signal_invalid");
    const identitySignals = identityNodes.map((node) => node.getAttribute("data-num-iid"));
    if (identitySignals.some((value) => typeof value !== "string" || !safeItemId.test(value))) {
      return failure("stable_id_signal_invalid");
    }
    if (identitySignals.some((value) => value !== current.contentId)) {
      return failure("stable_id_signal_mismatch");
    }

    const titleCandidates = [
      [globalThis.document.querySelector('meta[property="og:title"]')?.getAttribute("content"), "open_graph"],
      [detailRoot.querySelector('[data-x2n-field="title"]')?.textContent, "item_heading"],
      [detailRoot.querySelector("h1")?.textContent, "item_heading"],
      [detailRoot.querySelector('[role="heading"][aria-level="1"]')?.textContent, "item_heading"],
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
    if (detailRoot.querySelector('[data-x2n-body="item-text"]') !== null) typeSignals.add("text");
    if (detailRoot.querySelector('[data-x2n-media="image-gallery"]') !== null) typeSignals.add("image_gallery");
    if (detailRoot.querySelector('[data-x2n-media="video"]') !== null) typeSignals.add("video");
    if (declaredType === "mixed" && typeSignals.size < 2) return failure("content_type_signal_mismatch");
    if (
      new Set(["image_gallery", "text", "video"]).has(declaredType)
      && (typeSignals.size !== 1 || !typeSignals.has(declaredType))
    ) return failure("content_type_signal_mismatch");
    if (declaredType === "unknown" && typeSignals.size !== 0) return failure("content_type_signal_mismatch");
    const contentType = declaredType || (typeSignals.size > 1 ? "mixed" : ([...typeSignals][0] ?? "unknown"));
    const sourceByType = {
      image_gallery: "item_image_marker",
      mixed: "item_mixed_markers",
      text: "item_text_marker",
      video: "item_video_marker",
    };
    const contentTypeSource = sourceByType[contentType] ?? null;
    const contentTypeStatus = contentType === "unknown" ? "unknown" : "observed";

    return {
      page_context: {
        content_id: current.contentId,
        content_type: contentType,
        title: title.value,
      },
      page_url: ["https:", "", "item.taobao.com", "item.htm"].join("/"),
      platform,
      provenance: {
        canonical_url: { source: "stable_num_iid_and_official_item_route", status: "derived" },
        content_id: { source: "location_semantic_id_and_item_surface", status: "observed_verified" },
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

export function validateTaobaoPageFacts(value) {
  if (!exactKeys(value, ["code", "platform", "reason", "schema_version", "status"])
    && !exactKeys(value, ["page_context", "page_url", "platform", "provenance", "schema_version", "status"])) {
    throw new TypeError("Taobao page facts contain unknown or missing fields");
  }
  if (value.schema_version !== SCHEMA_VERSION || value.platform !== PLATFORM) {
    throw new TypeError("Taobao page facts identity mismatch");
  }
  if (value.status === "platform_changed") {
    if (value.code !== PLATFORM_CHANGED || !FAILURE_REASONS.has(value.reason)) {
      throw new TypeError("Taobao platform-changed result is invalid");
    }
    return value;
  }
  if (value.status !== "ready") throw new TypeError("Taobao page facts status is invalid");
  if (!exactKeys(value.page_context, ["content_id", "content_type", "title"])) {
    throw new TypeError("Taobao page context is invalid");
  }
  const { content_id: contentId, content_type: contentType, title } = value.page_context;
  if (
    !SYNTHETIC_ITEM_ID.test(contentId)
    || !new Set(["image_gallery", "mixed", "text", "unknown", "video"]).has(contentType)
  ) throw new TypeError("Taobao page context identity or type is invalid");
  if (title !== null && (
    typeof title !== "string"
    || title.length === 0
    || title.length > 500
    || title !== title.replace(/\s+/gu, " ").trim()
    || /[\u0000-\u001F\u007F]/u.test(title)
    || /https?:\/\//iu.test(title)
  )) throw new TypeError("Taobao page title is unsafe");
  if (!validCanonicalPageUrl(value.page_url)) {
    throw new TypeError("Taobao canonical page URL is invalid");
  }
  if (!exactKeys(value.provenance, ["canonical_url", "content_id", "content_type", "title"])) {
    throw new TypeError("Taobao provenance is invalid");
  }
  const expectedProvenance = {
    canonical_url: new Set(["derived:stable_num_iid_and_official_item_route"]),
    content_id: new Set(["observed_verified:location_semantic_id_and_item_surface"]),
    content_type: new Set([
      "observed:item_image_marker",
      "observed:item_mixed_markers",
      "observed:item_text_marker",
      "observed:item_video_marker",
      "unknown:null",
    ]),
    title: new Set(["invalid:null", "missing:null", "observed:item_heading", "observed:open_graph"]),
  };
  for (const [field, allowed] of Object.entries(expectedProvenance)) {
    const item = value.provenance[field];
    if (!exactKeys(item, ["source", "status"]) || !allowed.has(`${item.status}:${String(item.source)}`)) {
      throw new TypeError(`Taobao provenance is invalid: ${field}`);
    }
  }
  if ((title === null) !== new Set(["invalid", "missing"]).has(value.provenance.title.status)) {
    throw new TypeError("Taobao title status does not match its value");
  }
  if ((contentType === "unknown") !== (value.provenance.content_type.status === "unknown")) {
    throw new TypeError("Taobao content type status does not match its value");
  }
  return value;
}

export function buildTaobaoCapturePayload(value) {
  const facts = validateTaobaoPageFacts(value);
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
