import { recognizePage } from "./page-support.js";
import { PLATFORM_NAMES, unavailableDetailGuidance } from "./sidepanel-guidance.js";

const tabs = [...document.querySelectorAll('[role="tab"]')];
const panels = [...document.querySelectorAll('[role="tabpanel"]')];
const pageContext = document.querySelector("#page-context");
const pageKicker = document.querySelector("#page-kicker");
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
const workflowCard = document.querySelector("#workflow-card");
const workflowEyebrow = document.querySelector("#workflow-eyebrow");
const workflowTitle = document.querySelector("#workflow-title");
const workflowCopy = document.querySelector("#workflow-copy");
const workflowAction = document.querySelector("#workflow-action");
const workflowNote = document.querySelector("#workflow-note");
const workflowStepOne = document.querySelector("#workflow-step-one");
const workflowStepTwo = document.querySelector("#workflow-step-two");
const workflowStepThree = document.querySelector("#workflow-step-three");
const batchSwitcher = document.querySelector("#batch-switcher");
const batchSwitcherSummary = document.querySelector("#batch-switcher-summary");
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
let fallbackTabId = null;
let panelMotion = null;
let lastPageResult = null;
let activeMvpCurrentScope = "xiaohongshu_current_content";

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

function setWorkflowSteps({ first, second, third, active }) {
  const steps = [
    [workflowStepOne, first],
    [workflowStepTwo, second],
    [workflowStepThree, third],
  ];
  for (const [step, label] of steps) {
    if (!step) continue;
    step.textContent = label;
    step.dataset.state = "pending";
  }
  const activeIndex = Math.max(0, Math.min(2, active));
  for (let index = 0; index < activeIndex; index += 1) steps[index][0].dataset.state = "done";
  steps[activeIndex][0].dataset.state = "active";
}

function setWorkflow({ state, eyebrow, title, copy, note, steps }) {
  workflowCard.dataset.state = state;
  workflowEyebrow.textContent = eyebrow;
  workflowTitle.textContent = title;
  workflowCopy.textContent = copy;
  workflowNote.textContent = note;
  setWorkflowSteps(steps);
}

function resetWorkflowActions() {
  workflowAction.hidden = true;
  saveButton.hidden = true;
  saveButton.disabled = true;
  saveMvpCurrentButton.hidden = true;
  saveMvpCurrentButton.disabled = true;
  batchSwitcher.hidden = true;
  saveMvpCurrentSecondButton.disabled = true;
}

function showGenericCurrentAction() {
  workflowAction.hidden = false;
  saveButton.hidden = false;
  saveButton.disabled = false;
  saveButton.textContent = "保存这个页面";
}

function showMvpCurrentAction() {
  const recordingSecondBatch = activeMvpCurrentScope === "xiaohongshu_current_content_second_batch";
  workflowAction.hidden = false;
  saveMvpCurrentButton.hidden = false;
  saveMvpCurrentButton.disabled = false;
  saveMvpCurrentButton.textContent = "保存这条笔记";
  batchSwitcher.hidden = false;
  batchSwitcherSummary.textContent = recordingSecondBatch ? "正在记录第二组" : "第一组已经完成？";
  saveMvpCurrentSecondButton.disabled = false;
  saveMvpCurrentSecondButton.textContent = recordingSecondBatch ? "回到第一组" : "改为记录第二组";
}

