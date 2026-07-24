const PLATFORM = "xiaohongshu";
const SCHEMA_VERSION = "1.0";
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;
const STATUSES = new Set([
  "auth_required",
  "empty_unverified",
  "partial",
  "platform_changed",
  "ready",
  "verification_required",
]);
const COMPLETION_SIGNALS = new Set([
  "authoritative_end",
  "bounded_limit_reached",
  "more_available",
  "unknown",
]);
const ERROR_CODES = new Set([
  "X2N_ADAPTER_AUTH_EXPIRED",
  "X2N_PLATFORM_CHANGED",
  "X2N_POLICY_BLOCKED",
  "X2N_PROVENANCE_INCOMPLETE",
]);

function exactKeys(value, expected) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

function canonicalPageUrl(contentId) {
  return ["https:", "", "www.xiaohongshu.com", "explore", contentId].join("/");
}

/**
 * Extract one Owner-triggered, bounded visible batch. This function performs no
 * scrolling, network access, storage access, event synthesis, or account mutation.
 * Keep helpers nested because chrome.scripting serializes only the function body.
 */
export function extractXhsLikesVisibleBatch(input) {
  const platform = "xiaohongshu";
  const schemaVersion = "1.0";
  const safeId = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;
  const maxItems = 20;
  const base = (status, code, completionSignal = "unknown") => ({
    batch: {
      automatic_scroll: false,
      completion_signal: completionSignal,
      explicit_owner_action: true,
      visible_card_count: 0,
    },
    code,
    errors: [],
    inbox: {
      automatic_filing: false,
      disposition: "unclassified",
      taxonomy_mutation: false,
    },
    items: [],
    platform,
    schema_version: schemaVersion,
    status,
  });
  const surfaceFailure = (status, code) => {
    const result = base(status, code);
    result.errors.push({ card_index: null, code });
    return result;
  };
  const normalizeText = (raw) => {
    if (typeof raw !== "string") return null;
    const value = raw.replace(/\s+/gu, " ").trim();
    if (
      value.length === 0
      || value.length > 500
      || /[\u0000-\u001F\u007F]/u.test(value)
      || /https?:\/\//iu.test(value)
    ) return null;
    return value;
  };
  const idFromUrl = (raw, origin) => {
    if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) return null;
    try {
      const value = new URL(raw, origin);
      if (
        value.protocol !== "https:"
        || !new Set(["xiaohongshu.com", "www.xiaohongshu.com"]).has(value.hostname.toLowerCase())
        || value.username
        || value.password
        || value.port
      ) return null;
      const match = value.pathname.match(
        /^\/(?:explore|discovery\/item)\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\/?$/u,
      );
      return match ? match[1] : null;
    } catch {
      return null;
    }
  };
  const isHidden = (node) => node.hidden
    || node.getAttribute("aria-hidden") === "true"
    || node.closest("[hidden], [aria-hidden=\"true\"]") !== null;

  try {
    if (
      !input
      || input.ownerGesture !== true
      || input.maxItems !== maxItems
      || !new Set(["canary_20", "full_scan"]).has(input.scopeMode)
    ) return surfaceFailure("platform_changed", "X2N_POLICY_BLOCKED");
    if (!globalThis.document || !globalThis.location) {
      return surfaceFailure("platform_changed", "X2N_PLATFORM_CHANGED");
    }
    const locationUrl = new URL(globalThis.location.href);
    if (
      locationUrl.protocol !== "https:"
      || !new Set(["xiaohongshu.com", "www.xiaohongshu.com"]).has(locationUrl.hostname.toLowerCase())
    ) return surfaceFailure("platform_changed", "X2N_PLATFORM_CHANGED");

    const path = locationUrl.pathname.toLowerCase();
    if (
      path.includes("/login")
      || globalThis.document.querySelector('[data-x2n-state="auth_required"], input[type="password"]')
    ) return surfaceFailure("auth_required", "X2N_ADAPTER_AUTH_EXPIRED");
    if (
      path.includes("captcha")
      || path.includes("verify")
      || globalThis.document.querySelector('[data-x2n-state="verification_required"]')
    ) return surfaceFailure("verification_required", "X2N_POLICY_BLOCKED");

    let root = globalThis.document.querySelector('[data-x2n-surface="xhs-likes"]');
    if (!root && /^\/user\/profile\/[A-Za-z0-9._-]+\/?$/u.test(locationUrl.pathname)) {
      const selected = [...globalThis.document.querySelectorAll(
        '[aria-selected="true"], [data-active="true"], [class~="active"]',
      )].find((node) => normalizeText(node.textContent) === "赞过");
      if (selected) root = globalThis.document.querySelector("main, [role=\"main\"]");
    }
    if (!root) return surfaceFailure("platform_changed", "X2N_PLATFORM_CHANGED");

    const anchors = [...root.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]')]
      .filter((anchor) => !isHidden(anchor));
    const candidates = [];
    const seenNodes = new Set();
    for (const anchor of anchors) {
      const card = anchor.closest("[data-x2n-card], article, li") ?? anchor;
      if (seenNodes.has(card)) continue;
      seenNodes.add(card);
      candidates.push({ anchor, card });
    }
    const selectedCandidates = candidates.slice(0, maxItems);
    const result = base("ready", null);
    result.batch.visible_card_count = selectedCandidates.length;
    const logicalKeys = new Set();
    for (const [index, candidate] of selectedCandidates.entries()) {
      const contentId = idFromUrl(candidate.anchor.getAttribute("href"), locationUrl.origin);
      if (contentId === null || !safeId.test(contentId)) {
        result.errors.push({ card_index: index, code: "X2N_PROVENANCE_INCOMPLETE" });
        continue;
      }
      if (logicalKeys.has(contentId)) continue;
      logicalKeys.add(contentId);
      const declaredType = (candidate.card.getAttribute("data-x2n-note-type") ?? "").toLowerCase();
      let contentType = "unknown";
      if (declaredType === "video" || candidate.card.querySelector("video, [data-x2n-media=\"video\"]")) {
        contentType = "video";
      } else if (
        declaredType === "image_gallery"
        || declaredType === "image"
        || candidate.card.querySelector('[data-x2n-media="image_gallery"], [data-x2n-media="image"]')
      ) {
        contentType = "image_gallery";
      }
      const title = normalizeText(
        candidate.card.getAttribute("data-x2n-title")
          ?? candidate.card.querySelector('[data-x2n-field="title"], h1, h2, h3, [role="heading"]')?.textContent,
      );
      result.items.push({
        content_id: contentId,
        content_type: contentType,
        inbox_disposition: "unclassified",
        page_url: ["https:", "", "www.xiaohongshu.com", "explore", contentId].join("/"),
        title,
      });
    }
    result.batch.visible_card_count = logicalKeys.size + result.errors.length;
    if (result.errors.length > 0) {
      result.status = "partial";
      result.code = "X2N_PROVENANCE_INCOMPLETE";
      result.batch.completion_signal = "unknown";
      return result;
    }
    if (result.items.length === 0) {
      result.status = "empty_unverified";
      result.code = "X2N_PROVENANCE_INCOMPLETE";
      result.errors.push({ card_index: null, code: result.code });
      return result;
    }
    const declaredCompletion = root.getAttribute("data-x2n-completion");
    const paginationEnd = globalThis.document.querySelector(
      'button[aria-label="下一页"][disabled], [role="button"][aria-label="下一页"][aria-disabled="true"]',
    );
    if (input.scopeMode === "canary_20" && result.items.length === maxItems) {
      result.batch.completion_signal = "bounded_limit_reached";
    } else if (declaredCompletion === "authoritative_end" || paginationEnd) {
      result.batch.completion_signal = "authoritative_end";
    } else if (candidates.length > maxItems || declaredCompletion === "more_available") {
      result.batch.completion_signal = "more_available";
    }
    return result;
  } catch {
    return surfaceFailure("platform_changed", "X2N_PLATFORM_CHANGED");
  }
}

