const NATIVE_HOST = "com.linzecolin.x2n";
const CONTRACT_VERSION = "1.0";
const MESSAGE_TYPES = Object.freeze(new Set(["X2N_HEALTH", "X2N_GET_JOB"]));

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

async function handleMessage(message, sender) {
  if (!trustedSender(sender) || !message || typeof message !== "object" || !MESSAGE_TYPES.has(message.type)) {
    return { ok: false, code: "X2N_EXTENSION_MESSAGE_REJECTED", status: "rejected" };
  }
  try {
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

function configurePanel() {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => undefined);
}

chrome.runtime.onInstalled.addListener(configurePanel);
chrome.runtime.onStartup.addListener(configurePanel);
configurePanel();
