const PLATFORM = "douyin";
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
const COMPLETION_SIGNALS = new Set(["bounded_limit_reached", "more_available", "unknown"]);
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

export function extractDouyinVisibleBatch(input) {
    const mode = input?.mode;
    const selectedLabel = mode === "favorites" ? "收藏" : mode === "likes" ? "喜欢" : null;
    const expectedListSurface = mode === "favorites"
      ? "user-favorite-list"
      : mode === "likes"
        ? "user-like-list"
        : null;
    // The current desktop profile surface exposes an active tab panel instead
    // of the older dedicated list node.  Keep both deliberately narrow
    // contracts: accepting a generic page root would make footer/recommendation
    // cards look like owner-selected collection content.
    const expectedTabSurface = mode === "favorites"
      ? "user-favorite-tab"
      : mode === "likes"
        ? "user-like-tab"
        : null;
    const platform = "douyin";
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
      items: [],
      platform,
      schema_version: schemaVersion,
      status,
    });
    const failure = (status, code) => {
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
        || /(?:https?|file|data):\/\//iu.test(value)
      ) return null;
      return value;
    };
    const isHidden = (node) => node.hidden
      || node.getAttribute("aria-hidden") === "true"
      || node.closest("[hidden], [aria-hidden=\"true\"]") !== null;
    const parseCardIdentity = (raw, origin) => {
      if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) return null;
      try {
        const value = new URL(raw, origin);
        if (
          value.protocol !== "https:"
          || value.hostname.toLowerCase() !== "www.douyin.com"
          || value.username
          || value.password
          || value.port
        ) return null;
        const match = value.pathname.match(/^\/(video|note)\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\/?$/u);
        if (!match) return null;
        return { contentId: match[2], contentType: match[1] === "video" ? "video" : "image_gallery" };
      } catch {
        return null;
      }
    };
    try {
      if (
        !input
        || selectedLabel === null
        || input.ownerGesture !== true
        || input.maxItems !== maxItems
        || !new Set(["canary_20", "owner_mvp_20"]).has(input.scopeMode)
      ) return failure("platform_changed", "X2N_POLICY_BLOCKED");
      if (!globalThis.document || !globalThis.location) return failure("platform_changed", "X2N_PLATFORM_CHANGED");
      const locationUrl = new URL(globalThis.location.href);
      if (locationUrl.protocol !== "https:" || locationUrl.hostname.toLowerCase() !== "www.douyin.com") {
        return failure("platform_changed", "X2N_PLATFORM_CHANGED");
      }
      const path = locationUrl.pathname.toLowerCase();
      if (
        path.includes("/login")
        || globalThis.document.querySelector('[data-x2n-state="auth_required"], input[type="password"]')
      ) return failure("auth_required", "X2N_ADAPTER_AUTH_EXPIRED");
      if (
        path.includes("captcha")
        || path.includes("verify")
        || globalThis.document.querySelector('[data-x2n-state="verification_required"]')
      ) return failure("verification_required", "X2N_POLICY_BLOCKED");

      const selectedControls = [...globalThis.document.querySelectorAll([
        'button[aria-selected="true"]',
        'button[data-active="true"]',
        'a[aria-selected="true"]',
        'a[data-active="true"]',
        '[role="tab"][aria-selected="true"]',
        '[role="tab"][data-active="true"]',
        '[role="tab"].active',
      ].join(", "))].filter((node) => !isHidden(node) && normalizeText(node.textContent) === selectedLabel);
      if (selectedControls.length !== 1 || !expectedListSurface || !expectedTabSurface) {
        return failure("platform_changed", "X2N_PLATFORM_CHANGED");
      }
      const legacyRoots = [...globalThis.document.querySelectorAll(`[data-e2e="${expectedListSurface}"]`)]
        .filter((node) => !isHidden(node));
      const activeTabRoots = [...globalThis.document.querySelectorAll(
        `[data-e2e="${expectedTabSurface}"][role="tabpanel"].semi-tabs-pane-active`,
      )].filter((node) => !isHidden(node));
      // Current desktop profiles can render an empty active tab shell and the
      // same relation's real, platform-named list in a sibling portal.  The
      // dedicated list remains the narrower evidence, so prefer it when it is
      // unique; use the active panel only when that dedicated list is absent.
      // Never broaden this to a generic page or scroll root.
      if (activeTabRoots.length > 1) return failure("platform_changed", "X2N_PLATFORM_CHANGED");
      const root = legacyRoots.length === 1
        ? legacyRoots[0]
        : legacyRoots.length === 0 && activeTabRoots.length === 1
          ? activeTabRoots[0]
          : null;
      if (root === null) return failure("platform_changed", "X2N_PLATFORM_CHANGED");

      const candidates = [];
      const seenCards = new Set();
      for (const anchor of root.querySelectorAll('a[href*="/video/"], a[href*="/note/"]')) {
        if (isHidden(anchor)) continue;
        const card = anchor.closest("[data-x2n-card], article, li, [data-e2e*=\"feed-item\"]") ?? anchor;
        if (seenCards.has(card)) continue;
        seenCards.add(card);
        candidates.push({ anchor, card });
      }
      const selectedCandidates = candidates.slice(0, maxItems);
      const result = base("ready", null);
      result.batch.visible_card_count = selectedCandidates.length;
      const ids = new Set();
      for (const [index, candidate] of selectedCandidates.entries()) {
        const identity = parseCardIdentity(candidate.anchor.getAttribute("href"), locationUrl.origin);
        if (identity === null || !safeId.test(identity.contentId) || ids.has(identity.contentId)) {
          result.errors.push({ card_index: index, code: "X2N_PROVENANCE_INCOMPLETE" });
          continue;
        }
        ids.add(identity.contentId);
        const declaredType = (candidate.card.getAttribute("data-x2n-content-type") ?? "").toLowerCase();
        const contentType = new Set(["image_gallery", "unknown", "video"]).has(declaredType)
          ? declaredType
          : identity.contentType;
        const title = normalizeText(candidate.card.getAttribute("data-x2n-title"));
        result.items.push({ content_id: identity.contentId, content_type: contentType, title });
      }
      if (result.errors.length > 0) {
        result.status = "partial";
        result.code = "X2N_PROVENANCE_INCOMPLETE";
        return result;
      }
      if (result.items.length === 0) {
        result.status = "empty_unverified";
        result.code = "X2N_PROVENANCE_INCOMPLETE";
        result.errors.push({ card_index: null, code: result.code });
        return result;
      }
      result.batch.completion_signal = result.items.length === maxItems
        ? "bounded_limit_reached"
        : candidates.length > maxItems ? "more_available" : "unknown";
      return result;
    } catch {
      return failure("platform_changed", "X2N_PLATFORM_CHANGED");
    }
}

