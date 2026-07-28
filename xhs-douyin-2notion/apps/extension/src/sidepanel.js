import { recognizePage } from "./page-support.js";

const tabs = [...document.querySelectorAll('[role="tab"]')];
const panels = [...document.querySelectorAll('[role="tabpanel"]')];
const pageStatus = document.querySelector("#page-status");
const platformStatus = document.querySelector("#platform-status");
const hostStatus = document.querySelector("#host-status");
const refreshButton = document.querySelector("#refresh-status");
const saveButton = document.querySelector("#save-current");
const captureStatus = document.querySelector("#capture-status");
const fallbackButton = document.querySelector("#capture-fallback");
const syncPolicy = document.querySelector("#sync-policy");
const syncScope = document.querySelector("#sync-scope");
const syncMaxItems = document.querySelector("#sync-max-items");
const syncSourceCollection = document.querySelector("#sync-source-collection");
const selectedCollectionFields = document.querySelector("#selected-collection-fields");
const ownerSelectionId = document.querySelector("#owner-selection-id");
const ownerSelectionManifest = document.querySelector("#owner-selection-manifest");
const sourceIdentity = document.querySelector("#source-identity");
const startSyncButton = document.querySelector("#start-sync");
const syncStatus = document.querySelector("#sync-status");
const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;
const SHA256 = /^[0-9a-f]{64}$/u;
const SYNC_SCOPE_RULES = Object.freeze({
  bilibili_selected_collection: Object.freeze({ maxItems: 20, selectedCollection: true }),
  douyin_favorites: Object.freeze({ maxItems: 80, selectedCollection: false }),
  douyin_likes: Object.freeze({ maxItems: 80, selectedCollection: false }),
  kuaishou_selected_collection: Object.freeze({ maxItems: 20, selectedCollection: true }),
  taobao_selected_collection: Object.freeze({ maxItems: 20, selectedCollection: true }),
  weibo_selected_collection: Object.freeze({ maxItems: 20, selectedCollection: true }),
  xiaohongshu_favorites: Object.freeze({ maxItems: 80, selectedCollection: false }),
  xiaohongshu_likes: Object.freeze({ maxItems: 80, selectedCollection: false }),
});
let activeTabId = null;
let currentPageExecutable = false;
let captureInFlight = false;
let pageRefreshGeneration = 0;
let capabilityOutcomes = null;
let fallbackFromJobId = null;
const EXECUTABLE_PLATFORM_NAMES = Object.freeze({
  bilibili: "Bilibili",
  douyin: "Douyin",
  kuaishou: "Kuaishou",
  taobao: "Taobao",
  weibo: "Weibo",
  xiaohongshu: "Xiaohongshu",
});

function selectTab(selected) {
  for (const tab of tabs) {
    const active = tab === selected;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  }
  for (const panel of panels) panel.hidden = panel.id !== selected.getAttribute("aria-controls");
}

for (const tab of tabs) {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (!new Set(["ArrowLeft", "ArrowRight"]).has(event.key)) return;
    event.preventDefault();
    const offset = event.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(tabs.indexOf(tab) + offset + tabs.length) % tabs.length];
    selectTab(next);
    next.focus();
  });
}

async function activePage() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    return { ...recognizePage(tab?.url ?? ""), tabId: tab?.id ?? null };
  } catch {
    return { ...recognizePage(""), tabId: null };
  }
}

function renderPage(result) {
  activeTabId = Number.isSafeInteger(result.tabId) ? result.tabId : null;
  const executablePlatform = result.executable
    && Object.hasOwn(EXECUTABLE_PLATFORM_NAMES, result.platform)
    && activeTabId !== null;
  currentPageExecutable = executablePlatform;
  saveButton.disabled = !executablePlatform;
  saveButton.textContent = saveButton.disabled ? "Save unavailable" : "Save current page";
  fallbackButton.disabled = fallbackFromJobId === null || captureInFlight || !executablePlatform;
  if (!captureInFlight && fallbackFromJobId === null) {
    captureStatus.textContent = "";
    delete captureStatus.dataset.jobId;
  }
  if (executablePlatform) {
    const platformName = EXECUTABLE_PLATFORM_NAMES[result.platform];
    pageStatus.textContent = `${platformName} detail page recognized`;
    platformStatus.textContent = "Only this explicitly selected current page will be read";
    return;
  }
  if (result.supported) {
    pageStatus.textContent = "Supported page recognized";
    platformStatus.textContent = `${result.platform}: current-page gate remains disabled`;
    return;
  }
  pageStatus.textContent = "No executable save for this page";
  platformStatus.textContent = result.reason;
}

