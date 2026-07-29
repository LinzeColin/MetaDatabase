import { recognizePage } from "./page-support.js";

const tabs = [...document.querySelectorAll('[role="tab"]')];
const panels = [...document.querySelectorAll('[role="tabpanel"]')];
const pageStatus = document.querySelector("#page-status");
const platformStatus = document.querySelector("#platform-status");
const hostStatus = document.querySelector("#host-status");
const refreshButton = document.querySelector("#refresh-status");
const saveButton = document.querySelector("#save-current");
const saveMvpCurrentButton = document.querySelector("#save-current-mvp");
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
const OWNER_MVP_ENROLLMENT_SCOPE_IDS = Object.freeze(new Set([
  "xiaohongshu_favorites",
  "douyin_favorites",
  "douyin_likes",
]));
let activeTabId = null;
let currentPageExecutable = false;
let mvpCurrentPageExecutable = false;
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
  const xhsMvpCurrentExecutable = result.mvpCurrentEligible === true
    && result.platform === "xiaohongshu"
    && activeTabId !== null;
  currentPageExecutable = executablePlatform;
  mvpCurrentPageExecutable = xhsMvpCurrentExecutable;
  saveButton.disabled = !executablePlatform;
  saveMvpCurrentButton.disabled = !xhsMvpCurrentExecutable;
  saveButton.textContent = saveButton.disabled ? "Save unavailable" : "Save current page";
  saveMvpCurrentButton.textContent = saveMvpCurrentButton.disabled
    ? "MVP current-content unavailable"
    : "Record this page for direct MVP preparation or armed capture";
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
  if (xhsMvpCurrentExecutable) {
    pageStatus.textContent = "Xiaohongshu detail page ready for direct MVP";
    platformStatus.textContent = "One explicit action records only a private content fingerprint before arming";
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

function isMvpEnrollmentScope(scopeId, outcome) {
  return outcome?.terminal === "READY_FOR_MVP_ACTIVATION"
    && outcome?.reason_code === "CI_SYNTH_READY"
    && outcome?.feature_flag === "ci_synthetic_only"
    && OWNER_MVP_ENROLLMENT_SCOPE_IDS.has(scopeId);
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
  ) return null;
  const mvpActivation = outcome.feature_flag === "mvp_activation_candidate";
  const mvpEnrollment = isMvpEnrollmentScope(syncScope.value, outcome);
  const synthetic = outcome.feature_flag === "ci_synthetic_only";
  if (!mvpActivation && !synthetic) return null;
  if (mvpActivation && (
    maxItems !== 20
    || !new Set(["xiaohongshu_favorites", "xiaohongshu_likes", "douyin_favorites", "douyin_likes"]).has(syncScope.value)
  )) return null;
  if (mvpEnrollment && (maxItems !== 20 || activeTabId === null)) return null;
  if (!rule.selectedCollection) {
    const sourceCollectionId = syncSourceCollection.value.trim();
    if (sourceCollectionId && !SAFE_TOKEN.test(sourceCollectionId)) return null;
    return {
      activationMode: mvpActivation
        ? "mvp_activation_candidate"
        : mvpEnrollment
          ? "mvp_manifest_enrollment"
          : "ci_synthetic_only",
      maxItems,
      scopeId: syncScope.value,
      sourceCollectionId: sourceCollectionId || null,
      tabId: mvpActivation || mvpEnrollment ? activeTabId : undefined,
    };
  }
  const selectionId = ownerSelectionId.value.trim();
  const manifest = ownerSelectionManifest.value.trim();
  const source = sourceIdentity.value.trim();
  if (!SAFE_TOKEN.test(selectionId) || !SAFE_TOKEN.test(source) || !SHA256.test(manifest)) return null;
  return {
    activationMode: "ci_synthetic_only",
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
  const outcome = selectedOutcome();
  const mvpActivation = outcome?.feature_flag === "mvp_activation_candidate";
  const mvpEnrollment = isMvpEnrollmentScope(syncScope.value, outcome);
  startSyncButton.textContent = mvpActivation
    ? "Run owner-selected 20-item MVP action"
    : mvpEnrollment
      ? "Prepare owner-selected 20-item MVP input"
    : "Start selected synthetic dispatch";
  const maximum = String(mvpActivation || mvpEnrollment ? 20 : (rule?.maxItems ?? 1));
  syncMaxItems.max = maximum;
  if (
    !Number.isSafeInteger(Number(syncMaxItems.value))
    || Number(syncMaxItems.value) > Number(maximum)
    || ((mvpActivation || mvpEnrollment) && Number(syncMaxItems.value) !== 20)
  ) {
    syncMaxItems.value = maximum;
  }
  if (outcome) {
    syncPolicy.textContent = outcome.feature_flag === "mvp_activation_candidate"
      ? "Owner-authorized MVP action: exactly 20 items, one explicit gesture, no automatic scroll."
      : mvpEnrollment
        ? "Private MVP preparation: exactly 20 visible items, hashes only, no Canonical write or automatic scroll."
      : outcome.terminal === "READY_FOR_MVP_ACTIVATION"
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

async function captureCurrentPage(explicitFallbackFromJobId = null, ownerMvpCurrent = false) {
  if (
    activeTabId === null
    || captureInFlight
    || (!ownerMvpCurrent && saveButton.disabled)
    || (ownerMvpCurrent && saveMvpCurrentButton.disabled)
  ) return;
  if (ownerMvpCurrent && explicitFallbackFromJobId !== null) return;
  const requestedTabId = activeTabId;
  captureInFlight = true;
  saveButton.disabled = true;
  saveMvpCurrentButton.disabled = true;
  captureStatus.textContent = ownerMvpCurrent
    ? "Reading one explicitly selected MVP current-content page…"
    : "Reading sanitized current-page facts…";
  const pendingNotice = setTimeout(() => {
    captureStatus.textContent = "Still waiting for local confirmation — do not retry";
  }, 15_000);
  try {
    const message = {
      tabId: requestedTabId,
      type: ownerMvpCurrent ? "X2N_CAPTURE_CURRENT_MVP" : "X2N_CAPTURE_CURRENT",
    };
    if (explicitFallbackFromJobId !== null) message.fallbackFromJobId = explicitFallbackFromJobId;
    const result = await chrome.runtime.sendMessage(message);
    if (result?.ok && (result.response?.job_id || ownerMvpCurrent)) {
      fallbackFromJobId = null;
      fallbackButton.hidden = true;
      if (result.response?.job_id) {
        captureStatus.dataset.jobId = result.response.job_id;
        captureStatus.textContent = result.response.status === "completed"
          ? (ownerMvpCurrent
            ? "Current content committed to the armed MVP scope"
            : "Current page committed to the canonical store")
          : "Current page queued in the local companion";
      } else {
        delete captureStatus.dataset.jobId;
        captureStatus.textContent = "Current page fingerprint recorded privately; no Canonical content was written.";
      }
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
    saveMvpCurrentButton.disabled = !(mvpCurrentPageExecutable && activeTabId === requestedTabId);
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
  syncStatus.textContent = payload.activationMode === "mvp_activation_candidate"
    ? "Reading one owner-selected, sanitized 20-item batch…"
    : payload.activationMode === "mvp_manifest_enrollment"
      ? "Reading one owner-selected, hash-only 20-item MVP preparation batch…"
    : "Requesting local synthetic dispatch…";
  try {
    const result = await chrome.runtime.sendMessage({ type: "X2N_START_SYNC", ...payload });
    if (result?.ok && (result.response?.job_id || payload.activationMode === "mvp_manifest_enrollment")) {
      syncStatus.textContent = payload.activationMode === "mvp_activation_candidate"
        ? "Bounded owner action committed to the local canonical store."
        : payload.activationMode === "mvp_manifest_enrollment"
          ? "Private MVP selection recorded with hashes only; no Canonical content was written."
        : "Local synthetic adapter dispatch completed with zero platform calls.";
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
saveMvpCurrentButton.addEventListener("click", () => captureCurrentPage(null, true));
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