export function validateDouyinVisibleBatch(value) {
  if (!exactKeys(value, ["batch", "code", "errors", "items", "platform", "schema_version", "status"])) {
    throw new TypeError("Douyin visible-batch facts contain unknown or missing fields");
  }
  if (value.platform !== PLATFORM || value.schema_version !== SCHEMA_VERSION || !STATUSES.has(value.status)) {
    throw new TypeError("Douyin visible-batch identity or status mismatch");
  }
  if (!exactKeys(value.batch, ["automatic_scroll", "completion_signal", "explicit_owner_action", "visible_card_count"])) {
    throw new TypeError("Douyin visible-batch boundary is invalid");
  }
  if (
    value.batch.automatic_scroll !== false
    || value.batch.explicit_owner_action !== true
    || !COMPLETION_SIGNALS.has(value.batch.completion_signal)
    || !Number.isInteger(value.batch.visible_card_count)
    || value.batch.visible_card_count < 0
    || value.batch.visible_card_count > 20
    || !Array.isArray(value.items)
    || !Array.isArray(value.errors)
    || value.items.length > 20
    || value.errors.length > 20
  ) throw new TypeError("Douyin visible-batch boundary is unsafe");
  const ids = new Set();
  for (const item of value.items) {
    if (!exactKeys(item, ["content_id", "content_type", "title"])) {
      throw new TypeError("Douyin visible item shape is invalid");
    }
    if (
      !SAFE_ID.test(item.content_id)
      || !new Set(["image_gallery", "unknown", "video"]).has(item.content_type)
      || ids.has(item.content_id)
      || (item.title !== null && (
        typeof item.title !== "string"
        || item.title.length === 0
        || item.title.length > 500
        || item.title !== item.title.replace(/\s+/gu, " ").trim()
        || /[\u0000-\u001F\u007F]/u.test(item.title)
        || /(?:https?|file|data):\/\//iu.test(item.title)
      ))
    ) throw new TypeError("Douyin visible item value is unsafe");
    ids.add(item.content_id);
  }
  const indexes = new Set();
  for (const error of value.errors) {
    if (
      !exactKeys(error, ["card_index", "code"])
      || !ERROR_CODES.has(error.code)
      || (error.card_index !== null && (
        !Number.isInteger(error.card_index)
        || error.card_index < 0
        || error.card_index >= value.batch.visible_card_count
        || indexes.has(error.card_index)
      ))
    ) throw new TypeError("Douyin visible error evidence is invalid");
    if (error.card_index !== null) indexes.add(error.card_index);
  }
  if (value.code !== null && !ERROR_CODES.has(value.code)) throw new TypeError("Douyin visible error code is invalid");
  if (value.status === "ready") {
    if (
      value.code !== null
      || value.errors.length !== 0
      || value.items.length === 0
      || value.items.length !== value.batch.visible_card_count
    ) throw new TypeError("Ready Douyin visible batch is incomplete");
  } else if (
    value.code === null
    || value.errors.length === 0
    || !value.errors.some((error) => error.code === value.code)
  ) {
    throw new TypeError("Non-ready Douyin visible batch lacks error evidence");
  } else if (value.status === "partial") {
    if (
      value.errors.some((error) => error.card_index === null)
      || value.items.length + value.errors.length !== value.batch.visible_card_count
    ) throw new TypeError("Partial Douyin visible batch lacks per-card evidence");
  } else if (
    value.batch.visible_card_count !== 0
    || value.items.length !== 0
    || value.errors.length !== 1
    || value.errors[0].card_index !== null
  ) {
    throw new TypeError("Blocked Douyin visible batch has invalid surface evidence");
  }
  if (value.batch.completion_signal === "bounded_limit_reached" && value.status !== "ready") {
    throw new TypeError("Non-ready Douyin visible batch cannot complete a scope");
  }
  return value;
}