function renderPage(result) {
  lastPageResult = result;
  activeTabId = Number.isSafeInteger(result.tabId) ? result.tabId : null;
  if (fallbackTabId !== activeTabId || fallbackFromJobId === null) {
    fallbackFromJobId = null;
    fallbackTabId = null;
    fallbackButton.hidden = true;
  }
  const executablePlatform = result.executable
    && Object.hasOwn(PLATFORM_NAMES, result.platform)
    && activeTabId !== null;
  const xhsMvpCurrentExecutable = result.mvpCurrentEligible === true
    && result.platform === "xiaohongshu"
    && activeTabId !== null;
  currentPageExecutable = executablePlatform;
  mvpCurrentPageExecutable = xhsMvpCurrentExecutable;
  resetWorkflowActions();
  fallbackButton.disabled = fallbackFromJobId === null || captureInFlight || !executablePlatform;
  if (!captureInFlight && fallbackFromJobId === null) {
    captureStatus.textContent = "";
    delete captureStatus.dataset.jobId;
  }
  if (executablePlatform) {
    setPageContextState("ready");
    const platformName = PLATFORM_NAMES[result.platform];
    pageKicker.textContent = "当前内容";
    pageStatus.textContent = `可以保存这篇${platformName}内容`;
    platformStatus.textContent = "只会处理你已经打开的这一篇";
    setWorkflow({
      state: "ready",
      eyebrow: "现在可以保存",
      title: "保存这个页面",
      copy: "点击一次即可。本页不会自动翻页，也不会改变你的账号状态。",
      note: "保存后可以继续浏览；x2n 不会替你执行下一步。",
      steps: { first: "已经打开内容", second: "点击保存", third: "继续浏览", active: 1 },
    });
    showGenericCurrentAction();
    return;
  }
  if (result.guideSurface === "xiaohongshu_favorites_list") {
    setPageContextState("guide");
    pageKicker.textContent = "小红书收藏";
    pageStatus.textContent = "你正在查看收藏清单";
    platformStatus.textContent = "请打开一篇笔记后继续";
    setWorkflow({
      state: "guide",
      eyebrow: "第一步",
      title: "打开一篇想保存的笔记",
      copy: "现在不用点任何灰色按钮。请在左侧点开任意一篇收藏笔记；打开后，这里会自动出现“保存这条笔记”。",
      note: "x2n 不会替你翻页、点开笔记或改变账号状态。",
      steps: { first: "点开一篇收藏笔记", second: "点击保存这条笔记", third: "打开下一篇继续保存", active: 0 },
    });
    return;
  }
  if (xhsMvpCurrentExecutable) {
    const recordingSecondBatch = activeMvpCurrentScope === "xiaohongshu_current_content_second_batch";
    setPageContextState("ready");
    pageKicker.textContent = "小红书笔记";
    pageStatus.textContent = recordingSecondBatch ? "可以保存到第二组" : "可以保存这条笔记";
    platformStatus.textContent = "点击后只记录这篇内容；不会自动处理其他笔记";
    setWorkflow({
      state: "ready",
      eyebrow: recordingSecondBatch ? "第二组" : "第一组",
      title: "保存这条笔记",
      copy: "点击一次即可记录这篇笔记。然后打开下一篇，重复同样的操作。",
      note: "x2n 只记录你亲自打开的内容，不会自动翻页或改变账号状态。",
      steps: { first: "已经打开笔记", second: "点击保存这条笔记", third: "打开下一篇继续保存", active: 1 },
    });
    showMvpCurrentAction();
    return;
  }
  const unavailableGuidance = result.supported ? unavailableDetailGuidance(result.platform) : null;
  if (unavailableGuidance !== null) {
    setPageContextState("blocked");
    pageKicker.textContent = unavailableGuidance.kicker;
    pageStatus.textContent = unavailableGuidance.status;
    platformStatus.textContent = unavailableGuidance.platformStatus;
    setWorkflow({ state: "blocked", ...unavailableGuidance });
    return;
  }
  if (result.supported) {
    setPageContextState("blocked");
    pageKicker.textContent = "当前网站";
    pageStatus.textContent = "请先打开一篇内容";
    platformStatus.textContent = "列表和搜索页不会被自动保存";
    setWorkflow({
      state: "blocked",
      eyebrow: "下一步",
      title: "打开一篇内容后再保存",
      copy: "x2n 只在你已经打开的单条内容页工作。打开内容后，保存按钮会自动出现。",
      note: "页面不符合条件时，x2n 不会猜测或执行任何操作。",
      steps: { first: "打开一篇内容", second: "点击保存", third: "继续浏览", active: 0 },
    });
    return;
  }
  setPageContextState("blocked");
  pageKicker.textContent = "当前页面";
  pageStatus.textContent = "这里暂时不能保存";
  platformStatus.textContent = "请打开一篇支持的网站内容后再试";
  setWorkflow({
    state: "blocked",
    eyebrow: "下一步",
    title: "打开一篇内容后再保存",
    copy: "x2n 不会从列表、搜索结果或不明确的页面猜测要保存什么。",
    note: "打开内容后，本页会自动更新，不需要重启扩展。",
    steps: { first: "打开一篇内容", second: "点击保存", third: "继续浏览", active: 0 },
  });
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
    && /^[0-9a-f-]{36}$/u.test(response.job_id)
    && activeTabId !== null
    && currentPageExecutable;
  fallbackFromJobId = eligible ? response.job_id : null;
  fallbackTabId = eligible ? activeTabId : null;
  fallbackButton.hidden = !eligible;
  fallbackButton.disabled = !eligible || captureInFlight || !currentPageExecutable;
  if (eligible) {
    captureStatus.textContent = "清单处理已停止。你可以改为明确保存当前已打开的页面。";
  }
}

