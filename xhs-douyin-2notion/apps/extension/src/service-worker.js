import { canCaptureXhsMvpCurrent, recognizePage } from "./page-support.js";
import {
  buildBilibiliCapturePayload,
  extractBilibiliCurrentPage,
  validateBilibiliPageFacts,
} from "./bilibili-current-page.js";
import {
  buildDouyinCapturePayload,
  extractDouyinCurrentPage,
  validateDouyinPageFacts,
} from "./douyin-current-page.js";
import {
  extractDouyinVisibleBatch,
  validateDouyinVisibleBatch,
} from "./douyin-visible-lists.js";
import {
  buildKuaishouCapturePayload,
  extractKuaishouCurrentPage,
  validateKuaishouPageFacts,
} from "./kuaishou-current-page.js";
import {
  buildTaobaoCapturePayload,
  extractTaobaoCurrentPage,
  validateTaobaoPageFacts,
} from "./taobao-current-page.js";
import {
  buildWeiboCapturePayload,
  extractWeiboCurrentPage,
  validateWeiboPageFacts,
} from "./weibo-current-page.js";
import { buildXhsCapturePayload, extractXhsCurrentPage, validateXhsPageFacts } from "./xhs-current-page.js";
import { extractXhsFavoritesVisibleBatch, validateXhsFavoritesBatch } from "./xhs-favorites.js";
import { extractXhsLikesVisibleBatch, validateXhsLikesBatch } from "./xhs-likes.js";

const NATIVE_HOST = "com.linzecolin.x2n";
const CONTRACT_VERSION = "1.0";
const MESSAGE_TYPES = Object.freeze(new Set([
  "X2N_CAPTURE_CURRENT",
  "X2N_CAPTURE_CURRENT_MVP",
  "X2N_GET_CAPABILITIES",
  "X2N_GET_JOB",
  "X2N_HEALTH",
  "X2N_START_SYNC",
]));
const MVP_CURRENT_SCOPE_IDS = Object.freeze(new Set([
  "xiaohongshu_current_content",
  "xiaohongshu_current_content_second_batch",
]));
const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;
const SHA256 = /^[0-9a-f]{64}$/u;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const OWNER_MVP_ENROLLMENT_SCOPE_IDS = Object.freeze(new Set([
  "xiaohongshu_favorites",
  "douyin_favorites",
  "douyin_likes",
]));
const SCOPE_MATRIX = Object.freeze({
  bilibili_selected_collection: Object.freeze({
    maxItems: 20,
    platform: "bilibili",
    relation: "saved_current",
    selectedCollection: true,
  }),
  douyin_favorites: Object.freeze({
    maxItems: 80,
    platform: "douyin",
    relation: "favorited",
    selectedCollection: false,
  }),
  douyin_likes: Object.freeze({
    maxItems: 80,
    platform: "douyin",
    relation: "liked",
    selectedCollection: false,
  }),
  kuaishou_selected_collection: Object.freeze({
    maxItems: 20,
    platform: "kuaishou",
    relation: "saved_current",
    selectedCollection: true,
  }),
  taobao_selected_collection: Object.freeze({
    maxItems: 20,
    platform: "taobao",
    relation: "saved_current",
    selectedCollection: true,
  }),
  weibo_selected_collection: Object.freeze({
    maxItems: 20,
    platform: "weibo",
    relation: "favorited",
    selectedCollection: true,
  }),
  xiaohongshu_favorites: Object.freeze({
    maxItems: 80,
    platform: "xiaohongshu",
    relation: "favorited",
    selectedCollection: false,
  }),
  xiaohongshu_likes: Object.freeze({
    maxItems: 80,
    platform: "xiaohongshu",
    relation: "liked",
    selectedCollection: false,
  }),
});
const CURRENT_PAGE_ADAPTERS = Object.freeze({
  bilibili: Object.freeze({
    buildPayload: buildBilibiliCapturePayload,
    extract: extractBilibiliCurrentPage,
    validate: validateBilibiliPageFacts,
  }),
  douyin: Object.freeze({
    buildPayload: buildDouyinCapturePayload,
    extract: extractDouyinCurrentPage,
    validate: validateDouyinPageFacts,
  }),
  kuaishou: Object.freeze({
    buildPayload: buildKuaishouCapturePayload,
    extract: extractKuaishouCurrentPage,
    validate: validateKuaishouPageFacts,
  }),
  taobao: Object.freeze({
    buildPayload: buildTaobaoCapturePayload,
    extract: extractTaobaoCurrentPage,
    validate: validateTaobaoPageFacts,
  }),
  weibo: Object.freeze({
    buildPayload: buildWeiboCapturePayload,
    extract: extractWeiboCurrentPage,
    validate: validateWeiboPageFacts,
  }),
  xiaohongshu: Object.freeze({
    buildPayload: buildXhsCapturePayload,
    extract: extractXhsCurrentPage,
    validate: validateXhsPageFacts,
  }),
});
const MVP_VISIBLE_BATCH_ADAPTERS = Object.freeze({
  douyin_favorites: Object.freeze({
    extract: extractDouyinVisibleBatch,
    mode: "favorites",
    validate: validateDouyinVisibleBatch,
  }),
  douyin_likes: Object.freeze({
    extract: extractDouyinVisibleBatch,
    mode: "likes",
    validate: validateDouyinVisibleBatch,
  }),
  xiaohongshu_favorites: Object.freeze({
    extract: extractXhsFavoritesVisibleBatch,
    validate: validateXhsFavoritesBatch,
  }),
  xiaohongshu_likes: Object.freeze({
    extract: extractXhsLikesVisibleBatch,
    validate: validateXhsLikesBatch,
  }),
});