export function validateXhsLikesBatch(value) {
  if (!exactKeys(value, [
    "batch", "code", "errors", "inbox", "items", "platform", "schema_version", "status",
  ])) throw new TypeError("XHS likes facts contain unknown or missing fields");
  if (value.platform !== PLATFORM || value.schema_version !== SCHEMA_VERSION || !STATUSES.has(value.status)) {
    throw new TypeError("XHS likes facts identity or status mismatch");
  }
  if (!exactKeys(value.batch, [
    "automatic_scroll", "completion_signal", "explicit_owner_action", "visible_card_count",
  ])) throw new TypeError("XHS likes batch boundary is invalid");
  if (
    value.batch.automatic_scroll !== false
    || value.batch.explicit_owner_action !== true
    || !COMPLETION_SIGNALS.has(value.batch.completion_signal)
    || !Number.isInteger(value.batch.visible_card_count)
    || value.batch.visible_card_count < 0
    || value.batch.visible_card_count > 20
  ) throw new TypeError("XHS likes batch boundary is unsafe");
  if (
    !exactKeys(value.inbox, ["automatic_filing", "disposition", "taxonomy_mutation"])
    || value.inbox.automatic_filing !== false
    || value.inbox.disposition !== "unclassified"
    || value.inbox.taxonomy_mutation !== false
  ) throw new TypeError("XHS likes Inbox policy is unsafe");
  if (!Array.isArray(value.items) || value.items.length > 20 || !Array.isArray(value.errors)) {
    throw new TypeError("XHS likes item or error collection is invalid");
  }
  const logicalKeys = new Set();
  for (const item of value.items) {
    if (!exactKeys(item, [
      "content_id", "content_type", "inbox_disposition", "page_url", "title",
    ])) throw new TypeError("XHS likes item shape is invalid");
    if (
      !SAFE_ID.test(item.content_id)
      || !new Set(["image_gallery", "unknown", "video"]).has(item.content_type)
      || item.inbox_disposition !== "unclassified"
      || item.page_url !== canonicalPageUrl(item.content_id)
      || (item.title !== null && (
        typeof item.title !== "string" || item.title.length === 0 || item.title.length > 500 || /https?:\/\//iu.test(item.title)
      ))
    ) throw new TypeError("XHS likes item value is unsafe");
    if (logicalKeys.has(item.content_id)) throw new TypeError("XHS likes batch contains a duplicate logical item");
    logicalKeys.add(item.content_id);
  }
  const errorIndexes = new Set();
  for (const error of value.errors) {
    if (
      !exactKeys(error, ["card_index", "code"])
      || !ERROR_CODES.has(error.code)
      || (error.card_index !== null && (
        !Number.isInteger(error.card_index)
        || error.card_index < 0
        || error.card_index >= value.batch.visible_card_count
        || errorIndexes.has(error.card_index)
      ))
    ) throw new TypeError("XHS likes error evidence is invalid");
    if (error.card_index !== null) errorIndexes.add(error.card_index);
  }
  if (value.code !== null && !ERROR_CODES.has(value.code)) throw new TypeError("XHS likes error code is invalid");
  if (value.status === "ready") {
    if (
      value.code !== null
      || value.errors.length !== 0
      || value.items.length === 0
      || value.items.length !== value.batch.visible_card_count
    ) throw new TypeError("Ready XHS likes batch is incomplete");
  } else if (
    value.code === null
    || value.errors.length === 0
    || !value.errors.some((error) => error.code === value.code)
  ) {
    throw new TypeError("Non-ready XHS likes batch lacks error evidence");
  } else if (value.status === "partial") {
    if (
      value.errors.some((error) => error.card_index === null)
      || value.items.length + value.errors.length !== value.batch.visible_card_count
    ) throw new TypeError("Partial XHS likes batch lacks per-card evidence");
  } else if (
    value.batch.visible_card_count !== 0
    || value.items.length !== 0
    || value.errors.length !== 1
    || value.errors[0].card_index !== null
  ) {
    throw new TypeError("Blocked XHS likes batch has invalid surface evidence");
  }
  if (
    new Set(["authoritative_end", "bounded_limit_reached"]).has(value.batch.completion_signal)
    && value.status !== "ready"
  ) throw new TypeError("Non-ready XHS likes batch cannot complete a scope");
  return value;
}
