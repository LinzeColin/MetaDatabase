import { recognizePage } from "./page-support.js";

const tabs = [...document.querySelectorAll('[role="tab"]')];
const panels = [...document.querySelectorAll('[role="tabpanel"]')];
const pageContext = document.querySelector("#page-context");
const pageStatus = document.querySelector("#page-status");
const platformStatus = document.querySelector("#platform-status");
const hostHealth = document.querySelector("#host-health");
const hostStatus = document.querySelector("#host-status");
const refreshButton = document.querySelector("#refresh-status");
const saveButton = document.querySelector("#save-current");
const saveMvpCurrentButton = document.querySelector("#save-current-mvp");
const saveMvpCurrentSecondButton = document.querySelector("#save-current-mvp-second");
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
  "douyin_favorites",
  "douyin_likes",
]));
const OWNER_MVP_CURRENT_SCOPE_IDS = Object.freeze(new Set([
  "xiaohongshu_current_content",
  "xiaohongshu_current_content_second_batch",
]));
let activeTabId = null;
let currentPageExecutable = false;
let mvpCurrentPageExecutable = false;
let captureInFlight = false;
let pageRefreshGeneration = 0;
let capabilityOutcomes = null;
let fallbackFromJobId = null;
let panelMotion = null;
const EXECUTABLE_PLATFORM_NAMES = Object.freeze({
  bilibili: "哔哩哔哩",
  douyin: "抖音",
  kuaishou: "快手",
  taobao: "淘宝",
  weibo: "微博",
  xiaohongshu: "小红书",
});