async function refreshPage() {
  const generation = ++pageRefreshGeneration;
  const result = await activePage();
  if (generation === pageRefreshGeneration) renderPage(result);
}

function selectedScopeRule() {
  return SYNC_SCOPE_RULES[syncScope.value] ?? null;
}

function selectedOutcome() {
  return capabilityOutcomes?.get(syncScope.value) ?? null;
}

function renderFallback(result) {
  const response = result?.response;
  const eligible = result?.fallbackAvailable === true
    && typeof response?.job_id === "string"
    && /^[0-9a-f-]{36}$/u.test(response.job_id);
  fallbackFromJobId = eligible ? response.job_id : null;
  fallbackButton.hidden = !eligible;
  fallbackButton.disabled = !eligible || captureInFlight || !currentPageExecutable;
  if (eligible) {
    captureStatus.textContent = "List dispatch stopped. You can explicitly save the currently open page instead.";
  }
}

function syncPayload() {
  const rule = selectedScopeRule();
  const maxItems = Number(syncMaxItems.value);
  if (!rule || !Number.isSafeInteger(maxItems) || maxItems < 1 || maxItems > rule.maxItems) return null;
  const outcome = selectedOutcome();
  if (
    outcome?.terminal !== "READY_FOR_MVP_ACTIVATION"
    || outcome?.reason_code !== "CI_SYNTH_READY"
    || outcome?.feature_flag !== "ci_synthetic_only"
  ) return null;
  if (!rule.selectedCollection) {
    const sourceCollectionId = syncSourceCollection.value.trim();
    if (sourceCollectionId && !SAFE_TOKEN.test(sourceCollectionId)) return null;
    return {
      maxItems,
      scopeId: syncScope.value,
      sourceCollectionId: sourceCollectionId || null,
    };
  }
  const selectionId = ownerSelectionId.value.trim();
  const manifest = ownerSelectionManifest.value.trim();
  const source = sourceIdentity.value.trim();
  if (!SAFE_TOKEN.test(selectionId) || !SAFE_TOKEN.test(source) || !SHA256.test(manifest)) return null;
  return {
    maxItems,
    ownerSelectionId: selectionId,
    ownerSelectionManifestSha256: manifest,
    scopeId: syncScope.value,
    sourceIdentity: source,
  };
}

function renderSyncScope() {
  const rule = selectedScopeRule();
  const selectedCollection = rule?.selectedCollection === true;
  selectedCollectionFields.hidden = !selectedCollection;
  syncSourceCollection.disabled = selectedCollection;
  if (selectedCollection) syncSourceCollection.value = "";
  const maximum = String(rule?.maxItems ?? 1);
  syncMaxItems.max = maximum;
  if (!Number.isSafeInteger(Number(syncMaxItems.value)) || Number(syncMaxItems.value) > Number(maximum)) {
    syncMaxItems.value = maximum;
  }
  const outcome = selectedOutcome();
  if (outcome) {
    syncPolicy.textContent = outcome.terminal === "READY_FOR_MVP_ACTIVATION"
      ? "CI-synthetic dispatch only. This does not enable any live platform request."
      : `Scope disabled by local external gate: ${outcome.reason_code}`;
  }
  startSyncButton.disabled = syncPayload() === null;
}

function renderCapabilities(result) {
  const outcomes = result?.response?.capabilities?.outcomes;
  if (!Array.isArray(outcomes) || outcomes.length !== 8) {
    capabilityOutcomes = null;
    syncPolicy.textContent = "Capability snapshot unavailable — dispatch remains stopped.";
    startSyncButton.disabled = true;
    return;
  }
  const mapped = new Map(outcomes.map((outcome) => [outcome?.scope_id, outcome]));
  if (mapped.size !== 8 || Object.keys(SYNC_SCOPE_RULES).some((scopeId) => !mapped.has(scopeId))) {
    capabilityOutcomes = null;
    syncPolicy.textContent = "Capability snapshot is incomplete — dispatch remains stopped.";
    startSyncButton.disabled = true;
    return;
  }
  capabilityOutcomes = mapped;
  renderSyncScope();
}

async function refreshCapabilities() {
  try {
    const result = await chrome.runtime.sendMessage({ type: "X2N_GET_CAPABILITIES" });
    renderCapabilities(result);
  } catch {
    renderCapabilities(null);
  }
}

