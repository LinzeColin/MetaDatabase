import { recognizePage } from "./page-support.js";
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
import { buildXhsCapturePayload, extractXhsCurrentPage, validateXhsPageFacts } from "./xhs-current-page.js";

const NATIVE_HOST = "com.linzecolin.x2n";
const CONTRACT_VERSION = "1.0";
const MESSAGE_TYPES = Object.freeze(new Set(["X2N_CAPTURE_CURRENT", "X2N_GET_JOB", "X2N_HEALTH"]));
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
  xiaohongshu: Object.freeze({
    buildPayload: buildXhsCapturePayload,
    extract: extractXhsCurrentPage,
    validate: validateXhsPageFacts,
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
  if (!support.executable || !adapter) {
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
  const response = await nativeRequest("capture_current", adapter.buildPayload(facts));
  return {
    ok: response?.accepted === true,
    response,
    status: response?.status ?? "rejected",
  };
}

async function handleMessage(message, sender) {
  if (!trustedSender(sender) || !message || typeof message !== "object" || !MESSAGE_TYPES.has(message.type)) {
    return { ok: false, code: "X2N_EXTENSION_MESSAGE_REJECTED", status: "rejected" };
  }
  try {
    if (message.type === "X2N_CAPTURE_CURRENT") return captureCurrent(message);
    if (message.type === "X2N_HEALTH") {
      const response = await nativeRequest("health", {});
      return { ok: response?.accepted === true, response };
    }
    if (typeof message.jobId !== "string" || !/^[0-9a-f-]{36}$/.test(message.jobId)) {
      return { ok: false, code: "X2N_INVALID_JOB_ID", status: "rejected" };
    }
    const response = await nativeRequest("get_job", { job_id: message.jobId });
    return { ok: response?.accepted === true, response };
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