function createPanelMotion() {
  if (typeof Element.prototype.animate !== "function" || typeof window.matchMedia !== "function") return null;
  const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
  let reducedMotion = preference.matches;
  const updatePreference = (event) => {
    reducedMotion = event.matches;
  };
  preference.addEventListener("change", updatePreference);
  const animate = (target, y, duration, delay = 0) => {
    if (reducedMotion || !target) return;
    for (const animation of target.getAnimations()) animation.cancel();
    target.animate(
      [
        { opacity: 0, transform: `translateY(${y}px)` },
        { opacity: 1, transform: "translateY(0)" },
      ],
      { delay, duration, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
    );
  };
  animate(document.querySelector(".app-header"), -12, 420);
  animate(document.querySelector(".top-tabs"), -6, 300, 110);
  animate(document.querySelector("#panel-save"), 10, 340, 180);
  window.addEventListener("pagehide", () => preference.removeEventListener("change", updatePreference), { once: true });
  return {
    enterPanel(panel) {
      if (!panel.hidden) animate(panel, 8, 260);
    },
    updateStatus(target) {
      animate(target, 4, 180);
    },
  };
}

function setPageContextState(state) {
  if (!pageContext || pageContext.dataset.state === state) return;
  pageContext.dataset.state = state;
  panelMotion?.updateStatus(pageContext);
}

function setHostHealthState(state) {
  if (!hostHealth || hostHealth.dataset.state === state) return;
  hostHealth.dataset.state = state;
  panelMotion?.updateStatus(hostHealth);
}

function setBusy(control, busy) {
  if (!control) return;
  if (busy) control.setAttribute("aria-busy", "true");
  else control.removeAttribute("aria-busy");
}

function selectTab(selected) {
  for (const tab of tabs) {
    const active = tab === selected;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  }
  const selectedPanelId = selected.getAttribute("aria-controls");
  for (const panel of panels) panel.hidden = panel.id !== selectedPanelId;
  const selectedPanel = panels.find((panel) => panel.id === selectedPanelId);
  if (selectedPanel) panelMotion?.enterPanel(selectedPanel);
}

for (const tab of tabs) {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (!new Set(["ArrowLeft", "ArrowRight", "Home", "End"]).has(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home"
      ? tabs[0]
      : event.key === "End"
        ? tabs.at(-1)
        : tabs[(tabs.indexOf(tab) + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
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
  saveMvpCurrentSecondButton.disabled = !xhsMvpCurrentExecutable;
  saveButton.textContent = saveButton.disabled ? "当前页面暂不可保存" : "保存当前页面";
  saveMvpCurrentButton.textContent = saveMvpCurrentButton.disabled
    ? "批次 1 暂不可用"
    : "记录到 MVP 批次 1";
  saveMvpCurrentSecondButton.textContent = saveMvpCurrentSecondButton.disabled
    ? "批次 2 暂不可用"
    : "记录到 MVP 批次 2";
  fallbackButton.disabled = fallbackFromJobId === null || captureInFlight || !executablePlatform;
  if (!captureInFlight && fallbackFromJobId === null) {
    captureStatus.textContent = "";
    delete captureStatus.dataset.jobId;
  }
  if (executablePlatform) {
    setPageContextState("ready");
    const platformName = EXECUTABLE_PLATFORM_NAMES[result.platform];
    pageStatus.textContent = `已识别 ${platformName} 详情页`;
    platformStatus.textContent = "只会读取你明确选择的这一页";
    return;
  }
  if (xhsMvpCurrentExecutable) {
    setPageContextState("mvp");
    pageStatus.textContent = "小红书详情页可用于 MVP 预备";
    platformStatus.textContent = "一次明确操作只记录私有内容指纹，不写入正式内容";
    return;
  }
  if (result.supported) {
    setPageContextState("blocked");
    pageStatus.textContent = "已识别支持的页面";
    platformStatus.textContent = `${result.platform}：当前页面门禁仍关闭`;
    return;
  }
  setPageContextState("blocked");
  pageStatus.textContent = "当前页面暂不可执行保存";
  platformStatus.textContent = `已安全停止：${result.reason}`;
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
    captureStatus.textContent = "清单处理已停止。你可以改为明确保存当前已打开的页面。";
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
    || !new Set(["douyin_favorites", "douyin_likes"]).has(syncScope.value)
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
    ? "执行已选的 20 项 MVP 操作"
    : mvpEnrollment
      ? "准备已选的 20 项 MVP 输入"
      : "开始已选的合成测试操作";
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
      ? "已授权 MVP：必须恰好 20 项、一次明确操作，不自动滚动。"
      : mvpEnrollment
        ? "私有 MVP 预备：恰好 20 项可见内容，只记录哈希，不写入 SQLite，不自动滚动。"
      : outcome.terminal === "READY_FOR_MVP_ACTIVATION"
      ? "仅限 CI 合成测试，不会启用真实平台请求。"
      : `本地外部门禁已关闭此范围：${outcome.reason_code}`;
  }
  startSyncButton.disabled = syncPayload() === null;
}

function renderCapabilities(result) {
  const outcomes = result?.response?.capabilities?.outcomes;
  if (!Array.isArray(outcomes) || outcomes.length !== 8) {
    capabilityOutcomes = null;
    syncPolicy.textContent = "能力快照不可用，操作保持停止。";
    startSyncButton.disabled = true;
    return;
  }
  const mapped = new Map(outcomes.map((outcome) => [outcome?.scope_id, outcome]));
  if (mapped.size !== 8 || Object.keys(SYNC_SCOPE_RULES).some((scopeId) => !mapped.has(scopeId))) {
    capabilityOutcomes = null;
    syncPolicy.textContent = "能力快照不完整，操作保持停止。";
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

async function captureCurrentPage(explicitFallbackFromJobId = null, ownerMvpScope = null) {
  const ownerMvpCurrent = OWNER_MVP_CURRENT_SCOPE_IDS.has(ownerMvpScope);
  if (
    activeTabId === null
    || captureInFlight
    || (!ownerMvpCurrent && saveButton.disabled)
    || (ownerMvpScope === "xiaohongshu_current_content" && saveMvpCurrentButton.disabled)
    || (ownerMvpScope === "xiaohongshu_current_content_second_batch" && saveMvpCurrentSecondButton.disabled)
  ) return;
  if (ownerMvpCurrent && explicitFallbackFromJobId !== null) return;
  const requestedTabId = activeTabId;
  captureInFlight = true;
  setBusy(ownerMvpScope === "xiaohongshu_current_content"
    ? saveMvpCurrentButton
    : ownerMvpScope === "xiaohongshu_current_content_second_batch"
      ? saveMvpCurrentSecondButton
      : saveButton, true);
  saveButton.disabled = true;
  saveMvpCurrentButton.disabled = true;
  saveMvpCurrentSecondButton.disabled = true;
  captureStatus.textContent = ownerMvpCurrent
    ? "正在读取这一页明确选择的 MVP 当前内容…"
    : "正在读取已净化的当前页面事实…";
  const pendingNotice = setTimeout(() => {
    captureStatus.textContent = "仍在等待本地确认，请不要重复点击";
  }, 15_000);
  try {
    const message = {
      tabId: requestedTabId,
      type: ownerMvpCurrent ? "X2N_CAPTURE_CURRENT_MVP" : "X2N_CAPTURE_CURRENT",
    };
    if (ownerMvpCurrent) message.ownerMvpScope = ownerMvpScope;
    if (explicitFallbackFromJobId !== null) message.fallbackFromJobId = explicitFallbackFromJobId;
    const result = await chrome.runtime.sendMessage(message);
    if (result?.ok && (result.response?.job_id || ownerMvpCurrent)) {
      fallbackFromJobId = null;
      fallbackButton.hidden = true;
      if (result.response?.job_id) {
        captureStatus.dataset.jobId = result.response.job_id;
        captureStatus.textContent = result.response.status === "completed"
          ? (ownerMvpCurrent
            ? `当前内容已写入已启动的 MVP ${ownerMvpScope === "xiaohongshu_current_content" ? "批次 1" : "批次 2"}`
            : "当前页面已写入本地知识库")
          : "当前页面已在本地助手中排队";
      } else {
        delete captureStatus.dataset.jobId;
        captureStatus.textContent = "当前页面指纹已私有记录；未写入 SQLite 正式内容。";
      }
    } else if (result?.code === "X2N_PLATFORM_CHANGED") {
      captureStatus.textContent = "页面结构已变化，已停止且未保存。";
    } else if (result?.status === "active_tab_permission_required") {
      captureStatus.textContent = "请在这个页面点击工具栏中的 x2n 后再试。";
    } else {
      captureStatus.textContent = "当前无法保存，未执行任何操作。";
      renderFallback(result);
    }
  } catch {
    captureStatus.textContent = "当前无法保存，未执行任何操作。";
  } finally {
    clearTimeout(pendingNotice);
    captureInFlight = false;
    setBusy(saveButton, false);
    setBusy(saveMvpCurrentButton, false);
    setBusy(saveMvpCurrentSecondButton, false);
    saveButton.disabled = !(currentPageExecutable && activeTabId === requestedTabId);
    saveMvpCurrentButton.disabled = !(mvpCurrentPageExecutable && activeTabId === requestedTabId);
    saveMvpCurrentSecondButton.disabled = !(mvpCurrentPageExecutable && activeTabId === requestedTabId);
    fallbackButton.disabled = fallbackFromJobId === null || !(currentPageExecutable && activeTabId === requestedTabId);
  }
}

async function startSelectedSync() {
  const payload = syncPayload();
  if (!payload) {
    syncStatus.textContent = "所选范围尚未就绪，未执行任何操作。";
    renderSyncScope();
    return;
  }
  startSyncButton.disabled = true;
  setBusy(startSyncButton, true);
  syncStatus.textContent = payload.activationMode === "mvp_activation_candidate"
    ? "正在读取一组由你选择的、已净化的 20 项内容…"
    : payload.activationMode === "mvp_manifest_enrollment"
      ? "正在读取一组由你选择的、仅保留哈希的 20 项 MVP 预备内容…"
    : "正在请求本地合成测试操作…";
  try {
    const result = await chrome.runtime.sendMessage({ type: "X2N_START_SYNC", ...payload });
    if (result?.ok && (result.response?.job_id || payload.activationMode === "mvp_manifest_enrollment")) {
      syncStatus.textContent = payload.activationMode === "mvp_activation_candidate"
        ? "已完成限定的用户操作并写入本地知识库。"
        : payload.activationMode === "mvp_manifest_enrollment"
          ? "私有 MVP 选择已仅以哈希记录；未写入 SQLite 正式内容。"
        : "本地合成适配操作已完成，平台调用数为 0。";
    } else if (result?.fallbackAvailable) {
      syncStatus.textContent = "清单处理已停止；可以改为单独保存当前页面。";
      renderFallback(result);
    } else {
      syncStatus.textContent = "当前无法处理清单，未执行任何操作。";
    }
  } catch {
    syncStatus.textContent = "当前无法处理清单，未执行任何操作。";
  } finally {
    setBusy(startSyncButton, false);
    renderSyncScope();
  }
}

async function refreshStatus() {
  refreshButton.disabled = true;
  setBusy(refreshButton, true);
  setHostHealthState("checking");
  hostStatus.textContent = "正在检查本地助手…";
  try {
    const result = await Promise.race([
      chrome.runtime.sendMessage({ type: "X2N_HEALTH" }),
      new Promise((resolve) => setTimeout(() => resolve({ ok: false }), 4_000)),
    ]);
    const connected = result?.ok === true;
    setHostHealthState(connected ? "ready" : "blocked");
    hostStatus.textContent = connected ? "本地助手已连接" : "本地助手不可用，未执行任何操作。";
  } catch {
    setHostHealthState("blocked");
    hostStatus.textContent = "本地助手不可用，未执行任何操作。";
  } finally {
    refreshButton.disabled = false;
    setBusy(refreshButton, false);
  }
  await refreshCapabilities();
}

refreshButton.addEventListener("click", refreshStatus);
saveButton.addEventListener("click", () => captureCurrentPage());
saveMvpCurrentButton.addEventListener("click", () => captureCurrentPage(null, "xiaohongshu_current_content"));
saveMvpCurrentSecondButton.addEventListener("click", () => captureCurrentPage(null, "xiaohongshu_current_content_second_batch"));
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
panelMotion = createPanelMotion();
renderSyncScope();
refreshPage().catch(() => undefined);
refreshStatus().catch(() => undefined);