// Lifecycle-only probe used by restart chaos. Product behavior never reads it;
// every durable status still comes from the Native Host and SQLite.
globalThis.__X2N_LIFECYCLE_PROBE = crypto.randomUUID();

function canonicalJson(value) {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (Number.isSafeInteger(value)) return String(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  throw new TypeError("Unsupported canonical JSON value");
}

async function sha256(value) {
  const bytes = new TextEncoder().encode(canonicalJson(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function nativeRequest(action, payload) {
  const request = {
    action,
    payload,
    payload_hash: await sha256(payload),
    request_id: crypto.randomUUID(),
    schema_version: CONTRACT_VERSION,
    sent_at: new Date().toISOString(),
  };
  return chrome.runtime.sendNativeMessage(NATIVE_HOST, request);
}

async function stagedReleaseArtifactSha256() {
  try {
    const response = await fetch(chrome.runtime.getURL("release_identity.json"), { cache: "no-store" });
    if (!response.ok) return null;
    const identity = await response.json();
    if (
      !identity
      || typeof identity !== "object"
      || Array.isArray(identity)
      || Object.keys(identity).sort().join(",") !== "artifact_sha256,schema_version"
      || identity.schema_version !== "1.0"
      || typeof identity.artifact_sha256 !== "string"
      || !SHA256.test(identity.artifact_sha256)
    ) return null;
    return identity.artifact_sha256;
  } catch {
    return null;
  }
}

function validToken(value) {
  return typeof value === "string" && SAFE_TOKEN.test(value);
}

function fallbackAvailable(response) {
  return response?.accepted === false
    && response?.error?.code === "X2N_ADAPTER_FAILED_FALLBACK_AVAILABLE"
    && response?.error?.next_action === "capture_current"
    && typeof response?.job_id === "string"
    && UUID.test(response.job_id);
}

function buildStartSyncPayload(message) {
  const scope = typeof message.scopeId === "string" ? SCOPE_MATRIX[message.scopeId] : null;
  if (!scope || !Number.isSafeInteger(message.maxItems) || message.maxItems < 1 || message.maxItems > scope.maxItems) {
    return null;
  }
  const mvpActivation = message.activationMode === "mvp_activation_candidate";
  const mvpEnrollment = message.activationMode === "mvp_manifest_enrollment";
  if (mvpActivation && message.maxItems !== 20) return null;
  if (
    mvpEnrollment
    && (message.maxItems !== 20 || !OWNER_MVP_ENROLLMENT_SCOPE_IDS.has(message.scopeId))
  ) return null;
  const base = {
    auto_scroll: false,
    bounded_batch: true,
    change_account_state: false,
    dispatch_version: "1.0",
    max_items: message.maxItems,
    platform: scope.platform,
    relation: scope.relation,
    scope_id: message.scopeId,
    user_gesture: true,
  };
  if (mvpEnrollment) base.owner_mvp_manifest_enrollment = true;
  if (!scope.selectedCollection) {
    if (message.sourceCollectionId !== null && message.sourceCollectionId !== undefined && !validToken(message.sourceCollectionId)) {
      return null;
    }
    return { ...base, source_collection_id: message.sourceCollectionId ?? null };
  }
  if (
    !validToken(message.ownerSelectionId)
    || !validToken(message.sourceIdentity)
    || typeof message.ownerSelectionManifestSha256 !== "string"
    || !SHA256.test(message.ownerSelectionManifestSha256)
  ) return null;
  return {
    ...base,
    owner_selection_id: message.ownerSelectionId,
    owner_selection_manifest_sha256: message.ownerSelectionManifestSha256,
    source_identity: message.sourceIdentity,
  };
}

async function activeOwnerTab(tabId) {
  if (!Number.isSafeInteger(tabId) || tabId <= 0) throw new Error("invalid tab");
  const [focusedTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const tab = await chrome.tabs.get(tabId);
  if (!tab.active || focusedTab?.id !== tab.id || focusedTab.windowId !== tab.windowId) {
    throw new Error("active tab mismatch");
  }
  return tab;
}

async function captureVisibleMvpBatch(message, payload) {
  const adapter = MVP_VISIBLE_BATCH_ADAPTERS[payload.scope_id];
  const mvpActivation = message.activationMode === "mvp_activation_candidate";
  const mvpEnrollment = message.activationMode === "mvp_manifest_enrollment";
  if (!adapter || payload.max_items !== 20 || (!mvpActivation && !mvpEnrollment)) {
    return { ok: false, code: "X2N_POLICY_BLOCKED", status: "platform_disabled" };
  }
  let tab;
  try {
    tab = await activeOwnerTab(message.tabId);
  } catch {
    return { ok: false, code: "X2N_POLICY_BLOCKED", status: "active_tab_unavailable" };
  }
  let injected;
  try {
    injected = await chrome.scripting.executeScript({
      args: [{
        maxItems: 20,
        mode: adapter.mode,
        ownerGesture: true,
        scopeMode: "owner_mvp_20",
      }],
      func: adapter.extract,
      target: { tabId: tab.id },
      world: "ISOLATED",
    });
  } catch {
    return { ok: false, code: "X2N_POLICY_BLOCKED", status: "active_tab_permission_required" };
  }
  if (!Array.isArray(injected) || injected.length !== 1) {
    return { ok: false, code: "X2N_PLATFORM_CHANGED", status: "platform_changed" };
  }
  try {
    const current = await activeOwnerTab(tab.id);
    if (current.url !== tab.url) throw new Error("active tab changed");
    const facts = adapter.validate(injected[0]?.result);
    if (facts.status !== "ready" || facts.items.length !== 20) {
      return { ok: false, code: facts.code ?? "X2N_PROVENANCE_INCOMPLETE", status: facts.status };
    }
    const response = await nativeRequest("start_sync", { ...payload, visible_batch: facts });
    return {
      ok: response?.accepted === true,
      response,
      fallbackAvailable: fallbackAvailable(response),
      status: response?.status ?? "rejected",
    };
  } catch {
    return { ok: false, code: "X2N_PLATFORM_CHANGED", status: "platform_changed" };
  }
}

function trustedSender(sender) {
  return sender.id === chrome.runtime.id
    && sender.url === chrome.runtime.getURL("sidepanel.html");
}

async function captureCurrent(message) {
  if (!Number.isSafeInteger(message.tabId) || message.tabId <= 0) {
    return { ok: false, code: "X2N_INVALID_INPUT", status: "rejected" };
  }
  let tab;
  try {
    const [focusedTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    tab = await chrome.tabs.get(message.tabId);
    if (!tab.active || focusedTab?.id !== tab.id || focusedTab.windowId !== tab.windowId) {
      throw new Error("active tab mismatch");
    }
  } catch {
    return { ok: false, code: "X2N_POLICY_BLOCKED", status: "active_tab_unavailable" };
  }
  const support = recognizePage(tab.url ?? "");
  const adapter = CURRENT_PAGE_ADAPTERS[support.platform];
  const mvpCurrentEligible = canCaptureXhsMvpCurrent(message, support);
  if ((!support.executable && !mvpCurrentEligible) || !adapter) {
    return { ok: false, code: "X2N_POLICY_BLOCKED", status: "platform_disabled" };
  }

  let injected;
  try {
    injected = await chrome.scripting.executeScript({
      func: adapter.extract,
      target: { tabId: tab.id },
      world: "ISOLATED",
    });
  } catch {
    return { ok: false, code: "X2N_POLICY_BLOCKED", status: "active_tab_permission_required" };
  }
  if (!Array.isArray(injected) || injected.length !== 1) {
    return { ok: false, code: "X2N_PLATFORM_CHANGED", status: "platform_changed" };
  }

  try {
    const [focusedTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    const currentTab = await chrome.tabs.get(message.tabId);
    if (
      !currentTab.active
      || focusedTab?.id !== currentTab.id
      || focusedTab.windowId !== currentTab.windowId
      || currentTab.url !== tab.url
    ) throw new Error("active tab changed during capture");
  } catch {
    return { ok: false, code: "X2N_POLICY_BLOCKED", status: "active_tab_changed" };
  }

  let facts;
  try {
    facts = adapter.validate(injected[0]?.result);
  } catch {
    return { ok: false, code: "X2N_PLATFORM_CHANGED", status: "platform_changed" };
  }
  if (facts.status === "platform_changed") {
    return { ok: false, code: facts.code, reason: facts.reason, status: facts.status };
  }
  const payload = adapter.buildPayload(facts);
  if (message.type === "X2N_CAPTURE_CURRENT_MVP") {
    if (!mvpCurrentEligible || !MVP_CURRENT_SCOPE_IDS.has(message.ownerMvpScope)) {
      return { ok: false, code: "X2N_POLICY_BLOCKED", status: "platform_disabled" };
    }
    payload.owner_mvp_scope = message.ownerMvpScope;
  }
  if (message.fallbackFromJobId !== undefined) {
    if (typeof message.fallbackFromJobId !== "string" || !UUID.test(message.fallbackFromJobId)) {
      return { ok: false, code: "X2N_INVALID_INPUT", status: "rejected" };
    }
    payload.fallback_from_job_id = message.fallbackFromJobId;
  }
  const response = await nativeRequest("capture_current", payload);
  return {
    ok: response?.accepted === true,
    response,
    fallbackAvailable: fallbackAvailable(response),
    status: response?.status ?? "rejected",
  };
}

async function handleMessage(message, sender) {
  if (!trustedSender(sender) || !message || typeof message !== "object" || !MESSAGE_TYPES.has(message.type)) {
    return { ok: false, code: "X2N_EXTENSION_MESSAGE_REJECTED", status: "rejected" };
  }
  try {
    if (message.type === "X2N_CAPTURE_CURRENT" || message.type === "X2N_CAPTURE_CURRENT_MVP") {
      return captureCurrent(message);
    }
    if (message.type === "X2N_GET_CAPABILITIES") {
      const response = await nativeRequest("get_capabilities", { capability_contract_version: "1.0" });
      return { ok: response?.accepted === true, response };
    }
    if (message.type === "X2N_HEALTH") {
      const artifactSha256 = await stagedReleaseArtifactSha256();
      const response = await nativeRequest(
        "health",
        artifactSha256 === null
          ? {}
          : { mvp_browser_handshake: true, mvp_release_artifact_sha256: artifactSha256 },
      );
      return { ok: response?.accepted === true, response };
    }
    if (message.type === "X2N_START_SYNC") {
      const payload = buildStartSyncPayload(message);
      if (!payload) return { ok: false, code: "X2N_INVALID_INPUT", status: "rejected" };
      if (
        new Set(["mvp_activation_candidate", "mvp_manifest_enrollment"]).has(message.activationMode)
        && new Set(["douyin", "xiaohongshu"]).has(payload.platform)
      ) {
        return captureVisibleMvpBatch(message, payload);
      }
      const response = await nativeRequest("start_sync", payload);
      return {
        ok: response?.accepted === true,
        response,
        fallbackAvailable: fallbackAvailable(response),
        status: response?.status ?? "rejected",
      };
    }
    if (typeof message.jobId !== "string" || !/^[0-9a-f-]{36}$/.test(message.jobId)) {
      return { ok: false, code: "X2N_INVALID_JOB_ID", status: "rejected" };
    }
    const response = await nativeRequest("get_job", { job_id: message.jobId });
    return { ok: response?.accepted === true, response, fallbackAvailable: fallbackAvailable(response) };
  } catch {
    return { ok: false, code: "X2N_NATIVE_HOST_UNAVAILABLE", status: "unavailable" };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender)
    .then(sendResponse)
    .catch(() => sendResponse({
      ok: false,
      code: "X2N_EXTENSION_FAIL_CLOSED",
      status: "unavailable",
    }));
  // Keep the message channel open without relying on Promise-listener support
  // in older Chrome versions covered by minimum_chrome_version.
  return true;
});

chrome.action.onClicked.addListener((tab) => {
  if (Number.isSafeInteger(tab?.id)) chrome.sidePanel.open({ tabId: tab.id }).catch(() => undefined);
});
