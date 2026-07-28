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
export function extractXhsFavoritesVisibleBatch(input) {
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
    collection: { id: null, name_private: null, status: "unavailable" },
    errors: [],
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
      || !new Set(["canary_20", "owner_mvp_20", "full_scan"]).has(input.scopeMode)
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

    let root = globalThis.document.querySelector('[data-x2n-surface="xhs-favorites"]');
    if (!root && /^\/user\/profile\/[A-Za-z0-9._-]+\/?$/u.test(locationUrl.pathname)) {
      const selected = [...globalThis.document.querySelectorAll(
        '[aria-selected="true"], [data-active="true"], [class~="active"]',
      )].find((node) => normalizeText(node.textContent) === "收藏");
      if (selected) root = globalThis.document.querySelector("main, [role=\"main\"]");
    }
    if (!root) return surfaceFailure("platform_changed", "X2N_PLATFORM_CHANGED");

    const rootCollectionId = root.getAttribute("data-x2n-collection-id");
    const rootCollectionName = normalizeText(root.getAttribute("data-x2n-collection-name"));
    const collection = rootCollectionId === null && rootCollectionName === null
      ? { id: null, name_private: null, status: "unavailable" }
      : safeId.test(rootCollectionId ?? "") && rootCollectionName !== null
        ? { id: rootCollectionId, name_private: rootCollectionName, status: "observed" }
        : null;
    if (collection === null) {
      return surfaceFailure("partial", "X2N_PROVENANCE_INCOMPLETE");
    }

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
    result.collection = collection;
    result.batch.visible_card_count = selectedCandidates.length;
    const logicalKeys = new Set();
    for (const [index, candidate] of selectedCandidates.entries()) {
      const contentId = idFromUrl(candidate.anchor.getAttribute("href"), locationUrl.origin);
      const cardCollectionId = candidate.card.getAttribute("data-x2n-collection-id") ?? collection.id;
      const rawCollectionName = candidate.card.getAttribute("data-x2n-collection-name");
      const cardCollectionName = rawCollectionName === null ? collection.name_private : normalizeText(rawCollectionName);
      if (
        contentId === null
        || !safeId.test(contentId)
        || ((cardCollectionId === null) !== (cardCollectionName === null))
        || (cardCollectionId !== null && !safeId.test(cardCollectionId))
      ) {
        result.errors.push({ card_index: index, code: "X2N_PROVENANCE_INCOMPLETE" });
        continue;
      }
      const logicalKey = `${contentId}:${String(cardCollectionId)}`;
      if (logicalKeys.has(logicalKey)) continue;
      logicalKeys.add(logicalKey);
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
        collection_id: cardCollectionId,
        collection_name_private: cardCollectionName,
        content_id: contentId,
        content_type: contentType,
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
    if (new Set(["canary_20", "owner_mvp_20"]).has(input.scopeMode) && result.items.length === maxItems) {
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

export function validateXhsFavoritesBatch(value) {
  if (!exactKeys(value, [
    "batch", "code", "collection", "errors", "items", "platform", "schema_version", "status",
  ])) throw new TypeError("XHS favorites facts contain unknown or missing fields");
  if (value.platform !== PLATFORM || value.schema_version !== SCHEMA_VERSION || !STATUSES.has(value.status)) {
    throw new TypeError("XHS favorites facts identity or status mismatch");
  }
  if (!exactKeys(value.batch, [
    "automatic_scroll", "completion_signal", "explicit_owner_action", "visible_card_count",
  ])) throw new TypeError("XHS favorites batch boundary is invalid");
  if (
    value.batch.automatic_scroll !== false
    || value.batch.explicit_owner_action !== true
    || !COMPLETION_SIGNALS.has(value.batch.completion_signal)
    || !Number.isInteger(value.batch.visible_card_count)
    || value.batch.visible_card_count < 0
    || value.batch.visible_card_count > 20
  ) throw new TypeError("XHS favorites batch boundary is unsafe");
  if (!exactKeys(value.collection, ["id", "name_private", "status"])) {
    throw new TypeError("XHS favorites collection mapping is invalid");
  }
  if (
    !new Set(["observed", "unavailable"]).has(value.collection.status)
    || ((value.collection.id === null) !== (value.collection.name_private === null))
    || ((value.collection.status === "unavailable") !== (value.collection.id === null))
    || (value.collection.id !== null && !SAFE_ID.test(value.collection.id))
    || (value.collection.name_private !== null && (
      typeof value.collection.name_private !== "string"
      || value.collection.name_private.length === 0
      || value.collection.name_private.length > 500
      || /https?:\/\//iu.test(value.collection.name_private)
    ))
  ) throw new TypeError("XHS favorites collection mapping is unsafe");
  if (!Array.isArray(value.items) || value.items.length > 20 || !Array.isArray(value.errors)) {
    throw new TypeError("XHS favorites item or error collection is invalid");
  }
  const logicalKeys = new Set();
  for (const item of value.items) {
    if (!exactKeys(item, [
      "collection_id", "collection_name_private", "content_id", "content_type", "page_url", "title",
    ])) throw new TypeError("XHS favorites item shape is invalid");
    if (
      !SAFE_ID.test(item.content_id)
      || !new Set(["image_gallery", "unknown", "video"]).has(item.content_type)
      || item.page_url !== canonicalPageUrl(item.content_id)
      || ((item.collection_id === null) !== (item.collection_name_private === null))
      || (item.collection_id !== null && !SAFE_ID.test(item.collection_id))
      || (item.collection_name_private !== null && (
        typeof item.collection_name_private !== "string"
        || item.collection_name_private.length === 0
        || item.collection_name_private.length > 500
        || /[\u0000-\u001F\u007F]/u.test(item.collection_name_private)
        || /https?:\/\//iu.test(item.collection_name_private)
      ))
      || (item.title !== null && (
        typeof item.title !== "string" || item.title.length === 0 || item.title.length > 500 || /https?:\/\//iu.test(item.title)
      ))
    ) throw new TypeError("XHS favorites item value is unsafe");
    const logicalKey = `${item.content_id}:${String(item.collection_id)}`;
    if (logicalKeys.has(logicalKey)) throw new TypeError("XHS favorites batch contains a duplicate logical item");
    logicalKeys.add(logicalKey);
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
    ) throw new TypeError("XHS favorites error evidence is invalid");
    if (error.card_index !== null) errorIndexes.add(error.card_index);
  }
  if (value.code !== null && !ERROR_CODES.has(value.code)) throw new TypeError("XHS favorites error code is invalid");
  if (value.status === "ready") {
    if (
      value.code !== null
      || value.errors.length !== 0
      || value.items.length === 0
      || value.items.length !== value.batch.visible_card_count
    ) throw new TypeError("Ready XHS favorites batch is incomplete");
  } else if (
    value.code === null
    || value.errors.length === 0
    || !value.errors.some((error) => error.code === value.code)
  ) {
    throw new TypeError("Non-ready XHS favorites batch lacks error evidence");
  } else if (value.status === "partial") {
    if (
      value.errors.some((error) => error.card_index === null)
      || value.items.length + value.errors.length !== value.batch.visible_card_count
    ) throw new TypeError("Partial XHS favorites batch lacks per-card evidence");
  } else if (
    value.batch.visible_card_count !== 0
    || value.items.length !== 0
    || value.errors.length !== 1
    || value.errors[0].card_index !== null
  ) {
    throw new TypeError("Blocked XHS favorites batch has invalid surface evidence");
  }
  if (
    new Set(["authoritative_end", "bounded_limit_reached"]).has(value.batch.completion_signal)
    && value.status !== "ready"
  ) throw new TypeError("Non-ready XHS favorites batch cannot complete a scope");
  return value;
}