async function captureCurrentPage(explicitFallbackFromJobId = null) {
  if (activeTabId === null || saveButton.disabled || captureInFlight) return;
  const requestedTabId = activeTabId;
  captureInFlight = true;
  saveButton.disabled = true;
  captureStatus.textContent = "Reading sanitized current-page facts…";
  const pendingNotice = setTimeout(() => {
    captureStatus.textContent = "Still waiting for local confirmation — do not retry";
  }, 15_000);
  try {
    const message = { tabId: requestedTabId, type: "X2N_CAPTURE_CURRENT" };
    if (explicitFallbackFromJobId !== null) message.fallbackFromJobId = explicitFallbackFromJobId;
    const result = await chrome.runtime.sendMessage(message);
    if (result?.ok && result.response?.job_id) {
      fallbackFromJobId = null;
      fallbackButton.hidden = true;
      captureStatus.dataset.jobId = result.response.job_id;
      captureStatus.textContent = result.response.status === "completed"
        ? "Current page committed to the canonical store"
        : "Current page queued in the local companion";
    } else if (result?.code === "X2N_PLATFORM_CHANGED") {
      captureStatus.textContent = "Page structure changed — capture stopped without saving";
    } else if (result?.status === "active_tab_permission_required") {
      captureStatus.textContent = "Reopen x2n from the toolbar on this page, then try again";
    } else {
      captureStatus.textContent = "Capture unavailable — no action executed";
      renderFallback(result);
    }
  } catch {
    captureStatus.textContent = "Capture unavailable — no action executed";
  } finally {
    clearTimeout(pendingNotice);
    captureInFlight = false;
    saveButton.disabled = !(currentPageExecutable && activeTabId === requestedTabId);
    fallbackButton.disabled = fallbackFromJobId === null || !(currentPageExecutable && activeTabId === requestedTabId);
  }
}

async function startSelectedSync() {
  const payload = syncPayload();
  if (!payload) {
    syncStatus.textContent = "Selected scope is not ready — no action executed.";
    renderSyncScope();
    return;
  }
  startSyncButton.disabled = true;
  syncStatus.textContent = "Requesting local synthetic dispatch…";
  try {
    const result = await chrome.runtime.sendMessage({ type: "X2N_START_SYNC", ...payload });
    if (result?.ok && result.response?.job_id) {
      syncStatus.textContent = "Local synthetic adapter dispatch completed with zero platform calls.";
    } else if (result?.fallbackAvailable) {
      syncStatus.textContent = "List dispatch stopped; a separate current-page fallback is available.";
      renderFallback(result);
    } else {
      syncStatus.textContent = "Sync unavailable — no action executed.";
    }
  } catch {
    syncStatus.textContent = "Sync unavailable — no action executed.";
  } finally {
    renderSyncScope();
  }
}

async function refreshStatus() {
  refreshButton.disabled = true;
  hostStatus.textContent = "Checking local companion…";
  try {
    const result = await Promise.race([
      chrome.runtime.sendMessage({ type: "X2N_HEALTH" }),
      new Promise((resolve) => setTimeout(() => resolve({ ok: false }), 4_000)),
    ]);
    hostStatus.textContent = result?.ok ? "Local companion connected" : "Local companion unavailable — no action executed";
  } catch {
    hostStatus.textContent = "Local companion unavailable — no action executed";
  } finally {
    refreshButton.disabled = false;
  }
  await refreshCapabilities();
}

refreshButton.addEventListener("click", refreshStatus);
saveButton.addEventListener("click", () => captureCurrentPage());
fallbackButton.addEventListener("click", () => {
  if (fallbackFromJobId !== null) captureCurrentPage(fallbackFromJobId);
});
startSyncButton.addEventListener("click", startSelectedSync);
for (const control of [syncScope, syncMaxItems, syncSourceCollection, ownerSelectionId, ownerSelectionManifest, sourceIdentity]) {
  control.addEventListener("input", renderSyncScope);
  control.addEventListener("change", renderSyncScope);
}
chrome.tabs.onActivated.addListener(() => {
  refreshPage().catch(() => undefined);
});
chrome.tabs.onUpdated.addListener((_tabId, changeInfo) => {
  if (changeInfo.status === "complete" || typeof changeInfo.url === "string") {
    refreshPage().catch(() => undefined);
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    refreshPage().catch(() => undefined);
    refreshStatus().catch(() => undefined);
  }
});

selectTab(tabs[0]);
renderSyncScope();
refreshPage().catch(() => undefined);
refreshStatus().catch(() => undefined);