function captureFailureMessage(result) {
  const code = result?.response?.error?.code ?? result?.code;
  const detail = result?.response?.error?.safe_message;
  if (code === "X2N_PLATFORM_CHANGED") return "这篇内容的页面刚刚变化了。请保持它打开，然后再点一次保存。";
  if (code === "X2N_NATIVE_HOST_UNAVAILABLE") return "本机助手暂时没有连接。打开“帮助”，点“重新检查本地助手”。";
  if (
    (code === "POLICY_BLOCKED" || code === "X2N_POLICY_BLOCKED")
    && detail === "Owner input is unavailable"
  ) {
    return "本机正在完成第一次准备。请等几秒，再点一次“保存这条笔记”。";
  }
  return "这次没有保存成功。请保持这篇笔记打开，然后再点一次保存。";
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
    || (ownerMvpCurrent && saveMvpCurrentButton.disabled)
  ) return;
  if (ownerMvpCurrent && explicitFallbackFromJobId !== null) return;
  const requestedTabId = activeTabId;
  captureInFlight = true;
  setBusy(ownerMvpCurrent ? saveMvpCurrentButton : saveButton, true);
  saveButton.disabled = true;
  saveMvpCurrentButton.disabled = true;
  saveMvpCurrentSecondButton.disabled = true;
  captureStatus.textContent = ownerMvpCurrent
    ? "正在保存这条笔记，请不要重复点击。"
    : "正在保存这个页面，请不要重复点击。";
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
      fallbackTabId = null;
      fallbackButton.hidden = true;
      if (result.response?.job_id) {
        captureStatus.dataset.jobId = result.response.job_id;
        captureStatus.textContent = result.response.status === "completed"
          ? (ownerMvpCurrent
            ? "已保存这条笔记。打开下一篇后继续保存。"
            : "当前页面已写入本地知识库")
          : "当前页面已在本地助手中排队";
      } else {
        delete captureStatus.dataset.jobId;
        captureStatus.textContent = ownerMvpCurrent
          ? "已记录这条笔记。打开下一篇后，继续点击“保存这条笔记”。"
          : "当前页面已在本机记录。";
      }
    } else if (result?.code === "X2N_PLATFORM_CHANGED") {
      captureStatus.textContent = "页面结构已变化，已停止且未保存。";
    } else if (result?.status === "active_tab_permission_required") {
      captureStatus.textContent = "请在这个页面点击工具栏中的 x2n 后再试。";
    } else {
      captureStatus.textContent = captureFailureMessage(result);
      renderFallback(result);
    }
  } catch {
    captureStatus.textContent = "本机助手暂时没有连接。打开“帮助”，点“重新检查本地助手”。";
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

function toggleMvpCurrentBatch() {
  if (!mvpCurrentPageExecutable || captureInFlight) return;
  activeMvpCurrentScope = activeMvpCurrentScope === "xiaohongshu_current_content"
    ? "xiaohongshu_current_content_second_batch"
    : "xiaohongshu_current_content";
  renderPage(lastPageResult);
  captureStatus.textContent = activeMvpCurrentScope === "xiaohongshu_current_content_second_batch"
    ? "现在记录第二组。点击“保存这条笔记”继续。"
    : "现在记录第一组。点击“保存这条笔记”继续。";
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
saveMvpCurrentButton.addEventListener("click", () => captureCurrentPage(null, activeMvpCurrentScope));
saveMvpCurrentSecondButton.addEventListener("click", toggleMvpCurrentBatch);
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
